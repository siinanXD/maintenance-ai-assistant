"""Public entry points for the tool-using maintenance agent."""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from app.agent.checkpoints import agent_checkpointer
from app.agent.graph import run_agent_workflow
from app.agent.tools import available_tools
from app.ai.status import attach_audit_metadata
from app.domain_models.common import utc_now
from app.models import ChatMessage
from app.services.ai_retrieval import allowed_ai_scopes
from app.services.conversation_context_service import (
    last_structured_context,
    normalize_session_id,
)

DEFAULT_HISTORY_MESSAGES = 4
DEFAULT_HISTORY_TTL_MINUTES = 120
DEFAULT_HISTORY_MAX_CHARS = 1400


def run_agent(message, user, session_id="", provider=None):
    """Run the agent for one user message and return a chat-compatible result.

    The LangGraph loop (guard -> agent -> tools -> validate -> respond) selects
    tools with explicit arguments. Session memory comes from the configured
    checkpointer, or from ``ChatMessage`` rows when no checkpointer is active;
    in both cases the last structured data scope of the session is handed to
    the prompt so follow-up questions can refine it.
    """
    normalized_session_id = normalize_session_id(session_id)
    checkpointer, backend = agent_checkpointer()
    history = []
    structured_hint = None
    if checkpointer is None:
        history = conversation_history(user, normalized_session_id)
        structured_hint = last_structured_context(user, normalized_session_id) or None
    result = run_agent_workflow(
        message,
        user,
        session_id=normalized_session_id,
        history=history,
        provider=provider,
        thread_id=thread_id_for(user, normalized_session_id),
        checkpointer=checkpointer,
        structured_hint=structured_hint,
    )
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["session_id"] = normalized_session_id
    diagnostics["memory_backend"] = backend
    if checkpointer is None:
        diagnostics["history_messages"] = len(history)
    requested_scopes = list(result.pop("tool_scopes", []) or [])
    return attach_audit_metadata(
        user,
        result,
        requested_scopes,
        sorted(allowed_ai_scopes(user)),
        workflow="agent",
        message=message,
    )


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
    }


def _config_int(key, default):
    """Return an integer config value with a safe fallback."""
    try:
        return int(current_app.config.get(key, default))
    except (TypeError, ValueError):
        return default


def _bounded(text, max_chars):
    """Return text limited to the configured history size."""
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "..."
