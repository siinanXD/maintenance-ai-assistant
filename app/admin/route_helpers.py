"""Shared helpers and imports for admin API route modules."""

# ruff: noqa: F401, I001

from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request, send_file

from app.auth.services import find_department, parse_role
from app.extensions import db
from app.models import (
    AIAuditEvent,
    AIFAQEntry,
    AIPromptVersion,
    AIResponseSnippet,
    AssistantTrainingEntry,
    Employee,
    KnowledgeDocument,
    KnowledgeGap,
    Role,
    Site,
    User,
)
from app.permissions import (
    permission_schema,
    replace_user_permissions,
    serialize_permissions,
    upsert_default_permissions,
)
from app.responses import error_response, service_error_response, success_response
from app.security import roles_required
from app.services.admin_retrieval_debug_service import retrieval_debug_items
from app.services.ai_audit_service import ai_analytics_summary, ai_user_usage_metrics
from app.services.ai_history_service import paginated_chat_history, parse_limit_offset
from app.services.ai_observability_service import ai_observability_dashboard
from app.services.ai_faq_admin_service import (
    approve_faq_entry,
    create_faq_entry,
    create_response_snippet,
    faq_suggestions,
    list_faq_entries,
    list_response_snippets,
    update_faq_entry,
)
from app.services.ai_prompt_admin_service import (
    activate_prompt_version,
    create_prompt_version,
    get_prompt_template,
    list_prompt_templates,
    prompt_test_preview,
)
from app.services.assistant_training_service import (
    create_training_entry,
    delete_training_entry,
    list_training_entries,
    update_training_entry,
)
from app.services.audit_service import audit_log_query, create_audit_log
from app.services.background_job_service import (
    enqueue_atlas_resync_job,
    enqueue_knowledge_aging_job,
    enqueue_rag_reindex_job,
    list_background_jobs,
)
from app.services.backup_service import (
    backup_path_for,
    create_backup,
    list_backups,
    restore_backup,
)
from app.services.database_schema_service import (
    database_schema_error_payload,
    database_schema_status as _default_database_schema_status,
)
from app.services.knowledge_gap_service import knowledge_gap_detection, list_knowledge_gaps
from app.services.knowledge_network_service import knowledge_network
from app.services.knowledge_quality_service import change_knowledge_quality_status
from app.services.knowledge_service import (
    delete_knowledge_document,
    knowledge_index_status,
    list_knowledge_documents,
    reindex_all_knowledge,
    reindex_knowledge_document,
    reindex_stale_knowledge,
    resync_atlas_knowledge,
    upload_knowledge_document,
)
from app.services.mail_service import mail_config_status
from app.services.notification_service import delivery_query, send_test_email
from app.services.operations_tracking_service import aggregate_operations, record_event
from app.services.payload_parsing_service import parse_bool as parse_optional_bool
from app.services.retrieval_evaluation_history import retrieval_evaluation_history
from app.services.retrieval_evaluation_service import run_admin_golden_retrieval_evaluation
from app.services.retrieval_telemetry_service import retrieval_quality_analytics
from app.services.site_service import create_site, list_sites, update_site


def database_schema_status():
    """Return schema status while honoring app.admin.routes monkeypatches."""
    import sys

    route_module = sys.modules.get("app.admin.routes")
    patched = getattr(route_module, "database_schema_status", None)
    if patched is not None and patched is not database_schema_status:
        return patched()
    return _default_database_schema_status()


def find_user_conflict(username=None, email=None, exclude_user_id=None):
    """Return an existing user with the same username or email, if any."""
    filters = []
    if username:
        filters.append(User.username == username)
    if email:
        filters.append(User.email == email)
    if not filters:
        return None

    query = User.query.filter(db.or_(*filters))
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.first()


def validate_user_department(role, department):
    """Raise when a non-admin user has no department assignment."""
    if role != Role.MASTER_ADMIN and not department:
        raise ValueError("department_id or department is required")


def find_employee(employee_id):
    """Return an employee for an optional admin user payload value."""
    if employee_id in (None, ""):
        return None
    try:
        parsed_employee_id = int(employee_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("employee_id must be a valid employee id") from exc
    employee = db.session.get(Employee, parsed_employee_id)
    if not employee:
        raise ValueError("employee_id does not reference an existing employee")
    return employee


def parse_retrieval_telemetry_args(args):
    """Return validated retrieval telemetry query arguments."""
    try:
        days = int(args.get("days", 30))
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("days and limit must be integers") from exc
    if days < 1 or days > 365:
        raise ValueError("days must be an integer between 1 and 365")
    if limit < 1 or limit > 50:
        raise ValueError("limit must be an integer between 1 and 50")
    return days, limit


def parse_retrieval_evaluation_history_args(args):
    """Return validated retrieval evaluation history query arguments."""
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer between 1 and 50") from exc
    if limit < 1 or limit > 50:
        raise ValueError("limit must be an integer between 1 and 50")
    return limit


def user_audit_payload(user):
    """Return a safe user snapshot for admin audit logs."""
    if not user:
        return {}
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "department_id": user.department_id,
        "employee_id": user.employee_id,
        "is_active": user.is_active,
        "permissions": serialize_permissions(user),
    }


def paginated_audit_response(query):
    """Return a paginated audit log response."""
    try:
        limit = min(max(1, int(request.args.get("limit", 50))), 200)
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return error_response("limit and offset must be integers", 400)
    total = query.count()
    entries = query.offset(offset).limit(limit).all()
    return jsonify(
        {
            "success": True,
            "data": [entry.to_dict() for entry in entries],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
            },
            "message": "Audit log loaded",
        }
    )


def paginated_delivery_response(query):
    """Return a paginated notification delivery response."""
    try:
        limit = min(max(1, int(request.args.get("limit", 50))), 200)
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return error_response("limit and offset must be integers", 400)
    total = query.count()
    deliveries = query.offset(offset).limit(limit).all()
    return jsonify(
        {
            "success": True,
            "data": [delivery.to_dict() for delivery in deliveries],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
            },
            "mail": mail_config_status(),
            "message": "Notification deliveries loaded",
        }
    )


def filtered_ai_event_query(args):
    """Return an AI audit event query filtered from request arguments."""
    query = AIAuditEvent.query
    workflow = str(args.get("workflow") or "").strip()
    status = str(args.get("status") or "").strip()
    error = str(args.get("error") or "").strip()
    if workflow:
        query = query.filter(AIAuditEvent.workflow == workflow)
    if status:
        query = query.filter(AIAuditEvent.status == status)
    if error:
        query = query.filter(AIAuditEvent.error_category == error)
    days = args.get("days")
    if days not in (None, ""):
        try:
            days_value = int(days)
        except (TypeError, ValueError) as exc:
            raise ValueError("days must be an integer between 1 and 90") from exc
        if days_value < 1 or days_value > 90:
            raise ValueError("days must be an integer between 1 and 90")
        query = query.filter(
            AIAuditEvent.created_at >= datetime.now(UTC) - timedelta(days=days_value)
        )
    return query.order_by(AIAuditEvent.created_at.desc(), AIAuditEvent.id.desc())


def current_admin_user():
    """Return the current authenticated master admin."""
    from app.security import current_user

    return current_user()


__all__ = [name for name in globals() if not name.startswith("__")]
