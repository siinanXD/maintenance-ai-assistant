"""Inventory API routes."""

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.inventory.services import forecast_inventory_risks
from app.models import InventoryMaterial, Machine, Site
from app.responses import (
    error_response,
    optional_paginated_response,
    service_error_response,
    success_response,
)
from app.security import current_user, dashboard_permission_required
from app.services.operations_tracking_service import record_event
from app.services.stock_movement_service import (
    book_receipt,
    material_movements,
    reorder_suggestions,
)

inventory_bp = Blueprint("inventory", __name__)


def filtered_inventory_query():
    """Return inventory materials filtered by supported request arguments."""
    query = InventoryMaterial.query
    site_id = request.args.get("site_id", type=int)
    if site_id is not None:
        query = query.filter(InventoryMaterial.site_id == site_id)
    machine_id = request.args.get("machine_id", type=int)
    if machine_id is not None:
        query = query.filter(InventoryMaterial.machine_id == machine_id)
    return query


def material_dashboard_status(material):
    """Return the dashboard stock status bucket for an inventory material."""
    quantity = int(material.quantity or 0)
    if quantity <= 3:
        return "critical"
    if quantity <= 10:
        return "low"
    return "ok"


def inventory_status_counts(materials):
    """Return dashboard stock status counts for inventory materials."""
    counts = {"critical": 0, "low": 0, "ok": 0}
    for material in materials:
        counts[material_dashboard_status(material)] += 1
    return counts


def top_inventory_shortages(materials, limit=3):
    """Return the lowest-quantity materials for dashboard shortage chips."""
    ordered_materials = sorted(
        materials,
        key=lambda material: (
            int(material.quantity or 0),
            material.name.lower(),
            material.id,
        ),
    )
    return [
        {
            "id": material.id,
            "name": material.name,
            "quantity": int(material.quantity or 0),
            "min_quantity": int(material.min_quantity or 0),
            "criticality": material.criticality,
        }
        for material in ordered_materials[:limit]
    ]


def parse_int(value, field_name, default=0):
    """Parse a non-negative integer from an inventory payload field."""
    try:
        amount = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if amount < 0:
        raise ValueError(f"{field_name} must not be negative")
    return amount


