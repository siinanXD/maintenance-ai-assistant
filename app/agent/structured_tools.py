"""Parameter-driven structured tools (lists, counts, reports) for the agent.

These tools replace the former rule-based chat router. Each handler calls a
query core in ``app.agent.queries`` with explicit arguments and returns a
deterministic German ``answer_markdown`` next to compact items, public source
cards and a ``structured_context`` used for follow-ups and observability.
"""

from __future__ import annotations

from app.agent.tools import ToolResult, ToolSpec, compact_records, compact_sources, register_tool

STRUCTURED_TOOL_NAMES = frozenset(
    {
        "list_tasks",
        "list_incidents",
        "count_records",
        "list_employees",
        "list_employee_documents",
        "list_vacations",
        "list_documents",
        "list_shift_entries",
        "list_inventory",
        "list_maintenance_plans",
        "machine_incident_report",
    }
)


def outcome_result(outcome):
    """Convert a ``QueryOutcome`` into a ``ToolResult``."""
    if outcome.denied:
        return ToolResult(
            status="permission_denied",
            error="permission_denied",
            summary=outcome.summary(),
            content={
                "entity_type": outcome.entity_type,
                "answer_markdown": outcome.answer_markdown,
                "required_permission": [outcome.scope, "view"],
            },
            structured_context=dict(outcome.structured_context),
        )
    content = {
        "entity_type": outcome.entity_type,
        "query": outcome.query,
        "filters": dict(outcome.filters),
        "count": outcome.count,
        "items": compact_records(outcome.items),
        "answer_markdown": outcome.answer_markdown,
        "structured_context": dict(outcome.structured_context),
    }
    for key, value in (outcome.extra or {}).items():
        content.setdefault(key, value)
    return ToolResult(
        content=content,
        sources=compact_sources(outcome.sources),
        summary=outcome.summary(),
        structured_context=dict(outcome.structured_context),
    )


def _run(query_callable, user, arguments):
    """Run a query core and normalize argument errors into tool errors."""
    try:
        outcome = query_callable(user, **arguments)
    except ValueError as exc:
        return ToolResult(status="error", error=f"invalid_arguments:{exc}", summary=str(exc))
    return outcome_result(outcome)


