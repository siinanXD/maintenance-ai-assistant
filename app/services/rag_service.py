"""Compatibility facade for LangGraph-ready RAG orchestration."""

from app.services.langgraph_rag_workflow import (
    build_langgraph_rag_context,
    run_langgraph_rag_workflow,
)


def build_rag_context(message, user, requested_scopes=None, conversation_context=None):
    """Return retrieved context, sources, and RAG diagnostics for a question."""
    return build_langgraph_rag_context(
        message,
        user,
        requested_scopes=requested_scopes,
        conversation_context=conversation_context,
    )


def answer_with_rag(
    message,
    user,
    requested_scopes=None,
    provider=None,
    conversation_context=None,
    answer_generator=None,
):
    """Generate an answer with retrieved context and source metadata.

    ``answer_generator`` optionally replaces the direct provider call with a
    callable ``(message, retrieval, extra_rules) -> (answer, diagnostics)`` so
    callers can keep provider fallback, evidence gates and diagnostics while
    the LangGraph workflow owns the node sequence.
    """
    return run_langgraph_rag_workflow(
        message,
        user,
        requested_scopes=requested_scopes,
        provider=provider,
        conversation_context=conversation_context,
        answer_generator=answer_generator,
    )
