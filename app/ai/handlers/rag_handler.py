"""RAG and general OpenAI chat answer handling."""

from __future__ import annotations

import logging
from typing import Any

from app.ai.context import fallback_error_answer, should_use_general_hybrid_mode
from app.ai.handlers.tracing_handler import finalize_chat_answer
from app.ai.intent import (
    blocked_requested_scopes,
    extract_error_query,
    looks_like_error_question,
)
from app.ai.status import (
    ANSWER_CATEGORY_GENERAL,
    ANSWER_CATEGORY_RAG,
    MODEL_KNOWLEDGE_LABEL,
    ai_diagnostics,
    empty_retrieval_diagnostics,
    fallback_general_answer,
    grounded_empty_retrieval_answer,
    openai_assistant_answer,
    openai_general_answer,
    retrieval_has_evidence,
    should_generate_without_evidence,
)
from app.security import has_dashboard_permission
from app.services.error_service import search_errors
from app.services.langfuse_service import langfuse_trace_context
from app.services.rag_service import answer_with_rag as run_rag_answer_workflow

logger = logging.getLogger(__name__)


def try_general_hybrid_answer(
    message: str,
    user,
    conversation_context,
    requested_scopes,
    allowed_scopes,
) -> dict[str, Any] | None:
    """Return a general-knowledge answer without retrieval when the question allows it."""
    if not should_use_general_hybrid_mode(message, requested_scopes):
        return None
    with langfuse_trace_context(
        "general_chat",
        user=user,
        session_id=conversation_context.session_id,
        metadata={"source_count": 0, "retrieval_used": False},
        tags=["chat", "general"],
    ):
        answer, diagnostics = openai_general_answer(message, "")
    return finalize_chat_answer(
        user,
        {
            "type": "general_chat",
            "answer": answer,
            "diagnostics": diagnostics,
            "data": {},
            "sources": [],
            "answer_category": ANSWER_CATEGORY_GENERAL,
            "retrieval_used": False,
            "source_label": MODEL_KNOWLEDGE_LABEL,
        },
        requested_scopes,
        allowed_scopes,
        workflow="general_chat",
        message=message,
        conversation_context=conversation_context,
    )


def grounded_answer_generator(user, conversation_context):
    """Return the chat answer generator used by the LangGraph answer node.

    The generator keeps the product rules in one place: generate with the
    configured provider only when retrieval produced evidence (or the explicit
    ``AI_GENERATE_WITHOUT_EVIDENCE`` policy allows it), otherwise return a
    grounded local no-answer without calling the provider.
    """

    def generate(message, retrieval, extra_rules):
        """Return ``(answer, diagnostics)`` for one retrieval payload.

        Applied short-term conversation context counts as evidence: the prior
        answer in the session was already grounded, so follow-up questions may
        be answered from it.
        """
        context_applied = bool(getattr(conversation_context, "applied", False))
        if (
            retrieval_has_evidence(retrieval)
            or context_applied
            or should_generate_without_evidence()
        ):
            with langfuse_trace_context(
                "chat",
                user=user,
                session_id=conversation_context.session_id,
                metadata={"source_count": len(retrieval.get("sources") or [])},
                tags=["chat", "rag", *sorted(retrieval.get("requested_scopes") or [])],
            ):
                return openai_assistant_answer(
                    message,
                    retrieval["context"],
                    extra_rules=extra_rules,
                )
        answer = grounded_empty_retrieval_answer(message, retrieval=retrieval, user=user)
        return answer, empty_retrieval_diagnostics()

    return generate


def answer_with_rag(
    message: str,
    user,
    conversation_context,
    requested_scopes,
    allowed_scopes,
    *,
    build_action_preview,
) -> dict[str, Any]:
    """Answer with retrieval-augmented context and optional action previews.

    The full LangGraph workflow runs here: retrieval, context assembly, answer
    generation, validation (confidence and post-generation safety) and trace
    logging. Route-level audit metadata is attached afterwards.
    """
    blocked_scopes = blocked_requested_scopes(user, requested_scopes)
    workflow_result = run_rag_answer_workflow(
        message,
        user,
        requested_scopes=requested_scopes,
        conversation_context=conversation_context,
        answer_generator=grounded_answer_generator(user, conversation_context),
    )
    answer = workflow_result.get("answer")
    diagnostics = workflow_result.get("diagnostics") or {}
    retrieval_data = workflow_result.get("data") or {}
    sources = workflow_result.get("sources") or []

    if not answer:
        logger.warning("ai_fallback workflow=chat type=assistant")
        retrieval_message = conversation_context.retrieval_query(message)
        if looks_like_error_question(message) and has_dashboard_permission(
            user,
            "errors",
            "view",
        ):
            entries = search_errors(extract_error_query(retrieval_message), user)
            answer = fallback_error_answer(entries)
        else:
            answer = fallback_general_answer(retrieval_data, blocked_scopes)
        diagnostics = diagnostics or ai_diagnostics("fallback_used", fallback_used=True)

    retrieval_message = conversation_context.retrieval_query(message)
    response_type = "error_help" if looks_like_error_question(retrieval_message) else "assistant"
    response_data = (
        retrieval_data.get("errors", []) if response_type == "error_help" else retrieval_data
    )
    action_preview = build_action_preview(message, user, sources)
    result: dict[str, Any] = {
        "type": response_type,
        "answer": answer,
        "diagnostics": diagnostics,
        "data": response_data,
        "sources": sources,
        "rag": workflow_result.get("rag", {}),
        "answer_category": ANSWER_CATEGORY_RAG,
        "retrieval_used": bool(sources),
    }
    if isinstance(workflow_result.get("confidence"), dict):
        result["confidence"] = workflow_result["confidence"]
    if action_preview:
        result["action_preview"] = action_preview
    return finalize_chat_answer(
        user,
        result,
        workflow_result.get("requested_scopes") or [],
        workflow_result.get("allowed_scopes") or [],
        message=message,
        conversation_context=conversation_context,
    )
