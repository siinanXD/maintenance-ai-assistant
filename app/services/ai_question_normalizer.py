"""Shared normalization helpers for AI maintenance questions."""

from __future__ import annotations

import re

from flask import has_app_context

from app.models import Department

FOLLOW_UP_PATTERNS = (
    "und welche",
    "welche davon",
    "wie viele davon",
    "nur die offenen",
    "nur die dringenden",
    "die von gestern",
    "die kritischen",
    "davon",
    "noch offen",
)
STATUS_TERMS = {
    "open": (
        "offen",
        "offene",
        "offenen",
        "open",
        "ausstehend",
        "ausstehende",
        "steht aus",
        "stehen aus",
        "unerledigt",
    ),
    "in_progress": ("in bearbeitung", "in arbeit", "aktive", "aktiv"),
    "done": ("beendet", "geschlossen", "erledigt", "abgeschlossen", "closed", "done"),
}
TASK_STATUS_TERMS = {
    "in_progress": ("in bearbeitung", "in arbeit"),
    "done": ("beendet", "geschlossen", "erledigt", "abgeschlossen"),
    "open": (
        "offen",
        "ausstehend",
        "ausstehende",
        "steht aus",
        "stehen aus",
        "unerledigt",
    ),
}
SEVERITY_TERMS = {
    "critical": ("kritisch", "kritische", "critical"),
}
MY_AREA_TERMS = (
    "mein bereich",
    "meinem bereich",
    "meine abteilung",
    "meiner abteilung",
    "unserem bereich",
)


def contains_lookup_term(text, term):
    """Return whether normalized text contains one lookup term as a word or phrase."""
    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term or "-" in normalized_term:
        return normalized_term in normalized_text
    return bool(re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_text))


def contains_any_lookup_term(text, terms):
    """Return whether normalized text contains any lookup term as a word or phrase."""
    return any(contains_lookup_term(text, term) for term in terms)


def normalize_text(value, strip_punctuation=True):
    """Return lowercase lookup text normalized for German maintenance questions."""
    text = " ".join(str(value or "").lower().split())
    replacements = {
        "\u00e4": "ae",
        "\u00f6": "oe",
        "\u00fc": "ue",
        "\u00df": "ss",
        "\u00c3\u00a4": "ae",
        "\u00c3\u00b6": "oe",
        "\u00c3\u00bc": "ue",
        "\u00c3\u009f": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    if strip_punctuation:
        text = re.sub(r"[^\w\s-]+", " ", text)
        return " ".join(text.split())
    return text


def detect_status(value, terms=None):
    """Return a normalized lifecycle status mentioned in a question."""
    text = normalize_text(value)
    status_terms = terms or STATUS_TERMS
    for status, aliases in status_terms.items():
        if any(alias in text for alias in aliases):
            return status
    return ""


def detect_severity(value):
    """Return a normalized severity mentioned in a question."""
    text = normalize_text(value)
    for severity, aliases in SEVERITY_TERMS.items():
        if any(alias in text for alias in aliases):
            return severity
    return ""


def detect_time_range(value):
    """Return the supported relative time range mentioned in a question."""
    text = normalize_text(value)
    if "gestern" in text:
        return "yesterday"
    if "heute" in text:
        return "today"
    return ""


def detect_department(value):
    """Return a department name mentioned in a question."""
    if not has_app_context():
        return ""
    text = normalize_text(value)
    for department in Department.query.order_by(Department.name.asc()).all():
        normalized_name = normalize_text(department.name)
        if re.search(rf"(?<!\w){re.escape(normalized_name)}(?!\w)", text):
            return department.name
    return ""


def mentions_my_area(value):
    """Return whether a question asks for the user's own department or area."""
    text = normalize_text(value)
    return any(term in text for term in MY_AREA_TERMS)


def is_structured_follow_up(value):
    """Return whether a question asks to refine the previous structured scope."""
    text = normalize_text(value)
    return any(pattern in text for pattern in FOLLOW_UP_PATTERNS)


ERROR_QUESTION_TERMS = ("fehler", "stoerung", "error", "fehlercode", "ursache")
ERROR_CODE_TOKEN = re.compile(r"\b[A-Z]{0,3}\d{2,5}\b")


def mentions_error_question(value):
    """Return whether a question asks for fault or error-catalog help."""
    text = normalize_text(value)
    if any(term in text for term in ERROR_QUESTION_TERMS):
        return True
    match = ERROR_CODE_TOKEN.search(str(value or "").upper())
    if not match:
        return False
    token = match.group(0)
    if any(char.isalpha() for char in token):
        return True
    return not (1900 <= int(token) <= 2099)


SCOPE_KEYWORDS = {
    "tasks": ("task", "tasks", "aufgabe", "aufgaben", "arbeit", "arbeiten", "todo"),
    "errors": (
        "fehler",
        "stoerung",
        "stoerungen",
        "stoerfall",
        "stoerfaelle",
        "problem",
        "probleme",
        "error",
        "fehlercode",
        "ursache",
        "not-halt",
        "not halt",
        "not-aus",
        "sicherheitskreis",
    ),
    "employees": (
        "mitarbeiter",
        "personal",
        "personaldaten",
        "gehalt",
        "gehaltsklasse",
        "adresse",
        "geburtsdatum",
        "qualifikation",
    ),
    "machines": (
        "maschine",
        "maschinen",
        "anlage",
        "anlagen",
        "machine",
        "wartungsplan",
        "wartungsplaene",
        "maintenance",
    ),
    "inventory": ("lager", "bestand", "material", "materialien", "ersatzteil", "inventory"),
    "documents": (
        "dokument",
        "dokumente",
        "unterlage",
        "unterlagen",
        "doku",
        "bericht",
        "berichte",
        "report",
    ),
    "shiftplans": ("schichtplan", "schichtplanung", "dienstplan", "schicht"),
    "admin_users": ("user", "users", "nutzer", "benutzer", "accounts"),
}
TODAY_TERMS = ("heute", "heutige", "heutigen", "today", "anstehend")


def detect_requested_scopes(value):
    """Return dashboard scopes explicitly referenced by a question (retrieval hints)."""
    text = normalize_text(value)
    scopes = {
        scope
        for scope, keywords in SCOPE_KEYWORDS.items()
        if contains_any_lookup_term(text, keywords)
    }
    if mentions_error_question(value) and ERROR_CODE_TOKEN.search(str(value or "").upper()):
        scopes.add("errors")
    if contains_any_lookup_term(text, SCOPE_KEYWORDS["tasks"]) and any(
        term in text for term in TODAY_TERMS
    ):
        scopes.add("tasks")
    return scopes
