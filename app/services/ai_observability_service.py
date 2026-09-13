"""Admin-facing AI monitoring and observability read models."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from math import ceil

from flask import current_app

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import AIAuditEvent, AIFeedback, ChatMessage, KnowledgeDocument, KnowledgeGap
from app.services.ai_answer_quality_service import answer_quality_from_history_item
from app.services.ai_governance_service import evaluate_governance_alerts
from app.services.ai_metric_catalog_service import metric_catalog
from app.services.ai_prompting import text_system_prompt
from app.services.ai_provider_readiness_service import ai_provider_readiness_snapshot
from app.services.ai_routing import ai_price_configuration_status
from app.services.knowledge_aging_service import knowledge_aging_policy
from app.services.knowledge_gap_service import knowledge_gap_detection
from app.services.langfuse_metrics_service import langfuse_metrics_summary
from app.services.retrieval_telemetry_service import retrieval_quality_analytics
from app.services.text_normalization_service import tokenize_text

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


def ai_observability_dashboard(args=None):
    """Return an admin-facing AI monitoring dashboard from existing telemetry."""
    args = args or {}
    days = _bounded_int(args.get("days"), DEFAULT_OBSERVABILITY_DAYS, 1, 365)
    limit = _bounded_int(args.get("limit"), DEFAULT_OBSERVABILITY_LIMIT, 1, MAX_OBSERVABILITY_LIMIT)
    chat_message_id = _optional_int(args.get("chat_message_id"))
    since = utc_now() - timedelta(days=days)
    events = _audit_events_since(since)
    chats = _chat_messages_since(since)
    feedback_entries = _feedback_since(since)
    telemetry = retrieval_quality_analytics(days=days, limit=limit)
    provider_readiness = ai_provider_readiness_snapshot(current_app.config)
    metrics = _metrics(events, chats, feedback_entries, telemetry)
    metrics.update(_provider_readiness_metrics(provider_readiness))
    retrieval_monitoring = _retrieval_monitoring(events, feedback_entries, limit)
    quality_metrics = _quality_metrics(events, telemetry)
    governance = evaluate_governance_alerts(
        metrics,
        quality_metrics=quality_metrics,
        retrieval_monitoring=retrieval_monitoring,
        telemetry=telemetry,
        provider_readiness=provider_readiness,
    )
    metrics.update(_governance_metrics(governance))
    recommended_actions = _observability_recommended_actions(
        metrics,
        retrieval_monitoring,
        quality_metrics,
        provider_readiness,
        limit,
    )
    ai_logs = _ai_logs(chats, limit)
    failed_requests = _failed_requests(events, limit)
    return {
        "window_days": days,
        "provider_readiness": provider_readiness,
        "metrics": metrics,
        "retrieval_monitoring": retrieval_monitoring,
        "ai_logs": ai_logs,
        "logs": ai_logs,
        "failed_requests": failed_requests,
        "quality_metrics": quality_metrics,
        "governance": governance,
        "alerts": governance["alerts"],
        "top_questions": metrics["top_questions"],
        "frequent_questions": metrics["frequent_questions"],
        "frequent_search_terms": metrics["frequent_search_terms"],
        "source_distribution": metrics["source_distribution_rows"],
        "source_kind_distribution": metrics["source_kind_distribution_rows"],
        "top_structured_modules": metrics["top_structured_modules"],
        "recommended_actions": recommended_actions,
        "next_best_action": recommended_actions[0] if recommended_actions else None,
        "recommended_action_summary": _recommended_action_summary(
            recommended_actions,
            metrics,
        ),
        "debug_tools": _debug_tools(chats, chat_message_id),
        "langfuse_metrics": langfuse_metrics_summary(days=days),
        "metric_catalog": metric_catalog(),
        "privacy": {
            "source": "chat_history_audit_metadata_retrieval_telemetry",
            "raw_questions_visible_to_admins": True,
            "raw_answers_bounded": True,
            "raw_chunk_text_visible": False,
            "source_ids_visible": False,
            "source_metadata_aggregates_visible": True,
        },
    }


def _provider_readiness_metrics(provider_readiness):
    """Return stable provider readiness metrics for AI Admin dashboards."""
    readiness = provider_readiness.get("readiness") or {}
    next_action = readiness.get("next_action") or {}
    degraded_components = readiness.get("degraded_components") or []
    if not isinstance(degraded_components, list):
        degraded_components = []
    return {
        "provider_ready": bool(provider_readiness.get("ready")),
        "provider_readiness_status": str(readiness.get("status") or "unknown"),
        "provider_degraded_component_count": len(degraded_components),
        "provider_next_action_type": str(next_action.get("configuration_action") or "")
        if isinstance(next_action, dict)
        else "",
    }


def _governance_metrics(governance):
    """Return stable top-level governance metric counters."""
    return {
        "governance_status": str(governance.get("status") or "ok"),
        "governance_alert_count": int(governance.get("alert_count") or 0),
        "governance_critical_alert_count": int(governance.get("critical_count") or 0),
        "governance_warning_alert_count": int(governance.get("warning_count") or 0),
    }


def _audit_events_since(since):
    """Return audit events in the observability window."""
    return (
        AIAuditEvent.query.filter(AIAuditEvent.created_at >= since)
        .order_by(AIAuditEvent.created_at.desc(), AIAuditEvent.id.desc())
        .all()
    )


def _chat_messages_since(since):
    """Return chat messages in the observability window."""
    return (
        ChatMessage.query.filter(ChatMessage.created_at >= since)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .all()
    )


def _feedback_since(since):
    """Return feedback entries in the observability window."""
    return (
        AIFeedback.query.filter(AIFeedback.created_at >= since)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .all()
    )


def _metrics(events, chats, feedback_entries, telemetry):
    """Return top-level AI operations metrics."""
    event_count = len(events)
    response_times = [event.latency_ms for event in events if event.latency_ms]
    retrieval_times = [_retrieval_duration_ms(event) for event in events]
    retrieval_times = [value for value in retrieval_times if value is not None]
    empty_retrieval_count = sum(1 for chat in chats if _is_empty_retrieval(chat))
    no_answer_count = sum(1 for chat in chats if _is_no_answer(chat))
    hallucination_warning_count = sum(1 for chat in chats if _has_hallucination_warning(chat))
    source_conflict_count = sum(1 for chat in chats if _has_source_conflict(chat))
    answer_quality_distribution = _answer_quality_distribution(chats)
    answer_quality_reason_distribution = _answer_quality_reason_distribution(chats)
    answer_quality_actions = _answer_quality_reason_actions(
        answer_quality_reason_distribution["counts"]
    )
    primary_warning_distribution = _primary_warning_distribution(chats)
    uncertainty_distribution = _uncertainty_distribution(chats)
    uncertainty_counts = uncertainty_distribution["counts"]
    high_uncertainty_count = uncertainty_counts.get("high", 0)
    uncertain_answer_count = high_uncertainty_count + uncertainty_counts.get("medium", 0)
    error_count = sum(1 for event in events if _is_error_event(event))
    source_distribution = _source_distribution(events)
    source_kind_distribution = _source_kind_distribution(events)
    feedback_summary = _feedback_summary(feedback_entries)
    source_counts = [int(event.source_count or 0) for event in events]
    chat_source_counts = [int(chat.source_count or 0) for chat in chats]
    structured_answer_count = sum(1 for chat in chats if _is_structured_answer(chat))
    rag_answer_count = sum(1 for chat in chats if _is_rag_answer(chat))
    no_source_count = sum(1 for value in chat_source_counts if value == 0)
    no_source_breakdown = _no_source_breakdown(chats)
    low_confidence_count = sum(1 for chat in chats if _is_low_confidence_chat(chat))
    fallback_count = sum(1 for event in events if event.fallback_used)
    token_usage = _token_usage(events)
    cost_windows = _cost_windows(events)
    latency = _latency_metrics(response_times, retrieval_times)
    answered_source_counts = [
        int(chat.source_count or 0) for chat in chats if _is_answered_chat(chat)
    ]
    structured_module_distribution = _structured_module_distribution(chats)
    reranking_metrics = _reranking_metrics(events)
    retrieval_slo = _retrieval_slo_summary(telemetry)
    source_rows = _source_rows(events)
    source_freshness = _source_freshness_summary(source_rows)
    evaluation_gate_metrics = _evaluation_gate_metrics(telemetry)
    source_metadata_metrics = _source_metadata_metrics(telemetry)
    action_summaries = _action_summaries(
        source_rows,
        feedback_entries,
        telemetry,
    )
    top_documents = _document_usage_rows(
        Counter(
            (row["source_type"], row["source_id"])
            for row in source_rows
            if row.get("source_id") is not None
        ),
        DEFAULT_OBSERVABILITY_LIMIT,
    )
    return {
        "event_count": event_count,
        "chat_count": len(chats),
        "total_requests": event_count,
        "successful_requests": max(event_count - error_count, 0),
        "failed_requests": error_count,
        "request_success_rate": _rate(max(event_count - error_count, 0), event_count),
        "average_response_ms": latency["average_response_ms"],
        "p95_response_ms": latency["p95_response_ms"],
        "average_retrieval_ms": latency["average_retrieval_ms"],
        "p95_retrieval_ms": latency["p95_retrieval_ms"],
        "latency": latency,
        "total_tokens": token_usage["total_tokens"],
        "input_tokens": token_usage["input_tokens"],
        "output_tokens": token_usage["output_tokens"],
        "cached_tokens": token_usage["cached_tokens"],
        "average_tokens": token_usage["average_tokens"],
        "token_usage": token_usage,
        "cost_windows": cost_windows,
        "costs": _cost_metrics(cost_windows, events),
        "price_configuration": ai_price_configuration_status(),
        "error_count": error_count,
        "failed_request_count": error_count,
        "failure_reason_distribution": _failure_reason_distribution(events),
        "error_rate": _rate(error_count, event_count),
        "empty_retrieval_count": empty_retrieval_count,
        "empty_retrieval_rate": _rate(empty_retrieval_count, len(chats)),
        "no_answer_count": no_answer_count,
        "no_answer_rate": _rate(no_answer_count, len(chats)),
        "source_conflict_count": source_conflict_count,
        "source_conflict_rate": _rate(source_conflict_count, len(chats)),
        "answer_quality_distribution": answer_quality_distribution["counts"],
        "answer_quality_distribution_rows": answer_quality_distribution["rows"],
        "answer_quality_reason_distribution": answer_quality_reason_distribution["counts"],
        "answer_quality_reason_distribution_rows": answer_quality_reason_distribution["rows"],
        "answer_quality_actions": answer_quality_actions,
        "answer_quality_action_count": len(answer_quality_actions),
        "answer_quality_action_summary": _action_summary(answer_quality_actions),
        "primary_warning_distribution": primary_warning_distribution["counts"],
        "primary_warning_distribution_rows": primary_warning_distribution["rows"],
        "uncertainty_distribution": uncertainty_distribution["counts"],
        "uncertainty_distribution_rows": uncertainty_distribution["rows"],
        "high_uncertainty_count": high_uncertainty_count,
        "high_uncertainty_rate": _rate(high_uncertainty_count, len(chats)),
        "uncertain_answer_count": uncertain_answer_count,
        "uncertain_answer_rate": _rate(uncertain_answer_count, len(chats)),
        "low_confidence_answers": low_confidence_count,
        "low_confidence_answer_count": low_confidence_count,
        "low_confidence_rate": _rate(low_confidence_count, len(chats)),
        "retrieval_hit_rate": _rate(
            sum(1 for event in events if int(event.source_count or 0) > 0),
            event_count,
        ),
        "source_freshness": source_freshness,
        "stale_source_count": source_freshness["stale_source_count"],
        "stale_source_rate": source_freshness["stale_source_rate"],
        "undated_source_count": source_freshness["undated_source_count"],
        "retrieval_action_count": action_summaries["retrieval"]["total"],
        "retrieval_critical_action_count": action_summaries["retrieval"]["critical_priority_count"],
        "retrieval_high_action_count": action_summaries["retrieval"]["high_priority_count"],
        "evaluation_action_count": action_summaries["evaluation"]["total"],
        "evaluation_critical_action_count": action_summaries["evaluation"][
            "critical_priority_count"
        ],
        "evaluation_high_action_count": action_summaries["evaluation"]["high_priority_count"],
        "evaluation_quality_gate_status": evaluation_gate_metrics["status"],
        "evaluation_quality_gate_passed": evaluation_gate_metrics["passed"],
        "evaluation_quality_gate_issue_count": evaluation_gate_metrics["issue_count"],
        "evaluation_blocking_count": evaluation_gate_metrics["blocking_count"],
        "evaluation_warning_count": evaluation_gate_metrics["warning_count"],
        "source_metadata_gap_count": source_metadata_metrics["gap_count"],
        "source_metadata_gap_fields": source_metadata_metrics["gap_fields"],
        "source_metadata_min_coverage_rate": source_metadata_metrics["min_coverage_rate"],
        "average_final_top_k": _average(source_counts),
        "average_source_count": _average(source_counts),
        "source_count_average": _average(chat_source_counts),
        "average_answer_source_count": _average(chat_source_counts),
        "source_count_average_answered": _average(answered_source_counts),
        "structured_answer_count": structured_answer_count,
        "structured_answer_rate": _rate(structured_answer_count, len(chats)),
        "rag_answer_count": rag_answer_count,
        "rag_answer_rate": _rate(rag_answer_count, len(chats)),
        "no_source_count": no_source_count,
        "no_source_rate": _rate(no_source_count, len(chats)),
        "no_source_answers": no_source_count,
        "no_source_answer_rate": _rate(no_source_count, len(chats)),
        "no_source_permission_denied_count": no_source_breakdown["permission_denied"],
        "no_source_no_data_count": no_source_breakdown["no_data"],
        "no_source_answer_count": no_source_breakdown["answered_without_sources"],
        "no_source_breakdown": no_source_breakdown,
        "top_structured_modules": structured_module_distribution["rows"],
        "structured_module_distribution": structured_module_distribution["counts"],
        "structured_domain_distribution": structured_module_distribution["counts"],
        "structured_domain_distribution_rows": structured_module_distribution["rows"],
        "reranking": reranking_metrics,
        "reranking_request_count": reranking_metrics["request_count"],
        "average_rerank_candidate_limit": reranking_metrics["average_candidate_limit"],
        "average_rerank_candidate_count": reranking_metrics["average_candidate_count"],
        "average_rerank_reduction_rate": reranking_metrics["average_reduction_rate"],
        "hallucination_warning_count": hallucination_warning_count,
        "fallback_count": fallback_count,
        "fallback_rate": _rate(fallback_count, event_count),
        "positive_feedback_count": feedback_summary["positive"],
        "negative_feedback_count": feedback_summary["negative"],
        "feedback": feedback_summary,
        "top_questions": _top_questions(chats),
        "frequent_questions": _top_questions(chats),
        "frequent_search_terms": _frequent_search_terms(chats),
        "most_used_documents": top_documents,
        "knowledge_gaps": _knowledge_gap_metrics(chats),
        "source_distribution": source_distribution,
        "source_distribution_rows": _counter_rows(source_distribution),
        "source_kind_distribution": source_kind_distribution,
        "source_kind_distribution_rows": _counter_rows(source_kind_distribution),
        "retrieval_slo": retrieval_slo,
        "retrieval_slo_warnings": retrieval_slo["warnings"],
        "atlas_queries": retrieval_slo["atlas_queries"],
        "atlas_errors": retrieval_slo["atlas_errors"],
        "atlas_latency": retrieval_slo["atlas_latency"],
        "atlas_fallbacks": retrieval_slo["atlas_fallbacks"],
        "atlas_sync_failures": retrieval_slo["atlas_sync_failures"],
        "atlas_vector_count": retrieval_slo["atlas_vector_count"],
        "atlas_reindex_required": retrieval_slo["atlas_reindex_required"],
        "telemetry_status": retrieval_slo["status"],
    }


def _retrieval_monitoring(events, feedback_entries, limit):
    """Return retrieval hit, score, chunk, and document usage details."""
    source_rows = _source_rows(events)
    source_freshness = _source_freshness_summary(source_rows)
    stale_sources = _stale_source_rows(source_rows, limit)
    undated_sources = _undated_source_rows(source_rows, limit)
    chunk_counter = Counter()
    document_counter = Counter()
    for row in source_rows:
        if row.get("chunk_id") is not None:
            chunk_counter[(row["source_id"], row["chunk_id"], row["source_type"])] += 1
        if row.get("source_id") is not None:
            document_counter[(row["source_type"], row["source_id"])] += 1
    negative_feedback_ids = _negative_feedback_event_ids(feedback_entries)
    poor_hits = _poor_hit_rows(source_rows, negative_feedback_ids, limit)
    score_summary = _score_summary(source_rows)
    retrieval_quality_actions = _retrieval_quality_actions(
        poor_hits,
        score_summary,
    )
    metadata_quality_actions = _source_metadata_quality_actions(
        source_freshness,
        stale_sources,
        undated_sources,
    )
    return {
        "top_hits": _top_hit_rows(source_rows, limit),
        "poor_hits": poor_hits,
        "score_summary": score_summary,
        "retrieval_quality_actions": retrieval_quality_actions,
        "source_freshness": source_freshness,
        "stale_sources": stale_sources,
        "undated_sources": undated_sources,
        "metadata_quality_actions": metadata_quality_actions,
        "action_summary": _retrieval_action_summary(
            retrieval_quality_actions + metadata_quality_actions,
        ),
        "chunk_usage": _chunk_usage_rows(chunk_counter, limit),
        "frequently_used_documents": _document_usage_rows(document_counter, limit),
    }


def _action_summaries(source_rows, feedback_entries, telemetry):
    """Return retrieval and evaluation action summaries for top-level metrics."""
    negative_feedback_ids = _negative_feedback_event_ids(feedback_entries)
    poor_hits = _poor_hit_rows(
        source_rows,
        negative_feedback_ids,
        DEFAULT_OBSERVABILITY_LIMIT,
    )
    score_summary = _score_summary(source_rows)
    source_freshness = _source_freshness_summary(source_rows)
    metadata_actions = _source_metadata_quality_actions(
        source_freshness,
        _stale_source_rows(source_rows, DEFAULT_OBSERVABILITY_LIMIT),
        _undated_source_rows(source_rows, DEFAULT_OBSERVABILITY_LIMIT),
    )
    retrieval_actions = _retrieval_quality_actions(poor_hits, score_summary)
    evaluation = telemetry.get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    source_metadata_gaps = _source_metadata_gaps(latest_eval)
    quality_gate = latest_eval.get("quality_gate") or _empty_evaluation_quality_gate()
    evaluation_actions = _evaluation_quality_actions(
        latest_eval,
        quality_gate,
        source_metadata_gaps,
    )
    return {
        "retrieval": _action_summary(retrieval_actions + metadata_actions),
        "evaluation": _action_summary(evaluation_actions),
    }


def _evaluation_gate_metrics(telemetry):
    """Return compact top-level metrics for the latest retrieval quality gate."""
    evaluation = (telemetry or {}).get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    quality_gate = latest_eval.get("quality_gate") or _empty_evaluation_quality_gate()
    blocking_rows = _quality_gate_blocking_rows(quality_gate.get("blocking") or [])
    warning_rows = _quality_gate_warning_rows(quality_gate.get("warnings") or [])
    return {
        "status": str(quality_gate.get("status") or "unknown")[:40],
        "passed": bool(quality_gate.get("passed") is True),
        "blocking_count": len(blocking_rows),
        "warning_count": len(warning_rows),
        "issue_count": len(blocking_rows) + len(warning_rows),
    }


def _source_metadata_metrics(telemetry):
    """Return compact top-level source metadata coverage metrics."""
    evaluation = (telemetry or {}).get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    gaps = _source_metadata_gaps(latest_eval)
    coverage_rates = [
        _bounded_rate(latest_eval.get(metric))
        for metric in (
            "source_id_coverage_rate",
            "source_type_coverage_rate",
            "source_pair_coverage_rate",
            "metadata_pair_coverage_rate",
        )
        if latest_eval.get(metric) is not None
    ]
    return {
        "gap_count": len(gaps),
        "gap_fields": [gap["field"] for gap in gaps],
        "min_coverage_rate": min(coverage_rates) if coverage_rates else None,
    }


def _observability_recommended_actions(
    metrics,
    retrieval_monitoring,
    quality_metrics,
    provider_readiness,
    limit,
):
    """Return prioritized AI admin actions across evaluation, retrieval, and gaps."""
    actions = []
    provider_action = _provider_readiness_action(provider_readiness)
    if provider_action:
        actions.append(provider_action)
    _extend_recommended_actions(
        actions,
        quality_metrics.get("evaluation_actions") or [],
        "evaluation",
    )
    _extend_recommended_actions(
        actions,
        retrieval_monitoring.get("retrieval_quality_actions") or [],
        "retrieval_quality",
    )
    _extend_recommended_actions(
        actions,
        retrieval_monitoring.get("metadata_quality_actions") or [],
        "source_metadata",
    )
    knowledge_gaps = metrics.get("knowledge_gaps") or {}
    _extend_recommended_actions(
        actions,
        knowledge_gaps.get("recommended_actions") or [],
        "knowledge_gap",
    )
    actions.sort(
        key=lambda action: (
            _priority_rank(action.get("priority")),
            _action_source_rank(action.get("action_source")),
            str(action.get("type") or ""),
        )
    )
    ranked_actions = actions[:limit]
    for index, action in enumerate(ranked_actions, start=1):
        action["rank"] = index
        action["rank_label"] = f"P{index}"
    return ranked_actions


def _extend_recommended_actions(actions, rows, action_source):
    """Append prompt-safe action rows with a stable action source label."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        action = dict(row)
        action["action_source"] = action_source
        actions.append(action)


