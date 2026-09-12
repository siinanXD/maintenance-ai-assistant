"""Deterministic tool-selection policy for the mock provider.

Keeps the agent loop fully testable offline: the policy picks one tool from the
last user message with simple German keyword rules and, once tool results are
present, composes a short grounded answer from them. It never invents data.
"""

from __future__ import annotations

import json
import re

ERROR_CODE_PATTERN = re.compile(r"\b[A-Z]{1,6}[-_ ]?\d{2,6}\b", re.IGNORECASE)
MACHINE_PATTERN = re.compile(
    r"\b(?:maschine|anlage|presse|linie|station|roboter|ofen)\s+([A-Za-z0-9][\w-]*)",
    re.IGNORECASE,
)
QUANTITY_PATTERN = re.compile(r"\b(\d{1,7})\s*(?:stueck|stück|stk)\b", re.IGNORECASE)
CREATE_TASK_TERMS = ("task anlegen", "aufgabe anlegen", "task erstellen", "aufgabe erstellen")
DRAFT_TERMS = ("entwurf", "vorschlag", "vorschlagen")
KEYWORD_TOOLS = (
    (("reindex", "neu indexieren", "reindexieren"), "request_knowledge_reindex"),
    (("priorisier", "prioritaet", "priorität", "rangfolge"), "prioritize_tasks"),
    (("briefing", "tagesueberblick", "tagesüberblick"), "daily_briefing"),
    (("lager", "bestand", "material", "ersatzteil"), "search_inventory"),
    (("handbuch", "anleitung", "dokument", "bericht", "manual"), "search_documents"),
    (("mitarbeiter", "personal", "qualifikation"), "search_employees"),
    (("schicht", "uebergabe", "übergabe", "handover"), "search_shift_handovers"),
    (("maschine", "anlage", "presse", "roboter"), "search_machines"),
    (("task", "aufgabe", "todo", "erledigt", "faellig", "fällig"), "search_tasks"),
)


def select_mock_tool_call(messages, tools):
    """Return ``(content, tool_calls)`` for the mock provider."""
    available = {tool["function"]["name"] for tool in tools or [] if "function" in tool}
    user_text = _last_user_text(messages)
    tool_payloads = _tool_results_after_last_user(messages)
    if tool_payloads:
        return _compose_answer(tool_payloads), []
    name, arguments = _choose_tool(user_text, available)
    if not name:
        return _no_tool_answer(user_text), []
    return None, [{"id": "mock-call-1", "name": name, "arguments": arguments}]


def _choose_tool(text, available):
    """Return the tool name and arguments for a user message."""
    lowered = text.lower()
    if any(term in lowered for term in CREATE_TASK_TERMS) and "create_task" in available:
        title = _title_from_text(text)
        return "create_task", {"title": title, "description": text[:500]}
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
    machine = MACHINE_PATTERN.search(text)
    if (
        machine
        and "get_machine_overview" in available
        and any(
            term in lowered for term in ("profil", "status", "ueberblick", "überblick", "zustand")
        )
    ):
        return "get_machine_overview", {"machine": machine.group(1)}
    if (
        ERROR_CODE_PATTERN.search(text)
        or any(term in lowered for term in ("fehler", "stoerung", "störung", "error"))
    ) and "error_assistant" in available:
        return "error_assistant", {"query": text[:1000]}
    for terms, name in KEYWORD_TOOLS:
        if name in available and any(term in lowered for term in terms):
            if name in {"prioritize_tasks", "daily_briefing", "request_knowledge_reindex"}:
                return name, {}
            return name, {"query": text[:500]}
    if "search_knowledge" in available:
        return "search_knowledge", {"query": text[:500]}
    return "", {}


def _compose_answer(tool_payloads):
    """Compose a grounded German answer from tool payloads."""
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
