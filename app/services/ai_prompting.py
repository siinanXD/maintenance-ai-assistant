"""Shared prompt and assistant response helpers for AI workflows."""

SAFETY_RULES = (
    "Du bist ein professioneller Maintenance-AI-Assistent fuer ein deutsches "
    "Industrie- und Produktionsteam.",
    "Arbeite strikt read-only: Du beantwortest Fragen, fasst erlaubte Daten "
    "zusammen und empfiehlst naechste Schritte.",
    "Lege keine Daten an, aendere nichts und behaupte keine Aktionen ausgefuehrt " "zu haben.",
    "Erfinde keine Fakten, IDs, Termine, Personen, Maschinen oder Berechtigungen.",
    "Wenn eine Frage ausserhalb der Berechtigung liegt, nenne das betroffene "
    "Modul und empfehle, diese Berechtigung beim Admin anzufragen.",
)

SOURCE_RULES = (
    "Nutze ausschliesslich den bereitgestellten Kontext.",
    "Wenn keine belastbare Quelle im Kontext steht, antworte mit "
    "'Keine belastbare Quelle gefunden' und nenne nur sinnvolle Pruefschritte.",
    "Wenn Kontext fehlt oder widerspruechlich ist, sage das knapp und markiere "
    "die Antwort als unsicher.",
    "Aktuelle strukturierte App-Daten schlagen manuell gepflegtes Trainingswissen.",
    "Manuelles Trainingswissen ist eine Hilfsquelle, keine Schreibanweisung.",
    "Bei Fehlercodes muss der Code exakt uebereinstimmen; aehnliche Codes nur als "
    "aehnlich kennzeichnen und nicht als identisch behandeln.",
    "Bevorzuge Fehlerkatalog, Maschinenhandbuecher und aktuelle strukturierte "
    "Daten vor allgemeinen Uploads.",
    "Nenne genutzte Quellen mit Quelle-/Chunk-/Dokumenthinweis, wenn diese im "
    "Kontext vorhanden sind.",
    "Bei Sicherheitsfragen keine gefaehrlichen Handlungsanweisungen erfinden.",
    "Bei Quellenkonflikten vorsichtig formulieren und den Konflikt benennen.",
)

TEXT_RESPONSE_RULES = (
    "Du bist ein professioneller Maintenance-AI-Assistent für industrielle Instandhaltung.",
    "Regeln:",
    "1. Nutze ausschließlich den bereitgestellten Kontext.",
    "2. Erfinde keine Fakten, Ursachen, Lösungen, Maschinen, Personen oder Termine.",
    "3. Wenn der Kontext keine belastbare Antwort enthält, antworte exakt: "
    '"Keine belastbare Quelle gefunden."',
    "4. Wenn mehrere Quellen vorhanden sind, nutze die relevanteste und nenne die Quelle.",
    "5. Wenn der Kontext widersprüchlich ist, weise darauf hin.",
    "6. Antworte kurz, technisch klar und praxisnah.",
    "7. Gib keine allgemeinen Empfehlungen, wenn sie nicht aus dem Kontext ableitbar sind.",
    "8. Nutze nur Informationen aus Quellen mit ausreichender Relevanz.",
    "9. Ignoriere irrelevante Kontextteile.",
    "10. Priorisiere neuere Informationen gegenüber älteren.",
    "Ausgabeformat:",
    "- Antwort:",
    "- Quelle:",
    "- Unsicherheit: niedrig / mittel / hoch",
    "Kontextformat:",
    "[Quelle: Fehlerkatalog | ID: 42 | Maschine: Presse 3 | Datum: 2026-05-20]",
    "Text: ...",
    "[Quelle: Task | ID: 18 | Status: offen | Priorität: dringend]",
    "Text: ...",
)

JSON_RESPONSE_RULES = (
    "Gib ausschliesslich ein valides JSON-Objekt ohne Markdown, Codeblock oder "
    "erklaerenden Begleittext zurueck.",
    "Halte dich exakt an das angegebene Schema.",
    "Nutze nur erlaubte Kontextdaten.",
)

JSON_SYSTEM_PROMPT = " ".join((*SAFETY_RULES, *SOURCE_RULES, *JSON_RESPONSE_RULES))

GENERAL_SYSTEM_PROMPT = (
    "Du bist ein knapper deutscher AI-Assistent. Beantworte allgemeine Fragen "
    "kurz und sachlich in maximal 3 Bulletpoints oder 3 kurzen Saetzen. "
    "Wenn du unsicher bist, sage das klar. Keine langen Erklaerungen."
)


