"""Vacation workflow service helpers."""

from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import false

from app.extensions import db
from app.models import Department, Employee, Role, ShiftPlanEntry, VacationRequest
from app.security import has_dashboard_permission
from app.services.operations_tracking_service import record_event
from app.shiftplans.services import parse_date

VALID_VACATION_STATUSES = {"pending", "approved", "rejected", "cancelled"}
ACTIVE_VACATION_STATUSES = ("pending", "approved")
VACATION_SHIFT_TYPES = {"", "Frueh", "Spaet", "Nacht", "Tag", "Alle"}


def count_workdays(start, end):
    """Count Monday through Friday workdays between start and end, inclusive."""
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def parse_year_arg(value=None):
    """Parse a vacation year query argument or return the current year."""
    raw_year = value or datetime.now(UTC).year
    try:
        year = int(raw_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("year muss eine Zahl sein") from exc
    if year < 1900 or year > 2200:
        raise ValueError("year liegt außerhalb des erlaubten Bereichs")
    return year


def optional_int(value):
    """Return an integer for optional form values or None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("ID muss eine Zahl sein") from exc


def bounded_text(value, limit):
    """Return stripped text limited to the given number of characters."""
    return str(value or "").strip()[:limit]


def normalize_shift_type(value):
    """Return a supported vacation shift type."""
    shift_type = str(value or "").strip()
    if shift_type not in VACATION_SHIFT_TYPES:
        raise ValueError("shift_type ist ungültig")
    return shift_type


def employee_in_user_department(user, employee):
    """Return whether an employee belongs to the current user's department."""
    if not user or not employee or not user.department:
        return False
    return employee.department == user.department.name


def can_manage_department_vacations(user):
    """Return whether a user can manage vacation requests for their department."""
    return bool(
        user
        and user.role != Role.MASTER_ADMIN
        and user.department
        and has_dashboard_permission(user, "employees", "write")
    )


def can_create_vacation_for_employee(user, employee):
    """Return whether a user can submit a vacation request for an employee."""
    if not user or not employee:
        return False
    if user.role == Role.MASTER_ADMIN:
        return True
    if user.employee_id == employee.id:
        return True
    return can_manage_department_vacations(user) and employee_in_user_department(
        user,
        employee,
    )


def can_decide_vacation(user, vacation_request):
    """Return whether a user can approve or reject a vacation request."""
    if not user or not vacation_request:
        return False
    if user.role == Role.MASTER_ADMIN:
        return True
    return can_manage_department_vacations(user) and employee_in_user_department(
        user,
        vacation_request.employee,
    )


def visible_vacation_query(user):
    """Return the vacation query scoped to the current user's visibility."""
    query = VacationRequest.query
    if not user:
        return query.filter(false())
    if user.role == Role.MASTER_ADMIN:
        return query
    if can_manage_department_vacations(user):
        return query.join(Employee, VacationRequest.employee_id == Employee.id).filter(
            Employee.department == user.department.name,
        )
    if user.employee_id:
        return query.filter(VacationRequest.employee_id == user.employee_id)
    return query.filter(false())


def visible_employee_query(user):
    """Return employees visible in vacation summaries for the current user."""
    query = Employee.query
    if not user:
        return query.filter(false())
    if user.role == Role.MASTER_ADMIN:
        return query
    if can_manage_department_vacations(user):
        return query.filter(Employee.department == user.department.name)
    if user.employee_id:
        return query.filter(Employee.id == user.employee_id)
    return query.filter(false())


def vacation_days_for_statuses(employee_id, year, statuses, exclude_request_id=None):
    """Return summed vacation days for one employee, year and status set."""
    query = db.session.query(db.func.sum(VacationRequest.days_used)).filter(
        VacationRequest.employee_id == employee_id,
        VacationRequest.status.in_(statuses),
        db.extract("year", VacationRequest.start_date) == year,
    )
    if exclude_request_id is not None:
        query = query.filter(VacationRequest.id != exclude_request_id)
    return int(query.scalar() or 0)


def vacation_balance(employee_id, year):
    """Return vacation entitlement, used days and reserved pending days."""
    employee = db.session.get(Employee, employee_id)
    if not employee:
        return None
    used = vacation_days_for_statuses(employee_id, year, ("approved",))
    pending = vacation_days_for_statuses(employee_id, year, ("pending",))
    total = employee.vacation_days_per_year
    remaining = total - used
    return {
        "total": total,
        "used": used,
        "remaining": remaining,
        "pending": pending,
        "available": remaining - pending,
    }


def has_overlapping_active_request(employee_id, start_date, end_date, exclude_request_id=None):
    """Return whether an active vacation request overlaps the given range."""
    query = VacationRequest.query.filter(
        VacationRequest.employee_id == employee_id,
        VacationRequest.status.in_(ACTIVE_VACATION_STATUSES),
        VacationRequest.start_date <= end_date,
        VacationRequest.end_date >= start_date,
    )
    if exclude_request_id is not None:
        query = query.filter(VacationRequest.id != exclude_request_id)
    return query.first() is not None


def resolve_representative(representative_employee_id, employee):
    """Return the representative employee or a validation error tuple."""
    try:
        parsed_id = optional_int(representative_employee_id)
    except ValueError as exc:
        return None, {"error": str(exc)}, 400
    if parsed_id is None:
        return None, None, None
    if parsed_id == employee.id:
        return None, {"error": "Vertreter darf nicht die antragstellende Person sein"}, 400
    representative = db.session.get(Employee, parsed_id)
    if not representative:
        return None, {"error": "Vertreter nicht gefunden"}, 404
    if employee.department and representative.department != employee.department:
        return None, {"error": "Vertreter muss aus demselben Bereich kommen"}, 400
    return representative, None, None


def planned_shift_count(employee_id, start_date, end_date, shift_type=""):
    """Return how many existing shift-plan entries collide with the vacation period."""
    query = ShiftPlanEntry.query.filter(
        ShiftPlanEntry.employee_id == employee_id,
        ShiftPlanEntry.work_date >= start_date,
        ShiftPlanEntry.work_date <= end_date,
        ShiftPlanEntry.shift != "Urlaub",
    )
    if shift_type and shift_type not in {"Alle", "Tag"}:
        query = query.filter(ShiftPlanEntry.shift == shift_type)
    return query.count()


def department_absence_count(employee, start_date, end_date):
    """Return active absence counts in the employee department for the period."""
    if not employee.department:
        return 0, 0
    department_employee_ids = [
        item.id for item in Employee.query.filter(Employee.department == employee.department).all()
    ]
    if not department_employee_ids:
        return 0, 0
    overlapping = VacationRequest.query.filter(
        VacationRequest.employee_id.in_(department_employee_ids),
        VacationRequest.status.in_(ACTIVE_VACATION_STATUSES),
        VacationRequest.start_date <= end_date,
        VacationRequest.end_date >= start_date,
    ).all()
    absent_ids = {vacation.employee_id for vacation in overlapping}
    absent_ids.add(employee.id)
    return len(department_employee_ids), len(absent_ids)


def vacation_impact(employee, start_date, end_date, representative=None, shift_type=""):
    """Return operational impact metadata for a planned vacation request."""
    department_total, absent_count = department_absence_count(employee, start_date, end_date)
    planned_count = planned_shift_count(employee.id, start_date, end_date, shift_type)
    workdays = count_workdays(start_date, end_date)
    available_after_absence = max(0, department_total - absent_count)

    reasons = []
    level = "ok"
    if department_total and available_after_absence <= 1:
        level = "critical"
        reasons.append("Unterbesetzung im Bereich möglich")
    elif department_total and absent_count / max(department_total, 1) >= 0.35:
        level = "warning"
        reasons.append("Mehrere Abwesenheiten im Bereich")
    if planned_count:
        level = "critical" if level == "critical" else "warning"
        reasons.append(f"{planned_count} geplante Schichten betroffen")
    if not representative:
        level = "critical" if level == "critical" else "warning"
        reasons.append("kein Vertreter hinterlegt")

    if not reasons:
        summary = "Keine auffälligen Personal- oder Schichtkonflikte erkannt."
    else:
        summary = "; ".join(reasons) + "."

    return {
        "level": level,
        "summary": summary,
        "workdays": workdays,
        "department": employee.department,
        "department_employee_count": department_total,
        "overlapping_absence_count": absent_count,
        "available_after_absence": available_after_absence,
        "planned_shift_count": planned_count,
        "representative_ok": representative is not None,
    }


def build_vacation_impact_response(data, user):
    """Return an impact preview for the vacation request form."""
    try:
        employee_id = int(data.get("employee_id") or 0)
        start_date = parse_date(data.get("start_date"))
        end_date = parse_date(data.get("end_date"))
        shift_type = normalize_shift_type(data.get("shift_type"))
    except (TypeError, ValueError) as exc:
        return None, {"error": str(exc)}, 400
    if not employee_id:
        return None, {"error": "employee_id erforderlich"}, 400
    if end_date < start_date:
        return None, {"error": "Enddatum muss nach Startdatum liegen"}, 400
    employee = db.session.get(Employee, employee_id)
    if not employee:
        return None, {"error": "Mitarbeiter nicht gefunden"}, 404
    if not can_create_vacation_for_employee(user, employee):
        return None, {"error": "Fehlende Berechtigung"}, 403
    representative, error, status = resolve_representative(
        data.get("representative_employee_id"),
        employee,
    )
    if error:
        return None, error, status
    balance = vacation_balance(employee_id, start_date.year)
    impact = vacation_impact(employee, start_date, end_date, representative, shift_type)
    impact["overlap"] = has_overlapping_active_request(employee_id, start_date, end_date)
    impact["balance_exceeded"] = bool(balance and impact["workdays"] > balance["available"])
    return (
        {
            "employee": employee.to_dict("basic"),
            "representative": representative.to_dict("basic") if representative else None,
            "balance": balance,
            "impact": impact,
        },
        None,
        200,
    )


def vacation_event_state(vacation):
    """Return compact vacation request state for audit old/new values."""
    return {
        "id": vacation.id,
        "employee_id": vacation.employee_id,
        "status": vacation.status,
        "start_date": vacation.start_date.isoformat() if vacation.start_date else None,
        "end_date": vacation.end_date.isoformat() if vacation.end_date else None,
        "days_used": vacation.days_used,
        "approved_by": vacation.approved_by,
        "decided_at": vacation.decided_at.isoformat() if vacation.decided_at else None,
        "cancelled_by": vacation.cancelled_by,
        "cancelled_at": vacation.cancelled_at.isoformat() if vacation.cancelled_at else None,
        "representative_employee_id": vacation.representative_employee_id,
        "shift_type": vacation.shift_type,
        "impact_level": vacation.impact_level,
    }


def record_vacation_event(
    event_type,
    vacation,
    user,
    old_value=None,
    new_value=None,
    description="",
):
    """Persist a vacation operations event without breaking the main workflow."""
    try:
        department = Department.query.filter_by(name=vacation.employee.department).first()
        record_event(
            event_type=event_type,
            feature="vacations",
            entity_type="vacation_request",
            entity_id=vacation.id,
            user=user,
            department=department,
            metadata={
                "employee_id": vacation.employee_id,
                "status": vacation.status,
                "start_date": vacation.start_date.isoformat(),
                "end_date": vacation.end_date.isoformat(),
                "days_used": vacation.days_used,
                "impact_level": vacation.impact_level,
            },
            old_value=old_value,
            new_value=new_value,
            description=description,
            commit=True,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Vacation event logging failed",
            extra={"vacation_request_id": getattr(vacation, "id", None)},
        )


def list_vacation_requests(args, user):
    """Return visible vacation requests filtered by query arguments."""
    query = visible_vacation_query(user)

    status = (args.get("status") or "").strip()
    if status:
        if status not in VALID_VACATION_STATUSES:
            return None, {"error": "status ist ungültig"}, 400
        query = query.filter(VacationRequest.status == status)

    employee_id = (args.get("employee_id") or "").strip()
    if employee_id:
        try:
            query = query.filter(VacationRequest.employee_id == int(employee_id))
        except (TypeError, ValueError):
            return None, {"error": "employee_id muss eine Zahl sein"}, 400

    year = (args.get("year") or "").strip()
    if year:
        try:
            parsed_year = parse_year_arg(year)
        except ValueError as exc:
            return None, {"error": str(exc)}, 400
        query = query.filter(
            db.extract("year", VacationRequest.start_date) == parsed_year,
        )

    vacations = query.order_by(VacationRequest.start_date.desc()).all()
    return [vacation.to_dict() for vacation in vacations], None, 200


def create_vacation_request(data, user):
    """Create a pending vacation request after validating business rules."""
    try:
        employee_id = int(data.get("employee_id") or 0)
        start_date = parse_date(data.get("start_date"))
        end_date = parse_date(data.get("end_date"))
        shift_type = normalize_shift_type(data.get("shift_type"))
    except (TypeError, ValueError) as exc:
        return None, {"error": str(exc)}, 400

    if not employee_id:
        return None, {"error": "employee_id erforderlich"}, 400
    if end_date < start_date:
        return None, {"error": "Enddatum muss nach Startdatum liegen"}, 400

    employee = db.session.get(Employee, employee_id)
    if not employee:
        return None, {"error": "Mitarbeiter nicht gefunden"}, 404
    if not can_create_vacation_for_employee(user, employee):
        return None, {"error": "Fehlende Berechtigung"}, 403

    days = count_workdays(start_date, end_date)
    if days == 0:
        return None, {"error": "Kein Werktag im gewählten Zeitraum"}, 400
    if has_overlapping_active_request(employee_id, start_date, end_date):
        return (
            None,
            {"error": "Urlaubsantrag überschneidet sich mit einem aktiven Antrag"},
            409,
        )

    balance = vacation_balance(employee_id, start_date.year)
    if not balance or days > balance["available"]:
        return None, {"error": "Nicht genug verfügbarer Resturlaub"}, 409

    representative, error, status = resolve_representative(
        data.get("representative_employee_id"),
        employee,
    )
    if error:
        return None, error, status
    impact = vacation_impact(employee, start_date, end_date, representative, shift_type)

    vacation = VacationRequest(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        days_used=days,
        status="pending",
        requested_by=user.id,
        representative_employee_id=representative.id if representative else None,
        shift_type=shift_type,
        reason=bounded_text(data.get("reason"), 160),
        impact_level=impact["level"],
        impact_summary=impact["summary"],
        notes=bounded_text(data.get("notes"), 500),
    )
    db.session.add(vacation)
    db.session.commit()
    record_vacation_event(
        "vacation.requested",
        vacation,
        user,
        new_value=vacation_event_state(vacation),
        description=f"Urlaubsantrag erstellt: Mitarbeiter {vacation.employee_id}",
    )
    return vacation.to_dict(), None, 201


def delete_vacation_request(request_id, user):
    """Delete a pending vacation request if the user may withdraw it."""
    vacation = db.session.get(VacationRequest, request_id)
    if not vacation:
        return None, {"error": "Urlaubsantrag nicht gefunden"}, 404
    if vacation.status != "pending":
        return None, {"error": "Nur ausstehende Anträge können zurückgezogen werden"}, 409
    if user.role != Role.MASTER_ADMIN and user.employee_id != vacation.employee_id:
        return None, {"error": "Fehlende Berechtigung"}, 403
    db.session.delete(vacation)
    db.session.commit()
    return None, None, 204


def decide_vacation_request(request_id, user, status):
    """Approve or reject a vacation request."""
    if status not in {"approved", "rejected"}:
        return None, {"error": "Entscheidung ist ungültig"}, 400
    vacation = db.session.get(VacationRequest, request_id)
    if not vacation:
        return None, {"error": "Urlaubsantrag nicht gefunden"}, 404
    if not can_decide_vacation(user, vacation):
        return None, {"error": "Fehlende Berechtigung"}, 403
    if vacation.status != "pending":
        return None, {"error": "Antrag ist nicht mehr ausstehend"}, 409

    old_state = vacation_event_state(vacation)
    if status == "approved":
        total = vacation.employee.vacation_days_per_year
        used_without_request = vacation_days_for_statuses(
            vacation.employee_id,
            vacation.start_date.year,
            ("approved",),
            exclude_request_id=vacation.id,
        )
        if used_without_request + vacation.days_used > total:
            return None, {"error": "Nicht genug verfügbarer Resturlaub"}, 409

    vacation.status = status
    vacation.approved_by = user.id
    vacation.decided_at = datetime.now(UTC)
    db.session.commit()
    event_type = "vacation.approved" if status == "approved" else "vacation.rejected"
    record_vacation_event(
        event_type,
        vacation,
        user,
        old_value=old_state,
        new_value=vacation_event_state(vacation),
        description=f"Urlaubsantrag {status}: Mitarbeiter {vacation.employee_id}",
    )
    return vacation.to_dict(), None, 200


def can_cancel_vacation(user, vacation_request):
    """Return whether a user can cancel a vacation request."""
    if not user or not vacation_request:
        return False
    if user.role == Role.MASTER_ADMIN:
        return True
    if user.employee_id == vacation_request.employee_id:
        return True
    return can_manage_department_vacations(user) and employee_in_user_department(
        user,
        vacation_request.employee,
    )


def cancel_vacation_request(request_id, user):
    """Cancel a pending or approved vacation request without deleting its history."""
    vacation = db.session.get(VacationRequest, request_id)
    if not vacation:
        return None, {"error": "Urlaubsantrag nicht gefunden"}, 404
    if vacation.status == "cancelled":
        return None, {"error": "Urlaubsantrag ist bereits storniert"}, 409
    if vacation.status == "rejected":
        return None, {"error": "Abgelehnte Anträge können nicht storniert werden"}, 409
    if not can_cancel_vacation(user, vacation):
        return None, {"error": "Fehlende Berechtigung"}, 403

    old_state = vacation_event_state(vacation)
    vacation.status = "cancelled"
    vacation.cancelled_by = user.id
    vacation.cancelled_at = datetime.now(UTC)
    db.session.commit()
    record_vacation_event(
        "vacation.cancelled",
        vacation,
        user,
        old_value=old_state,
        new_value=vacation_event_state(vacation),
        description=f"Urlaubsantrag storniert: Mitarbeiter {vacation.employee_id}",
    )
    return vacation.to_dict(), None, 200


def vacation_summary_for_user(args, user):
    """Return vacation balances for employees visible to the user."""
    try:
        year = parse_year_arg(args.get("year"))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    employees = visible_employee_query(user).order_by(Employee.name.asc()).all()
    result = []
    for employee in employees:
        balance = vacation_balance(employee.id, year)
        result.append(
            {
                "employee_id": employee.id,
                "name": employee.name,
                "department": employee.department,
                "team": employee.team,
                "shift_model": employee.shift_model,
                "current_shift": employee.current_shift,
                "qualifications": employee.qualifications,
                **balance,
            }
        )
    return result, None, 200
