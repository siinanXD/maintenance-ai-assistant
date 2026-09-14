"""Prompt-safe retrieval telemetry and quality analytics."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from app.domain_models.common import utc_now
from app.models import AIAuditEvent, AIFeedback, KnowledgeGap
from app.services.retrieval_evaluation_history import retrieval_evaluation_history
from app.services.retrieval_telemetry_common import (
    NEGATIVE_RATINGS,
    event_reference,
    feedback_reference,
    is_error_event,
    low_confidence_score,
    normalize_limit,
    normalize_window_days,
)
from app.services.retrieval_telemetry_slo import reranking_summary, retrieval_slo_metrics
from app.services.retrieval_telemetry_sources import (
    collect_used_chunk_ids,
    poor_source_summary,
    source_telemetry,
    source_usage_summary,
    unused_chunk_summary,
)


def retrieval_quality_analytics(days=None, limit=None):
    """Return aggregated retrieval quality telemetry without storing raw content."""
    window_days = normalize_window_days(days)
    item_limit = normalize_limit(limit)
    since = utc_now() - timedelta(days=window_days)
    previous_since = since - timedelta(days=window_days)
    events = _audit_events_since(since)
    previous_events = _audit_events_between(previous_since, since)
    feedback_entries = _feedback_since(since)
    previous_feedback_entries = _feedback_between(previous_since, since)
    source_stats = source_telemetry(events, feedback_entries)
    used_chunk_ids = collect_used_chunk_ids(source_stats)
    return {
        "window_days": window_days,
        "events": _event_overview(events),
        "retrieval_slo": retrieval_slo_metrics(
            events=events,
            feedback_entries=feedback_entries,
            previous_events=previous_events,
            previous_feedback_entries=previous_feedback_entries,
            window_days=window_days,
        ),
        "retrieval_evaluation_history": retrieval_evaluation_history(limit=item_limit),
        "reranking": reranking_summary(events),
        "source_usage": source_usage_summary(source_stats, item_limit),
        "poor_sources": poor_source_summary(source_stats, item_limit),
        "unsuccessful_questions": _unsuccessful_question_summary(events),
        "knowledge_gaps": _knowledge_gap_summary(since, item_limit),
        "negative_feedback": _negative_feedback_summary(feedback_entries, item_limit),
        "unused_chunks": unused_chunk_summary(used_chunk_ids, item_limit),
        "privacy": {
            "stores_prompt_text": False,
            "stores_answer_text": False,
            "stores_chunk_text": False,
            "source": "aggregated_audit_feedback_gap_metadata",
        },
    }


def _audit_events_since(since):
    """Return audit events in the telemetry window."""
    return (
        AIAuditEvent.query.filter(AIAuditEvent.created_at >= since)
        .order_by(AIAuditEvent.created_at.desc(), AIAuditEvent.id.desc())
        .all()
    )


def _audit_events_between(start_at, end_at):
    """Return audit events inside a closed-open time range."""
    return (
        AIAuditEvent.query.filter(
            AIAuditEvent.created_at >= start_at,
            AIAuditEvent.created_at < end_at,
        )
        .order_by(AIAuditEvent.created_at.desc(), AIAuditEvent.id.desc())
        .all()
    )


def _feedback_since(since):
    """Return feedback entries in the telemetry window."""
    return (
        AIFeedback.query.filter(AIFeedback.created_at >= since)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .all()
    )


def _feedback_between(start_at, end_at):
    """Return feedback entries inside a closed-open time range."""
    return (
        AIFeedback.query.filter(
            AIFeedback.created_at >= start_at,
            AIFeedback.created_at < end_at,
        )
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .all()
    )


def _unsuccessful_question_summary(events):
    """Return prompt-free signals for retrieval misses and weak answers."""
    low_confidence_threshold = low_confidence_score()
    no_source_events = [event for event in events if int(event.source_count or 0) == 0]
    low_confidence_events = [
        event
        for event in events
        if event.confidence_score is not None
        and int(event.confidence_score) <= low_confidence_threshold
    ]
    error_events = [event for event in events if is_error_event(event)]
    return {
        "no_source_events": len(no_source_events),
        "low_confidence_events": len(low_confidence_events),
        "error_events": len(error_events),
        "low_confidence_threshold": low_confidence_threshold,
        "by_workflow": dict(Counter(str(event.workflow or "") for event in no_source_events)),
        "by_status": dict(Counter(str(event.status or "") for event in no_source_events)),
        "by_error_category": dict(
            Counter(event.error_category for event in error_events if event.error_category)
        ),
        "latest": [event_reference(event) for event in no_source_events[:10]],
    }


def _knowledge_gap_summary(since, limit):
    """Return frequently recurring knowledge gaps without exposing question text."""
    window_gaps = (
        KnowledgeGap.query.filter(KnowledgeGap.last_seen_at >= since)
        .order_by(
            KnowledgeGap.occurrence_count.desc(),
            KnowledgeGap.last_seen_at.desc(),
            KnowledgeGap.id.desc(),
        )
        .all()
    )
    open_total = KnowledgeGap.query.filter(KnowledgeGap.status == "open").count()
    return {
        "open_total": open_total,
        "window_total": len(window_gaps),
        "top_gaps": [_gap_payload(gap) for gap in window_gaps[:limit]],
    }


def _negative_feedback_summary(feedback_entries, limit):
    """Return answer-level negative feedback metadata without prompts or answers."""
    negative_feedback = [
        feedback for feedback in feedback_entries if feedback.rating in NEGATIVE_RATINGS
    ]
    return {
        "total": len(negative_feedback),
        "with_sources": sum(1 for item in negative_feedback if item.source_count > 0),
        "without_sources": sum(1 for item in negative_feedback if item.source_count == 0),
        "by_response_type": dict(
            Counter(str(item.response_type or "") for item in negative_feedback),
        ),
        "latest": [feedback_reference(feedback) for feedback in negative_feedback[:limit]],
    }


def _event_overview(events):
    """Return aggregate retrieval event coverage."""
    with_sources = sum(1 for event in events if int(event.source_count or 0) > 0)
    total_sources = sum(int(event.source_count or 0) for event in events)
    return {
        "total": len(events),
        "with_sources": with_sources,
        "without_sources": len(events) - with_sources,
        "source_count": total_sources,
        "average_sources": round(total_sources / len(events), 2) if events else 0,
    }


def _gap_payload(gap):
    """Return a content-safe knowledge-gap analytics payload."""
    return {
        "id": gap.id,
        "question_hash": gap.question_hash,
        "status": gap.status,
        "occurrence_count": gap.occurrence_count,
        "machine": gap.machine,
        "department": gap.department,
        "audit_event_id": gap.audit_event_id,
        "last_seen_at": gap.last_seen_at.isoformat(),
    }
