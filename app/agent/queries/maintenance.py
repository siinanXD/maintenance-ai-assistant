"""Inspection and maintenance plan queries for the agent."""

from __future__ import annotations

from app.machines.maintenance_services import visible_maintenance_plans_query
from app.models import MaintenancePlan
from app.security import has_dashboard_permission
from app.services.ai_question_normalizer import normalize_text

from .common import (
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
    format_structured_list_answer,
)

DUE_STATES = {"overdue", "due_soon", "ok"}
KINDS = {"inspection", "maintenance"}
DUE_LABELS = {"overdue": "überfällig", "due_soon": "in 30 Tagen fällig", "ok": "im Plan"}
PLAN_NOUNS = {"inspection": "Prüfungen", "maintenance": "Wartungen", None: "Pläne"}


def list_maintenance_plans(user, *, due_state=None, kind=None, machine=None, count_only=False):
    """Return active plans filtered by due state, kind and machine, soonest first."""
    if not has_dashboard_permission(user, "machines", "view"):
        return denied_outcome("maintenance_plans", "machines", "Prüfungen und Wartung")
    due_state = str(due_state or "").strip() or None
    kind = str(kind or "").strip() or None
    if due_state and due_state not in DUE_STATES:
        raise ValueError(f"unsupported due_state: {due_state}")
    if kind and kind not in KINDS:
        raise ValueError(f"unsupported kind: {kind}")
    machine = str(machine or "").strip()

    query = visible_maintenance_plans_query(user).filter(MaintenancePlan.is_active.is_(True))
    if kind:
        query = query.filter(MaintenancePlan.kind == kind)
    plans = query.order_by(MaintenancePlan.next_due_date.asc(), MaintenancePlan.id.asc()).all()
    if due_state:
        plans = [plan for plan in plans if plan.due_state() == due_state]
    if machine:
        needle = normalize_text(machine)
        plans = [
            plan for plan in plans if plan.machine and needle in normalize_text(plan.machine.name)
        ]

    total = len(plans)
    visible = plans[:MAX_LIST_ITEMS]
    noun = PLAN_NOUNS[kind]
    title = f"{noun} {DUE_LABELS[due_state]}" if due_state else f"{noun} nach Fälligkeit"
    filters = {
        key: value
        for key, value in (("due_state", due_state), ("kind", kind), ("machine", machine))
        if value
    }
    answer = format_structured_list_answer(
        title=title,
        label=", ".join(f"{key}={value}" for key, value in filters.items()) or "aktive Pläne",
        items=[] if count_only else visible,
        total_count=total,
        count_label="Anzahl",
        formatter=_plan_line,
        source="Prüf- und Wartungspläne",
        overflow_suffix="weitere Pläne",
        empty_message="Keine passenden aktiven Pläne gefunden.",
    )
    return QueryOutcome(
        entity_type="maintenance_plans",
        scope="machines",
        answer_markdown=answer,
        count=total,
        items=[] if count_only else [_plan_payload(plan) for plan in visible],
        filters=filters,
        structured_context=build_structured_context(
            "maintenance_plans", status=due_state or "", machine=machine
        ),
        query="maintenance_plans",
    )


def _plan_line(plan):
    """Return one markdown line: due date, title, machine, last result."""
    machine = f", {plan.machine.name}" if plan.machine else ""
    basis = f" ({plan.legal_basis})" if plan.legal_basis else ""
    last = plan.records[0] if plan.records else None
    last_text = (
        f", zuletzt {last.performed_on.strftime('%d.%m.%Y')}" if last else ", noch kein Nachweis"
    )
    return f"- {plan.next_due_date.strftime('%d.%m.%Y')}: {plan.title}{basis}{machine}{last_text}"


def _plan_payload(plan):
    """Return safe plan data for the model."""
    return {
        "id": plan.id,
        "title": plan.title,
        "kind": plan.kind,
        "legal_basis": plan.legal_basis,
        "next_due_date": plan.next_due_date.isoformat(),
        "due_state": plan.due_state(),
        "machine": plan.machine.name if plan.machine else "",
        "last_result": plan.records[0].result if plan.records else None,
    }