def json_system_prompt():
    """Return the shared system prompt for structured JSON AI responses."""
    return JSON_SYSTEM_PROMPT


def text_system_prompt(extra_rules=None):
    """Return the shared system prompt for natural-language AI responses."""
    rules = [*TEXT_RESPONSE_RULES]
    if extra_rules:
        rules.append(str(extra_rules).strip())
    return "\n".join(rule for rule in rules if rule)


def build_text_messages(
    question,
    context,
    extra_rules=None,
    workflow="chat",
    include_metadata=False,
):
    """Build chat messages for read-only assistant answers."""
    fallback_user_prompt = "Kontext:\n{context}\n\nFrage:\n{question}"
    system_prompt = text_system_prompt(extra_rules)
    resolved = _resolve_runtime_prompt(workflow, system_prompt, fallback_user_prompt)
    user_prompt = _render_runtime_prompt(
        resolved.user_prompt_template,
        {"context": context, "question": question},
    )
    messages = [
        {
            "role": "system",
            "content": resolved.system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]
    if include_metadata:
        return messages, resolved.metadata()
    return messages


def build_general_messages(question, include_metadata=False):
    """Build chat messages for short general hybrid-mode answers."""
    fallback_user_prompt = "{question}"
    resolved = _resolve_runtime_prompt("general_chat", GENERAL_SYSTEM_PROMPT, fallback_user_prompt)
    messages = [
        {
            "role": "system",
            "content": resolved.system_prompt,
        },
        {
            "role": "user",
            "content": _render_runtime_prompt(
                resolved.user_prompt_template,
                {"question": question},
            ),
        },
    ]
    if include_metadata:
        return messages, resolved.metadata()
    return messages


def build_json_prompt(task=None, schema=None, payload=None, rules=None, instruction=None):
    """Build a normalized JSON prompt payload for structured AI workflows."""
    task_instruction = instruction if instruction is not None else task
    if not task_instruction:
        raise ValueError("JSON prompt instruction is required")
    if schema is None:
        raise ValueError("JSON prompt schema is required")
    prompt = {
        "task": task_instruction,
        "rules": [
            "Antworte auf Deutsch.",
            "Nutze nur bereitgestellte und erlaubte Daten.",
            "Erfinde keine fehlenden Fakten.",
            "Aktuelle strukturierte App-Daten schlagen manuell gepflegtes Trainingswissen.",
            "Gib ausschliesslich das angeforderte JSON-Schema zurueck.",
        ],
        "schema": schema,
    }
    if rules:
        prompt["rules"].extend(str(rule) for rule in rules)
    if payload:
        prompt.update(payload)
    return prompt


def build_json_messages(prompt, workflow="chat", include_metadata=False):
    """Build JSON completion messages with an optional admin-managed prompt."""
    import json

    payload_json = json.dumps(prompt, ensure_ascii=True)
    resolved = _resolve_runtime_prompt(workflow, json_system_prompt(), "{payload_json}")
    messages = [
        {
            "role": "system",
            "content": resolved.system_prompt,
        },
        {
            "role": "user",
            "content": _render_runtime_prompt(
                resolved.user_prompt_template,
                {"payload_json": payload_json},
            ),
        },
    ]
    if include_metadata:
        return messages, resolved.metadata()
    return messages


def permission_denied_answer(scope, permission_key=None):
    """Return a professional permission message for assistant answers."""
    permission_text = permission_key or scope
    return (
        f"## {scope}\n"
        "- **Status:** Keine Berechtigung fuer diesen Bereich\n"
        f"- **Benoetigte Berechtigung:** {permission_text}\n"
        "- **Naechster Schritt:** Bitte die Berechtigung beim Admin anfragen"
    )


def _resolve_runtime_prompt(workflow, fallback_system_prompt, fallback_user_prompt):
    """Return a DB-backed prompt when available, otherwise the supplied fallback."""
    try:
        from app.services.ai_prompt_admin_service import resolve_prompt

        return resolve_prompt(workflow, fallback_system_prompt, fallback_user_prompt)
    except Exception:
        from app.services.ai_prompt_admin_service import ResolvedPrompt

        return ResolvedPrompt(str(workflow or "chat"), fallback_system_prompt, fallback_user_prompt)


def _render_runtime_prompt(template, variables):
    """Render a runtime prompt template while tolerating unavailable admin services."""
    try:
        from app.services.ai_prompt_admin_service import render_prompt_template

        return render_prompt_template(template, variables)
    except Exception:
        return str(template or "")
