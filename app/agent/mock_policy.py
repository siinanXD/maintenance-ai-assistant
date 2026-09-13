"""Deterministic tool-selection policy for the mock provider.

Keeps the agent loop fully testable offline: the policy picks tools and
explicit arguments from the last user message with simple German keyword
rules and, once tool results are present, composes a short grounded answer
from them. It never invents data.

Structured intents (filtered lists and counts) select the parameterized
``list_*``/``count_records`` tools whenever they exist in the registry, even
when the user lacks the permission: the tool runner then returns the standard
permission-denied answer instead of silently searching elsewhere.
"""

from __future__ import annotations

import json
import re

from app.agent.tools import TOOL_REGISTRY
from app.services.ai_question_normalizer import (
    TASK_STATUS_TERMS,
    detect_department,
    detect_severity,
    detect_status,
    detect_time_range,
    is_structured_follow_up,
    normalize_text,
)

MAX_CALLS_PER_TURN = 4
ERROR_CODE_PATTERN = re.compile(r"\b[A-Z]{1,6}[-_ ]?\d{2,6}\b", re.IGNORECASE)
MACHINE_PATTERN = re.compile(
    r"\b(?:maschine|anlage|presse|linie|station|roboter|ofen)\s+([A-Za-z0-9][\w-]*)",
    re.IGNORECASE,
)
MACHINE_REFERENCE_PATTERN = re.compile(
    r"\b((?i:maschine|anlage|presse|linie|station|roboter|ofen)"
    r"(?:\s+(?:[A-Za-z]*\d[\w-]*|[A-Z][\w-]*))?(?:\s+\d+)?)"
)
QUANTITY_PATTERN = re.compile(r"\b(\d{1,7})\s*(?:stueck|stück|stk)\b", re.IGNORECASE)
IDENTIFIER_PATTERN = re.compile(r"#\s?\d+")
ISO_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
STRUCTURED_HINT_PATTERN = re.compile(
    r"\[structured_context\] Letzter Datenbereich dieser Sitzung:[^\n]*"
)
CREATE_TASK_TERMS = ("task anlegen", "aufgabe anlegen", "task erstellen", "aufgabe erstellen")
DRAFT_TERMS = ("entwurf", "vorschlag", "vorschlagen")
GENERAL_TERMS = ("hallo", "guten tag", "danke", "wer bist du", "was kannst du", "hilfe")
COUNT_TERMS = ("wie viele", "wieviele", "anzahl", "wie viel", "zaehl")
VALUE_TERMS = ("gesamtwert", "lagerwert", "bestandswert", "wert des", "wie viel wert", "kosten")
LIST_TERMS = (
    "welche",
    "zeige",
    "zeig ",
    "liste",
    "auflisten",
    "gib mir",
    "alle ",
    "gibt es",
    "was gibt",
    "wer ist",
    "wer sind",
    "wer hat",
    "wer fehlt",
    "wer ",
)
KEYWORD_TOOLS = (
    (("reindex", "neu indexieren", "reindexieren"), "request_knowledge_reindex"),
    (("priorisier", "prioritaet", "rangfolge"), "prioritize_tasks"),
    (("briefing", "tagesueberblick"), "daily_briefing"),
)
COUNT_SCOPE_TERMS = (
    ("tasks", ("task", "aufgabe", "todo")),
    ("errors", ("stoerung", "fehler", "incident", "problem")),
    ("machines", ("maschine", "anlage")),
    ("inventory", ("lager", "bestand", "material", "ersatzteil", "artikel")),
    ("documents", ("dokument", "bericht", "protokoll")),
    ("shiftplans", ("schichtplan", "schichtplaene")),
    ("admin_users", ("admin", "administrator")),
)
SHIFT_TERMS = (("frueh", "early"), ("spaet", "late"), ("nacht", "night"))
# Whole words only: "Hydraulikpruefung" is a knowledge question, not an inspection plan.
INSPECTION_PATTERN = re.compile(
    r"\b(pruefungen|pruefpflicht\w*|wartungsplaene?|dguv|inspektion\w*)\b"
)
ENTITY_TOOLS = {
    "tasks": "list_tasks",
    "incidents": "list_incidents",
    "employees": "list_employees",
    "employee_documents": "list_employee_documents",
    "vacations": "list_vacations",
    "documents": "list_documents",
    "shiftplans": "list_shift_entries",
    "inventory": "list_inventory",
    "maintenance_plans": "list_maintenance_plans",
    "machines": "machine_incident_report",
}


