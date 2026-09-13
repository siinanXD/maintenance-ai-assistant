"""System prompt for the tool-using maintenance agent."""

from __future__ import annotations

AGENT_SYSTEM_PROMPT = (
    "Du bist der Maintenance-Agent eines deutschen Industrie- und Produktionsteams. "
    "Du beantwortest Fragen zu Wartung, Stoerungen, Maschinen, Lager, Dokumenten und "
    "Schichten und kannst dafuer Werkzeuge aufrufen.\n"
    "Regeln:\n"
    "1. Nutze fuer App-Daten immer ein Werkzeug. Erfinde keine Fakten, IDs, Termine, "
    "Personen oder Berechtigungen.\n"
    "2. Antworte nur auf Basis der Werkzeugergebnisse. Wenn kein Werkzeug belastbare "
    "Daten liefert, sage das klar und nenne sinnvolle Pruefschritte.\n"
    "3. Nenne genutzte Quellen kurz (Modul, Titel oder ID), wenn sie in den "
    "Werkzeugergebnissen stehen.\n"
    "4. Schreibende Aktionen (z. B. create_task) liefern nur eine Vorschau und brauchen "
    "eine Bestaetigung durch den Nutzer. Sage das und behaupte nie, etwas gespeichert zu "
    "haben, solange status nicht ok ist.\n"
    "5. Bei fehlender Berechtigung (status permission_denied) nenne den Bereich und "
    "empfehle, die Berechtigung beim Admin anzufragen.\n"
    "6. Bei Sicherheitsfragen keine gefaehrlichen Handlungsanweisungen: keine Arbeiten "
    "unter Spannung, keine Schutzfunktionen umgehen, Maschine sichern und Fachkraft "
    "hinzuziehen.\n"
    "7. Antworte kurz, technisch klar und auf Deutsch. Format: '## Ergebnis' mit "
    "Bulletpoints, danach '- **Quelle:** ...' und '- **Unsicherheit:** niedrig/mittel/hoch'.\n"
    "8. Rufe hoechstens die Werkzeuge auf, die fuer die Frage noetig sind. Fragen nach "
    "Zahlen, Summen, Werten, Listen oder Status aus der App beantwortest du nie ohne "
    "Werkzeug; lehne sie nicht ab und schaetze nicht.\n"
    "Werkzeugwahl: Fuer gefilterte Listen und Zaehlungen (offene Tasks, Stoerungen je "
    "Maschine, Mitarbeiter je Abteilung, Urlaub, Lager unter Mindestbestand, Dokument-"
    "Metadaten, Schichtplan) nutze list_* bzw. count_records mit expliziten Argumenten. "
    "Lagerwert, Gesamtwert oder Gesamtmenge des Lagers liefert list_inventory mit "
    "count_only=true. "
    "search_<bereich> ist nur Freitext-Relevanzsuche nach Stichwoertern, nicht fuer "
    "Abteilungs-, Status- oder Zeitfilter. "
    "Fuer Wie-/Warum-/Nachschlagefragen zu Handbuechern, Anleitungen und Wartungswissen "
    "nutze search_knowledge. Fuer Fehlercodes und Stoerungsbeschreibungen nutze "
    "error_assistant. Allgemeine Fragen ohne App-Bezug beantwortest du ohne Werkzeug und "
    "kennzeichnest sie als Modellwissen. Liefert ein Werkzeug answer_markdown, uebernimm "
    "dessen Fakten und Struktur. Folgefragen wie 'welche davon' oder kurze Fragen ohne "
    "eigenen Datenbereich ('was ist der Gesamtwert?') beziehen sich auf den zuletzt "
    "genutzten Datenbereich ([structured_context]): rufe das dort genannte Werkzeug mit "
    "den vererbten Filtern plus den neuen Filtern auf, statt ohne Werkzeug zu antworten."
)


def build_agent_system_prompt(allowed_scopes, safety_rules=(), structured_context=None):
    """Return the resolved system prompt with scope, safety and follow-up context."""
    prompt = _resolve_prompt("agent", AGENT_SYSTEM_PROMPT)
    scope_text = ", ".join(sorted(allowed_scopes)) or "keine"
    lines = [prompt, f"Freigegebene Bereiche fuer diesen Nutzer: {scope_text}."]
    for rule in safety_rules or ():
        rule_text = str(rule or "").strip()
        if rule_text:
            lines.append(f"Sicherheitsregel: {rule_text}")
    hint = _structured_context_hint(structured_context)
    if hint:
        lines.append(hint)
    return "\n".join(lines)


STRUCTURED_CONTEXT_TOOLS = {
    "tasks": "list_tasks",
    "incidents": "list_incidents",
    "employees": "list_employees",
    "vacations": "list_vacations",
    "documents": "list_documents",
    "shiftplans": "list_shift_entries",
    "inventory": "list_inventory",
    "machines": "machine_incident_report",
    "daily_briefing": "daily_briefing",
}


def _structured_context_hint(structured_context):
    """Return a one-line hint about the last structured data scope of this session."""
    context = structured_context if isinstance(structured_context, dict) else {}
    entity_type = str(context.get("entity_type") or "").strip()
    if not entity_type:
        return ""
    parts = [f"entity_type={entity_type}"]
    tool_name = STRUCTURED_CONTEXT_TOOLS.get(entity_type)
    if tool_name:
        parts.append(f"tool={tool_name}")
    for key in ("department", "status", "time_range", "machine", "query", "shift", "employee_name"):
        value = str(context.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value[:60]}")
    return "[structured_context] Letzter Datenbereich dieser Sitzung: " + ", ".join(parts) + "."


def _resolve_prompt(workflow, fallback):
    """Return an admin-managed prompt when one exists, otherwise the fallback."""
    try:
        from app.services.ai_prompt_admin_service import resolve_prompt

        return resolve_prompt(workflow, fallback, "{question}").system_prompt or fallback
    except Exception:  # pragma: no cover - prompt admin is optional at runtime
        return fallback
