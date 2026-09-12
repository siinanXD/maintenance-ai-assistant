"""Tests for shift model service foundations."""

from datetime import date, timedelta

from app.extensions import db
from app.models import (
    Employee,
    EmployeeMachineQualification,
    Machine,
    Role,
    ShiftPlan,
    ShiftPlanCoverageSlot,
)
from app.shiftplans.generator import build_local_shift_entries
from app.shiftplans.rules import (
    validate_max_daily_hours,
    validate_rest_time,
    validate_vacation_conflict,
)
from app.shiftplans.scoring import is_backward_rotation, is_forward_rotation, score_candidate
from app.shiftplans.templates import (
    get_shift_model_template,
    list_shift_model_templates,
    resolve_shift_model_template,
)


def test_shift_model_catalog_contains_required_templates():
    """Verify the first supported German shift model templates are registered."""
    keys = {template.key for template in list_shift_model_templates()}

    assert {
        "one_shift",
        "two_shift",
        "three_shift",
        "teilkonti",
        "vollkonti_4",
        "vollkonti_5",
    }.issubset(keys)


def test_shift_model_resolution_supports_legacy_rhythm_aliases():
    """Verify legacy rhythm labels resolve to stable template keys."""
    assert resolve_shift_model_template("2-Schicht").key == "two_shift"
    assert resolve_shift_model_template("3-Schicht Rhythmus").key == "three_shift"
    assert resolve_shift_model_template("Teilkonti").key == "teilkonti"
    assert resolve_shift_model_template("one_shift_day").key == "one_shift"
    assert resolve_shift_model_template("Vollkonti 5-Schicht").key == "vollkonti_5"


def test_shift_model_active_days_match_model_type():
    """Verify weekday coverage differs between two-shift, Teilkonti and Vollkonti."""
    two_shift = get_shift_model_template("two_shift")
    teilkonti = get_shift_model_template("teilkonti")
    vollkonti = get_shift_model_template("vollkonti_4")
    saturday = date(2026, 5, 2)
    sunday = date(2026, 5, 3)

    assert not two_shift.is_active_on(saturday)
    assert teilkonti.is_active_on(saturday)
    assert not teilkonti.is_active_on(sunday)
    assert vollkonti.is_active_on(sunday)


def test_local_shift_generator_uses_template_active_days(
    app,
    make_employee,
    make_machine,
):
    """Verify direct template generation respects model-specific active days."""
    make_employee(personnel_number="P-SM-1", name="Template One", department="Produktion")
    make_employee(personnel_number="P-SM-2", name="Template Two", department="Produktion")
    machine_id = make_machine(name="Template Anlage", required_employees=1)

    with app.app_context():
        employees = Employee.query.order_by(Employee.id.asc()).all()
        machines = Machine.query.order_by(Machine.id.asc()).all()
        for employee in employees:
            db.session.add(
                EmployeeMachineQualification(
                    employee_id=employee.id,
                    machine_id=machine_id,
                    level="trained",
                )
            )
        db.session.commit()
        entries, warnings = build_local_shift_entries(
            date(2026, 5, 1),
            3,
            "two_shift",
            employees,
            machines,
        )

    assert warnings == []
    assert {entry["work_date"] for entry in entries} == {"2026-05-01"}
    assert {entry["shift"] for entry in entries} == {"Frueh", "Spaet"}