def parse_float(value, field_name, default=0):
    """Parse a non-negative float from an inventory payload field."""
    try:
        amount = float(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if amount < 0:
        raise ValueError(f"{field_name} must not be negative")
    return amount


def machine_for_payload(data):
    """Resolve the optional machine reference from request data."""
    if not data.get("machine_id"):
        return None
    return db.session.get(Machine, int(data["machine_id"]))


def site_for_payload(data, machine=None):
    """Resolve an optional site reference from request data or linked machine."""
    if data.get("site_id"):
        return db.session.get(Site, int(data["site_id"]))
    return machine.site if machine and machine.site else None


@inventory_bp.get("")
@dashboard_permission_required("inventory", "view")
def list_materials():
    """Return inventory materials, optionally paginated for large stock catalogs."""
    query = (
        filtered_inventory_query()
        .options(selectinload(InventoryMaterial.machine))
        .order_by(InventoryMaterial.name.asc(), InventoryMaterial.id.asc())
    )
    return optional_paginated_response(
        query,
        lambda material: material.to_dict(),
        message="Inventory materials loaded",
        default_limit=100,
        max_limit=200,
    )


@inventory_bp.get("/summary")
@dashboard_permission_required("inventory", "view")
def inventory_summary():
    """Return inventory totals, with optional material rows for legacy clients."""
    include_materials = str(request.args.get("include_materials", "true")).lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    base_query = filtered_inventory_query()
    totals_query = base_query.with_entities(
        func.count(InventoryMaterial.id),
        func.coalesce(func.sum(InventoryMaterial.quantity), 0),
        func.coalesce(func.sum(InventoryMaterial.quantity * InventoryMaterial.unit_cost), 0.0),
    )
    totals = totals_query.one()
    dashboard_materials = base_query.order_by(
        InventoryMaterial.quantity.asc(),
        InventoryMaterial.name.asc(),
        InventoryMaterial.id.asc(),
    ).all()
    payload = {
        "material_count": int(totals[0] or 0),
        "total_quantity": int(totals[1] or 0),
        "total_value": round(float(totals[2] or 0.0), 2),
        "status_counts": inventory_status_counts(dashboard_materials),
        "top_shortages": top_inventory_shortages(dashboard_materials),
    }
    if include_materials:
        materials = (
            base_query.options(selectinload(InventoryMaterial.machine))
            .order_by(
                InventoryMaterial.name.asc(),
                InventoryMaterial.id.asc(),
            )
            .all()
        )
        payload["materials"] = [material.to_dict() for material in materials]
    return jsonify(payload)


@inventory_bp.get("/reorder")
@dashboard_permission_required("inventory", "view")
def reorder():
    """Return materials at or below minimum stock with order quantities."""
    return success_response(reorder_suggestions(), message="Reorder suggestions loaded")


@inventory_bp.get("/<int:material_id>/movements")
@dashboard_permission_required("inventory", "view")
def movements(material_id):
    """Return the latest stock movements of one material."""
    material = db.get_or_404(InventoryMaterial, material_id)
    return success_response(material_movements(material), message="Movements loaded")


@inventory_bp.post("/<int:material_id>/receipts")
@dashboard_permission_required("inventory", "write")
def receipt(material_id):
    """Book delivered parts into stock."""
    material = db.get_or_404(InventoryMaterial, material_id)
    movement, error, status = book_receipt(
        material, request.get_json(silent=True) or {}, current_user()
    )
    if error:
        return service_error_response(error, status)
    return success_response(
        {"movement": movement.to_dict(), "material": material.to_dict()}, status, "Receipt booked"
    )


@inventory_bp.post("/forecast")
@dashboard_permission_required("inventory", "view")
@dashboard_permission_required("tasks", "view")
def inventory_forecast():
    """Return spare-part forecasts for visible tasks and linked inventory."""
    forecast, error, status = forecast_inventory_risks(
        request.get_json(silent=True) or {},
        current_user(),
    )
    if error:
        return service_error_response(error, status)
    return success_response(forecast, status, "Inventory forecast loaded")


@inventory_bp.post("")
@dashboard_permission_required("inventory", "write")
def create_material():
    """Create an inventory material and link it to a machine if provided."""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return error_response("name is required", 400)
    try:
        machine = machine_for_payload(data)
        material = InventoryMaterial(
            name=data["name"].strip(),
            unit_cost=parse_float(data.get("unit_cost"), "unit_cost"),
            quantity=parse_int(data.get("quantity"), "quantity"),
            min_quantity=parse_int(data.get("min_quantity"), "min_quantity"),
            criticality=str(data.get("criticality") or "normal").strip(),
            lead_time_days=parse_int(data.get("lead_time_days"), "lead_time_days"),
            manufacturer=data.get("manufacturer", "").strip(),
            site=site_for_payload(data, machine=machine),
            machine=machine,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    db.session.add(material)
    db.session.flush()
    record_event(
        "inventory.created",
        "inventory",
        entity_type="inventory_material",
        entity_id=material.id,
        user=current_user(),
        machine=material.machine,
        site_id=material.site_id,
        metadata={
            "name": material.name,
            "quantity": material.quantity,
            "min_quantity": material.min_quantity,
            "criticality": material.criticality,
        },
    )
    db.session.commit()
    return jsonify(material.to_dict()), 201


@inventory_bp.put("/<int:material_id>")
@dashboard_permission_required("inventory", "write")
def update_material(material_id):
    """Update an inventory material including cost, quantity and machine."""
    material = db.get_or_404(InventoryMaterial, material_id)
    data = request.get_json(silent=True) or {}
    try:
        old_quantity = material.quantity
        if "name" in data:
            material.name = data["name"].strip()
        if "unit_cost" in data:
            material.unit_cost = parse_float(data["unit_cost"], "unit_cost")
        if "quantity" in data:
            material.quantity = parse_int(data["quantity"], "quantity")
        if "min_quantity" in data:
            material.min_quantity = parse_int(data["min_quantity"], "min_quantity")
        if "criticality" in data:
            material.criticality = str(data.get("criticality") or "normal").strip()
        if "lead_time_days" in data:
            material.lead_time_days = parse_int(data["lead_time_days"], "lead_time_days")
        if "manufacturer" in data:
            material.manufacturer = data["manufacturer"].strip()
        if "machine_id" in data:
            material.machine = machine_for_payload(data)
        if "site_id" in data or "machine_id" in data:
            material.site = site_for_payload(data, machine=material.machine)
    except ValueError as exc:
        return error_response(str(exc), 400)
    event_type = (
        "inventory.quantity_changed" if old_quantity != material.quantity else "inventory.updated"
    )
    record_event(
        event_type,
        "inventory",
        entity_type="inventory_material",
        entity_id=material.id,
        user=current_user(),
        machine=material.machine,
        site_id=material.site_id,
        metadata={
            "name": material.name,
            "old_quantity": old_quantity,
            "new_quantity": material.quantity,
            "delta": material.quantity - old_quantity,
            "min_quantity": material.min_quantity,
            "criticality": material.criticality,
        },
    )
    db.session.commit()
    return jsonify(material.to_dict())


@inventory_bp.delete("/<int:material_id>")
@dashboard_permission_required("inventory", "write")
def delete_material(material_id):
    """Delete an inventory material from the lager."""
    material = db.get_or_404(InventoryMaterial, material_id)
    record_event(
        "inventory.deleted",
        "inventory",
        entity_type="inventory_material",
        entity_id=material.id,
        user=current_user(),
        machine=material.machine,
        site_id=material.site_id,
        metadata={"name": material.name, "quantity": material.quantity},
    )
    db.session.delete(material)
    db.session.commit()
    return "", 204