def select_mock_tool_call(messages, tools):
    """Return ``(content, tool_calls)`` for the mock provider."""
    available = {tool["function"]["name"] for tool in tools or [] if "function" in tool}
    user_text = _last_user_text(messages)
    tool_payloads = _tool_results_after_last_user(messages)
    if tool_payloads:
        return _compose_answer(tool_payloads), []
    calls = _choose_tool_calls(
        user_text,
        available,
        set(TOOL_REGISTRY),
        _structured_hint_from_messages(messages),
    )
    if not calls:
        return _no_tool_answer(user_text), []
    return None, [
        {"id": f"mock-call-{index}", "name": name, "arguments": arguments}
        for index, (name, arguments) in enumerate(calls[:MAX_CALLS_PER_TURN], start=1)
    ]


def _choose_tool_calls(text, available, registry_names=None, structured_hint=None):
    """Return ``[(tool_name, arguments)]`` for a user message (may be empty)."""
    registry = set(registry_names or []) | set(available)
    lowered = normalize_text(text)
    signals = _signals(text, lowered)

    action = _action_tool(text, lowered, available)
    if action:
        return [action]
    if _is_general_chat(lowered):
        return []
    if IDENTIFIER_PATTERN.search(text) and "search_knowledge" in available:
        return [("search_knowledge", {"query": text[:500]})]
    if structured_hint and (is_structured_follow_up(text) or _is_bare_follow_up(lowered)):
        follow_up = _follow_up_call(text, lowered, signals, structured_hint, registry)
        if follow_up:
            return [follow_up]
    structured = _structured_calls(text, lowered, signals, registry, available)
    if structured:
        return structured
    if (
        ERROR_CODE_PATTERN.search(text)
        or any(term in lowered for term in ("fehler", "stoerung", "error"))
    ) and "error_assistant" in available:
        return [("error_assistant", {"query": text[:1000]})]
    search = _search_tool(lowered, available)
    if search:
        return [(search, {"query": text[:500]})]
    if "search_knowledge" in available:
        return [("search_knowledge", {"query": text[:500]})]
    return []


# ---------------------------------------------------------------------------
# Rule groups
# ---------------------------------------------------------------------------


def _action_tool(text, lowered, available):
    """Return write/planning/keyword tools that take precedence over lookups."""
    if any(term in lowered for term in CREATE_TASK_TERMS) and "create_task" in available:
        return "create_task", {"title": _title_from_text(text), "description": text[:500]}
    if any(term in lowered for term in DRAFT_TERMS) and "draft_task" in available:
        return "draft_task", {"text": text[:2000]}
    quantity = QUANTITY_PATTERN.search(text)
    if (
        quantity
        and "plan_order" in available
        and any(term in lowered for term in ("auftrag", "planen", "fertigen", "produzieren"))
    ):
        return "plan_order", {
            "product": _product_from_text(text),
            "quantity": int(quantity.group(1)),
        }
    for terms, name in KEYWORD_TOOLS:
        if name in available and any(term in lowered for term in terms):
            return name, {}
    machine = MACHINE_PATTERN.search(text)
    if (
        machine
        and "get_machine_overview" in available
        and any(term in lowered for term in ("profil", "status", "ueberblick", "zustand"))
        and "stoerung" not in lowered
    ):
        return "get_machine_overview", {"machine": machine.group(1)}
    if (
        any(term in lowered for term in ("uebergabe", "handover", "uebergeben"))
        and "search_shift_handovers" in available
    ):
        return "search_shift_handovers", {"query": text[:500]}
    return None