def _provider_readiness_action(provider_readiness):
    """Return one critical admin action for degraded provider readiness."""
    readiness = provider_readiness.get("readiness") or {}
    next_action = readiness.get("next_action") or {}
    if provider_readiness.get("ready") or not isinstance(next_action, dict):
        return None
    component = str(next_action.get("component") or "provider")
    reason = str(next_action.get("reason") or "")
    return {
        "type": str(next_action.get("configuration_action") or "review_provider_configuration"),
        "priority": "critical",
        "target_type": "ai_provider_readiness",
        "target": component,
        "component": component,
        "reason": reason,
        "recommended_action": str(next_action.get("recommended_action") or ""),
        "next_steps": [
            "AI-Provider-Konfiguration im Admin-Status pruefen.",
            "Fehlende Umgebungsvariable setzen oder auf lokalen Fallback wechseln.",
            "Health- und AI-Status nach der Konfigurationsaenderung erneut pruefen.",
        ],
        "success_criteria": [
            "AI provider_readiness.ready ist true.",
            "Readiness enthaelt keine degraded provider components.",
        ],
        "action_source": "provider_readiness",
    }


def _priority_rank(priority):
    """Return sort rank for action priorities."""
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }.get(str(priority or "unknown"), 4)


def _action_source_rank(action_source):
    """Return stable sort rank for action sources."""
    return {
        "provider_readiness": 0,
        "evaluation": 1,
        "retrieval_quality": 2,
        "source_metadata": 3,
        "knowledge_gap": 4,
    }.get(str(action_source or "unknown"), 4)


