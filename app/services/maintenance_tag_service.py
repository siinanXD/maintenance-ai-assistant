"""Maintenance tag taxonomy and local keyword suggestions."""

import re

from app.extensions import db
from app.models import AssistantTrainingEntry

TAG_LIBRARY_VERSION = "maintenance-tags-v1"
TAG_LIBRARY_CATEGORY = "maintenance_tags"

GERMAN_TRANSLATION = str.maketrans(
    {
        "\u00e4": "ae",
        "\u00f6": "oe",
        "\u00fc": "ue",
        "\u00df": "ss",
        "\u00c4": "Ae",
        "\u00d6": "Oe",
        "\u00dc": "Ue",
    }
)

STOPWORDS = {
    "aber",
    "alle",
    "als",
    "am",
    "an",
    "auf",
    "bei",
    "das",
    "dem",
    "den",
    "der",
    "die",
    "ein",
    "eine",
    "fuer",
    "im",
    "in",
    "ist",
    "mit",
    "nach",
    "oder",
    "und",
    "von",
    "zu",
    "zur",
}

MAINTENANCE_TAG_CATEGORIES = (
    {
        "key": "fault_type",
        "label": "Fehlerarten",
        "tags": (
            {
                "key": "sensor_fault",
                "label": "Sensorikfehler",
                "keywords": (
                    "sensor",
                    "signal",
                    "geber",
                    "lichtschranke",
                    "initiator",
                    "naeherschalter",
                    "barcode",
                    "scanner",
                ),
            },
            {
                "key": "drive_overload",
                "label": "Antrieb ueberlastet",
                "keywords": (
                    "motor",
                    "antrieb",
                    "ueberlast",
                    "frequenzumrichter",
                    "servo",
                    "achse",
                    "lagerreibung",
                ),
            },
            {
                "key": "pressure_loss",
                "label": "Druckverlust",
                "keywords": (
                    "druck",
                    "druckverlust",
                    "unterdruck",
                    "vakuum",
                    "kompressor",
                    "hydraulikdruck",
                    "leckage",
                ),
            },
            {
                "key": "temperature_deviation",
                "label": "Temperaturabweichung",
                "keywords": (
                    "temperatur",
                    "heizzone",
                    "heizkreis",
                    "kuehlung",
                    "kuehlkreis",
                    "ueberhitzt",
                ),
            },
            {
                "key": "communication_fault",
                "label": "Kommunikationsfehler",
                "keywords": (
                    "kommunikation",
                    "sps",
                    "netzwerk",
                    "bus",
                    "ip",
                    "steuerung",
                    "koppler",
                ),
            },
            {
                "key": "safety_fault",
                "label": "Sicherheitskreis",
                "keywords": (
                    "not halt",
                    "nothalt",
                    "schutzzaun",
                    "tuerkontakt",
                    "sicherheitsrelais",
                    "verriegelung",
                    "zuhaltung",
                ),
            },
            {
                "key": "material_flow",
                "label": "Materialfluss",
                "keywords": (
                    "materialstau",
                    "stau",
                    "foerderband",
                    "bandlauf",
                    "fuellstand",
                    "kanban",
                    "material",
                ),
            },
            {
                "key": "quality_deviation",
                "label": "Qualitaetsabweichung",
                "keywords": (
                    "qualitaet",
                    "nio",
                    "pruefergebnis",
                    "toleranz",
                    "kalibrierung",
                    "messwert",
                    "prozessdrift",
                ),
            },
        ),
    },
    {
        "key": "cause",
        "label": "Ursachen",
        "tags": (
            {
                "key": "electrical",
                "label": "Elektrisch",
                "keywords": (
                    "kabel",
                    "kabelbruch",
                    "spannung",
                    "kontakt",
                    "leitung",
                    "strom",
                    "sicherung",
                ),
            },
            {
                "key": "mechanical",
                "label": "Mechanisch",
                "keywords": (
                    "lager",
                    "verschleiss",
                    "spiel",
                    "mechanik",
                    "verspannung",
                    "blockiert",
                    "riss",
                ),
            },
            {
                "key": "hydraulic",
                "label": "Hydraulisch",
                "keywords": (
                    "hydraulik",
                    "zylinder",
                    "ventil",
                    "oel",
                    "schlauch",
                    "verschraubung",
                    "dichtung",
                ),
            },
            {
                "key": "pneumatic",
                "label": "Pneumatisch",
                "keywords": (
                    "pneumatik",
                    "druckluft",
                    "luftfilter",
                    "ableiter",
                    "trockner",
                    "magnetventil",
                ),
            },
            {
                "key": "contamination",
                "label": "Verschmutzung",
                "keywords": (
                    "verschmutzt",
                    "verschmutzung",
                    "filter",
                    "linse",
                    "kontakte",
                    "reinigen",
                    "schmutz",
                ),
            },
            {
                "key": "configuration",
                "label": "Parametrierung",
                "keywords": (
                    "parameter",
                    "rezept",
                    "sollwert",
                    "offset",
                    "parametrierung",
                    "referenzfahrt",
                    "software",
                ),
            },
        ),
    },
    {
        "key": "solution",
        "label": "Loesungen",
        "tags": (
            {
                "key": "clean",
                "label": "Reinigen",
                "keywords": ("reinigen", "saeubern", "filter reinigen", "linse reinigen"),
            },
            {
                "key": "inspect_measure",
                "label": "Pruefen und messen",
                "keywords": (
                    "pruefen",
                    "messen",
                    "sichtpruefung",
                    "diagnose",
                    "durchgang",
                    "messzange",
                ),
            },
            {
                "key": "adjust",
                "label": "Einstellen",
                "keywords": (
                    "einstellen",
                    "nachjustieren",
                    "abstand",
                    "sollwert",
                    "parameter",
                    "kalibrieren",
                ),
            },
            {
                "key": "replace",
                "label": "Tauschen",
                "keywords": (
                    "tauschen",
                    "wechseln",
                    "ersetzen",
                    "austausch",
                    "lager tauschen",
                    "filter wechseln",
                ),
            },
            {
                "key": "refill_lubricate",
                "label": "Nachfuellen und schmieren",
                "keywords": (
                    "nachfuellen",
                    "schmieren",
                    "oelwechsel",
                    "schmierfett",
                    "befuellen",
                ),
            },
            {
                "key": "test_document",
                "label": "Testlauf dokumentieren",
                "keywords": (
                    "probelauf",
                    "testlauf",
                    "dokumentieren",
                    "protokoll",
                    "freigeben",
                    "nachweis",
                ),
            },
        ),
    },
    {
        "key": "machine_area",
        "label": "Maschinenbereiche",
        "tags": (
            {
                "key": "sensorics",
                "label": "Sensorik",
                "keywords": ("sensor", "geber", "scanner", "lichtschranke", "initiator"),
            },
            {
                "key": "drive_train",
                "label": "Antrieb",
                "keywords": ("motor", "antrieb", "servo", "achse", "spindel", "lager"),
            },
            {
                "key": "hydraulics",
                "label": "Hydraulik",
                "keywords": ("hydraulik", "zylinder", "ventil", "oel", "presse"),
            },
            {
                "key": "pneumatics",
                "label": "Pneumatik",
                "keywords": ("pneumatik", "druckluft", "kompressor", "vakuum"),
            },
            {
                "key": "controls",
                "label": "Steuerung",
                "keywords": ("sps", "steuerung", "netzwerk", "bus", "rezept"),
            },
            {
                "key": "safety",
                "label": "Sicherheit",
                "keywords": ("not halt", "nothalt", "schutzzaun", "sicherheit", "tuerkontakt"),
            },
            {
                "key": "material_handling",
                "label": "Foerdertechnik",
                "keywords": ("foerderband", "band", "materialfluss", "stau", "kanban"),
            },
            {
                "key": "heating_cooling",
                "label": "Heizen/Kuehlen",
                "keywords": ("heizzone", "heizkreis", "kuehlung", "kuehlkreis", "temperatur"),
            },
        ),
    },
    {
        "key": "risk_priority",
        "label": "Risiko/Prioritaet",
        "tags": (
            {
                "key": "critical_risk",
                "label": "Kritisch",
                "keywords": (
                    "kritisch",
                    "stillstand",
                    "sicherheit",
                    "not halt",
                    "nothalt",
                    "ausfall",
                    "urgent",
                ),
            },
            {
                "key": "high_priority",
                "label": "Hoch",
                "keywords": (
                    "hoch",
                    "dringend",
                    "eilig",
                    "stoerung",
                    "produktionsverlust",
                    "soon",
                ),
            },
            {
                "key": "normal_priority",
                "label": "Normal",
                "keywords": ("normal", "routine", "wartung", "pruefung", "geplant"),
            },
            {
                "key": "low_risk",
                "label": "Niedrig",
                "keywords": ("niedrig", "hinweis", "beobachten", "dokumentation"),
            },
        ),
    },
)


