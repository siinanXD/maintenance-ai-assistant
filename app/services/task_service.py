"""Task service layer.

All task business logic lives here. Routes should call these functions
and do nothing more than validate input, call the service, and return a response.
"""

import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Department, ErrorEntry, GeneratedDocument, Priority, Role, Task, TaskStatus
from app.security import has_dashboard_permission
from app.services.ai_service import AIServiceError, MockAIProvider, get_ai_provider
from app.services.error_service import visible_errors_query
from app.services.knowledge_service import (
    delete_source_knowledge_document,
    mark_task_knowledge_stale,
)
from app.services.maintenance_tag_service import suggest_tags_for_task_payload
from app.services.operations_tracking_service import record_event

logger = logging.getLogger(__name__)

TASK_PRIORITY_MODE_AI = "ai"
TASK_PRIORITY_MODE_LOCAL = "local"
TASK_PRIORITY_MODES = {TASK_PRIORITY_MODE_AI, TASK_PRIORITY_MODE_LOCAL}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Department resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AI features
# ---------------------------------------------------------------------------


def prioritize_visible_tasks(data, user):
    """Return non-persisted AI priorities for tasks visible to the given user.

    Returns (priorities_list, None, 200) or (None, error_dict, status) on failure.
    """
    try:
        status = parse_enum(TaskStatus, data.get("status"), None)
        limit = parse_priority_limit(data.get("limit", 20))
        priority_mode = parse_task_priority_mode(data.get("mode"))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    query = visible_tasks_query(user)
    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.due_date.asc(), Task.id.desc()).limit(limit).all()
    serialized = serialize_tasks_for_prioritization(tasks, user)
    context = {
        "role": user.role.value,
        "department": user.department.name if user.department else "",
        "history_fields": [
            "maintenance_reports_count",
            "related_error_count",
            "recent_related_errors",
            "recent_shift_handovers",
            "machines",
            "risk_signals",
        ],
    }

    if priority_mode == TASK_PRIORITY_MODE_LOCAL:
        provider_result = MockAIProvider().prioritize_tasks(serialized, context)
    else:
        try:
            provider_result = get_ai_provider().prioritize_tasks(serialized, context)
        except AIServiceError:
            logger.warning(
                "ai_fallback workflow=task_prioritization user_id=%s task_count=%s",
                user.id,
                len(serialized),
            )
            provider_result = MockAIProvider().prioritize_tasks(serialized, context)

    priorities = normalize_task_priorities(provider_result, tasks, serialized)
    return priorities, None, 200


def suggest_task_from_text(data, user):
    """Return a non-persisted AI task suggestion derived from free text.

    Returns (suggestion_dict, None, 200) or (None, error_dict, status) on failure.
    """
    text = str(data.get("text") or "").strip()
    if not text:
        return None, {"error": "text is required"}, 400
    if len(text) > 2000:
        return None, {"error": "text must not exceed 2000 characters"}, 400

    user_context = {
        "role": user.role.value,
        "department": user.department.name if user.department else "",
    }
    from app.services.retrieval_service import knowledge_context_for_chat

    rag_context, rag_sources = knowledge_context_for_chat(text, user)
    if rag_context:
        user_context["rag_context"] = rag_context
        user_context["rag_sources"] = rag_sources
    try:
        suggestion = get_ai_provider().suggest_task(text, user_context)
    except AIServiceError:
        logger.warning(
            "ai_fallback workflow=task_suggestion user_id=%s text_length=%s",
            user.id,
            len(text),
        )
        suggestion = MockAIProvider().suggest_task(text, user_context)

    normalized = normalize_task_suggestion(suggestion, text, user)
    normalized["sources"] = rag_sources
    normalized["diagnostics"] = {
        "status": "local_answer",
        "rag_source_count": len(rag_sources),
    }
    normalized["tag_suggestions"] = suggest_tags_for_task_payload(
        {
            **normalized,
            "text": text,
        }
    )
    return normalized, None, 200


# ---------------------------------------------------------------------------
# Normalization helpers (AI output → stable shape)
# ---------------------------------------------------------------------------


def parse_priority_limit(value):
    """Parse and validate a task prioritization limit (1–100)."""
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer between 1 and 100") from exc
    if limit < 1 or limit > 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return limit