def _structured_calls(text, lowered, signals, registry, available):
    """Return parameterized list/count tool calls for structured questions."""
    count_only = signals["count"]
    department = signals["department"]
    if _mentions(lowered, ("urlaub", "urlaubsantr", "abwesenheit")):
        return _registry_call(registry, "list_vacations", _vacation_arguments(lowered, signals))
    if _mentions(lowered, ("mitarbeiter", "personal", "teamleiter", "kolleg", "beschaeftigte")):
        if _mentions(lowered, ("dokument", "unterlage", "zertifikat", "datei")):
            arguments = {"count_only": count_only}
            if _mentions(lowered, ("gespeichert", "hochgeladen", "datei", "welche dokumente")):
                arguments["mode"] = "stored_documents"
            if department:
                arguments["department"] = department
            return _registry_call(registry, "list_employee_documents", arguments)
        if "qualifikation" in lowered and "search_employees" in available:
            return [("search_employees", {"query": text[:500]})]
        arguments = {"count_only": count_only}
        if department:
            arguments["department"] = department
        if "teamleiter" in lowered:
            arguments["role"] = "team_lead"
        availability = _availability(lowered)
        if availability:
            arguments["availability"] = availability
        if signals["structured"] or availability:
            return _registry_call(registry, "list_employees", arguments)
        if "search_employees" in available:
            return [("search_employees", {"query": text[:500]})]
        return _registry_call(registry, "list_employees", arguments)
    availability = _availability(lowered)
    if availability and signals["list"]:
        return _registry_call(
            registry, "list_employees", {"availability": availability, "count_only": False}
        )
    if "schicht" in lowered:
        return _registry_call(registry, "list_shift_entries", _shift_arguments(text, lowered))
    if INSPECTION_PATTERN.search(lowered):
        arguments = {"count_only": count_only}
        if _mentions(lowered, ("ueberfaellig", "verpasst", "abgelaufen")):
            arguments["due_state"] = "overdue"
        elif _mentions(lowered, ("bald", "demnaechst", "naechste", "diesen monat", "anstehend")):
            arguments["due_state"] = "due_soon"
        if "wartungsplan" not in lowered:
            arguments["kind"] = "inspection"
        return _registry_call(registry, "list_maintenance_plans", arguments)
    if _mentions(lowered, ("lager", "bestand", "material", "ersatzteil", "artikel")):
        if _mentions(lowered, VALUE_TERMS):
            return _registry_call(registry, "list_inventory", {"filter": "all", "count_only": True})
        arguments = _inventory_arguments(text, lowered, count_only)
        if arguments or _mentions(lowered, ("welche", "zeige", "liste", "alle ")):
            return _registry_call(
                registry, "list_inventory", {"filter": "all", "count_only": count_only, **arguments}
            )
        return None
    if _mentions(lowered, ("dokument", "bericht", "protokoll")) and not _mentions(
        lowered, ("handbuch", "anleitung", "manual")
    ):
        arguments = _document_arguments(text, lowered, department)
        if arguments:
            return _registry_call(registry, "list_documents", arguments)
        if count_only:
            return _registry_call(registry, "count_records", {"scope": "documents"})
        return None
    if _mentions(lowered, ("ausfallzeit", "stillstandszeit", "ausfallzeiten")):
        return _registry_call(registry, "machine_incident_report", {})
    incident_words = _mentions(lowered, ("stoerung", "fehler", "problem", "incident", "error"))
    machine_reference = _machine_reference(text)
    if incident_words and signals["structured"]:
        if _mentions(lowered, ("meisten", "haeufigsten", "am meisten")):
            return _registry_call(
                registry, "list_incidents", {"group_by": "machine", "count_only": False}
            )
        if machine_reference and not count_only and not signals["status"]:
            return _registry_call(
                registry, "machine_incident_report", {"machine": machine_reference}
            )
        arguments = {"count_only": count_only}
        for key, value in (
            ("status", signals["status"]),
            ("severity", signals["severity"]),
            ("department", department),
            ("time_range", signals["time_range"]),
            ("machine", machine_reference),
        ):
            if value:
                arguments[key] = value
        if count_only and len(arguments) == 1 and not machine_reference:
            return _count_calls(lowered, registry) or _registry_call(
                registry, "list_incidents", arguments
            )
        return _registry_call(registry, "list_incidents", arguments)
    task_words = _mentions(lowered, ("task", "aufgabe", "todo"))
    if task_words and (signals["structured"] or _mentions(lowered, ("dringend", "faellig"))):
        arguments = {"count_only": count_only}
        status = detect_status(text, TASK_STATUS_TERMS)
        if status:
            arguments["status"] = status
        if department:
            arguments["department"] = department
        if machine_reference:
            arguments["machine"] = machine_reference
        if "dringend" in lowered:
            arguments["priority"] = "urgent"
        if "ueberfaellig" in lowered:
            arguments["due"] = "overdue"
        elif signals["time_range"] == "yesterday":
            arguments["time_range"] = "yesterday"
        elif signals["time_range"] == "today" or _mentions(lowered, ("anstehend", "faellig")):
            arguments["due"] = "today"
        if count_only and len(arguments) == 1:
            return _count_calls(lowered, registry) or _registry_call(
                registry, "list_tasks", arguments
            )
        return _registry_call(registry, "list_tasks", arguments)
    if count_only:
        return _count_calls(lowered, registry)
    return None