def _negative_feedback_event_ids(feedback_entries):
    """Return audit event ids with negative feedback ratings."""
    return {
        feedback.audit_event_id
        for feedback in feedback_entries
        if feedback.rating in NEGATIVE_RATINGS
    }


def _ai_logs(chats, limit):
    """Return bounded AI request logs for admin diagnosis."""
    return [_ai_log_row(chat) for chat in chats[:limit]]


def _failed_requests(events, limit):
    """Return prompt-safe failed AI request rows from audit metadata."""
    return [_failed_request_row(event) for event in events if _is_error_event(event)][:limit]


def _failed_request_row(event):
    """Return one failed request row without prompt or response text."""
    return {
        "audit_event_id": event.id,
        "created_at": event.created_at.isoformat(),
        "workflow": event.workflow,
        "status": event.status,
        "failure_reason": _failure_reason(event),
        "error_category": event.error_category,
        "provider": event.provider,
        "model": event.model,
        "model_tier": event.model_tier,
        "fallback_used": bool(event.fallback_used),
        "latency_ms": event.latency_ms,
        "total_tokens": event.total_tokens,
        "source_count": event.source_count,
    }


def _ai_log_row(chat):
    """Return one bounded AI log row."""
    diagnostics = chat.diagnostics()
    event = chat.audit_event
    explainability = (
        event.retrieval_explainability()
        if event
        else (diagnostics.get("retrieval_explainability") or {})
    )
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    quality_warnings = diagnostics.get("quality_warnings") or []
    answer_quality = answer_quality_from_history_item(chat.to_dict())
    return {
        "chat_message_id": chat.id,
        "audit_event_id": chat.audit_event_id,
        "created_at": chat.created_at.isoformat(),
        "user_question": _bounded(chat.message, 300),
        "answer_preview": _bounded(chat.response, 420),
        "response_type": chat.response_type,
        "answer_quality": answer_quality,
        "answer_quality_label": _answer_quality_label(chat, quality_warnings),
        "confidence": _confidence_payload(chat, answer_quality),
        "source_count": chat.source_count,
        "sources": [_source_reference(source) for source in (sources or [])[:8]],
        "error": event.error_category if event else "",
        "status": event.status if event else diagnostics.get("status", ""),
        "response_duration_ms": event.latency_ms if event else 0,
        "retrieval_duration_ms": _retrieval_duration_ms(event) if event else 0,
        "quality_warnings": quality_warnings,
        "knowledge_gap_id": _optional_int(diagnostics.get("knowledge_gap_id")),
        "knowledge_gap_created": bool(diagnostics.get("knowledge_gap_created")),
        "langfuse": _langfuse_reference(diagnostics),
    }


def _quality_metrics(events, telemetry):
    """Return retrieval quality metrics aligned with golden evaluation when available."""
    total_events = len(events)
    hit_count = sum(1 for event in events if int(event.source_count or 0) > 0)
    similarity_values = _similarity_values(events)
    evaluation = telemetry.get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    source_metadata_gaps = _source_metadata_gaps(latest_eval)
    evaluation_quality_gate = latest_eval.get("quality_gate") or _empty_evaluation_quality_gate()
    evaluation_blocking = _quality_gate_blocking_rows(
        (evaluation_quality_gate or {}).get("blocking") or []
    )
    evaluation_warnings = _quality_gate_warning_rows(
        (evaluation_quality_gate or {}).get("warnings") or []
    )
    evaluation_actions = _evaluation_quality_actions(
        latest_eval,
        evaluation_quality_gate,
        source_metadata_gaps,
    )
    return {
        "recall_at_k": latest_eval.get("recall_at_k"),
        "mrr": latest_eval.get("mrr"),
        "ndcg_at_k": latest_eval.get("ndcg_at_k"),
        "keyword_hit_rate": latest_eval.get("keyword_hit_rate"),
        "keyword_query_count": latest_eval.get("keyword_query_count", 0),
        "no_result_rate": latest_eval.get("no_result_rate"),
        "no_result_count": latest_eval.get("no_result_count", 0),
        "expected_no_result_count": latest_eval.get("expected_no_result_count", 0),
        "expected_no_result_success_count": latest_eval.get(
            "expected_no_result_success_count",
            0,
        ),
        "expected_no_result_success_rate": latest_eval.get("expected_no_result_success_rate"),
        "unexpected_no_result_count": latest_eval.get("unexpected_no_result_count", 0),
        "unexpected_no_result_rate": latest_eval.get("unexpected_no_result_rate"),
        "min_source_count_fail_count": latest_eval.get(
            "min_source_count_fail_count",
            0,
        ),
        "min_source_count_pass_rate": latest_eval.get("min_source_count_pass_rate"),
        "query_type_expected_count": latest_eval.get("query_type_expected_count", 0),
        "query_type_match_count": latest_eval.get("query_type_match_count", 0),
        "query_type_accuracy": latest_eval.get("query_type_accuracy"),
        "permission_leak_count": latest_eval.get("permission_leak_count", 0),
        "forbidden_source_hit_count": latest_eval.get("forbidden_source_hit_count", 0),
        "source_metadata_count": latest_eval.get("source_metadata_count", 0),
        "source_id_coverage_rate": latest_eval.get("source_id_coverage_rate"),
        "source_type_coverage_rate": latest_eval.get("source_type_coverage_rate"),
        "source_pair_coverage_rate": latest_eval.get("source_pair_coverage_rate"),
        "metadata_pair_coverage_rate": latest_eval.get("metadata_pair_coverage_rate"),
        "source_metadata_gaps": source_metadata_gaps,
        "evaluation_quality_gate": evaluation_quality_gate,
        "evaluation_blocking_count": len(evaluation_blocking),
        "evaluation_blocking_metrics": [blocking["metric"] for blocking in evaluation_blocking],
        "evaluation_blocking_rows": evaluation_blocking,
        "evaluation_warning_count": len(evaluation_warnings),
        "evaluation_warning_metrics": [warning["metric"] for warning in evaluation_warnings],
        "evaluation_warning_rows": evaluation_warnings,
        "evaluation_actions": evaluation_actions,
        "evaluation_action_summary": _action_summary(evaluation_actions),
        "retrieval_hit_rate": _rate(hit_count, total_events),
        "empty_retrieval_rate": _rate(total_events - hit_count, total_events),
        "average_similarity_score": _average(similarity_values),
        "low_similarity_count": sum(
            1 for value in similarity_values if value <= LOW_SIMILARITY_THRESHOLD
        ),
        "evaluated_query_count": latest_eval.get("query_count", 0),
    }