def parse_task_priority_mode(value):
    """Return the requested task priority provider mode."""
    mode = str(value or TASK_PRIORITY_MODE_AI).strip().lower()
    if mode not in TASK_PRIORITY_MODES:
        raise ValueError("mode must be one of: ai, local")
    return mode


def serialize_tasks_for_prioritization(tasks, user):
    """Return task payloads enriched with permission-safe history context."""
    histories = task_priority_histories(tasks, user)
    serialized = []
    for task in tasks:
        payload = task.to_dict()
        payload["history"] = histories.get(task.id, empty_task_priority_history(task))
        serialized.append(payload)
    return serialized


def task_priority_histories(tasks, user):
    """Build compact maintenance-history context for visible task prioritization."""
    if not tasks:
        return {}
    documents_by_task = task_priority_documents_by_task(tasks, user)
    visible_errors = task_priority_visible_errors(user)
    visible_handovers = task_priority_visible_handovers(user)
    histories = {}
    for task in tasks:
        documents = documents_by_task.get(task.id, [])
        histories[task.id] = task_priority_history(
            task,
            documents,
            visible_errors,
            visible_handovers,
        )
    return histories


def task_priority_documents_by_task(tasks, user):
    """Return generated maintenance documents grouped by task when visible."""
    if not has_dashboard_permission(user, "documents", "view"):
        return {}
    task_ids = [task.id for task in tasks]
    documents = (
        GeneratedDocument.query.filter(GeneratedDocument.task_id.in_(task_ids))
        .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
        .all()
    )
    grouped = defaultdict(list)
    for document in documents:
        grouped[document.task_id].append(document)
    return grouped


def task_priority_visible_errors(user):
    """Return recent visible errors that can inform task risk without leaking data."""
    if not has_dashboard_permission(user, "errors", "view"):
        return []
    return (
        visible_errors_query(user)
        .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
        .limit(100)
        .all()
    )


def task_priority_visible_handovers(user):
    """Return recent visible handovers that can inform task risk without leaking data."""
    if not has_dashboard_permission(user, "shiftplans", "view"):
        return []
    from app.handover.services import visible_handovers_query
    from app.models import ShiftHandover

    return (
        visible_handovers_query(user)
        .order_by(ShiftHandover.shift_date.desc(), ShiftHandover.id.desc())
        .limit(100)
        .all()
    )


def task_priority_history(task, documents, visible_errors, visible_handovers=None):
    """Return one compact history payload for a task."""
    machines = task_history_machines(documents)
    related_errors = task_related_errors(task, machines, visible_errors)
    related_handovers = task_related_handovers(task, machines, visible_handovers or [])
    return {
        "maintenance_reports_count": len(documents),
        "last_maintenance_report_at": (documents[0].created_at.isoformat() if documents else None),
        "machines": machines,
        "related_error_count": len(related_errors),
        "recent_related_errors": related_errors[:3],
        "shift_handover_count": len(related_handovers),
        "recent_shift_handovers": related_handovers[:3],
        "reopened_count": task.reopened_count or 0,
        "blocked": bool(task.blocked_reason),
        "risk_signals": task_priority_history_signals(
            task,
            documents,
            related_errors,
            related_handovers,
        ),
        "source_references": task_priority_source_references(
            task,
            documents,
            related_errors,
            related_handovers,
        ),
    }


def empty_task_priority_history(task):
    """Return an empty but structurally stable task-priority history payload."""
    return {
        "maintenance_reports_count": 0,
        "last_maintenance_report_at": None,
        "machines": [],
        "related_error_count": 0,
        "recent_related_errors": [],
        "shift_handover_count": 0,
        "recent_shift_handovers": [],
        "reopened_count": task.reopened_count or 0,
        "blocked": bool(task.blocked_reason),
        "risk_signals": task_priority_history_signals(task, [], [], []),
        "source_references": task_priority_source_references(task, [], [], []),
    }


def task_history_machines(documents):
    """Return unique machine references from visible task documents."""
    machines = []
    seen = set()
    for document in documents:
        machine_id = document.machine_id
        name = str(document.machine or "").strip()
        key = (machine_id, name.lower())
        if key in seen or (not machine_id and not name):
            continue
        seen.add(key)
        machines.append({"id": machine_id, "name": name})
    return machines


