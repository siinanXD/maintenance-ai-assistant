"""Thresholds, labels and small numeric helpers shared by the AI observability read models."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import ceil

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import KnowledgeDocument

DEFAULT_OBSERVABILITY_DAYS = 30


DEFAULT_OBSERVABILITY_LIMIT = 10


MAX_OBSERVABILITY_LIMIT = 50


LOW_SIMILARITY_THRESHOLD = 0.35


LOW_SCORE_THRESHOLD = 35.0


LOW_CONFIDENCE_SCORE_THRESHOLD = 45


NEGATIVE_RATINGS = {"not_helpful"}


CONFIGURATION_FAILURE_STATUSES = {
    "api_key_missing",
    "base_url_missing",
    "unsupported_provider",
}


STRUCTURED_DOMAIN_LABELS = {
    "tasks": "Tasks",
    "errors": "Stoerungen",
    "machines": "Maschinen",
    "vacations": "Urlaub",
    "employees": "Mitarbeiter",
    "documents": "Dokumente",
    "shiftplans": "Schichtplanung",
    "inventory": "Lager",
}


STRUCTURED_ENTITY_DOMAINS = {
    "tasks": "tasks",
    "task": "tasks",
    "incidents": "errors",
    "incident": "errors",
    "errors": "errors",
    "error": "errors",
    "machines": "machines",
    "machine": "machines",
    "vacations": "vacations",
    "vacation": "vacations",
    "employees": "employees",
    "employee": "employees",
    "documents": "documents",
    "document": "documents",
    "shiftplans": "shiftplans",
    "shiftplan": "shiftplans",
    "inventory": "inventory",
}


def is_at_or_after(value, since):
    """Return whether a possibly timezone-naive datetime is inside a window."""
    if not value:
        return False
    left = value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value
    right = since.replace(tzinfo=None) if getattr(since, "tzinfo", None) else since
    return left >= right


def source_age_days(value):
    """Return non-negative source age in whole days from an ISO timestamp."""
    source_time = _parse_iso_datetime(value)
    if source_time is None:
        return None
    now_value = utc_now()
    if getattr(now_value, "tzinfo", None):
        now_value = now_value.replace(tzinfo=None)
    return max(0, (now_value - source_time).days)


def _parse_iso_datetime(value):
    """Return a timezone-naive datetime parsed from an ISO timestamp."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if getattr(parsed, "tzinfo", None):
        parsed = parsed.replace(tzinfo=None)
    return parsed


def counter_rows(counter):
    """Return sorted counter rows."""
    return [{"key": key, "count": count} for key, count in Counter(counter).most_common()]


def normalized_question(message):
    """Return a stable grouping key for common question analysis."""
    return " ".join(str(message or "").lower().split())[:300]


def knowledge_title(document_id):
    """Return a knowledge document title for a source id if it still exists."""
    if document_id is None:
        return ""
    try:
        document = db.session.get(KnowledgeDocument, int(document_id))
    except (TypeError, ValueError):
        return ""
    return bounded(getattr(document, "title", ""), 180) if document else ""


def average(values):
    """Return a rounded arithmetic mean."""
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return 0
    return round(sum(numeric_values) / len(numeric_values), 4)


def average_from_total(total, count):
    """Return a rounded average from a total and count."""
    return round(total / count, 2) if count else None


def percentile(values, percentile):
    """Return a nearest-rank percentile."""
    numeric_values = sorted(float(value) for value in values if value is not None)
    if not numeric_values:
        return 0
    index = max(0, min(len(numeric_values) - 1, ceil(len(numeric_values) * percentile) - 1))
    return int(round(numeric_values[index]))


def rate(numerator, denominator):
    """Return a rounded ratio."""
    return round(numerator / denominator, 4) if denominator else 0


def bounded_rate(value):
    """Return a clamped zero-to-one rate for observability payloads."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, parsed)), 4)


def optional_int(value):
    """Return an optional integer value."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value):
    """Return an optional float value."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bounded_int(value, default, minimum, maximum):
    """Return a bounded integer value."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def bounded(value, max_chars):
    """Return normalized text bounded to max chars."""
    text = " ".join(str(value or "").strip().split())
    return text[:max_chars]
