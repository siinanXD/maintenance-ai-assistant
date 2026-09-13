"""Inventory service helpers."""

import re
import unicodedata

from app.models import InventoryMaterial, Machine
from app.services.task_service import prioritize_visible_tasks


def forecast_inventory_risks(data, user):
    """Return spare-part risk forecasts for visible tasks and inventory."""
    try:
        threshold = parse_low_stock_threshold(data.get("low_stock_threshold", 5))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    priorities, error, status = prioritize_visible_tasks(data, user)
    if error:
        return None, error, status

    machines = Machine.query.order_by(Machine.name.asc()).all()
    materials_by_machine = _materials_by_machine()
    items = []
    unmatched_tasks = []

    for priority in priorities:
        task = priority["task"]
        machine, match_reason = _match_machine_with_reason(task, machines)
        if not machine:
            if _is_high_priority(priority):
                unmatched_tasks.append(_unmatched_task_payload(priority))
            continue

        for material in materials_by_machine.get(machine.id, []):
            risk_level = _inventory_risk_level(material, priority, threshold)
            if not risk_level:
                continue
            items.append(
                _forecast_item_payload(
                    material,
                    machine,
                    priority,
                    risk_level,
                    threshold,
                    match_reason,
                )
            )

    items.sort(key=lambda item: (_risk_rank(item["risk_level"]), item["quantity"]))
    return (
        {
            "items": items,
            "unmatched_tasks": unmatched_tasks,
            "summary": _forecast_summary(items),
        },
        None,
        200,
    )


def parse_low_stock_threshold(value):
    """Parse and validate the forecast low-stock threshold."""
    try:
        threshold = int(value if value not in (None, "") else 5)
    except (TypeError, ValueError) as exc:
        raise ValueError("low_stock_threshold must be a non-negative integer") from exc
    if threshold < 0:
        raise ValueError("low_stock_threshold must be a non-negative integer")
    return threshold


def _materials_by_machine():
    """Return inventory materials grouped by linked machine id."""
    grouped = {}
    materials = InventoryMaterial.query.order_by(InventoryMaterial.name.asc()).all()
    for material in materials:
        if not material.machine_id:
            continue
        grouped.setdefault(material.machine_id, []).append(material)
    return grouped


def _match_machine_with_reason(task, machines):
    """Return the best matching machine and a short explanation."""
    task_text = " ".join(
        [
            str(task.get("title") or ""),
            str(task.get("description") or ""),
        ]
    )
    normalized_task_text = _normalize_match_text(task_text)
    task_tokens = set(normalized_task_text.split())

    for machine in machines:
        match_reason = _machine_match_reason(machine, normalized_task_text, task_tokens)
        if match_reason:
            return machine, match_reason
    return None, ""


def _normalize_match_text(value):
    """Normalize text for tolerant machine matching."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _machine_aliases(machine):
    """Return normalized name and produced-item aliases for a machine."""
    aliases = []
    for value in (machine.name, machine.produced_item):
        normalized = _normalize_match_text(value)
        if normalized:
            aliases.append(normalized)
            without_trailing_number = re.sub(r"\s+\d+$", "", normalized).strip()
            if without_trailing_number and without_trailing_number != normalized:
                aliases.append(without_trailing_number)
    return aliases


def _machine_match_reason(machine, normalized_task_text, task_tokens):
    """Return why a task matched a machine or an empty string."""
    for alias in _machine_aliases(machine):
        if alias and alias in normalized_task_text:
            return f"Treffer ueber Maschinen-/Produktname: {alias}"

    machine_tokens = set(_normalize_match_text(machine.name).split())
    meaningful_tokens = {
        token for token in machine_tokens if len(token) >= 3 and not token.isdigit()
    }
    numeric_tokens = {token for token in machine_tokens if token.isdigit()}
    shared_tokens = meaningful_tokens & task_tokens
    shared_numbers = numeric_tokens & task_tokens
    if len(shared_tokens) >= 2:
        return "Treffer ueber Teilnamen: " + ", ".join(sorted(shared_tokens))
    if shared_tokens and shared_numbers:
        return "Treffer ueber Teilname und Nummer"
    return ""


def _is_high_priority(priority):
    """Return whether a task priority should be reported as unmatched."""
    return priority.get("risk_level") in {"high", "critical"} or priority.get("score", 0) >= 65


def _inventory_risk_level(material, priority, threshold):
    """Return the material risk level for a prioritized task."""
    quantity = material.quantity or 0
    risk_level = priority.get("risk_level")
    if quantity == 0:
        return "critical"
    if quantity <= threshold and risk_level in {"high", "critical"}:
        return "high"
    if quantity <= threshold * 2 and risk_level in {"medium", "high", "critical"}:
        return "medium"
    return None


def _forecast_item_payload(material, machine, priority, risk_level, threshold, match_reason):
    """Return a serialized forecast warning item."""
    return {
        "machine": machine.to_dict(),
        "material": material.to_dict(),
        "quantity": material.quantity,
        "task": priority["task"],
        "score": priority["score"],
        "risk_level": risk_level,
        "match_reason": match_reason,
        "reason": _forecast_reason(material, priority, risk_level, threshold),
        "recommended_action": _forecast_action(risk_level),
    }


def _forecast_reason(material, priority, risk_level, threshold):
    """Return a German explanation for one forecast warning."""
    if risk_level == "critical":
        return f"{material.name} ist nicht mehr auf Lager."
    if risk_level == "high":
        return (
            f"{material.name} liegt bei {material.quantity} Stueck und damit "
            f"unter oder auf dem Mindestbestand {threshold}; Task-Risiko "
            f"{priority['risk_level']}."
        )
    return (
        f"{material.name} liegt bei {material.quantity} Stueck und der "
        f"verknuepfte Task ist mit {priority['risk_level']} bewertet."
    )


def _forecast_action(risk_level):
    """Return the recommended inventory action for a risk level."""
    actions = {
        "critical": "Sofort Ersatzteil pruefen und Nachbestellung ausloesen.",
        "high": "Nachbestellung vorbereiten und Task vor Arbeitsbeginn pruefen.",
        "medium": "Bestand beobachten und Material fuer den Task reservieren.",
    }
    return actions[risk_level]


def _unmatched_task_payload(priority):
    """Return a high-risk task without recognized machine reference."""
    return {
        "task": priority["task"],
        "score": priority["score"],
        "risk_level": priority["risk_level"],
        "reason": priority["reason"],
        "recommended_action": "Maschinenbezug im Task pruefen oder ergaenzen.",
    }


def _forecast_summary(items):
    """Return aggregate warning counts for forecast items."""
    summary = {"critical": 0, "high": 0, "medium": 0, "total": len(items)}
    for item in items:
        if item["risk_level"] in summary:
            summary[item["risk_level"]] += 1
    return summary


def _risk_rank(risk_level):
    """Return a sorting rank for forecast risk levels."""
    ranks = {"critical": 0, "high": 1, "medium": 2}
    return ranks.get(risk_level, 3)