def task_related_errors(task, machines, visible_errors):
    """Return visible errors related to a task by machine or technical terms."""
    tokens = task_priority_tokens(
        " ".join(
            [
                task.title or "",
                task.description or "",
                " ".join(machine.get("name") or "" for machine in machines),
            ]
        )
    )
    related = []
    for entry in visible_errors:
        if not task_error_matches(entry, tokens, machines):
            continue
        related.append(
            {
                "id": entry.id,
                "error_code": entry.error_code,
                "title": entry.title,
                "severity": entry.severity,
                "status": entry.status,
                "machine": entry.machine,
                "machine_id": entry.machine_id,
                "repeat_count": entry.repeat_count,
                "downtime_minutes": entry.downtime_minutes,
                "created_at": entry.created_at.isoformat(),
                "role_visibility": _task_priority_role_visibility(
                    entry.department.name if entry.department else "",
                ),
            }
        )
    return related


def task_related_handovers(task, machines, visible_handovers):
    """Return visible shift handovers related to a task by machine or technical terms."""
    tokens = task_priority_tokens(
        " ".join(
            [
                task.title or "",
                task.description or "",
                " ".join(machine.get("name") or "" for machine in machines),
            ]
        )
    )
    related = []
    for handover in visible_handovers:
        if not task_handover_matches(handover, tokens, machines):
            continue
        related.append(
            {
                "id": handover.id,
                "title": f"Schichtuebergabe {handover.shift_date.isoformat()}",
                "status": handover.status,
                "shift_date": handover.shift_date.isoformat(),
                "shift_type": handover.shift_type,
                "machine_id": handover.machine_id,
                "machine": handover.machine.name if handover.machine else "",
                "problem_category": handover.problem_category,
                "open_tasks": str(handover.open_tasks or "")[:220],
                "next_notes": str(handover.next_notes or "")[:220],
                "created_at": handover.created_at.isoformat() if handover.created_at else "",
                "role_visibility": _task_priority_role_visibility(handover.department),
            }
        )
    return related


def task_error_matches(entry, tokens, machines):
    """Return whether an error entry is relevant for a task-priority history."""
    machine_ids = {machine.get("id") for machine in machines if machine.get("id")}
    machine_names = {
        str(machine.get("name") or "").strip().lower()
        for machine in machines
        if machine.get("name")
    }
    if entry.machine_id and entry.machine_id in machine_ids:
        return True
    if entry.machine and entry.machine.strip().lower() in machine_names:
        return True

    haystack = " ".join(
        [
            entry.machine or "",
            entry.error_code or "",
            entry.title or "",
            entry.description or "",
            entry.symptoms or "",
            entry.possible_causes or "",
            entry.solution or "",
        ]
    ).lower()
    return any(token in haystack for token in tokens)


def task_handover_matches(handover, tokens, machines):
    """Return whether a shift handover is relevant for task-priority history."""
    machine_ids = {machine.get("id") for machine in machines if machine.get("id")}
    machine_names = {
        str(machine.get("name") or "").strip().lower()
        for machine in machines
        if machine.get("name")
    }
    if handover.machine_id and handover.machine_id in machine_ids:
        return True
    handover_machine = handover.machine.name.strip().lower() if handover.machine else ""
    if handover_machine and handover_machine in machine_names:
        return True

    haystack = " ".join(
        [
            handover.area or "",
            handover_machine,
            handover.content or "",
            handover.open_tasks or "",
            handover.machine_notes or "",
            handover.next_notes or "",
            handover.cause or "",
            handover.action_taken or "",
            handover.follow_up_task or "",
        ]
    ).lower()
    return any(token in haystack for token in tokens)


def task_priority_tokens(text):
    """Return useful technical tokens for task-history matching."""
    ignored = {
        "anlage",
        "task",
        "test",
        "pruefen",
        "prüfen",
        "wartung",
        "kontrolle",
        "normal",
    }
    return {token for token in re.findall(r"[\w-]{4,}", text.lower()) if token not in ignored}


def task_priority_history_signals(task, documents, related_errors, related_handovers=None):
    """Return compact risk signals derived from task and visible history."""
    signals = []
    if task.blocked_reason:
        signals.append("blocked")
    if task.reopened_count:
        signals.append("reopened")
    if documents:
        signals.append("maintenance_report_history")
    if related_errors:
        signals.append("related_error_history")
    if related_handovers:
        signals.append("shift_handover_history")
    if any(handover.get("status") == "open" for handover in related_handovers or []):
        signals.append("open_handover_history")
    if any(error.get("severity") in {"high", "critical"} for error in related_errors):
        signals.append("critical_error_history")
    if any((error.get("repeat_count") or 0) > 0 for error in related_errors):
        signals.append("recurring_error_history")
    if any((error.get("downtime_minutes") or 0) > 0 for error in related_errors):
        signals.append("downtime_history")
    return signals


