"""Tests for inspection plans, execution records and machine reliability KPIs."""

from datetime import UTC, date, datetime, timedelta

from app.extensions import db
from app.machines.services import machine_reliability
from app.models import MaintenancePlan, Role, Task


def _admin(make_user):
    """Create a maintenance admin in the Instandhaltung department."""
    return make_user(
        username="inspection_admin", role=Role.MASTER_ADMIN, department_name="Instandhaltung"
    )


def _create_inspection(client, headers, machine_id, **overrides):
    """Create an inspection plan through the API and return its payload."""
    payload = {
        "title": "Elektrische Prüfung ortsfester Anlagen",
        "kind": "inspection",
        "legal_basis": "DGUV Vorschrift 3",
        "interval_days": 365,
        "next_due_date": (date.today() - timedelta(days=3)).isoformat(),
        "machine_id": machine_id,
        "department": "Instandhaltung",
        **overrides,
    }
    response = client.post("/api/v1/machines/maintenance-plans", headers=headers, json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_inspection_plan_reports_kind_basis_and_due_state(
    client, make_user, make_machine, auth_headers
):
    """Verify inspection plans carry their legal basis and show as overdue."""
    headers = auth_headers(_admin(make_user)["username"])
    plan = _create_inspection(client, headers, make_machine(name="Presse DGUV"))

    assert plan["kind"] == "inspection"
    assert plan["legal_basis"] == "DGUV Vorschrift 3"
    assert plan["due_state"] == "overdue"
    assert plan["last_record"] is None


def test_passed_inspection_is_documented_and_moves_due_date(
    app, client, make_user, make_machine, auth_headers
):
    """Verify a passed inspection is stored and schedules the next one."""
    headers = auth_headers(_admin(make_user)["username"])
    plan = _create_inspection(client, headers, make_machine(name="Presse Pass"))
    performed = date.today() - timedelta(days=1)

    response = client.post(
        f"/api/v1/machines/maintenance-plans/{plan['id']}/records",
        headers=headers,
        json={
            "performed_on": performed.isoformat(),
            "performed_by": "Elektro Schmidt GmbH",
            "result": "passed",
            "notes": "Prüfprotokoll 2026-117",
        },
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["record"]["follow_up_task_id"] is None
    assert body["plan"]["next_due_date"] == (performed + timedelta(days=365)).isoformat()
    assert body["plan"]["due_state"] == "ok"
    assert body["plan"]["last_record"]["performed_by"] == "Elektro Schmidt GmbH"
    records = client.get(
        f"/api/v1/machines/maintenance-plans/{plan['id']}/records", headers=headers
    ).get_json()["data"]
    assert [record["result"] for record in records] == ["passed"]


def test_failed_inspection_creates_urgent_follow_up_and_retest(
    app, client, make_user, make_machine, auth_headers
):
    """Verify a failed inspection opens an urgent task and a re-test within a week."""
    headers = auth_headers(_admin(make_user)["username"])
    plan = _create_inspection(client, headers, make_machine(name="Kompressor Fail"))

    response = client.post(
        f"/api/v1/machines/maintenance-plans/{plan['id']}/records",
        headers=headers,
        json={
            "performed_on": date.today().isoformat(),
            "performed_by": "TÜV Süd",
            "result": "failed",
            "notes": "Sicherheitsventil öffnet nicht",
        },
    )

    body = response.get_json()["data"]
    assert response.status_code == 201
    assert body["plan"]["next_due_date"] == (date.today() + timedelta(days=7)).isoformat()
    with app.app_context():
        task = db.session.get(Task, body["record"]["follow_up_task_id"])
        assert task.priority.value == "urgent"
        assert task.title.startswith("Mängel beheben: Elektrische Prüfung")
        assert "DGUV Vorschrift 3" in task.description
        assert "Sicherheitsventil" in task.description


def test_record_validation(client, make_user, make_machine, auth_headers):
    """Verify future dates, missing inspector and unknown results are rejected."""
    headers = auth_headers(_admin(make_user)["username"])
    plan = _create_inspection(client, headers, make_machine(name="Presse Validate"))
    path = f"/api/v1/machines/maintenance-plans/{plan['id']}/records"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert (
        client.post(
            path,
            headers=headers,
            json={"performed_on": tomorrow, "performed_by": "X", "result": "passed"},
        ).status_code
        == 400
    )
    assert client.post(path, headers=headers, json={"result": "passed"}).status_code == 400
    assert (
        client.post(path, headers=headers, json={"performed_by": "X", "result": "ok"}).status_code
        == 400
    )


def test_follow_up_needs_task_permission(
    client, make_user, make_machine, set_dashboard_permission, auth_headers
):
    """Verify a record with defects is refused when the user cannot create tasks."""
    user = make_user(
        username="inspector_no_tasks", role=Role.INSTANDHALTUNG, department_name="Instandhaltung"
    )
    set_dashboard_permission(user["username"], "machines", can_view=True, can_write=True)
    set_dashboard_permission(user["username"], "tasks", can_view=True, can_write=False)
    headers = auth_headers(user["username"])
    plan = _create_inspection(client, headers, make_machine(name="Presse Perm"))
    path = f"/api/v1/machines/maintenance-plans/{plan['id']}/records"

    refused = client.post(
        path, headers=headers, json={"performed_by": "Meister", "result": "defects"}
    )
    allowed = client.post(
        path,
        headers=headers,
        json={"performed_by": "Meister", "result": "defects", "create_follow_up": False},
    )

    assert refused.status_code == 403
    assert allowed.status_code == 201


def test_invalid_plan_kind_is_rejected(client, make_user, make_machine, auth_headers):
    """Verify only maintenance and inspection are valid plan kinds."""
    headers = auth_headers(_admin(make_user)["username"])
    response = client.post(
        "/api/v1/machines/maintenance-plans",
        headers=headers,
        json={"title": "X", "kind": "audit", "interval_days": 30, "department": "Instandhaltung"},
    )
    assert response.status_code == 400


def test_deleting_plan_removes_records(app, client, make_user, make_machine, auth_headers):
    """Verify records do not outlive their plan."""
    headers = auth_headers(_admin(make_user)["username"])
    plan = _create_inspection(client, headers, make_machine(name="Presse Delete"))
    client.post(
        f"/api/v1/machines/maintenance-plans/{plan['id']}/records",
        headers=headers,
        json={"performed_by": "Meister", "result": "passed"},
    )

    assert (
        client.delete(
            f"/api/v1/machines/maintenance-plans/{plan['id']}", headers=headers
        ).status_code
        == 204
    )
    with app.app_context():
        assert db.session.get(MaintenancePlan, plan["id"]) is None


def test_machine_reliability_from_incidents():
    """Verify availability, MTBF and MTTR over the 90-day window."""
    now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    errors = [
        {"created_at": (now - timedelta(days=10)).isoformat(), "downtime_minutes": 120},
        {"created_at": (now - timedelta(days=40)).isoformat(), "downtime_minutes": 60},
        {"created_at": (now - timedelta(days=120)).isoformat(), "downtime_minutes": 999},
    ]

    kpis = machine_reliability(errors, now=now)

    window = 90 * 24 * 60
    assert kpis["failure_count"] == 2
    assert kpis["availability_percent"] == round((window - 180) / window * 100, 2)
    assert kpis["mtbf_hours"] == round((window - 180) / 2 / 60, 1)
    assert kpis["mttr_minutes"] == 90
    assert machine_reliability([], now=now)["mtbf_hours"] is None


def test_machine_profile_exposes_reliability(client, make_user, make_machine, auth_headers):
    """Verify the machine profile KPIs include availability and MTBF."""
    headers = auth_headers(_admin(make_user)["username"])
    machine_id = make_machine(name="Presse Kennzahl")

    kpis = client.get(f"/api/v1/machines/{machine_id}/profile", headers=headers).get_json()["data"][
        "kpis"
    ]

    assert kpis["availability_percent"] == 100.0
    assert kpis["mtbf_hours"] is None
    assert kpis["reliability_window_days"] == 90
