"""Rule-based deterministic shift plan generator."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import EmployeeMachineQualification, ShiftPlanEntry
from app.shiftplans.rules import validate_candidate_assignment
from app.shiftplans.scoring import (
    CandidateScore,
    explain_selection,
    score_candidate,
)
from app.shiftplans.templates import ShiftTemplate, ShiftWindow, resolve_shift_template


def build_local_shift_plan(
    start_date: date,
    days: int,
    shift_model_value: object,
    employees: list[object],
    machines: list[object],
    unavailable: dict[date, set[int]] | None = None,
    respect_active_weekdays: bool = True,
    preferences: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Build local shift entries and structured undercoverage slots."""
    entries, warnings = build_local_shift_entries(
        start_date,
        days,
        shift_model_value,
        employees,
        machines,
        unavailable=unavailable,
        respect_active_weekdays=respect_active_weekdays,
        preferences=preferences,
    )
    return entries, warnings, undercoverage_slots_from_warnings(warnings)


def build_local_shift_entries(
    start_date: date,
    days: int,
    shift_model_value: object,
    employees: list[object],
    machines: list[object],
    unavailable: dict[date, set[int]] | None = None,
    respect_active_weekdays: bool = True,
    preferences: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build valid local shift entries with hard-rule candidate filtering."""
    entries: list[dict[str, object]] = []
    planned_rule_entries: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    unavailable = unavailable or {}
    if not employees:
        return entries, warnings

    template = resolve_shift_template(shift_model_value)
    machines_to_plan = machines or [None]
    qualification_map = qualification_map_for(employees, machines_to_plan)
    vacation_days = vacation_days_from_unavailable(unavailable)
    historical_entries = historical_entries_for(employees, start_date)

    for day_offset in range(days):
        work_date = start_date + timedelta(days=day_offset)
        if respect_active_weekdays and not template.is_active_on(work_date):
            continue
        for machine in machines_to_plan:
            required = required_employee_count(machine, employees, template.shifts)
            for shift_window in template.shifts:
                assigned_for_slot = 0
                for _slot_index in range(required):
                    result = select_candidate_for_slot(
                        employees,
                        machine,
                        work_date,
                        shift_window,
                        template,
                        planned_rule_entries + historical_entries,
                        vacation_days,
                        qualification_map,
                        preferences,
                        enforce_active_weekdays=respect_active_weekdays,
                    )
                    if not result:
                        warnings.append(
                            coverage_warning(
                                work_date,
                                shift_window.key,
                                machine,
                                required,
                                assigned_for_slot,
                            )
                        )
                        break
                    employee, score = result
                    rule_entry = candidate_rule_entry(employee, machine, work_date, shift_window)
                    planned_rule_entries.append(rule_entry)
                    entries.append(shift_entry_payload(rule_entry, score))
                    assigned_for_slot += 1
    return entries, warnings


def select_candidate_for_slot(
    employees: list[object],
    machine: object | None,
    work_date: date,
    shift_window: ShiftWindow,
    template: ShiftTemplate,
    existing_entries: list[dict[str, object]],
    vacation_days: set[tuple[int, date]],
    qualification_map: dict[tuple[int, int], object],
    preferences: str,
    enforce_active_weekdays: bool = True,
) -> tuple[object, CandidateScore] | None:
    """Return the highest-scoring valid employee for one shift slot."""
    valid_candidates: list[tuple[object, CandidateScore]] = []
    for employee in employees:
        candidate = candidate_rule_entry(employee, machine, work_date, shift_window)
        violations = validate_candidate_assignment(
            candidate,
            existing_entries,
            vacation_days,
            qualification_map,
            template,
            enforce_active_weekdays=enforce_active_weekdays,
        )
        if violations:
            continue
        score = score_candidate(
            employee,
            machine,
            work_date,
            shift_window.key,
            existing_entries,
            qualification_map,
            template,
            preferences,
        )
        valid_candidates.append((employee, score))
    if not valid_candidates:
        return None
    return max(valid_candidates, key=lambda item: (item[1].total_score, -int(item[0].id)))


def candidate_rule_entry(
    employee: object,
    machine: object | None,
    work_date: date,
    shift_window: ShiftWindow,
) -> dict[str, object]:
    """Return a candidate entry used by rules and scoring."""
    return {
        "employee_id": int(employee.id),
        "machine_id": int(machine.id) if machine else None,
        "work_date": work_date,
        "shift": shift_window.key,
        "start_time": shift_window.start_time,
        "end_time": shift_window.end_time,
    }


def shift_entry_payload(
    rule_entry: dict[str, object],
    score: CandidateScore,
) -> dict[str, object]:
    """Return a persisted shift entry payload from a valid candidate."""
    return {
        "employee_id": rule_entry["employee_id"],
        "machine_id": rule_entry["machine_id"],
        "work_date": rule_entry["work_date"].isoformat(),
        "shift": rule_entry["shift"],
        "start_time": rule_entry["start_time"],
        "end_time": rule_entry["end_time"],
        "notes": explain_selection(score),
    }


def required_employee_count(
    machine: object | None,
    employees: list[object],
    shift_windows: tuple[ShiftWindow, ...],
) -> int:
    """Return how many employees are required for a shift slot."""
    if machine:
        return int(machine.required_employees)
    return max(1, len(employees) // max(1, len(shift_windows)))


def qualification_map_for(
    employees: list[object],
    machines: list[object | None],
) -> dict[tuple[int, int], object]:
    """Return machine qualifications keyed by employee and machine id."""
    employee_ids = {int(employee.id) for employee in employees}
    machine_ids = {int(machine.id) for machine in machines if machine}
    if not employee_ids or not machine_ids:
        return {}
    qualifications = EmployeeMachineQualification.query.filter(
        EmployeeMachineQualification.employee_id.in_(employee_ids),
        EmployeeMachineQualification.machine_id.in_(machine_ids),
    ).all()
    return {
        (qualification.employee_id, qualification.machine_id): qualification
        for qualification in qualifications
    }


def vacation_days_from_unavailable(
    unavailable: dict[date, set[int]],
) -> set[tuple[int, date]]:
    """Return blocked employee-date pairs from unavailable date mapping."""
    return {
        (int(employee_id), work_date)
        for work_date, employee_ids in unavailable.items()
        for employee_id in employee_ids
    }


def historical_entries_for(
    employees: list[object],
    start_date: date,
    lookback_days: int = 28,
) -> list[dict[str, object]]:
    """Return recent existing entries used for fair scoring and rest checks."""
    employee_ids = [int(employee.id) for employee in employees]
    if not employee_ids:
        return []
    period_start = start_date - timedelta(days=lookback_days)
    rows = ShiftPlanEntry.query.filter(
        ShiftPlanEntry.employee_id.in_(employee_ids),
        ShiftPlanEntry.work_date >= period_start,
        ShiftPlanEntry.work_date < start_date,
    ).all()
    return [
        {
            "employee_id": row.employee_id,
            "machine_id": row.machine_id,
            "work_date": row.work_date,
            "shift": row.shift,
            "start_time": row.start_time,
            "end_time": row.end_time,
        }
        for row in rows
    ]


def coverage_warning(
    work_date: date,
    shift_key: str,
    machine: object | None,
    required: int,
    slot_index: int,
) -> dict[str, object]:
    """Return a structured warning for one unfilled required slot."""
    machine_text = f" an {machine.name}" if machine else ""
    missing = max(0, required - slot_index)
    return {
        "type": "coverage",
        "severity": "critical",
        "machine_id": machine.id if machine else None,
        "machine_name": machine.name if machine else None,
        "work_date": work_date.isoformat(),
        "shift": shift_key,
        "required": required,
        "assigned": slot_index,
        "missing": missing,
        "reason": "Keine regelkonforme Besetzung moeglich",
        "suggestion": (
            "Maschinenqualifikationen pflegen oder zusaetzliche " "Mitarbeitende freigeben"
        ),
        "message": (
            f"Keine regelkonforme Besetzung am {work_date.isoformat()} "
            f"fuer {shift_key}{machine_text}."
        ),
    }


def undercoverage_slots_from_warnings(
    warnings: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return visible undercoverage slots derived from coverage warnings."""
    slots = {}
    for warning in warnings:
        if warning.get("type") != "coverage":
            continue
        key = (
            warning.get("work_date"),
            warning.get("shift"),
            warning.get("machine_id"),
        )
        slots[key] = {
            "work_date": warning.get("work_date"),
            "shift": warning.get("shift"),
            "machine_id": warning.get("machine_id"),
            "machine_name": warning.get("machine_name"),
            "required": int(warning.get("required") or 0),
            "assigned": int(warning.get("assigned") or 0),
            "missing": int(warning.get("missing") or 0),
            "reason": warning.get("reason") or "Keine regelkonforme Besetzung moeglich",
            "suggestion": (
                warning.get("suggestion")
                or "Maschinenqualifikationen pflegen oder Mitarbeitende freigeben"
            ),
        }
    return sorted(
        slots.values(),
        key=lambda slot: (
            str(slot.get("work_date") or ""),
            str(slot.get("shift") or ""),
            int(slot.get("machine_id") or 0),
        ),
    )
