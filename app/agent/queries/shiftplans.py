"""Shift-plan entry, count and coverage queries for the agent."""

from __future__ import annotations

from datetime import timedelta

from app.models import ShiftPlan, ShiftPlanCoverageSlot, ShiftPlanEntry
from app.security import employee_access_level, has_dashboard_permission
from app.services.ai_structured_source_service import (
    shiftplan_coverage_source_cards,
    shiftplan_entry_source_cards,
)
from app.services.visibility_query_service import visible_shiftplans_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_SHIFTPLAN_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
    parse_iso_date,
    plant_today,
    tomorrow,
)

MODES = {"entries", "count", "understaffed"}
SHIFT_NAMES = {
    "early": "Frueh",
    "frueh": "Frueh",
    "fruehschicht": "Frueh",
    "late": "Spaet",
    "spaet": "Spaet",
    "spaetschicht": "Spaet",
    "night": "Nacht",
    "nacht": "Nacht",
    "nachtschicht": "Nacht",
}


def list_shift_entries(user, *, mode="entries", date=None, time_range=None, shift=None):
    """Return shift entries for a date, a shift headcount or next week's undercoverage."""
    if not has_dashboard_permission(user, "shiftplans", "view"):
        return denied_outcome("shiftplans", "shiftplans", "Schichtplanung")
    mode = str(mode or "entries").strip().lower()
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    shift_name = _shift_name(shift)
    if mode == "understaffed":
        return _understaffed_next_week(user)
    if mode == "count":
        return _shift_count(user, shift_name)
    work_date = parse_iso_date(date) or _date_for_time_range(time_range)
    return _entries_for_date(user, work_date, shift_name)


