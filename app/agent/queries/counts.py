"""Permission-aware module counts for the agent."""

from __future__ import annotations

from app.models import User
from app.permissions import can_read_employee_context
from app.security import has_dashboard_permission
from app.services.ai_structured_source_service import module_count_source_card
from app.services.document_service import visible_documents_query
from app.services.error_service import visible_errors_query
from app.services.task_service import visible_tasks_query
from app.services.visibility_query_service import (
    visible_employees_query,
    visible_inventory_materials_query,
    visible_machines_query,
    visible_shiftplans_query,
)

from .common import DASHBOARD_SCOPE_LABELS, QueryOutcome, build_structured_context, denied_outcome

COUNT_SCOPES = (
    "tasks",
    "errors",
    "machines",
    "inventory",
    "documents",
    "shiftplans",
    "employees",
    "admin_users",
)
COUNT_ENTITY_TYPES = {
    "tasks": "tasks",
    "errors": "incidents",
    "machines": "machines",
    "inventory": "inventory",
    "documents": "documents",
    "shiftplans": "shiftplans",
    "employees": "employees",
    "admin_users": "admin_users",
}


def count_records(user, scope):
    """Return the visible record count for one dashboard scope."""
    scope = str(scope or "").strip().lower()
    if scope not in COUNT_SCOPES:
        raise ValueError(f"unsupported scope: {scope}")
    entity_type = COUNT_ENTITY_TYPES[scope]
    if scope == "employees":
        if not can_read_employee_context(user):
            return denied_outcome(entity_type, "employees")
        count = visible_employees_query(user).count()
        source_label = "Mitarbeiterdatenbank"
    elif scope == "admin_users":
        if not has_dashboard_permission(user, "admin_users", "view"):
            return denied_outcome(entity_type, "admin_users")
        count = User.query.count()
        source_label = "Nutzerverwaltung"
    else:
        if not has_dashboard_permission(user, scope, "view"):
            return denied_outcome(entity_type, scope)
        count = _count_query(user, scope).count()
        source_label = DASHBOARD_SCOPE_LABELS[scope]
    label = DASHBOARD_SCOPE_LABELS[scope]
    answer = f"## {label}\n- **Gesamt:** {count}\n- **Quelle:** {source_label}"
    source = module_count_source_card(scope, count, user)
    return QueryOutcome(
        entity_type=entity_type,
        scope=scope,
        answer_markdown=answer,
        count=count,
        filters={"scope": scope},
        sources=[source] if source else [],
        structured_context=build_structured_context(entity_type, query="count"),
        query="count",
    )


def _count_query(user, scope):
    """Return the visibility-scoped query for a countable scope."""
    return {
        "tasks": visible_tasks_query(user),
        "errors": visible_errors_query(user),
        "machines": visible_machines_query(user),
        "inventory": visible_inventory_materials_query(user),
        "documents": visible_documents_query(user),
        "shiftplans": visible_shiftplans_query(user),
    }[scope]
