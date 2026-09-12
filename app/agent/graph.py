"""LangGraph state machine for the tool-using maintenance agent.

Nodes::

    guard -> agent -> tools -> agent -> ... -> validate -> respond

- ``guard`` runs deterministic safety and permission checks and builds the
  provider messages, continuing a checkpointed thread when one exists.
- ``agent`` asks the provider for an answer or tool calls.
- ``tools`` executes tool calls through the permission-gated registry.
- ``validate`` applies confidence scoring and post-generation safety.
- ``respond`` writes prompt-safe workflow diagnostics.

State stays JSON-serializable so a LangGraph checkpointer can persist it per
thread (user + session). The user is referenced by id, tools are derived from
the user's permissions, and the provider is resolved per call (an override
context variable exists for tests).

When ``langgraph`` is unavailable the same node functions run in a
deterministic loop, mirroring the RAG workflow module.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

from flask import current_app, has_app_context

from app.agent.prompts import build_agent_system_prompt
from app.agent.tools import available_tools, execute_tool, provider_tool_schemas, tool_spec
from app.extensions import db
from app.models import User
from app.services.ai_confidence_service import attach_confidence_to_result
from app.services.ai_retrieval import allowed_ai_scopes
from app.services.ai_routing import local_metadata
from app.services.ai_safety_service import (
    SAFETY_NOTICE,
    apply_post_generation_safety_to_result,
    assess_ai_safety,
    enforce_post_generation_safety,
)
from app.services.ai_service import AIServiceError, get_ai_provider
from app.services.langfuse_service import langfuse_trace_context

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - optional dependency
    END = None
    StateGraph = None

logger = logging.getLogger(__name__)

AGENT_PIPELINE_STEPS = ["guard", "agent", "tools", "validate", "respond"]
DEFAULT_MAX_ITERATIONS = 4
DEFAULT_HISTORY_MESSAGES = 4
DEFAULT_HISTORY_MAX_CHARS = 1400
MAX_TOOL_CALLS_PER_ROUND = 4
USAGE_KEYS = ("input_tokens", "output_tokens", "cached_tokens", "total_tokens")
COMPILED_GRAPH_KEY = "agent_compiled_graph"
_PROVIDER_OVERRIDE: ContextVar[Any] = ContextVar("maintenance_agent_provider", default=None)


class AgentState(TypedDict, total=False):
    """JSON-serializable state passed between agent workflow nodes."""

    message: str
    user_id: int
    session_id: str
    history: list
    messages: list
    pending_tool_calls: list
    tool_trace: list
    sources: list
    data: dict
    iterations: int
    max_iterations: int
    pending_action: Any
    answer: Any
    diagnostics: dict
    usage: dict
    safety: dict
    blocked: bool
    tool_scopes: list
    turn_count: int
    result: dict
    trace: list
    workflow_engine: str


def run_agent_workflow(
    message,
    user,
    session_id="",
    history=None,
    provider=None,
    thread_id=None,
    checkpointer=None,
):
    """Run the agent workflow and return the result payload.

    ``checkpointer`` enables persistent thread state; ``thread_id`` scopes it
    to one user session. Without a checkpointer the optional ``history`` list
    seeds the conversation.
    """
    text = str(message or "").strip()
    if not text:
        raise ValueError("Agent workflow requires a non-empty message.")
    turn_state: AgentState = {
        "message": text,
        "user_id": int(user.id),
        "session_id": session_id or "",
        "history": list(history or []),
        "pending_tool_calls": [],
        "tool_trace": [],
        "sources": [],
        "data": {},
        "iterations": 0,
        "max_iterations": max_iterations(),
        "pending_action": None,
        "answer": None,
        "diagnostics": {},
        "usage": {},
        "safety": {},
        "blocked": False,
        "tool_scopes": [],
        "result": {},
        "trace": [],
        "workflow_engine": _workflow_engine_name(),
    }
    token = _PROVIDER_OVERRIDE.set(provider)
    try:
        graph = _compiled_graph(checkpointer)
        if graph is None:
            state = dict(turn_state)
            state["messages"] = []
            return _run_fallback_workflow(state)["result"]
        config = {}
        if checkpointer is not None:
            config = {"configurable": {"thread_id": thread_id or f"{user.id}:{uuid4().hex}"}}
        return graph.invoke(turn_state, config=config)["result"]
    finally:
        _PROVIDER_OVERRIDE.reset(token)


def max_iterations():
    """Return the configured agent iteration cap."""
    return max(1, _config_int("AI_AGENT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS))


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def guard_node(state):
    """Run deterministic safety checks and build the provider messages.

    A checkpointed thread already carries ``messages`` from earlier turns; they
    are compacted to plain user/assistant turns so tool payloads from previous
    rounds do not accumulate.
    """
    user = _state_user(state)
    safety = assess_ai_safety(state["message"])
    tools = available_tools(user)
    scopes = allowed_ai_scopes(user)
    system_prompt = build_agent_system_prompt(scopes, safety.prompt_rules)
    previous = compact_history(state.get("messages") or [])
    if not previous:
        previous = [
            {"role": item["role"], "content": item["content"]}
            for item in state.get("history") or []
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
    previous = previous[-2 * _config_int("AI_SESSION_CONTEXT_MESSAGES", DEFAULT_HISTORY_MESSAGES) :]
    messages = [{"role": "system", "content": system_prompt}, *previous]
    messages.append({"role": "user", "content": state["message"]})
    blocked = bool(safety.blocked_actions)
    update = {
        "messages": messages,
        "safety": safety.to_dict(),
        "blocked": blocked,
        "turn_count": int(state.get("turn_count") or 0) + 1,
        "trace": _append_trace(
            state,
            "guard",
            {
                "tool_count": len(tools),
                "safety_risk_level": safety.risk_level,
                "blocked": blocked,
                "history_messages": len(previous),
            },
        ),
    }
    if blocked:
        update["answer"] = (
            f"{SAFETY_NOTICE}"
            "- **Ergebnis:** Anfragen zum Umgehen von Schutzfunktionen oder zu Arbeiten "
            "unter Spannung werden nicht bearbeitet.\n"
            "- **Naechster Schritt:** Maschine sichern, freigegebene Anweisungen nutzen "
            "und qualifizierte Fachkraft hinzuziehen."
        )
        update["diagnostics"] = _local_diagnostics("safety_blocked")
    return update


def agent_node(state):
    """Ask the provider for an answer or tool calls."""
    user = _state_user(state)
    provider = _current_provider()
    tools = available_tools(user)
    messages = list(state.get("messages") or [])
    iterations = int(state.get("iterations") or 0) + 1
    started = perf_counter()
    try:
        with langfuse_trace_context(
            "agent",
            user=user,
            session_id=state.get("session_id") or "",
            metadata={"iteration": iterations, "tool_count": len(tools)},
            tags=["agent", "tools"],
        ):
            response = provider.chat_with_tools(
                messages,
                provider_tool_schemas(tools),
                workflow="agent",
            )
    except AIServiceError as exc:
        logger.warning("agent_provider_failed provider=%s error=%s", provider.name, exc.error_code)
        return {
            "iterations": iterations,
            "pending_tool_calls": [],
            "answer": None,
            "diagnostics": _error_diagnostics(provider, exc),
            "trace": _append_trace(
                state, "agent", {"iteration": iterations, "error": exc.error_code}
            ),
        }
    usage = _merge_usage(state.get("usage") or {}, response.metadata, perf_counter() - started)
    tool_calls = [
        {"id": call.id, "name": call.name, "arguments": dict(call.arguments or {})}
        for call in response.tool_calls
        if tool_spec(call.name)
    ]
    if tool_calls and iterations < int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS):
        messages.append(_assistant_tool_message(response.content, tool_calls))
        return {
            "iterations": iterations,
            "messages": messages,
            "pending_tool_calls": tool_calls[:MAX_TOOL_CALLS_PER_ROUND],
            "usage": usage,
            "trace": _append_trace(
                state,
                "agent",
                {"iteration": iterations, "tool_calls": [call["name"] for call in tool_calls]},
            ),
        }
    answer = response.content
    if not answer and tool_calls:
        answer = _iteration_limit_answer(state.get("tool_trace") or [])
    if answer:
        messages.append({"role": "assistant", "content": answer})
    return {
        "iterations": iterations,
        "messages": messages,
        "pending_tool_calls": [],
        "answer": answer,
        "usage": usage,
        "diagnostics": _provider_diagnostics(provider, usage),
        "trace": _append_trace(state, "agent", {"iteration": iterations, "final": True}),
    }


def tools_node(state):
    """Execute pending tool calls and feed results back into the messages."""
    user = _state_user(state)
    messages = list(state.get("messages") or [])
    tool_trace = list(state.get("tool_trace") or [])
    sources = list(state.get("sources") or [])
    data = dict(state.get("data") or {})
    scopes = list(state.get("tool_scopes") or [])
    pending_action = state.get("pending_action")
    pending_calls = state.get("pending_tool_calls") or []
    for call in pending_calls:
        name = call["name"]
        started = perf_counter()
        with langfuse_trace_context(
            "agent_tool",
            user=user,
            session_id=state.get("session_id") or "",
            metadata={"tool": name},
            tags=["agent", "tool", name],
        ):
            result = execute_tool(name, call.get("arguments") or {}, user)
        duration_ms = int((perf_counter() - started) * 1000)
        payload = result.to_model_payload()
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "name": name,
                "content": json.dumps(payload, ensure_ascii=True, default=str),
            }
        )
        tool_trace.append(
            {
                "tool": name,
                "status": result.status,
                "summary": str(result.summary or "")[:200],
                "arguments": _safe_arguments(call.get("arguments")),
                "source_count": len(result.sources),
                "duration_ms": duration_ms,
            }
        )
        sources = _merge_sources(sources, result.sources)
        data[name] = result.content
        spec = tool_spec(name)
        if spec is not None:
            scopes.extend(scope for scope in spec.scopes if scope not in scopes)
        if result.status == "confirmation_required":
            pending_action = (result.content or {}).get("pending_action") or pending_action
    return {
        "messages": messages,
        "pending_tool_calls": [],
        "tool_trace": tool_trace,
        "sources": sources,
        "data": data,
        "tool_scopes": scopes,
        "pending_action": pending_action,
        "trace": _append_trace(state, "tools", {"executed": len(pending_calls)}),
    }


def validate_node(state):
    """Assemble the result and apply confidence and post-generation safety checks."""
    answer = state.get("answer")
    diagnostics = dict(state.get("diagnostics") or {})
    tool_trace = list(state.get("tool_trace") or [])
    if not answer:
        answer = _fallback_answer(tool_trace, diagnostics)
        diagnostics.setdefault("fallback_used", True)
    if not diagnostics:
        diagnostics = _local_diagnostics("local_answer")
    result = {
        "type": "agent",
        "answer": answer,
        "sources": list(state.get("sources") or []),
        "data": {"tools": state.get("data") or {}},
        "diagnostics": diagnostics,
        "tool_trace": tool_trace,
        "tool_scopes": list(state.get("tool_scopes") or []),
        "answer_category": "agent",
        "retrieval_used": bool(state.get("sources")),
        "rag": {
            "enabled": True,
            "pipeline": list(AGENT_PIPELINE_STEPS),
            "safety": state.get("safety") or {},
            "source_count": len(state.get("sources") or []),
        },
    }
    if state.get("pending_action"):
        result["pending_action"] = state["pending_action"]
    result = attach_confidence_to_result(state["message"], result)
    post_safety = enforce_post_generation_safety(result.get("answer"), state.get("safety"))
    result = apply_post_generation_safety_to_result(result, post_safety)
    return {
        "result": result,
        "trace": _append_trace(
            state,
            "validate",
            {
                "post_generation_safety": post_safety.action,
                "confidence_level": (result.get("confidence") or {}).get("level", ""),
            },
        ),
    }


def respond_node(state):
    """Attach prompt-safe workflow diagnostics to the result."""
    trace = _append_trace(state, "respond")
    result = dict(state.get("result") or {})
    result.setdefault("rag", {})["agent"] = {
        "engine": state.get("workflow_engine", "fallback"),
        "fallback_active": state.get("workflow_engine") != "langgraph",
        "nodes": list(AGENT_PIPELINE_STEPS),
        "completed_nodes": [entry["node"] for entry in trace],
        "iterations": int(state.get("iterations") or 0),
        "turn_count": int(state.get("turn_count") or 0),
        "tool_calls": [entry["tool"] for entry in state.get("tool_trace") or []],
        "max_iterations": int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS),
    }
    result["diagnostics"].setdefault("workflow", "agent")
    result["diagnostics"]["agent_iterations"] = int(state.get("iterations") or 0)
    result["diagnostics"]["agent_tool_calls"] = [
        entry["tool"] for entry in state.get("tool_trace") or []
    ]
    return {"result": result, "trace": trace}


# ---------------------------------------------------------------------------
# Routing and runners
# ---------------------------------------------------------------------------


def route_after_guard(state):
    """Skip the model when the guard blocked the request."""
    return "validate" if state.get("blocked") else "agent"


def route_after_agent(state):
    """Continue with tools while calls are pending, otherwise validate."""
    return "tools" if state.get("pending_tool_calls") else "validate"


def _run_fallback_workflow(state):
    """Run the node sequence without LangGraph."""
    state.update(guard_node(state))
    if not state.get("blocked"):
        while True:
            state.update(agent_node(state))
            if not state.get("pending_tool_calls"):
                break
            state.update(tools_node(state))
    state.update(validate_node(state))
    state.update(respond_node(state))
    return state


def _compiled_graph(checkpointer=None):
    """Return the compiled LangGraph workflow or ``None`` for the fallback runner."""
    if StateGraph is None or END is None:
        return None
    cache = current_app.extensions if has_app_context() else None
    cache_key = (COMPILED_GRAPH_KEY, id(checkpointer))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    try:
        graph = StateGraph(AgentState)
        graph.add_node("guard", guard_node)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_node("validate", validate_node)
        graph.add_node("respond", respond_node)
        graph.set_entry_point("guard")
        graph.add_conditional_edges(
            "guard", route_after_guard, {"agent": "agent", "validate": "validate"}
        )
        graph.add_conditional_edges(
            "agent", route_after_agent, {"tools": "tools", "validate": "validate"}
        )
        graph.add_edge("tools", "agent")
        graph.add_edge("validate", "respond")
        graph.add_edge("respond", END)
        compiled = graph.compile(checkpointer=checkpointer)
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "agent_langgraph_compile_failed fallback=deterministic_runner", exc_info=True
        )
        return None
    if cache is not None:
        cache[cache_key] = compiled
    return compiled


def _workflow_engine_name():
    """Return which workflow engine is active."""
    return "langgraph" if StateGraph is not None and END is not None else "fallback"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compact_history(messages):
    """Return plain user/assistant turns from a provider message list.

    Tool payloads and assistant tool-call envelopes are dropped so the next
    turn starts from a bounded conversational memory.
    """
    compact = []
    for message in messages or []:
        role = message.get("role")
        content = message.get("content")
        if role == "user" and content:
            compact.append({"role": "user", "content": str(content)})
        elif role == "assistant" and content and not message.get("tool_calls"):
            compact.append({"role": "assistant", "content": str(content)})
    max_chars = _config_int("AI_SESSION_CONTEXT_MAX_CHARS", DEFAULT_HISTORY_MAX_CHARS)
    return [
        {
            "role": item["role"],
            "content": (
                item["content"]
                if len(item["content"]) <= max_chars
                else item["content"][:max_chars] + "..."
            ),
        }
        for item in compact
    ]


def _state_user(state):
    """Return the user for the state's user id."""
    user = db.session.get(User, int(state["user_id"]))
    if user is None:
        raise ValueError("Agent workflow user no longer exists.")
    return user