def _retrieval_slo_summary(telemetry):
    """Return compact prompt-safe retrieval SLO details for AI observability."""
    slo = (telemetry or {}).get("retrieval_slo") or {}
    last_values = dict(slo.get("last_values") or {})
    warnings = [
        {
            "metric": str(warning.get("metric") or "")[:120],
            "value": _optional_float(warning.get("value")),
            "status": str(warning.get("status") or "ok")[:40],
            "threshold": _optional_float(warning.get("threshold")),
        }
        for warning in (slo.get("warnings") or [])[:10]
        if isinstance(warning, dict)
    ]
    return {
        "status": str(slo.get("status") or "ok")[:40],
        "source_metadata_missing_rate": _optional_float(
            last_values.get("source_metadata_missing_rate")
        ),
        "source_metadata_missing_fields": _slo_missing_fields(
            last_values.get("source_metadata_missing_fields")
        ),
        "no_source_rate": _optional_float(last_values.get("no_source_rate")),
        "fallback_rate": _optional_float(last_values.get("fallback_rate")),
        "atlas_queries": _optional_int(last_values.get("atlas_queries")) or 0,
        "atlas_errors": _optional_int(last_values.get("atlas_errors")) or 0,
        "atlas_latency": _optional_float(last_values.get("atlas_latency")) or 0,
        "atlas_fallbacks": _optional_int(last_values.get("atlas_fallbacks")) or 0,
        "atlas_sync_failures": _optional_int(last_values.get("atlas_sync_failures")) or 0,
        "atlas_vector_count": _optional_int(last_values.get("atlas_vector_count")) or 0,
        "atlas_reindex_required": bool(last_values.get("atlas_reindex_required")),
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def _slo_missing_fields(value):
    """Return prompt-safe missing source metadata field counts for SLO summaries."""
    return [
        {
            "field": str(item.get("field") or "")[:80],
            "count": _optional_int(item.get("count")) or 0,
        }
        for item in (value or [])[:20]
        if isinstance(item, dict) and item.get("field")
    ]


def _source_metadata_gaps(latest_eval):
    """Return prompt-safe source metadata coverage gaps from the latest evaluation."""
    labels = {
        "source_id_coverage_rate": "source_id",
        "source_type_coverage_rate": "source_type",
        "source_pair_coverage_rate": "source_pair",
        "metadata_pair_coverage_rate": "metadata_pair",
    }
    gaps = []
    if not latest_eval:
        return gaps
    for metric, field in labels.items():
        rate = latest_eval.get(metric)
        if rate is None:
            continue
        coverage_rate = _bounded_rate(rate)
        if coverage_rate < 1.0:
            gaps.append(
                {
                    "field": field,
                    "metric": metric,
                    "coverage_rate": coverage_rate,
                    "missing_rate": round(1.0 - coverage_rate, 4),
                }
            )
    return gaps


def _evaluation_quality_actions(latest_eval, quality_gate, source_metadata_gaps):
    """Return remediation actions for failed retrieval evaluation signals."""
    if not latest_eval:
        return [
            {
                "type": "run_retrieval_evaluation",
                "priority": "high",
                "target_type": "retrieval_evaluation",
                "target": "golden_questions",
                "reason": "Es liegt noch kein Retrieval-Evaluation-Lauf vor.",
                "recommended_action": (
                    "Golden Test Questions ausfuehren, damit Recall, MRR, "
                    "No-Result-Rate und Permission-Leaks messbar sind."
                ),
                "next_steps": [
                    "Golden Test Questions pruefen oder anlegen.",
                    "Retrieval-Evaluation ausfuehren.",
                    "Quality-Gate-Ergebnis im AI Admin kontrollieren.",
                ],
            }
        ]
    actions = []
    permission_leak_count = int(latest_eval.get("permission_leak_count") or 0)
    if permission_leak_count:
        actions.append(
            {
                "type": "fix_permission_leaks",
                "priority": "critical",
                "target_type": "retrieval_evaluation",
                "target": "permission_leak_count",
                "count": permission_leak_count,
                "reason": (
                    f"{permission_leak_count} Retrieval-Evaluation-Hit(s) verletzen "
                    "die erwartete Sichtbarkeit."
                ),
                "recommended_action": (
                    "Metadatenfilter, Rollen-/Department-Sichtbarkeit und "
                    "Permission-Leak-Golden-Tests pruefen."
                ),
                "next_steps": [
                    "Forbidden Source Hits aus dem Evaluation-Run analysieren.",
                    "Rollen- und Department-Filter fuer Retrieval-Kandidaten pruefen.",
                    "Evaluation nach Filterkorrektur erneut ausfuehren.",
                ],
            }
        )
    unexpected_no_result_count = int(latest_eval.get("unexpected_no_result_count") or 0)
    min_source_count_fail_count = int(latest_eval.get("min_source_count_fail_count") or 0)
    if unexpected_no_result_count or min_source_count_fail_count:
        actions.append(
            {
                "type": "improve_retrieval_coverage",
                "priority": "high",
                "target_type": "retrieval_evaluation",
                "target": "coverage_failures",
                "unexpected_no_result_count": unexpected_no_result_count,
                "min_source_count_fail_count": min_source_count_fail_count,
                "reason": (
                    "Evaluation zeigt unerwartete No-Result-Faelle oder zu wenige "
                    "Quellen fuer erwartete Antworten."
                ),
                "recommended_action": (
                    "Fehlende Dokumente, Chunking, Hybrid Search und erwartete "
                    "Quellen der Golden Questions pruefen."
                ),
                "next_steps": [
                    "Queries mit unerwartetem No-Result nach Quellenabdeckung sortieren.",
                    "Expected Sources und Keywords in Golden Questions pruefen.",
                    "Nach Reindex Recall@K und MRR vergleichen.",
                ],
            }
        )
    if source_metadata_gaps:
        actions.append(
            {
                "type": "complete_evaluation_source_metadata",
                "priority": "medium",
                "target_type": "retrieval_evaluation",
                "target": "source_metadata_gaps",
                "count": len(source_metadata_gaps),
                "fields": [gap["field"] for gap in source_metadata_gaps],
                "reason": "Evaluation meldet unvollstaendige Source-Metadaten.",
                "recommended_action": (
                    "Source-ID, Source-Type und Metadaten-Paare in Evaluation "
                    "und Retrieval-Ausgabe angleichen."
                ),
                "next_steps": [
                    "Source-Metadata-Gaps nach Feld priorisieren.",
                    "Retriever-Payload und Index-Metadaten fuer diese Felder pruefen.",
                    "Evaluation erneut ausfuehren und Coverage-Raten vergleichen.",
                ],
            }
        )
    warnings = _quality_gate_warning_rows((quality_gate or {}).get("warnings") or [])
    if warnings:
        warning_metrics = [warning["metric"] for warning in warnings]
        actions.append(
            {
                "type": "review_evaluation_warnings",
                "priority": "medium",
                "target_type": "retrieval_evaluation",
                "target": "quality_gate_warnings",
                "count": len(warnings),
                "warning_metrics": warning_metrics,
                "focus_areas": _evaluation_warning_focus_areas(warning_metrics),
                "reason": "Das Retrieval Quality Gate meldet Warnungen.",
                "recommended_action": _evaluation_warning_recommended_action(warning_metrics),
                "next_steps": _evaluation_warning_next_steps(warning_metrics),
                "success_criteria": _evaluation_warning_success_criteria(warning_metrics),
            }
        )
    return actions[:5]


def _evaluation_warning_focus_areas(metrics):
    """Return concise focus labels for evaluation quality warning metrics."""
    labels = {
        "block_metadata_coverage_rate": "chunk_structure_metadata",
        "keyword_hit_rate": "expected_keywords",
        "recall_at_k": "expected_sources",
        "mrr": "source_ranking",
        "source_pair_coverage_rate": "source_metadata",
        "metadata_pair_coverage_rate": "source_metadata",
    }
    return sorted({labels.get(str(metric), "retrieval_quality") for metric in metrics})


def _evaluation_warning_recommended_action(metrics):
    """Return a specific admin recommendation for evaluation warnings."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return (
            "Chunk-Strukturmetadaten im Index pruefen und betroffene Dokumente "
            "mit aktuellem Chunking neu indexieren."
        )
    return "Warnmetriken fachlich pruefen und priorisieren."


def _evaluation_warning_next_steps(metrics):
    """Return targeted next steps for evaluation warning metrics."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return [
            "Evaluation-Warnungen nach block_metadata_coverage_rate filtern.",
            "Index-Metadaten chunk_block_count und chunk_block_kinds pruefen.",
            "Betroffene Dokumente mit hybrid_semantic Chunking neu indexieren.",
        ]
    return [
        "Quality-Gate-Warnungen nach Metrik gruppieren.",
        "Betroffene Golden Questions reproduzieren.",
        "Schwellwerte und erwartete Quellen fachlich validieren.",
    ]


