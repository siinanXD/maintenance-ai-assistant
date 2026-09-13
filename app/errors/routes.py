"""Error catalog API routes."""

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import ErrorEntry
from app.responses import error_response, paginate_query, service_error_response, success_response
from app.security import (
    current_user,
    dashboard_permission_required,
    same_department_or_admin,
)
from app.services.attachment_service import delete_attachments_for
from app.services.error_service import (
    ERROR_STATUSES,
    analyze_error_description,
    close_error_entry,
    create_error_entry,
    error_event_state,
    open_work_order_counts,
    search_errors,
    suggest_similar_errors,
    update_error_entry,
    visible_errors_query,
)
from app.services.knowledge_service import delete_source_knowledge_document
from app.services.maintenance_tag_service import suggest_tags_for_error_payload
from app.services.missing_information_service import missing_information_for_error_entry
from app.services.operations_tracking_service import record_event

errors_bp = Blueprint("errors", __name__)


def _truthy_query_arg(name):
    """Return whether a query parameter is a truthy flag."""
    return str(request.args.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


@errors_bp.get("")
@dashboard_permission_required("errors", "view")
def list_errors():
    """Return visible error catalog entries with optional pagination.

    Query params:
        page  — page number (default 1)
        limit — items per page, 1-100 (default 20)
    """
    user = current_user()
    query = visible_errors_query(user)
    status = str(request.args.get("status", "")).strip().lower()
    if status:
        if status not in ERROR_STATUSES:
            return error_response("Invalid status filter", 400)
        query = query.filter(ErrorEntry.status == status)
    if _truthy_query_arg("active"):
        query = query.filter(
            ErrorEntry.status.in_(("open", "in_progress")),
            ErrorEntry.last_seen_at.isnot(None),
        ).order_by(
            ErrorEntry.last_seen_at.desc(),
            ErrorEntry.created_at.desc(),
            ErrorEntry.id.desc(),
        )
    else:
        query = query.order_by(ErrorEntry.error_code.asc())
    open_tasks = open_work_order_counts(user)
    return paginate_query(
        query, lambda e: {**e.to_dict(), "open_task_count": open_tasks.get(e.id, 0)}
    )


@errors_bp.post("")
@dashboard_permission_required("errors", "write")
def add_error():
    """Create an error catalog entry in an allowed department."""
    data = request.get_json(silent=True) or {}
    user = current_user()
    entry, error, status = create_error_entry(data, user)
    if error:
        return service_error_response(error, status)
    payload = entry.to_dict()
    payload["missing_information"] = missing_information_for_error_entry(
        {**data, **payload},
        user,
    )
    payload["tag_suggestions"] = suggest_tags_for_error_payload({**data, **payload})
    return jsonify(payload), status


@errors_bp.post("/analyze")
@dashboard_permission_required("errors", "write")
def analyze_error():
    """Return a non-persisted AI analysis for an error description."""
    analysis, error, status = analyze_error_description(
        request.get_json(silent=True) or {},
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    return success_response(analysis, message="Error analysis generated")


@errors_bp.post("/similar")
@dashboard_permission_required("errors", "view")
def similar_errors():
    """Return visible error catalog entries similar to a description."""
    result, error, status = suggest_similar_errors(
        request.get_json(silent=True) or {},
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    return success_response(result, status, "Similar errors loaded")


@errors_bp.get("/search")
@dashboard_permission_required("errors", "view")
def search():
    """Search visible error catalog entries."""
    entries = search_errors(request.args.get("query", ""), current_user())
    return jsonify([entry.to_dict() for entry in entries])


@errors_bp.get("/<int:error_id>")
@dashboard_permission_required("errors", "view")
def get_error(error_id):
    """Return a visible error catalog entry by id."""
    entry = db.get_or_404(ErrorEntry, error_id)
    if not same_department_or_admin(entry):
        return error_response("Forbidden", 403)
    return jsonify(entry.to_dict())


@errors_bp.put("/<int:error_id>")
@dashboard_permission_required("errors", "write")
def edit_error(error_id):
    """Update a visible error catalog entry."""
    entry = db.get_or_404(ErrorEntry, error_id)
    if not same_department_or_admin(entry):
        return error_response("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    user = current_user()
    updated, error, status = update_error_entry(
        entry,
        data,
        user,
    )
    if error:
        return service_error_response(error, status)
    payload = updated.to_dict()
    payload["missing_information"] = missing_information_for_error_entry(
        {**payload, **data},
        user,
    )
    payload["tag_suggestions"] = suggest_tags_for_error_payload({**payload, **data})
    return jsonify(payload)


@errors_bp.post("/<int:error_id>/close")
@dashboard_permission_required("errors", "write")
def close_error(error_id):
    """Close a visible error catalog entry."""
    entry = db.get_or_404(ErrorEntry, error_id)
    if not same_department_or_admin(entry):
        return error_response("Forbidden", 403)
    updated, error, status = close_error_entry(entry, current_user())
    if error:
        return service_error_response(error, status)
    return success_response(updated.to_dict(), status, "Error closed")


@errors_bp.delete("/<int:error_id>")
@dashboard_permission_required("errors", "write")
def delete_error(error_id):
    """Delete a visible error catalog entry."""
    entry = db.get_or_404(ErrorEntry, error_id)
    if not same_department_or_admin(entry):
        return error_response("Forbidden", 403)
    record_event(
        "error.deleted",
        "errors",
        entity_type="error_entry",
        entity_id=entry.id,
        user=current_user(),
        department=entry.department,
        machine_id=entry.machine_id,
        metadata={"error_code": entry.error_code, "severity": entry.severity},
        old_value=error_event_state(entry),
        description=f"Stoerung geloescht: {entry.error_code}",
    )
    delete_source_knowledge_document("error_entry", entry.id)
    delete_attachments_for("error", entry.id)
    db.session.delete(entry)
    db.session.commit()
    return "", 204
