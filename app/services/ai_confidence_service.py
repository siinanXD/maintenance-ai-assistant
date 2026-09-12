"""Transparent confidence scoring for AI answers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.models import AIFeedback

DEFAULT_CONFIDENCE_WEIGHTS = {
    "source_count": 0.18,
    "retrieval_score": 0.22,
    "quality": 0.18,
    "consistency": 0.14,
    "machine_relevance": 0.14,
    "feedback": 0.14,
}
QUALITY_STATUS_SIGNALS = {
    "admin_approved": 1.0,
    "technician_confirmed": 0.95,
    "ai_suggested": 0.62,
    "draft": 0.35,
    "outdated": 0.45,
    "low_quality": 0.18,
    "duplicate": 0.14,
    "rejected": 0.0,
}
STRUCTURED_SOURCE_QUALITY_SIGNAL = 0.74
NO_FEEDBACK_SIGNAL = 0.58
LOW_CONFIDENCE_THRESHOLD = 45
HIGH_CONFIDENCE_THRESHOLD = 70
LOW_CONFIDENCE_NOTICE = (
    "## Niedrige Confidence\n"
    "- **Hinweis:** Die Antwort basiert auf wenigen, schwachen oder "
    "nicht eindeutig passenden Quellen. Bitte fachlich pruefen.\n\n"
)
LOW_CONFIDENCE_RESPONSE_TYPES = {"assistant", "error_help", "general_chat"}
SAFETY_NOTICE_HEADING = "## Sicherheitshinweis"
LOCAL_ANSWER_EXCLUDED_CONFIDENCE_TYPES = frozenset(
    {
        "permission_denied",
        "general_chat",
        "order_plan",
    }
)
HIGH_CONFIDENCE_STRUCTURED_RESPONSE_TYPES = frozenset(
    {
        "employee_document_count",
        "employee_document_list",
        "employee_stored_document_count",
        "employee_stored_document_list",
        "employee_count",
        "employee_list",
        "employee_department_count",
        "employee_department_list",
        "employee_available",
        "employee_absences",
        "employee_team_lead_unavailable",
        "inventory_count",
        "inventory_low_stock",
        "inventory_critical",
        "inventory_machine_materials",
        "shiftplan_shift_count",
        "shiftplan_entries",
        "shiftplan_understaffed",
        "document_recent",
        "document_outdated",
        "document_this_week",
        "document_department_list",
        "document_machine_list",
        "vacation_pending_count",
        "vacation_pending_list",
        "vacation_own_pending",
        "vacation_own_status",
        "vacation_absences",
        "machine_downtime",
        "machine_incidents",
        "structured_scope",
        "tasks_today",
        "tasks_status",
        "daily_briefing",
    }
)
STRUCTURED_SQL_CONFIDENCE_SCORE = 88


@dataclass(frozen=True)
class ConfidenceResult:
    """Computed confidence score with transparent factor contributions."""

    score: int
    level: str
    factors: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    warning: str = ""

    def to_dict(self):
        """Return a JSON-serializable confidence payload."""
        return {
            "score": self.score,
            "level": self.level,
            "warning": self.warning,
            "factors": dict(self.factors),
            "contributions": dict(self.contributions),
            "reasons": list(self.reasons),
            "method": (
                "Source-based confidence from retrieval, quality, consistency, "
                "machine context, and feedback. This is not hallucination detection."
            ),
        }


def attach_confidence_to_result(message, result):
    """Compute confidence for a chat result and attach diagnostics safely."""
    result = result if isinstance(result, dict) else {"answer": result}
    diagnostics = result.setdefault("diagnostics", {})
    confidence = calculate_ai_confidence(
        message=message,
        sources=result.get("sources") or [],
        response_type=result.get("type", "assistant"),
        result=result,
    )
    payload = confidence.to_dict()
    diagnostics["confidence"] = payload
    diagnostics["confidence_score"] = confidence.score
    diagnostics["confidence_level"] = confidence.level
    result["confidence"] = payload
    if should_mark_low_confidence(result, confidence):
        result["answer"] = mark_low_confidence_answer(result.get("answer"))
    return result


def calculate_ai_confidence(message, sources, response_type="assistant", result=None):
    """Return a transparent confidence score for one AI answer context."""
    safe_type = str(response_type or "assistant")
    if uses_structured_sql_confidence(safe_type, result):
        return _structured_sql_confidence(safe_type)
    safe_sources = [source for source in sources if isinstance(source, dict)]
    weights = _confidence_weights()
    factors = {
        "source_count": _source_count_signal(safe_sources),
        "retrieval_score": _retrieval_score_signal(safe_sources),
        "quality": _quality_signal(safe_sources),
        "consistency": _consistency_signal(safe_sources),
        "machine_relevance": _machine_relevance_signal(message, safe_sources),
        "feedback": _feedback_signal(safe_sources, response_type),
    }
    contributions = {
        key: round(factors[key] * weights[key] * 100, 2) for key in DEFAULT_CONFIDENCE_WEIGHTS
    }
    score = int(round(sum(contributions.values())))
    score = max(0, min(100, score))
    level = _confidence_level(score)
    return ConfidenceResult(
        score=score,
        level=level,
        factors={key: round(value, 4) for key, value in factors.items()},
        contributions=contributions,
        reasons=_confidence_reasons(factors, safe_sources),
        warning=_confidence_warning(level),
    )


def should_mark_low_confidence(result, confidence):
    """Return whether an answer should be visibly marked as low confidence."""
    response_type = str(result.get("type") or "assistant")
    answer = str(result.get("answer") or "")
    return (
        confidence.level == "low"
        and response_type in LOW_CONFIDENCE_RESPONSE_TYPES
        and not answer.startswith(LOW_CONFIDENCE_NOTICE.strip())
        # A leading safety notice (e.g. a redacted answer) already carries the
        # stronger warning; do not push it below a confidence marker.
        and not answer.startswith(SAFETY_NOTICE_HEADING)
    )


def mark_low_confidence_answer(answer):
    """Return an answer prefixed with a low-confidence notice."""
    return f"{LOW_CONFIDENCE_NOTICE}{str(answer or '').strip()}".strip()


def uses_structured_sql_confidence(response_type, result=None):
    """Return whether a response should use high-confidence structured SQL scoring."""
    safe_type = str(response_type or "assistant")
    if safe_type in HIGH_CONFIDENCE_STRUCTURED_RESPONSE_TYPES:
        return True
    if safe_type in LOW_CONFIDENCE_RESPONSE_TYPES:
        return False
    if safe_type in LOCAL_ANSWER_EXCLUDED_CONFIDENCE_TYPES:
        return False
    if isinstance(result, dict):
        diagnostics = result.get("diagnostics") or {}
        if diagnostics.get("status") == "local_answer":
            return True
    return False


def _structured_sql_confidence(response_type):
    """Return a high-confidence result for permission-filtered structured SQL answers."""
    return ConfidenceResult(
        score=STRUCTURED_SQL_CONFIDENCE_SCORE,
        level="high",
        factors={
            "source_count": 1.0,
            "retrieval_score": 1.0,
            "quality": 1.0,
            "consistency": 1.0,
            "machine_relevance": 1.0,
            "feedback": NO_FEEDBACK_SIGNAL,
        },
        contributions={key: 0.0 for key in DEFAULT_CONFIDENCE_WEIGHTS},
        reasons=[
            "Antwort basiert auf strukturierten App-Daten (SQL), nicht auf Modellwissen.",
            f"Antworttyp: {response_type}.",
        ],
        warning="",
    )


def _confidence_weights():
    """Return normalized configurable confidence weights."""
    configured = {}
    if has_app_context():
        configured = current_app.config.get("AI_CONFIDENCE_WEIGHTS", {}) or {}
    weights = dict(DEFAULT_CONFIDENCE_WEIGHTS)
    for key in DEFAULT_CONFIDENCE_WEIGHTS:
        if key in configured:
            weights[key] = _float_value(configured[key], DEFAULT_CONFIDENCE_WEIGHTS[key])
    total = sum(max(value, 0.0) for value in weights.values())
    if total <= 0:
        return DEFAULT_CONFIDENCE_WEIGHTS
    return {key: max(value, 0.0) / total for key, value in weights.items()}


def _source_count_signal(sources):
    """Return a normalized signal for the number of relevant sources."""
    count = len(_relevant_sources(sources))
    if count <= 0:
        return 0.0
    if count == 1:
        return 0.45
    if count == 2:
        return 0.78
    return 1.0


def _retrieval_score_signal(sources):
    """Return a normalized signal from average retrieval score."""
    scores = [_float_value(source.get("score"), 0.0) for source in _relevant_sources(sources)]
    if not scores:
        return 0.0
    average_score = sum(scores) / len(scores)
    return _clamp(average_score / 100.0, 0.0, 1.0)


def _quality_signal(sources):
    """Return a normalized signal from source quality statuses."""
    relevant_sources = _relevant_sources(sources)
    if not relevant_sources:
        return 0.0
    values = [_source_quality_signal(source) for source in relevant_sources]
    return sum(values) / len(values)


def _consistency_signal(sources):
    """Return a transparent consistency signal across retrieved sources."""
    relevant_sources = _relevant_sources(sources)
    if not relevant_sources:
        return 0.0
    if len(relevant_sources) == 1:
        return 0.55

    type_signal = _type_agreement_signal(relevant_sources)
    score_signal = _score_closeness_signal(relevant_sources)
    return _clamp((type_signal * 0.45) + (score_signal * 0.55), 0.0, 1.0)


def _machine_relevance_signal(message, sources):
    """Return whether machine-related questions have machine-related support."""
    relevant_sources = _relevant_sources(sources)
    if not relevant_sources:
        return 0.0
    if not _message_mentions_machine_context(message):
        return 0.7
    source_values = [_source_machine_signal(source) for source in relevant_sources]
    return max(source_values) if source_values else 0.0


def _feedback_signal(sources, response_type):
    """Return a source-aware signal from previous user feedback."""
    try:
        stats = _feedback_stats_for_sources(sources, response_type)
    except SQLAlchemyError:
        return NO_FEEDBACK_SIGNAL
    total = stats["helpful"] + stats["partial"] + stats["not_helpful"]
    if total <= 0:
        return NO_FEEDBACK_SIGNAL
    raw = (stats["helpful"] + (stats["partial"] * 0.45) - stats["not_helpful"]) / total
    return _clamp((raw + 1.0) / 2.0, 0.0, 1.0)


def _feedback_stats_for_sources(sources, response_type):
    """Return aggregated feedback counts for matching current sources."""
    if not has_app_context():
        return {"helpful": 0, "partial": 0, "not_helpful": 0}

    source_keys = {_source_key(source) for source in sources if _source_key(source)}
    stats = {"helpful": 0, "partial": 0, "not_helpful": 0}
    feedback_items = AIFeedback.query.order_by(AIFeedback.created_at.desc()).limit(300).all()
    for feedback in feedback_items:
        if source_keys and _feedback_matches_sources(feedback, source_keys):
            _increment_feedback_stats(stats, feedback.rating)
            continue
        if not source_keys and response_type and feedback.response_type == response_type:
            _increment_feedback_stats(stats, feedback.rating)
    return stats


def _feedback_matches_sources(feedback, source_keys):
    """Return whether one feedback item references any current source key."""
    return any(_source_key(source) in source_keys for source in feedback.sources())


def _increment_feedback_stats(stats, rating):
    """Increment feedback stats for one rating value."""
    if rating == "helpful":
        stats["helpful"] += 1
    elif rating == "partially_helpful":
        stats["partial"] += 1
    elif rating == "not_helpful":
        stats["not_helpful"] += 1


def _source_key(source):
    """Return a stable source key used for feedback aggregation."""
    source_type = str(source.get("type") or "")
    source_id = source.get("id")
    chunk_id = source.get("chunk_id")
    if not source_type or source_id in (None, ""):
        return None
    return (source_type, str(source_id), str(chunk_id or ""))


def _relevant_sources(sources):
    """Return sources with a positive score or structured context value."""
    relevant = []
    for source in sources:
        score = _float_value(source.get("score"), 0.0)
        source_type = str(source.get("type") or "")
        if score > 0 or source_type:
            relevant.append(source)
    return relevant


def _source_quality_signal(source):
    """Return normalized quality signal for one source."""
    status = str(source.get("quality_status") or "").strip()
    if status:
        return QUALITY_STATUS_SIGNALS.get(status, 0.5)
    if source.get("type") == "knowledge":
        return 0.5
    return STRUCTURED_SOURCE_QUALITY_SIGNAL


def _type_agreement_signal(sources):
    """Return how strongly sources agree by source type."""
    counts = {}
    for source in sources:
        source_type = str(source.get("type") or "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1
    return max(counts.values()) / len(sources)


def _score_closeness_signal(sources):
    """Return whether source scores are in a similar range."""
    scores = [_float_value(source.get("score"), 0.0) for source in sources]
    average_score = sum(scores) / len(scores) if scores else 0.0
    if average_score <= 0:
        return 0.25
    variance = sum((score - average_score) ** 2 for score in scores) / len(scores)
    coefficient = math.sqrt(variance) / max(average_score, 1.0)
    return _clamp(1.0 - coefficient, 0.0, 1.0)


def _source_machine_signal(source):
    """Return machine-context relevance for one source."""
    machine_match = _float_value(source.get("machine_match"), 0.0)
    if machine_match > 0:
        return _clamp(machine_match, 0.0, 1.0)
    if source.get("machine_match_reasons"):
        return 0.9
    score_debug = source.get("score_debug") or {}
    signals = score_debug.get("signals") if isinstance(score_debug, dict) else {}
    if isinstance(signals, dict):
        debug_match = _float_value(signals.get("machine_match"), 0.0)
        if debug_match > 0:
            return _clamp(debug_match, 0.0, 1.0)
        if signals.get("machine_match_reasons"):
            return 0.9
    source_type = str(source.get("type") or "")
    if source_type == "machine":
        return 0.82
    if source_type in {"error", "inventory", "task"}:
        return 0.62
    if source_type == "knowledge":
        return 0.45
    return 0.2


def _message_mentions_machine_context(message):
    """Return whether the user question appears machine- or fault-related."""
    text = str(message or "").lower()
    keywords = (
        "maschine",
        "anlage",
        "presse",
        "fehler",
        "stoerung",
        "sensor",
        "motor",
        "lager",
        "hydraulik",
        "ventil",
    )
    return any(keyword in text for keyword in keywords) or bool(
        re.search(r"\b[A-Z]{1,4}[-_]?\d{2,5}\b", str(message or "")),
    )


def _confidence_level(score):
    """Return the public confidence level for a numeric score."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _confidence_warning(level):
    """Return a warning text for low-confidence answers."""
    if level != "low":
        return ""
    return (
        "Antwort nur eingeschraenkt belastbar: Quellenlage, Qualitaet oder "
        "Maschinenbezug sind schwach."
    )