def suggest_tags_for_error_payload(data):
    """Return tag suggestions for an error catalog payload."""
    return suggest_maintenance_tags(
        data,
        source_type="error_entry",
        fields=(
            "machine",
            "error_code",
            "title",
            "description",
            "possible_causes",
            "solution",
            "severity",
            "cause_category",
            "impact",
        ),
    )


def suggest_tags_for_task_payload(data):
    """Return tag suggestions for a task payload."""
    return suggest_maintenance_tags(
        data,
        source_type="task",
        fields=(
            "title",
            "description",
            "priority",
            "status",
            "blocked_reason",
            "department",
            "machine",
            "text",
        ),
    )


def suggest_tags_for_knowledge_payload(data):
    """Return tag suggestions for a manual or generated knowledge payload."""
    return suggest_maintenance_tags(
        data,
        source_type="knowledge",
        fields=(
            "title",
            "question",
            "answer",
            "keywords",
            "category",
            "department",
            "description",
            "solution",
        ),
    )


def suggest_maintenance_tags(data, source_type="generic", fields=None, limit_per_category=4):
    """Return local keyword-based tag suggestions for a payload."""
    text = _payload_text(data, fields)
    tokens = _tokenize(text)
    suggestions = []
    if not tokens and not text:
        return _suggestion_result(source_type, suggestions)

    for category in MAINTENANCE_TAG_CATEGORIES:
        for tag in category["tags"]:
            matched_terms = _matched_keywords(tag["keywords"], text, tokens)
            if not matched_terms:
                continue
            suggestions.append(
                {
                    "category": category["key"],
                    "category_label": category["label"],
                    "tag": tag["key"],
                    "label": tag["label"],
                    "score": _tag_score(matched_terms, source_type, category["key"]),
                    "matched_terms": matched_terms,
                    "source": "maintenance_tag_library",
                }
            )

    suggestions.sort(key=lambda item: (-item["score"], item["category"], item["label"]))
    suggestions = _limit_by_category(suggestions, limit_per_category)
    return _suggestion_result(source_type, suggestions)


