"""Machine API routes."""

from flask import Blueprint, Response, jsonify, request

from app.extensions import db
from app.machines.maintenance_services import (
    create_maintenance_plan,
    delete_maintenance_plan,
    generate_due_maintenance_tasks,
    get_visible_maintenance_plan,
    recommend_preventive_maintenance,
    record_maintenance,
    update_maintenance_plan,
    visible_maintenance_plans_query,
)
from app.machines.services import (
    answer_machine_assistant,
    build_machine_history,
    build_machine_profile,
    machine_list_signals,
    machine_qr_svg,
)
from app.models import InventoryMaterial, Machine, MaintenancePlan, ShiftPlanEntry, Site
from app.responses import (
    error_response,
    optional_paginated_response,
    service_error_response,
    success_response,
)
from app.security import current_user, dashboard_permission_required
from app.services.knowledge_service import (
    delete_source_knowledge_document,
    mark_machine_knowledge_stale,
)
from app.services.operations_tracking_service import record_event
from app.services.text_normalization_service import normalize_text

machines_bp = Blueprint("machines", __name__)


def parse_required_employees(value):
    """Parse and validate the required employee count for a machine."""
    try:
        amount = int(1 if value in (None, "") else value)
    except (TypeError, ValueError) as exc:
        raise ValueError("required_employees must be a number") from exc
    if amount < 1:
        raise ValueError("required_employees must be at least 1")
    return amount


def normalize_machine_name(value):
    """Return a canonical machine name from user input."""
    return " ".join(str(value or "").strip().split())


def machine_name_exists(name, exclude_id=None):
    """Return whether a normalized machine name already exists."""
    normalized_name = normalize_text(name)
    query = Machine.query
    if exclude_id is not None:
        query = query.filter(Machine.id != exclude_id)
    return any(normalize_text(machine.name) == normalized_name for machine in query.all())


def site_for_payload(data):
    """Resolve an optional site reference from request data."""
    if not data.get("site_id"):
        return None
    return db.session.get(Site, int(data["site_id"]))


def machine_event_state(machine):
    """Return compact machine state for audit old/new values."""
    return {
        "id": machine.id,
        "name": machine.name,
        "produced_item": machine.produced_item,
        "required_employees": machine.required_employees,
        "site_id": machine.site_id,
        "criticality": machine.criticality,
        "status": machine.status,
        "last_downtime_at": (
            machine.last_downtime_at.isoformat() if machine.last_downtime_at else None
        ),
    }


@machines_bp.get("")
@dashboard_permission_required("machines", "view")
def list_machines():
    """Return machines, optionally paginated for large plant catalogs."""
    query = Machine.query.order_by(Machine.name.asc(), Machine.id.asc())
    site_id = request.args.get("site_id", type=int)
    if site_id is not None:
        query = query.filter(Machine.site_id == site_id)
    machine_id = request.args.get("machine_id", type=int)
    if machine_id is not None:
        query = query.filter(Machine.id == machine_id)
    user = current_user()
    signals = machine_list_signals(query.all(), user)
    return optional_paginated_response(
        query,
        lambda machine: {**machine.to_dict(), **signals.get(machine.id, {})},
        message="Machines loaded",
        default_limit=100,
        max_limit=200,
    )


