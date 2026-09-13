"""Tests for machine and inventory workflows."""

from datetime import date, timedelta
from pathlib import Path

from app.extensions import db
from app.models import (
    Department,
    ErrorEntry,
    GeneratedDocument,
    KnowledgeDocument,
    Machine,
    MachineManual,
    MaintenancePlan,
    Priority,
    Role,
    ShiftHandover,
    Task,
)
from app.services.ai_service import AIServiceError

REPO_ROOT = Path(__file__).resolve().parents[1]


def inventory_react_source():
    """Return the combined React inventory island source."""
    source_paths = list((REPO_ROOT / "frontend" / "src" / "inventory").rglob("*.ts"))
    source_paths.extend((REPO_ROOT / "frontend" / "src" / "inventory").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def machine_react_source():
    """Return the combined React machine island source."""
    source_paths = list((REPO_ROOT / "frontend" / "src" / "machines").rglob("*.ts"))
    source_paths.extend((REPO_ROOT / "frontend" / "src" / "machines").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def test_machine_create_rejects_duplicates_and_invalid_staffing(
    client,
    make_user,
    auth_headers,
):
    """Verify machine creation validates names and employee requirements."""
    admin = make_user(
        username="asset_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])

    create_response = client.post(
        "/api/v1/machines",
        headers=headers,
        json={
            "name": "Anlage 4",
            "produced_item": "Gehaeuse",
            "required_employees": 2,
        },
    )
    duplicate_response = client.post(
        "/api/v1/machines",
        headers=headers,
        json={"name": "Anlage 4"},
    )
    normalized_duplicate_response = client.post(
        "/api/v1/machines",
        headers=headers,
        json={"name": "  anlage   4  "},
    )
    invalid_response = client.post(
        "/api/v1/machines",
        headers=headers,
        json={"name": "Anlage 5", "required_employees": 0},
    )

    assert create_response.status_code == 201
    assert create_response.get_json()["required_employees"] == 2
    assert duplicate_response.status_code == 409
    assert normalized_duplicate_response.status_code == 409
    assert invalid_response.status_code == 400


def test_machine_update_marks_knowledge_stale(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify machine metadata changes invalidate the RAG source."""
    admin = make_user(
        username="asset_stale_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])
    create_response = client.post(
        "/api/v1/machines",
        headers=headers,
        json={"name": "Anlage Stale", "produced_item": "Alt"},
    )
    machine_id = create_response.get_json()["id"]
    with app.app_context():
        document = KnowledgeDocument.query.filter_by(
            source_type="machine",
            source_id=machine_id,
        ).one()
        document.status = "indexed"
        db.session.commit()

    update_response = client.put(
        f"/api/v1/machines/{machine_id}",
        headers=headers,
        json={"name": "Anlage Stale Neu"},
    )

    assert update_response.status_code == 200
    with app.app_context():
        document = KnowledgeDocument.query.filter_by(
            source_type="machine",
            source_id=machine_id,
        ).one()
        assert document.title == "Anlage Stale Neu"
        assert document.status == "stale"


def test_maintenance_plan_creates_and_generates_due_task(
    client,
    make_user,
    make_machine,
    auth_headers,
):
    """Verify due recurring maintenance plans generate open tasks."""
    admin = make_user(
        username="maintenance_plan_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Presse 1")
    headers = auth_headers(admin["username"])
    today = date.today().isoformat()

    missing_response = client.post(
        "/api/v1/machines/maintenance-plans",
        headers=headers,
        json={"interval_days": 7, "next_due_date": today, "department": "Produktion"},
    )
    create_response = client.post(
        "/api/v1/machines/maintenance-plans",
        headers=headers,
        json={
            "title": "Hydraulik pruefen",
            "description": "Oelstand, Leckagen und Druck pruefen.",
            "interval_days": 7,
            "next_due_date": today,
            "priority": Priority.SOON.value,
            "machine_id": machine_id,
            "department": "Produktion",
        },
    )
    plan_id = create_response.get_json()["data"]["id"]
    list_response = client.get("/api/v1/machines/maintenance-plans", headers=headers)
    generate_response = client.post(
        "/api/v1/machines/maintenance-plans/generate-due",
        headers=headers,
    )

    generated = generate_response.get_json()["data"]
    with client.application.app_context():
        plan = db.session.get(MaintenancePlan, plan_id)
        task = db.session.get(Task, generated["items"][0]["task"]["id"])

    assert missing_response.status_code == 400
    assert create_response.status_code == 201
    assert create_response.get_json()["data"]["machine_id"] == machine_id
    assert list_response.status_code == 200
    assert [plan["id"] for plan in list_response.get_json()["data"]] == [plan_id]
    assert generate_response.status_code == 200
    assert generated["generated_count"] == 1
    assert task.title == "Wartung: Presse 1: Hydraulik pruefen"
    assert task.status.value == "open"
    assert plan.last_generated_task_id == task.id
    assert plan.next_due_date > date.today()


def test_maintenance_plan_update_delete_and_inactive_generation(
    client,
    make_user,
    auth_headers,
):
    """Verify maintenance plans can be updated, skipped when inactive, and deleted."""
    admin = make_user(
        username="maintenance_plan_update_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])
    create_response = client.post(
        "/api/v1/machines/maintenance-plans",
        headers=headers,
        json={
            "title": "Filter wechseln",
            "interval_days": 30,
            "next_due_date": date.today().isoformat(),
            "department": "Produktion",
        },
    )
    plan_id = create_response.get_json()["data"]["id"]

    update_response = client.put(
        f"/api/v1/machines/maintenance-plans/{plan_id}",
        headers=headers,
        json={"interval_days": 14, "is_active": False},
    )
    generate_response = client.post(
        "/api/v1/machines/maintenance-plans/generate-due",
        headers=headers,
    )
    delete_response = client.delete(
        f"/api/v1/machines/maintenance-plans/{plan_id}",
        headers=headers,
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["interval_days"] == 14
    assert update_response.get_json()["data"]["is_active"] is False
    assert generate_response.status_code == 200
    assert generate_response.get_json()["data"]["generated_count"] == 0
    assert delete_response.status_code == 204


def test_preventive_maintenance_recommendations_use_visible_history(
    app,
    client,
    make_user,
    make_machine,
    make_task,
    make_document,
    make_error_entry,
    set_dashboard_permission,
    auth_headers,
):
    """Verify preventive recommendations are built from visible machine history."""
    admin = make_user(
        username="preventive_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="preventive_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    set_dashboard_permission(user["username"], "documents", can_view=True)
    set_dashboard_permission(user["username"], "shiftplans", can_view=True)
    machine_id = make_machine(name="Anlage Preventive")
    task_id = make_task(
        "Anlage Preventive Hydraulik pruefen",
        creator_username=user["username"],
        department_name="Instandhaltung",
        description="Anlage Preventive zeigt wieder Druckverlust.",
    )
    make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Instandhaltung",
        machine="Anlage Preventive",
        relative_path="2026/05/preventive/report.html",
    )
    make_error_entry(
        "Anlage Preventive",
        "PV900",
        "Druckverlust",
        department_name="Instandhaltung",
        possible_causes="Hydraulikfilter zugesetzt",
        solution="Filter pruefen",
    )
    with app.app_context():
        department = Department.query.filter_by(name="Instandhaltung").one()
        plan = MaintenancePlan(
            title="Hydraulik Preventive",
            description="Regelmaessige Hydraulikpruefung",
            interval_days=30,
            next_due_date=date.today() + timedelta(days=7),
            priority=Priority.SOON,
            is_active=True,
            machine_id=machine_id,
            department=department,
            created_by=user["id"],
        )
        db.session.add(plan)
        db.session.add(
            ShiftHandover(
                department="Instandhaltung",
                area="Hydraulik",
                machine_id=machine_id,
                shift_date=date.today(),
                shift_type="Spaet",
                status="open",
                content="Anlage Preventive zeigte wieder Druckverlust.",
                open_tasks="Hydraulikdruck in naechster Schicht pruefen.",
                machine_notes="Filter und Ventilblock beobachten.",
                next_notes="Wartungsfenster vorbereiten.",
            )
        )
        db.session.commit()
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    response = client.get(
        "/api/v1/machines/maintenance-recommendations",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["items"][0]["machine"]["name"] == "Anlage Preventive"
    assert payload["items"][0]["source_counts"]["tasks"] == 1
    assert payload["items"][0]["source_counts"]["errors"] == 1
    assert payload["items"][0]["source_counts"]["maintenance_reports"] == 1
    assert payload["items"][0]["source_counts"]["maintenance_plans"] == 1
    assert payload["items"][0]["source_counts"]["shift_handovers"] == 1
    assert payload["items"][0]["source_counts"]["rag_sources"] >= 1
    assert payload["items"][0]["recommendation_type"] == "maintenance_recommendation_light"
    assert payload["items"][0]["confidence"] >= 50
    assert payload["items"][0]["confidence_level"] in {"medium", "high"}
    assert payload["items"][0]["confidence_uncertainty"] in {"low", "medium"}
    assert payload["items"][0]["confidence_reason"]
    next_steps = payload["items"][0]["next_steps"]
    next_step_types = {step["type"] for step in next_steps}
    assert next_steps
    assert "error_history_review" in next_step_types
    assert "maintenance_plan_review" in next_step_types
    assert all(step["title"] and step["detail"] for step in next_steps)
    assert all(step["urgency"] in {"high", "medium", "low"} for step in next_steps)
    evidence_summary = payload["items"][0]["evidence_summary"]
    assert evidence_summary["uses_only_visible_sources"] is True
    assert evidence_summary["predictive_claim"] is False
    assert evidence_summary["direct_source_count"] == 5
    assert evidence_summary["rag_source_count"] >= 1
    rag_evidence = evidence_summary["rag_sources"][0]
    assert rag_evidence["type"] == "knowledge"
    assert rag_evidence["source_type"]
    assert rag_evidence["source_id"]
    assert rag_evidence["chunk_id"]
    assert rag_evidence["title"]
    assert rag_evidence["module"] == "knowledge"
    assert rag_evidence["role_visibility"]
    assert rag_evidence["created_at"]
    assert "text" not in rag_evidence
    assert {
        "task",
        "error",
        "maintenance_report",
        "maintenance_plan",
        "shift_handover",
        "rag_source",
    } <= set(evidence_summary["source_types"])
    assert evidence_summary["recurring_issue_window_days"] == 30
    assert evidence_summary["latest_signal_at"]
    assert "Predictive-Maintenance" in payload["disclaimer"]
    assert "Ausfallwahrscheinlichkeit" in payload["items"][0]["limitations"][0]
    evidence_types = {item["type"] for item in payload["items"][0]["evidence"]}
    assert {
        "task",
        "error",
        "maintenance_report",
        "maintenance_plan",
        "shift_handover",
    } <= evidence_types


def test_preventive_maintenance_recommendations_do_not_leak_handovers_without_permission(
    app,
    client,
    make_user,
    make_machine,
    make_task,
    make_error_entry,
    set_dashboard_permission,
    auth_headers,
):
    """Verify maintenance recommendations do not count handovers without visibility."""
    user = make_user(
        username="preventive_no_handover_permission",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    set_dashboard_permission(user["username"], "errors", can_view=True)
    set_dashboard_permission(user["username"], "shiftplans", can_view=False)
    machine_id = make_machine(name="Anlage Preventive Hidden")
    make_task(
        "Anlage Preventive Hidden Hydraulik pruefen",
        creator_username=user["username"],
        department_name="Instandhaltung",
        description="Anlage Preventive Hidden zeigt wieder Druckverlust.",
    )
    make_error_entry(
        "Anlage Preventive Hidden",
        "PV901",
        "Druckverlust",
        department_name="Instandhaltung",
        possible_causes="Hydraulikfilter zugesetzt",
        solution="Filter pruefen",
    )
    with app.app_context():
        db.session.add(
            ShiftHandover(
                department="Instandhaltung",
                area="Hydraulik",
                machine_id=machine_id,
                shift_date=date.today(),
                shift_type="Spaet",
                status="open",
                content="Diese Uebergabe darf ohne Recht nicht in Empfehlungen erscheinen.",
                open_tasks="Hydraulikdruck pruefen.",
            )
        )
        db.session.commit()

    response = client.get(
        "/api/v1/machines/maintenance-recommendations",
        headers=auth_headers(user["username"]),
    )

    item = response.get_json()["data"]["items"][0]
    evidence_types = {entry["type"] for entry in item["evidence"]}
    assert response.status_code == 200
    assert item["machine"]["name"] == "Anlage Preventive Hidden"
    assert item["source_counts"]["shift_handovers"] == 0
    assert item["confidence_uncertainty"] in {"low", "medium", "high"}
    assert "shift_handover" not in evidence_types
    assert "shift_handover" not in item["evidence_summary"]["source_types"]


def test_maintenance_task_generation_requires_task_write_permission(
    client,
    make_user,
    auth_headers,
    set_dashboard_permission,
):
    """Verify plan generation requires task write permission in addition to machine write."""
    user = make_user(username="maintenance_plan_machine_only")
    set_dashboard_permission(user["username"], "machines", can_view=True, can_write=True)
    set_dashboard_permission(user["username"], "tasks", can_view=True, can_write=False)

    response = client.post(
        "/api/v1/machines/maintenance-plans/generate-due",
        headers=auth_headers(user["username"]),
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == "tasks write permission is required"


def test_non_admin_without_machine_write_permission_is_forbidden(
    client,
    make_user,
    auth_headers,
):
    """Verify write permissions are enforced for machine endpoints."""
    user = make_user(
        username="machine_view_only",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )

    response = client.post(
        "/api/v1/machines",
        headers=auth_headers(user["username"]),
        json={"name": "Anlage ohne Recht"},
    )

    assert response.status_code == 403


def test_inventory_create_and_summary_calculates_totals(
    client,
    make_user,
    make_machine,
    auth_headers,
):
    """Verify inventory material creation and summary totals."""
    admin = make_user(
        username="inventory_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Anlage Lager")
    headers = auth_headers(admin["username"])

    create_response = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "name": "Schraube M6",
            "unit_cost": 0.12,
            "quantity": 500,
            "machine_id": machine_id,
            "manufacturer": "ACME",
        },
    )
    summary_response = client.get("/api/v1/inventory/summary", headers=headers)

    assert create_response.status_code == 201
    assert create_response.get_json()["total_value"] == 60.0
    assert summary_response.status_code == 200
    assert summary_response.get_json()["material_count"] == 1
    assert summary_response.get_json()["total_quantity"] == 500
    assert summary_response.get_json()["total_value"] == 60.0


def test_inventory_rejects_negative_or_non_numeric_values(
    client,
    make_user,
    auth_headers,
):
    """Verify inventory parser edgecases return explicit 400 errors."""
    admin = make_user(
        username="inventory_validation_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])

    negative_response = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"name": "Oel", "quantity": -1},
    )
    invalid_float_response = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"name": "Oel 2", "unit_cost": "abc"},
    )

    assert negative_response.status_code == 400
    assert invalid_float_response.status_code == 400


def test_inventory_update_rejects_invalid_numbers(
    client,
    make_user,
    make_material,
    auth_headers,
):
    """Verify inventory updates return 400 for invalid numeric fields."""
    admin = make_user(
        username="inventory_update_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    material_id = make_material("Lager Update", 1.5, 3)
    headers = auth_headers(admin["username"])

    negative_response = client.put(
        f"/api/v1/inventory/{material_id}",
        headers=headers,
        json={"quantity": -5},
    )
    invalid_response = client.put(
        f"/api/v1/inventory/{material_id}",
        headers=headers,
        json={"unit_cost": "teuer"},
    )

    assert negative_response.status_code == 400
    assert invalid_response.status_code == 400


def test_delete_machine_detaches_inventory_material(
    client,
    make_user,
    make_machine,
    make_material,
    auth_headers,
):
    """Verify deleting a machine keeps inventory materials but clears the link."""
    admin = make_user(
        username="machine_delete_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Anlage Loeschen")
    make_material("Material", 2.5, 4, machine_id=machine_id)
    headers = auth_headers(admin["username"])

    delete_response = client.delete(f"/api/v1/machines/{machine_id}", headers=headers)
    materials_response = client.get("/api/v1/inventory", headers=headers)

    assert delete_response.status_code == 204
    assert materials_response.get_json()[0]["machine_id"] is None


def test_machine_and_inventory_lists_support_optional_pagination(
    client,
    make_user,
    make_machine,
    make_material,
    auth_headers,
):
    """Verify large catalog endpoints keep old arrays and expose paginated shapes."""
    admin = make_user(
        username="pagination_asset_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Paginated Anlage")
    make_material("Paginated Lager", 2.5, 4, machine_id=machine_id)
    headers = auth_headers(admin["username"])

    legacy_machines = client.get("/api/v1/machines", headers=headers)
    paged_machines = client.get("/api/v1/machines?limit=1", headers=headers)
    legacy_materials = client.get("/api/v1/inventory", headers=headers)
    paged_materials = client.get("/api/v1/inventory?limit=1", headers=headers)
    compact_summary = client.get(
        "/api/v1/inventory/summary?include_materials=0",
        headers=headers,
    )

    assert legacy_machines.status_code == 200
    assert isinstance(legacy_machines.get_json(), list)
    assert paged_machines.status_code == 200
    assert paged_machines.get_json()["data"]["pagination"]["total"] >= 1
    assert len(paged_machines.get_json()["data"]["items"]) == 1
    assert legacy_materials.status_code == 200
    assert isinstance(legacy_materials.get_json(), list)
    assert paged_materials.get_json()["data"]["pagination"]["total"] >= 1
    compact_payload = compact_summary.get_json()
    assert "materials" not in compact_payload
    assert compact_payload["status_counts"] == {"critical": 0, "low": 1, "ok": 0}
    assert compact_payload["top_shortages"][0]["name"] == "Paginated Lager"


def test_inventory_forecast_respects_task_department_visibility(
    client,
    make_user,
    make_machine,
    make_material,
    make_task,
    auth_headers,
):
    """Verify inventory forecasts only use tasks visible to the user."""
    requester = make_user(
        username="forecast_requester",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    other_user = make_user(
        username="forecast_other",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    visible_machine_id = make_machine(name="Anlage Sichtbar")
    hidden_machine_id = make_machine(name="Anlage Fremd")
    make_material("Sichtbares Lager", 4.0, 1, machine_id=visible_machine_id)
    make_material("Fremdes Lager", 4.0, 0, machine_id=hidden_machine_id)
    make_task(
        "Stillstand Anlage Sichtbar",
        creator_username=requester["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Anlage Sichtbar steht mit Sensorfehler",
    )
    make_task(
        "Stillstand Anlage Fremd",
        creator_username=other_user["username"],
        department_name="Produktion",
        priority=Priority.URGENT,
        description="Anlage Fremd steht",
    )

    response = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(requester["username"]),
        json={"status": "open", "low_stock_threshold": 5},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert [item["material"]["name"] for item in payload["items"]] == [
        "Sichtbares Lager",
    ]


def test_inventory_forecast_requires_inventory_and_task_view(
    client,
    make_user,
    set_dashboard_permission,
    auth_headers,
):
    """Verify inventory forecasts require both inventory and task view rights."""
    tasks_only = make_user(
        username="forecast_tasks_only",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    inventory_only = make_user(
        username="forecast_inventory_only",
        role=Role.VERWALTUNG,
        department_name="Verwaltung",
    )
    set_dashboard_permission(
        inventory_only["username"],
        "tasks",
        can_view=False,
        can_write=False,
    )

    missing_inventory = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(tasks_only["username"]),
        json={},
    )
    missing_tasks = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(inventory_only["username"]),
        json={},
    )

    assert missing_inventory.status_code == 403
    assert missing_tasks.status_code == 403


def test_inventory_forecast_flags_low_stock_for_critical_task(
    client,
    make_user,
    make_machine,
    make_material,
    make_task,
    auth_headers,
):
    """Verify low inventory linked to a critical task creates a warning."""
    user = make_user(
        username="forecast_low_stock",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage Kritisch")
    make_material("Sensor S1", 12.5, 1, machine_id=machine_id)
    make_task(
        "Stillstand Anlage Kritisch",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
        description="Anlage Kritisch steht mit Sensorfehler",
    )

    response = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(user["username"]),
        json={"status": "open", "low_stock_threshold": 5},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["summary"]["high"] == 1
    assert payload["items"][0]["material"]["name"] == "Sensor S1"
    assert payload["items"][0]["risk_level"] == "high"
    assert payload["items"][0]["score"] >= 65


def test_inventory_forecast_matches_machine_partial_name(
    client,
    make_user,
    make_machine,
    make_material,
    make_task,
    auth_headers,
):
    """Verify inventory forecasts match tasks with partial machine names."""
    user = make_user(
        username="forecast_partial_match",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="CNC-Fraese 01", produced_item="Alu Gehaeuse")
    make_material("Fraeser Reserve", 42.0, 1, machine_id=machine_id)
    make_task(
        "Stillstand CNC-Fraese",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
        description="CNC-Fraese meldet Lagergeraeusch",
    )

    response = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(user["username"]),
        json={"status": "open", "low_stock_threshold": 5},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["items"][0]["machine"]["name"] == "CNC-Fraese 01"
    assert payload["items"][0]["material"]["name"] == "Fraeser Reserve"
    assert payload["items"][0]["match_reason"]


def test_inventory_forecast_reports_unmatched_high_risk_tasks(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify high-risk tasks without a machine match are returned visibly."""
    user = make_user(
        username="forecast_unmatched",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_task(
        "Stillstand unbekannte Linie",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
        description="Anlage ohne Stammdatensatz steht",
    )

    response = client.post(
        "/api/v1/inventory/forecast",
        headers=auth_headers(user["username"]),
        json={"status": "open", "low_stock_threshold": 5},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["items"] == []
    assert payload["unmatched_tasks"][0]["task"]["title"] == "Stillstand unbekannte Linie"


def test_inventory_forecast_rejects_invalid_payloads(
    client,
    make_user,
    auth_headers,
):
    """Verify inventory forecasts reject malformed filters."""
    user = make_user(
        username="forecast_validation",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    bad_threshold = client.post(
        "/api/v1/inventory/forecast",
        headers=headers,
        json={"low_stock_threshold": -1},
    )
    bad_limit = client.post(
        "/api/v1/inventory/forecast",
        headers=headers,
        json={"limit": 0},
    )
    bad_status = client.post(
        "/api/v1/inventory/forecast",
        headers=headers,
        json={"status": "unknown"},
    )

    assert bad_threshold.status_code == 400
    assert bad_limit.status_code == 400
    assert bad_status.status_code == 400


def test_inventory_page_contains_forecast_ui(client):
    """Verify the inventory page exposes the forecast controls."""
    response = client.get("/inventory")
    html = response.get_data(as_text=True)
    source = inventory_react_source()

    assert response.status_code == 200
    assert "maintenance-inventory-root" in html
    assert "data-react-inventory-fallback" not in html
    assert "data-inventory-forecast-form" in source
    assert "data-inventory-forecast-list" in source
    assert "Ersatzteil-Prognose" in source


def test_machine_history_only_uses_permitted_sources(
    client,
    make_user,
    set_dashboard_permission,
    make_machine,
    make_task,
    make_error_entry,
    make_document,
    auth_headers,
):
    """Verify machine history only includes sources allowed by dashboard rights."""
    user = make_user(
        username="history_source_rights",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user["username"], "machines", can_view=True)
    set_dashboard_permission(user["username"], "errors", can_view=False)
    set_dashboard_permission(user["username"], "documents", can_view=False)
    machine_id = make_machine(name="Anlage Historie")
    task_id = make_task(
        "Task Anlage Historie",
        creator_username=user["username"],
        department_name="Produktion",
        description="Anlage Historie pruefen",
    )
    make_error_entry(
        "Anlage Historie",
        "E900",
        "Fehler Anlage Historie",
        department_name="Produktion",
    )
    make_document(
        task_id,
        user["id"],
        department="Produktion",
        machine="Anlage Historie",
    )

    response = client.get(
        f"/api/v1/machines/{machine_id}/history",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["source_counts"] == {
        "tasks": 1,
        "errors": 0,
        "documents": 0,
        "total": 1,
    }
    assert [item["type"] for item in payload["timeline"]] == ["task"]


def test_machine_history_respects_non_admin_department_scope(
    client,
    make_user,
    make_machine,
    make_task,
    make_error_entry,
    make_document,
    auth_headers,
):
    """Verify non-admin machine history excludes other departments."""
    requester = make_user(
        username="history_department_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    other_user = make_user(
        username="history_other_department",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    machine_id = make_machine(name="Anlage Bereich")
    visible_task_id = make_task(
        "Task Anlage Bereich sichtbar",
        creator_username=requester["username"],
        department_name="Instandhaltung",
        description="Anlage Bereich pruefen",
    )
    make_task(
        "Task Anlage Bereich fremd",
        creator_username=other_user["username"],
        department_name="Produktion",
        description="Anlage Bereich pruefen",
    )
    make_error_entry(
        "Anlage Bereich",
        "E901",
        "Sichtbarer Fehler",
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Anlage Bereich",
        "E902",
        "Fremder Fehler",
        department_name="Produktion",
    )
    make_document(
        visible_task_id,
        requester["id"],
        department="Instandhaltung",
        machine="Anlage Bereich",
    )
    make_document(
        visible_task_id,
        requester["id"],
        relative_path="2026/05/task_2/maintenance_report.html",
        department="Produktion",
        machine="Anlage Bereich",
    )

    response = client.get(
        f"/api/v1/machines/{machine_id}/history",
        headers=auth_headers(requester["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["source_counts"]["tasks"] == 1
    assert payload["source_counts"]["errors"] == 1
    assert payload["source_counts"]["documents"] == 1
    assert all("fremd" not in item["title"].lower() for item in payload["timeline"])


def test_machine_history_unknown_machine_returns_404(client, make_user, auth_headers):
    """Verify unknown machines return 404 for history requests."""
    admin = make_user(
        username="history_missing_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.get(
        "/api/v1/machines/999/history",
        headers=auth_headers(admin["username"]),
    )

    assert response.status_code == 404


def test_machine_history_uses_local_summary_without_openai_key(
    client,
    make_user,
    make_machine,
    auth_headers,
):
    """Verify machine history returns a local summary with mock AI settings."""
    admin = make_user(
        username="history_summary_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Anlage Zusammenfassung")

    response = client.get(
        f"/api/v1/machines/{machine_id}/history",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["summary"]["diagnostics"]["status"] == "local_answer"
    assert "Anlage Zusammenfassung" in payload["summary"]["text"]


def test_machine_profile_combines_operational_sources(
    app,
    client,
    make_user,
    make_machine,
    make_task,
    auth_headers,
):
    """Verify the machine profile combines related operational records."""
    admin = make_user(
        username="machine_profile_admin",
        role=Role.MASTER_ADMIN,
        department_name="Produktion",
    )
    machine_id = make_machine(name="Profil Anlage", produced_item="Pumpenrad")
    task_id = make_task(
        "Profil Anlage Filter pruefen",
        creator_username=admin["username"],
        department_name="Produktion",
        priority=Priority.SOON,
        description="Profil Anlage braucht einen Filtercheck.",
    )
    with app.app_context():
        department = Department.query.filter_by(name="Produktion").one()
        machine = db.session.get(Machine, machine_id)
        db.session.add_all(
            [
                ErrorEntry(
                    machine=machine.name,
                    machine_id=machine.id,
                    error_code="PF-100",
                    title="Sensorfehler",
                    description="Sensor meldet unplausible Werte.",
                    possible_causes="Sensorik verschmutzt",
                    solution="Sensor reinigen und neu kalibrieren.",
                    department=department,
                    status="open",
                    severity="critical",
                    cause_category="Sensorik",
                    impact="Produktion verlangsamt",
                    downtime_minutes=45,
                ),
                GeneratedDocument(
                    task_id=task_id,
                    document_type="maintenance_report",
                    title="Filtercheck Bericht",
                    relative_path="2026/05/profile/filtercheck.html",
                    department="Produktion",
                    machine=machine.name,
                    machine_id=machine.id,
                    created_by=admin["id"],
                    status="approved",
                ),
                MachineManual(
                    machine_id=machine.id,
                    department="Produktion",
                    title="Profil Anlage Handbuch",
                    original_filename="profil-anlage.pdf",
                    relative_path="profile/profil-anlage.pdf",
                    content_type="application/pdf",
                    created_by=admin["id"],
                ),
                MaintenancePlan(
                    title="Monatliche Sichtpruefung",
                    description="Dichtungen, Sensorik und Filter pruefen.",
                    interval_days=30,
                    next_due_date=date.today(),
                    priority=Priority.SOON,
                    machine=machine,
                    department=department,
                    created_by=admin["id"],
                    last_generated_task_id=task_id,
                ),
                ShiftHandover(
                    department="Produktion",
                    area="Linie 1",
                    machine_id=machine.id,
                    shift_date=date.today(),
                    shift_type="Frueh",
                    previous_shift="Nacht",
                    next_shift="Spaet",
                    status="open",
                    machine_status="Sensorik beobachten",
                    production_status="eingeschraenkt",
                    responsible_employee="Max Mustermann",
                ),
            ]
        )
        db.session.commit()

    response = client.get(
        f"/api/v1/machines/{machine_id}/profile",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["machine"]["id"] == machine_id
    assert payload["kpis"]["open_tasks"] == 1
    assert payload["kpis"]["active_errors"] == 1
    assert payload["kpis"]["maintenance_due"] == 1
    assert payload["kpis"]["documents"] == 2
    assert payload["kpis"]["shift_handovers"] == 1
    assert payload["kpis"]["downtime_minutes"] == 45
    assert payload["open_tasks"][0]["id"] == task_id
    assert payload["active_errors"][0]["error_code"] == "PF-100"
    assert payload["documents"]["reports"][0]["machine_id"] == machine_id
    assert payload["documents"]["manuals"][0]["machine_id"] == machine_id
    assert payload["maintenance_plans"][0]["machine_id"] == machine_id
    assert payload["shift_handovers"][0]["machine_id"] == machine_id
    assert {item["type"] for item in payload["timeline"]} >= {
        "task",
        "error",
        "document",
        "manual",
        "maintenance",
        "handover",
    }


def test_machine_page_contains_history_ui(client):
    """Verify the machine page exposes the history target container."""
    response = client.get("/machines")
    html = response.get_data(as_text=True)
    source = machine_react_source()

    assert response.status_code == 200
    assert "maintenance-machines-root" in html
    assert "data-react-machines-fallback" not in html
    assert "data-machine-history-panel" in source
    assert "data-machine-history-list" in source
    assert "data-machine-assistant-form" in source
    assert "data-machine-assistant-sources" in source
    assert "data-maintenance-recommendations-list" in source
    assert "Anlagenakte" in source


def test_machine_detail_page_contains_profile_targets(client):
    """Verify the machine detail page exposes the profile UI hooks."""
    response = client.get("/machines/123")
    html = response.get_data(as_text=True)
    source = machine_react_source()

    assert response.status_code == 200
    assert "maintenance-machine-profile-root" in html
    assert "data-react-machine-profile-fallback" not in html
    assert "data-machine-profile-page" in source
    assert 'data-machine-id="123"' in html
    assert "data-machine-profile-kpis" in source
    assert "data-machine-profile-tasks" in source
    assert "data-machine-profile-errors" in source
    assert "data-machine-profile-documents" in source
    assert "data-machine-profile-handovers" in source


def test_machine_assistant_uses_local_context_and_requires_question(
    client,
    make_user,
    make_machine,
    make_task,
    auth_headers,
):
    """Verify the machine assistant answers locally and validates questions."""
    user = make_user(
        username="machine_assistant_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage Assistent")
    make_task(
        "Task Anlage Assistent",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Anlage Assistent pruefen",
    )
    headers = auth_headers(user["username"])

    empty_response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=headers,
        json={},
    )
    valid_response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=headers,
        json={"question": "Was ist wichtig?"},
    )

    payload = valid_response.get_json()
    assert empty_response.status_code == 400
    assert valid_response.status_code == 200
    assert payload["diagnostics"]["status"] == "local_answer"
    assert payload["context"]["source_counts"]["tasks"] == 1


def test_machine_assistant_uses_rag_sources_after_reindex(
    client,
    make_user,
    make_machine,
    make_task,
    make_error_entry,
    auth_headers,
):
    """Verify the machine assistant adds indexed RAG sources to its context."""
    admin = make_user(
        username="machine_assistant_rag_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="machine_assistant_rag_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage RAG")
    make_task(
        "Hydraulikfilter Anlage RAG pruefen",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Anlage RAG zeigt Druckverlust am Hydraulikfilter.",
    )
    make_error_entry(
        "Anlage RAG",
        "RAG900",
        "Hydraulikfilter Druckverlust",
        department_name="Instandhaltung",
        possible_causes="Hydraulikfilter zugesetzt oder Druckversorgung instabil",
        solution="Filter pruefen, Druck messen und Befund dokumentieren",
    )
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=auth_headers(user["username"]),
        json={"question": "Welche bekannten Hydraulikfilter-Probleme gibt es?"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["context"]["rag_source_count"] >= 1
    assert any(source["type"] == "knowledge" for source in payload["sources"])
    assert "RAG-Kontext" in payload["answer"]


def test_machine_assistant_excludes_unpermitted_sources(
    client,
    make_user,
    make_machine,
    make_task,
    make_error_entry,
    make_document,
    set_dashboard_permission,
    auth_headers,
):
    """Verify machine assistant context only includes permitted data sources."""
    user = make_user(
        username="machine_assistant_limited_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage Gesperrt")
    task_id = make_task(
        "Task Anlage Gesperrt",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Anlage Gesperrt pruefen",
    )
    make_error_entry(
        "Anlage Gesperrt",
        "E790",
        "Sensorfehler",
        department_name="Instandhaltung",
    )
    make_document(
        task_id,
        user["id"],
        relative_path="2026/05/task_limited/maintenance_report.html",
        department="Instandhaltung",
        machine="Anlage Gesperrt",
    )
    set_dashboard_permission(user["username"], "tasks", can_view=False)
    set_dashboard_permission(user["username"], "errors", can_view=False)
    set_dashboard_permission(user["username"], "documents", can_view=False)
    set_dashboard_permission(user["username"], "inventory", can_view=False)

    response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=auth_headers(user["username"]),
        json={"question": "Was ist sichtbar?"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["context"]["source_counts"] == {
        "tasks": 0,
        "errors": 0,
        "documents": 0,
        "total": 0,
    }
    assert payload["context"]["forecast_items"] == 0
    assert payload["context"]["rag_source_count"] == 0
    assert payload["sources"] == []


def test_machine_assistant_falls_back_when_ai_provider_fails(
    client,
    make_user,
    make_machine,
    auth_headers,
    monkeypatch,
):
    """Verify machine assistant returns a local answer when AI provider fails."""

    class FailingProvider:
        """AI provider stub that always fails."""

        name = "openai"

        def answer_question(self, question, context):
            """Raise an AI service error for fallback testing."""
            raise AIServiceError("provider unavailable")

    user = make_user(
        username="machine_assistant_fallback_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage Fallback")
    monkeypatch.setattr(
        "app.machines.services.get_ai_provider",
        lambda: FailingProvider(),
    )

    response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=auth_headers(user["username"]),
        json={"question": "Was ist zu tun?"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["diagnostics"]["status"] == "fallback_used"
    assert "Anlage Fallback" in payload["answer"]


def test_machine_list_reports_visible_task_and_error_signals(
    client,
    make_user,
    make_machine,
    make_task,
    make_error_entry,
    auth_headers,
):
    """Verify machine cards get open task, active error and last error signals."""
    admin = make_user(
        username="machine_signal_admin",
        role=Role.MASTER_ADMIN,
        department_name="Instandhaltung",
    )
    signal_machine_id = make_machine(name="Presse Signal 7")
    quiet_machine_id = make_machine(name="Presse Ruhig 2")
    make_task(
        "Presse Signal 7 Hydraulik pruefen",
        creator_username=admin["username"],
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Presse Signal 7",
        "PS700",
        "Druckverlust Hauptzylinder",
        department_name="Instandhaltung",
    )

    response = client.get("/api/v1/machines", headers=auth_headers(admin["username"]))

    assert response.status_code == 200
    machines = {item["id"]: item for item in response.get_json()}
    assert machines[signal_machine_id]["open_tasks"] == 1
    assert machines[signal_machine_id]["active_errors"] == 1
    assert machines[signal_machine_id]["last_error"] == "Druckverlust Hauptzylinder"
    assert machines[quiet_machine_id]["open_tasks"] == 0
    assert machines[quiet_machine_id]["active_errors"] == 0
    assert machines[quiet_machine_id]["last_error"] == ""
