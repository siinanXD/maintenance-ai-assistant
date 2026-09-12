"""Answer diagnostics, audit metadata and provider status for agent chats."""

import logging

from flask import current_app

from app.services.ai_answer_quality_service import answer_quality_from_result
from app.services.ai_audit_service import ai_analytics_summary, create_ai_audit_event
from app.services.ai_confidence_service import attach_confidence_to_result
from app.services.ai_provider_readiness_service import ai_provider_readiness_snapshot
from app.services.ai_question_normalizer import mentions_error_question
from app.services.ai_routing import local_metadata, workflow_profile
from app.services.ai_safety_service import (
    apply_post_generation_safety_to_result,
    apply_safety_payload_warning,
    apply_safety_warning,
    assess_ai_safety,
    enforce_post_generation_safety,
    reapply_post_generation_penalty,
)
from app.services.ai_service import ai_provider_catalog
from app.services.conversation_context_service import build_structured_context_metadata
from app.services.embedding_service import embedding_provider_catalog
from app.services.langfuse_service import langfuse_status
from app.services.query_understanding_service import classify_query
from app.services.retrieval_debug_service import (
    is_retrieval_debug_visible,
    public_retrieval_debug,
)
from app.services.retrieval_explainability_service import retrieval_explainability_summary

LAST_OPENAI_ERROR = None
OPENAI_PROVIDER = "OpenAI"
logger = logging.getLogger(__name__)

ANSWER_CATEGORY_STRUCTURED = "structured_data"
ANSWER_CATEGORY_RAG = "rag"
ANSWER_CATEGORY_GENERAL = "general_ai_knowledge"
MODEL_KNOWLEDGE_LABEL = "Modellwissen"


def answer_mode_for_message(message, response_type="", diagnostics=None):
    """Return the product-facing answer mode used by chat UX and diagnostics."""
    diagnostics = diagnostics or {}
    query_understanding = diagnostics.get("query_understanding") or {}
    query_type = query_understanding.get("query_type")
    text = str(message or "").lower()
    if response_type == "agent_action":
        return "task_help"
    if query_type == "document_question" or any(
        word in text for word in ("dokument", "handbuch", "anleitung", "pdf")
    ):
        return "document_search"
    if query_type == "trend_history_question" or any(
        word in text for word in ("aehnlich", "ähnlich", "wiederkehrend", "historie")
    ):
        return "similar_errors"
    if mentions_error_question(message):
        return "error_analysis"
    if query_type == "machine_question" or any(
        word in text for word in ("maschine", "anlage", "presse")
    ):
        return "machine_knowledge"
    return "maintenance_assistant"


def chat_quality_warnings(result, message=""):
    """Return visible quality warnings for the chat answer without storing prompt text."""
    diagnostics = result.get("diagnostics") or {}
    sources = result.get("sources") or []
    answer_category = diagnostics.get("answer_category") or result.get("answer_category")
    confidence = result.get("confidence") or diagnostics.get("confidence") or {}
    warnings = []
    if not sources and answer_category != ANSWER_CATEGORY_GENERAL:
        warnings.append(
            {
                "type": "empty_retrieval",
                "severity": "warning",
                "message": (
                    "Keine Quellen gefunden; Antwort nur als vorsichtige Orientierung nutzen."
                ),
            }
        )
    if confidence.get("level") == "low":
        warnings.append(
            {
                "type": "low_confidence",
                "severity": "warning",
                "message": "Niedrige Confidence; Quellenlage oder Maschinenbezug ist schwach.",
            }
        )
    if (
        not sources
        and answer_category in {ANSWER_CATEGORY_RAG, ANSWER_CATEGORY_GENERAL}
        and mentions_error_question(message)
    ):
        warnings.append(
            {
                "type": "hallucination_risk",
                "severity": "risk",
                "message": "Halluzinationsrisiko: Fehleranalyse ohne belegte Quelle blockiert.",
            }
        )
    if any(source.get("quality_status") == "outdated" for source in sources):
        warnings.append(
            {
                "type": "stale_source",
                "severity": "warning",
                "message": "Mindestens eine Quelle ist als veraltet markiert.",
            }
        )
    source_conflicts = diagnostics.get("source_conflicts") or {}
    if source_conflicts.get("has_conflicts"):
        warnings.append(
            {
                "type": "source_conflict",
                "severity": "warning",
                "message": (
                    "Quellenlage ist widerspruechlich; Antwort fachlich pruefen "
                    "und Konflikt klaeren."
                ),
            }
        )
    return warnings


