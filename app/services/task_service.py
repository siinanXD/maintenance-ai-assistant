"""Task service layer.

All task business logic lives here. Routes should call these functions
and do nothing more than validate input, call the service, and return a response.
"""

import logging
from datetime import UTC, date, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Department, ErrorEntry, Priority, Role, Task, TaskStatus
from app.security import has_dashboard_permission
from app.services.error_service import visible_errors_query
from app.services.knowledge_service import (
    delete_source_knowledge_document,
    mark_task_knowledge_stale,
)
from app.services.operations_tracking_service import record_event

logger = logging.getLogger(__name__)


def linked_error_entry(value, user):
    """Return the incident a work order is raised for, or ``None`` when unset.

    Raises ``PermissionError`` when the user may not read incidents or the
    incident belongs to another department, ``ValueError`` when it is unknown.
    """
    if value in (None, ""):
        return None
    try:
        entry_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("error_entry_id must be a number") from exc
    if not has_dashboard_permission(user, "errors", "view"):
        raise PermissionError("Keine Berechtigung fuer Stoerungen")
    entry = visible_errors_query(user).filter(ErrorEntry.id == entry_id).first()
    if entry is None:
        raise ValueError("error_entry_id does not reference a visible incident")
    return entry


def parse_date(value):
    """Parse an ISO date string into a date object, defaulting to today."""
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("due_date must use YYYY-MM-DD") from exc


def parse_enum(enum_cls, value, default=None):
    """Parse an enum value and raise a descriptive error on invalid input."""
    if not value:
        return default
    try:
        return enum_cls(value)
    except ValueError as exc:
        valid = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"Invalid value '{value}'. Use one of: {valid}") from exc


def validate_task_payload(data, require_title=True):
    """Validate task payload fields before create or update."""
    if require_title and not data.get("title"):
        raise ValueError("title is required")
    if "title" in data and not str(data["title"]).strip():
        raise ValueError("title must not be empty")