def _follow_up_call(text, lowered, signals, hint, registry):
    """Return a refined call for "welche davon"-style follow-ups."""
    entity_type = str(hint.get("entity_type") or "")
    tool_name = ENTITY_TOOLS.get(entity_type)
    if not tool_name or tool_name not in registry:
        return None
    inherited = {
        key: hint[key]
        for key in ("department", "status", "time_range", "machine", "shift")
        if hint.get(key)
    }
    fresh = {
        "department": signals["department"],
        "status": signals["status"],
        "time_range": signals["time_range"],
        "machine": _machine_reference(text),
    }
    if entity_type == "tasks":
        fresh["status"] = detect_status(text, TASK_STATUS_TERMS)
    merged = {**inherited, **{key: value for key, value in fresh.items() if value}}
    if tool_name in {"list_tasks", "list_incidents"}:
        arguments = {
            key: merged[key]
            for key in ("department", "status", "time_range", "machine")
            if merged.get(key)
        }
        if entity_type == "incidents" and signals["severity"]:
            arguments["severity"] = signals["severity"]
        if entity_type == "tasks" and "dringend" in lowered:
            arguments["priority"] = "urgent"
        arguments["count_only"] = signals["count"]
        return tool_name, arguments
    if tool_name == "list_employees":
        arguments = {"count_only": signals["count"]}
        if merged.get("department"):
            arguments["department"] = merged["department"]
        availability = _availability(lowered)
        if availability:
            arguments["availability"] = availability
        return tool_name, arguments
    if tool_name == "list_employee_documents":
        arguments = {"count_only": signals["count"]}
        if merged.get("department"):
            arguments["department"] = merged["department"]
        return tool_name, arguments
    if tool_name == "list_vacations":
        return tool_name, _vacation_arguments(lowered, signals)
    if tool_name == "list_documents":
        arguments = _document_arguments(text, lowered, merged.get("department"))
        return tool_name, arguments or {"filter": "recent"}
    if tool_name == "list_shift_entries":
        arguments = _shift_arguments(text, lowered)
        if merged.get("shift") and "shift" not in arguments:
            arguments["shift"] = _shift_alias(merged["shift"])
        return tool_name, arguments
    if tool_name == "list_inventory":
        if _mentions(lowered, VALUE_TERMS):
            return tool_name, {"filter": "all", "count_only": True}
        arguments = _inventory_arguments(text, lowered, signals["count"])
        return tool_name, {"filter": "all", "count_only": signals["count"], **arguments}
    if tool_name == "machine_incident_report":
        machine = merged.get("machine")
        return tool_name, {"machine": machine} if machine else {}
    return None