def seed_maintenance_tag_library(created_by=None):
    """Seed missing maintenance tag taxonomy entries as manual AI training data."""
    entries = maintenance_tag_training_entries(created_by=created_by)
    existing = {
        entry.title: entry
        for entry in AssistantTrainingEntry.query.filter_by(
            category=TAG_LIBRARY_CATEGORY,
        ).all()
    }
    created = 0
    registered = 0
    for payload in entries:
        entry = existing.get(payload["title"])
        if entry:
            registered += _ensure_training_entry_registered(entry)
            continue
        entry = AssistantTrainingEntry(**payload)
        db.session.add(entry)
        db.session.flush()
        registered += _ensure_training_entry_registered(entry)
        created += 1
    db.session.flush()
    return {
        "category": TAG_LIBRARY_CATEGORY,
        "created": created,
        "registered": registered,
        "expected": len(entries),
    }


def maintenance_tag_training_entries(created_by=None):
    """Return seed payloads for the maintenance tag knowledge library."""
    entries = []
    for category in MAINTENANCE_TAG_CATEGORIES:
        tags = list(category["tags"])
        labels = ", ".join(tag["label"] for tag in tags)
        keywords = _category_keywords(category)
        entries.append(
            {
                "title": f"Tag-Bibliothek: {category['label']}",
                "question": (
                    "Welche Maintenance-Stichwoerter gehoeren zur Kategorie "
                    f"{category['label']}?"
                ),
                "answer": (
                    f"Die Kategorie {category['label']} buendelt typische Tags: "
                    f"{labels}. Nutze sie fuer Fehler, Tasks und Knowledge-Drafts, "
                    "wenn passende Begriffe im Text erkannt werden."
                ),
                "keywords": ", ".join(keywords),
                "category": TAG_LIBRARY_CATEGORY,
                "department": "",
                "is_active": True,
                "priority": 90,
                "created_by": created_by,
            }
        )
    return entries