def _evaluation_warning_success_criteria(metrics):
    """Return success criteria for evaluation warning remediation."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return [
            "block_metadata_coverage_rate liegt mindestens bei 0.8.",
            "block_kind_distribution zeigt erwartete Chunk-Strukturtypen.",
        ]
    return [
        "Quality-Gate-Warnungen sinken oder sind fachlich begruendet.",
        "Betroffene Golden Questions erreichen die erwarteten Quellen.",
    ]


def _quality_gate_warning_rows(warnings):
    """Return prompt-safe quality-gate warning rows."""
    return _quality_gate_issue_rows(warnings)


def _quality_gate_blocking_rows(blocking):
    """Return prompt-safe quality-gate blocking rows."""
    return _quality_gate_issue_rows(blocking)


def _quality_gate_issue_rows(issues):
    """Return prompt-safe quality-gate issue rows."""
    rows = []
    for issue in issues[:10]:
        if not isinstance(issue, dict):
            continue
        metric = str(issue.get("metric") or "")[:120]
        if not metric:
            continue
        rows.append(
            {
                "metric": metric,
                "value": _optional_float(issue.get("value")),
                "threshold": _optional_float(issue.get("threshold")),
                "reason": str(issue.get("reason") or "")[:160],
            }
        )
    return rows


def _empty_evaluation_quality_gate():
    """Return the default quality gate payload when no evaluation run exists."""
    return {
        "status": "unknown",
        "passed": False,
        "blocking": [],
        "warnings": [],
        "summary": "Keine Retrieval-Evaluation vorhanden.",
    }


def _debug_tools(chats, chat_message_id):
    """Return selected request details for step-by-step debugging."""
    selected = _selected_chat(chats, chat_message_id)
    if not selected:
        return {
            "selected_chat_message_id": None,
            "request_analysis": None,
            "prompt_blueprint": None,
            "available_requests": [],
        }
    return {
        "selected_chat_message_id": selected.id,
        "request_analysis": _request_analysis(selected),
        "prompt_blueprint": _prompt_blueprint(selected),
        "available_requests": [
            {
                "answer_uncertainty": _answer_uncertainty(chat),
                "chat_message_id": chat.id,
                "confidence": _confidence_payload(chat),
                "created_at": chat.created_at.isoformat(),
                "question": _bounded(chat.message, 160),
                "confidence_level": chat.confidence_level,
                "source_count": chat.source_count,
            }
            for chat in chats[:20]
        ],
    }


def _selected_chat(chats, chat_message_id):
    """Return the requested chat or the newest available chat."""
    if not chats:
        return None
    if chat_message_id is None:
        return chats[0]
    for chat in chats:
        if chat.id == chat_message_id:
            return chat
    return chats[0]


def _request_analysis(chat):
    """Return one request analysis with retrieval, confidence, and safety signals."""
    diagnostics = chat.diagnostics()
    event = chat.audit_event
    explainability = (
        event.retrieval_explainability()
        if event
        else (diagnostics.get("retrieval_explainability") or {})
    )
    context_builder = (
        explainability.get("context_builder") if isinstance(explainability, dict) else {}
    )
    query_understanding = (
        (explainability.get("query_understanding") if isinstance(explainability, dict) else {})
        or diagnostics.get("query_understanding")
        or {}
    )
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    answer_quality = answer_quality_from_history_item(chat.to_dict())
    return {
        "question": _bounded(chat.message, 500),
        "answer_preview": _bounded(chat.response, 700),
        "answer_quality": answer_quality,
        "query_understanding": query_understanding,
        "retrieval": {
            "source_count": chat.source_count,
            "retrieval_duration_ms": _retrieval_duration_ms(event) if event else 0,
            "sources": [_source_reference(source) for source in (sources or [])[:10]],
            "score_summary": _score_summary(_source_rows([event]) if event else []),
        },
        "context_builder": {
            "stats": (context_builder or {}).get("stats", {}),
            "sections": _context_sections(context_builder),
            "explainability": (context_builder or {}).get("explainability", {}),
        },
        "confidence": _confidence_payload(chat, answer_quality),
        "quality_warnings": diagnostics.get("quality_warnings") or [],
        "safety": (explainability or {}).get("safety", {}),
        "post_generation_safety": (explainability or {}).get("post_generation_safety", {}),
    }


def _prompt_blueprint(chat):
    """Return a bounded prompt blueprint without raw chunk text."""
    diagnostics = chat.diagnostics()
    event = chat.audit_event
    explainability = (
        event.retrieval_explainability()
        if event
        else (diagnostics.get("retrieval_explainability") or {})
    )
    context_builder = (
        explainability.get("context_builder") if isinstance(explainability, dict) else {}
    )
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    return {
        "system_prompt": text_system_prompt(),
        "user_question": _bounded(chat.message, 1000),
        "context_visibility": "source references and context-builder sections only",
        "context_sections": _context_sections(context_builder),
        "source_references": [_source_reference(source) for source in (sources or [])[:10]],
        "prompt_preview": (
            "Kontext: "
            + _bounded(_context_preview(context_builder, sources), 1200)
            + "\n\nFrage: "
            + _bounded(chat.message, 500)
        ),
    }


def _context_sections(context_builder):
    """Return context-builder sections without full context text."""
    if not isinstance(context_builder, dict):
        return []
    sections = context_builder.get("sections") or []
    return [
        {
            "label": _bounded(section.get("label") or section.get("type"), 120),
            "source_count": section.get("source_count"),
            "used_chars": section.get("used_chars"),
            "truncated": bool(section.get("truncated")),
        }
        for section in sections[:12]
        if isinstance(section, dict)
    ]


def _context_preview(context_builder, sources):
    """Return a compact context preview based on section and source metadata."""
    sections = _context_sections(context_builder)
    section_labels = [section["label"] for section in sections if section.get("label")]
    source_labels = [_source_label(source) for source in (sources or [])[:8]]
    parts = []
    if section_labels:
        parts.append("Sections: " + ", ".join(section_labels))
    if source_labels:
        parts.append("Sources: " + ", ".join(source_labels))
    return " | ".join(parts) if parts else "Keine gespeicherten Kontext-Metadaten."


def _top_questions(chats):
    """Return frequent bounded questions grouped by normalized text."""
    grouped = {}
    for chat in chats:
        key = _normalized_question(chat.message)
        item = grouped.setdefault(
            key,
            {
                "question": _bounded(chat.message, 220),
                "count": 0,
                "latest_at": chat.created_at,
                "confidence_total": 0,
                "confidence_count": 0,
            },
        )
        item["count"] += 1
        if chat.created_at > item["latest_at"]:
            item["latest_at"] = chat.created_at
            item["question"] = _bounded(chat.message, 220)
        if chat.confidence_score is not None:
            item["confidence_total"] += chat.confidence_score
            item["confidence_count"] += 1
    rows = []
    for item in grouped.values():
        rows.append(
            {
                "question": item["question"],
                "count": item["count"],
                "latest_at": item["latest_at"].isoformat(),
                "average_confidence": _average_from_total(
                    item["confidence_total"],
                    item["confidence_count"],
                ),
            }
        )
    return sorted(rows, key=lambda row: (row["count"], row["latest_at"]), reverse=True)[:10]


def _frequent_search_terms(chats):
    """Return common informative terms from AI questions."""
    stopwords = {
        "bitte",
        "das",
        "der",
        "die",
        "eine",
        "fuer",
        "für",
        "ich",
        "ist",
        "mit",
        "und",
        "was",
        "welche",
        "wie",
        "zu",
    }
    counter = Counter()
    for chat in chats:
        for token in tokenize_text(chat.message):
            if len(token) < 3 or token in stopwords:
                continue
            counter[token] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(10)]


def _feedback_summary(feedback_entries):
    """Return positive, neutral and negative feedback counters."""
    positive = sum(1 for feedback in feedback_entries if feedback.rating == "helpful")
    partial = sum(1 for feedback in feedback_entries if feedback.rating == "partially_helpful")
    negative = sum(1 for feedback in feedback_entries if feedback.rating in NEGATIVE_RATINGS)
    total = positive + partial + negative
    return {
        "total": total,
        "positive": positive,
        "partially_helpful": partial,
        "negative": negative,
        "positive_rate": _rate(positive, total),
        "negative_rate": _rate(negative, total),
    }


def _cost_windows(events):
    """Return rolling AI cost totals for day, week and month windows."""
    now = utc_now()
    windows = {
        "day": now - timedelta(days=1),
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
    }
    return {
        name: round(
            sum(
                float(event.estimated_cost_usd or 0.0)
                for event in events
                if _is_at_or_after(event.created_at, since)
            ),
            6,
        )
        for name, since in windows.items()
    }


def _is_at_or_after(value, since):
    """Return whether a possibly timezone-naive datetime is inside a window."""
    if not value:
        return False
    left = value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value
    right = since.replace(tzinfo=None) if getattr(since, "tzinfo", None) else since
    return left >= right


def _reranking_metrics(events):
    """Return aggregate prompt-safe reranking diagnostics from audit metadata."""
    rows = []
    for event in events:
        explainability = event.retrieval_explainability()
        debug = explainability.get("retrieval_debug") if isinstance(explainability, dict) else {}
        reranking = debug.get("reranking") if isinstance(debug, dict) else {}
        if not isinstance(reranking, dict):
            continue
        rows.append(
            {
                "candidate_limit": _optional_int(reranking.get("candidate_limit")),
                "candidate_count": _optional_int(reranking.get("candidate_count")),
                "final_top_k": _optional_int(reranking.get("final_top_k")),
                "final_source_count": _optional_int(reranking.get("final_source_count")),
                "reduction_rate": _optional_float(reranking.get("reduction_rate")),
            }
        )
    return {
        "request_count": len(rows),
        "average_candidate_limit": _average(
            row["candidate_limit"] for row in rows if row["candidate_limit"] is not None
        ),
        "average_candidate_count": _average(
            row["candidate_count"] for row in rows if row["candidate_count"] is not None
        ),
        "average_final_top_k": _average(
            row["final_top_k"] for row in rows if row["final_top_k"] is not None
        ),
        "average_final_source_count": _average(
            row["final_source_count"] for row in rows if row["final_source_count"] is not None
        ),
        "average_reduction_rate": _average(
            row["reduction_rate"] for row in rows if row["reduction_rate"] is not None
        ),
    }


def _knowledge_gap_metrics(chats=None):
    """Return compact knowledge-gap counters for AI admin dashboards."""
    open_gaps = KnowledgeGap.query.filter_by(status="open").count()
    detection = knowledge_gap_detection({"limit": DEFAULT_OBSERVABILITY_LIMIT})
    uncertain_question_gaps = _uncertain_question_gap_rows(chats or [])
    uncertain_question_actions = _uncertain_question_gap_actions(uncertain_question_gaps)
    top_gaps = (
        KnowledgeGap.query.order_by(
            KnowledgeGap.occurrence_count.desc(),
            KnowledgeGap.last_seen_at.desc(),
            KnowledgeGap.id.desc(),
        )
        .limit(10)
        .all()
    )
    detection_summary = detection.get("summary") or {}
    recommended_actions = (
        list(detection.get("knowledge_gap_actions") or []) + uncertain_question_actions
    )[:10]
    action_priority_counts = Counter(
        str(action.get("priority") or "unknown") for action in recommended_actions
    )
    action_type_counts = Counter(
        str(action.get("type") or "unknown") for action in recommended_actions
    )
    return {
        "open_count": open_gaps,
        "recurring_count": detection_summary.get("recurring_gap_count", 0),
        "machine_gap_count": detection_summary.get("machine_gap_count", 0),
        "error_gap_count": detection_summary.get("error_gap_count", 0),
        "uncovered_error_gap_count": detection_summary.get("uncovered_error_gap_count", 0),
        "critical_uncovered_error_gap_count": detection_summary.get(
            "critical_uncovered_error_gap_count",
            0,
        ),
        "uncovered_machine_gap_count": detection_summary.get(
            "uncovered_machine_gap_count",
            0,
        ),
        "critical_uncovered_machine_gap_count": detection_summary.get(
            "critical_uncovered_machine_gap_count",
            0,
        ),
        "department_gap_count": detection_summary.get("department_gap_count", 0),
        "uncertain_question_gap_count": len(uncertain_question_gaps),
        "high_uncertainty_answer_count": sum(item["count"] for item in uncertain_question_gaps),
        "uncertain_question_gaps": uncertain_question_gaps,
        "uncertain_question_actions": uncertain_question_actions,
        "uncertain_question_action_count": len(uncertain_question_actions),
        "frequent_terms": detection.get("frequent_terms") or [],
        "machine_gaps": detection.get("machine_gaps") or [],
        "uncovered_machine_gaps": detection.get("uncovered_machine_gaps") or [],
        "error_gaps": detection.get("error_gaps") or [],
        "uncovered_error_gaps": detection.get("uncovered_error_gaps") or [],
        "department_gaps": detection.get("department_gaps") or [],
        "recommended_actions": recommended_actions,
        "action_count": len(recommended_actions),
        "high_priority_action_count": action_priority_counts.get("high", 0),
        "action_priority_distribution": _counter_rows(action_priority_counts),
        "action_type_distribution": _counter_rows(action_type_counts),
        "top_gaps": [
            {
                "id": gap.id,
                "question_hash": gap.question_hash,
                "status": gap.status,
                "occurrence_count": gap.occurrence_count,
                "machine": gap.machine,
                "department": gap.department,
                "last_seen_at": gap.last_seen_at.isoformat(),
            }
            for gap in top_gaps
        ],
    }


def _uncertain_question_gap_rows(chats):
    """Return high-uncertainty question groups as potential knowledge gaps."""
    grouped = {}
    for chat in chats:
        answer_quality = answer_quality_from_history_item(chat.to_dict())
        if answer_quality.get("uncertainty") != "high":
            continue
        key = _normalized_question(chat.message)
        item = grouped.setdefault(
            key,
            {
                "question": _bounded(chat.message, 220),
                "count": 0,
                "no_answer_count": 0,
                "latest_at": chat.created_at,
                "confidence_total": 0,
                "confidence_count": 0,
                "knowledge_gap_id": None,
            },
        )
        item["count"] += 1
        if answer_quality.get("status") == "no_answer":
            item["no_answer_count"] += 1
        if chat.confidence_score is not None:
            item["confidence_total"] += chat.confidence_score
            item["confidence_count"] += 1
        if chat.created_at >= item["latest_at"]:
            item["latest_at"] = chat.created_at
            item["question"] = _bounded(chat.message, 220)
            item["knowledge_gap_id"] = _optional_int(chat.diagnostics().get("knowledge_gap_id"))
    rows = [
        {
            "question": item["question"],
            "count": item["count"],
            "no_answer_count": item["no_answer_count"],
            "latest_at": item["latest_at"].isoformat(),
            "average_confidence": _average_from_total(
                item["confidence_total"],
                item["confidence_count"],
            ),
            "answer_uncertainty": "high",
            "knowledge_gap_id": item["knowledge_gap_id"],
        }
        for item in grouped.values()
    ]
    return sorted(rows, key=lambda row: (row["count"], row["latest_at"]), reverse=True)[:10]


def _uncertain_question_gap_actions(rows):
    """Return remediation actions for high-uncertainty answer clusters."""
    actions = []
    for row in rows[:5]:
        priority = "high" if row["no_answer_count"] or row["count"] >= 3 else "medium"
        actions.append(
            {
                "type": "review_uncertain_answer_gap",
                "priority": priority,
                "target_type": "ai_question",
                "target_id": row.get("knowledge_gap_id"),
                "target": row["question"],
                "reason": (
                    f"{row['count']} hoch unsichere Antwort(en), "
                    f"{row['no_answer_count']} No-Answer-Fall/Faelle"
                ),
                "recommended_action": (
                    "Frage fachlich klaeren und fehlende Knowledge-Quelle oder "
                    "Golden Test Question ergaenzen."
                ),
                "next_steps": [
                    "Unsichere Antwort mit Fachverantwortlichen fachlich pruefen.",
                    "Fehlende Dokumentation, FAQ oder Fehlerwissen als Knowledge-Quelle anlegen.",
                    "Golden Test Question mit erwarteter Quelle und Keywords ergaenzen.",
                ],
                "success_criteria": [
                    "Wiederholte Frage liefert eine belegte Antwort mit sichtbarer Quelle.",
                    "Antwort-Unsicherheit sinkt nach erneuter RAG-Evaluation.",
                ],
            }
        )
    return actions


def _source_rows(events):
    """Return flattened source rows from audit events."""
    rows = []
    for event in events:
        if not event:
            continue
        explainability = event.retrieval_explainability()
        sources = explainability.get("sources") if isinstance(explainability, dict) else []
        for rank, source in enumerate(sources or [], start=1):
            score = _source_score(source)
            similarity = _source_similarity(source)
            source_type = source.get("type") or "knowledge"
            source_id = _optional_int(source.get("id"))
            source_created_at = _bounded(source.get("created_at"), 40)
            rows.append(
                {
                    "audit_event_id": event.id,
                    "workflow": event.workflow,
                    "rank": rank,
                    "source_type": source_type,
                    "source_id": source_id,
                    "source_record_id": _optional_int(source.get("source_record_id")),
                    "title": _source_title(source, source_type, source_id),
                    "source_kind": _bounded(source.get("source_kind"), 80),
                    "knowledge_source_type": _bounded(source.get("knowledge_source_type"), 80),
                    "module": _bounded(source.get("module"), 80),
                    "machine_id": _optional_int(source.get("machine_id")),
                    "role_visibility": _bounded(source.get("role_visibility"), 140),
                    "role": _bounded(source.get("role"), 80),
                    "employee_access_level": _bounded(
                        source.get("employee_access_level"),
                        40,
                    ),
                    "chunk_id": _optional_int(source.get("chunk_id")),
                    "section_title": _bounded(
                        source.get("section_title") or source.get("source_section"),
                        160,
                    ),
                    "score": score,
                    "similarity": similarity,
                    "quality_status": _source_quality(source),
                    "source_created_at": source_created_at,
                    "source_age_days": _source_age_days(source_created_at),
                    "retrieved_at": event.created_at.isoformat(),
                    "created_at": event.created_at.isoformat(),
                }
            )
    return rows


def _source_distribution(events):
    """Return source usage counts by source type."""
    counter = Counter()
    for event in events:
        for row in _source_rows([event]):
            counter[row["source_type"]] += 1
    return dict(counter)


def _source_kind_distribution(events):
    """Return source usage counts by retrieval source kind."""
    counter = Counter()
    for event in events:
        for row in _source_rows([event]):
            counter[row.get("source_kind") or "unknown"] += 1
    return dict(counter)


def _top_hit_rows(source_rows, limit):
    """Return top retrieval hits by rank and score."""
    rows = sorted(
        source_rows,
        key=lambda row: (
            0 if row["rank"] == 1 else -row["rank"],
            row["score"] if row["score"] is not None else -1,
            row["similarity"] if row["similarity"] is not None else -1,
        ),
        reverse=True,
    )
    return [_source_hit_payload(row) for row in rows[:limit]]


def _poor_hit_rows(source_rows, negative_feedback_ids, limit):
    """Return low-quality retrieval hits for monitoring."""
    poor_rows = [
        row
        for row in source_rows
        if row["audit_event_id"] in negative_feedback_ids
        or (row["score"] is not None and row["score"] <= LOW_SCORE_THRESHOLD)
        or (row["similarity"] is not None and row["similarity"] <= LOW_SIMILARITY_THRESHOLD)
    ]
    poor_rows.sort(
        key=lambda row: (
            row["audit_event_id"] in negative_feedback_ids,
            -(row["score"] if row["score"] is not None else 1000),
            -(row["similarity"] if row["similarity"] is not None else 1),
        ),
        reverse=True,
    )
    return [_source_hit_payload(row) for row in poor_rows[:limit]]


def _source_hit_payload(row):
    """Return one retrieval-hit payload."""
    payload = dict(row)
    payload["label"] = _source_row_label(row)
    return payload


def _score_summary(source_rows):
    """Return aggregate retrieval score metrics."""
    scores = [row["score"] for row in source_rows if row.get("score") is not None]
    similarities = [row["similarity"] for row in source_rows if row.get("similarity") is not None]
    return {
        "source_count": len(source_rows),
        "average_score": _average(scores),
        "average_similarity": _average(similarities),
        "low_score_count": sum(1 for score in scores if score <= LOW_SCORE_THRESHOLD),
        "low_similarity_count": sum(
            1 for similarity in similarities if similarity <= LOW_SIMILARITY_THRESHOLD
        ),
    }


def _retrieval_quality_actions(poor_hits, score_summary):
    """Return remediation actions for weak or negatively rated retrieval hits."""
    if not poor_hits:
        return []
    low_score_count = int(score_summary.get("low_score_count") or 0)
    low_similarity_count = int(score_summary.get("low_similarity_count") or 0)
    priority = "high" if low_score_count or low_similarity_count else "medium"
    return [
        {
            "type": "review_low_quality_retrieval_hits",
            "priority": priority,
            "target_type": "retrieval_quality",
            "target": "poor_hits",
            "count": len(poor_hits),
            "low_score_count": low_score_count,
            "low_similarity_count": low_similarity_count,
            "sample_sources": _source_action_samples(poor_hits),
            "reason": (
                f"{len(poor_hits)} Retrieval-Treffer wurden durch negatives Feedback "
                "oder schwache Score-Signale markiert."
            ),
            "recommended_action": (
                "Schlechte Treffer pruefen, Chunk-Zuschnitt und Metadaten verbessern "
                "oder fehlende Golden Test Questions ergaenzen."
            ),
            "next_steps": [
                "Poor-Hit-Beispiele fachlich mit der Nutzerfrage vergleichen.",
                "Chunk-Metadaten, Source-Titel und Maschinenbezug fuer diese Quellen pruefen.",
                "Golden Test Question fuer den betroffenen Fragetyp ergaenzen.",
            ],
            "success_criteria": [
                "Negative Feedback-Hits gehen nach Reindex/Evaluation zurueck.",
                "Recall und MRR bleiben stabil oder verbessern sich.",
            ],
        }
    ]


def _source_freshness_summary(source_rows):
    """Return source age metrics for retrieval monitoring."""
    stale_days = knowledge_aging_policy().stale_days
    age_values = []
    undated_count = 0
    for row in source_rows:
        age_days = row.get("source_age_days")
        if age_days is None:
            undated_count += 1
            continue
        age_values.append(age_days)
    stale_count = sum(1 for age_days in age_values if age_days >= stale_days)
    return {
        "stale_threshold_days": stale_days,
        "measured_source_count": len(age_values),
        "undated_source_count": undated_count,
        "average_source_age_days": _average(age_values),
        "oldest_source_age_days": max(age_values) if age_values else 0,
        "stale_source_count": stale_count,
        "stale_source_rate": _rate(stale_count, len(age_values)),
    }


def _stale_source_rows(source_rows, limit):
    """Return bounded stale source rows for admin review."""
    stale_days = knowledge_aging_policy().stale_days
    rows = [
        row
        for row in source_rows
        if row.get("source_age_days") is not None and row["source_age_days"] >= stale_days
    ]
    rows.sort(
        key=lambda row: (
            row.get("source_age_days") or 0,
            str(row.get("retrieved_at") or ""),
        ),
        reverse=True,
    )
    payloads = []
    for row in rows[:limit]:
        payload = _source_hit_payload(row)
        payload["stale_threshold_days"] = stale_days
        payloads.append(payload)
    return payloads


def _undated_source_rows(source_rows, limit):
    """Return bounded source rows without parseable source timestamps."""
    rows = [row for row in source_rows if row.get("source_age_days") is None]
    rows.sort(key=lambda row: str(row.get("retrieved_at") or ""), reverse=True)
    return [_source_hit_payload(row) for row in rows[:limit]]


def _source_metadata_quality_actions(source_freshness, stale_sources, undated_sources):
    """Return source metadata remediation actions for AI admin dashboards."""
    actions = []
    stale_count = int(source_freshness.get("stale_source_count") or 0)
    undated_count = int(source_freshness.get("undated_source_count") or 0)
    stale_days = int(source_freshness.get("stale_threshold_days") or 0)
    if stale_count:
        actions.append(
            {
                "type": "review_stale_sources",
                "priority": "high" if stale_count >= 3 else "medium",
                "target_type": "retrieval_source_metadata",
                "target": "stale_sources",
                "count": stale_count,
                "stale_threshold_days": stale_days,
                "sample_sources": _source_action_samples(stale_sources),
                "reason": (
                    f"{stale_count} abgerufene Quelle(n) sind aelter als " f"{stale_days} Tage."
                ),
                "recommended_action": (
                    "Quellen fachlich pruefen, veraltete Inhalte aktualisieren "
                    "oder als ueberholt markieren."
                ),
                "next_steps": [
                    "Stale Source-Liste nach haeufig genutzten Dokumenten priorisieren.",
                    "Fachverantwortliche Aktualitaet und Gueltigkeit pruefen lassen.",
                    "Aktualisierte Dokumente neu indexieren und Retrieval-Evaluation wiederholen.",
                ],
                "success_criteria": [
                    "Stale-Source-Rate sinkt im Observability-Dashboard.",
                    "Antworten nutzen aktualisierte Quellen mit sichtbaren Zeitstempeln.",
                ],
            }
        )
    if undated_count:
        actions.append(
            {
                "type": "complete_source_dates",
                "priority": "medium",
                "target_type": "retrieval_source_metadata",
                "target": "undated_sources",
                "count": undated_count,
                "sample_sources": _source_action_samples(undated_sources),
                "reason": (
                    f"{undated_count} abgerufene Quelle(n) haben kein auswertbares " "Source-Datum."
                ),
                "recommended_action": (
                    "Fehlende created_at/source_created_at Metadaten ergaenzen, "
                    "damit RAG-Frische und Recency-Ranking belastbar werden."
                ),
                "next_steps": [
                    "Undatierte Quellen auf Import- oder Dokument-Metadaten pruefen.",
                    "Erstell- oder Gueltigkeitsdatum in der Knowledge-Quelle nachpflegen.",
                    "Quelle neu indexieren und Source-Freshness erneut kontrollieren.",
                ],
                "success_criteria": [
                    "Undated-Source-Count faellt auf null oder ist fachlich begruendet.",
                    "Recency- und Aging-Signale koennen die Quelle bewerten.",
                ],
            }
        )
    return actions


def _source_action_samples(rows, limit=3):
    """Return compact source labels for metadata action previews."""
    samples = []
    for row in rows[:limit]:
        samples.append(
            {
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "source_record_id": row.get("source_record_id"),
                "title": row.get("title"),
                "label": row.get("label"),
            }
        )
    return samples


def _retrieval_action_summary(actions):
    """Return aggregate retrieval action counters for admin dashboards."""
    return _action_summary(actions)


def _recommended_action_summary(actions, metrics):
    """Return root action summary plus related action families not in the top list."""
    summary = _action_summary(actions)
    answer_quality_actions = metrics.get("answer_quality_actions") or []
    answer_quality_summary = metrics.get("answer_quality_action_summary") or {}
    summary["answer_quality_action_count"] = int(metrics.get("answer_quality_action_count") or 0)
    summary["answer_quality_high_action_count"] = int(
        answer_quality_summary.get("high_priority_count") or 0
    )
    if answer_quality_actions:
        next_action = answer_quality_actions[0]
        summary["answer_quality_next_action_type"] = str(next_action.get("type") or "")
        summary["answer_quality_next_action_priority"] = str(next_action.get("priority") or "")
    return summary


def _action_summary(actions):
    """Return aggregate action counters for admin dashboards."""
    priority_counts = Counter(str(action.get("priority") or "unknown") for action in actions)
    type_counts = Counter(str(action.get("type") or "unknown") for action in actions)
    source_counts = Counter(
        str(action.get("action_source")) for action in actions if action.get("action_source")
    )
    summary = {
        "total": len(actions),
        "critical_priority_count": priority_counts.get("critical", 0),
        "high_priority_count": priority_counts.get("high", 0),
        "medium_priority_count": priority_counts.get("medium", 0),
        "priority_distribution": _counter_rows(priority_counts),
        "type_distribution": _counter_rows(type_counts),
    }
    if actions:
        next_action = actions[0]
        summary["next_action_type"] = str(next_action.get("type") or "")
        summary["next_action_priority"] = str(next_action.get("priority") or "")
        if next_action.get("action_source"):
            summary["next_action_source"] = str(next_action.get("action_source"))
    if source_counts:
        summary["source_distribution"] = _counter_rows(source_counts)
    return summary


def _source_age_days(value):
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


def _chunk_usage_rows(counter, limit):
    """Return frequently used chunk references."""
    rows = []
    for (source_id, chunk_id, source_type), count in counter.most_common(limit):
        rows.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "chunk_id": chunk_id,
                "uses": count,
                "label": _knowledge_title(source_id) if source_type == "knowledge" else "",
            }
        )
    return rows


def _document_usage_rows(counter, limit):
    """Return frequently used document or structured source references."""
    rows = []
    for (source_type, source_id), count in counter.most_common(limit):
        rows.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "uses": count,
                "label": _knowledge_title(source_id) if source_type == "knowledge" else "",
            }
        )
    return rows


def _source_reference(source):
    """Return one source reference without chunk body text."""
    source_type = source.get("type") or "knowledge"
    source_id = _optional_int(source.get("id"))
    return {
        "type": source_type,
        "id": source_id,
        "title": _source_title(source, source_type, source_id),
        "source_record_id": _optional_int(source.get("source_record_id")),
        "source_kind": _bounded(source.get("source_kind"), 80),
        "knowledge_source_type": _bounded(source.get("knowledge_source_type"), 80),
        "module": _bounded(source.get("module"), 80),
        "machine_id": _optional_int(source.get("machine_id")),
        "role_visibility": _bounded(source.get("role_visibility"), 140),
        "role": _bounded(source.get("role"), 80),
        "employee_access_level": _bounded(source.get("employee_access_level"), 40),
        "created_at": _bounded(source.get("created_at"), 40),
        "chunk_id": _optional_int(source.get("chunk_id")),
        "section_title": _bounded(
            source.get("section_title") or source.get("source_section"),
            160,
        ),
        "score": _source_score(source),
        "similarity": _source_similarity(source),
        "quality_status": _source_quality(source),
        "label": _source_label(source),
    }


def _source_title(source, source_type=None, source_id=None):
    """Return a bounded prompt-safe source title."""
    title = _bounded(source.get("title") or source.get("source_title"), 180)
    if title:
        return title
    safe_type = str(source_type or source.get("type") or "knowledge")
    safe_id = source_id if source_id is not None else _optional_int(source.get("id"))
    return _knowledge_title(safe_id) if safe_type == "knowledge" else ""


def _source_label(source):
    """Return a readable source reference label."""
    source_type = str(source.get("type") or "knowledge")
    source_id = _optional_int(source.get("id"))
    chunk_id = _optional_int(source.get("chunk_id"))
    section = _bounded(source.get("section_title") or source.get("source_section"), 80)
    label = source_type
    if source_type == "knowledge" and source_id:
        title = _knowledge_title(source_id)
        if title:
            label = title
    elif source_id is not None:
        label = f"{source_type} #{source_id}"
    if chunk_id is not None:
        label = f"{label} / Chunk #{chunk_id}"
    if section:
        label = f"{label} - {section}"
    return label


def _source_row_label(row):
    """Return a source label from a flattened source row."""
    source = {
        "type": row.get("source_type"),
        "id": row.get("source_id"),
        "chunk_id": row.get("chunk_id"),
        "section_title": row.get("section_title"),
    }
    return _source_label(source)


def _source_score(source):
    """Return the best score available for a source."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if isinstance(explainability, dict) and explainability.get("final_score") is not None:
        return _optional_float(explainability.get("final_score"))
    return _optional_float(source.get("score") if isinstance(source, dict) else None)