def _count_calls(lowered, registry):
    """Return one ``count_records`` call per mentioned scope."""
    if "count_records" not in registry:
        return None
    calls = []
    for scope, terms in COUNT_SCOPE_TERMS:
        if _mentions(lowered, terms):
            calls.append(("count_records", {"scope": scope}))
    return calls[:MAX_CALLS_PER_TURN] or None


def _search_tool(lowered, available):
    """Return a free-text ``search_<scope>`` tool for descriptive questions."""
    for terms, name in (
        (("lager", "bestand", "material", "ersatzteil"), "search_inventory"),
        (("handbuch", "anleitung", "dokument", "bericht", "manual"), "search_documents"),
        (("mitarbeiter", "personal", "qualifikation"), "search_employees"),
        (("schicht", "uebergabe", "handover"), "search_shift_handovers"),
        (("maschine", "anlage", "presse", "roboter"), "search_machines"),
        (("task", "aufgabe", "todo", "erledigt", "faellig"), "search_tasks"),
    ):
        if name in available and any(term in lowered for term in terms):
            return name
    return ""


# ---------------------------------------------------------------------------
# Argument extraction
# ---------------------------------------------------------------------------


def _signals(text, lowered):
    """Return the structured signals detected in a question."""
    count = any(term in lowered for term in COUNT_TERMS)
    listing = any(term in lowered for term in LIST_TERMS)
    status = detect_status(text)
    severity = detect_severity(text)
    time_range = detect_time_range(text)
    return {
        "count": count,
        "list": listing,
        "status": status,
        "severity": severity,
        "time_range": time_range,
        "department": detect_department(text),
        "structured": bool(count or listing or status or severity),
    }


def _vacation_arguments(lowered, signals):
    """Return ``list_vacations`` arguments for a vacation question."""
    own = _mentions(lowered, ("mein", "meine", "meinen", "meiner", "ich"))
    if own and _mentions(lowered, ("status", "genehmigt", "letzte", "letzter")):
        return {"scope": "own_latest"}
    if own:
        return {"scope": "own_pending"}
    if _mentions(lowered, ("morgen", "naechste woche", "naechster woche", "wer hat", "abwesen")):
        arguments = {"scope": "absences"}
        arguments["time_range"] = "next_week" if "woche" in lowered else "tomorrow"
        if signals["department"]:
            arguments["department"] = signals["department"]
        return arguments
    return {"scope": "pending", "count_only": signals["count"]}


def _availability(lowered):
    """Return the employee availability filter mentioned in a question."""
    absent = _mentions(lowered, ("fehlt", "fehlen", "nicht da", "abwesend"))
    if absent and "morgen" in lowered:
        return "absent_tomorrow"
    if absent:
        return "absent_today"
    if _mentions(lowered, ("verfuegbar", "anwesend", "heute da", "sind da", "ist da")):
        return "available_today"
    return ""


def _shift_arguments(text, lowered):
    """Return ``list_shift_entries`` arguments for a shift question."""
    arguments = {}
    if _mentions(lowered, ("unterbesetz", "unbesetzt", "fehlen", "luecke")):
        arguments["mode"] = "understaffed"
    elif any(term in lowered for term in COUNT_TERMS):
        arguments["mode"] = "count"
    else:
        arguments["mode"] = "entries"
    for alias, shift in SHIFT_TERMS:
        if alias in lowered:
            arguments["shift"] = shift
            break
    iso_date = ISO_DATE_PATTERN.search(text)
    if iso_date:
        arguments["date"] = iso_date.group(1)
    elif "heute" in lowered:
        arguments["time_range"] = "today"
    elif "morgen" in lowered:
        arguments["time_range"] = "tomorrow"
    return arguments


def _shift_alias(value):
    """Return the tool alias for a persisted German shift name."""
    lowered = normalize_text(value)
    for alias, shift in SHIFT_TERMS:
        if alias in lowered:
            return shift
    return ""


