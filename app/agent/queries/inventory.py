"""Inventory material queries for the agent."""

from __future__ import annotations

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
    filters = {"filter": inventory_filter}
    if machine:
        filters["machine"] = machine
    query = (
        f"inventory_{inventory_filter}"
        if inventory_filter != "machine"
        else "inventory_machine_materials"
    )
    return QueryOutcome(
        entity_type="inventory",
        scope="inventory",
        answer_markdown=format_structured_list_answer(
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
        ),
        count=len(materials),
        items=[_material_payload(material) for material in materials],
        filters=filters,
        sources=inventory_source_cards(materials),
        structured_context=build_structured_context("inventory", query=query, machine=machine),
        query=query,
    )


def _count(user):
    """Return the visible inventory material count."""
    count = visible_inventory_materials_query(user).count()
    source = module_count_source_card("inventory", count, user)
    return QueryOutcome(
        entity_type="inventory",
        scope="inventory",
        answer_markdown=(
            "## Lager\n"
            f"- **Sichtbare Artikel:** {count}\n"
            "- **Quelle:** Strukturierte Lagerdaten"
        ),
        count=count,
        filters={"filter": "all"},
        sources=[source] if source else [],
        structured_context=build_structured_context("inventory", query="inventory_count"),
        query="inventory_count",
    )


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
        "is_below_minimum": material.min_quantity > 0 and material.quantity < material.min_quantity,
    }
