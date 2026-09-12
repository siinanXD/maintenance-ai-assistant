"""Machine incident and downtime queries for the agent."""

from __future__ import annotations

from sqlalchemy import and_, or_

from app.models import ErrorEntry, Machine
from app.security import has_dashboard_permission
from app.services.ai_question_normalizer import normalize_text
from app.services.ai_structured_source_service import incident_source_cards, machine_source_card
from app.services.error_service import visible_errors_query
from app.services.visibility_query_service import visible_machines_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
)

MAX_GROUPS = 10


def machine_incident_report(user, *, machine=None):
    """Return incidents for one machine, or the downtime ranking across machines."""
    if not (
        has_dashboard_permission(user, "machines", "view")
        and has_dashboard_permission(user, "errors", "view")
    ):
        return denied_outcome("machines", "machines", "Maschinen und Fehlerkatalog")
    reference = str(machine or "").strip()
    if not reference:
        return _downtime_ranking(user)
    resolved = resolve_visible_machine(user, reference)
    if resolved is None:
        return QueryOutcome(
            entity_type="incidents",
            scope="machines",
            answer_markdown=(
                "## Stoerungen\n"
                f"- **Maschine:** {reference}\n"
                "- **Status:** Keine sichtbare Maschine mit diesem Namen gefunden\n"
                "- **Quelle:** Strukturierte Fehlerdaten"
            ),
            filters={"machine": reference},
            structured_context=build_structured_context("machines", machine=reference),
            query="machine_incidents",
        )
    return _machine_incidents(user, resolved)


def resolve_visible_machine(user, reference):
    """Return a visible machine by id, exact or partial name match (longest name wins)."""
    text = str(reference or "").strip()
    query = visible_machines_query(user)
    if text.isdigit():
        machine = query.filter(Machine.id == int(text)).first()
        if machine:
            return machine
    normalized = normalize_text(text)
    candidates = query.order_by(Machine.name.asc()).all()
    exact = [machine for machine in candidates if normalize_text(machine.name) == normalized]
    if exact:
        return exact[0]
    partial = [
        machine
        for machine in candidates
        if normalized
        and (
            normalized in normalize_text(machine.name) or normalize_text(machine.name) in normalized
        )
    ]
    if not partial:
        return None
    return max(partial, key=lambda item: len(item.name or ""))


def _machine_incidents(user, machine):
    """Return visible incidents for one resolved machine."""
    incidents = (
        visible_errors_query(user)
        .filter(
            or_(
                ErrorEntry.machine_id == machine.id,
                and_(ErrorEntry.machine_id.is_(None), ErrorEntry.machine.ilike(machine.name)),
            )
        )
        .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    lines = [
        f"## Stoerungen an {machine.name}",
        f"- **Anzahl:** {len(incidents)}",
        "- **Quelle:** Strukturierte Fehlerdaten",
    ]
    if not incidents:
        lines.extend(["", "Keine sichtbaren Stoerungen fuer diese Maschine gefunden."])
    else:
        lines.extend(["", "Sichtbare Treffer:"])
        for incident in incidents[:MAX_ANSWER_ITEMS]:
            lines.append(
                f"- #{incident.id} {incident.error_code} - {incident.title} "
                f"({incident.status}, {incident.severity})"
            )
        if len(incidents) > MAX_ANSWER_ITEMS:
            lines.append(f"- ... {len(incidents) - MAX_ANSWER_ITEMS} weitere passende Stoerungen")
    return QueryOutcome(
        entity_type="incidents",
        scope="machines",
        answer_markdown="\n".join(lines),
        count=len(incidents),
        items=[incident.to_dict() for incident in incidents],
        filters={"machine": machine.name},
        sources=_machine_and_incident_sources(machine, incidents),
        structured_context=build_structured_context(
            "machines", machine=machine.name, query="machine_incidents"
        ),
        extra={"machine": {"id": machine.id, "name": machine.name}},
        query="machine_incidents",
    )


def _downtime_ranking(user):
    """Return the visible machine group with the highest downtime sum."""
    incidents = (
        visible_errors_query(user)
        .filter(ErrorEntry.downtime_minutes > 0)
        .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
        .limit(200)
        .all()
    )
    visible_machines = {
        machine.id: machine
        for machine in visible_machines_query(user).order_by(Machine.name.asc()).all()
    }
    groups = {}
    for incident in incidents:
        machine = visible_machines.get(incident.machine_id)
        machine_name = machine.name if machine else incident.machine or "Unbekannte Maschine"
        key = ("id", incident.machine_id) if incident.machine_id else ("name", machine_name.lower())
        group = groups.setdefault(
            key,
            {
                "machine_id": incident.machine_id,
                "machine": machine_name,
                "machine_record": machine,
                "total_downtime_minutes": 0,
                "incident_count": 0,
                "examples": [],
            },
        )
        group["total_downtime_minutes"] += int(incident.downtime_minutes or 0)
        group["incident_count"] += 1
        if len(group["examples"]) < MAX_ANSWER_ITEMS:
            group["examples"].append(incident)
    ranked = sorted(
        groups.values(),
        key=lambda item: (
            -item["total_downtime_minutes"],
            -item["incident_count"],
            item["machine"],
        ),
    )
    top_group = ranked[0] if ranked else None
    supporting = top_group["examples"] if top_group else []
    lines = ["## Maschinenausfallzeit", "- **Quelle:** Strukturierte Fehlerdaten"]
    if not top_group:
        lines.append("- **Status:** Keine sichtbaren Stoerungen mit Ausfallzeit gefunden.")
    else:
        lines.extend(
            [
                f"- **Top-Maschine:** {top_group['machine']}",
                f"- **Ausfallzeit:** {top_group['total_downtime_minutes']} Minuten",
                f"- **Sichtbare Stoerungen:** {top_group['incident_count']}",
                "",
                "Sichtbare Beispiele:",
            ]
        )
        for incident in supporting[:MAX_ANSWER_ITEMS]:
            lines.append(
                f"- #{incident.id} {incident.error_code} - {incident.title} "
                f"({incident.downtime_minutes} Min.)"
            )
        if len(ranked) > 1:
            lines.extend(["", "Weitere Maschinen:"])
            for group in ranked[1:MAX_GROUPS]:
                lines.append(f"- {group['machine']}: {group['total_downtime_minutes']} Min.")
    return QueryOutcome(
        entity_type="machines",
        scope="machines",
        answer_markdown="\n".join(lines),
        count=len(incidents),
        items=[incident.to_dict() for incident in supporting],
        filters={"metric": "downtime_minutes"},
        sources=_machine_and_incident_sources(
            top_group.get("machine_record") if top_group else None, supporting
        ),
        structured_context=build_structured_context("machines", query="downtime"),
        extra={
            "aggregation": {
                "group_by": "machine",
                "top": _public_group(top_group),
                "groups": [_public_group(group) for group in ranked[:MAX_GROUPS]],
            }
        },
        query="downtime",
    )


def _machine_and_incident_sources(machine, incidents):
    """Return one machine source plus capped visible incident sources."""
    sources = []
    machine_source = machine_source_card(machine)
    if machine_source:
        sources.append(machine_source)
    sources.extend(incident_source_cards(incidents))
    return sources


def _public_group(group):
    """Return a prompt-safe downtime group payload."""
    if not group:
        return None
    return {
        "machine_id": group["machine_id"],
        "machine": group["machine"],
        "total_downtime_minutes": group["total_downtime_minutes"],
        "incident_count": group["incident_count"],
        "examples": [incident.to_dict() for incident in group["examples"]],
    }
