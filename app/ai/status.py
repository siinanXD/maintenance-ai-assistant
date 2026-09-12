"""AI orchestration services for permission-aware workflows."""
# ruff: noqa: F401, F821

import inspect
import logging

from flask import current_app

from app.services.ai_answer_quality_service import answer_quality_from_result
from app.services.ai_audit_service import ai_analytics_summary, create_ai_audit_event
from app.services.ai_confidence_service import attach_confidence_to_result
from app.services.ai_provider_readiness_service import ai_provider_readiness_snapshot
from app.services.ai_routing import local_metadata, workflow_profile
from app.services.ai_safety_service import (
    apply_post_generation_safety_to_result,
    apply_safety_payload_warning,
    apply_safety_warning,
    assess_ai_safety,
    enforce_post_generation_safety,
    reapply_post_generation_penalty,
)
from app.services.ai_service import (
    AIServiceError,
    ai_provider_catalog,
    ai_provider_fallback_reason,
    get_ai_provider,
    provider_fallback_error_message,
)
from app.services.conversation_context_service import (
    build_structured_context_metadata,
)
from app.services.embedding_service import embedding_provider_catalog
from app.services.empty_retrieval_response_service import build_empty_retrieval_answer
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

DASHBOARD_SCOPE_LABELS = {
    "tasks": "Tasks",
    "errors": "Fehlerkatalog",
    "employees": "Mitarbeiter",
    "machines": "Maschinen",
    "inventory": "Lager",
    "documents": "Dokumente",
    "shiftplans": "Schichtplanung",
    "admin_users": "Admin Users",
}

SCOPE_KEYWORDS = {
    "tasks": ["task", "tasks", "aufgabe", "aufgaben", "todo"],
    "errors": [
        "fehler",
        "stoerung",
        "störung",
        "error",
        "fehlercode",
        "ursache",
    ],
    "employees": [
        "mitarbeiter",
        "personal",
        "personaldaten",
        "gehalt",
        "gehaltsklasse",
        "adresse",
        "geburtsdatum",
        "qualifikation",
    ],
    "machines": ["maschine", "maschinen", "anlage", "anlagen", "machine"],
    "inventory": ["lager", "bestand", "material", "ersatzteil", "inventory"],
    "documents": ["dokument", "dokumente", "bericht", "berichte", "report"],
    "shiftplans": ["schichtplan", "schichtplanung", "dienstplan", "schicht"],
    "admin_users": ["user", "users", "nutzer", "benutzer", "accounts"],
}

COUNT_WORDS = [
    "wie viele",
    "wie vile",
    "wieviele",
    "wievile",
    "anzahl",
    "count",
    "many",
]

GENERAL_KNOWLEDGE_PREFIXES = (
    "was ist",
    "was bedeutet",
    "wie funktioniert",
    "warum",
    "wer ist",
    "erklaere",
    "erkläre",
    "what is",
    "how does",
    "why",
)

APP_DATA_INTENT_PHRASES = (
    "bei uns",
    "im system",
    "in der app",
    "in unserer datenbank",
    "meine",
    "mein",
    "unsere",
    "unser",
    "sichtbar",
    "vorhanden",
    "angelegt",
    "offen",
    "heute",
    "morgen",
    "anstehend",
    "zeige",
    "liste",
    "auflisten",
    "anzeigen",
    "gibt es",
    "erstellen",
    "anlegen",
    "loeschen",
    "löschen",
    "aendern",
    "ändern",
)


def answer_mode_for_message(message, response_type="", diagnostics=None):
    """Return the product-facing answer mode used by chat UX and diagnostics."""
    diagnostics = diagnostics or {}
    query_understanding = diagnostics.get("query_understanding") or {}
    query_type = query_understanding.get("query_type")
    text = str(message or "").lower()
    if response_type == "tasks_today" or "task" in response_type:
        return "task_help"
    if response_type == "order_plan":
        return "task_prioritization"
    if response_type == "general_chat":
        return "summary"
    if query_type == "document_question" or any(
        word in text for word in ("dokument", "handbuch", "anleitung", "pdf")
    ):
        return "document_search"
    if query_type == "trend_history_question" or any(
        word in text for word in ("aehnlich", "ähnlich", "wiederkehrend", "historie")
    ):
        return "similar_errors"
    if response_type == "error_help" or looks_like_error_question(message):
        return "error_analysis"
    if query_type == "machine_question" or any(
        word in text for word in ("maschine", "anlage", "presse")
    ):
        return "machine_knowledge"
    return "maintenance_assistant"


