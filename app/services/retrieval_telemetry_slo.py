"""Retrieval SLO values, warnings and trends over a time window."""

from __future__ import annotations

from collections import Counter

from app.services.retrieval_telemetry_common import (
    NEGATIVE_RATINGS,
    SLO_THRESHOLDS,
    average,
    compute_percentile,
    event_sources,
    json_list,
    low_confidence_score,
    missing_source_metadata_fields,
    normalize_window_days,
    optional_float,
    optional_int,
    rate,
    source_has_metadata_gap,
)
from app.services.vector_sync_status_service import vector_store_drift_status


def retrieval_slo_metrics(
    events=None,
    feedback_entries=None,
    previous_events=None,
    previous_feedback_entries=None,
    window_days=None,
):
    """Return prompt-safe retrieval SLO metrics, trends, and warning status."""
    current_events = list(events or [])
    current_feedback = list(feedback_entries or [])
    previous_event_list = list(previous_events or [])
    previous_feedback = list(previous_feedback_entries or [])
    drift_status = vector_store_drift_status()
    current_values = _slo_metric_values(
        current_events,
        current_feedback,
        drift_status=drift_status,
    )
    previous_values = _slo_metric_values(
        previous_event_list,
        previous_feedback,
        drift_status={},
    )
    warnings = _slo_warnings(current_values)
    return {
        "window_days": normalize_window_days(window_days),
        "status": _worst_status([warning["status"] for warning in warnings]),
        "last_values": current_values,
        "previous_values": previous_values,
        "trends": _slo_trends(current_values, previous_values),
        "warnings": warnings,
        "thresholds": SLO_THRESHOLDS,
        "privacy": {
            "stores_prompt_text": False,
            "stores_answer_text": False,
            "stores_chunk_text": False,
            "source": "ai_audit_metadata_feedback_and_vector_drift",
        },
    }


def _slo_metric_values(events, feedback_entries, drift_status=None):
    """Return central retrieval SLO values for one event window."""
    event_count = len(events)
    feedback_count = len(feedback_entries)
    negative_feedback_count = sum(
        1 for feedback in feedback_entries if feedback.rating in NEGATIVE_RATINGS
    )
    drift = drift_status if isinstance(drift_status, dict) else {}
    return {
        "event_count": event_count,
        "retrieval_p95_ms": compute_percentile(
            [_retrieval_duration_ms(event) for event in events],
            0.95,
        ),
        "no_source_rate": rate(
            sum(1 for event in events if int(event.source_count or 0) == 0),
            event_count,
        ),
        "low_confidence_rate": rate(
            sum(1 for event in events if _is_low_confidence_event(event)),
            event_count,
        ),
        "permission_filtered_candidate_count": sum(
            _permission_filtered_candidate_count(event) for event in events
        ),
        "negative_feedback_rate": rate(negative_feedback_count, feedback_count),
        "safety_risk_count": sum(1 for event in events if _event_has_safety_risk(event)),
        "fallback_rate": rate(
            sum(1 for event in events if bool(event.fallback_used)),
            event_count,
        ),
        "vector_sync_failure_count": int(drift.get("vector_sync_failure_count") or 0),
        "stale_index_count": int(drift.get("stale_document_count") or 0),
        "atlas_queries": int(drift.get("atlas_queries") or 0),
        "atlas_errors": int(drift.get("atlas_errors") or 0),
        "atlas_latency": optional_float(drift.get("atlas_latency")) or 0,
        "atlas_fallbacks": int(drift.get("atlas_fallbacks") or 0),
        "atlas_sync_failures": int(drift.get("atlas_sync_failures") or 0),
        "atlas_vector_count": optional_int(drift.get("atlas_vector_count")) or 0,
        "atlas_reindex_required": 1 if drift.get("atlas_reindex_required") else 0,
        "source_metadata_missing_rate": _source_metadata_missing_rate(events),
        "source_metadata_missing_fields": _source_metadata_missing_fields(events),
    }


def _retrieval_duration_ms(event):
    """Return retrieval duration metadata for one audit event."""
    explainability = event.retrieval_explainability()
    if not isinstance(explainability, dict):
        return None
    return optional_int(explainability.get("retrieval_duration_ms"))


def _is_low_confidence_event(event):
    """Return whether an audit event falls below the low-confidence SLO threshold."""
    if event.confidence_score is None:
        return False
    return int(event.confidence_score) <= low_confidence_score()