def normalize_task_priorities(provider_result, tasks, serialized_tasks=None):
    """Normalize provider priority output and attach full task payloads."""
    provider_items = _provider_priority_items(provider_result)
    priority_by_task_id = {
        int(item["task_id"]): item for item in provider_items if _has_valid_task_id(item)
    }
    fallback_payloads = serialized_tasks or [task.to_dict() for task in tasks]
    fallback_items = MockAIProvider().prioritize_tasks(fallback_payloads, {})["priorities"]
    fallback_by_task_id = {item["task_id"]: item for item in fallback_items}
    serialized_by_task_id = {
        int(item["id"]): item for item in fallback_payloads if _has_valid_payload_id(item)
    }

    normalized = []
    for task in tasks:
        item = priority_by_task_id.get(task.id, fallback_by_task_id[task.id])
        serialized_task = serialized_by_task_id.get(task.id, {})
        evidence_counts = task_priority_evidence_counts(serialized_task)
        normalized.append(
            {
                "task": task.to_dict(),
                "score": _clamped_score(item.get("score")),
                "risk_level": _valid_risk_level(item.get("risk_level")),
                "reason": str(item.get("reason") or "").strip()[:500],
                "recommended_action": str(item.get("recommended_action") or "").strip()[:500],
                "confidence": task_priority_confidence(item, evidence_counts),
                "evidence_counts": evidence_counts,
                "evidence_references": task_priority_evidence_references(serialized_task),
                "next_steps": task_priority_next_steps(serialized_task),
            }
        )

    return sorted(normalized, key=lambda item: item["score"], reverse=True)


def task_priority_confidence(provider_item, evidence_counts):
    """Return confidence and uncertainty for one task-priority suggestion."""
    counts = evidence_counts if isinstance(evidence_counts, dict) else {}
    score = 35
    score += min(25, int(counts.get("risk_signals") or 0) * 6)
    score += min(15, int(counts.get("related_errors") or 0) * 5)
    score += min(10, int(counts.get("maintenance_reports") or 0) * 4)
    score += min(8, int(counts.get("shift_handovers") or 0) * 4)
    score += min(5, int(counts.get("machines") or 0) * 3)
    if str((provider_item or {}).get("reason") or "").strip():
        score += 5
    score = max(0, min(95, score))
    level = _task_priority_confidence_level(score)
    return {
        "score": score,
        "level": level,
        "uncertainty": _task_priority_uncertainty(level),
        "reason": _task_priority_confidence_reason(counts),
        "uses_only_visible_sources": bool(counts.get("uses_only_visible_sources", True)),
    }


def _task_priority_confidence_level(score):
    """Return a coarse confidence level for a task-priority suggestion."""
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _task_priority_uncertainty(level):
    """Return an uncertainty label aligned with the confidence level."""
    if level == "high":
        return "low"
    if level == "medium":
        return "medium"
    return "high"


def _task_priority_confidence_reason(evidence_counts):
    """Return a short explanation for task-priority confidence."""
    if int(evidence_counts.get("related_errors") or 0) and int(
        evidence_counts.get("maintenance_reports") or 0
    ):
        return "Fehlerhistorie und Wartungsberichte stuetzen die Priorisierung."
    if int(evidence_counts.get("related_errors") or 0):
        return "Sichtbare Fehlerhistorie stuetzt die Priorisierung."
    if int(evidence_counts.get("shift_handovers") or 0):
        return "Schichtuebergaben liefern zusaetzlichen Kontext."
    if int(evidence_counts.get("risk_signals") or 0):
        return "Task-Signale stuetzen die Priorisierung, Quellenlage ist begrenzt."
    return "Geringe Zusatzhistorie; Priorisierung basiert hauptsaechlich auf Task-Daten."