def finalize_chat_result_quality(result, message):
    """Attach answer mode and quality-control diagnostics to a chat result."""
    diagnostics = result.setdefault("diagnostics", ai_diagnostics("local_answer"))
    diagnostics["answer_mode"] = answer_mode_for_message(
        message,
        result.get("type", ""),
        diagnostics,
    )
    warnings = chat_quality_warnings(result, message)
    diagnostics["quality_warnings"] = warnings
    diagnostics["empty_retrieval"] = any(
        warning["type"] == "empty_retrieval" for warning in warnings
    )
    diagnostics["hallucination_warning"] = any(
        warning["type"] == "hallucination_risk" for warning in warnings
    )
    result["answer_quality"] = answer_quality_from_result(result, diagnostics, warnings)
    return result


def ai_diagnostics(
    status,
    fallback_used=False,
    error=None,
    provider=None,
    metadata=None,
):
    """Build a safe diagnostic payload without exposing secrets."""
    metadata = metadata or {}
    if not metadata and status in {"local_answer", "permission_denied"}:
        metadata = local_metadata("local", status)
    default_profile = workflow_profile("chat")
    payload = {
        "status": status,
        "fallback_used": fallback_used,
        "provider": provider or metadata.get("provider") or OPENAI_PROVIDER,
        "model": metadata.get("model") or default_profile.model,
    }
    for key in (
        "langfuse_enabled",
        "langfuse_trace_id",
        "langfuse_observation_id",
        "langfuse_host",
    ):
        if key in metadata:
            payload[key] = metadata[key]
    for key in (
        "workflow",
        "model_tier",
        "temperature",
        "max_tokens",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "total_tokens",
        "estimated_cost_usd",
    ):
        if key in metadata:
            payload[key] = metadata[key]
    if error:
        payload["error"] = error
    return payload


def _answer_category_for_result(result):
    """Return the high-level answer category for traceability and UI display."""
    diagnostics = result.get("diagnostics") or {}
    explicit = result.get("answer_category") or diagnostics.get("answer_category")
    if explicit:
        return str(explicit)
    if result.get("rag") is not None:
        return ANSWER_CATEGORY_RAG
    return ANSWER_CATEGORY_STRUCTURED


def _retrieval_used_for_result(result, answer_category, sources):
    """Return whether vector/RAG retrieval contributed visible answer sources."""
    diagnostics = result.get("diagnostics") or {}
    explicit = result.get("retrieval_used")
    if explicit is None:
        explicit = diagnostics.get("retrieval_used")
    if explicit is not None:
        return bool(explicit)
    if answer_category != ANSWER_CATEGORY_RAG:
        return False
    return bool(sources)