def retrieval_has_evidence(retrieval):
    """Return whether a RAG retrieval payload contains usable answer evidence."""
    return bool(retrieval.get("sources"))


def should_generate_without_evidence():
    """Return whether a configured provider should still receive unsourced prompts.

    The policy is explicit: ``AI_GENERATE_WITHOUT_EVIDENCE`` must be enabled and
    a non-mock provider must be configured. Otherwise empty retrieval stays a
    local, grounded no-answer and no LLM call is made.
    """
    if not _config_flag("AI_GENERATE_WITHOUT_EVIDENCE", False):
        return False
    provider = get_ai_provider()
    configured_provider = current_app.config.get("AI_PROVIDER", "openai").lower()
    return provider.name != "mock" or configured_provider != "mock"


def _config_flag(key, default=False):
    """Return a boolean config flag that tolerates string values."""
    value = current_app.config.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def empty_retrieval_diagnostics():
    """Return diagnostics for a grounded no-answer that skipped generation.

    Provider misconfiguration stays visible (for example ``api_key_missing``)
    so admins can distinguish a deliberate evidence gate from a broken setup.
    """
    configured_provider = str(current_app.config.get("AI_PROVIDER", "openai") or "").lower()
    reason = ""
    if configured_provider != "mock":
        reason = ai_provider_fallback_reason(current_app.config)
    if reason:
        diagnostics = ai_diagnostics(
            reason,
            fallback_used=True,
            error=provider_fallback_error_message(reason),
            metadata=local_metadata("local", "chat"),
        )
    else:
        diagnostics = ai_diagnostics("local_answer", fallback_used=True)
    diagnostics["generation_skipped"] = "no_evidence"
    return diagnostics


def grounded_empty_retrieval_answer(message, retrieval=None, user=None):
    """Return a non-hallucinating fallback when no relevant source was retrieved."""
    return build_empty_retrieval_answer(message, retrieval=retrieval, user=user)


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
                    "Keine Quellen gefunden; Antwort nur als vorsichtige " "Orientierung nutzen."
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
        and result.get("type") in {"assistant", "error_help"}
        and looks_like_error_question(message)
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


def answer_quality_payload(result, diagnostics, warnings):
    """Return a compact UI-facing answer quality summary."""
    return answer_quality_from_result(result, diagnostics, warnings)


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
    response_type = str(result.get("type") or "")
    if response_type == "general_chat":
        return ANSWER_CATEGORY_GENERAL
    if result.get("rag") is not None or response_type in {"assistant", "error_help"}:
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
    conversation_context=None,
):
    """Attach source diagnostics and metadata-only audit id to a chat result."""
    diagnostics = result.setdefault("diagnostics", ai_diagnostics("local_answer"))
    rag = result.get("rag") or {}
    if conversation_context is not None:
        diagnostics["conversation_context"] = conversation_context.diagnostics()
        diagnostics["session_id"] = conversation_context.session_id
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
        workflow or result.get("type", "assistant"),
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
    """Return redacted OpenAI configuration status for admins."""
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


def redacted_openai_error(error):
    """Return a user-safe error category for OpenAI failures."""
    if isinstance(error, AIServiceError):
        return error.error_code
    name = error.__class__.__name__
    return name if name.endswith("Error") else "OpenAIError"


def _call_answer_question(provider, message, context, extra_rules=None):
    """Call ``answer_question`` and pass extra rules only when the provider accepts them."""
    if not extra_rules:
        return provider.answer_question(message, context)
    try:
        parameters = inspect.signature(provider.answer_question).parameters
    except (TypeError, ValueError):
        return provider.answer_question(message, context)
    accepts_rules = "extra_rules" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    if accepts_rules:
        return provider.answer_question(message, context, extra_rules=extra_rules)
    return provider.answer_question(message, context)


