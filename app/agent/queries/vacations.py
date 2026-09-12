"""Vacation and absence queries for the agent."""

from __future__ import annotations

from app.models import VacationRequest
from app.services.ai_question_normalizer import normalize_text
from app.services.ai_structured_source_service import vacation_source_cards
from app.vacations.services import visible_vacation_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    next_week_bounds,
    parse_iso_date,
    tomorrow,
)

SCOPES = {"pending", "own_pending", "own_latest", "absences"}
STATUS_LABELS = {
    "approved": "genehmigt",
    "cancelled": "storniert",
    "pending": "offen",
    "rejected": "abgelehnt",
}


def list_vacations(
    user,
    *,
    scope="pending",
    time_range=None,
    date_from=None,
    date_to=None,
    department=None,
    count_only=False,
):
    """Return vacation requests or absences for the requested scope."""
    scope = str(scope or "pending").strip().lower()
    if scope not in SCOPES:
        raise ValueError(f"unsupported scope: {scope}")
    if scope == "own_pending":
        return _own_pending(user)
    if scope == "own_latest":
        return _own_latest_status(user)
    if scope == "pending":
        return _pending(user, count_only)
    return _absences(user, time_range, date_from, date_to, str(department or "").strip())


def _pending(user, count_only):
    """Return visible pending vacation requests (count or list)."""
    query = visible_vacation_query(user).filter(VacationRequest.status == "pending")
    count = query.count()
    limit = MAX_ANSWER_ITEMS if count_only else MAX_LIST_ITEMS
    vacations = (
        query.order_by(VacationRequest.created_at.desc(), VacationRequest.start_date.desc())
        .limit(limit)
        .all()
    )
    return QueryOutcome(
        entity_type="vacations",
        scope="employees",
        answer_markdown=_format_pending_answer(count, vacations),
        count=count,
        items=[_vacation_payload(vacation) for vacation in vacations],
        filters={"status": "pending"},
        sources=vacation_source_cards(vacations),
        structured_context=build_structured_context(
            "vacations", query="pending_count", status="pending"
        ),
        query="pending_count" if count_only else "pending_list",
    )


