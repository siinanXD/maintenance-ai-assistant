"""Session identifiers and persisted structured-context memory for agent chats."""

from __future__ import annotations

import re
from datetime import timedelta

from flask import current_app, has_app_context

from app.domain_models.common import utc_now
from app.models import ChatMessage

DEFAULT_CONTEXT_TTL_MINUTES = 120
MAX_SESSION_ID_LENGTH = 120
STRUCTURED_CONTEXT_KEYS = (
    "entity_type",
    "department",
    "status",
    "time_range",
    "machine",
    "query",
    "shift",
    "employee_id",
    "employee_name",
)
ENTITY_TYPE_SCOPES = {
    "tasks": "tasks",
    "incidents": "errors",
    "errors": "errors",
    "maintenance": "tasks",
    "employees": "employees",
    "vacations": "employees",
    "documents": "documents",
    "machines": "machines",
    "shiftplans": "shiftplans",
    "inventory": "inventory",
    "daily_briefing": "tasks",
}


def normalize_session_id(value):
    """Return a safe optional chat session identifier."""
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", str(value or "").strip())
    return normalized[:MAX_SESSION_ID_LENGTH]


def structured_scope_to_dashboard_scope(structured_scope):
    """Return the dashboard permission scope for a structured memory payload."""
    entity_type = str((structured_scope or {}).get("entity_type") or "").strip()
    return ENTITY_TYPE_SCOPES.get(entity_type)


def build_structured_context_metadata(message, result, requested_scopes=None):
    """Return compact structured scope metadata to persist with chat diagnostics."""
    context = _safe_structured_context(result.get("structured_context") if result else None)
    if not context.get("entity_type"):
        return {}
    return context


def last_structured_context(user, session_id):
    """Return the structured context persisted with the latest chat turn of a session."""
    if not user or not session_id:
        return {}
    cutoff = utc_now() - timedelta(minutes=_context_ttl_minutes())
    entry = (
        ChatMessage.query.filter(
            ChatMessage.user_id == user.id,
            ChatMessage.session_id == session_id,
            ChatMessage.created_at >= cutoff,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .first()
    )
    if entry is None:
        return {}
    return _safe_structured_context(entry.diagnostics().get("structured_context"))


def _safe_structured_context(value):
    """Return a sanitized structured context dictionary."""
    if not isinstance(value, dict):
        return {}
    context = {}
    for key in STRUCTURED_CONTEXT_KEYS:
        raw_value = value.get(key)
        if raw_value in (None, ""):
            continue
        context[key] = _bounded_text(raw_value, 120)
    entity_type = context.get("entity_type")
    if entity_type and entity_type not in ENTITY_TYPE_SCOPES:
        return {}
    return context


def _bounded_text(value, max_chars):
    """Return compact text bounded to a maximum length."""
    text = " ".join(str(value or "").strip().split())
    return text[:max_chars]


def _context_ttl_minutes():
    """Return the short-term context lifetime in minutes."""
    value = (
        current_app.config.get("AI_SESSION_CONTEXT_TTL_MINUTES", DEFAULT_CONTEXT_TTL_MINUTES)
        if has_app_context()
        else DEFAULT_CONTEXT_TTL_MINUTES
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TTL_MINUTES
    return parsed if parsed > 0 else DEFAULT_CONTEXT_TTL_MINUTES
