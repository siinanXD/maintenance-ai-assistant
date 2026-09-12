"""LangGraph-ready orchestration for RAG chat answers."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from app.services.ai_confidence_service import attach_confidence_to_result
from app.services.ai_safety_service import (
    apply_post_generation_safety_to_result,
    enforce_post_generation_safety,
)
from app.services.ai_service import get_ai_provider
from app.services.langfuse_service import langfuse_trace_context
from app.services.query_classifier_service import classify_ai_query
from app.services.retrieval_explainability_service import retrieval_explainability_summary
from app.services.retrieval_service import is_rag_enabled, retrieve_context

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - optional dependency during migration.
    END = None
    StateGraph = None


logger = logging.getLogger(__name__)

LANGGRAPH_RAG_PIPELINE_STEPS = [
    "question",
    "intent_classification",
    "structured_data_retrieval",
    "vector_retrieval",
    "context_assembly",
    "answer_generation",
    "validation",
    "trace_logging",
]


class RagWorkflowState(TypedDict, total=False):
    """Mutable state passed between LangGraph RAG workflow nodes."""

    message: str
    user: Any
    requested_scopes: Any
    provider: Any
    conversation_context: Any
    query_classification: Any
    retrieval: dict[str, Any]
    rag: dict[str, Any]
    answer: str
    diagnostics: Any
    answer_generator: Any
    result: dict[str, Any]
    trace: list[dict[str, Any]]
    workflow_engine: str


def build_langgraph_rag_context(
    message,
    user,
    requested_scopes=None,
    conversation_context=None,
):
    """Return retrieved context and diagnostics using the LangGraph node contract."""
    state = _initial_state(
        message=message,
        user=user,
        requested_scopes=requested_scopes,
        provider=None,
        conversation_context=conversation_context,
        workflow_engine=_workflow_engine_name(),
    )
    for node in (
        question_node,
        intent_classification_node,
        structured_data_retrieval_node,
        vector_retrieval_node,
        context_assembly_node,
        trace_logging_node,
    ):
        state.update(node(state))
    return state["retrieval"]


def run_langgraph_rag_workflow(
    message,
    user,
    requested_scopes=None,
    provider=None,
    conversation_context=None,
    answer_generator=None,
):
    """Generate an answer through LangGraph when available, with fallback runner."""
    state = _initial_state(
        message=message,
        user=user,
        requested_scopes=requested_scopes,
        provider=provider,
        conversation_context=conversation_context,
        workflow_engine=_workflow_engine_name(),
        answer_generator=answer_generator,
    )
    graph = _compiled_langgraph()
    if graph is not None:
        return graph.invoke(state)["result"]
    return _run_fallback_workflow(state)["result"]


def question_node(state):
    """Validate the incoming question and normalize it in workflow state."""
    message = str(state.get("message") or "").strip()
    if not message:
        raise ValueError("RAG workflow requires a non-empty message.")
    return {
        "message": message,
        "trace": _append_trace(state, "question"),
    }


def intent_classification_node(state):
    """Classify the question before retrieval nodes run."""
    classification = classify_ai_query(state["message"])
    return {
        "query_classification": classification,
        "trace": _append_trace(
            state,
            "intent_classification",
            {"query_type": getattr(classification, "query_type", "")},
        ),
    }


def structured_data_retrieval_node(state):
    """Run the existing retrieval pipeline to preserve SQL and permission gates."""
    retrieval = retrieve_context(
        state["message"],
        state["user"],
        state.get("requested_scopes"),
        conversation_context=state.get("conversation_context"),
        query_classification=state["query_classification"],
    )
    return {
        "retrieval": retrieval,
        "trace": _append_trace(
            state,
            "structured_data_retrieval",
            {
                "source_count": len(retrieval.get("sources") or []),
                "requested_scopes": sorted(retrieval.get("requested_scopes") or []),
            },
        ),
    }


def vector_retrieval_node(state):
    """Record vector retrieval diagnostics from the unified retrieval result."""
    retrieval = state["retrieval"]
    knowledge_source_count = _knowledge_source_count(retrieval.get("sources") or [])
    return {
        "trace": _append_trace(
            state,
            "vector_retrieval",
            {
                "knowledge_source_count": knowledge_source_count,
                "fallback_keyword_used": bool(
                    (retrieval.get("retrieval_debug") or {}).get("keyword_fallback_used"),
                ),
            },
        ),
    }


def context_assembly_node(state):
    """Attach RAG diagnostics to the retrieval payload for downstream consumers."""
    retrieval = dict(state["retrieval"])
    rag = _rag_diagnostics(
        retrieval,
        state["query_classification"],
        state.get("conversation_context"),
        state.get("workflow_engine", "fallback"),
    )
    retrieval["rag"] = rag
    return {
        "retrieval": retrieval,
        "rag": rag,
        "trace": _append_trace(
            state,
            "context_assembly",
            {"context_length": len(str(retrieval.get("context") or ""))},
        ),
    }


def answer_generation_node(state):
    """Generate the assistant answer from assembled RAG context.

    When the state carries an ``answer_generator`` callable, it owns provider
    selection, evidence gating and diagnostics. Otherwise the configured
    provider is called directly.
    """
    retrieval = state["retrieval"]
    generator = state.get("answer_generator")
    if generator is not None:
        answer, diagnostics = generator(
            state["message"],
            retrieval,
            prompt_rules_for_retrieval(retrieval),
        )
        return {
            "answer": answer,
            "diagnostics": diagnostics,
            "trace": _append_trace(
                state,
                "answer_generation",
                {
                    "generator": "delegated",
                    "status": str((diagnostics or {}).get("status") or ""),
                    "answered": answer is not None,
                },
            ),
        }
    provider = state.get("provider") or get_ai_provider()
    with langfuse_trace_context(
        "chat",
        user=state["user"],
        session_id=getattr(state.get("conversation_context"), "session_id", ""),
        metadata={"source_count": len(retrieval.get("sources") or [])},
        tags=["rag", "langgraph", *sorted(retrieval.get("requested_scopes") or [])],
    ):
        answer = provider.answer_question(
            state["message"],
            retrieval["context"],
            extra_rules=prompt_rules_for_retrieval(retrieval),
        )
    return {
        "answer": answer,
        "provider": provider,
        "trace": _append_trace(state, "answer_generation"),
    }


def validation_node(state):
    """Attach confidence and post-generation safety validation to the answer."""
    retrieval = state["retrieval"]
    provider = state.get("provider")
    provider_name = getattr(provider, "name", "") if provider is not None else ""
    if not provider_name and state.get("answer_generator") is None:
        provider_name = getattr(get_ai_provider(), "name", "unknown")
    result = {
        "answer": state.get("answer"),
        "sources": retrieval["sources"],
        "data": retrieval["data"],
        "rag": retrieval["rag"],
        "provider": provider_name or "unknown",
        "requested_scopes": retrieval.get("requested_scopes") or [],
        "allowed_scopes": retrieval.get("allowed_scopes") or [],
    }
    diagnostics = state.get("diagnostics")
    if isinstance(diagnostics, dict):
        result["diagnostics"] = diagnostics
    if state.get("answer") is None:
        # Provider failure: leave fallback wording to the caller, keep diagnostics.
        return {
            "result": result,
            "trace": _append_trace(state, "validation", {"skipped": "no_answer"}),
        }
    result = attach_confidence_to_result(state["message"], result)
    post_safety = enforce_post_generation_safety(
        result.get("answer"),
        retrieval["rag"].get("safety"),
    )
    result = apply_post_generation_safety_to_result(result, post_safety)
    return {
        "result": result,
        "trace": _append_trace(
            state,
            "validation",
            {
                "confidence_level": (result.get("confidence") or {}).get("level", ""),
                "post_generation_safety": post_safety.action,
            },
        ),
    }


def trace_logging_node(state):
    """Expose workflow trace metadata without changing route-level audit behavior."""
    trace = _append_trace(state, "trace_logging")
    retrieval = state.get("retrieval")
    result = state.get("result")
    if isinstance(retrieval, dict):
        retrieval.setdefault("rag", {})["langgraph"] = _trace_payload(
            trace,
            state.get("workflow_engine", "fallback"),
        )
    if isinstance(result, dict):
        result.setdefault("rag", {})["langgraph"] = _trace_payload(
            trace,
            state.get("workflow_engine", "fallback"),
        )
    return {
        "retrieval": retrieval,
        "result": result,
        "trace": trace,
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


def _initial_state(
    message,
    user,
    requested_scopes,
    provider,
    conversation_context,
    workflow_engine,
    answer_generator=None,
):
    """Return the initial workflow state."""
    return {
        "message": message,
        "user": user,
        "requested_scopes": requested_scopes,
        "provider": provider,
        "conversation_context": conversation_context,
        "answer_generator": answer_generator,
        "trace": [],
        "workflow_engine": workflow_engine,
    }


def _run_fallback_workflow(state):
    """Run the same node sequence without LangGraph installed."""
    for node in (
        question_node,
        intent_classification_node,
        structured_data_retrieval_node,
        vector_retrieval_node,
        context_assembly_node,
        answer_generation_node,
        validation_node,
        trace_logging_node,
    ):
        state.update(node(state))
    return state


def _compiled_langgraph():
    """Return a compiled LangGraph workflow, or None when fallback should run."""
    if StateGraph is None or END is None:
        return None
    try:
        graph = StateGraph(RagWorkflowState)
        graph.add_node("question", question_node)
        graph.add_node("intent_classification", intent_classification_node)
        graph.add_node("structured_data_retrieval", structured_data_retrieval_node)
        graph.add_node("vector_retrieval", vector_retrieval_node)
        graph.add_node("context_assembly", context_assembly_node)
        graph.add_node("answer_generation", answer_generation_node)
        graph.add_node("validation", validation_node)
        graph.add_node("trace_logging", trace_logging_node)
        graph.set_entry_point("question")
        graph.add_edge("question", "intent_classification")
        graph.add_edge("intent_classification", "structured_data_retrieval")
        graph.add_edge("structured_data_retrieval", "vector_retrieval")
        graph.add_edge("vector_retrieval", "context_assembly")
        graph.add_edge("context_assembly", "answer_generation")
        graph.add_edge("answer_generation", "validation")
        graph.add_edge("validation", "trace_logging")
        graph.add_edge("trace_logging", END)
        return graph.compile()
    except Exception:
        logger.warning("langgraph_compile_failed fallback=deterministic_runner", exc_info=True)
        return None


def _workflow_engine_name():
    """Return the workflow engine name available in this runtime."""
    return "langgraph" if StateGraph is not None and END is not None else "fallback"


def _rag_diagnostics(
    retrieval,
    query_classification,
    conversation_context,
    workflow_engine,
):
    """Return the public RAG diagnostics payload for a retrieval result."""
    rag = {
        "enabled": is_rag_enabled(),
        "pipeline": list(LANGGRAPH_RAG_PIPELINE_STEPS),
        "source_count": len(retrieval.get("sources") or []),
        "knowledge_source_count": _knowledge_source_count(retrieval.get("sources") or []),
        "explainability": retrieval_explainability_summary(retrieval.get("sources") or []),
        "query_understanding": retrieval.get("query_understanding") or {},
        "query_classification": query_classification.to_dict(),
        "safety": retrieval.get("safety") or {},
        "conflicts": retrieval.get("conflicts") or {},
        "context_builder": retrieval.get("context_builder") or {},
        "knowledge_links": retrieval.get("knowledge_links") or {},
        "incident_timeline": retrieval.get("timeline_context") or {},
        "retrieval_duration_ms": retrieval.get("retrieval_duration_ms", 0),
        "retrieval_debug": retrieval.get("retrieval_debug") or {},
        "langgraph": {
            "engine": workflow_engine,
            "fallback_active": workflow_engine == "fallback",
            "nodes": list(LANGGRAPH_RAG_PIPELINE_STEPS),
        },
    }
    if conversation_context is not None:
        rag["conversation_context"] = conversation_context.diagnostics()
    return rag


def _knowledge_source_count(sources):
    """Return how many retrieved sources came from RAG knowledge chunks."""
    return sum(1 for source in sources if source.get("type") == "knowledge")


def _append_trace(state, node_name, metadata=None):
    """Return trace entries with the current node appended."""
    trace = list(state.get("trace") or [])
    trace.append(
        {
            "node": node_name,
            "status": "ok",
            "metadata": metadata or {},
        },
    )
    return trace


def _trace_payload(trace, workflow_engine):
    """Return prompt-safe workflow trace diagnostics."""
    return {
        "engine": workflow_engine,
        "fallback_active": workflow_engine == "fallback",
        "nodes": list(LANGGRAPH_RAG_PIPELINE_STEPS),
        "completed_nodes": [entry["node"] for entry in trace],
    }
