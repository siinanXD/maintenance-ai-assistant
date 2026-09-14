"""Chat and audit rows for AI observability: logs, answer quality, knowledge gaps."""

from __future__ import annotations

from collections import Counter

from app.models import KnowledgeGap
from app.services.ai_answer_quality_service import answer_quality_from_history_item
from app.services.ai_observability_common import (
    CONFIGURATION_FAILURE_STATUSES,
    DEFAULT_OBSERVABILITY_LIMIT,
    LOW_CONFIDENCE_SCORE_THRESHOLD,
    NEGATIVE_RATINGS,
    STRUCTURED_DOMAIN_LABELS,
    STRUCTURED_ENTITY_DOMAINS,
    average_from_total,
    bounded,
    counter_rows,
    normalized_question,
    optional_int,
    rate,
)
from app.services.ai_observability_sources import retrieval_duration_ms, source_reference
from app.services.knowledge_gap_service import knowledge_gap_detection
from app.services.text_normalization_service import tokenize_text


def build_ai_logs(chats, limit):
    """Return bounded AI request logs for admin diagnosis."""
    return [_ai_log_row(chat) for chat in chats[:limit]]


def build_failed_requests(events, limit):
    """Return prompt-safe failed AI request rows from audit metadata."""
    return [_failed_request_row(event) for event in events if is_error_event(event)][:limit]


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
        "user_question": bounded(chat.message, 300),
        "answer_preview": bounded(chat.response, 420),
        "response_type": chat.response_type,
        "answer_quality": answer_quality,
        "answer_quality_label": _answer_quality_label(chat, quality_warnings),
        "confidence": confidence_payload(chat, answer_quality),
        "source_count": chat.source_count,
        "sources": [source_reference(source) for source in (sources or [])[:8]],
        "error": event.error_category if event else "",
        "status": event.status if event else diagnostics.get("status", ""),
        "response_duration_ms": event.latency_ms if event else 0,
        "retrieval_duration_ms": retrieval_duration_ms(event) if event else 0,
        "quality_warnings": quality_warnings,
        "knowledge_gap_id": optional_int(diagnostics.get("knowledge_gap_id")),
        "knowledge_gap_created": bool(diagnostics.get("knowledge_gap_created")),
        "langfuse": _langfuse_reference(diagnostics),
    }


def top_questions(chats):
    """Return frequent bounded questions grouped by normalized text."""
    grouped = {}
    for chat in chats:
        key = normalized_question(chat.message)
        item = grouped.setdefault(
            key,
            {
                "question": bounded(chat.message, 220),
                "count": 0,
                "latest_at": chat.created_at,
                "confidence_total": 0,
                "confidence_count": 0,
            },
        )
        item["count"] += 1
        if chat.created_at > item["latest_at"]:
            item["latest_at"] = chat.created_at
            item["question"] = bounded(chat.message, 220)
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
                "average_confidence": average_from_total(
                    item["confidence_total"],
                    item["confidence_count"],
                ),
            }
        )
    return sorted(rows, key=lambda row: (row["count"], row["latest_at"]), reverse=True)[:10]


def frequent_search_terms(chats):
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


def build_feedback_summary(feedback_entries):
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
        "positive_rate": rate(positive, total),
        "negative_rate": rate(negative, total),
    }