def _confidence_reasons(factors, sources):
    """Return concise human-readable reasons for the confidence score."""
    reasons = []
    if not sources:
        reasons.append("Keine relevanten Quellen gefunden.")
    if factors["source_count"] >= 0.78:
        reasons.append("Mehrere relevante Quellen vorhanden.")
    elif factors["source_count"] > 0:
        reasons.append("Nur wenige relevante Quellen vorhanden.")
    if factors["quality"] >= 0.8:
        reasons.append("Quellenqualitaet ist hoch.")
    elif factors["quality"] and factors["quality"] < 0.5:
        reasons.append("Quellenqualitaet ist niedrig oder unklar.")
    if factors["machine_relevance"] >= 0.8:
        reasons.append("Maschinenkontext passt gut zur Frage.")
    elif factors["machine_relevance"] < 0.4:
        reasons.append("Maschinenkontext ist schwach oder fehlt.")
    if factors["feedback"] > NO_FEEDBACK_SIGNAL:
        reasons.append("Bisheriges Feedback stuetzt aehnliche Quellen.")
    elif factors["feedback"] < NO_FEEDBACK_SIGNAL:
        reasons.append("Bisheriges Feedback ist kritisch.")
    return reasons[:6]


def _float_value(value, default):
    """Return a safe float value."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, minimum, maximum):
    """Return value constrained to the provided inclusive range."""
    return max(minimum, min(maximum, value))