def _source_similarity(source):
    """Return semantic similarity for one source when available."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if not isinstance(explainability, dict):
        return None
    return _optional_float(explainability.get("semantic_similarity"))


def _source_quality(source):
    """Return source quality status."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if isinstance(explainability, dict) and explainability.get("quality_status"):
        return str(explainability.get("quality_status"))
    return str(source.get("quality_status") or "") if isinstance(source, dict) else ""


def _retrieval_duration_ms(event):
    """Return retrieval duration from stored explainability."""
    if not event:
        return None
    explainability = event.retrieval_explainability()
    if not isinstance(explainability, dict):
        return None
    return _optional_int(explainability.get("retrieval_duration_ms"))


def _similarity_values(events):
    """Return all semantic similarity samples from audit events."""
    values = []
    for row in _source_rows(events):
        if row.get("similarity") is not None:
            values.append(row["similarity"])
    return values


def _is_empty_retrieval(chat):
    """Return whether a chat was answered without retrieved sources."""
    diagnostics = chat.diagnostics()
    return bool(diagnostics.get("empty_retrieval")) or int(chat.source_count or 0) == 0


def _is_structured_answer(chat):
    """Return whether a chat used the structured database answer path."""
    return _structured_domain(chat) is not None


def _is_rag_answer(chat):
    """Return whether a chat looks like a RAG-backed unstructured answer."""
    diagnostics = chat.diagnostics()
    if str(diagnostics.get("answer_category") or "") == "rag":
        return True
    if _is_structured_answer(chat) or int(chat.source_count or 0) <= 0:
        return False
    return str(chat.response_type or "") not in {"permission_denied", "local_answer"}


