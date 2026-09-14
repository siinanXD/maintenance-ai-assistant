"""Filtered task lists and counts for the agent."""

from __future__ import annotations

from app.extensions import db
from app.models import Department, Priority, Task, TaskStatus
from app.security import has_dashboard_permission
from app.services.ai_structured_source_service import task_source_cards
from app.services.task_service import visible_tasks_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    aggregate_or_row_sources,
    build_structured_context,
    denied_outcome,
    filter_summary,
    plant_today,
    today_bounds,
    yesterday_bounds,
)

TASK_STATUSES = {
    "open": TaskStatus.OPEN,
    "in_progress": TaskStatus.IN_PROGRESS,
    "done": TaskStatus.DONE,
}
FILTER_KEYS = ("department", "status", "time_range", "due", "machine", "priority")


def list_tasks(
    user,
    *,
    status=None,
    department=None,
    machine=None,
    priority=None,
    time_range=None,
    due=None,
    count_only=False,
):
    """Return visible tasks matching explicit filters."""
    if not has_dashboard_permission(user, "tasks", "view"):
        return denied_outcome("tasks", "tasks")
    filters = _clean_filters(
        status=status,
        department=department,
        machine=machine,
        priority=priority,
        time_range=time_range,
        due=due,
    )
    query = _filtered_task_query(user, filters)
    count = query.count()
    tasks = _ordered_tasks(query, filters).limit(MAX_LIST_ITEMS).all()
    title = "Heutige Tasks" if filters.get("due") == "today" else "Tasks"
    return QueryOutcome(
        entity_type="tasks",
        scope="tasks",
        answer_markdown=format_answer(title, count, tasks, filters, count_only),
        count=count,
        items=[task.to_dict() for task in tasks],
        filters=filters,
        sources=aggregate_or_row_sources(task_source_cards(tasks), "tasks", count, user),
        structured_context=build_structured_context(
            "tasks",
            department=filters.get("department"),
            status=filters.get("status"),
            time_range=filters.get("time_range"),
            machine=filters.get("machine"),
            query="due_today" if filters.get("due") == "today" else "",
        ),
        query="count" if count_only else "list",
    )


def _clean_filters(**filters):
    """Return only non-empty, normalized filter values."""
    cleaned = {}
    for key, value in filters.items():
        text = str(value or "").strip()
        if text:
            cleaned[key] = (
                text.lower() if key in {"status", "priority", "time_range", "due"} else text
            )
    return cleaned


def _filtered_task_query(user, filters):
    """Return visible tasks filtered by explicit structured filters."""
    query = visible_tasks_query(user)
    status = filters.get("status")
    if status in TASK_STATUSES:
        query = query.filter(Task.status == TASK_STATUSES[status])
    if filters.get("department"):
        query = query.filter(Task.department.has(Department.name == filters["department"]))
    if filters.get("priority") == "urgent":
        query = query.filter(Task.priority == Priority.URGENT)
    if filters.get("machine"):
        pattern = f"%{filters['machine']}%"
        query = query.filter(db.or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    if filters.get("time_range") in {"today", "yesterday"}:
        start_at, end_at = (
            today_bounds() if filters["time_range"] == "today" else yesterday_bounds()
        )
        if status == "done":
            query = query.filter(Task.completed_at >= start_at, Task.completed_at < end_at)
        else:
            query = query.filter(Task.created_at >= start_at, Task.created_at < end_at)
    if filters.get("due") == "today":
        query = query.filter(Task.due_date == plant_today())
    elif filters.get("due") == "overdue":
        query = query.filter(
            Task.due_date < plant_today(),
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )
    return query


def _ordered_tasks(query, filters):
    """Return the task query ordered for stable answers."""
    if filters.get("status") == "done":
        return query.order_by(Task.completed_at.desc(), Task.id.desc())
    return query.order_by(Task.priority.asc(), Task.due_date.asc(), Task.id.desc())


def format_answer(label, count, tasks, filters, count_only):
    """Return a compact German answer for a filtered task list."""
    lines = [
        f"## {label}",
        f"- **Anzahl:** {count}",
        f"- **Filter:** {filter_summary(filters, FILTER_KEYS)}",
        "- **Quelle:** Strukturierte Daten",
    ]
    if count == 0:
        lines.append("")
        lines.append("Keine passenden sichtbaren Eintraege gefunden.")
        return "\n".join(lines)
    if count_only:
        return "\n".join(lines)
    lines.append("")
    lines.append("Sichtbare Treffer:")
    for task in tasks[:MAX_ANSWER_ITEMS]:
        department_name = task.department.name if task.department else "ohne Bereich"
        lines.append(f"- #{task.id} {task.title} ({task.status.value}, {department_name})")
    if count > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {count - MAX_ANSWER_ITEMS} weitere passende Eintraege")
    return "\n".join(lines)
