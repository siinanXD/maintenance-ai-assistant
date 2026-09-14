"""Thresholds, window bounds and value helpers shared by the retrieval telemetry modules."""

from __future__ import annotations

import json
from math import ceil

from flask import current_app, has_app_context

from app.extensions import db
from app.models import KnowledgeDocument
from app.services.ai_confidence_service import LOW_CONFIDENCE_THRESHOLD

DEFAULT_WINDOW_DAYS = 30


DEFAULT_LIMIT = 10


DEFAULT_LOW_CONFIDENCE_SCORE = LOW_CONFIDENCE_THRESHOLD


DEFAULT_LOW_SOURCE_SCORE = 20.0


MAX_LIMIT = 50


POSITIVE_RATINGS = {"helpful"}


PARTIAL_RATINGS = {"partially_helpful"}


NEGATIVE_RATINGS = {"not_helpful"}


SLO_THRESHOLDS = {
    "retrieval_p95_ms": {"warning": 1200, "critical": 3000},
    "no_source_rate": {"warning": 0.2, "critical": 0.4},
    "low_confidence_rate": {"warning": 0.2, "critical": 0.4},
    "permission_filtered_candidate_count": {"warning": 3, "critical": 10},
    "negative_feedback_rate": {"warning": 0.15, "critical": 0.3},
    "safety_risk_count": {"warning": 1, "critical": 5},
    "fallback_rate": {"warning": 0.25, "critical": 0.5},
    "vector_sync_failure_count": {"warning": 1, "critical": 3},
    "stale_index_count": {"warning": 1, "critical": 5},
    "source_metadata_missing_rate": {"warning": 0.1, "critical": 0.25},
    "atlas_errors": {"warning": 1, "critical": 3},
    "atlas_fallbacks": {"warning": 1, "critical": 1},
    "atlas_sync_failures": {"warning": 1, "critical": 3},
    "atlas_reindex_required": {"warning": 1, "critical": 2},
}


ESSENTIAL_SOURCE_METADATA_FIELDS = (
    "source_type",
    "source_id",
    "module",
    "role_visibility",
    "created_at",
)


def event_sources(event):
    """Return prompt-safe retrieval source references stored on one audit event."""
    explainability = event.retrieval_explainability()
    if not isinstance(explainability, dict):
        return []
    sources = explainability.get("sources") or []
    return [source for source in sources if isinstance(source, dict)]


def source_has_metadata_gap(source):
    """Return whether one retrieved source lacks essential public metadata."""
    return bool(missing_source_metadata_fields(source))


def missing_source_metadata_fields(source):
    """Return essential metadata fields missing from one retrieved source."""
    normalized = {
        "source_type": source.get("source_type") or source.get("type"),
        "source_id": source.get("source_id") or source.get("id"),
        "module": source.get("module"),
        "role_visibility": source.get("role_visibility"),
        "created_at": source.get("created_at"),
    }
    return [
        field
        for field in ESSENTIAL_SOURCE_METADATA_FIELDS
        if not _has_metadata_value(normalized.get(field))
    ]


def _has_metadata_value(value):
    """Return whether a metadata value is populated without rejecting zero IDs."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def compute_percentile(values, percentile):
    """Return a nearest-rank percentile from optional numeric values."""
    numeric_values = sorted(value for value in values if value is not None)
    if not numeric_values:
        return 0
    index = max(0, min(len(numeric_values) - 1, ceil(len(numeric_values) * percentile) - 1))
    return int(round(numeric_values[index]))


def rate(numerator, denominator):
    """Return a rounded ratio or zero for an empty denominator."""
    return round(numerator / denominator, 4) if denominator else 0.0


def chunk_block_kinds(metadata):
    """Return bounded chunk block kinds from stored chunk metadata."""
    raw_value = str((metadata or {}).get("chunk_block_kinds") or "")
    return [bounded_string(kind.strip(), 40) for kind in raw_value.split(",") if kind.strip()]


def metadata_int_values(metadata_rows, key):
    """Return parsed integer metadata values for one content-safe metric key."""
    values = []
    for metadata in metadata_rows:
        parsed = optional_int(metadata.get(key))
        if parsed is not None:
            values.append(parsed)
    return values


def event_reference(event):
    """Return metadata-only event reference for admin drill-down."""
    return {
        "id": event.id,
        "workflow": event.workflow,
        "status": event.status,
        "source_count": event.source_count,
        "confidence_score": event.confidence_score,
        "confidence_level": event.confidence_level,
        "error_category": event.error_category,
        "created_at": event.created_at.isoformat(),
    }


def feedback_reference(feedback):
    """Return metadata-only feedback reference for admin drill-down."""
    return {
        "id": feedback.id,
        "chat_message_id": feedback.chat_message_id,
        "audit_event_id": feedback.audit_event_id,
        "response_type": feedback.response_type,
        "source_count": feedback.source_count,
        "review_status": feedback.review_status,
        "created_at": feedback.created_at.isoformat(),
    }


def db_get_knowledge_document(document_id):
    """Return a knowledge document by id without raising for missing rows."""
    try:
        return db.session.get(KnowledgeDocument, int(document_id))
    except (TypeError, ValueError):
        return None


def is_error_event(event):
    """Return whether an audit event represents an unsuccessful AI execution."""
    status = str(event.status or "").lower()
    return bool(event.error_category) or "error" in status or "failed" in status


def counter_payload(counter, limit=5):
    """Return a sorted counter payload."""
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def normalize_window_days(value):
    """Return a bounded telemetry window in days."""
    default = _config_int("RETRIEVAL_TELEMETRY_WINDOW_DAYS", DEFAULT_WINDOW_DAYS)
    return _bounded_int(value, default=default, minimum=1, maximum=365)


def normalize_limit(value):
    """Return a bounded result limit."""
    default = _config_int("RETRIEVAL_TELEMETRY_LIMIT", DEFAULT_LIMIT)
    return _bounded_int(value, default=default, minimum=1, maximum=MAX_LIMIT)


def low_confidence_score():
    """Return the low-confidence threshold used for unsuccessful question telemetry."""
    return _bounded_int(
        _config_int(
            "RETRIEVAL_TELEMETRY_LOW_CONFIDENCE_SCORE",
            DEFAULT_LOW_CONFIDENCE_SCORE,
        ),
        default=DEFAULT_LOW_CONFIDENCE_SCORE,
        minimum=0,
        maximum=100,
    )


def low_source_score():
    """Return the low-source-score threshold used for poor source telemetry."""
    return _config_float("RETRIEVAL_TELEMETRY_LOW_SOURCE_SCORE", DEFAULT_LOW_SOURCE_SCORE)


def _config_int(name, default):
    """Return an integer config value."""
    value = current_app.config.get(name, default) if has_app_context() else default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_float(name, default):
    """Return a float config value."""
    value = current_app.config.get(name, default) if has_app_context() else default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded_int(value, default, minimum, maximum):
    """Return an integer clamped to a closed range."""
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def json_list(value):
    """Return a JSON-list database value as a list of strings."""
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item not in (None, "")]


def average(values):
    """Return a rounded arithmetic mean for numeric telemetry values."""
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return 0
    return round(sum(numeric_values) / len(numeric_values), 4)


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


def bounded_string(value, max_length):
    """Return a stripped string bounded for public analytics payloads."""
    return str(value or "").strip()[:max_length]