def _structured_domain(chat):
    """Return the structured business domain for a chat, if it used app data."""
    response_type = str(chat.response_type or "").strip()
    diagnostics = chat.diagnostics()
    if response_type == "permission_denied" or diagnostics.get("status") == "permission_denied":
        return None
    domain = _structured_domain_from_context(diagnostics.get("structured_context") or {})
    if domain:
        return domain
    if str(diagnostics.get("answer_category") or "") == "structured_data":
        return "unknown"
    return None


def _structured_domain_from_context(context):
    """Return a structured domain from persisted structured context metadata."""
    if not isinstance(context, dict):
        return ""
    entity_type = str(context.get("entity_type") or "").strip()
    return STRUCTURED_ENTITY_DOMAINS.get(entity_type, "")


def _is_answered_chat(chat):
    """Return whether a chat should count toward answered-source averages."""
    return (
        not _is_permission_denied_chat(chat)
        and not _is_no_answer(chat)
        and not _is_no_source_no_data_chat(chat)
    )


def _no_source_breakdown(chats):
    """Return clearer no-source buckets without changing legacy totals."""
    breakdown = {
        "permission_denied": 0,
        "no_data": 0,
        "answered_without_sources": 0,
    }
    for chat in chats:
        if int(chat.source_count or 0) != 0:
            continue
        if _is_permission_denied_chat(chat):
            breakdown["permission_denied"] += 1
        elif _is_no_source_no_data_chat(chat):
            breakdown["no_data"] += 1
        else:
            breakdown["answered_without_sources"] += 1
    return breakdown


def _is_permission_denied_chat(chat):
    """Return whether a chat represents an explicit permission denial."""
    diagnostics = chat.diagnostics()
    return (
        str(chat.response_type or "") == "permission_denied"
        or str(diagnostics.get("status") or "") == "permission_denied"
    )


def _is_no_source_no_data_chat(chat):
    """Return whether a no-source chat is a structured no-data response."""
    return int(chat.source_count or 0) == 0 and _is_structured_answer(chat)


def _structured_module_distribution(chats):
    """Return answer counts grouped by structured Maintenance module."""
    counter = Counter()
    for chat in chats:
        domain = _structured_domain(chat)
        if not domain:
            continue
        counter[domain] += 1
    return {
        "counts": dict(counter),
        "rows": [
            {
                "module": module,
                "label": _structured_module_label(module),
                "count": count,
                "rate": _rate(count, sum(counter.values())),
            }
            for module, count in counter.most_common()
        ],
    }


