"""Inventory material queries for the agent."""

from __future__ import annotations

from sqlalchemy import func

from app.models import InventoryMaterial
from app.security import has_dashboard_permission
from app.services.ai_question_normalizer import normalize_text
from app.services.ai_structured_source_service import (
    inventory_source_cards,
    module_count_source_card,
)
from app.services.visibility_query_service import visible_inventory_materials_query

from .common import (
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
    format_structured_list_answer,
    machine_name,
)

FILTERS = {"all", "low_stock", "critical", "machine"}
CRITICAL_VALUES = {"critical", "kritisch", "high", "hoch"}


def list_inventory(user, *, filter="all", machine=None, count_only=False):
    """Return visible inventory materials for one filter, or the total count."""
    if not has_dashboard_permission(user, "inventory", "view"):
        return denied_outcome("inventory", "inventory", "Lager")
    inventory_filter = str(filter or "all").strip().lower()
    if inventory_filter not in FILTERS:
        raise ValueError(f"unsupported filter: {inventory_filter}")
    machine = str(machine or "").strip()
    if inventory_filter == "machine" and not machine:
        raise ValueError("machine is required for filter=machine")
    if count_only and inventory_filter == "all" and not machine:
        return _count(user)

    materials = _visible_materials(user)
    if inventory_filter == "low_stock":
        materials = [
            material
            for material in materials
            if material.min_quantity > 0 and material.quantity < material.min_quantity
        ]
        materials.sort(key=lambda item: (item.quantity - item.min_quantity, item.name))
        title = "Nachzubestellende Materialien"
    elif inventory_filter == "critical":
        materials = [
            material
            for material in materials
            if str(getattr(material, "criticality", "") or "").strip().lower() in CRITICAL_VALUES
        ]
        materials.sort(
            key=lambda item: (
                0 if str(item.criticality or "").lower() in {"critical", "kritisch"} else 1,
                item.name,
            )
        )
        title = "Kritische Materialien"
    elif inventory_filter == "machine":
        title = f"Teile zu {machine}"
    else:
        title = "Lagerartikel"
    if machine:
        materials = [
            material
            for material in materials
            if normalize_text(machine) in normalize_text(machine_name(material))
        ]
    materials = materials[:MAX_LIST_ITEMS]
    totals = _totals_for(materials)
    filters = {"filter": inventory_filter}
    if machine:
        filters["machine"] = machine
    query = (
        f"inventory_{inventory_filter}"
        if inventory_filter != "machine"
        else "inventory_machine_materials"
    )
    answer = format_structured_list_answer(
        title=title,
        label="sichtbare Lagerartikel",
        items=materials,
        count_label="Sichtbare Artikel",
        formatter=lambda material: (
            f"- {material.name}: Bestand {material.quantity}, "
            f"Mindestbestand {material.min_quantity}"
            f"{f', Maschine {machine_name(material)}' if machine_name(material) else ''}"
        ),
        source="Strukturierte Lagerdaten",
        overflow_suffix="weitere Artikel",
        empty_message="Keine sichtbaren Lagerartikel fuer diese Anfrage gefunden.",
    )
    if materials:
        answer = answer.replace(
            "- **Quelle:** Strukturierte Lagerdaten",
            f"- **Gesamtwert der Treffer:** {format_euro(totals['total_value'])}\n"
            "- **Quelle:** Strukturierte Lagerdaten",
            1,
        )
    return QueryOutcome(
        entity_type="inventory",
        scope="inventory",
        answer_markdown=answer,
        count=len(materials),
        items=[_material_payload(material) for material in materials],
        filters=filters,
        sources=inventory_source_cards(materials),
        structured_context=build_structured_context("inventory", query=query, machine=machine),
        extra={"totals": totals},
        query=query,
    )


def _count(user):
    """Return the visible inventory summary: positions, quantity, stock value, shortages."""
    query = visible_inventory_materials_query(user)
    totals = _totals_for_query(query)
    count = totals["positions"]
    source = module_count_source_card("inventory", count, user)
    return QueryOutcome(
        entity_type="inventory",
        scope="inventory",
        answer_markdown=(
            "## Lager\n"
            f"- **Sichtbare Artikel:** {count}\n"
            f"- **Gesamtmenge:** {totals['total_quantity']}\n"
            f"- **Lagerwert:** {format_euro(totals['total_value'])}\n"
            f"- **Unter Mindestbestand:** {totals['below_minimum']}\n"
            "- **Quelle:** Strukturierte Lagerdaten"
        ),
        count=count,
        filters={"filter": "all"},
        sources=[source] if source else [],
        structured_context=build_structured_context("inventory", query="inventory_count"),
        extra={"totals": totals},
        query="inventory_count",
    )


def _totals_for_query(query):
    """Return aggregate totals for a visible inventory query."""
    positions, quantity, value = query.with_entities(
        func.count(InventoryMaterial.id),
        func.coalesce(func.sum(InventoryMaterial.quantity), 0),
        func.coalesce(func.sum(InventoryMaterial.quantity * InventoryMaterial.unit_cost), 0.0),
    ).one()
    below_minimum = query.filter(
        InventoryMaterial.min_quantity > 0,
        InventoryMaterial.quantity < InventoryMaterial.min_quantity,
    ).count()
    return {
        "positions": int(positions or 0),
        "total_quantity": int(quantity or 0),
        "total_value": round(float(value or 0.0), 2),
        "below_minimum": int(below_minimum or 0),
    }


def _totals_for(materials):
    """Return aggregate totals for an in-memory material list."""
    return {
        "positions": len(materials),
        "total_quantity": int(sum(int(material.quantity or 0) for material in materials)),
        "total_value": round(sum(_material_value(material) for material in materials), 2),
        "below_minimum": sum(
            1
            for material in materials
            if material.min_quantity > 0 and material.quantity < material.min_quantity
        ),
    }


def _material_value(material):
    """Return quantity times unit cost for one material."""
    return float(material.quantity or 0) * float(material.unit_cost or 0.0)


def format_euro(value):
    """Return a German-formatted euro amount (1.234,56 EUR)."""
    text = f"{float(value or 0.0):,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + " EUR"


def _visible_materials(user):
    """Return visible inventory rows ordered for structured answers."""
    return (
        visible_inventory_materials_query(user)
        .order_by(InventoryMaterial.quantity.asc(), InventoryMaterial.name.asc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )


def _material_payload(material):
    """Return safe inventory material data."""
    return {
        "id": material.id,
        "name": material.name,
        "quantity": material.quantity,
        "min_quantity": material.min_quantity,
        "criticality": material.criticality,
        "lead_time_days": material.lead_time_days,
        "manufacturer": material.manufacturer,
        "machine_id": material.machine_id,
        "machine": machine_name(material),
        "unit_cost": float(material.unit_cost or 0.0),
        "stock_value": round(_material_value(material), 2),
        "is_below_minimum": material.min_quantity > 0 and material.quantity < material.min_quantity,
    }
