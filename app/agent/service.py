"""Public entry points for the tool-using maintenance agent."""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from app.agent.checkpoints import agent_checkpointer
from app.agent.graph import run_agent_workflow
from app.agent.tools import available_tools
from app.ai.handlers.structured_handler import (
    try_domain_structured_answers,
    try_local_structured_routes,
)
from app.ai.handlers.tracing_handler import finalize_chat_answer
from app.ai.intent import detect_requested_scopes
from app.domain_models.common import utc_now
from app.models import ChatMessage
from app.services.ai_retrieval import allowed_ai_scopes
from app.services.conversation_context_service import (
    conversation_context_for_chat,
    normalize_session_id,
)

DEFAULT_HISTORY_MESSAGES = 4
DEFAULT_HISTORY_TTL_MINUTES = 120
DEFAULT_HISTORY_MAX_CHARS = 1400
FAST_PATH_MARKER = "structured_rules"


def run_agent(message, user, session_id="", provider=None):
    """Run the agent for one user message and return a chat-compatible result.

    Order of operations:

    1. Deterministic structured fast path (counts, lists, status questions,
       permission denials) reuses the rule-based handlers without a model call.
    2. Otherwise the LangGraph agent loop runs with tool calling. Session
       memory comes from the configured checkpointer, or from ``ChatMessage``
       rows when no checkpointer is active.
    """
    normalized_session_id = normalize_session_id(session_id)
    fast_result = structured_fast_path(message, user, normalized_session_id)
    if fast_result is not None:
        return fast_result

    checkpointer, backend = agent_checkpointer()
    history = []
    if checkpointer is None:
        history = conversation_history(user, normalized_session_id)
    result = run_agent_workflow(
        message,
        user,
        session_id=normalized_session_id,
        history=history,
        provider=provider,
        thread_id=thread_id_for(user, normalized_session_id),
        checkpointer=checkpointer,
    )
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["session_id"] = normalized_session_id
    diagnostics["memory_backend"] = backend
    if checkpointer is None:
        diagnostics["history_messages"] = len(history)
    requested_scopes = list(result.pop("tool_scopes", []) or [])
    return finalize_chat_answer(
        user,
        result,
        requested_scopes,
        sorted(allowed_ai_scopes(user)),
        workflow="agent",
        message=message,
    )


def structured_fast_path(message, user, session_id):
    """Return a deterministic structured answer when the rule handlers match.

    The handlers are permission-aware and already produce audited results, so
    matching questions cost no model tokens and stay fully reproducible.
    """
    if not _config_flag("AI_AGENT_STRUCTURED_FAST_PATH", True):
        return None
    conversation_context = conversation_context_for_chat(user, message, session_id)
    requested_scopes = detect_requested_scopes(message)
    if conversation_context.applied:
        requested_scopes |= set(conversation_context.suggested_scopes)
    allowed_scopes = allowed_ai_scopes(user)
    result = try_domain_structured_answers(
        message,
        user,
        conversation_context,
        requested_scopes,
        allowed_scopes,
    )
    if result is None:
        result = try_local_structured_routes(
            message,
            user,
            conversation_context,
            requested_scopes,
            allowed_scopes,
        )
    if result is None:
        return None
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["agent_fast_path"] = FAST_PATH_MARKER
    diagnostics.setdefault("workflow", "agent")
    diagnostics["session_id"] = session_id
    result.setdefault("rag", {})["agent"] = {
        "engine": "fast_path",
        "fallback_active": False,
        "nodes": ["structured_rules"],
        "completed_nodes": ["structured_rules"],
        "iterations": 0,
        "tool_calls": [],
    }
    result.setdefault("tool_trace", [])
    return result


def thread_id_for(user, session_id):
    """Return the checkpoint thread id scoped to one user session."""
    if not session_id:
        return None
    return f"user:{user.id}:{session_id}"


def conversation_history(user, session_id):
    """Return recent chat turns of one session as provider messages."""
    if not session_id:
        return []
    limit = _config_int("AI_SESSION_CONTEXT_MESSAGES", DEFAULT_HISTORY_MESSAGES)
    ttl_minutes = _config_int("AI_SESSION_CONTEXT_TTL_MINUTES", DEFAULT_HISTORY_TTL_MINUTES)
    max_chars = _config_int("AI_SESSION_CONTEXT_MAX_CHARS", DEFAULT_HISTORY_MAX_CHARS)
    cutoff = utc_now() - timedelta(minutes=max(1, ttl_minutes))
    entries = (
        ChatMessage.query.filter(
            ChatMessage.user_id == user.id,
            ChatMessage.session_id == session_id,
            ChatMessage.created_at >= cutoff,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(max(1, limit))
        .all()
    )
    history = []
    for entry in reversed(entries):
        history.append({"role": "user", "content": _bounded(entry.message, max_chars)})
        history.append({"role": "assistant", "content": _bounded(entry.response, max_chars)})
    return history


def agent_capabilities(user):
    """Return the tools the user may call through the agent."""
    tools = available_tools(user)
    _, backend = agent_checkpointer()
    return {
        "tools": [spec.to_dict() for spec in tools],
        "tool_count": len(tools),
        "max_iterations": _config_int("AI_AGENT_MAX_ITERATIONS", 4),
        "confirmation_required_tools": [spec.name for spec in tools if spec.requires_confirmation],
        "memory_backend": backend,
        "structured_fast_path": _config_flag("AI_AGENT_STRUCTURED_FAST_PATH", True),
    }


def _config_int(key, default):
    """Return an integer config value with a safe fallback."""
    try:
        return int(current_app.config.get(key, default))
    except (TypeError, ValueError):
        return default


def _config_flag(key, default):
    """Return a boolean config value that tolerates string values."""
    value = current_app.config.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _bounded(text, max_chars):
    """Return text limited to the configured history size."""
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "..."