def _current_provider():
    """Return the provider override for this run or the configured provider."""
    override = _PROVIDER_OVERRIDE.get()
    return override if override is not None else get_ai_provider()


def _config_int(key, default):
    """Return an integer config value with a safe fallback."""
    if not has_app_context():
        return default
    try:
        return int(current_app.config.get(key, default))
    except (TypeError, ValueError):
        return default


def _assistant_tool_message(content, tool_calls):
    """Return the provider-format assistant message carrying tool calls."""
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=True),
                },
            }
            for call in tool_calls
        ],
    }


def _merge_usage(usage, metadata, elapsed_seconds):
    """Accumulate token usage, cost and latency across provider calls."""
    merged = dict(usage)
    metadata = metadata or {}
    for key in USAGE_KEYS:
        merged[key] = int(merged.get(key) or 0) + int(metadata.get(key) or 0)
    merged["estimated_cost_usd"] = round(
        float(merged.get("estimated_cost_usd") or 0.0)
        + float(metadata.get("estimated_cost_usd") or 0.0),
        6,
    )
    merged["latency_ms"] = int(merged.get("latency_ms") or 0) + int(
        metadata.get("latency_ms") or round(elapsed_seconds * 1000)
    )
    merged["calls"] = int(merged.get("calls") or 0) + 1
    for key in ("model", "model_tier", "temperature", "max_tokens", "provider"):
        if metadata.get(key) not in (None, ""):
            merged[key] = metadata[key]
    for key in (
        "langfuse_trace_id",
        "langfuse_observation_id",
        "langfuse_host",
        "langfuse_enabled",
    ):
        if key in metadata:
            merged[key] = metadata[key]
    return merged