def _structured_module_label(module):
    """Return a compact German label for one structured module key."""
    labels = {**STRUCTURED_DOMAIN_LABELS, "unknown": "Unbekannt"}
    return labels.get(str(module or "unknown"), str(module or "unknown"))


def _is_no_answer(chat):
    """Return whether a chat ended in explicit no-answer handling."""
    return answer_quality_from_history_item(chat.to_dict()).get("status") == "no_answer"


def _answer_quality_distribution(chats):
    """Return answer-quality status counts and rates for admin dashboards."""
    counter = Counter(
        answer_quality_from_history_item(chat.to_dict()).get("status") or "unverified"
        for chat in chats
    )
    total = len(chats)
    rows = [
        {
            "status": status,
            "count": count,
            "rate": _rate(count, total),
        }
        for status, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def _primary_warning_distribution(chats):
    """Return primary answer-quality warning counts and rates for admin dashboards."""
    counter = Counter(
        answer_quality_from_history_item(chat.to_dict()).get("primary_warning_type") or "none"
        for chat in chats
    )
    total = len(chats)
    rows = [
        {
            "warning_type": warning_type,
            "count": count,
            "rate": _rate(count, total),
        }
        for warning_type, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def _answer_quality_reason_distribution(chats):
    """Return answer-quality reason counts and rates for admin dashboards."""
    counter = Counter(
        answer_quality_from_history_item(chat.to_dict()).get("status_reason") or "unverified_answer"
        for chat in chats
    )
    total = len(chats)
    rows = [
        {
            "status_reason": status_reason,
            "count": count,
            "rate": _rate(count, total),
        }
        for status_reason, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def _answer_quality_reason_actions(reason_counts):
    """Return remediation actions for answer-quality reason aggregates."""
    counts = reason_counts or {}
    actions = []
    no_answer_count = int(counts.get("empty_retrieval_hallucination_guard") or 0)
    if no_answer_count:
        actions.append(
            {
                "type": "review_no_answer_guarded_questions",
                "priority": "high",
                "target_type": "answer_quality_reason",
                "target": "empty_retrieval_hallucination_guard",
                "count": no_answer_count,
                "reason": (
                    f"{no_answer_count} Antwort(en) wurden wegen leerem Retrieval "
                    "und Hallucination-Guard als No-Answer markiert."
                ),
                "recommended_action": (
                    "Knowledge Gaps, fehlende Dokumente und Retrieval-Filter fuer "
                    "diese Fragen pruefen."
                ),
                "next_steps": [
                    "No-Answer-Fragen im AI Admin nach Knowledge Gaps gruppieren.",
                    "Fehlende Maschinen-, Fehler- oder Wartungsdokumente ergaenzen.",
                    "Nach Reindex Retrieval-Hit-Rate und No-Answer-Rate vergleichen.",
                ],
            }
        )
    conflict_count = int(counts.get("source_conflict_detected") or 0)
    if conflict_count:
        actions.append(
            {
                "type": "review_conflicting_answer_sources",
                "priority": "medium",
                "target_type": "answer_quality_reason",
                "target": "source_conflict_detected",
                "count": conflict_count,
                "reason": (
                    f"{conflict_count} Antwort(en) wurden wegen widerspruechlicher "
                    "Quellen markiert."
                ),
                "recommended_action": (
                    "Konfliktquellen fachlich pruefen und bestaetigte Fassung " "dokumentieren."
                ),
                "next_steps": [
                    "Betroffene AI-Logs nach Quellenkonflikten filtern.",
                    "Veraltete oder widerspruechliche Dokumente markieren.",
                    "Nach Korrektur betroffene Golden Questions erneut ausfuehren.",
                ],
            }
        )
    return actions[:5]


def _uncertainty_distribution(chats):
    """Return answer uncertainty counts and rates for admin dashboards."""
    counter = Counter(
        answer_quality_from_history_item(chat.to_dict()).get("uncertainty") or "unknown"
        for chat in chats
    )
    total = len(chats)
    rows = [
        {"uncertainty": uncertainty, "count": count, "rate": _rate(count, total)}
        for uncertainty, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def _has_hallucination_warning(chat):
    """Return whether a chat has a hallucination-risk warning."""
    diagnostics = chat.diagnostics()
    if diagnostics.get("hallucination_warning"):
        return True
    warnings = diagnostics.get("quality_warnings") or []
    return any(
        isinstance(warning, dict) and warning.get("type") == "hallucination_risk"
        for warning in warnings
    )


def _answer_quality_label(chat, warnings):
    """Return a simple quality label for one answer."""
    if _has_hallucination_warning(chat):
        return "risk"
    if _has_source_conflict(chat):
        return "conflict"
    if chat.confidence_level == "low" or warnings:
        return "warning"
    if chat.confidence_level == "high" and int(chat.source_count or 0) > 0:
        return "good"
    return "ok"


def _has_source_conflict(chat):
    """Return whether a chat answer used conflicting source evidence."""
    diagnostics = chat.diagnostics()
    if (diagnostics.get("source_conflicts") or {}).get("has_conflicts"):
        return True
    warnings = diagnostics.get("quality_warnings") or []
    return any(
        isinstance(warning, dict) and warning.get("type") == "source_conflict"
        for warning in warnings
    )


def _is_low_confidence_chat(chat):
    """Return whether a chat answer should count as low confidence."""
    diagnostics = chat.diagnostics()
    confidence = diagnostics.get("confidence") or {}
    level = str(
        chat.confidence_level
        or diagnostics.get("confidence_level")
        or confidence.get("level")
        or "",
    ).strip()
    if level == "low":
        return True
    score = _optional_int(
        chat.confidence_score or diagnostics.get("confidence_score") or confidence.get("score"),
    )
    return score is not None and score <= LOW_CONFIDENCE_SCORE_THRESHOLD


def _is_error_event(event):
    """Return whether an audit event counts as an AI error."""
    status = str(event.status or "").strip()
    return (
        status in CONFIGURATION_FAILURE_STATUSES
        or bool(event.error_category)
        or "error" in status.lower()
    )


def _failure_reason_distribution(events):
    """Return prompt-safe failed request reason counts."""
    counter = Counter(_failure_reason(event) for event in events if _is_error_event(event))
    return [{"reason": reason, "count": count} for reason, count in counter.most_common() if reason]


def _failure_reason(event):
    """Return a normalized prompt-safe failure reason for one audit event."""
    status = str(event.status or "").strip()
    if status in CONFIGURATION_FAILURE_STATUSES:
        return status
    if "error" in status.lower() and event.error_category:
        return str(event.error_category or "").strip()[:120]
    if event.error_category:
        return str(event.error_category or "").strip()[:120]
    return status[:120]


def _confidence_payload(chat, answer_quality=None):
    """Return prompt-safe confidence metadata enriched with answer uncertainty."""
    quality = answer_quality or answer_quality_from_history_item(chat.to_dict())
    return {
        "score": chat.confidence_score,
        "level": chat.confidence_level,
        "uncertainty": quality.get("uncertainty") or "unknown",
    }


def _answer_uncertainty(chat):
    """Return the answer uncertainty label for compact request selectors."""
    return _confidence_payload(chat)["uncertainty"]


def _langfuse_reference(diagnostics):
    """Return safe Langfuse trace identifiers from diagnostics."""
    return {
        "enabled": bool(diagnostics.get("langfuse_enabled")),
        "trace_id": diagnostics.get("langfuse_trace_id") or "",
        "observation_id": diagnostics.get("langfuse_observation_id") or "",
        "host": diagnostics.get("langfuse_host") or "",
    }


def _counter_rows(counter):
    """Return sorted counter rows."""
    return [{"key": key, "count": count} for key, count in Counter(counter).most_common()]


def _normalized_question(message):
    """Return a stable grouping key for common question analysis."""
    return " ".join(str(message or "").lower().split())[:300]


def _knowledge_title(document_id):
    """Return a knowledge document title for a source id if it still exists."""
    if document_id is None:
        return ""
    try:
        document = db.session.get(KnowledgeDocument, int(document_id))
    except (TypeError, ValueError):
        return ""
    return _bounded(getattr(document, "title", ""), 180) if document else ""


def _token_usage(events):
    """Return token usage metrics from audit events without duplicating counters."""
    total_tokens = sum(event.total_tokens or 0 for event in events)
    input_tokens = sum(event.input_tokens or 0 for event in events)
    output_tokens = sum(event.output_tokens or 0 for event in events)
    cached_tokens = sum(event.cached_tokens or 0 for event in events)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
        "average_tokens": _average([event.total_tokens for event in events]),
        "cache_rate": _rate(cached_tokens, input_tokens),
    }


def _cost_metrics(cost_windows, events):
    """Return cost metrics from the existing rolling cost windows."""
    total_tokens = sum(event.total_tokens or 0 for event in events)
    estimated_cost = round(sum(float(event.estimated_cost_usd or 0.0) for event in events), 6)
    return {
        "day": cost_windows.get("day", 0.0),
        "week": cost_windows.get("week", 0.0),
        "month": cost_windows.get("month", 0.0),
        "estimated_cost_usd": estimated_cost,
        "cost_per_1k_tokens": round((estimated_cost / total_tokens) * 1000, 6)
        if total_tokens
        else 0,
    }


def _latency_metrics(response_times, retrieval_times):
    """Return response and retrieval latency metrics."""
    return {
        "average_response_ms": _average(response_times),
        "p95_response_ms": _percentile(response_times, 0.95),
        "average_retrieval_ms": _average(retrieval_times),
        "p95_retrieval_ms": _percentile(retrieval_times, 0.95),
    }


def _average(values):
    """Return a rounded arithmetic mean."""
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return 0
    return round(sum(numeric_values) / len(numeric_values), 4)


def _average_from_total(total, count):
    """Return a rounded average from a total and count."""
    return round(total / count, 2) if count else None


def _percentile(values, percentile):
    """Return a nearest-rank percentile."""
    numeric_values = sorted(float(value) for value in values if value is not None)
    if not numeric_values:
        return 0
    index = max(0, min(len(numeric_values) - 1, ceil(len(numeric_values) * percentile) - 1))
    return int(round(numeric_values[index]))


def _rate(numerator, denominator):
    """Return a rounded ratio."""
    return round(numerator / denominator, 4) if denominator else 0


def _bounded_rate(value):
    """Return a clamped zero-to-one rate for observability payloads."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, parsed)), 4)


def _optional_int(value):
    """Return an optional integer value."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value):
    """Return an optional float value."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_int(value, default, minimum, maximum):
    """Return a bounded integer value."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _bounded(value, max_chars):
    """Return normalized text bounded to max chars."""
    text = " ".join(str(value or "").strip().split())
    return text[:max_chars]
