"""Services for AI chat history and admin chat search."""

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import ChatMessage
from app.services.ai_answer_quality_service import answer_quality_from_history_item
from app.services.conversation_context_service import normalize_session_id

logger = logging.getLogger(__name__)


def save_chat_exchange(user, message, result, session_id=""):
    """Persist one chat exchange with safe response metadata."""
    diagnostics = result.get("diagnostics") or {}
    confidence = diagnostics.get("confidence") or {}
    normalized_session_id = normalize_session_id(
        session_id or diagnostics.get("session_id") or "",
    )
    chat = ChatMessage(
        user_id=user.id,
        message=str(message or "")[:8000],
        response=str(result.get("answer") or "")[:16000],
        response_type=str(result.get("type") or "assistant")[:80],
        session_id=normalized_session_id,
        diagnostics_json=json.dumps(diagnostics, ensure_ascii=True),
        source_count=len(result.get("sources") or []),
        confidence_score=_optional_int(
            diagnostics.get("confidence_score") or confidence.get("score"),
        ),
        confidence_level=str(
            diagnostics.get("confidence_level") or confidence.get("level") or "",
        )[:40],
        audit_event_id=diagnostics.get("audit_event_id"),
    )
    return chat


def chat_history_query(user, filters=None, include_all=False):
    """Return a filtered chat history query for a user or all users."""
    filters = filters or {}
    query = ChatMessage.query
    if not include_all:
        query = query.filter(ChatMessage.user_id == user.id)

    user_id = filters.get("user_id")
    if include_all and user_id not in (None, ""):
        try:
            query = query.filter(ChatMessage.user_id == int(user_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("user_id must be an integer") from exc

    q = str(filters.get("q") or "").strip()
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (ChatMessage.message.ilike(pattern)) | (ChatMessage.response.ilike(pattern))
        )

    return query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())


def paginated_chat_history(user, args, include_all=False):
    """Return paginated chat history entries and pagination metadata."""
    query = chat_history_query(user, args, include_all=include_all)
    limit, offset = parse_limit_offset(args)
    total = query.count()
    entries = query.offset(offset).limit(limit).all()
    return {
        "items": [chat_history_item(entry, include_user=include_all) for entry in entries],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    }


def chat_history_item(entry, include_user=False):
    """Return one chat-history item with compact answer-quality metadata."""
    payload = entry.to_dict(include_user=include_user)
    payload["answer_quality"] = answer_quality_from_history_item(payload)
    return payload


def history_answer_quality(item):
    """Return answer-quality metadata reconstructed from stored chat fields."""
    return answer_quality_from_history_item(item)


def parse_limit_offset(args, default_limit=30, max_limit=200):
    """Parse common limit and offset query parameters."""
    try:
        limit = min(max(1, int(args.get("limit", default_limit))), max_limit)
        offset = max(0, int(args.get("offset", 0)))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    return limit, offset


def _optional_int(value):
    """Return an optional integer for persisted diagnostics."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def save_chat_message(user, message, response, session_id=""):
    """Persist a chat message and its assistant response in the database."""
    result = response if isinstance(response, dict) else {"answer": response}
    chat = save_chat_exchange(user, message, result, session_id=session_id)
    db.session.add(chat)
    try:
        db.session.commit()
        return chat
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("ai_chat_save_failed user_id=%s", getattr(user, "id", None))
        return None