def openai_assistant_answer(message, context, extra_rules=None):
    """Generate an AI answer using OpenAI and permission-aware context."""
    global LAST_OPENAI_ERROR
    provider = get_ai_provider()

    configured_provider = current_app.config.get("AI_PROVIDER", "openai").lower()
    if provider.name == "mock" and configured_provider != "mock":
        fallback_reason = ai_provider_fallback_reason(current_app.config)
        LAST_OPENAI_ERROR = fallback_reason or "provider_unavailable"
        logger.warning("ai_fallback workflow=chat reason=%s", LAST_OPENAI_ERROR)
        return None, ai_diagnostics(
            LAST_OPENAI_ERROR,
            fallback_used=True,
            error=provider_fallback_error_message(LAST_OPENAI_ERROR),
            metadata=local_metadata("local", "chat"),
        )

    try:
        answer = _call_answer_question(provider, message, context, extra_rules)
    except AIServiceError as exc:
        LAST_OPENAI_ERROR = redacted_openai_error(exc)
        logger.exception("ai_call_failed workflow=chat provider=%s", provider.name)
        return None, ai_diagnostics(
            "openai_error",
            fallback_used=True,
            error=LAST_OPENAI_ERROR,
            provider=provider.name,
            metadata=getattr(provider, "last_call_metadata", {}),
        )

    LAST_OPENAI_ERROR = None
    metadata = getattr(provider, "last_call_metadata", {})
    if provider.name == "mock":
        return answer, ai_diagnostics(
            "local_answer",
            provider=provider.name,
            metadata=metadata,
        )
    return answer, ai_diagnostics(
        "openai_used",
        provider=provider.name,
        metadata=metadata,
    )


def general_tracking_notice():
    """Return the required tracking notice for hybrid-mode answers."""
    return (
        "\n\n- **Hinweis:** Allgemeine AI-Fragen werden in der Chat-Historie "
        "und als AI-Nutzungsmetadaten protokolliert."
    )


def with_general_tracking_notice(answer):
    """Return an answer with exactly one general-chat tracking notice."""
    text = str(answer or "").strip()
    notice = general_tracking_notice().strip()
    if notice in text:
        return text
    return f"{text}\n\n{notice}" if text else notice


def local_general_chat_answer(reason):
    """Return a concise local fallback for general questions."""
    if reason == "api_key_missing":
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** OpenAI ist nicht konfiguriert\n"
            "- **Naechster Schritt:** OPENAI_API_KEY in der .env setzen und Server neu starten"
        )
    if reason == "base_url_missing":
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** OpenAI-kompatibler Provider ist nicht vollstaendig konfiguriert\n"
            "- **Naechster Schritt:** AI_BASE_URL fuer den lokalen Endpoint setzen"
        )
    if reason == "unsupported_provider":
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** Der konfigurierte AI-Provider hat noch keinen Adapter\n"
            "- **Naechster Schritt:** AI_PROVIDER auf openai, openai_compatible oder mock setzen"
        )
    if reason in {"model_not_found", "model_not_allowed"}:
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** Das konfigurierte OpenAI-Modell ist nicht freigeschaltet\n"
            "- **Naechster Schritt:** OPENAI_MODEL auf ein verfuegbares Modell setzen"
        )
    if reason == "rate_limit":
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** OpenAI-Rate-Limit erreicht\n"
            "- **Naechster Schritt:** Kurz warten oder ein Modell mit hoeherem Limit nutzen"
        )
    if reason == "authentication_error":
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** OpenAI-Key wurde abgelehnt\n"
            "- **Naechster Schritt:** OPENAI_API_KEY pruefen oder neu erstellen"
        )
    if reason in {"connection_error", "timeout"}:
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** Verbindung zu OpenAI nicht erfolgreich\n"
            "- **Naechster Schritt:** Netzwerk, Firewall und Timeout-Konfiguration pruefen"
        )
    return (
        "## Allgemeine Antwort\n"
        "- **Status:** OpenAI ist gerade nicht erreichbar\n"
        "- **Naechster Schritt:** API-Key, Modellname, Netzwerk und OpenAI-Status pruefen"
    )