def test_vollkonti_local_generation_includes_weekend(
    app,
    make_employee,
    make_machine,
):
    """Verify 24/7 templates produce weekend entries."""
    for index in range(1, 4):
        make_employee(
            personnel_number=f"P-SM-VK-{index}",
            name=f"Vollkonti {index}",
            department="Produktion",
        )
    machine_id = make_machine(name="Vollkonti Anlage", required_employees=1)

    with app.app_context():
        employees = Employee.query.order_by(Employee.id.asc()).all()
        machines = Machine.query.order_by(Machine.id.asc()).all()
        for employee in employees:
            db.session.add(
                EmployeeMachineQualification(
                    employee_id=employee.id,
                    machine_id=machine_id,
                    level="trained",
                )
            )
        db.session.commit()
        entries, warnings = build_local_shift_entries(
            date(2026, 5, 2),
            2,
            "vollkonti_4",
            employees,
            machines,
        )

    assert warnings == []
    assert {entry["work_date"] for entry in entries} == {"2026-05-02", "2026-05-03"}
    assert {entry["shift"] for entry in entries} == {"Frueh", "Spaet", "Nacht"}
    assert all(entry["start_time"] and entry["end_time"] for entry in entries)


def test_shiftplan_models_endpoint_returns_template_catalog(
    client,
    make_user,
    auth_headers,
):
    """Verify the backend exposes shift model metadata for frontend selection."""
    admin = make_user(
        username="shift_model_api_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.get(
        "/api/v1/shiftplans/models",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert {item["key"] for item in payload} >= {"one_shift", "vollkonti_5"}
    assert {
        "key",
        "display_name",
        "description",
        "shifts",
        "shift_times",
        "team_count",
        "weekend_operation",
        "rotation_direction",
        "weekly_hours_target",
        "max_consecutive_nights",
        "recommended_rest_hours",
    }.issubset(payload[0])


def test_shiftplan_generate_accepts_shift_model_key(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify generation accepts canonical shift_model_key values."""
    admin = make_user(
        username="shift_model_generate_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-GEN-1",
        name="Generate Model One",
        department="Produktion",
    )
    machine_id = make_machine(name="Generate Model Anlage", required_employees=1)
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-05-04",
            "days": 1,
            "shift_model_key": "one_shift",
            "preferences": {"text": "Tagschicht bevorzugt"},
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 201, payload
    assert payload["rhythm"] == "one_shift"
    assert {entry["shift"] for entry in payload["entries"]} == {"Frueh"}


def test_shiftplan_preview_does_not_persist_plan(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify dry-run preview returns a plan shape without saving it."""
    admin = make_user(
        username="shift_model_preview_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-PREV-1",
        name="Preview Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Preview Anlage", required_employees=1)
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()
        plan_count_before = ShiftPlan.query.count()

    response = client.post(
        "/api/v1/shiftplans/preview",
        json={
            "department": "Produktion",
            "start_date": "2026-06-01",
            "days": 1,
            "shift_model_key": "one_shift",
            "machine_ids": [machine_id],
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    with app.app_context():
        plan_count_after = ShiftPlan.query.count()
    assert response.status_code == 200
    assert payload["is_preview"] is True
    assert payload["entries"]
    assert plan_count_after == plan_count_before


def test_shiftplan_generate_filters_selected_machines(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify machine_ids restrict generation to selected machines."""
    admin = make_user(
        username="shift_model_machine_filter_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-MACH-1",
        name="Machine Filter Person",
        department="Produktion",
    )
    selected_machine_id = make_machine(name="Selected Anlage", required_employees=1)
    other_machine_id = make_machine(name="Skipped Anlage", required_employees=1)
    with app.app_context():
        for machine_id in (selected_machine_id, other_machine_id):
            db.session.add(
                EmployeeMachineQualification(
                    employee_id=employee_id,
                    machine_id=machine_id,
                    level="trained",
                )
            )
        db.session.commit()

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-06-01",
            "days": 1,
            "shift_model_key": "one_shift",
            "machine_ids": [selected_machine_id],
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 201, payload
    assert {entry["machine"]["id"] for entry in payload["entries"]} == {selected_machine_id}
    assert other_machine_id not in {slot["machine_id"] for slot in payload["unassigned_slots"]}


def test_shiftplan_generate_rejects_invalid_machine_ids(
    client,
    make_user,
    make_employee,
    auth_headers,
):
    """Verify invalid machine selection returns a clear client error."""
    admin = make_user(
        username="shift_model_bad_machine_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    make_employee(
        personnel_number="P-SM-BADMACH-1",
        name="Bad Machine Person",
        department="Produktion",
    )

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-06-01",
            "days": 1,
            "shift_model_key": "one_shift",
            "machine_ids": [99999],
        },
        headers=auth_headers(admin["username"]),
    )

    assert response.status_code == 400
    assert "Unbekannte Maschine" in response.get_json()["message"]


def test_shiftplan_undercoverage_is_persisted_as_visible_slots(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify undercoverage survives plan reloads as unassigned slots."""
    admin = make_user(
        username="shift_model_undercoverage_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-UC-1",
        name="Undercoverage Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Undercoverage Anlage", required_employees=2)
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-06-01",
            "days": 1,
            "shift_model_key": "one_shift",
            "machine_ids": [machine_id],
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    plan_id = payload["id"]
    with app.app_context():
        persisted_count = ShiftPlanCoverageSlot.query.filter_by(plan_id=plan_id).count()
    reload_response = client.get(
        "/api/v1/shiftplans",
        headers=auth_headers(admin["username"]),
    )
    reloaded_plan = next(plan for plan in reload_response.get_json() if plan["id"] == plan_id)
    assert response.status_code == 201, payload
    assert payload["unassigned_slots"]
    assert persisted_count == len(payload["unassigned_slots"])
    assert reloaded_plan["unassigned_slots"]


def test_shiftplan_generate_updates_employee_rotation_state(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify generation stores last/current/next shift state on employees."""
    admin = make_user(
        username="shift_model_rotation_state_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-ROTSTATE-1",
        name="Rotation State Person",
        department="Produktion",
    )
    machine_id = make_machine(name="Rotation State Anlage", required_employees=1)
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()

    # one_shift has no weekend operation, so anchor the plan on the next Monday
    # to keep the test deterministic regardless of the weekday it runs on.
    start_date = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)
    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": start_date.isoformat(),
            "days": 2,
            "shift_model_key": "one_shift",
            "machine_ids": [machine_id],
        },
        headers=auth_headers(admin["username"]),
    )

    with app.app_context():
        employee = db.session.get(Employee, employee_id)
        current_shift = employee.current_shift
        next_shift = employee.next_shift
        updated_at = employee.rotation_state_updated_at
    assert response.status_code == 201, response.get_json()
    assert current_shift == "Frueh"
    assert next_shift == "Frueh"
    assert updated_at is not None


def test_shiftplan_generate_accepts_legacy_rhythm_field(
    app,
    client,
    make_user,
    make_employee,
    make_machine,
    auth_headers,
):
    """Verify legacy rhythm payloads still generate plans."""
    admin = make_user(
        username="shift_model_legacy_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    employee_id = make_employee(
        personnel_number="P-SM-LEG-1",
        name="Legacy Model One",
        department="Produktion",
    )
    machine_id = make_machine(name="Legacy Model Anlage", required_employees=1)
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-05-04",
            "days": 1,
            "rhythm": "1-Schicht",
            "preferences": "Tagschicht bevorzugt",
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 201, payload
    assert payload["rhythm"] == "1-Schicht"
    assert {entry["shift"] for entry in payload["entries"]} == {"Frueh"}


def test_shiftplan_generate_rejects_invalid_shift_model_key(
    client,
    make_user,
    auth_headers,
):
    """Verify invalid explicit model keys return a clear client error."""
    admin = make_user(
        username="shift_model_invalid_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-05-04",
            "days": 1,
            "shift_model_key": "unknown_model",
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert "Unbekanntes Schichtmodell" in payload["message"]


def test_shiftplan_generate_rejects_empty_shift_model_key(
    client,
    make_user,
    auth_headers,
):
    """Verify empty explicit model keys do not silently fall back to rhythm."""
    admin = make_user(
        username="shift_model_empty_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/shiftplans/generate",
        json={
            "department": "Produktion",
            "start_date": "2026-05-04",
            "days": 1,
            "shift_model_key": "",
            "rhythm": "1-Schicht",
        },
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert "shift_model_key darf nicht leer sein" in payload["message"]


def test_hard_rules_report_rest_daily_hours_and_vacation_conflicts():
    """Verify core hard-rule helpers reject invalid assignments."""
    candidate = {
        "employee_id": 1,
        "machine_id": None,
        "work_date": date(2026, 5, 2),
        "shift": "Frueh",
        "start_time": "06:00",
        "end_time": "18:30",
    }
    previous = {
        "employee_id": 1,
        "machine_id": None,
        "work_date": date(2026, 5, 1),
        "shift": "Nacht",
        "start_time": "22:00",
        "end_time": "06:00",
    }

    assert validate_max_daily_hours(candidate)
    assert validate_rest_time(candidate, [previous])
    assert validate_vacation_conflict(candidate, {(1, date(2026, 5, 2))})


def test_generator_uses_legacy_mode_when_qualification_matrix_is_empty(
    app,
    make_employee,
    make_machine,
):
    """Verify empty structured qualifications do not block legacy data."""
    employee_id = make_employee(
        personnel_number="P-SM-UQ",
        name="Legacy Qualified",
        department="Produktion",
    )
    make_machine(name="Qualification Required Anlage", required_employees=1)

    with app.app_context():
        employees = Employee.query.order_by(Employee.id.asc()).all()
        machines = Machine.query.order_by(Machine.id.asc()).all()
        entries, warnings = build_local_shift_entries(
            date(2026, 5, 4),
            1,
            "one_shift",
            employees,
            machines,
        )

    assert warnings == []
    assert [entry["employee_id"] for entry in entries] == [employee_id]


def test_generator_filters_missing_machine_qualification_when_matrix_exists(
    app,
    make_employee,
    make_machine,
):
    """Verify partial structured qualifications remain strict."""
    unqualified_id = make_employee(
        personnel_number="P-SM-UQ-STRICT",
        name="Unqualified",
        department="Produktion",
    )
    qualified_id = make_employee(
        personnel_number="P-SM-Q-STRICT",
        name="Qualified",
        department="Produktion",
    )
    machine_id = make_machine(name="Strict Qualification Anlage", required_employees=1)

    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=qualified_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.commit()
        employees = Employee.query.order_by(Employee.id.asc()).all()
        machines = Machine.query.order_by(Machine.id.asc()).all()
        entries, warnings = build_local_shift_entries(
            date(2026, 5, 4),
            1,
            "one_shift",
            employees,
            machines,
        )

    assert warnings == []
    assert [entry["employee_id"] for entry in entries] == [qualified_id]
    assert unqualified_id not in {entry["employee_id"] for entry in entries}


def test_forward_rotation_helpers_and_scoring_prefer_forward(
    app,
    make_employee,
):
    """Verify forward rotation receives a better score than backward rotation."""
    employee_id = make_employee(
        personnel_number="P-SM-ROT",
        name="Rotation Person",
        department="Produktion",
    )
    template = get_shift_model_template("three_shift")
    previous = [
        {
            "employee_id": employee_id,
            "machine_id": None,
            "work_date": date(2026, 5, 4),
            "shift": "Frueh",
            "start_time": "06:00",
            "end_time": "14:00",
        }
    ]

    with app.app_context():
        employee = db.session.get(Employee, employee_id)
        forward = score_candidate(
            employee,
            None,
            date(2026, 5, 5),
            "Spaet",
            previous,
            {},
            template,
        )
        backward = score_candidate(
            employee,
            None,
            date(2026, 5, 5),
            "Frueh",
            [
                {
                    **previous[0],
                    "shift": "Nacht",
                    "start_time": "22:00",
                    "end_time": "06:00",
                }
            ],
            {},
            template,
        )

    assert is_forward_rotation("Frueh", "Spaet")
    assert is_backward_rotation("Nacht", "Frueh")
    assert forward.total_score > backward.total_score
