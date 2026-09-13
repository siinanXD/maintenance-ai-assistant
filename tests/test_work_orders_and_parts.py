"""Tests for incident work orders, spare-part withdrawals and reorder suggestions."""

from app.extensions import db
from app.models import ErrorEntry, InventoryMaterial, InventoryMovement, Role


def _create_material(app, name, quantity, min_quantity=0, unit_cost=10.0, lead_time_days=0):
    """Create one inventory material and return its id."""
    with app.app_context():
        material = InventoryMaterial(
            name=name,
            unit_cost=unit_cost,
            quantity=quantity,
            min_quantity=min_quantity,
            lead_time_days=lead_time_days,
        )
        db.session.add(material)
        db.session.commit()
        return material.id


def test_work_order_from_incident_closes_incident_on_completion(
    app, client, make_user, make_error_entry, auth_headers
):
    """Verify a task raised for an incident links back and can close it when done."""
    tech = make_user(username="wo_tech", role=Role.INSTANDHALTUNG, department_name="Instandhaltung")
    error_id = make_error_entry(
        "Presse 5", "P5-7", "Ventil klemmt", department_name="Instandhaltung"
    )
    headers = auth_headers(tech["username"])

    created = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "P5-7 Ventil tauschen", "error_entry_id": error_id},
    )
    assert created.status_code == 201
    task = created.get_json()
    assert task["error_entry"]["error_code"] == "P5-7"

    listed = client.get("/api/v1/errors?limit=100", headers=headers).get_json()["data"]
    assert next(item for item in listed if item["id"] == error_id)["open_task_count"] == 1

    completed = client.post(
        f"/api/v1/tasks/{task['id']}/complete", headers=headers, json={"close_error_entry": True}
    )
    assert completed.status_code == 200
    with app.app_context():
        assert db.session.get(ErrorEntry, error_id).status == "closed"


def test_work_order_cannot_link_incident_of_other_department(
    client, make_user, make_error_entry, auth_headers
):
    """Verify incidents of another department are not linkable."""
    user = make_user(username="wo_prod", role=Role.PRODUKTION, department_name="Produktion")
    foreign_error = make_error_entry("Band 2", "B2-1", "Riss", department_name="Instandhaltung")

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers(user["username"]),
        json={"title": "Band pruefen", "error_entry_id": foreign_error},
    )

    assert response.status_code == 400


def test_closing_incident_without_permission_leaves_task_open(
    app, client, make_user, make_error_entry, set_dashboard_permission, auth_headers
):
    """Verify a refused incident close does not complete the task either."""
    user = make_user(username="wo_readonly", role=Role.PRODUKTION, department_name="Produktion")
    error_id = make_error_entry("Band 3", "B3-1", "Laeuft schief", department_name="Produktion")
    headers = auth_headers(user["username"])
    task_id = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Band ausrichten", "error_entry_id": error_id},
    ).get_json()["id"]
    set_dashboard_permission(user["username"], "errors", can_view=True, can_write=False)

    response = client.post(
        f"/api/v1/tasks/{task_id}/complete", headers=headers, json={"close_error_entry": True}
    )

    assert response.status_code == 403
    assert client.get(f"/api/v1/tasks/{task_id}", headers=headers).get_json()["status"] == "open"


def test_withdrawal_reduces_stock_and_is_listed_on_task(
    app, client, make_user, make_task, auth_headers
):
    """Verify parts taken for a work order leave stock and show up with their value."""
    tech = make_user(
        username="parts_tech", role=Role.INSTANDHALTUNG, department_name="Instandhaltung"
    )
    task_id = make_task("Lager wechseln", tech["username"], department_name="Instandhaltung")
    material_id = _create_material(app, "Rillenkugellager 6205", quantity=5, unit_cost=12.5)
    headers = auth_headers(tech["username"])

    withdrawn = client.post(
        f"/api/v1/tasks/{task_id}/materials",
        headers=headers,
        json={"material_id": material_id, "quantity": 2, "note": "Antriebsseite"},
    )
    assert withdrawn.status_code == 201
    assert withdrawn.get_json()["data"]["quantity_change"] == -2

    listed = client.get(f"/api/v1/tasks/{task_id}/materials", headers=headers).get_json()["data"]
    assert listed["total_value"] == 25.0
    assert listed["items"][0]["material_name"] == "Rillenkugellager 6205"
    with app.app_context():
        assert db.session.get(InventoryMaterial, material_id).quantity == 3