def attach_audit_metadata(
    user,
    result,
    requested_scopes=None,
    allowed_scopes=None,
    workflow=None,
    message="",
):
    """Attach source diagnostics and metadata-only audit id to a chat result."""
    diagnostics = result.setdefault("diagnostics", ai_diagnostics("local_answer"))
    rag = result.get("rag") or {}
    query_understanding = rag.get("query_understanding")
    if not query_understanding:
        query_understanding = classify_query(message, requested_scopes).to_dict()
    diagnostics["query_understanding"] = query_understanding
    if rag.get("query_classification"):
        diagnostics["query_classification"] = rag.get("query_classification")
    safety = rag.get("safety")
    if not safety:
        safety_assessment = assess_ai_safety(message)
        safety = safety_assessment.to_dict()
    diagnostics["safety"] = safety
    if rag.get("conflicts"):
        diagnostics["source_conflicts"] = rag["conflicts"]
    if rag.get("context_builder"):
        diagnostics["context_builder"] = rag["context_builder"]
    if rag.get("retrieval_duration_ms") is not None:
        diagnostics["retrieval_duration_ms"] = rag.get("retrieval_duration_ms")
    if rag.get("retrieval_debug") and is_retrieval_debug_visible(user):
        diagnostics["retrieval_debug"] = public_retrieval_debug(rag.get("retrieval_debug"))
    if rag.get("knowledge_links"):
        diagnostics["knowledge_links"] = rag.get("knowledge_links")
    result = attach_confidence_to_result(message, result)
    diagnostics = result.setdefault("diagnostics", ai_diagnostics("local_answer"))
    sources = result.get("sources") or []
    answer_category = _answer_category_for_result(result)
    retrieval_used = _retrieval_used_for_result(result, answer_category, sources)
    source_label = result.get("source_label") or diagnostics.get("source_label")
    if not source_label and answer_category == ANSWER_CATEGORY_GENERAL:
        source_label = MODEL_KNOWLEDGE_LABEL
    result["answer_category"] = answer_category
    result["retrieval_used"] = retrieval_used
    if source_label:
        result["source_label"] = source_label
        diagnostics["source_label"] = source_label
    diagnostics["answer_category"] = answer_category
    diagnostics["retrieval_used"] = retrieval_used
    safety_assessment = assess_ai_safety(message, query_understanding=None, sources=sources)
    if safety.get("safety_relevant"):
        safety_assessment = assess_ai_safety(message, sources=sources)
    result["answer"] = apply_safety_warning(result.get("answer"), safety_assessment)
    result["answer"] = apply_safety_payload_warning(result.get("answer"), safety)
    post_safety = enforce_post_generation_safety(result.get("answer"), safety)
    result = apply_post_generation_safety_to_result(result, post_safety)
    result = reapply_post_generation_penalty(result)
    diagnostics = result.setdefault("diagnostics", ai_diagnostics("local_answer"))
    diagnostics["source_count"] = len(sources)
    diagnostics["scopes"] = sorted(requested_scopes or [])
    structured_context = build_structured_context_metadata(
        message,
        result,
        requested_scopes=requested_scopes,
    )
    if structured_context:
        diagnostics["structured_context"] = structured_context
    diagnostics["retrieval_explainability"] = retrieval_explainability_summary(sources)
    diagnostics["retrieval_explainability"].update(
        {
            "query_understanding": diagnostics.get("query_understanding") or {},
            "query_classification": diagnostics.get("query_classification") or {},
            "safety": diagnostics.get("safety") or {},
            "post_generation_safety": diagnostics.get("post_generation_safety") or {},
            "conflicts": diagnostics.get("source_conflicts") or {},
            "context_builder": diagnostics.get("context_builder") or {},
            "knowledge_links": diagnostics.get("knowledge_links") or {},
            "retrieval_duration_ms": diagnostics.get("retrieval_duration_ms", 0),
        }
    )
    if rag.get("retrieval_debug"):
        diagnostics["retrieval_explainability"]["retrieval_debug"] = public_retrieval_debug(
            rag.get("retrieval_debug"),
        )
    finalize_chat_result_quality(result, message)
    event_id = create_ai_audit_event(
        user,
        workflow or result.get("type", "agent"),
        diagnostics,
        requested_scopes=requested_scopes or [],
        allowed_scopes=allowed_scopes or [],
        source_count=len(sources),
    )
    diagnostics["audit_event_id"] = event_id
    return result


def redacted_status_error(error):
    """Return an admin-safe AI status error label without secret-related wording."""
    if not error:
        return None
    if error == "api_key_missing":
        return "configuration_missing"
    return str(error)


def ai_status():
    """Return redacted provider configuration status for admins."""
    last_error = redacted_status_error(LAST_OPENAI_ERROR)
    provider_readiness = ai_provider_readiness_snapshot(
        current_app.config,
        last_error=last_error,
    )
    return {
        "api_key_configured": provider_readiness["api_key_configured"],
        "model": workflow_profile("chat").model,
        "model_profiles": {
            "fast": workflow_profile("task_suggestion").to_dict(),
            "balanced": workflow_profile("chat").to_dict(),
            "quality": workflow_profile("quality_analysis").to_dict(),
        },
        "provider": provider_readiness["provider"],
        "provider_status": provider_readiness["provider_status"],
        "provider_catalog": ai_provider_catalog(),
        "provider_catalog_selectable": [
            item for item in ai_provider_catalog() if item.get("status") == "supported"
        ],
        "embedding_provider_status": provider_readiness["embedding_provider_status"],
        "embedding_provider_catalog": embedding_provider_catalog(),
        "streaming_configured": bool(current_app.config.get("AI_ENABLE_STREAMING", False)),
        "streaming_available": False,
        "streaming_enabled": False,
        "langfuse": langfuse_status(current_app.config),
        "ready": provider_readiness["ready"],
        "readiness": provider_readiness["readiness"],
        "last_error": last_error,
        "analytics": ai_analytics_summary(7),
    }