def _own_pending(user):
    """Return the current user's own pending vacation requests."""
    if not getattr(user, "employee_id", None):
        return _no_result("own_pending", "Keine eigene Mitarbeiterzuordnung gefunden.")
    vacations = (
        visible_vacation_query(user)
        .filter(
            VacationRequest.employee_id == user.employee_id,
            VacationRequest.status == "pending",
        )
        .order_by(VacationRequest.created_at.desc(), VacationRequest.start_date.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    lines = [
        "## Urlaub",
        f"- **Offene Antraege:** {len(vacations)}",
        "- **Quelle:** Strukturierte Urlaubsdaten",
    ]
    if not vacations:
        lines.extend(["", "Du hast keinen sichtbaren offenen Urlaubsantrag."])
    else:
        lines.extend(["", "Offene Antraege:"])
        lines.extend(_vacation_line(vacation) for vacation in vacations[:MAX_ANSWER_ITEMS])
    return QueryOutcome(
        entity_type="vacations",
        scope="employees",
        answer_markdown="\n".join(lines),
        count=len(vacations),
        items=[_vacation_payload(vacation) for vacation in vacations],
        filters={"scope": "own_pending"},
        sources=vacation_source_cards(vacations, role_visibility=f"employee:{user.employee_id}"),
        structured_context=build_structured_context("vacations", query="own_pending"),
        query="own_pending",
    )


def _own_latest_status(user):
    """Return the latest visible vacation request status for the current user."""
    if not getattr(user, "employee_id", None):
        return _no_result("own_latest_status", "Keine eigene Mitarbeiterzuordnung gefunden.")
    vacation = (
        visible_vacation_query(user)
        .filter(VacationRequest.employee_id == user.employee_id)
        .order_by(VacationRequest.created_at.desc(), VacationRequest.start_date.desc())
        .first()
    )
    vacations = [vacation] if vacation else []
    lines = ["## Urlaubsantrag", "- **Quelle:** Strukturierte Urlaubsdaten"]
    if not vacation:
        lines.append("- **Status:** Kein sichtbarer Urlaubsantrag gefunden.")
    else:
        lines.extend(
            [
                f"- **Status:** {STATUS_LABELS.get(vacation.status, vacation.status)}",
                f"- **Zeitraum:** {vacation.start_date.isoformat()} "
                f"bis {vacation.end_date.isoformat()}",
                f"- **Arbeitstage:** {vacation.days_used}",
            ]
        )
    return QueryOutcome(
        entity_type="vacations",
        scope="employees",
        answer_markdown="\n".join(lines),
        count=len(vacations),
        items=[_vacation_payload(item) for item in vacations],
        filters={"scope": "own_latest"},
        sources=vacation_source_cards(vacations, role_visibility=f"employee:{user.employee_id}"),
        structured_context=build_structured_context("vacations", query="own_latest_status"),
        query="own_latest_status",
    )


def _absences(user, time_range, date_from, date_to, department):
    """Return approved visible vacations overlapping a period."""
    time_range = str(time_range or "").strip().lower()
    start_date = parse_iso_date(date_from)
    end_date = parse_iso_date(date_to)
    if start_date or end_date:
        start_date = start_date or end_date
        end_date = end_date or start_date
        label = (
            start_date.isoformat()
            if start_date == end_date
            else f"{start_date.isoformat()} bis {end_date.isoformat()}"
        )
        time_range = ""
    elif time_range == "next_week":
        start_date, end_date = next_week_bounds()
        label = "naechste Woche"
    else:
        start_date = end_date = tomorrow()
        label = "morgen"
        time_range = "tomorrow"
    vacations = (
        visible_vacation_query(user)
        .filter(
            VacationRequest.status == "approved",
            VacationRequest.start_date <= end_date,
            VacationRequest.end_date >= start_date,
        )
        .order_by(VacationRequest.start_date.asc(), VacationRequest.id.asc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    if department:
        vacations = [
            vacation
            for vacation in vacations
            if vacation.employee
            and normalize_text(vacation.employee.department) == normalize_text(department)
        ]
    lines = [
        "## Abwesenheiten",
        f"- **Zeitraum:** {label}",
        f"- **Genehmigte Urlaube:** {len(vacations)}",
        "- **Quelle:** Strukturierte Urlaubsdaten",
    ]
    if not vacations:
        lines.extend(["", "Keine sichtbaren genehmigten Urlaube fuer diesen Zeitraum gefunden."])
    else:
        lines.extend(["", "Sichtbare Abwesenheiten:"])
        lines.extend(_vacation_line(vacation) for vacation in vacations[:MAX_ANSWER_ITEMS])
        if len(vacations) > MAX_ANSWER_ITEMS:
            lines.append(f"- ... {len(vacations) - MAX_ANSWER_ITEMS} weitere sichtbare Urlaube")
    filters = {"status": "approved", "period": label}
    if department:
        filters["department"] = department
    return QueryOutcome(
        entity_type="vacations",
        scope="employees",
        answer_markdown="\n".join(lines),
        count=len(vacations),
        items=[_vacation_payload(vacation) for vacation in vacations],
        filters=filters,
        sources=vacation_source_cards(vacations),
        structured_context=build_structured_context(
            "vacations",
            query="approved_absences",
            time_range=time_range,
            department=department,
            status="approved",
        ),
        extra={
            "period": {
                "label": label,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        },
        query="approved_absences",
    )


def _no_result(query, message):
    """Return a safe no-result vacation outcome."""
    return QueryOutcome(
        entity_type="vacations",
        scope="employees",
        answer_markdown="## Urlaub\n- **Quelle:** Strukturierte Urlaubsdaten\n\n" + message,
        structured_context=build_structured_context("vacations"),
        query=query,
    )


def _format_pending_answer(count, examples):
    """Return a compact German answer for visible pending vacation requests."""
    lines = [
        "## Offene Urlaubsantraege",
        f"- **Anzahl:** {count}",
        "- **Quelle:** Strukturierte Urlaubsdaten",
    ]
    if examples:
        lines.extend(["", "Sichtbare Beispiele:"])
        lines.extend(_vacation_line(vacation) for vacation in examples[:MAX_ANSWER_ITEMS])
    return "\n".join(lines)


def _vacation_payload(vacation):
    """Return compact prompt-safe vacation data."""
    employee = vacation.employee
    return {
        "id": vacation.id,
        "employee_id": vacation.employee_id,
        "employee_name": employee.name if employee else "",
        "department": employee.department if employee else "",
        "start_date": vacation.start_date.isoformat(),
        "end_date": vacation.end_date.isoformat(),
        "days_used": vacation.days_used,
        "status": vacation.status,
        "status_label": STATUS_LABELS.get(vacation.status, vacation.status),
        "shift_type": vacation.shift_type,
        "created_at": vacation.created_at.isoformat() if vacation.created_at else "",
    }


def _vacation_line(vacation):
    """Return one compact vacation answer line."""
    employee = vacation.employee
    name = employee.name if employee else "Unbekannt"
    department = employee.department if employee else "ohne Bereich"
    return (
        f"- #{vacation.id} {name} ({department}): "
        f"{vacation.start_date.isoformat()} bis {vacation.end_date.isoformat()}, "
        f"{STATUS_LABELS.get(vacation.status, vacation.status)}"
    )
