"""Visibility rules for AI chat responses shown in the global chat bubble."""

from copy import deepcopy

from app.models import Role
from app.services.ai_answer_quality_service import redacted_answer_quality

ANSWER_ONLY_MODE = "answer_only"
VISIBLE_STATUS_KEYS = ("status", "fallback_used")


def can_view_ai_evidence(user):
    """Return whether a user may see AI sources and diagnostics in the chat UI."""
    if not user:
        return False
    return bool(getattr(user, "is_admin", False) or getattr(user, "role", None) == Role.IT)


def wants_answer_only_response(payload):
    """Return whether a request asks for answer-only chat output."""
    return str((payload or {}).get("response_mode") or "").strip() == ANSWER_ONLY_MODE


def should_redact_ai_response(user, result, answer_only=False):
    """Return whether an AI response should be reduced for the current user."""
    diagnostics = (result or {}).get("diagnostics") or {}
    if (
        diagnostics.get("status") == "permission_denied"
        or (result or {}).get("type") == "permission_denied"
    ):
        return True
    return bool(answer_only and not can_view_ai_evidence(user))


def redact_ai_chat_response(result, user, answer_only=False):
    """Return a user-visible AI chat response with restricted evidence removed."""
    if not should_redact_ai_response(user, result, answer_only=answer_only):
        return result

    redacted = deepcopy(result or {})
    redacted["sources"] = []
    redacted["data"] = _empty_data(redacted.get("data"))
    redacted["diagnostics"] = _redacted_diagnostics(redacted.get("diagnostics"))
    redacted["evidence_visible"] = False
    redacted["answer_quality"] = redacted_answer_quality(redacted.get("answer_quality"))
    redacted.pop("rag", None)
    redacted.pop("action_preview", None)
    redacted.pop("confidence", None)
    # Tool traces stay limited to names and status; pending actions belong to the
    # requesting user and are required to confirm agent write actions.
    if "tool_trace" in redacted:
        redacted["tool_trace"] = [
            {"tool": entry.get("tool"), "status": entry.get("status")}
            for entry in redacted.get("tool_trace") or []
            if isinstance(entry, dict)
        ]
    return redacted


def redact_chat_history_result(result, user):
    """Return a chat-history payload redacted for non-evidence users."""
    if can_view_ai_evidence(user):
        return result

    redacted = deepcopy(result or {})
    items = []
    for item in redacted.get("items") or []:
        items.append(redact_chat_history_item(item))
    redacted["items"] = items
    return redacted


def redact_chat_history_item(item):
    """Return one chat-history entry without source and diagnostic detail."""
    redacted = deepcopy(item or {})
    redacted["diagnostics"] = _redacted_diagnostics(redacted.get("diagnostics"))
    redacted["source_count"] = 0
    redacted["confidence_score"] = None
    redacted["confidence_level"] = ""
    redacted["answer_quality"] = redacted_answer_quality(redacted.get("answer_quality"))
    redacted["evidence_visible"] = False
    redacted.pop("sources", None)
    return redacted


def _redacted_diagnostics(diagnostics):
    """Return only the status fields needed by normal chat users."""
    source = diagnostics or {}
    payload = {key: source[key] for key in VISIBLE_STATUS_KEYS if key in source}
    status = payload.get("status") or "local_answer"
    payload["status"] = status
    payload["answer_origin"] = _answer_origin(source)
    payload["evidence_visible"] = False
    return payload


def _answer_origin(diagnostics):
    """Return whether a response came from AI or local fallback."""
    status = str((diagnostics or {}).get("status") or "")
    if status == "openai_used":
        return "ai"
    return "local"


def _empty_data(value):
    """Return an empty container matching the original data shape."""
    if isinstance(value, dict):
        return {}
    return []