def _permission_filtered_candidate_count(event):
    """Return a safe proxy for scopes filtered by permissions."""
    requested = set(json_list(event.requested_scopes))
    allowed = set(json_list(event.allowed_scopes))
    blocked_scope_count = len(requested - allowed)
    if str(event.status or "") == "permission_denied" and not blocked_scope_count:
        return 1
    return blocked_scope_count


def reranking_summary(events):
    """Return aggregate candidate-pool reduction metrics from audit debug data."""
    rows = []
    for event in events:
        explainability = event.retrieval_explainability()
        debug = explainability.get("retrieval_debug") if isinstance(explainability, dict) else {}
        reranking = debug.get("reranking") if isinstance(debug, dict) else {}
        if not isinstance(reranking, dict):
            continue
        row = {
            "candidate_limit": optional_int(reranking.get("candidate_limit")),
            "candidate_count": optional_int(reranking.get("candidate_count")),
            "final_top_k": optional_int(reranking.get("final_top_k")),
            "final_source_count": optional_int(reranking.get("final_source_count")),
            "reduction_rate": optional_float(reranking.get("reduction_rate")),
        }
        if row["candidate_limit"] is None and row["final_top_k"] is None:
            continue
        rows.append(row)
    return {
        "request_count": len(rows),
        "average_candidate_limit": average(
            row["candidate_limit"] for row in rows if row["candidate_limit"] is not None
        ),
        "average_candidate_count": average(
            row["candidate_count"] for row in rows if row["candidate_count"] is not None
        ),
        "average_final_top_k": average(
            row["final_top_k"] for row in rows if row["final_top_k"] is not None
        ),
        "average_final_source_count": average(
            row["final_source_count"] for row in rows if row["final_source_count"] is not None
        ),
        "average_reduction_rate": average(
            row["reduction_rate"] for row in rows if row["reduction_rate"] is not None
        ),
    }


def _event_has_safety_risk(event):
    """Return whether audit metadata contains a safety-relevant risk signal."""
    explainability = event.retrieval_explainability()
    if not isinstance(explainability, dict):
        return False
    safety = explainability.get("safety")
    post_safety = explainability.get("post_generation_safety")
    return _safety_relevant(safety) or _safety_relevant(post_safety)


def _source_metadata_missing_rate(events):
    """Return the share of retrieved sources missing essential public metadata."""
    sources = [source for event in events for source in event_sources(event)]
    missing_count = sum(1 for source in sources if source_has_metadata_gap(source))
    return rate(missing_count, len(sources))


def _source_metadata_missing_fields(events):
    """Return prompt-safe missing source metadata field counts."""
    counter = Counter()
    for event in events:
        for source in event_sources(event):
            counter.update(missing_source_metadata_fields(source))
    return [{"field": field, "count": count} for field, count in counter.most_common()]


def _safety_relevant(value):
    """Return whether a serialized safety payload is safety relevant."""
    return isinstance(value, dict) and bool(value.get("safety_relevant"))


def _slo_warnings(values):
    """Return warning rows for SLO values that cross configured thresholds."""
    warnings = []
    for metric, thresholds in SLO_THRESHOLDS.items():
        value = values.get(metric, 0)
        status = _threshold_status(value, thresholds)
        if status == "ok":
            continue
        warnings.append(
            {
                "metric": metric,
                "value": value,
                "status": status,
                "threshold": thresholds[status],
            }
        )
    return warnings


def _threshold_status(value, thresholds):
    """Return ok, warning, or critical for one SLO value."""
    if value >= thresholds["critical"]:
        return "critical"
    if value >= thresholds["warning"]:
        return "warning"
    return "ok"


def _slo_trends(current_values, previous_values):
    """Return simple trends for every central retrieval SLO metric."""
    trends = {}
    for metric in SLO_THRESHOLDS:
        current = current_values.get(metric, 0)
        previous = previous_values.get(metric, 0)
        delta = round(current - previous, 4)
        trends[metric] = {
            "current": current,
            "previous": previous,
            "delta": delta,
            "direction": _trend_direction(delta),
            "status": _trend_status(delta),
        }
    return trends


def _trend_direction(delta):
    """Return up, down, or flat for a numeric trend delta."""
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _trend_status(delta):
    """Return whether a higher SLO value is operationally better or worse."""
    if delta > 0:
        return "worse"
    if delta < 0:
        return "better"
    return "stable"


def _worst_status(statuses):
    """Return the worst status from a list of warning severities."""
    order = {"ok": 0, "warning": 1, "critical": 2}
    worst = "ok"
    for status in statuses:
        if order.get(status, 0) > order[worst]:
            worst = status
    return worst
