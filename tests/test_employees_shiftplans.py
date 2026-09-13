"""Tests for employee and shift planning workflows."""

from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from app.extensions import db
from app.models import (
    EmployeeMachineQualification,
    Notification,
    Role,
    ShiftPlan,
    ShiftPlanEntry,
    User,
    VacationRequest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _add_machine_qualifications(app, employee_ids, machine_ids, level="trained"):
    """Create structured qualifications for the given employees and machines."""
    with app.app_context():
        for employee_id in employee_ids:
            for machine_id in machine_ids:
                db.session.add(
                    EmployeeMachineQualification(
                        employee_id=employee_id,
                        machine_id=machine_id,
                        level=level,
                    )
                )
        db.session.commit()


def test_employee_create_rejects_missing_duplicate_and_invalid_values(
    client,
    make_user,
    auth_headers,
):
    """Verify employee creation validates required, duplicate and typed fields."""
    admin = make_user(
        username="employee_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])

    missing_response = client.post("/api/v1/employees", headers=headers, json={})
    create_response = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "personnel_number": "P-200",
            "name": "Lisa Produktion",
            "birth_date": "1991-02-03",
            "team": 2,
            "department": "Produktion",
        },
    )
    duplicate_response = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"personnel_number": "P-200", "name": "Lisa Produktion"},
    )
    invalid_response = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "personnel_number": "P-201",
            "name": "Ungueltig",
            "birth_date": "03-02-1991",
        },
    )

    assert missing_response.status_code == 400
    assert create_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert invalid_response.status_code == 400