def task_priority_evidence_counts(serialized_task):
    """Return public evidence counters for a prioritized task response."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if not isinstance(history, dict):
        history = {}
    recent_related_errors = history.get("recent_related_errors")
    recent_shift_handovers = history.get("recent_shift_handovers")
    machines = history.get("machines")
    risk_signals = history.get("risk_signals")
    return {
        "maintenance_reports": _safe_count(history.get("maintenance_reports_count")),
        "related_errors": _safe_count(history.get("related_error_count")),
        "recent_related_errors": len(recent_related_errors or []),
        "shift_handovers": _safe_count(history.get("shift_handover_count")),
        "recent_shift_handovers": len(recent_shift_handovers or []),
        "machines": len(machines or []),
        "risk_signals": len(risk_signals or []),
        "blocked": bool(history.get("blocked")),
        "reopened_count": _safe_count(history.get("reopened_count")),
        "uses_only_visible_sources": True,
    }


def task_priority_evidence_references(serialized_task):
    """Return prompt-safe source references for a prioritized task response."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if isinstance(history, dict) and isinstance(history.get("source_references"), list):
        return history["source_references"][:8]
    return [_task_priority_task_reference(serialized_task)] if serialized_task else []


def task_priority_source_references(task, documents, related_errors, related_handovers):
    """Return prompt-safe references used as task-priority evidence."""
    references = [_task_priority_task_reference(task.to_dict())]
    references.extend(
        _task_priority_document_reference(document) for document in (documents or [])[:3]
    )
    references.extend(_task_priority_error_reference(entry) for entry in (related_errors or [])[:3])
    references.extend(
        _task_priority_handover_reference(handover) for handover in (related_handovers or [])[:3]
    )
    return [reference for reference in references if reference]


def _task_priority_task_reference(task_payload):
    """Return a prompt-safe source reference for the prioritized task."""
    department = task_payload.get("department") if isinstance(task_payload, dict) else {}
    department_name = department.get("name") if isinstance(department, dict) else ""
    return {
        "type": "task",
        "id": task_payload.get("id") if isinstance(task_payload, dict) else None,
        "title": str(task_payload.get("title") or "")[:180]
        if isinstance(task_payload, dict)
        else "",
        "machine_id": None,
        "role_visibility": _task_priority_role_visibility(department_name),
        "created_at": task_payload.get("created_at") if isinstance(task_payload, dict) else "",
        "due_date": task_payload.get("due_date") if isinstance(task_payload, dict) else None,
    }


def _task_priority_document_reference(document):
    """Return a prompt-safe source reference for a visible maintenance report."""
    return {
        "type": "maintenance_report",
        "id": document.id,
        "title": str(document.title or "")[:180],
        "machine": document.machine,
        "machine_id": document.machine_id,
        "role_visibility": _task_priority_role_visibility(document.department),
        "created_at": document.created_at.isoformat() if document.created_at else "",
    }


def _task_priority_error_reference(entry):
    """Return a prompt-safe source reference for a visible related error."""
    return {
        "type": "error",
        "id": entry.get("id"),
        "title": str(entry.get("title") or "")[:180],
        "machine": entry.get("machine") or "",
        "machine_id": entry.get("machine_id"),
        "role_visibility": entry.get("role_visibility") or "public",
        "created_at": entry.get("created_at") or "",
        "error_code": entry.get("error_code") or "",
    }


def _task_priority_handover_reference(handover):
    """Return a prompt-safe source reference for a visible shift handover."""
    return {
        "type": "shift_handover",
        "id": handover.get("id"),
        "title": str(handover.get("title") or "")[:180],
        "machine": handover.get("machine") or "",
        "machine_id": handover.get("machine_id"),
        "role_visibility": handover.get("role_visibility") or "public",
        "created_at": handover.get("created_at") or "",
        "shift_date": handover.get("shift_date"),
    }


def _task_priority_role_visibility(department):
    """Return a prompt-safe visibility label for task-priority evidence."""
    department_name = str(department or "").strip()
    return f"department:{department_name[:120]}" if department_name else "public"


