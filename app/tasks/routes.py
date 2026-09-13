"""Task API routes."""

from datetime import date

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Priority, Task, TaskStatus
from app.responses import error_response, paginate_query, service_error_response, success_response
from app.security import (
    current_user,
    dashboard_permission_required,
    same_department_or_admin,
)
from app.services.attachment_service import delete_attachments_for
from app.services.maintenance_tag_service import suggest_tags_for_task_payload
from app.services.operations_tracking_service import record_event
from app.services.stock_movement_service import task_materials, withdraw_for_task
from app.services.task_service import (
    create_task,
    delete_task,
    parse_task_priority_mode,
    prioritize_visible_tasks,
    start_task,
    suggest_task_from_text,
    update_task,
    visible_tasks_query,
)
from app.services.workflow_service import complete_task_workflow

tasks_bp = Blueprint("tasks", __name__)


def task_payload_with_tags(task):
    """Return a task payload enriched with local maintenance tag suggestions."""
    payload = task.to_dict()
    payload["tag_suggestions"] = suggest_tags_for_task_payload(payload)
    return payload


@tasks_bp.get("")
@dashboard_permission_required("tasks", "view")
def list_tasks():
    """Return visible tasks for the current user with optional pagination and filters.

    Query params:
        status   — open | in_progress | done | cancelled
        priority — urgent | soon | normal
        page     — page number (default 1)
        limit    — items per page, 1-100 (default 20)
    """
    user = current_user()
    query = visible_tasks_query(user)
    status = request.args.get("status")
    priority = request.args.get("priority")
    try:
        if status:
            query = query.filter(Task.status == TaskStatus(status))
        if priority:
            query = query.filter(Task.priority == Priority(priority))
    except ValueError:
        return error_response("Invalid status or priority filter", 400)
    query = query.order_by(Task.due_date.asc(), Task.id.desc())
    return paginate_query(query, lambda t: t.to_dict())


@tasks_bp.post("")
@dashboard_permission_required("tasks", "write")
def add_task():
    """Create a task in an allowed department."""
    task, error, status = create_task(request.get_json(silent=True) or {}, current_user())
    if error:
        return service_error_response(error, status)
    return jsonify(task_payload_with_tags(task)), status


@tasks_bp.post("/suggest")
@dashboard_permission_required("tasks", "write")
def suggest_task():
    """Return a non-persisted AI task suggestion from free text."""
    data = request.get_json(silent=True) or {}
    suggestion, error, status = suggest_task_from_text(data, current_user())
    if error:
        return service_error_response(error, status)
    user = current_user()
    record_event(
        "ai.task_suggested",
        "ai",
        entity_type="task_suggestion",
        user=user,
        department=user.department,
        source="ai",
        metadata={
            "has_title": bool(suggestion.get("title")) if isinstance(suggestion, dict) else False,
        },
        commit=True,
    )
    return success_response(suggestion, message="Task suggestion generated")


@tasks_bp.post("/prioritize")
@dashboard_permission_required("tasks", "view")
def prioritize_tasks():
    """Return non-persisted priorities for visible tasks."""
    payload = request.get_json(silent=True) or {}
    priorities, error, status = prioritize_visible_tasks(
        payload,
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    user = current_user()
    priority_mode = parse_task_priority_mode(payload.get("mode"))
    record_event(
        "ai.tasks_prioritized",
        "ai",
        entity_type="task_priority",
        user=user,
        department=user.department,
        source="ai",
        metadata={
            "priority_mode": priority_mode,
            "result_count": len(priorities or []),
        },
        commit=True,
    )
    return success_response(priorities, status, "Task priorities loaded")


@tasks_bp.get("/today")
@dashboard_permission_required("tasks", "view")
def today_tasks():
    """Return today's visible tasks."""
    user = current_user()
    tasks = (
        visible_tasks_query(user)
        .filter(Task.due_date == date.today())
        .order_by(Task.priority.asc(), Task.id.desc())
        .all()
    )
    return jsonify([task.to_dict() for task in tasks])


@tasks_bp.get("/<int:task_id>")
@dashboard_permission_required("tasks", "view")
def get_task(task_id):
    """Return a visible task by id."""
    task = db.get_or_404(Task, task_id)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)
    return jsonify(task.to_dict())


@tasks_bp.put("/<int:task_id>")
@dashboard_permission_required("tasks", "write")
def edit_task(task_id):
    """Update a visible task."""
    task = db.get_or_404(Task, task_id)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)
    updated, error, status = update_task(task, request.get_json(silent=True) or {}, current_user())
    if error:
        return service_error_response(error, status)
    return jsonify(task_payload_with_tags(updated))


@tasks_bp.post("/<int:task_id>/start")
@dashboard_permission_required("tasks", "write")
def start_task_endpoint(task_id):
    """Start a visible task for the current user."""
    task = db.session.get(Task, task_id)
    if not task:
        return error_response("Task not found", 404)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)

    updated, error, status = start_task(task, current_user())
    if error:
        return service_error_response(error, status)
    return success_response(task_payload_with_tags(updated), status, "Task started")


@tasks_bp.post("/<int:task_id>/complete")
@dashboard_permission_required("tasks", "write")
def complete_task_endpoint(task_id):
    """Complete a visible task for the current user."""
    task = db.session.get(Task, task_id)
    if not task:
        return error_response("Task not found", 404)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)

    updated, document, error, status = complete_task_workflow(
        task,
        current_user(),
        request.get_json(silent=True) or {},
    )
    if error:
        return service_error_response(error, status)
    payload = task_payload_with_tags(updated)
    if document:
        payload["generated_document"] = document.to_dict()
    return success_response(payload, status, "Task completed")


@tasks_bp.delete("/<int:task_id>")
@dashboard_permission_required("tasks", "write")
def delete_task_endpoint(task_id):
    """Delete a visible task."""
    task = db.get_or_404(Task, task_id)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)
    record_event(
        "task.deleted",
        "tasks",
        entity_type="task",
        entity_id=task.id,
        task=task,
        user=current_user(),
        department=task.department,
        metadata={"title": task.title, "status": task.status.value},
    )
    delete_attachments_for("task", task.id)
    _, error, status = delete_task(task)
    if error:
        return service_error_response(error, status)
    return "", 204


@tasks_bp.get("/<int:task_id>/materials")
@dashboard_permission_required("tasks", "view")
def list_task_materials(task_id):
    """Return the spare parts withdrawn for a work order."""
    task = db.get_or_404(Task, task_id)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)
    payload, error, status = task_materials(task, current_user())
    if error:
        return service_error_response(error, status)
    return success_response(payload, message="Task materials loaded")


@tasks_bp.post("/<int:task_id>/materials")
@dashboard_permission_required("tasks", "write")
def withdraw_task_material(task_id):
    """Withdraw spare parts from stock for a work order."""
    task = db.get_or_404(Task, task_id)
    if not same_department_or_admin(task):
        return error_response("Forbidden", 403)
    movement, error, status = withdraw_for_task(
        task, request.get_json(silent=True) or {}, current_user()
    )
    if error:
        return service_error_response(error, status)
    return success_response(movement.to_dict(), status, "Material withdrawn")