def _shift_name(value):
    """Return the canonical shift name for an alias or an empty string."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in SHIFT_NAMES:
        return SHIFT_NAMES[text]
    raise ValueError(f"unsupported shift: {value}")


def _date_for_time_range(time_range):
    """Return a work date for the supported relative ranges (default tomorrow)."""
    text = str(time_range or "").strip().lower()
    if text == "today":
        return plant_today()
    return tomorrow()


def _entries_for_date(user, work_date, shift):
    """Return visible shift entries for one date and optional shift."""
    entries = [entry for entry in _visible_entries(user) if entry.work_date == work_date]
    if shift:
        entries = [entry for entry in entries if entry.shift == shift]
    entries = entries[:MAX_SHIFTPLAN_LIST_ITEMS]
    label = "morgen" if work_date == tomorrow() else work_date.isoformat()
    title = f"{shift}schicht {label}" if shift else f"Eingeplant {label}"
    time_range = "tomorrow" if work_date == tomorrow() else ""
    filters = {"date": work_date.isoformat()}
    if shift:
        filters["shift"] = shift
    return QueryOutcome(
        entity_type="shiftplans",
        scope="shiftplans",
        answer_markdown=_format_entry_answer(title, entries, user),
        count=len(entries),
        items=[_entry_payload(entry, user) for entry in entries],
        filters=filters,
        sources=shiftplan_entry_source_cards(entries, user),
        structured_context=build_structured_context(
            "shiftplans", query="entries", time_range=time_range, shift=shift
        ),
        query="entries",
    )


def _shift_count(user, shift):
    """Return the visible planned headcount for one shift (or all shifts)."""
    entries = [entry for entry in _visible_entries(user) if not shift or entry.shift == shift][
        :MAX_SHIFTPLAN_LIST_ITEMS
    ]
    employee_ids = {entry.employee_id for entry in entries}
    label = shift or "alle Schichten"
    return QueryOutcome(
        entity_type="shiftplans",
        scope="shiftplans",
        answer_markdown=(
            "## Schichtplanung\n"
            f"- **Schicht:** {label}\n"
            f"- **Sichtbar eingeplante Mitarbeiter:** {len(employee_ids)}\n"
            "- **Quelle:** Strukturierte Schichtplandaten"
        ),
        count=len(employee_ids),
        items=[_entry_payload(entry, user) for entry in entries],
        filters={"shift": shift} if shift else {},
        sources=shiftplan_entry_source_cards(entries, user),
        structured_context=build_structured_context("shiftplans", query="shift_count", shift=shift),
        query="shift_count",
    )


def _understaffed_next_week(user):
    """Return visible undercoverage slots for the next calendar week."""
    today = plant_today()
    start_date = today + timedelta(days=7 - today.weekday())
    end_date = start_date + timedelta(days=6)
    slots = [
        slot
        for slot in _visible_coverage_slots(user)
        if start_date <= slot.work_date <= end_date and slot.missing > 0
    ][:MAX_SHIFTPLAN_LIST_ITEMS]
    lines = [
        "## Unterbesetzte Schichten naechste Woche",
        f"- **Unterbesetzte Slots:** {len(slots)}",
        "- **Quelle:** Strukturierte Schichtplandaten",
    ]
    if not slots:
        lines.extend(["", "Keine sichtbare Unterbesetzung fuer diesen Zeitraum gefunden."])
    else:
        lines.extend(["", "Sichtbare Unterbesetzung:"])
        for slot in slots[:MAX_ANSWER_ITEMS]:
            machine = slot.machine.name if slot.machine else "ohne Maschine"
            lines.append(
                f"- {slot.work_date.isoformat()} {slot.shift}: {machine}, fehlen {slot.missing}"
            )
        if len(slots) > MAX_ANSWER_ITEMS:
            lines.append(f"- ... {len(slots) - MAX_ANSWER_ITEMS} weitere Slots")
    return QueryOutcome(
        entity_type="shiftplans",
        scope="shiftplans",
        answer_markdown="\n".join(lines),
        count=len(slots),
        items=[_coverage_payload(slot) for slot in slots],
        filters={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        sources=shiftplan_coverage_source_cards(slots),
        structured_context=build_structured_context(
            "shiftplans", query="understaffed", time_range="next_week"
        ),
        query="understaffed",
    )


def _visible_entries(user):
    """Return entries belonging to visible (published or own-admin) shift plans."""
    plan_ids = _visible_plan_ids(user)
    if not plan_ids:
        return []
    return (
        ShiftPlanEntry.query.filter(ShiftPlanEntry.plan_id.in_(plan_ids))
        .order_by(
            ShiftPlanEntry.work_date.asc(), ShiftPlanEntry.shift.asc(), ShiftPlanEntry.id.asc()
        )
        .limit(MAX_SHIFTPLAN_LIST_ITEMS)
        .all()
    )


def _visible_coverage_slots(user):
    """Return coverage slots belonging to visible shift plans."""
    plan_ids = _visible_plan_ids(user)
    if not plan_ids:
        return []
    return (
        ShiftPlanCoverageSlot.query.filter(ShiftPlanCoverageSlot.plan_id.in_(plan_ids))
        .order_by(
            ShiftPlanCoverageSlot.work_date.asc(),
            ShiftPlanCoverageSlot.shift.asc(),
            ShiftPlanCoverageSlot.id.asc(),
        )
        .limit(MAX_SHIFTPLAN_LIST_ITEMS)
        .all()
    )


def _visible_plan_ids(user):
    """Return ids of shift plans visible to a user."""
    return [
        plan.id
        for plan in visible_shiftplans_query(user)
        .order_by(ShiftPlan.start_date.desc(), ShiftPlan.id.desc())
        .limit(MAX_SHIFTPLAN_LIST_ITEMS)
        .all()
    ]


def _entry_payload(entry, user):
    """Return safe shift-plan entry data honoring the employee access level."""
    employee = entry.employee
    machine = entry.machine
    access_level = employee_access_level(user)
    return {
        "id": entry.id,
        "plan_id": entry.plan_id,
        "department": entry.plan.department if entry.plan else "",
        "employee": employee.to_dict("basic") if employee and access_level != "none" else None,
        "employee_access_level": access_level,
        "machine": machine.to_dict() if machine else None,
        "work_date": entry.work_date.isoformat(),
        "shift": entry.shift,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
    }


def _coverage_payload(slot):
    """Return safe undercoverage data."""
    machine = slot.machine
    return {
        "id": slot.id,
        "plan_id": slot.plan_id,
        "department": slot.plan.department if slot.plan else "",
        "machine_id": slot.machine_id,
        "machine_name": machine.name if machine else "",
        "work_date": slot.work_date.isoformat(),
        "shift": slot.shift,
        "required": slot.required,
        "assigned": slot.assigned,
        "missing": slot.missing,
    }


def _format_entry_answer(title, entries, user):
    """Return a compact German shift entry answer."""
    access_level = employee_access_level(user)
    lines = [
        f"## {title}",
        f"- **Eintraege:** {len(entries)}",
        "- **Quelle:** Strukturierte Schichtplandaten",
    ]
    if not entries:
        lines.extend(["", "Keine sichtbaren Schichtplaneintraege fuer diese Anfrage gefunden."])
        return "\n".join(lines)
    lines.extend(["", "Sichtbare Einplanung:"])
    for entry in entries[:MAX_ANSWER_ITEMS]:
        if access_level == "none":
            employee_name = "Mitarbeiter nicht sichtbar"
        else:
            employee_name = entry.employee.name if entry.employee else "Unbekannt"
        lines.append(
            f"- {entry.work_date.isoformat()} {entry.shift}: "
            f"{employee_name} ({entry.start_time}-{entry.end_time})"
        )
    if len(entries) > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {len(entries) - MAX_ANSWER_ITEMS} weitere Eintraege")
    return "\n".join(lines)