def test_withdrawal_never_goes_below_zero(app, client, make_user, make_task, auth_headers):
    """Verify stock shortages are refused with the available quantity."""
    tech = make_user(
        username="parts_short", role=Role.INSTANDHALTUNG, department_name="Instandhaltung"
    )
    task_id = make_task("Dichtung tauschen", tech["username"], department_name="Instandhaltung")
    material_id = _create_material(app, "O-Ring 40x3", quantity=1)

    response = client.post(
        f"/api/v1/tasks/{task_id}/materials",
        headers=auth_headers(tech["username"]),
        json={"material_id": material_id, "quantity": 3},
    )

    assert response.status_code == 409
    assert "Nur noch 1" in response.get_json()["message"]
    with app.app_context():
        assert db.session.get(InventoryMaterial, material_id).quantity == 1
        assert InventoryMovement.query.count() == 0


def test_withdrawal_requires_open_task(app, client, make_user, make_task, auth_headers):
    """Verify completed work orders do not accept new withdrawals."""
    from app.models import TaskStatus

    tech = make_user(
        username="parts_done", role=Role.INSTANDHALTUNG, department_name="Instandhaltung"
    )
    task_id = make_task(
        "Erledigt", tech["username"], department_name="Instandhaltung", status=TaskStatus.DONE
    )
    material_id = _create_material(app, "Keilriemen SPA", quantity=4)

    response = client.post(
        f"/api/v1/tasks/{task_id}/materials",
        headers=auth_headers(tech["username"]),
        json={"material_id": material_id, "quantity": 1},
    )

    assert response.status_code == 409


def test_goods_receipt_and_reorder_suggestion(app, client, make_user, make_task, auth_headers):
    """Verify receipts add stock and low materials get an order proposal."""
    admin = make_user(
        username="parts_admin", role=Role.MASTER_ADMIN, department_name="Instandhaltung"
    )
    headers = auth_headers(admin["username"])
    low_id = _create_material(
        app, "Filterpatrone", quantity=2, min_quantity=4, unit_cost=20.0, lead_time_days=30
    )
    _create_material(app, "Schraube M8", quantity=50, min_quantity=10)
    task_id = make_task("Filter wechseln", admin["username"], department_name="Instandhaltung")
    client.post(
        f"/api/v1/tasks/{task_id}/materials",
        headers=headers,
        json={"material_id": low_id, "quantity": 1},
    )

    suggestions = client.get("/api/v1/inventory/reorder", headers=headers).get_json()["data"]
    assert [item["material"]["name"] for item in suggestions["items"]] == ["Filterpatrone"]
    # refill to 2x minimum (8 - 1 in stock = 7) plus 30 days of 1/90 per day, rounded to 0
    assert suggestions["items"][0]["order_quantity"] == 7
    assert suggestions["total_value"] == 140.0

    receipt = client.post(
        f"/api/v1/inventory/{low_id}/receipts",
        headers=headers,
        json={"quantity": 10, "note": "LS 4711"},
    )
    assert receipt.status_code == 201
    assert receipt.get_json()["data"]["material"]["quantity"] == 11

    movements = client.get(f"/api/v1/inventory/{low_id}/movements", headers=headers).get_json()[
        "data"
    ]
    assert [movement["reason"] for movement in movements] == ["receipt", "withdrawal"]
    assert client.get("/api/v1/inventory/reorder", headers=headers).get_json()["data"]["count"] == 0


def test_receipt_requires_inventory_write(
    app, client, make_user, set_dashboard_permission, auth_headers
):
    """Verify only inventory writers can book goods receipts."""
    user = make_user(username="parts_viewer", role=Role.PRODUKTION)
    set_dashboard_permission(user["username"], "inventory", can_view=True, can_write=False)
    material_id = _create_material(app, "Sicherung 16A", quantity=3)

    response = client.post(
        f"/api/v1/inventory/{material_id}/receipts",
        headers=auth_headers(user["username"]),
        json={"quantity": 5},
    )

    assert response.status_code == 403
