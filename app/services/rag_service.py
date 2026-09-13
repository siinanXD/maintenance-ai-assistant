"""Retrieval pipeline behind the agent's ``search_knowledge`` tool.

The agent owns answer generation, so this module only assembles context:
question -> intent classification -> retrieval (SQL, vector, keyword fallback)
-> context assembly with diagnostics. Each step appends to a trace that is
exposed as ``rag.pipeline_trace``.
"""

from app.services.query_classifier_service import classify_ai_query
from app.services.retrieval_explainability_service import retrieval_explainability_summary
from app.services.retrieval_service import is_rag_enabled, retrieve_context

RAG_PIPELINE_STEPS = [
    "question",
    "intent_classification",
    "retrieval",
    "context_assembly",
]


def build_rag_context(message, user, requested_scopes=None, conversation_context=None):
    """Return retrieved context, sources, and RAG diagnostics for a question."""
    state = {
        "message": message,
        "user": user,
        "requested_scopes": requested_scopes,
        "conversation_context": conversation_context,
        "trace": [],
    }
    for step in (question_step, intent_classification_step, retrieval_step, context_assembly_step):
        state.update(step(state))
    retrieval = state["retrieval"]
    retrieval["rag"]["pipeline_trace"] = {
        "steps": list(RAG_PIPELINE_STEPS),
        "completed_steps": [entry["step"] for entry in state["trace"]],
    }
    return retrieval


def question_step(state):
    """Validate the incoming question and normalize it."""
    message = str(state.get("message") or "").strip()
    if not message:
        raise ValueError("RAG pipeline requires a non-empty message.")
    return {"message": message, "trace": _append_trace(state, "question")}


def intent_classification_step(state):
    """Classify the question before retrieval runs."""
    classification = classify_ai_query(state["message"])
    return {
        "query_classification": classification,
        "trace": _append_trace(
            state,
            "intent_classification",
            {"query_type": getattr(classification, "query_type", "")},
        ),
    }


def retrieval_step(state):
    """Run SQL, vector and keyword retrieval with permission gates."""
    retrieval = retrieve_context(
        state["message"],
        state["user"],
        state.get("requested_scopes"),
        conversation_context=state.get("conversation_context"),
        query_classification=state["query_classification"],
    )
    sources = retrieval.get("sources") or []
    return {
        "retrieval": retrieval,
        "trace": _append_trace(
            state,
            "retrieval",
            {
                "source_count": len(sources),
                "knowledge_source_count": _knowledge_source_count(sources),
                "keyword_fallback_used": bool(
                    (retrieval.get("retrieval_debug") or {}).get("keyword_fallback_used"),
                ),
            },
        ),
    }


def context_assembly_step(state):
    """Attach RAG diagnostics to the retrieval payload."""
    retrieval = dict(state["retrieval"])
    retrieval["rag"] = _rag_diagnostics(
        retrieval,
        state["query_classification"],
        state.get("conversation_context"),
    )
    return {
        "retrieval": retrieval,
        "trace": _append_trace(
            state,
            "context_assembly",
            {"context_length": len(str(retrieval.get("context") or ""))},
        ),
    }


def prompt_rules_for_retrieval(retrieval):
    """Return query-type-specific prompt rules from retrieval strategy metadata."""
    understanding = retrieval.get("query_understanding") or {}
    strategy = understanding.get("retrieval_strategy") or {}
    rules = [str(rule).strip() for rule in strategy.get("prompt_rules") or [] if rule]
    query_type = str(understanding.get("query_type") or "")
    if query_type == "error_analysis":
        rules.append("Trenne dokumentierte Ursache, Pruefung und empfohlene Massnahme klar.")
    elif query_type == "safety_question":
        rules.append("Bei Sicherheitsfragen nur quellenbasierte, vorsichtige Hinweise geben.")
    elif query_type == "document_question":
        rules.append("Nenne Dokument, Abschnitt oder Chunk, wenn diese Hinweise im Kontext stehen.")
    return " ".join(dict.fromkeys(rules))


def _rag_diagnostics(retrieval, query_classification, conversation_context):
    """Return the public RAG diagnostics payload for a retrieval result."""
    sources = retrieval.get("sources") or []
    rag = {
        "enabled": is_rag_enabled(),
        "pipeline": list(RAG_PIPELINE_STEPS),
        "source_count": len(sources),
        "knowledge_source_count": _knowledge_source_count(sources),
        "explainability": retrieval_explainability_summary(sources),
        "query_understanding": retrieval.get("query_understanding") or {},
        "query_classification": query_classification.to_dict(),
        "safety": retrieval.get("safety") or {},
        "conflicts": retrieval.get("conflicts") or {},
        "context_builder": retrieval.get("context_builder") or {},
        "knowledge_links": retrieval.get("knowledge_links") or {},
        "incident_timeline": retrieval.get("timeline_context") or {},
        "retrieval_duration_ms": retrieval.get("retrieval_duration_ms", 0),
        "retrieval_debug": retrieval.get("retrieval_debug") or {},
    }
    if conversation_context is not None:
        rag["conversation_context"] = conversation_context.diagnostics()
    return rag


def _knowledge_source_count(sources):
    """Return how many retrieved sources came from RAG knowledge chunks."""
    return sum(1 for source in sources if source.get("type") == "knowledge")


def _append_trace(state, step, metadata=None):
    """Return trace entries with the current step appended."""
    return [*(state.get("trace") or []), {"step": step, "metadata": metadata or {}}]
