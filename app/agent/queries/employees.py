"""Employee lists, counts and availability for the agent."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import Employee, VacationRequest
from app.permissions import can_read_employee_context
from app.security import employee_access_level
from app.services.ai_structured_source_service import (
    employee_count_source_card,
    employee_source_cards,
)
from app.services.visibility_query_service import visible_employees_query
from app.vacations.services import visible_vacation_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
)

AVAILABILITY_MODES = {"available_today", "absent_today", "absent_tomorrow"}


def list_employees(user, *, department=None, availability=None, role=None, count_only=False):
    """Return visible employees, optionally filtered by department or availability."""
    if not can_read_employee_context(user):
        return denied_outcome("employees", "employees")
    department = str(department or "").strip()
    availability = str(availability or "").strip().lower()
    if str(role or "").strip().lower() == "team_lead":
        return _team_lead_unavailable(department)
    if availability in AVAILABILITY_MODES:
        return _availability(user, availability)
    if department:
        if count_only:
            return _department_count(user, department)
        return _department_list(user, department)
    if count_only:
        return _total_count(user)
    return _total_list(user)


def _total_count(user):
    """Return the visible employee total."""
    count = visible_employees_query(user).count()
    source = employee_count_source_card(count, user)
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            f"## Mitarbeiter\n- **Gesamt:** {count}\n- **Quelle:** Mitarbeiterdatenbank"
        ),
        count=count,
        sources=[source] if source else [],
        structured_context=build_structured_context("employees", query="count"),
        query="count",
    )


def _department_count(user, department):
    """Return the visible employee count for one department."""
    count = _employees_in_department(user, department).count()
    source = employee_count_source_card(count, user, department=department)
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            "## Mitarbeiter\n"
            f"- **Bereich:** {department}\n"
            f"- **Sichtbare Mitarbeiter:** {count}\n"
            "- **Quelle:** Strukturierte Mitarbeiterdaten"
        ),
        count=count,
        filters={"department": department},
        sources=[source] if source else [],
        structured_context=build_structured_context(
            "employees", department=department, query="department_count"
        ),
        query="department_count",
    )


def _total_list(user):
    """Return all visible employees."""
    employees = (
        visible_employees_query(user)
        .order_by(Employee.name.asc(), Employee.id.asc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    return _employee_list_outcome(
        user,
        employees,
        title="Mitarbeiter",
        label="alle sichtbaren Mitarbeiter",
        count_label="Sichtbare Mitarbeiter",
        query="total_list",
    )


def _department_list(user, department):
    """Return visible employees for one department."""
    employees = (
        _employees_in_department(user, department)
        .order_by(Employee.name.asc(), Employee.id.asc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    return _employee_list_outcome(
        user,
        employees,
        title="Mitarbeiter",
        label=department,
        count_label="Sichtbare Mitarbeiter",
        query="department_list",
        department=department,
    )


def _availability(user, mode):
    """Return available or absent employees for today or tomorrow."""
    target_date = date.today() + timedelta(days=1 if mode.endswith("tomorrow") else 0)
    label = "morgen" if mode.endswith("tomorrow") else "heute"
    if mode == "available_today":
        employees = (
            visible_employees_query(user)
            .order_by(Employee.name.asc(), Employee.id.asc())
            .limit(MAX_LIST_ITEMS)
            .all()
        )
        absent_ids = _approved_absent_employee_ids(user, target_date)
        available = [employee for employee in employees if employee.id not in absent_ids]
        return _employee_list_outcome(
            user,
            available,
            title="Verfuegbare Mitarbeiter",
            label=label,
            count_label="Sichtbar verfuegbar",
            source="Strukturierte Mitarbeiterdaten und sichtbare genehmigte Urlaube",
            query="available",
            item_extra={"availability_status": "available"},
            extra={"date": target_date.isoformat()},
        )
    vacations = (
        visible_vacation_query(user)
        .filter(
            VacationRequest.status == "approved",
            VacationRequest.start_date <= target_date,
            VacationRequest.end_date >= target_date,
        )
        .order_by(VacationRequest.start_date.asc(), VacationRequest.id.asc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    visible_ids = {
        employee_id for (employee_id,) in visible_employees_query(user).with_entities(Employee.id)
    }
    employees = [
        vacation.employee
        for vacation in vacations
        if vacation.employee and vacation.employee_id in visible_ids
    ]
    return _employee_list_outcome(
        user,
        employees,
        title="Abwesende Mitarbeiter",
        label=label,
        count_label="Genehmigt abwesend",
        source="Sichtbare genehmigte Urlaube",
        query="approved_absences",
        item_extra={"availability_status": "absent", "absence_source": "approved_vacation"},
        extra={"date": target_date.isoformat()},
    )


def _team_lead_unavailable(department):
    """Return a grounded no-data answer: there is no structured team-lead field."""
    department_line = f"- **Bereich:** {department}\n" if department else ""
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            "## Teamleiter\n"
            f"{department_line}"
            "- **Status:** Kein strukturiertes Teamleiter-Feld vorhanden\n"
            "- **Quelle:** Strukturierte Mitarbeiterdaten"
        ),
        filters={"department": department} if department else {},
        structured_context=build_structured_context("employees", department=department),
        extra={"reason": "team_lead_field_missing"},
        query="team_lead",
    )


def _employee_list_outcome(
    user,
    employees,
    *,
    title,
    label,
    count_label,
    query,
    source=None,
    department="",
    item_extra=None,
    extra=None,
):
    """Return a formatted employee list outcome."""
    access_level = employee_access_level(user)
    items = [
        {**employee_payload_for_access_level(employee, access_level), **(item_extra or {})}
        for employee in employees
    ]
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=format_employee_list_answer(
            title, label, employees, count_label, source=source
        ),
        count=len(employees),
        items=items,
        filters={"department": department} if department else {},
        sources=employee_source_cards(employees, user),
        structured_context=build_structured_context(
            "employees", department=department, query=query
        ),
        extra=extra or {},
        query=query,
    )


def _employees_in_department(user, department):
    """Return visible employees filtered to one department."""
    return visible_employees_query(user).filter(Employee.department.ilike(department))


def _approved_absent_employee_ids(user, target_date):
    """Return employee ids with visible approved vacation on a date."""
    vacations = visible_vacation_query(user).filter(
        VacationRequest.status == "approved",
        VacationRequest.start_date <= target_date,
        VacationRequest.end_date >= target_date,
    )
    return {vacation.employee_id for vacation in vacations.all()}


def employee_payload_for_access_level(employee, access_level):
    """Return compact employee data allowed by the user's employee access level."""
    payload = {
        "id": employee.id,
        "personnel_number": employee.personnel_number,
        "name": employee.name,
        "department": employee.department,
        "team": employee.team,
    }
    if access_level != "shift":
        return payload
    payload.update(
        {
            "shift_model": employee.shift_model,
            "last_shift": employee.last_shift,
            "current_shift": employee.current_shift,
            "next_shift": employee.next_shift,
            "qualifications": employee.qualifications,
            "favorite_machine": employee.favorite_machine,
            "machine_qualifications": [
                {
                    "id": qualification.id,
                    "machine_id": qualification.machine_id,
                    "machine": qualification.machine.to_dict() if qualification.machine else None,
                    "level": qualification.level,
                    "valid_until": (
                        qualification.valid_until.isoformat() if qualification.valid_until else None
                    ),
                }
                for qualification in employee.machine_qualifications
            ],
        }
    )
    return payload


def format_employee_list_answer(
    title, label, employees, count_label, source=None, total_count=None
):
    """Return a compact German employee list answer."""
    visible_total = total_count if total_count is not None else len(employees)
    lines = [
        f"## {title}",
        f"- **Filter:** {label}",
        f"- **{count_label}:** {visible_total}",
        f"- **Quelle:** {source or 'Strukturierte Mitarbeiterdaten'}",
    ]
    if total_count is not None and total_count > len(employees):
        lines.append(
            f"- **Hinweis:** {len(employees)} von {total_count} sichtbaren Mitarbeitern angezeigt"
        )
    if not employees:
        lines.append("")
        lines.append("Keine sichtbaren Mitarbeiter fuer diese Anfrage gefunden.")
        return "\n".join(lines)
    lines.append("")
    lines.append("Sichtbare Mitarbeiter:")
    for employee in employees[:MAX_ANSWER_ITEMS]:
        team = f", Team {employee.team}" if employee.team is not None else ""
        lines.append(f"- {employee.name} ({employee.department}{team})")
    if len(employees) > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {len(employees) - MAX_ANSWER_ITEMS} weitere sichtbare Mitarbeiter")
    return "\n".join(lines)
