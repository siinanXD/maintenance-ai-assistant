"""Local prompt generation for incomplete fault and knowledge records."""

import re

FIELD_PROMPTS = {
    "machine": {
        "label": "Maschine oder Anlage",
        "question": "Welche Maschine, Anlage oder Linie ist betroffen?",
        "reason": "Ohne Maschinenbezug kann der Eintrag nicht sauber zugeordnet werden.",
        "examples": ["Maschine 3", "Anlage 4", "Linie A"],
    },
    "error_code": {
        "label": "Fehlercode",
        "question": "Welcher Fehlercode, Alarmtext oder welche Meldungsnummer wird angezeigt?",
        "reason": "Der Fehlercode verbindet neue Meldungen mit vorhandenen Katalogeintraegen.",
        "examples": ["E104", "CNC-E-104", "Alarm 42"],
    },
    "symptoms": {
        "label": "Symptome",
        "question": "Welche konkreten Symptome sind sichtbar oder messbar?",
        "reason": "Symptome helfen, Ursache und Dringlichkeit einzugrenzen.",
        "examples": ["Sensor meldet kein Signal", "Druck faellt ab", "Anlage stoppt"],
    },
    "previous_checks": {
        "label": "Bisherige Pruefung",
        "question": "Was wurde bereits geprueft, gemessen, gereinigt oder getauscht?",
        "reason": "Bereits erledigte Pruefungen vermeiden doppelte Arbeit.",
        "examples": ["Sensor gereinigt", "Kabel geprueft", "Reset durchgefuehrt"],
    },
    "affected_area": {
        "label": "Betroffener Bereich",
        "question": "Welcher Bereich, Standort oder welche Abteilung ist betroffen?",
        "reason": "Der Bereich steuert Sichtbarkeit, Verantwortlichkeit und Folgeaktionen.",
        "examples": ["Instandhaltung", "Produktion", "Werk 1"],
    },
    "solution_outcome": {
        "label": "Loesungsergebnis",
        "question": "Welches Ergebnis hatte die Massnahme oder wie ist der aktuelle Zustand?",
        "reason": "Das Ergebnis entscheidet, ob der Eintrag als Loesung taugt.",
        "examples": ["Stoerung behoben", "weiterhin sporadisch", "Probelauf erfolgreich"],
    },
}

ERROR_TEXT_FIELDS = (
    "machine",
    "error_code",
    "title",
    "description",
    "possible_causes",
    "solution",
    "department",
    "affected_area",
    "previous_checks",
    "checks_done",
    "inspection",
    "solution_result",
    "outcome",
)

KNOWLEDGE_TEXT_FIELDS = (
    "title",
    "question",
    "answer",
    "keywords",
    "category",
    "department",
    "machine",
    "error_code",
    "description",
    "context",
    "solution",
    "solution_result",
    "affected_area",
    "previous_checks",
)


def missing_information_for_error_entry(data, user=None):
    """Return missing-information prompts for an error catalog payload."""
    payload = _payload_dict(data)
    context = _combined_text(payload, ERROR_TEXT_FIELDS)
    detected_fields = _detected_fields(payload, context, user)
    return _build_result("error_entry", detected_fields)


def missing_information_for_knowledge_entry(data, user=None):
    """Return missing-information prompts for a manual knowledge payload."""
    payload = _payload_dict(data)
    context = _combined_text(payload, KNOWLEDGE_TEXT_FIELDS)
    detected_fields = _detected_fields(payload, context, user)
    return _build_result("knowledge_entry", detected_fields)


def _payload_dict(data):
    """Return a plain dictionary for a request payload or model-like object."""
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict"):
        return data.to_dict()
    return {}


def _combined_text(payload, field_names):
    """Return normalized text from relevant payload fields."""
    parts = []
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, list | tuple | set):
            parts.extend(str(item or "") for item in value)
        else:
            parts.append(str(value or ""))
    return _normalize_text(" ".join(parts))


def _detected_fields(payload, context, user=None):
    """Return field names that are already present in the payload context."""
    detected = set()
    if _has_machine(payload, context):
        detected.add("machine")
    if _has_error_code(payload, context):
        detected.add("error_code")
    if _has_symptoms(payload, context):
        detected.add("symptoms")
    if _has_previous_checks(payload, context):
        detected.add("previous_checks")
    if _has_affected_area(payload, context, user):
        detected.add("affected_area")
    if _has_solution_outcome(payload, context):
        detected.add("solution_outcome")
    return detected


def _build_result(entry_type, detected_fields):
    """Build the public JSON payload for missing-information prompts."""
    missing_fields = [
        field_name for field_name in FIELD_PROMPTS if field_name not in detected_fields
    ]
    questions = [
        _question_payload(field_name, index) for index, field_name in enumerate(missing_fields)
    ]
    return {
        "entry_type": entry_type,
        "status": "complete" if not missing_fields else "needs_information",
        "missing_fields": missing_fields,
        "detected_fields": sorted(detected_fields),
        "completion_ratio": round(
            len(detected_fields) / len(FIELD_PROMPTS),
            2,
        ),
        "questions": questions,
        "summary": _summary_text(missing_fields),
    }


