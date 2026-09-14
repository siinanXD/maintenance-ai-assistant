"""Deterministic local provider: keyword rules instead of a model, for tests and offline use."""

import re
from datetime import date

from app.services.ai_routing import (
    local_metadata,
)
from app.services.ai_service import BaseAIProvider, ToolCall, ToolCallResponse


class MockAIProvider(BaseAIProvider):
    """Provide deterministic local AI-like results without external services."""

    name = "mock"
    supports_tool_calls = True

    def chat_with_tools(self, messages, tools, workflow="agent"):
        """Select tools with deterministic keyword rules and summarize tool results."""
        from app.agent.mock_policy import select_mock_tool_call

        self.last_call_metadata = local_metadata(self.name, workflow)
        content, calls = select_mock_tool_call(messages, tools)
        return ToolCallResponse(
            content=content,
            tool_calls=[
                ToolCall(id=call["id"], name=call["name"], arguments=dict(call["arguments"]))
                for call in calls
            ],
            metadata=dict(self.last_call_metadata),
        )

    def suggest_task(self, text, user_context=None):
        """Return a deterministic task suggestion from free text."""
        self.last_call_metadata = local_metadata(self.name, "task_suggestion")
        department = _department_from_text(text, user_context)
        priority = "urgent" if _contains_any(text, ["not-halt", "stillstand"]) else "soon"
        machine = _extract_machine(text)
        title = _short_title(text, prefix="Pruefung")
        return {
            "title": title,
            "description": text.strip(),
            "department": department,
            "priority": priority,
            "status": "open",
            "possible_cause": _cause_from_text(text),
            "recommended_action": (
                f"{machine} sicher pruefen, Befund dokumentieren und "
                "bei Bedarf Instandhaltung informieren."
            ),
        }

    def analyze_error(self, text, user_context=None):
        """Return a deterministic error analysis from free text."""
        self.last_call_metadata = local_metadata(self.name, "error_analysis")
        machine = _extract_machine(text)
        return {
            "machine": machine,
            "title": _short_title(text, prefix="Stoerung"),
            "description": text.strip(),
            "possible_causes": _cause_from_text(text),
            "solution": (
                "Anlage sichern, Sichtpruefung durchfuehren, betroffene "
                "Komponenten pruefen und Ergebnis im Fehlerkatalog dokumentieren."
            ),
            "department": _department_from_text(text, user_context),
        }

    def generate_document_text(self, data):
        """Return a deterministic maintenance report text."""
        self.last_call_metadata = local_metadata(self.name, "document_text")
        return (
            f"Wartungsbericht fuer Task {data.get('task_id')}: "
            f"{data.get('title')}. Ergebnis: {data.get('result') or 'erledigt'}."
        )

    def answer_question(self, question, context, workflow="chat", extra_rules=None):
        """Return a cautious local answer for a question and context."""
        self.last_call_metadata = local_metadata(self.name, workflow)
        if not context.strip():
            return (
                "## Ergebnis\n"
                "- **Status:** Keine passende Grundlage gefunden\n"
                "- **Naechster Schritt:** Daten oder Suchbegriff pruefen"
            )
        return (
            "## Ergebnis\n"
            "- **Status:** Freigegebene Daten geprueft\n"
            "- **Hinweis:** Frage bitte konkreter nach Tasks, Fehlern, "
            "Maschinen, Lager, Dokumenten oder Mitarbeitern"
        )

    def answer_general_question(self, question):
        """Return a deterministic local answer for general hybrid mode."""
        self.last_call_metadata = local_metadata(self.name, "general_chat")
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** Allgemeine AI-Antwort ist lokal nicht verfuegbar\n"
            "- **Naechster Schritt:** OpenAI API-Key und Verbindung pruefen"
        )

    def prioritize_tasks(self, tasks, context=None):
        """Return deterministic task priorities without external services."""
        self.last_call_metadata = local_metadata(self.name, "task_prioritization")
        priorities = [_score_task_priority(task) for task in tasks]
        return {"priorities": priorities}

    def review_document(self, html_text, metadata=None):
        """Return a simple placeholder document review for local mode."""
        self.last_call_metadata = local_metadata(self.name, "document_review")
        return {
            "quality_score": 0,
            "status": "incomplete",
            "findings": [],
            "recommendations": [],
        }

    def error_assistant_query(self, query, matches):
        """Return None — local similarity results are sufficient in mock mode."""
        return None