def _provider_diagnostics(provider, usage):
    """Return diagnostics for a completed provider-driven agent run."""
    status = "local_answer" if provider.name == "mock" else "openai_used"
    diagnostics = {
        "status": status,
        "fallback_used": False,
        "provider": provider.name,
        "workflow": "agent",
    }
    diagnostics.update({key: value for key, value in usage.items() if key != "provider"})
    diagnostics.setdefault("model", usage.get("model") or "local")
    return diagnostics


def _error_diagnostics(provider, exc):
    """Return diagnostics for a failed provider call."""
    return {
        "status": "openai_error",
        "fallback_used": True,
        "provider": provider.name,
        "workflow": "agent",
        "error": exc.error_code,
        "model": getattr(provider, "model", "") or "",
    }


def _local_diagnostics(status):
    """Return diagnostics for a local (no provider) agent answer."""
    diagnostics = local_metadata("local", "agent")
    diagnostics.update({"status": status, "fallback_used": status != "local_answer"})
    return diagnostics


def _fallback_answer(tool_trace, diagnostics):
    """Return a grounded answer when the provider produced no final text."""
    lines = ["## Ergebnis (Agent)"]
    if diagnostics.get("status") == "openai_error":
        lines.append("- **Status:** Der AI-Provider ist gerade nicht erreichbar.")
    if tool_trace:
        lines.append("- **Ausgefuehrte Werkzeuge:**")
        for entry in tool_trace[:6]:
            lines.append(f"  - {entry['tool']}: {entry.get('summary') or entry.get('status')}")
    else:
        lines.append("- **Status:** Keine belastbare Antwort erzeugt.")
    lines.append("- **Naechster Schritt:** Frage konkreter stellen oder spaeter erneut versuchen.")
    return "\n".join(lines)


def _iteration_limit_answer(tool_trace):
    """Return an answer when the iteration cap stopped further tool calls."""
    lines = [
        "## Ergebnis (Agent)",
        "- **Status:** Iterationslimit erreicht; weitere Werkzeugaufrufe wurden gestoppt.",
    ]
    for entry in tool_trace[:6]:
        lines.append(f"- {entry['tool']}: {entry.get('summary') or entry.get('status')}")
    return "\n".join(lines)


def _merge_sources(existing, additions):
    """Merge source cards without duplicates."""
    seen = {(item.get("type"), item.get("id"), item.get("chunk_id")) for item in existing}
    merged = list(existing)
    for source in additions or []:
        key = (source.get("type"), source.get("id"), source.get("chunk_id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def _safe_arguments(arguments):
    """Return bounded tool arguments for diagnostics."""
    safe = {}
    for key, value in (arguments or {}).items():
        text = str(value)
        safe[str(key)] = text if len(text) <= 120 else text[:120] + "..."
    return safe


def _append_trace(state, node_name, metadata=None):
    """Return the trace with the current node appended."""
    trace = list(state.get("trace") or [])
    trace.append({"node": node_name, "status": "ok", "metadata": metadata or {}})
    return trace