def _ensure_training_entry_registered(entry):
    """Ensure a seeded training entry has a pending knowledge document."""
    from app.services.knowledge_service import mark_training_entry_knowledge_stale, source_document

    if source_document("manual_training", entry.id):
        return 0
    mark_training_entry_knowledge_stale(entry)
    return 1


def _category_keywords(category):
    """Return unique keywords for one category in stable order."""
    keywords = []
    seen = set()
    for tag in category["tags"]:
        for keyword in tag["keywords"]:
            normalized = str(keyword).strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            keywords.append(normalized)
    return keywords


def _payload_text(data, fields=None):
    """Return normalized searchable text from a payload or raw string."""
    if isinstance(data, str):
        return _normalize_text(data)
    if not isinstance(data, dict):
        return ""

    selected_fields = fields or data.keys()
    values = []
    for field_name in selected_fields:
        value = data.get(field_name)
        if isinstance(value, dict):
            values.extend(str(item) for item in value.values())
        elif isinstance(value, list | tuple | set):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return _normalize_text(" ".join(values))


def _normalize_text(value):
    """Normalize German maintenance text for deterministic keyword matching."""
    text = str(value or "").translate(GERMAN_TRANSLATION).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokenize(text):
    """Return relevant tokens from normalized text."""
    return {
        token for token in str(text or "").split() if len(token) >= 3 and token not in STOPWORDS
    }


def _matched_keywords(keywords, text, tokens):
    """Return matched keywords for one tag."""
    matches = []
    for keyword in keywords:
        normalized = _normalize_text(keyword)
        if not normalized:
            continue
        if " " in normalized and normalized in text:
            matches.append(keyword)
            continue
        if normalized in tokens:
            matches.append(keyword)
    return matches


def _tag_score(matched_terms, source_type, category_key):
    """Return a stable 0-100 confidence score for a tag match."""
    base_score = 50 + (len(matched_terms) * 12)
    if source_type in {"error_entry", "knowledge"}:
        base_score += 5
    if category_key == "risk_priority":
        base_score += 5
    return min(100, base_score)


def _limit_by_category(suggestions, limit_per_category):
    """Limit suggestions per category while preserving score order."""
    counts = {}
    limited = []
    for suggestion in suggestions:
        category = suggestion["category"]
        counts[category] = counts.get(category, 0) + 1
        if counts[category] > limit_per_category:
            continue
        limited.append(suggestion)
    return limited


def _suggestion_result(source_type, suggestions):
    """Return the public suggestion payload."""
    by_category = {}
    for suggestion in suggestions:
        by_category.setdefault(suggestion["category"], []).append(suggestion)
    return {
        "status": "suggested" if suggestions else "empty",
        "source_type": source_type,
        "provider": "local_keywords",
        "taxonomy_version": TAG_LIBRARY_VERSION,
        "items": suggestions,
        "by_category": by_category,
    }
