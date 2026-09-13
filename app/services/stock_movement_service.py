"""Spare-part withdrawals for work orders, goods receipts and reorder suggestions."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import InventoryMaterial, InventoryMovement
from app.security import has_dashboard_permission
from app.services.operations_tracking_service import record_event

REASON_WITHDRAWAL = "withdrawal"
REASON_RECEIPT = "receipt"
CONSUMPTION_WINDOW_DAYS = 90
CRITICALITY_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def parse_quantity(value):
    """Return a positive whole quantity or raise ``ValueError``."""
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("quantity must be a whole number") from exc
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    return quantity


def task_materials(task, user):
    """Return the parts withdrawn for a work order and their total value."""
    if not has_dashboard_permission(user, "inventory", "view"):
        return None, {"error": "Keine Berechtigung fuer das Lager"}, 403
    movements = (
        InventoryMovement.query.filter_by(task_id=task.id)
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .all()
    )
    items = [movement.to_dict() for movement in movements]
    return (
        {"items": items, "total_value": round(sum(item["value"] for item in items), 2)},
        None,
        200,
    )


def withdraw_for_task(task, data, user):
    """Take parts out of stock for a work order.

    Needs write access to the task (checked by the route) and read access to
    the inventory. The stock never goes below zero.
    """
    if not has_dashboard_permission(user, "inventory", "view"):
        return None, {"error": "Keine Berechtigung fuer das Lager"}, 403
    if task.status.value in {"done", "cancelled"}:
        return None, {"error": "Material kann nur fuer offene Auftraege gebucht werden"}, 409
    try:
        material_id = int(data.get("material_id"))
    except (TypeError, ValueError):
        return None, {"error": "material_id is required"}, 400
    try:
        quantity = parse_quantity(data.get("quantity"))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400
    material = db.session.get(InventoryMaterial, material_id, with_for_update=True)
    if material is None:
        return None, {"error": "Material nicht gefunden"}, 404
    if material.quantity < quantity:
        return (
            None,
            {"error": f"Nur noch {material.quantity} Stück von {material.name} auf Lager"},
            409,
        )

    material.quantity -= quantity
    movement = InventoryMovement(
        material=material,
        task=task,
        quantity_change=-quantity,
        reason=REASON_WITHDRAWAL,
        note=str(data.get("note") or "").strip()[:200],
        user_id=user.id,
    )
    db.session.add(movement)
    record_event(
        "inventory.withdrawn",
        "inventory",
        entity_type="inventory_material",
        entity_id=material.id,
        task=task,
        user=user,
        machine_id=material.machine_id,
        metadata={"quantity": quantity, "remaining": material.quantity},
        description=f"Material entnommen: {quantity}x {material.name}",
    )
    db.session.commit()
    return movement, None, 201


def book_receipt(material, data, user):
    """Add delivered parts to stock (goods receipt)."""
    try:
        quantity = parse_quantity(data.get("quantity"))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400
    material.quantity += quantity
    movement = InventoryMovement(
        material=material,
        quantity_change=quantity,
        reason=REASON_RECEIPT,
        note=str(data.get("note") or "").strip()[:200],
        user_id=user.id,
    )
    db.session.add(movement)
    record_event(
        "inventory.received",
        "inventory",
        entity_type="inventory_material",
        entity_id=material.id,
        user=user,
        machine_id=material.machine_id,
        metadata={"quantity": quantity, "stock": material.quantity},
        description=f"Wareneingang: {quantity}x {material.name}",
    )
    db.session.commit()
    return movement, None, 201


def material_movements(material, limit=50):
    """Return the latest stock movements of one material."""
    movements = (
        InventoryMovement.query.filter_by(material_id=material.id)
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .limit(limit)
        .all()
    )
    return [movement.to_dict() for movement in movements]


def reorder_suggestions():
    """Return materials at or below their minimum stock with an order proposal.

    The proposed quantity refills to twice the minimum and covers the parts
    consumed during the supplier lead time, based on the last 90 days.
    """
    since = datetime.now(UTC) - timedelta(days=CONSUMPTION_WINDOW_DAYS)
    consumption = dict(
        db.session.query(
            InventoryMovement.material_id, func.sum(-InventoryMovement.quantity_change)
        )
        .filter(
            InventoryMovement.reason == REASON_WITHDRAWAL,
            InventoryMovement.created_at >= since,
        )
        .group_by(InventoryMovement.material_id)
        .all()
    )
    materials = InventoryMaterial.query.filter(
        InventoryMaterial.min_quantity > 0,
        InventoryMaterial.quantity <= InventoryMaterial.min_quantity,
    ).all()
    items = []
    for material in materials:
        used = int(consumption.get(material.id) or 0)
        daily_use = used / CONSUMPTION_WINDOW_DAYS
        lead_time_need = round(daily_use * (material.lead_time_days or 0))
        order_quantity = max(material.min_quantity * 2 - material.quantity + lead_time_need, 1)
        items.append(
            {
                "material": material.to_dict(),
                "used_last_90_days": used,
                "order_quantity": order_quantity,
                "order_value": round(order_quantity * (material.unit_cost or 0), 2),
            }
        )
    items.sort(
        key=lambda item: (
            CRITICALITY_RANK.get(item["material"]["criticality"], 2),
            item["material"]["quantity"] - item["material"]["min_quantity"],
            item["material"]["name"].lower(),
        )
    )
    return {
        "items": items,
        "count": len(items),
        "total_value": round(sum(item["order_value"] for item in items), 2),
    }