def _question_payload(field_name, index):
    """Return one structured follow-up question for a missing field."""
    prompt = FIELD_PROMPTS[field_name]
    return {
        "id": field_name,
        "field": field_name,
        "label": prompt["label"],
        "question": prompt["question"],
        "reason": prompt["reason"],
        "answer_type": "text",
        "required": True,
        "priority": (index + 1) * 10,
        "examples": prompt["examples"],
    }


def _summary_text(missing_fields):
    """Return a concise German summary for the prompt block."""
    if not missing_fields:
        return "Alle Kerninformationen sind vorhanden."
    labels = [FIELD_PROMPTS[field_name]["label"] for field_name in missing_fields]
    return "Es fehlen gezielte Angaben zu: " + ", ".join(labels) + "."


def _has_machine(payload, context):
    """Return whether a machine or asset reference is available."""
    if _meaningful_text(payload.get("machine")) or _meaningful_text(payload.get("machine_id")):
        return True
    return bool(
        re.search(
            r"\b(?:maschine|anlage|linie|station|aggregat)\s*[:#-]?\s*[a-z0-9][a-z0-9_-]*\b",
            context,
        )
    )


def _has_error_code(payload, context):
    """Return whether an error code or alarm number is available."""
    if _meaningful_text(payload.get("error_code")) or _meaningful_text(payload.get("fault_code")):
        return True
    if re.search(r"\b[a-z]{1,5}(?:[-_][a-z]{1,5})?[-_]?\d{2,6}\b", context):
        return True
    return bool(
        re.search(
            r"\b(?:fehlercode|fehler|error|code|meldung|alarm)\s*[:#-]?\s*\d{2,6}\b",
            context,
        )
    )


def _has_symptoms(payload, context):
    """Return whether concrete symptoms are described."""
    symptom_text = " ".join(
        _meaningful_text(payload.get(field_name))
        for field_name in ("symptoms", "description", "title", "question")
    )
    if len(_tokens(symptom_text)) >= 4:
        return True
    symptom_words = {
        "meldet",
        "zeigt",
        "fehlt",
        "kein",
        "keine",
        "sporadisch",
        "stoppt",
        "steht",
        "blockiert",
        "druck",
        "temperatur",
        "vibration",
        "signal",
        "geraeusch",
        "leckt",
        "ausfall",
    }
    return bool(_tokens(context) & symptom_words)


def _has_previous_checks(payload, context):
    """Return whether previous checks or first actions are documented."""
    for field_name in ("previous_checks", "checks_done", "inspection", "diagnostics"):
        if _meaningful_text(payload.get(field_name)):
            return True
    check_words = {
        "geprueft",
        "pruefung",
        "kontrolliert",
        "getestet",
        "gemessen",
        "gereinigt",
        "reset",
        "neustart",
        "getauscht",
        "ausgetauscht",
        "sichtpruefung",
        "probelauf",
    }
    return bool(_tokens(context) & check_words)


def _has_affected_area(payload, context, user=None):
    """Return whether department, area or site context is available."""
    if any(
        _meaningful_text(payload.get(field_name))
        for field_name in ("department", "department_id", "affected_area", "area", "site")
    ):
        return True
    if user is not None and getattr(user, "department", None):
        return bool(_meaningful_text(getattr(user.department, "name", "")))
    return bool(
        re.search(
            r"\b(?:bereich|abteilung|werk|standort)\s*[:#-]?\s*[a-z0-9_-]+\b",
            context,
        )
    )


def _has_solution_outcome(payload, context):
    """Return whether the solution or current outcome is documented."""
    for field_name in ("solution_result", "outcome", "result", "resolution", "solution", "answer"):
        if len(_tokens(_meaningful_text(payload.get(field_name)))) >= 3:
            return True
    outcome_words = {
        "behoben",
        "geloest",
        "weiterhin",
        "ergebnis",
        "loesung",
        "massnahme",
        "funktioniert",
        "erfolgreich",
        "offen",
    }
    return bool(_tokens(context) & outcome_words)


def _meaningful_text(value):
    """Return stripped text unless it is a known placeholder."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    normalized = _normalize_text(text)
    placeholders = {
        "unknown",
        "unbekannt",
        "unbekannte maschine",
        "keine angabe",
        "n/a",
        "-",
    }
    return "" if normalized in placeholders else text


def _normalize_text(value):
    """Return lowercase ASCII-like text for local rule matching."""
    text = str(value or "").lower()
    replacements = {
        "\u00e4": "ae",
        "\u00f6": "oe",
        "\u00fc": "ue",
        "\u00df": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _tokens(value):
    """Return normalized content tokens for rule checks."""
    return {
        token
        for token in re.sub(r"[^a-z0-9_-]+", " ", _normalize_text(value)).split()
        if len(token) >= 3
    }