def _bool(value):
    """Return a boolean for JSON-ish values."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _list_tasks(user, arguments):
    from app.agent.queries.tasks import list_tasks

    return _run(
        list_tasks,
        user,
        {
            "status": arguments.get("status"),
            "department": arguments.get("department"),
            "machine": arguments.get("machine"),
            "priority": arguments.get("priority"),
            "time_range": arguments.get("time_range"),
            "due": arguments.get("due"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _list_incidents(user, arguments):
    from app.agent.queries.incidents import list_incidents

    return _run(
        list_incidents,
        user,
        {
            "status": arguments.get("status"),
            "severity": arguments.get("severity"),
            "department": arguments.get("department"),
            "machine": arguments.get("machine"),
            "time_range": arguments.get("time_range"),
            "group_by": arguments.get("group_by"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _count_records(user, arguments):
    from app.agent.queries.counts import count_records

    return _run(count_records, user, {"scope": arguments.get("scope")})


def _list_employees(user, arguments):
    from app.agent.queries.employees import list_employees

    return _run(
        list_employees,
        user,
        {
            "department": arguments.get("department"),
            "availability": arguments.get("availability"),
            "role": arguments.get("role"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _list_employee_documents(user, arguments):
    from app.agent.queries.employee_documents import list_employee_documents

    return _run(
        list_employee_documents,
        user,
        {
            "mode": arguments.get("mode") or "employees_with_documents",
            "department": arguments.get("department"),
            "employee": arguments.get("employee"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _list_vacations(user, arguments):
    from app.agent.queries.vacations import list_vacations

    return _run(
        list_vacations,
        user,
        {
            "scope": arguments.get("scope") or "pending",
            "time_range": arguments.get("time_range"),
            "date_from": arguments.get("date_from"),
            "date_to": arguments.get("date_to"),
            "department": arguments.get("department"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _list_documents(user, arguments):
    from app.agent.queries.documents import list_documents

    return _run(
        list_documents,
        user,
        {
            "filter": arguments.get("filter") or "recent",
            "department": arguments.get("department"),
            "machine": arguments.get("machine"),
        },
    )


def _list_shift_entries(user, arguments):
    from app.agent.queries.shiftplans import list_shift_entries

    return _run(
        list_shift_entries,
        user,
        {
            "mode": arguments.get("mode") or "entries",
            "date": arguments.get("date"),
            "time_range": arguments.get("time_range"),
            "shift": arguments.get("shift"),
        },
    )


def _list_maintenance_plans(user, arguments):
    from app.agent.queries.maintenance import list_maintenance_plans

    return _run(
        list_maintenance_plans,
        user,
        {
            "due_state": arguments.get("due_state"),
            "kind": arguments.get("kind"),
            "machine": arguments.get("machine"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _list_inventory(user, arguments):
    from app.agent.queries.inventory import list_inventory

    return _run(
        list_inventory,
        user,
        {
            "filter": arguments.get("filter") or "all",
            "machine": arguments.get("machine"),
            "count_only": _bool(arguments.get("count_only")),
        },
    )


def _machine_incident_report(user, arguments):
    from app.agent.queries.machines import machine_incident_report

    return _run(machine_incident_report, user, {"machine": arguments.get("machine")})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_STATUS = {
    "type": "string",
    "enum": ["open", "in_progress", "done"],
    "description": "Statusfilter.",
}
_DEPARTMENT = {"type": "string", "description": "Abteilung, z. B. Produktion."}
_MACHINE = {"type": "string", "description": "Maschinenname oder -teil des Namens."}
_COUNT_ONLY = {
    "type": "boolean",
    "description": "true liefert nur die Anzahl statt einer Liste.",
}

register_tool(
    ToolSpec(
        name="list_tasks",
        label="Tasks",
        description=(
            "Listet oder zaehlt sichtbare Wartungs-Tasks mit Filtern: Status, Abteilung, "
            "Maschine, Prioritaet (urgent), Zeitraum (heute/gestern angelegt oder "
            "abgeschlossen) und Faelligkeit (heute faellig, ueberfaellig). Fuer "
            "Fragen wie 'Wie viele offenen Tasks gibt es?' oder 'Welche Tasks stehen heute an?'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": _STATUS,
                "department": _DEPARTMENT,
                "machine": _MACHINE,
                "priority": {"type": "string", "enum": ["urgent"], "description": "Nur dringende."},
                "time_range": {
                    "type": "string",
                    "enum": ["today", "yesterday"],
                    "description": "Angelegt (bzw. bei done: abgeschlossen) heute oder gestern.",
                },
                "due": {
                    "type": "string",
                    "enum": ["today", "overdue"],
                    "description": "Faelligkeit: heute faellig oder ueberfaellig.",
                },
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_tasks,
        permission=("tasks", "view"),
        scopes=("tasks",),
    )
)

register_tool(
    ToolSpec(
        name="list_incidents",
        label="Stoerungen",
        description=(
            "Listet oder zaehlt sichtbare Stoerungen aus dem Fehlerkatalog mit Filtern: "
            "Status, Schwere (critical), Abteilung, Maschine, Zeitraum (heute/gestern). "
            "group_by=machine liefert die Maschine mit den meisten Stoerungen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": _STATUS,
                "severity": {
                    "type": "string",
                    "enum": ["critical"],
                    "description": "Nur kritische.",
                },
                "department": _DEPARTMENT,
                "machine": _MACHINE,
                "time_range": {
                    "type": "string",
                    "enum": ["today", "yesterday"],
                    "description": "Gemeldet (bzw. bei done: geschlossen) heute oder gestern.",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["machine"],
                    "description": "Aggregation: Stoerungen je Maschine (Top-Maschine).",
                },
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_incidents,
        permission=("errors", "view"),
        scopes=("errors",),
    )
)

register_tool(
    ToolSpec(
        name="count_records",
        label="Anzahl",
        description=(
            "Zaehlt sichtbare Datensaetze eines Bereichs: tasks, errors (Stoerungen), "
            "machines, inventory (Lagerartikel), documents, shiftplans, employees "
            "(Mitarbeiter) oder admin_users (Nutzerkonten). Bei mehreren Bereichen pro "
            "Bereich einmal aufrufen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": [
                        "tasks",
                        "errors",
                        "machines",
                        "inventory",
                        "documents",
                        "shiftplans",
                        "employees",
                        "admin_users",
                    ],
                    "description": "Bereich, der gezaehlt wird.",
                },
            },
            "required": ["scope"],
        },
        handler=_count_records,
        scopes=(),
    )
)

register_tool(
    ToolSpec(
        name="list_employees",
        label="Mitarbeiter",
        description=(
            "Listet oder zaehlt sichtbare Mitarbeiter, optional je Abteilung, oder liefert "
            "Verfuegbarkeit: heute verfuegbar, heute abwesend, morgen abwesend (genehmigter "
            "Urlaub). role=team_lead beantwortet Teamleiter-Fragen (kein Feld vorhanden)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "department": _DEPARTMENT,
                "availability": {
                    "type": "string",
                    "enum": ["available_today", "absent_today", "absent_tomorrow"],
                    "description": "Verfuegbarkeitsfilter.",
                },
                "role": {"type": "string", "enum": ["team_lead"], "description": "Rolle."},
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_employees,
        permission=("employees", "view"),
        scopes=("employees",),
    )
)

register_tool(
    ToolSpec(
        name="list_employee_documents",
        label="Mitarbeiterdokumente",
        description=(
            "Mitarbeiter mit hinterlegten Personaldokumenten (mode=employees_with_documents) "
            "oder die hinterlegten Dokument-Dateien selbst (mode=stored_documents), optional "
            "je Abteilung oder fuer einen Mitarbeiter (Name)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["employees_with_documents", "stored_documents"],
                    "description": "Was gelistet wird.",
                },
                "department": _DEPARTMENT,
                "employee": {"type": "string", "description": "Mitarbeitername oder ID."},
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_employee_documents,
        permission=("employees", "view"),
        scopes=("employees",),
    )
)

register_tool(
    ToolSpec(
        name="list_vacations",
        label="Urlaub",
        description=(
            "Urlaubsantraege und Abwesenheiten: scope=pending (offene Antraege), "
            "own_pending (eigene offene Antraege), own_latest (Status des eigenen letzten "
            "Antrags), absences (genehmigte Abwesenheiten morgen, naechste Woche oder in "
            "einem Datumsbereich, optional je Abteilung)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["pending", "own_pending", "own_latest", "absences"],
                    "description": "Abfragebereich.",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["tomorrow", "next_week"],
                    "description": "Relativer Zeitraum fuer absences.",
                },
                "date_from": {"type": "string", "description": "Start (YYYY-MM-DD)."},
                "date_to": {"type": "string", "description": "Ende (YYYY-MM-DD)."},
                "department": _DEPARTMENT,
                "count_only": _COUNT_ONLY,
            },
            "required": ["scope"],
        },
        handler=_list_vacations,
        scopes=("employees",),
    )
)

register_tool(
    ToolSpec(
        name="list_documents",
        label="Dokumente",
        description=(
            "Dokument-Metadaten: filter=recent (zuletzt geaendert), outdated (veraltet), "
            "this_week (diese Woche erstellt), department (je Abteilung), machine (je "
            "Maschine). Fuer Dokumentinhalte search_knowledge nutzen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["recent", "outdated", "this_week", "department", "machine", "all"],
                    "description": "Metadaten-Filter.",
                },
                "department": _DEPARTMENT,
                "machine": _MACHINE,
            },
            "required": ["filter"],
        },
        handler=_list_documents,
        permission=("documents", "view"),
        scopes=("documents",),
    )
)

register_tool(
    ToolSpec(
        name="list_shift_entries",
        label="Schichtplan",
        description=(
            "Schichtplanung aus veroeffentlichten Plaenen: mode=entries (wer ist an einem "
            "Datum bzw. morgen eingeplant, optional je Schicht), count (eingeplante "
            "Mitarbeiter je Schicht), understaffed (unterbesetzte Schichten naechste Woche)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["entries", "count", "understaffed"],
                    "description": "Abfrageart.",
                },
                "date": {"type": "string", "description": "Datum (YYYY-MM-DD)."},
                "time_range": {
                    "type": "string",
                    "enum": ["today", "tomorrow"],
                    "description": "Relatives Datum, Standard morgen.",
                },
                "shift": {
                    "type": "string",
                    "enum": ["early", "late", "night"],
                    "description": "Schicht: early=Frueh, late=Spaet, night=Nacht.",
                },
            },
            "required": [],
        },
        handler=_list_shift_entries,
        permission=("shiftplans", "view"),
        scopes=("shiftplans",),
    )
)

register_tool(
    ToolSpec(
        name="list_inventory",
        label="Lager",
        description=(
            "Lagerartikel: filter=all, low_stock (unter Mindestbestand, nachbestellen), "
            "critical (kritische Teile), machine (Teile einer Maschine). count_only "
            "liefert die Lagerzusammenfassung: Anzahl Artikel, Gesamtmenge, Lagerwert "
            "(Gesamtwert in EUR) und Artikel unter Mindestbestand."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["all", "low_stock", "critical", "machine"],
                    "description": "Lagerfilter.",
                },
                "machine": _MACHINE,
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_inventory,
        permission=("inventory", "view"),
        scopes=("inventory",),
    )
)

register_tool(
    ToolSpec(
        name="list_maintenance_plans",
        label="Prüfungen und Wartung",
        description=(
            "Aktive Prüfpflichten (z. B. DGUV V3) und Wartungspläne nach Fälligkeit. "
            "due_state=overdue (überfällig), due_soon (in 30 Tagen), ok; "
            "kind=inspection oder maintenance; optional machine."
        ),
        parameters={
            "type": "object",
            "properties": {
                "due_state": {
                    "type": "string",
                    "enum": ["overdue", "due_soon", "ok"],
                    "description": "Fälligkeit.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["inspection", "maintenance"],
                    "description": "inspection=Prüfpflicht, maintenance=Wartung.",
                },
                "machine": _MACHINE,
                "count_only": _COUNT_ONLY,
            },
            "required": [],
        },
        handler=_list_maintenance_plans,
        permission=("machines", "view"),
        scopes=("machines",),
    )
)

register_tool(
    ToolSpec(
        name="machine_incident_report",
        label="Maschinenstoerungen",
        description=(
            "Stoerungen einer bestimmten Maschine (machine angeben) oder ohne machine das "
            "Ranking der Maschinen nach Ausfallzeit (Downtime)."
        ),
        parameters={
            "type": "object",
            "properties": {"machine": _MACHINE},
            "required": [],
        },
        handler=_machine_incident_report,
        permission=("machines", "view"),
        extra_permissions=(("errors", "view"),),
        scopes=("machines", "errors"),
    )
)