def parse_non_negative_int(value, field_name, default=0):
    """Parse a non-negative integer task metric field."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must not be negative")
    return parsed


def minutes_between(start, end):
    """Return elapsed minutes for task timestamps with mixed tz awareness."""
    normalized_start = start.astimezone(UTC).replace(tzinfo=None) if start.tzinfo else start
    normalized_end = end.astimezone(UTC).replace(tzinfo=None) if end.tzinfo else end
    return (normalized_end - normalized_start).total_seconds() / 60


def task_event_state(task):
    """Return compact task state for audit old/new values."""
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value if task.status else "",
        "priority": task.priority.value if task.priority else "",
        "department_id": task.department_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "planned_minutes": task.planned_minutes,
        "actual_minutes": task.actual_minutes,
        "blocked": bool(task.blocked_reason),
        "current_worker_id": task.current_worker_id,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def get_department_for_payload(data, user):
    """Resolve the target department from request data and enforce ownership.

    Raises PermissionError if a non-admin tries to write to another department.
    Raises ValueError if no valid department can be determined.
    """
    department_id = data.get("department_id")
    department_name = data.get("department")
    department = None

    if department_id:
        department = db.session.get(Department, department_id)
    elif department_name:
        department = Department.query.filter_by(name=department_name).first()
    elif user.department_id:
        department = user.department

    if not department:
        raise ValueError("Valid department_id or department is required")
    if user.role != Role.MASTER_ADMIN and department.id != user.department_id:
        raise PermissionError("Users may only write tasks for their own department")
    return department


def visible_tasks_query(user):
    """Return a SQLAlchemy query scoped to tasks visible to the given user.

    MASTER_ADMIN sees all tasks. Other roles see only their department.
    """
    query = Task.query.options(
        joinedload(Task.department),
        joinedload(Task.creator),
        joinedload(Task.current_worker),
        joinedload(Task.completed_by_user),
    )
    if user.role != Role.MASTER_ADMIN:
        query = query.filter(Task.department_id == user.department_id)
    return query


def create_task(data, user):
    """Create and persist a new task for the given user.

    Returns (task, None, 201) on success or (None, error_dict, status) on failure.
    """
    try:
        validate_task_payload(data, require_title=True)
        department = get_department_for_payload(data, user)
        requested_status = parse_enum(TaskStatus, data.get("status"), TaskStatus.OPEN)
        error_entry = linked_error_entry(data.get("error_entry_id"), user)

        task = Task(
            title=data["title"].strip(),
            description=data.get("description", ""),
            priority=parse_enum(Priority, data.get("priority"), Priority.NORMAL),
            status=TaskStatus.OPEN,
            due_date=parse_date(data.get("due_date")),
            department=department,
            created_by=user.id,
            planned_minutes=parse_non_negative_int(
                data.get("planned_minutes"),
                "planned_minutes",
            ),
            actual_minutes=parse_non_negative_int(
                data.get("actual_minutes"),
                "actual_minutes",
            ),
            blocked_reason=str(data.get("blocked_reason") or "").strip(),
            error_entry=error_entry,
        )
        update_task_status(task, requested_status, user)
    except PermissionError as exc:
        return None, {"error": str(exc)}, 403
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    db.session.add(task)
    try:
        db.session.flush()
        record_event(
            "task.created",
            "tasks",
            entity_type="task",
            entity_id=task.id,
            task=task,
            user=user,
            department=task.department,
            metadata={
                "priority": task.priority.value,
                "status": task.status.value,
                "planned_minutes": task.planned_minutes,
            },
            new_value=task_event_state(task),
            description=f"Task erstellt: {task.title}",
        )
        mark_task_knowledge_stale(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("task_create_failed user_id=%s", user.id)
        return None, {"error": "Database error while creating task"}, 500

    logger.info(
        "task_created task_id=%s user_id=%s department_id=%s priority=%s status=%s",
        task.id,
        user.id,
        task.department_id,
        task.priority.value,
        task.status.value,
    )
    return task, None, 201


def update_task(task, data, user):
    """Apply a partial update to an existing task.

    Returns (task, None, 200) on success or (None, error_dict, status) on failure.
    """
    old_state = task_event_state(task)
    old_status = task.status
    old_priority = task.priority
    try:
        validate_task_payload(data, require_title=False)
        if "department_id" in data or "department" in data:
            task.department = get_department_for_payload(data, user)
        if "title" in data:
            task.title = data["title"].strip()
        if "description" in data:
            task.description = data["description"]
        if "priority" in data:
            task.priority = parse_enum(Priority, data["priority"], task.priority)
        if "status" in data:
            status = parse_enum(TaskStatus, data["status"], task.status)
            update_task_status(task, status, user)
        if "due_date" in data:
            task.due_date = parse_date(data["due_date"])
        if "planned_minutes" in data:
            task.planned_minutes = parse_non_negative_int(
                data["planned_minutes"],
                "planned_minutes",
            )
        if "actual_minutes" in data:
            task.actual_minutes = parse_non_negative_int(
                data["actual_minutes"],
                "actual_minutes",
            )
        if "blocked_reason" in data:
            task.blocked_reason = str(data.get("blocked_reason") or "").strip()
    except PermissionError as exc:
        return None, {"error": str(exc)}, 403
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    try:
        if old_status != task.status:
            event_type = "task.status_changed"
            description = f"Task-Status geaendert: {old_status.value} -> {task.status.value}"
        elif old_priority != task.priority:
            event_type = "task.priority_changed"
            description = (
                f"Task-Prioritaet geaendert: {old_priority.value} -> {task.priority.value}"
            )
        else:
            event_type = "task.updated"
            description = f"Task aktualisiert: {task.title}"
        record_event(
            event_type,
            "tasks",
            entity_type="task",
            entity_id=task.id,
            task=task,
            user=user,
            department=task.department,
            metadata={
                "old_status": old_status.value,
                "new_status": task.status.value,
                "priority": task.priority.value,
                "blocked": bool(task.blocked_reason),
            },
            old_value=old_state,
            new_value=task_event_state(task),
            description=description,
        )
        if old_status != task.status and old_priority != task.priority:
            record_event(
                "task.priority_changed",
                "tasks",
                entity_type="task",
                entity_id=task.id,
                task=task,
                user=user,
                department=task.department,
                metadata={
                    "old_priority": old_priority.value,
                    "new_priority": task.priority.value,
                    "status": task.status.value,
                },
                old_value=old_priority.value,
                new_value=task.priority.value,
                description=(
                    "Task-Prioritaet geaendert: " f"{old_priority.value} -> {task.priority.value}"
                ),
            )
        mark_task_knowledge_stale(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("task_update_failed task_id=%s user_id=%s", task.id, user.id)
        return None, {"error": "Database error while updating task"}, 500

    return task, None, 200


def delete_task(task):
    """Delete a task from the database.

    Returns (None, None, 204) on success or (None, error_dict, status) on failure.
    """
    try:
        delete_source_knowledge_document("task", task.id)
        db.session.delete(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("task_delete_failed task_id=%s", task.id)
        return None, {"error": "Database error while deleting task"}, 500

    logger.info("task_deleted task_id=%s", task.id)
    return None, None, 204


def update_task_status(task, new_status, user):
    """Apply a status change and keep workflow-tracking fields consistent.

    This is idempotent — calling it with the current status is a no-op.
    """
    if task.status == new_status:
        return

    previous_status = task.status
    task.status = new_status
    if previous_status == TaskStatus.DONE and new_status in {
        TaskStatus.OPEN,
        TaskStatus.IN_PROGRESS,
    }:
        task.reopened_count = (task.reopened_count or 0) + 1
    if new_status == TaskStatus.OPEN:
        task.current_worker = None
        task.started_at = None
        task.completed_by_user = None
        task.completed_at = None
    elif new_status == TaskStatus.IN_PROGRESS:
        task.current_worker = user
        task.started_at = task.started_at or datetime.now(UTC)
        task.completed_by_user = None
        task.completed_at = None
    elif new_status == TaskStatus.DONE:
        task.current_worker = task.current_worker or user
        task.started_at = task.started_at or datetime.now(UTC)
        task.completed_by_user = user
        task.completed_at = datetime.now(UTC)
    elif new_status == TaskStatus.CANCELLED:
        task.completed_by_user = None
        task.completed_at = None


def start_task(task, user):
    """Transition a task to IN_PROGRESS and assign it to the given user.

    Returns (task, None, 200) on success or (None, error_dict, status) on failure.
    """
    if task.status == TaskStatus.DONE:
        return None, {"error": "Done tasks cannot be started"}, 400
    if task.status == TaskStatus.CANCELLED:
        return None, {"error": "Cancelled tasks cannot be started"}, 400
    if task.status == TaskStatus.IN_PROGRESS:
        return None, {"error": "Task is already in progress"}, 409

    old_state = task_event_state(task)
    task.status = TaskStatus.IN_PROGRESS
    task.current_worker = user
    task.started_at = datetime.now(UTC)
    task.completed_by_user = None
    task.completed_at = None

    try:
        record_event(
            "task.started",
            "tasks",
            entity_type="task",
            entity_id=task.id,
            task=task,
            user=user,
            department=task.department,
            metadata={"priority": task.priority.value},
            old_value=old_state,
            new_value=task_event_state(task),
            description=f"Task gestartet: {task.title}",
        )
        mark_task_knowledge_stale(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("task_start_failed task_id=%s user_id=%s", task.id, user.id)
        return None, {"error": "Database error while starting task"}, 500

    logger.info("task_started task_id=%s user_id=%s", task.id, user.id)
    return task, None, 200


def complete_task(task, user):
    """Transition a task to DONE and record who completed it.

    Returns (task, None, 200) on success or (None, error_dict, status) on failure.
    """
    if task.status == TaskStatus.DONE:
        return None, {"error": "Task is already done"}, 409
    if task.status == TaskStatus.CANCELLED:
        return None, {"error": "Cancelled tasks cannot be completed"}, 400

    old_state = task_event_state(task)
    task.status = TaskStatus.DONE
    task.completed_by_user = user
    task.completed_at = datetime.now(UTC)
    if task.started_at and not task.actual_minutes:
        task.actual_minutes = max(
            0,
            round(minutes_between(task.started_at, task.completed_at)),
        )

    try:
        record_event(
            "task.completed",
            "tasks",
            entity_type="task",
            entity_id=task.id,
            task=task,
            user=user,
            department=task.department,
            metadata={
                "priority": task.priority.value,
                "actual_minutes": task.actual_minutes,
                "planned_minutes": task.planned_minutes,
            },
            old_value=old_state,
            new_value=task_event_state(task),
            description=f"Task abgeschlossen: {task.title}",
        )
        mark_task_knowledge_stale(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("task_complete_failed task_id=%s user_id=%s", task.id, user.id)
        return None, {"error": "Database error while completing task"}, 500

    logger.info("task_completed task_id=%s user_id=%s", task.id, user.id)
    return task, None, 200
