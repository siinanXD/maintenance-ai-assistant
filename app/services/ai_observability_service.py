"""Admin-facing AI monitoring and observability read models."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from flask import current_app

from app.domain_models.common import utc_now
from app.models import AIAuditEvent, AIFeedback, ChatMessage
from app.services.ai_governance_service import evaluate_governance_alerts
from app.services.ai_metric_catalog_service import metric_catalog
from app.services.ai_observability_actions import (
    build_action_summaries,
    build_source_metadata_gaps,
    empty_evaluation_quality_gate,
    evaluation_quality_actions,
    observability_recommended_actions,
    quality_gate_blocking_rows,
    quality_gate_warning_rows,
    recommended_action_summary,
)
from app.services.ai_observability_chats import (
    answer_quality_reason_actions,
    build_ai_logs,
    build_answer_quality_distribution,
    build_answer_quality_reason_distribution,
    build_failed_requests,
    build_feedback_summary,
    build_no_source_breakdown,
    build_primary_warning_distribution,
    build_structured_module_distribution,
    build_uncertainty_distribution,
    failure_reason_distribution,
    frequent_search_terms,
    has_hallucination_warning,
    has_source_conflict,
    is_answered_chat,
    is_empty_retrieval,
    is_error_event,
    is_low_confidence_chat,
    is_no_answer,
    is_rag_answer,
    is_structured_answer,
    knowledge_gap_metrics,
    top_questions,
)
from app.services.ai_observability_common import (
    DEFAULT_OBSERVABILITY_DAYS,
    DEFAULT_OBSERVABILITY_LIMIT,
    LOW_SIMILARITY_THRESHOLD,
    MAX_OBSERVABILITY_LIMIT,
    average,
    bounded_int,
    bounded_rate,
    counter_rows,
    is_at_or_after,
    optional_float,
    optional_int,
    percentile,
    rate,
)
from app.services.ai_observability_debug import debug_tools
from app.services.ai_observability_sources import (
    action_summary,
    build_reranking_metrics,
    build_retrieval_monitoring,
    build_similarity_values,
    build_source_distribution,
    build_source_kind_distribution,
    build_source_rows,
    document_usage_rows,
    retrieval_duration_ms,
    source_freshness_summary,
)
from app.services.ai_provider_readiness_service import ai_provider_readiness_snapshot
from app.services.ai_routing import ai_price_configuration_status
from app.services.langfuse_metrics_service import langfuse_metrics_summary
from app.services.retrieval_telemetry_service import retrieval_quality_analytics


def ai_observability_dashboard(args=None):
    """Return an admin-facing AI monitoring dashboard from existing telemetry."""
    args = args or {}
    days = bounded_int(args.get("days"), DEFAULT_OBSERVABILITY_DAYS, 1, 365)
    limit = bounded_int(args.get("limit"), DEFAULT_OBSERVABILITY_LIMIT, 1, MAX_OBSERVABILITY_LIMIT)
    chat_message_id = optional_int(args.get("chat_message_id"))
    since = utc_now() - timedelta(days=days)
    events = _audit_events_since(since)
    chats = _chat_messages_since(since)
    feedback_entries = _feedback_since(since)
    telemetry = retrieval_quality_analytics(days=days, limit=limit)
    provider_readiness = ai_provider_readiness_snapshot(current_app.config)
    metrics = _metrics(events, chats, feedback_entries, telemetry)
    metrics.update(_provider_readiness_metrics(provider_readiness))
    retrieval_monitoring = build_retrieval_monitoring(events, feedback_entries, limit)
    quality_metrics = _quality_metrics(events, telemetry)
    governance = evaluate_governance_alerts(
        metrics,
        quality_metrics=quality_metrics,
        retrieval_monitoring=retrieval_monitoring,
        telemetry=telemetry,
        provider_readiness=provider_readiness,
    )
    metrics.update(_governance_metrics(governance))
    recommended_actions = observability_recommended_actions(
        metrics,
        retrieval_monitoring,
        quality_metrics,
        provider_readiness,
        limit,
    )
    ai_logs = build_ai_logs(chats, limit)
    failed_requests = build_failed_requests(events, limit)
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
        "recommended_action_summary": recommended_action_summary(
            recommended_actions,
            metrics,
        ),
        "debug_tools": debug_tools(chats, chat_message_id),
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
    retrieval_times = [retrieval_duration_ms(event) for event in events]
    retrieval_times = [value for value in retrieval_times if value is not None]
    empty_retrieval_count = sum(1 for chat in chats if is_empty_retrieval(chat))
    no_answer_count = sum(1 for chat in chats if is_no_answer(chat))
    hallucination_warning_count = sum(1 for chat in chats if has_hallucination_warning(chat))
    source_conflict_count = sum(1 for chat in chats if has_source_conflict(chat))
    answer_quality_distribution = build_answer_quality_distribution(chats)
    answer_quality_reason_distribution = build_answer_quality_reason_distribution(chats)
    answer_quality_actions = answer_quality_reason_actions(
        answer_quality_reason_distribution["counts"]
    )
    primary_warning_distribution = build_primary_warning_distribution(chats)
    uncertainty_distribution = build_uncertainty_distribution(chats)
    uncertainty_counts = uncertainty_distribution["counts"]
    high_uncertainty_count = uncertainty_counts.get("high", 0)
    uncertain_answer_count = high_uncertainty_count + uncertainty_counts.get("medium", 0)
    error_count = sum(1 for event in events if is_error_event(event))
    source_distribution = build_source_distribution(events)
    source_kind_distribution = build_source_kind_distribution(events)
    feedback_summary = build_feedback_summary(feedback_entries)
    source_counts = [int(event.source_count or 0) for event in events]
    chat_source_counts = [int(chat.source_count or 0) for chat in chats]
    structured_answer_count = sum(1 for chat in chats if is_structured_answer(chat))
    rag_answer_count = sum(1 for chat in chats if is_rag_answer(chat))
    no_source_count = sum(1 for value in chat_source_counts if value == 0)
    no_source_breakdown = build_no_source_breakdown(chats)
    low_confidence_count = sum(1 for chat in chats if is_low_confidence_chat(chat))
    fallback_count = sum(1 for event in events if event.fallback_used)
    token_usage = _token_usage(events)
    cost_windows = _cost_windows(events)
    latency = _latency_metrics(response_times, retrieval_times)
    answered_source_counts = [
        int(chat.source_count or 0) for chat in chats if is_answered_chat(chat)
    ]
    structured_module_distribution = build_structured_module_distribution(chats)
    reranking_metrics = build_reranking_metrics(events)
    retrieval_slo = _retrieval_slo_summary(telemetry)
    source_rows = build_source_rows(events)
    source_freshness = source_freshness_summary(source_rows)
    evaluation_gate_metrics = _evaluation_gate_metrics(telemetry)
    source_metadata_metrics = _source_metadata_metrics(telemetry)
    action_summaries = build_action_summaries(
        source_rows,
        feedback_entries,
        telemetry,
    )
    top_documents = document_usage_rows(
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
        "request_success_rate": rate(max(event_count - error_count, 0), event_count),
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
        "failure_reason_distribution": failure_reason_distribution(events),
        "error_rate": rate(error_count, event_count),
        "empty_retrieval_count": empty_retrieval_count,
        "empty_retrieval_rate": rate(empty_retrieval_count, len(chats)),
        "no_answer_count": no_answer_count,
        "no_answer_rate": rate(no_answer_count, len(chats)),
        "source_conflict_count": source_conflict_count,
        "source_conflict_rate": rate(source_conflict_count, len(chats)),
        "answer_quality_distribution": answer_quality_distribution["counts"],
        "answer_quality_distribution_rows": answer_quality_distribution["rows"],
        "answer_quality_reason_distribution": answer_quality_reason_distribution["counts"],
        "answer_quality_reason_distribution_rows": answer_quality_reason_distribution["rows"],
        "answer_quality_actions": answer_quality_actions,
        "answer_quality_action_count": len(answer_quality_actions),
        "answer_quality_action_summary": action_summary(answer_quality_actions),
        "primary_warning_distribution": primary_warning_distribution["counts"],
        "primary_warning_distribution_rows": primary_warning_distribution["rows"],
        "uncertainty_distribution": uncertainty_distribution["counts"],
        "uncertainty_distribution_rows": uncertainty_distribution["rows"],
        "high_uncertainty_count": high_uncertainty_count,
        "high_uncertainty_rate": rate(high_uncertainty_count, len(chats)),
        "uncertain_answer_count": uncertain_answer_count,
        "uncertain_answer_rate": rate(uncertain_answer_count, len(chats)),
        "low_confidence_answers": low_confidence_count,
        "low_confidence_answer_count": low_confidence_count,
        "low_confidence_rate": rate(low_confidence_count, len(chats)),
        "retrieval_hit_rate": rate(
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
        "average_final_top_k": average(source_counts),
        "average_source_count": average(source_counts),
        "source_count_average": average(chat_source_counts),
        "average_answer_source_count": average(chat_source_counts),
        "source_count_average_answered": average(answered_source_counts),
        "structured_answer_count": structured_answer_count,
        "structured_answer_rate": rate(structured_answer_count, len(chats)),
        "rag_answer_count": rag_answer_count,
        "rag_answer_rate": rate(rag_answer_count, len(chats)),
        "no_source_count": no_source_count,
        "no_source_rate": rate(no_source_count, len(chats)),
        "no_source_answers": no_source_count,
        "no_source_answer_rate": rate(no_source_count, len(chats)),
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
        "fallback_rate": rate(fallback_count, event_count),
        "positive_feedback_count": feedback_summary["positive"],
        "negative_feedback_count": feedback_summary["negative"],
        "feedback": feedback_summary,
        "top_questions": top_questions(chats),
        "frequent_questions": top_questions(chats),
        "frequent_search_terms": frequent_search_terms(chats),
        "most_used_documents": top_documents,
        "knowledge_gaps": knowledge_gap_metrics(chats),
        "source_distribution": source_distribution,
        "source_distribution_rows": counter_rows(source_distribution),
        "source_kind_distribution": source_kind_distribution,
        "source_kind_distribution_rows": counter_rows(source_kind_distribution),
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


def _evaluation_gate_metrics(telemetry):
    """Return compact top-level metrics for the latest retrieval quality gate."""
    evaluation = (telemetry or {}).get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    quality_gate = latest_eval.get("quality_gate") or empty_evaluation_quality_gate()
    blocking_rows = quality_gate_blocking_rows(quality_gate.get("blocking") or [])
    warning_rows = quality_gate_warning_rows(quality_gate.get("warnings") or [])
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
    gaps = build_source_metadata_gaps(latest_eval)
    coverage_rates = [
        bounded_rate(latest_eval.get(metric))
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


def _quality_metrics(events, telemetry):
    """Return retrieval quality metrics aligned with golden evaluation when available."""
    total_events = len(events)
    hit_count = sum(1 for event in events if int(event.source_count or 0) > 0)
    similarity_values = build_similarity_values(events)
    evaluation = telemetry.get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    source_metadata_gaps = build_source_metadata_gaps(latest_eval)
    evaluation_quality_gate = latest_eval.get("quality_gate") or empty_evaluation_quality_gate()
    evaluation_blocking = quality_gate_blocking_rows(
        (evaluation_quality_gate or {}).get("blocking") or []
    )
    evaluation_warnings = quality_gate_warning_rows(
        (evaluation_quality_gate or {}).get("warnings") or []
    )
    evaluation_actions = evaluation_quality_actions(
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
        "evaluation_action_summary": action_summary(evaluation_actions),
        "retrieval_hit_rate": rate(hit_count, total_events),
        "empty_retrieval_rate": rate(total_events - hit_count, total_events),
        "average_similarity_score": average(similarity_values),
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
            "value": optional_float(warning.get("value")),
            "status": str(warning.get("status") or "ok")[:40],
            "threshold": optional_float(warning.get("threshold")),
        }
        for warning in (slo.get("warnings") or [])[:10]
        if isinstance(warning, dict)
    ]
    return {
        "status": str(slo.get("status") or "ok")[:40],
        "source_metadata_missing_rate": optional_float(
            last_values.get("source_metadata_missing_rate")
        ),
        "source_metadata_missing_fields": _slo_missing_fields(
            last_values.get("source_metadata_missing_fields")
        ),
        "no_source_rate": optional_float(last_values.get("no_source_rate")),
        "fallback_rate": optional_float(last_values.get("fallback_rate")),
        "atlas_queries": optional_int(last_values.get("atlas_queries")) or 0,
        "atlas_errors": optional_int(last_values.get("atlas_errors")) or 0,
        "atlas_latency": optional_float(last_values.get("atlas_latency")) or 0,
        "atlas_fallbacks": optional_int(last_values.get("atlas_fallbacks")) or 0,
        "atlas_sync_failures": optional_int(last_values.get("atlas_sync_failures")) or 0,
        "atlas_vector_count": optional_int(last_values.get("atlas_vector_count")) or 0,
        "atlas_reindex_required": bool(last_values.get("atlas_reindex_required")),
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def _slo_missing_fields(value):
    """Return prompt-safe missing source metadata field counts for SLO summaries."""
    return [
        {
            "field": str(item.get("field") or "")[:80],
            "count": optional_int(item.get("count")) or 0,
        }
        for item in (value or [])[:20]
        if isinstance(item, dict) and item.get("field")
    ]


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
                if is_at_or_after(event.created_at, since)
            ),
            6,
        )
        for name, since in windows.items()
    }


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
        "average_tokens": average([event.total_tokens for event in events]),
        "cache_rate": rate(cached_tokens, input_tokens),
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
        "average_response_ms": average(response_times),
        "p95_response_ms": percentile(response_times, 0.95),
        "average_retrieval_ms": average(retrieval_times),
        "p95_retrieval_ms": percentile(retrieval_times, 0.95),
    }