@machines_bp.post("")
@dashboard_permission_required("machines", "write")
def create_machine():
    """Create a machine with production output and staffing requirement."""
    data = request.get_json(silent=True) or {}
    machine_name = normalize_machine_name(data.get("name"))
    if not machine_name:
        return error_response("name is required", 400)
    if machine_name_exists(machine_name):
        return error_response("machine already exists", 409)
    try:
        machine = Machine(
            name=machine_name,
            produced_item=data.get("produced_item", "").strip(),
            required_employees=parse_required_employees(data.get("required_employees")),
            site=site_for_payload(data),
            criticality=str(data.get("criticality") or "normal").strip(),
            status=str(data.get("status") or "running").strip(),
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    db.session.add(machine)
    db.session.flush()
    mark_machine_knowledge_stale(machine)
    record_event(
        "machine.created",
        "machines",
        entity_type="machine",
        entity_id=machine.id,
        user=current_user(),
        machine=machine,
        metadata={"criticality": machine.criticality, "status": machine.status},
        new_value=machine_event_state(machine),
        description=f"Maschine erstellt: {machine.name}",
    )
    db.session.commit()
    return jsonify(machine.to_dict()), 201


@machines_bp.get("/maintenance-plans")
@dashboard_permission_required("machines", "view")
def list_maintenance_plans():
    """Return visible recurring maintenance plans."""
    plans = (
        visible_maintenance_plans_query(current_user())
        .order_by(MaintenancePlan.next_due_date.asc(), MaintenancePlan.id.asc())
        .all()
    )
    return success_response(
        [plan.to_dict() for plan in plans],
        message="Maintenance plans loaded",
    )


@machines_bp.post("/maintenance-plans")
@dashboard_permission_required("machines", "write")
def add_maintenance_plan():
    """Create a recurring maintenance plan."""
    plan, error, status = create_maintenance_plan(
        request.get_json(silent=True) or {},
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    return success_response(plan.to_dict(), status, "Maintenance plan created")


@machines_bp.post("/maintenance-plans/generate-due")
@dashboard_permission_required("machines", "write")
def generate_due_maintenance():
    """Generate open tasks for due recurring maintenance plans."""
    user = current_user()
    result, error, status = generate_due_maintenance_tasks(current_user())
    if error:
        return service_error_response(error, status)
    record_event(
        "maintenance.tasks_generated",
        "tasks",
        entity_type="maintenance_plan",
        user=user,
        source="machines",
        metadata={"generated_count": result.get("generated_count", 0)},
        commit=True,
    )
    return success_response(result, status, "Maintenance tasks generated")


@machines_bp.get("/maintenance-recommendations")
@dashboard_permission_required("machines", "view")
def preventive_maintenance_recommendations():
    """Return read-only preventive maintenance recommendations."""
    result, error, status = recommend_preventive_maintenance(
        current_user(),
        limit=request.args.get("limit", 5),
    )
    if error:
        return service_error_response(error, status)
    return success_response(result, status, "Maintenance recommendations loaded")


@machines_bp.put("/maintenance-plans/<int:plan_id>")
@dashboard_permission_required("machines", "write")
def edit_maintenance_plan(plan_id):
    """Update a visible recurring maintenance plan."""
    plan = get_visible_maintenance_plan(plan_id, current_user())
    if not plan:
        return error_response("Maintenance plan not found", 404)
    updated, error, status = update_maintenance_plan(
        plan,
        request.get_json(silent=True) or {},
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    return success_response(updated.to_dict(), status, "Maintenance plan updated")


@machines_bp.get("/maintenance-plans/<int:plan_id>/records")
@dashboard_permission_required("machines", "view")
def list_maintenance_records(plan_id):
    """Return the documented executions of a visible plan, newest first."""
    plan = get_visible_maintenance_plan(plan_id, current_user())
    if not plan:
        return error_response("Maintenance plan not found", 404)
    return success_response(
        [record.to_dict() for record in plan.records], message="Maintenance records loaded"
    )


@machines_bp.post("/maintenance-plans/<int:plan_id>/records")
@dashboard_permission_required("machines", "write")
def add_maintenance_record(plan_id):
    """Document an execution of a visible plan."""
    user = current_user()
    plan = get_visible_maintenance_plan(plan_id, user)
    if not plan:
        return error_response("Maintenance plan not found", 404)
    record, error, status = record_maintenance(plan, request.get_json(silent=True) or {}, user)
    if error:
        return service_error_response(error, status)
    record_event(
        "maintenance.recorded",
        "machines",
        entity_type="maintenance_plan",
        entity_id=plan.id,
        user=user,
        machine_id=plan.machine_id,
        metadata={"kind": plan.kind, "result": record.result},
        commit=True,
    )
    return success_response(
        {"record": record.to_dict(), "plan": plan.to_dict()}, status, "Maintenance recorded"
    )


@machines_bp.delete("/maintenance-plans/<int:plan_id>")
@dashboard_permission_required("machines", "write")
def remove_maintenance_plan(plan_id):
    """Delete a visible recurring maintenance plan."""
    plan = get_visible_maintenance_plan(plan_id, current_user())
    if not plan:
        return error_response("Maintenance plan not found", 404)
    error, status = delete_maintenance_plan(plan)
    if error:
        return service_error_response(error, status)
    return "", status


@machines_bp.get("/<int:machine_id>/history")
@dashboard_permission_required("machines", "view")
def machine_history(machine_id):
    """Return a read-only history for one machine."""
    machine = db.get_or_404(Machine, machine_id)
    return success_response(
        build_machine_history(machine, current_user()),
        message="Machine history loaded",
    )


@machines_bp.get("/<int:machine_id>/qr.svg")
@dashboard_permission_required("machines", "view")
def machine_qr_code(machine_id):
    """Return an SVG QR code that opens the machine page on a phone."""
    machine = db.get_or_404(Machine, machine_id)
    return Response(machine_qr_svg(machine, request.host_url), mimetype="image/svg+xml")


@machines_bp.get("/<int:machine_id>/profile")
@dashboard_permission_required("machines", "view")
def machine_profile(machine_id):
    """Return the full operational profile for one machine."""
    machine = db.get_or_404(Machine, machine_id)
    return success_response(
        build_machine_profile(machine, current_user()),
        message="Machine profile loaded",
    )


@machines_bp.post("/<int:machine_id>/assistant")
@dashboard_permission_required("machines", "view")
def machine_assistant(machine_id):
    """Answer a machine-specific maintenance question."""
    machine = db.get_or_404(Machine, machine_id)
    user = current_user()
    result, error, status = answer_machine_assistant(
        machine,
        user,
        request.get_json(silent=True) or {},
    )
    if error:
        return service_error_response(error, status)
    record_event(
        "ai.machine_assistant",
        "ai",
        entity_type="machine",
        entity_id=machine.id,
        user=user,
        machine=machine,
        source="ai",
        metadata={
            "status": (result.get("diagnostics") or {}).get("status")
            if isinstance(result, dict)
            else "",
        },
        commit=True,
    )
    return success_response(result, status, "Machine assistant response generated")


@machines_bp.put("/<int:machine_id>")
@dashboard_permission_required("machines", "write")
def update_machine(machine_id):
    """Update machine metadata used by inventory and shift planning."""
    machine = db.get_or_404(Machine, machine_id)
    data = request.get_json(silent=True) or {}
    old_state = machine_event_state(machine)
    old_status = machine.status
    if "name" in data:
        machine_name = normalize_machine_name(data["name"])
        if not machine_name:
            return error_response("name is required", 400)
        if machine_name_exists(machine_name, exclude_id=machine.id):
            return error_response("machine already exists", 409)
        machine.name = machine_name
    if "produced_item" in data:
        machine.produced_item = data["produced_item"].strip()
    if "required_employees" in data:
        try:
            machine.required_employees = parse_required_employees(data["required_employees"])
        except ValueError as exc:
            return error_response(str(exc), 400)
    if "site_id" in data:
        machine.site = site_for_payload(data)
    if "criticality" in data:
        machine.criticality = str(data.get("criticality") or "normal").strip()
    if "status" in data:
        machine.status = str(data.get("status") or "running").strip()
    user = current_user()
    record_event(
        "machine.updated",
        "machines",
        entity_type="machine",
        entity_id=machine.id,
        user=user,
        machine=machine,
        metadata={"criticality": machine.criticality, "status": machine.status},
        old_value=old_state,
        new_value=machine_event_state(machine),
        description=f"Maschine aktualisiert: {machine.name}",
    )
    if old_status != machine.status:
        record_event(
            "machine.status_changed",
            "machines",
            entity_type="machine",
            entity_id=machine.id,
            user=user,
            machine=machine,
            metadata={
                "old_status": old_status,
                "new_status": machine.status,
                "criticality": machine.criticality,
            },
            old_value=old_status,
            new_value=machine.status,
            description=f"Maschinenstatus geaendert: {old_status} -> {machine.status}",
        )
    mark_machine_knowledge_stale(machine)
    db.session.commit()
    return jsonify(machine.to_dict())


@machines_bp.delete("/<int:machine_id>")
@dashboard_permission_required("machines", "write")
def delete_machine(machine_id):
    """Delete a machine and detach related inventory and plan entries."""
    machine = db.get_or_404(Machine, machine_id)
    record_event(
        "machine.deleted",
        "machines",
        entity_type="machine",
        entity_id=machine.id,
        user=current_user(),
        machine=machine,
        metadata={"name": machine.name, "criticality": machine.criticality},
        old_value=machine_event_state(machine),
        description=f"Maschine geloescht: {machine.name}",
    )
    InventoryMaterial.query.filter_by(machine_id=machine.id).update({"machine_id": None})
    ShiftPlanEntry.query.filter_by(machine_id=machine.id).update({"machine_id": None})
    delete_source_knowledge_document("machine", machine.id)
    db.session.delete(machine)
    db.session.commit()
    return "", 204
