"""Signed pending actions for human-in-the-loop agent write tools.

A write tool never runs from the model loop. The loop returns a signed,
time-limited token describing the exact tool call. Only the same user can
confirm it, and the confirmation executes the tool once with a full audit trail.
Tokens are stateless, so no extra table or migration is needed.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.services.operations_tracking_service import record_event

logger = logging.getLogger(__name__)

ACTION_SALT = "maintenance-agent-action"
DEFAULT_ACTION_TTL_SECONDS = 600


def action_ttl_seconds():
    """Return how long a pending action token stays valid."""
    try:
        return max(
            30,
            int(current_app.config.get("AI_AGENT_ACTION_TTL_SECONDS", DEFAULT_ACTION_TTL_SECONDS)),
        )
    except (TypeError, ValueError):
        return DEFAULT_ACTION_TTL_SECONDS


def _serializer():
    """Return the signer bound to the application secret."""
    return URLSafeTimedSerializer(str(current_app.config["SECRET_KEY"]), salt=ACTION_SALT)


def create_pending_action(user, spec, arguments):
    """Return a signed pending action payload for one write tool call."""
    token = _serializer().dumps(
        {
            "tool": spec.name,
            "arguments": arguments,
            "user_id": int(user.id),
            "nonce": uuid4().hex,
        }
    )
    return {
        "token": token,
        "tool": spec.name,
        "label": spec.label or spec.name,
        "arguments": arguments,
        "expires_in_seconds": action_ttl_seconds(),
        "confirm_endpoint": "/api/v1/ai/agent/confirm",
    }


def load_pending_action(token, user):
    """Return the decoded pending action for the user or ``(None, error, status)``."""
    try:
        payload = _serializer().loads(str(token or ""), max_age=action_ttl_seconds())
    except SignatureExpired:
        return None, {"error": "action_expired", "message": "Die Aktion ist abgelaufen."}, 400
    except BadSignature:
        return None, {"error": "invalid_action_token", "message": "Ungueltige Aktion."}, 400
    if not isinstance(payload, dict) or int(payload.get("user_id") or 0) != int(user.id):
        return (
            None,
            {"error": "action_forbidden", "message": "Aktion gehoert nicht zum Nutzer."},
            403,
        )
    return payload, None, 200


def confirm_pending_action(token, user):
    """Execute a confirmed pending action and return ``(result, error, status)``."""
    from app.agent.tools import execute_tool, tool_spec

    payload, error, status = load_pending_action(token, user)
    if error:
        return None, error, status
    spec = tool_spec(payload.get("tool"))
    if spec is None or not spec.requires_confirmation:
        return None, {"error": "unknown_action", "message": "Unbekannte Aktion."}, 400
    result = execute_tool(spec.name, payload.get("arguments") or {}, user, confirmed=True)
    if result.status == "permission_denied":
        return None, {"error": "permission_denied", "message": result.summary}, 403
    if result.status != "ok":
        return None, {"error": result.error or "action_failed", "message": result.summary}, 400
    record_event(
        "ai.agent_action_confirmed",
        "ai",
        entity_type="agent_action",
        user=user,
        department=getattr(user, "department", None),
        source="ai",
        metadata={"tool": spec.name, "summary": result.summary[:200]},
    )
    try:
        db.session.commit()
    except Exception:  # pragma: no cover - audit persistence must not break the action
        db.session.rollback()
        logger.exception("agent_action_audit_failed tool=%s", spec.name)
    answer = (
        "## Aktion ausgefuehrt\n"
        f"- **Aktion:** {spec.label or spec.name}\n"
        f"- **Ergebnis:** {result.summary}"
    )
    return (
        {
            "type": "agent_action",
            "answer": answer,
            "data": result.content,
            "sources": result.sources,
            "tool": spec.name,
            "diagnostics": {"status": "local_answer", "fallback_used": False, "workflow": "agent"},
        },
        None,
        200,
    )