def knowledge_gap_metrics(chats=None):
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
        "action_priority_distribution": counter_rows(action_priority_counts),
        "action_type_distribution": counter_rows(action_type_counts),
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
        key = normalized_question(chat.message)
        item = grouped.setdefault(
            key,
            {
                "question": bounded(chat.message, 220),
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
            item["question"] = bounded(chat.message, 220)
            item["knowledge_gap_id"] = optional_int(chat.diagnostics().get("knowledge_gap_id"))
    rows = [
        {
            "question": item["question"],
            "count": item["count"],
            "no_answer_count": item["no_answer_count"],
            "latest_at": item["latest_at"].isoformat(),
            "average_confidence": average_from_total(
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


def is_empty_retrieval(chat):
    """Return whether a chat was answered without retrieved sources."""
    diagnostics = chat.diagnostics()
    return bool(diagnostics.get("empty_retrieval")) or int(chat.source_count or 0) == 0


def is_structured_answer(chat):
    """Return whether a chat used the structured database answer path."""
    return _structured_domain(chat) is not None


def is_rag_answer(chat):
    """Return whether a chat looks like a RAG-backed unstructured answer."""
    diagnostics = chat.diagnostics()
    if str(diagnostics.get("answer_category") or "") == "rag":
        return True
    if is_structured_answer(chat) or int(chat.source_count or 0) <= 0:
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


def is_answered_chat(chat):
    """Return whether a chat should count toward answered-source averages."""
    return (
        not _is_permission_denied_chat(chat)
        and not is_no_answer(chat)
        and not _is_no_source_no_data_chat(chat)
    )


def build_no_source_breakdown(chats):
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
    return int(chat.source_count or 0) == 0 and is_structured_answer(chat)


def build_structured_module_distribution(chats):
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
                "rate": rate(count, sum(counter.values())),
            }
            for module, count in counter.most_common()
        ],
    }


def _structured_module_label(module):
    """Return a compact German label for one structured module key."""
    labels = {**STRUCTURED_DOMAIN_LABELS, "unknown": "Unbekannt"}
    return labels.get(str(module or "unknown"), str(module or "unknown"))


def is_no_answer(chat):
    """Return whether a chat ended in explicit no-answer handling."""
    return answer_quality_from_history_item(chat.to_dict()).get("status") == "no_answer"


def build_answer_quality_distribution(chats):
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
            "rate": rate(count, total),
        }
        for status, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def build_primary_warning_distribution(chats):
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
            "rate": rate(count, total),
        }
        for warning_type, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def build_answer_quality_reason_distribution(chats):
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
            "rate": rate(count, total),
        }
        for status_reason, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def answer_quality_reason_actions(reason_counts):
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


def build_uncertainty_distribution(chats):
    """Return answer uncertainty counts and rates for admin dashboards."""
    counter = Counter(
        answer_quality_from_history_item(chat.to_dict()).get("uncertainty") or "unknown"
        for chat in chats
    )
    total = len(chats)
    rows = [
        {"uncertainty": uncertainty, "count": count, "rate": rate(count, total)}
        for uncertainty, count in counter.most_common()
    ]
    return {"counts": dict(counter), "rows": rows}


def has_hallucination_warning(chat):
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
    if has_hallucination_warning(chat):
        return "risk"
    if has_source_conflict(chat):
        return "conflict"
    if chat.confidence_level == "low" or warnings:
        return "warning"
    if chat.confidence_level == "high" and int(chat.source_count or 0) > 0:
        return "good"
    return "ok"


def has_source_conflict(chat):
    """Return whether a chat answer used conflicting source evidence."""
    diagnostics = chat.diagnostics()
    if (diagnostics.get("source_conflicts") or {}).get("has_conflicts"):
        return True
    warnings = diagnostics.get("quality_warnings") or []
    return any(
        isinstance(warning, dict) and warning.get("type") == "source_conflict"
        for warning in warnings
    )


def is_low_confidence_chat(chat):
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
    score = optional_int(
        chat.confidence_score or diagnostics.get("confidence_score") or confidence.get("score"),
    )
    return score is not None and score <= LOW_CONFIDENCE_SCORE_THRESHOLD


def is_error_event(event):
    """Return whether an audit event counts as an AI error."""
    status = str(event.status or "").strip()
    return (
        status in CONFIGURATION_FAILURE_STATUSES
        or bool(event.error_category)
        or "error" in status.lower()
    )


def failure_reason_distribution(events):
    """Return prompt-safe failed request reason counts."""
    counter = Counter(_failure_reason(event) for event in events if is_error_event(event))
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


def confidence_payload(chat, answer_quality=None):
    """Return prompt-safe confidence metadata enriched with answer uncertainty."""
    quality = answer_quality or answer_quality_from_history_item(chat.to_dict())
    return {
        "score": chat.confidence_score,
        "level": chat.confidence_level,
        "uncertainty": quality.get("uncertainty") or "unknown",
    }


def answer_uncertainty(chat):
    """Return the answer uncertainty label for compact request selectors."""
    return confidence_payload(chat)["uncertainty"]


def _langfuse_reference(diagnostics):
    """Return safe Langfuse trace identifiers from diagnostics."""
    return {
        "enabled": bool(diagnostics.get("langfuse_enabled")),
        "trace_id": diagnostics.get("langfuse_trace_id") or "",
        "observation_id": diagnostics.get("langfuse_observation_id") or "",
        "host": diagnostics.get("langfuse_host") or "",
    }