def _inventory_arguments(text, lowered, count_only):
    """Return ``list_inventory`` filter arguments (empty when no filter matches)."""
    machine_reference = _machine_reference(text)
    if _mentions(lowered, ("mindestbestand", "unter ", "niedrig", "knapp", "nachbestell")):
        return {"filter": "low_stock"}
    if "kritisch" in lowered:
        return {"filter": "critical"}
    if machine_reference:
        return {"filter": "machine", "machine": machine_reference}
    if count_only:
        return {"filter": "all"}
    return {}


def _document_arguments(text, lowered, department):
    """Return ``list_documents`` arguments (empty when no supported filter matches)."""
    machine_reference = _machine_reference(text)
    if _mentions(lowered, ("diese woche", "dieser woche", "wochen")):
        return {"filter": "this_week"}
    if _mentions(lowered, ("veraltet", "alt ", "alte ", "ueberholt")):
        return {"filter": "outdated"}
    if _mentions(lowered, ("neueste", "letzte", "aktuell", "zuletzt", "neu ")):
        return {"filter": "recent"}
    if machine_reference:
        return {"filter": "machine", "machine": machine_reference}
    if department:
        return {"filter": "department", "department": department}
    return {}


def _machine_reference(text):
    """Return a machine phrase such as ``Presse 3`` or ``Maschine Spritzgussanlage 04``."""
    match = MACHINE_REFERENCE_PATTERN.search(text)
    if not match:
        return ""
    reference = " ".join(match.group(1).split())
    words = reference.split(" ")
    if len(words) == 1:
        return ""
    if words[0].lower() in {"maschine", "anlage"}:
        reference = " ".join(words[1:])
    return reference[:120]


def _mentions(lowered, terms):
    """Return whether normalized text contains any of the terms."""
    return any(term in lowered for term in terms)


def _is_bare_follow_up(lowered):
    """Return whether a short question names no data scope of its own."""
    if len(lowered) > 60:
        return False
    scope_words = (
        "task",
        "aufgabe",
        "stoerung",
        "fehler",
        "maschine",
        "lager",
        "material",
        "mitarbeiter",
        "urlaub",
        "schicht",
        "dokument",
        "bericht",
        "ersatzteil",
        "bestand",
    )
    return not any(word in lowered for word in scope_words)


def _is_general_chat(lowered):
    """Return whether a message is small talk that needs no tool."""
    return len(lowered) <= 40 and any(term in lowered for term in GENERAL_TERMS)


def _registry_call(registry, name, arguments):
    """Return one call when the tool exists in the registry."""
    if name not in registry:
        return None
    return [(name, arguments)]


def _structured_hint_from_messages(messages):
    """Return the persisted structured context from the system prompt hint line."""
    for message in messages or []:
        if message.get("role") != "system":
            continue
        match = STRUCTURED_HINT_PATTERN.search(str(message.get("content") or ""))
        if not match:
            continue
        hint = {}
        for part in match.group(0).split(":", 1)[-1].split(","):
            key, _, value = part.strip().rstrip(".").partition("=")
            if key and value:
                hint[key.strip()] = value.strip()
        return hint
    return {}


# ---------------------------------------------------------------------------
# Answer composition
# ---------------------------------------------------------------------------


def _compose_answer(tool_payloads):
    """Compose a grounded German answer from tool payloads."""
    prepared = [
        str(payload.get("answer_markdown") or "").strip()
        for _, payload in tool_payloads
        if payload.get("status") in {"ok", "permission_denied"}
    ]
    if prepared and len(prepared) == len(tool_payloads) and all(prepared):
        return "\n\n".join(prepared)
    lines = ["## Ergebnis (Agent)"]
    for name, payload in tool_payloads:
        summary = str(payload.get("summary") or "").strip()
        status = str(payload.get("status") or "ok")
        if status == "confirmation_required":
            pending = payload.get("pending_action") or {}
            lines.append(
                f"- **Bestaetigung erforderlich:** {pending.get('label') or name} "
                "(bitte die Aktion im Chat bestaetigen)"
            )
            continue
        if status == "permission_denied":
            lines.append(f"- **{name}:** keine Berechtigung fuer diesen Bereich")
            continue
        if status not in {"ok"}:
            lines.append(f"- **{name}:** {summary or status}")
            continue
        lines.append(f"- **{name}:** {summary or 'ausgefuehrt'}")
        for item in _iter_items(payload)[:5]:
            lines.append(f"  - {item}")
        if payload.get("context"):
            snippet = " ".join(str(payload["context"]).split())[:280]
            lines.append(f"  - Wissen: {snippet}")
    lines.append("- **Quelle:** Werkzeugergebnisse aus freigegebenen App-Daten")
    return "\n".join(lines)


