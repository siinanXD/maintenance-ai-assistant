"""Public entry points for the tool-using maintenance agent."""

from __future__ import annotations

from datetime import timedelta

from flask import current_app

from app.agent.graph import run_agent_workflow
from app.agent.tools import available_tools
from app.ai.handlers.tracing_handler import finalize_chat_answer
from app.domain_models.common import utc_now
from app.models import ChatMessage
from app.services.ai_retrieval import allowed_ai_scopes
from app.services.conversation_context_service import normalize_session_id

DEFAULT_HISTORY_MESSAGES = 4
DEFAULT_HISTORY_TTL_MINUTES = 120
DEFAULT_HISTORY_MAX_CHARS = 1400


def run_agent(message, user, session_id="", provider=None):
    """Run the agent for one user message and return a chat-compatible result."""
    normalized_session_id = normalize_session_id(session_id)
    history = conversation_history(user, normalized_session_id)
    result = run_agent_workflow(
        message,
        user,
        session_id=normalized_session_id,
        history=history,
        provider=provider,
    )
    result.setdefault("diagnostics", {})["session_id"] = normalized_session_id
    result["diagnostics"]["history_messages"] = len(history)
    requested_scopes = list(result.pop("tool_scopes", []) or [])
    return finalize_chat_answer(
        user,
        result,
        requested_scopes,
        sorted(allowed_ai_scopes(user)),
        workflow="agent",
        message=message,
    )


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
    return {
        "tools": [spec.to_dict() for spec in tools],
        "tool_count": len(tools),
        "max_iterations": _config_int("AI_AGENT_MAX_ITERATIONS", 4),
        "confirmation_required_tools": [spec.name for spec in tools if spec.requires_confirmation],
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
