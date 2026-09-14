"""Filtered incident lists, counts and machine aggregation for the agent."""

from __future__ import annotations

from app.models import Department, ErrorEntry
from app.security import has_dashboard_permission
from app.services.ai_structured_source_service import (
    incident_source_cards,
    incident_source_cards_from_payloads,
)
from app.services.error_service import visible_errors_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    aggregate_or_row_sources,
    build_structured_context,
    denied_outcome,
    filter_summary,
    today_bounds,
    yesterday_bounds,
)

FILTER_KEYS = ("department", "status", "time_range", "machine", "severity")


def list_incidents(
    user,
    *,
    status=None,
    severity=None,
    department=None,
    machine=None,
    time_range=None,
    group_by=None,
    count_only=False,
):
    """Return visible incidents matching explicit filters, optionally grouped by machine."""
    if not has_dashboard_permission(user, "errors", "view"):
        return denied_outcome("incidents", "errors", "Fehlerkatalog")
    filters = {}
    for key, value in (
        ("status", status),
        ("severity", severity),
        ("department", department),
        ("machine", machine),
        ("time_range", time_range),
    ):
        text = str(value or "").strip()
        if text:
            filters[key] = text.lower() if key != "department" and key != "machine" else text
    if str(group_by or "").strip().lower() == "machine":
        return _machine_aggregation(user, filters)

    query = _filtered_incident_query(user, filters)
    count = query.count()
    incidents = _ordered_incidents(query, filters).limit(MAX_LIST_ITEMS).all()
    return QueryOutcome(
        entity_type="incidents",
        scope="errors",
        answer_markdown=_format_answer(count, incidents, filters, count_only),
        count=count,
        items=[incident.to_dict() for incident in incidents],
        filters=filters,
        sources=aggregate_or_row_sources(incident_source_cards(incidents), "errors", count, user),
        structured_context=_structured_context(filters),
        query="count" if count_only else "list",
    )


def _machine_aggregation(user, filters):
    """Return the machine with the most visible incident records."""
    query = _filtered_incident_query(user, filters)
    incidents = query.order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc()).all()
    groups = _incident_machine_groups(incidents)
    top_group = groups[0] if groups else None
    sources = aggregate_or_row_sources(
        incident_source_cards_from_payloads(top_group["examples"] if top_group else []),
        "errors",
        len(incidents),
        user,
    )
    return QueryOutcome(
        entity_type="incidents",
        scope="errors",
        answer_markdown=_format_machine_aggregation_answer(top_group, groups, filters),
        count=len(incidents),
        items=top_group["examples"] if top_group else [],
        filters={**filters, "group_by": "machine"},
        sources=sources,
        structured_context=_structured_context(filters),
        extra={
            "aggregation": {
                "group_by": "machine",
                "top": top_group,
                "groups": groups[:MAX_ANSWER_ITEMS],
            }
        },
        query="group_by_machine",
    )


def _filtered_incident_query(user, filters):
    """Return visible incidents filtered by explicit structured filters."""
    query = visible_errors_query(user)
    status = filters.get("status")
    if status:
        query = query.filter(ErrorEntry.status == ("closed" if status == "done" else status))
    if filters.get("department"):
        query = query.filter(ErrorEntry.department.has(Department.name == filters["department"]))
    if filters.get("severity") == "critical":
        query = query.filter(ErrorEntry.severity == "critical")
    if filters.get("machine"):
        query = query.filter(ErrorEntry.machine.ilike(f"%{filters['machine']}%"))
    if filters.get("time_range") in {"today", "yesterday"}:
        start_at, end_at = (
            today_bounds() if filters["time_range"] == "today" else yesterday_bounds()
        )
        if status == "done":
            query = query.filter(ErrorEntry.closed_at >= start_at, ErrorEntry.closed_at < end_at)
        else:
            query = query.filter(ErrorEntry.created_at >= start_at, ErrorEntry.created_at < end_at)
    return query


def _ordered_incidents(query, filters):
    """Return the incident query ordered for stable answers."""
    if filters.get("status") == "done":
        return query.order_by(ErrorEntry.closed_at.desc(), ErrorEntry.id.desc())
    return query.order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())


def _structured_context(filters):
    """Return the persisted structured memory payload."""
    return build_structured_context(
        "incidents",
        department=filters.get("department"),
        status=filters.get("status"),
        time_range=filters.get("time_range"),
        machine=filters.get("machine"),
    )


def _format_answer(count, incidents, filters, count_only):
    """Return a compact German incident answer."""
    lines = [
        "## Stoerungen",
        f"- **Anzahl:** {count}",
        f"- **Filter:** {filter_summary(filters, FILTER_KEYS)}",
        "- **Quelle:** Strukturierte Daten",
    ]
    if count == 0:
        lines.append("")
        lines.append("Keine passenden sichtbaren Eintraege gefunden.")
        return "\n".join(lines)
    if count_only:
        return "\n".join(lines)
    lines.append("")
    lines.append("Sichtbare Treffer:")
    for incident in incidents[:MAX_ANSWER_ITEMS]:
        department_name = incident.department.name if incident.department else "ohne Bereich"
        lines.append(
            f"- #{incident.id} {incident.title} "
            f"({incident.status}, {incident.severity}, {department_name})"
        )
    if count > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {count - MAX_ANSWER_ITEMS} weitere passende Eintraege")
    return "\n".join(lines)


def _incident_machine_groups(incidents):
    """Return visible incident groups keyed by machine identity."""
    groups = {}
    for incident in incidents:
        machine_name = incident.machine or "Unbekannte Maschine"
        key = (incident.machine_id or "", machine_name)
        group = groups.setdefault(
            key,
            {
                "machine_id": incident.machine_id,
                "machine": machine_name,
                "count": 0,
                "examples": [],
            },
        )
        group["count"] += 1
        if len(group["examples"]) < 5:
            group["examples"].append(incident.to_dict())
    return sorted(groups.values(), key=lambda item: (-item["count"], item["machine"]))


def _format_machine_aggregation_answer(top_group, groups, filters):
    """Return a compact German incident aggregation answer."""
    lines = [
        "## Stoerungen nach Maschine",
        f"- **Filter:** {filter_summary(filters, FILTER_KEYS)}",
        "- **Quelle:** Strukturierte Fehlerdaten",
    ]
    if not top_group:
        lines.append("- **Status:** Keine passenden sichtbaren Stoerungen gefunden.")
        return "\n".join(lines)
    lines.extend(
        [
            f"- **Top-Maschine:** {top_group['machine']}",
            f"- **Anzahl:** {top_group['count']}",
            "",
            "Sichtbare Beispiele:",
        ]
    )
    for incident in top_group["examples"][:MAX_ANSWER_ITEMS]:
        lines.append(
            f"- #{incident['id']} {incident['error_code']} - {incident['title']} "
            f"({incident['status']}, {incident['severity']})"
        )
    if len(groups) > 1:
        lines.append("")
        lines.append("Weitere Maschinen:")
        for group in groups[1:MAX_ANSWER_ITEMS]:
            lines.append(f"- {group['machine']}: {group['count']}")
    return "\n".join(lines)