def openai_general_answer(message, context=""):
    """Generate a short general AI answer for hybrid mode."""
    global LAST_OPENAI_ERROR
    provider = get_ai_provider()
    configured_provider = current_app.config.get("AI_PROVIDER", "openai").lower()
    if provider.name == "mock" and configured_provider != "mock":
        fallback_reason = ai_provider_fallback_reason(current_app.config)
        LAST_OPENAI_ERROR = fallback_reason or "provider_unavailable"
        answer = local_general_chat_answer(LAST_OPENAI_ERROR)
        return with_general_tracking_notice(answer), ai_diagnostics(
            LAST_OPENAI_ERROR,
            fallback_used=True,
            error=provider_fallback_error_message(LAST_OPENAI_ERROR),
            metadata=local_metadata("local", "general_chat"),
        )

    try:
        if context:
            answer = provider.answer_question(message, context, workflow="general_chat")
        else:
            answer = provider.answer_general_question(message)
    except AIServiceError as exc:
        LAST_OPENAI_ERROR = redacted_openai_error(exc)
        logger.exception(
            "ai_call_failed workflow=general_chat provider=%s",
            provider.name,
        )
        fallback = local_general_chat_answer(LAST_OPENAI_ERROR)
        return with_general_tracking_notice(fallback), ai_diagnostics(
            "openai_error",
            fallback_used=True,
            error=LAST_OPENAI_ERROR,
            provider=provider.name,
            metadata=getattr(provider, "last_call_metadata", {}),
        )

    LAST_OPENAI_ERROR = None
    metadata = getattr(provider, "last_call_metadata", {})
    status = "local_answer" if provider.name == "mock" else "openai_used"
    return with_general_tracking_notice(answer), ai_diagnostics(
        status,
        provider=provider.name,
        metadata=metadata,
    )


def fallback_general_answer(context_data, blocked_scopes=None):
    """Return a local read-only answer from allowed context counts."""
    blocked_scopes = blocked_scopes or []
    counts = {
        "Fehler": len(context_data.get("errors", [])),
        "Mitarbeiter": len(context_data.get("employees", [])),
        "Maschinen": len(context_data.get("machines", [])),
        "Lagerpositionen": len(context_data.get("inventory", [])),
        "Dokumente": len(context_data.get("documents", [])),
        "Schichtplaene": len(context_data.get("shiftplans", [])),
    }
    visible = [f"{label}: {count}" for label, count in counts.items() if count]
    lines = [
        "## Ergebnis",
        "- **Status:** Freigegebene Daten geprueft",
    ]
    if visible:
        lines.append(f"- **Sichtbarer Kontext:** {', '.join(visible[:4])}")
    else:
        lines.append("- **Sichtbarer Kontext:** Keine passenden Daten gefunden")
    if blocked_scopes:
        labels = [DASHBOARD_SCOPE_LABELS[scope] for scope in blocked_scopes]
        blocked_labels = ", ".join(labels)
        lines.append(f"- **Eingeschraenkt:** Keine Berechtigung fuer {blocked_labels}")
        lines.append("- **Naechster Schritt:** Berechtigung beim Admin anfragen")
    else:
        lines.append("- **Naechster Schritt:** Frage bei Bedarf konkreter stellen")
    return "\n".join(lines)


__all__ = [
    "ANSWER_CATEGORY_GENERAL",
    "ANSWER_CATEGORY_RAG",
    "ANSWER_CATEGORY_STRUCTURED",
    "MODEL_KNOWLEDGE_LABEL",
    "answer_mode_for_message",
    "retrieval_has_evidence",
    "should_generate_without_evidence",
    "empty_retrieval_diagnostics",
    "grounded_empty_retrieval_answer",
    "chat_quality_warnings",
    "finalize_chat_result_quality",
    "ai_diagnostics",
    "attach_audit_metadata",
    "redacted_status_error",
    "ai_status",
    "redacted_openai_error",
    "openai_assistant_answer",
    "general_tracking_notice",
    "with_general_tracking_notice",
    "local_general_chat_answer",
    "openai_general_answer",
    "fallback_general_answer",
]