def test_employee_shift_access_includes_shift_but_not_confidential_fields(
    client,
    make_user,
    make_employee,
    auth_headers,
    set_dashboard_permission,
):
    """Verify shift-level employee access excludes confidential fields."""
    user = make_user(
        username="employee_shift_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_employee(name="Shift Person", salary_group="E10")
    set_dashboard_permission(
        user["username"],
        "employees",
        can_view=True,
        can_write=False,
        employee_access_level="shift",
    )

    response = client.get("/api/v1/employees", headers=auth_headers(user["username"]))

    payload = response.get_json()["data"][0]
    assert response.status_code == 200
    assert payload["qualifications"] == "CNC"
    assert "salary_group" not in payload
    assert "documents" not in payload


def test_employee_write_requires_confidential_access(
    client,
    make_user,
    auth_headers,
    set_dashboard_permission,
):
    """Verify employee writes require both write permission and confidential access."""
    user = make_user(
        username="employee_write_guard",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    set_dashboard_permission(
        user["username"],
        "employees",
        can_view=True,
        can_write=True,
        employee_access_level="shift",
    )

    response = client.post(
        "/api/v1/employees",
        headers=auth_headers(user["username"]),
        json={"personnel_number": "P-300", "name": "Nicht erlaubt"},
    )

    assert response.status_code == 403


def test_employee_update_rejects_invalid_birth_date_or_team(
    client,
    make_user,
    make_employee,
    auth_headers,
):
    """Verify employee updates return 400 for invalid date or team values."""
    admin = make_user(
        username="employee_update_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(personnel_number="P-350", name="Update Person")
    headers = auth_headers(admin["username"])

    invalid_date_response = client.put(
        f"/api/v1/employees/{employee_id}",
        headers=headers,
        json={"birth_date": "01-01-1990"},
    )
    invalid_team_response = client.put(
        f"/api/v1/employees/{employee_id}",
        headers=headers,
        json={"team": "team-a"},
    )

    assert invalid_date_response.status_code == 400
    assert invalid_team_response.status_code == 400


def test_shiftplan_generate_uses_local_fallback(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify shift plan generation works without OpenAI via local fallback."""
    admin = make_user(
        username="shiftplan_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_ids = [
        make_employee(personnel_number="P-401", name="Prod One", department="Produktion"),
        make_employee(personnel_number="P-402", name="Prod Two", department="Produktion"),
    ]
    machine_id = make_machine(name="Schicht Anlage", required_employees=1)
    _add_machine_qualifications(app, employee_ids, [machine_id])

    response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "KW Test",
            "start_date": "2026-05-01",
            "days": 2,
            "rhythm": "2-Schicht",
            "department": "Produktion",
        },
    )

    payload = response.get_json()
    assert response.status_code == 201
    assert payload["title"] == "KW Test"
    assert "Regelbasierter Generator" in payload["notes"]
    assert len(payload["entries"]) == 4


def test_shiftplan_generate_rejects_when_no_production_employees(
    client,
    make_user,
    auth_headers,
):
    """Verify shift plan generation reports missing production employees."""
    admin = make_user(
        username="shiftplan_empty_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={"start_date": "2026-05-01", "department": "Produktion"},
    )

    assert response.status_code == 400
    assert (
        "mitarbeiter" in response.get_json()["message"].lower()
        or "abteilung" in response.get_json()["message"].lower()
    )


def test_shiftplan_generate_rejects_invalid_date_and_days(
    client,
    make_user,
    make_employee,
    auth_headers,
):
    """Verify shift plan generation validates date and duration inputs."""
    admin = make_user(
        username="shiftplan_validation_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    make_employee(personnel_number="P-450", name="Prod Valid", department="Produktion")
    headers = auth_headers(admin["username"])

    invalid_date_response = client.post(
        "/api/v1/shiftplans/generate",
        headers=headers,
        json={"start_date": "01.05.2026"},
    )
    invalid_days_response = client.post(
        "/api/v1/shiftplans/generate",
        headers=headers,
        json={"start_date": "2026-05-01", "days": "seven"},
    )

    assert invalid_date_response.status_code == 400
    assert invalid_days_response.status_code == 400


def test_shiftplan_generate_uses_legacy_qualification_fallback(
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify missing qualification matrix no longer creates empty plans."""
    admin = make_user(
        username="shiftplan_warning_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    make_employee(
        personnel_number="P-470",
        name="Prod Warn",
        department="Produktion",
        qualifications="",
        favorite_machine="",
    )
    make_machine(name="Warn Anlage 1", required_employees=1)
    make_machine(name="Warn Anlage 2", required_employees=1)

    response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Warnplan",
            "start_date": "2026-05-01",
            "days": 1,
            "rhythm": "2-Schicht",
            "department": "Produktion",
        },
    )

    payload = response.get_json()
    warning_types = {warning["type"] for warning in payload["warnings"]}
    assert response.status_code == 201
    assert warning_types == {"coverage"}
    assert payload["entries"]


def test_shiftplan_generate_rejects_empty_work_plan_without_persisting(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify true undercoverage returns an error instead of saving an empty plan."""
    admin = make_user(
        username="shiftplan_empty_guard_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-471",
        name="Unavailable Worker",
        department="Produktion",
    )
    make_machine(name="Unavailable Anlage", required_employees=1)
    with app.app_context():
        plan_count_before = ShiftPlan.query.count()

    response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Leerer Plan",
            "start_date": "2026-05-04",
            "days": 1,
            "shift_model_key": "one_shift",
            "department": "Produktion",
            "vacations": [
                {
                    "employee_id": employee_id,
                    "date": "2026-05-04",
                    "notes": "Abwesend",
                }
            ],
        },
    )

    payload = response.get_json()
    with app.app_context():
        plan_count_after = ShiftPlan.query.count()
    assert response.status_code == 422
    assert "Kein Plan erzeugt" in payload["message"]
    assert {warning["type"] for warning in payload["warnings"]} == {"coverage"}
    assert plan_count_after == plan_count_before


def test_employee_machine_qualification_matrix_and_update(
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify structured employee-machine qualifications can be listed and replaced."""
    admin = make_user(
        username="qualification_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-480",
        name="Qualified Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Qualification Anlage", required_employees=1)
    headers = auth_headers(admin["username"])

    update_response = client.put(
        f"/api/v1/employees/{employee_id}/qualifications",
        headers=headers,
        json={
            "qualifications": [
                {
                    "machine_id": machine_id,
                    "level": "expert",
                    "valid_until": "2026-12-31",
                    "notes": "Freigegeben durch Schichtleitung",
                }
            ]
        },
    )
    matrix_response = client.get("/api/v1/employees/qualifications", headers=headers)

    assert update_response.status_code == 200
    assert update_response.get_json()["qualifications"][0]["level"] == "expert"
    assert matrix_response.status_code == 200
    assert matrix_response.get_json()["qualifications"][0]["machine_id"] == machine_id


def test_shiftplan_conflicts_detect_missing_qualification_and_vacation(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify conflict endpoint reports vacation and qualification conflicts."""
    admin = make_user(
        username="shiftplan_conflict_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-490",
        name="Conflict Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Conflict Anlage", required_employees=1)
    with app.app_context():
        user = User.query.filter_by(username=admin["username"]).one()
        plan = ShiftPlan(
            title="Konfliktplan",
            start_date=date(2026, 6, 1),
            days=1,
            rhythm="2-Schicht",
            department="Produktion",
            created_by=user.id,
        )
        db.session.add(plan)
        db.session.flush()
        db.session.add(
            ShiftPlanEntry(
                plan_id=plan.id,
                employee_id=employee_id,
                machine_id=machine_id,
                work_date=date(2026, 6, 1),
                shift="Frueh",
                start_time="06:00",
                end_time="14:00",
            )
        )
        db.session.add(
            VacationRequest(
                employee_id=employee_id,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
                days_used=1,
                status="approved",
                requested_by=user.id,
                approved_by=user.id,
            )
        )
        db.session.commit()
        plan_id = plan.id

    response = client.get(
        f"/api/v1/shiftplans/{plan_id}/conflicts",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    conflict_types = {conflict["type"] for conflict in payload["conflicts"]}
    assert response.status_code == 200
    assert "vacation_conflict" in conflict_types
    assert "missing_qualification" in conflict_types


def test_shiftplan_conflicts_ignore_pending_vacation_and_valid_qualification(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify pending vacations do not block and valid qualifications prevent conflicts."""
    admin = make_user(
        username="shiftplan_clean_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-491",
        name="Clean Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Clean Anlage", required_employees=1)
    with app.app_context():
        user = User.query.filter_by(username=admin["username"]).one()
        plan = ShiftPlan(
            title="Sauberer Plan",
            start_date=date(2026, 6, 2),
            days=1,
            rhythm="2-Schicht",
            department="Produktion",
            created_by=user.id,
        )
        db.session.add(plan)
        db.session.flush()
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.add(
            ShiftPlanEntry(
                plan_id=plan.id,
                employee_id=employee_id,
                machine_id=machine_id,
                work_date=date(2026, 6, 2),
                shift="Frueh",
                start_time="06:00",
                end_time="14:00",
            )
        )
        db.session.add(
            VacationRequest(
                employee_id=employee_id,
                start_date=date(2026, 6, 2),
                end_date=date(2026, 6, 2),
                days_used=1,
                status="pending",
                requested_by=user.id,
            )
        )
        db.session.commit()
        plan_id = plan.id

    response = client.get(
        f"/api/v1/shiftplans/{plan_id}/conflicts",
        headers=auth_headers(admin["username"]),
    )

    conflict_types = {conflict["type"] for conflict in response.get_json()["data"]["conflicts"]}
    assert response.status_code == 200
    assert "vacation_conflict" not in conflict_types
    assert "missing_qualification" not in conflict_types


def test_shiftplan_move_to_occupied_slot_does_not_swap(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify drag-to-occupied-slot moves the source without swapping target entry."""
    admin = make_user(
        username="shiftplan_move_no_swap_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_one_id = make_employee(
        personnel_number="P-495-A",
        name="Move Person One",
        department="Produktion",
    )
    employee_two_id = make_employee(
        personnel_number="P-495-B",
        name="Move Person Two",
        department="Produktion",
    )
    machine_id = make_machine(name="Move Anlage", required_employees=2)
    _add_machine_qualifications(app, [employee_one_id, employee_two_id], [machine_id])
    with app.app_context():
        user = User.query.filter_by(username=admin["username"]).one()
        plan = ShiftPlan(
            title="Move Plan",
            start_date=date(2026, 6, 1),
            days=2,
            rhythm="one_shift",
            department="Produktion",
            created_by=user.id,
        )
        db.session.add(plan)
        db.session.flush()
        source = ShiftPlanEntry(
            plan_id=plan.id,
            employee_id=employee_one_id,
            machine_id=machine_id,
            work_date=date(2026, 6, 1),
            shift="Frueh",
            start_time="06:00",
            end_time="14:00",
        )
        target = ShiftPlanEntry(
            plan_id=plan.id,
            employee_id=employee_two_id,
            machine_id=machine_id,
            work_date=date(2026, 6, 2),
            shift="Frueh",
            start_time="06:00",
            end_time="14:00",
        )
        db.session.add_all([source, target])
        db.session.commit()
        source_id = source.id
        target_id = target.id

    response = client.patch(
        f"/api/v1/shiftplans/entries/{source_id}/move",
        headers=auth_headers(admin["username"]),
        json={"target_entry_id": target_id},
    )

    with app.app_context():
        source = db.session.get(ShiftPlanEntry, source_id)
        target = db.session.get(ShiftPlanEntry, target_id)
        target_day_count = ShiftPlanEntry.query.filter_by(
            plan_id=source.plan_id,
            machine_id=machine_id,
            work_date=date(2026, 6, 2),
            shift="Frueh",
        ).count()
    assert response.status_code == 200, response.get_json()
    assert source.employee_id == employee_one_id
    assert source.work_date == date(2026, 6, 2)
    assert target.employee_id == employee_two_id
    assert target.work_date == date(2026, 6, 2)
    assert target_day_count == 2


def test_shiftplan_validate_endpoint_and_xlsx_export(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify ad-hoc validation and XLSX export are available."""
    admin = make_user(
        username="shiftplan_export_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-492",
        name="Export Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Export Anlage", required_employees=1)
    _add_machine_qualifications(app, [employee_id], [machine_id])
    headers = auth_headers(admin["username"])

    create_response = client.post(
        "/api/v1/shiftplans/generate",
        headers=headers,
        json={
            "title": "Exportplan",
            "start_date": "2026-06-03",
            "days": 1,
            "rhythm": "2-Schicht",
            "department": "Produktion",
        },
    )
    plan_id = create_response.get_json()["id"]
    validate_response = client.post(
        "/api/v1/shiftplans/validate",
        headers=headers,
        json={
            "entries": [
                {
                    "employee_id": employee_id,
                    "work_date": "2026-06-03",
                    "shift": "Frueh",
                    "start_time": "06:00",
                    "end_time": "14:00",
                },
                {
                    "employee_id": employee_id,
                    "work_date": "2026-06-03",
                    "shift": "Spaet",
                    "start_time": "14:00",
                    "end_time": "22:00",
                },
            ]
        },
    )
    export_response = client.get(
        f"/api/v1/shiftplans/{plan_id}/export.xlsx",
        headers=headers,
    )

    assert validate_response.status_code == 200
    assert any(
        conflict["type"] == "duplicate_assignment"
        for conflict in validate_response.get_json()["data"]["conflicts"]
    )
    assert export_response.status_code == 200
    assert export_response.mimetype.endswith("spreadsheetml.sheet")
    with ZipFile(BytesIO(export_response.data)) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        assert "xl/worksheets/sheet2.xml" in workbook.namelist()


def test_shiftplan_publish_creates_in_app_notification(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify publishing a plan creates user-facing in-app notifications."""
    admin = make_user(
        username="shiftplan_notify_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    worker = make_user(
        username="shiftplan_notify_worker",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    employee_id = make_employee(
        personnel_number="P-493",
        name="Notify Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Notify Anlage", required_employees=1)
    _add_machine_qualifications(app, [employee_id], [machine_id])
    with app.app_context():
        stored_worker = db.session.get(User, worker["id"])
        stored_worker.employee_id = employee_id
        db.session.commit()

    create_response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Benachrichtigungsplan",
            "start_date": "2026-06-04",
            "days": 1,
            "rhythm": "2-Schicht",
            "department": "Produktion",
        },
    )
    plan_id = create_response.get_json()["id"]
    publish_response = client.patch(
        f"/api/v1/shiftplans/{plan_id}/publish",
        headers=auth_headers(admin["username"]),
    )
    notification_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(worker["username"]),
    )
    read_response = client.patch(
        "/api/v1/notifications/read-all",
        headers=auth_headers(worker["username"]),
    )

    assert publish_response.status_code == 200
    assert notification_response.status_code == 200
    assert notification_response.get_json()["data"]["unread_count"] >= 1
    assert read_response.status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(recipient_user_id=worker["id"]).count() >= 1


def test_admin_user_can_link_employee(
    client,
    app,
    make_user,
    make_employee,
    auth_headers,
):
    """Verify user payloads expose the linked employee for cockpit calendars."""
    admin = make_user(
        username="link_employee_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="link_employee_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    employee_id = make_employee(
        personnel_number="P-510",
        name="Kalender Person",
        department="Produktion",
    )

    response = client.put(
        f"/api/v1/admin/users/{user['id']}",
        headers=auth_headers(admin["username"]),
        json={"employee_id": employee_id},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["employee_id"] == employee_id
    assert payload["employee"]["name"] == "Kalender Person"

    with app.app_context():
        stored_user = db.session.get(User, user["id"])
        assert stored_user.employee_id == employee_id


def test_shiftplan_generate_saves_vacation_and_skips_worker(
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify vacation payloads are saved and not planned as work shifts."""
    admin = make_user(
        username="shiftplan_vacation_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-520",
        name="Vacation Person",
        department="Produktion",
    )
    make_machine(name="Vacation Anlage", required_employees=1)

    response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Urlaubsplan",
            "start_date": "2026-05-01",
            "days": 2,
            "rhythm": "2-Schicht",
            "department": "Produktion",
            "vacations": [
                {
                    "employee_id": employee_id,
                    "date": "2026-05-01",
                    "notes": "Erholungsurlaub",
                }
            ],
        },
    )

    payload = response.get_json()
    vacation_entries = [entry for entry in payload["entries"] if entry["work_date"] == "2026-05-01"]
    assert response.status_code == 201
    assert [entry["shift"] for entry in vacation_entries] == ["Urlaub"]
    assert vacation_entries[0]["notes"] == "Erholungsurlaub"


def test_shiftplan_calendar_returns_own_calendar_and_free_days(
    client,
    app,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify cockpit calendar returns linked employee entries and free days."""
    admin = make_user(
        username="calendar_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="calendar_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    employee_id = make_employee(
        personnel_number="P-530",
        name="Calendar Person",
        department="Produktion",
    )
    make_employee(
        personnel_number="P-531",
        name="Calendar Cover",
        department="Produktion",
    )
    make_machine(name="Calendar Anlage", required_employees=1)
    with app.app_context():
        stored_user = db.session.get(User, user["id"])
        stored_user.employee_id = employee_id
        db.session.commit()

    client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Kalenderplan",
            "start_date": "2026-05-01",
            "days": 1,
            "rhythm": "2-Schicht",
            "department": "Produktion",
            "vacations": [
                {
                    "employee_id": employee_id,
                    "date": "2026-05-01",
                    "notes": "Urlaub",
                }
            ],
        },
    )

    response = client.get(
        "/api/v1/shiftplans/calendar?start_date=2026-05-01&days=2",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    shifts = [entry["shift"] for entry in payload["entries"]]
    assert response.status_code == 200
    assert payload["employee"]["name"] == "Calendar Person"
    assert shifts == ["Urlaub", "Frei"]
    assert payload["entries"][0]["color"] == "amber"
    assert payload["entries"][1]["color"] == "violet"


def test_shiftplan_calendar_admin_can_filter_employee(
    client,
    make_user,
    make_employee,
    auth_headers,
):
    """Verify admins can request a selected employee calendar."""
    admin = make_user(
        username="calendar_filter_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-540",
        name="Filter Person",
        department="Produktion",
    )

    response = client.get(
        f"/api/v1/shiftplans/calendar?employee_id={employee_id}&start_date=2026-05-01&days=1",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["employee"]["name"] == "Filter Person"
    assert payload["entries"][0]["shift"] == "Frei"


def test_shiftplan_delete_requires_master_admin(
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify only MASTER_ADMIN can delete shift plans."""
    admin = make_user(username="sp_del_admin", role=Role.MASTER_ADMIN, department_name=None)
    non_admin = make_user(
        username="sp_del_nonadmin",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_employee(personnel_number="P-601", name="Prod Del", department="Produktion")
    make_machine(name="Del Anlage", required_employees=1)

    create_response = client.post(
        "/api/v1/shiftplans/generate",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Delete Test",
            "start_date": "2026-06-01",
            "days": 1,
            "rhythm": "2-Schicht",
            "department": "Produktion",
        },
    )
    assert create_response.status_code == 201
    plan_id = create_response.get_json()["id"]

    forbidden = client.delete(
        f"/api/v1/shiftplans/{plan_id}",
        headers=auth_headers(non_admin["username"]),
    )
    assert forbidden.status_code == 403

    ok = client.delete(
        f"/api/v1/shiftplans/{plan_id}",
        headers=auth_headers(admin["username"]),
    )
    assert ok.status_code == 204