def _contains_any(text, needles):
    """Return whether text contains any of the provided needles."""
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _extract_machine(text):
    """Extract a simple machine label from free text."""
    match = re.search(r"(maschine|anlage)\s*[\w-]+", text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return "Unbekannte Maschine"


def _department_from_text(text, user_context=None):
    """Infer a responsible department from text or user context."""
    lowered = text.lower()
    if _contains_any(lowered, ["lager", "geraeusch", "leck", "motor", "sensor"]):
        return "Instandhaltung"
    if user_context and user_context.get("department"):
        return user_context["department"]
    return "Produktion"


def _cause_from_text(text):
    """Infer a plausible cause from free text."""
    lowered = text.lower()
    if "sensor" in lowered:
        return "Sensor verschmutzt, falsch ausgerichtet oder Kabelverbindung gestoert."
    if "lager" in lowered or "geraeusch" in lowered:
        return "Lager verschlissen, Schmierung unzureichend oder mechanische Unwucht."
    if "leck" in lowered or "druck" in lowered:
        return "Leckage, Dichtung defekt oder Druckversorgung instabil."
    return "Ursache noch unklar; strukturierte Sichtpruefung erforderlich."


def _short_title(text, prefix):
    """Create a short German title from free text."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return f"{prefix} erforderlich"
    return f"{prefix}: {cleaned[:80]}"


def _score_task_priority(task):
    """Return a local priority score for a serialized task."""
    score = 0
    reasons = []
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()

    priority_score, priority_reason = _priority_score(task.get("priority"))
    score += priority_score
    reasons.append(priority_reason)

    history_score, history_reason = _history_score(task.get("history"))
    score += history_score
    if history_reason:
        reasons.append(history_reason)

    due_score, due_reason = _due_date_score(task.get("due_date"))
    score += due_score
    if due_reason:
        reasons.append(due_reason)

    status_score, status_reason = _status_score(task.get("status"))
    score += status_score
    reasons.append(status_reason)

    keyword_score, keyword_reason = _keyword_score(text)
    score += keyword_score
    if keyword_reason:
        reasons.append(keyword_reason)

    normalized_score = max(0, min(100, score))
    risk_level = _risk_level(normalized_score)
    return {
        "task_id": task.get("id"),
        "score": normalized_score,
        "risk_level": risk_level,
        "reason": "; ".join(reasons[:4]),
        "recommended_action": _recommended_priority_action(risk_level, task.get("history")),
    }


def _priority_score(priority):
    """Return score contribution and reason for a task priority."""
    if priority == "urgent":
        return 45, "Prioritaet urgent"
    if priority == "soon":
        return 30, "Prioritaet soon"
    return 15, "Prioritaet normal"


def _status_score(status):
    """Return score contribution and reason for a task status."""
    if status == "in_progress":
        return 15, "Task ist bereits in Arbeit"
    if status == "open":
        return 10, "Task ist offen"
    return 0, f"Status {status or 'unbekannt'}"


def _due_date_score(due_date_value):
    """Return score contribution and reason for the due date."""
    if not due_date_value:
        return 0, ""
    try:
        days_until_due = (date.fromisoformat(due_date_value) - date.today()).days
    except ValueError:
        return 0, ""

    if days_until_due < 0:
        return 25, "Faelligkeit ist ueberfaellig"
    if days_until_due == 0:
        return 18, "Faelligkeit ist heute"
    if days_until_due <= 2:
        return 10, "Faelligkeit innerhalb von zwei Tagen"
    if days_until_due <= 7:
        return 5, "Faelligkeit innerhalb einer Woche"
    return 0, ""


def _keyword_score(text):
    """Return score contribution and reason for risk keywords."""
    keyword_groups = [
        (
            ["not-halt", "stillstand", "ausfall", "steht"],
            25,
            "kritischer Anlagenzustand",
        ),
        (["leck", "druck", "hydraulik", "pneumatik"], 18, "Leckage oder Druckproblem"),
        (["sensor", "lichttaster", "signal"], 12, "Sensorik betroffen"),
        (["lager", "geraeusch", "motor", "unwucht"], 10, "mechanische Symptome"),
    ]
    for keywords, score, reason in keyword_groups:
        if _contains_any(text, keywords):
            return score, reason
    return 0, ""


def _history_score(history):
    """Return score contribution and reason from maintenance history context."""
    if not isinstance(history, dict):
        return 0, ""

    score = 0
    signals = set(history.get("risk_signals") or [])
    related_errors = history.get("recent_related_errors") or []
    related_error_count = _safe_int(history.get("related_error_count"))
    reports_count = _safe_int(history.get("maintenance_reports_count"))
    reopened_count = _safe_int(history.get("reopened_count"))
    reasons = []

    if history.get("blocked"):
        score += 20
        reasons.append("Task ist blockiert")
    if reopened_count:
        score += min(15, reopened_count * 5)
        reasons.append(f"{reopened_count} Wiedereroeffnung(en)")
    if related_error_count:
        score += min(20, related_error_count * 8)
        reasons.append(f"{related_error_count} verwandte Stoerung(en)")
    if "critical_error_history" in signals:
        score += 12
        reasons.append("kritische Fehlerhistorie")
    if "recurring_error_history" in signals:
        score += 8
        reasons.append("wiederkehrende Fehlerhistorie")
    if "downtime_history" in signals:
        score += 6
        reasons.append("Ausfallzeit in Historie")
    if reports_count:
        score += min(8, reports_count * 4)
        reasons.append(f"{reports_count} Wartungsbericht(e)")

    highest_severity = _highest_related_error_severity(related_errors)
    if highest_severity and highest_severity not in {"low", "medium"}:
        reasons.append(f"hoechste Stoerungsschwere {highest_severity}")

    if not reasons:
        return 0, ""
    return score, "Historie: " + ", ".join(reasons[:3])


def _safe_int(value):
    """Return an integer value for scoring or zero for malformed input."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _highest_related_error_severity(errors):
    """Return the highest severity label from related error payloads."""
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    severities = [
        str(error.get("severity") or "").lower() for error in errors if isinstance(error, dict)
    ]
    if not severities:
        return ""
    return max(severities, key=lambda severity: severity_order.get(severity, 0))


def _risk_level(score):
    """Return the risk level for a numeric task score."""
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _recommended_priority_action(risk_level, history=None):
    """Return a German next-action recommendation for a risk level."""
    signals = set(history.get("risk_signals") or []) if isinstance(history, dict) else set()
    if "critical_error_history" in signals or "downtime_history" in signals:
        return (
            "Vor Start Stoerungshistorie pruefen, Anlage absichern und "
            "naechste Massnahme dokumentieren."
        )
    if history and history.get("blocked"):
        return "Blocker klaeren, Verantwortliche informieren und Termin neu bewerten."
    actions = {
        "critical": "Sofort pruefen, Anlage sichern und Instandhaltung informieren.",
        "high": "Zeitnah einplanen und Ursache vor Schichtende dokumentieren.",
        "medium": "Im Tagesplan beruecksichtigen und Befund erfassen.",
        "low": "Nach aktuellen dringenden Tasks bearbeiten.",
    }
    return actions[risk_level]