def task_priority_next_steps(serialized_task):
    """Return structured next steps from visible task-priority evidence."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if not isinstance(history, dict):
        history = {}
    steps = []
    if history.get("blocked"):
        steps.append(
            task_priority_step(
                "resolve_blocker",
                "Blocker klaeren",
                (
                    "Blockierten Task zuerst mit Ursache, Verantwortlichem "
                    "und naechstem Termin klaeren."
                ),
                "task",
                "high",
            )
        )
    if history.get("recent_related_errors"):
        steps.append(
            task_priority_step(
                "review_related_errors",
                "Fehlerhistorie pruefen",
                "Sichtbare verwandte Fehler auf Ursache, Wiederholung und Stillstand auswerten.",
                "error",
                "high",
            )
        )
    if history.get("recent_shift_handovers"):
        steps.append(
            task_priority_step(
                "review_shift_handover",
                "Schichtuebergabe beruecksichtigen",
                "Offene Hinweise aus sichtbaren Uebergaben in die Task-Reihenfolge einbeziehen.",
                "shift_handover",
                "medium",
            )
        )
    if _safe_count(history.get("maintenance_reports_count")):
        steps.append(
            task_priority_step(
                "review_maintenance_reports",
                "Wartungsberichte abgleichen",
                (
                    "Letzte sichtbare Wartungsberichte gegen Task-Beschreibung "
                    "und Anlagenbezug pruefen."
                ),
                "maintenance_report",
                "medium",
            )
        )
    if _safe_count(history.get("reopened_count")):
        steps.append(
            task_priority_step(
                "check_reopened_task",
                "Wiedereroeffnung klaeren",
                (
                    "Wiedereroeffnete Aufgabe auf unvollstaendige Ursache "
                    "oder fehlende Abnahme pruefen."
                ),
                "task",
                "medium",
            )
        )
    if not steps:
        steps.append(
            task_priority_step(
                "execute_task",
                "Task planmaessig bearbeiten",
                (
                    "Keine zusaetzlichen Risikosignale gefunden; nach "
                    "Faelligkeit und Prioritaet einplanen."
                ),
                "task",
                "low",
            )
        )
    return steps[:4]


def task_priority_step(step_type, title, detail, source_type, urgency):
    """Return one bounded next-step payload for task prioritization."""
    return {
        "type": str(step_type or "")[:80],
        "title": str(title or "")[:160],
        "detail": str(detail or "")[:500],
        "source_type": str(source_type or "")[:80],
        "urgency": str(urgency or "medium")[:40],
    }


def normalize_task_suggestion(suggestion, original_text, user):
    """Validate and normalize an AI task suggestion into a stable dict."""
    suggestion = suggestion or {}
    department_name = suggestion.get("department")
    if user.role != Role.MASTER_ADMIN and user.department:
        department_name = user.department.name
    if not Department.query.filter_by(name=department_name).first():
        department_name = user.department.name if user.department else "Instandhaltung"

    priority = suggestion.get("priority", Priority.NORMAL.value)
    if priority not in {item.value for item in Priority}:
        priority = Priority.NORMAL.value

    status = suggestion.get("status", TaskStatus.OPEN.value)
    if status not in {item.value for item in TaskStatus}:
        status = TaskStatus.OPEN.value

    title = str(suggestion.get("title") or original_text[:80]).strip()
    return {
        "title": title[:160],
        "description": str(suggestion.get("description") or original_text).strip(),
        "department": department_name,
        "priority": priority,
        "status": status,
        "possible_cause": str(suggestion.get("possible_cause") or "").strip(),
        "recommended_action": str(suggestion.get("recommended_action") or "").strip(),
    }


def _provider_priority_items(provider_result):
    """Extract the priority list from a dict or list provider response."""
    if isinstance(provider_result, list):
        return provider_result
    if isinstance(provider_result, dict):
        priorities = provider_result.get("priorities", [])
        if isinstance(priorities, list):
            return priorities
    return []


def _has_valid_task_id(item):
    """Return True if the item dict contains a parseable task_id."""
    if not isinstance(item, dict):
        return False
    try:
        int(item.get("task_id"))
    except (TypeError, ValueError):
        return False
    return True


def _has_valid_payload_id(item):
    """Return True if the item dict contains a parseable serialized task id."""
    if not isinstance(item, dict):
        return False
    try:
        int(item.get("id"))
    except (TypeError, ValueError):
        return False
    return True


def _clamped_score(value):
    """Clamp a score value to the public 0–100 range."""
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _safe_count(value):
    """Return a non-negative integer counter from a possibly invalid value."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _valid_risk_level(value):
    """Return a supported risk level, falling back to 'low'."""
    if value in {"low", "medium", "high", "critical"}:
        return value
    return "low"