def _iter_items(payload):
    """Return short labels for list-like tool payload entries."""
    labels = []
    for key in ("items", "priorities", "matches", "open_tasks", "active_errors", "sections"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                label = (
                    item.get("title")
                    or item.get("name")
                    or item.get("error_code")
                    or item.get("summary")
                    or item.get("reason")
                )
                if label:
                    suffix = ""
                    if item.get("status"):
                        suffix = f" ({item['status']})"
                    labels.append(f"{label}{suffix}")
            elif item:
                labels.append(str(item))
    for key in ("draft", "task", "job", "machine"):
        record = payload.get(key)
        if isinstance(record, dict):
            label = record.get("title") or record.get("name") or record.get("id")
            if label:
                labels.append(f"{key}: {label}")
    if payload.get("causes"):
        labels.append("Ursachen: " + "; ".join(str(item) for item in payload["causes"][:3]))
    if payload.get("fixes"):
        labels.append("Massnahmen: " + "; ".join(str(item) for item in payload["fixes"][:3]))
    return labels


def _no_tool_answer(text):
    """Return a safe answer when no tool matches the request."""
    lowered = normalize_text(text)
    if _is_general_chat(lowered):
        return (
            "## Wartungsassistent\n"
            "- **Hinweis:** Ich beantworte Fragen zu Tasks, Stoerungen, Maschinen, Lager, "
            "Mitarbeitern, Schichten und Wartungswissen aus freigegebenen App-Daten.\n"
            "- **Naechster Schritt:** Stelle eine konkrete Frage, z. B. "
            '"Welche offenen Tasks gibt es?"'
        )
    return (
        "## Ergebnis (Agent)\n"
        "- **Status:** Kein passendes Werkzeug fuer diese Anfrage verfuegbar\n"
        "- **Naechster Schritt:** Frage konkreter nach Tasks, Stoerungen, Maschinen, "
        "Lager, Dokumenten oder Wissen stellen"
    )


def _last_user_text(messages):
    """Return the text of the last user message."""
    for message in reversed(messages or []):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _tool_results_after_last_user(messages):
    """Return ``(tool_name, payload)`` pairs that follow the last user message."""
    results = []
    names_by_call_id = {}
    for message in messages or []:
        role = message.get("role")
        if role == "user":
            results = []
            names_by_call_id = {}
            continue
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                names_by_call_id[call.get("id")] = function.get("name") or call.get("name")
        if role == "tool":
            try:
                payload = json.loads(message.get("content") or "{}")
            except (TypeError, ValueError):
                payload = {"summary": str(message.get("content") or "")[:200]}
            name = (
                names_by_call_id.get(message.get("tool_call_id")) or message.get("name") or "tool"
            )
            results.append((name, payload if isinstance(payload, dict) else {}))
    return results


def _title_from_text(text):
    """Return a task title from a create-task request."""
    cleaned = text
    for term in CREATE_TASK_TERMS:
        index = cleaned.lower().find(term)
        if index != -1:
            cleaned = cleaned[index + len(term) :]
            break
    cleaned = cleaned.strip(" :,-.")
    return (cleaned or text)[:120]


def _product_from_text(text):
    """Return a product label from an order planning request."""
    match = re.search(r"(?:von|fuer|für)\s+([A-Za-z0-9][\w\s-]{2,60})", text)
    if match:
        return match.group(1).strip()[:120]
    return text[:120]
