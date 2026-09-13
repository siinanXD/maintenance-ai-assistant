"""Aging and stale-review logic for persisted knowledge documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import AIFeedback, KnowledgeDocument

logger = logging.getLogger(__name__)

REVIEWED_QUALITY_STATUSES = {"admin_approved", "technician_confirmed"}
AGING_CANDIDATE_QUALITY_STATUSES = {
    "draft",
    "ai_suggested",
    "technician_confirmed",
    "admin_approved",
}
TERMINAL_QUALITY_STATUSES = {"outdated", "rejected"}
DEFAULT_STALE_DAYS = 180
DEFAULT_UNCONFIRMED_DAYS = 60
DEFAULT_STABLE_CONFIRMATIONS = 3
DEFAULT_STABLE_HELPFUL_FEEDBACK = 3
DEFAULT_OUTDATED_MULTIPLIER = 0.55
DEFAULT_STALE_MULTIPLIER = 0.65
DEFAULT_OLD_MULTIPLIER = 0.78
DEFAULT_FEEDBACK_SCAN_LIMIT = 300


@dataclass(frozen=True)
class KnowledgeAgingPolicy:
    """Runtime thresholds that control knowledge aging decisions."""

    stale_days: int = DEFAULT_STALE_DAYS
    unconfirmed_days: int = DEFAULT_UNCONFIRMED_DAYS
    stable_confirmations: int = DEFAULT_STABLE_CONFIRMATIONS
    stable_helpful_feedback: int = DEFAULT_STABLE_HELPFUL_FEEDBACK
    outdated_multiplier: float = DEFAULT_OUTDATED_MULTIPLIER
    stale_multiplier: float = DEFAULT_STALE_MULTIPLIER
    old_multiplier: float = DEFAULT_OLD_MULTIPLIER


@dataclass(frozen=True)
class KnowledgeAgingState:
    """Computed aging state for one knowledge document."""

    document_id: int | None
    quality_status: str
    status: str
    age_days: int
    unconfirmed_days: int
    confirmation_count: int
    helpful_feedback_count: int
    stable: bool
    should_mark_outdated: bool
    retrieval_multiplier: float
    reason: str
    recommendation: str

    def to_dict(self):
        """Return a JSON-serializable aging state."""
        return {
            "document_id": self.document_id,
            "quality_status": self.quality_status,
            "status": self.status,
            "age_days": self.age_days,
            "unconfirmed_days": self.unconfirmed_days,
            "confirmation_count": self.confirmation_count,
            "helpful_feedback_count": self.helpful_feedback_count,
            "stable": self.stable,
            "should_mark_outdated": self.should_mark_outdated,
            "retrieval_multiplier": self.retrieval_multiplier,
            "reason": self.reason,
            "recommendation": self.recommendation,
        }


def knowledge_aging_policy():
    """Return the active knowledge aging policy from configuration."""
    return KnowledgeAgingPolicy(
        stale_days=_positive_int_config("KNOWLEDGE_AGING_STALE_DAYS", DEFAULT_STALE_DAYS),
        unconfirmed_days=_positive_int_config(
            "KNOWLEDGE_AGING_UNCONFIRMED_DAYS",
            DEFAULT_UNCONFIRMED_DAYS,
        ),
        stable_confirmations=_positive_int_config(
            "KNOWLEDGE_AGING_STABLE_CONFIRMATIONS",
            DEFAULT_STABLE_CONFIRMATIONS,
        ),
        stable_helpful_feedback=_positive_int_config(
            "KNOWLEDGE_AGING_STABLE_HELPFUL_FEEDBACK",
            DEFAULT_STABLE_HELPFUL_FEEDBACK,
        ),
        outdated_multiplier=_bounded_float_config(
            "RAG_AGING_OUTDATED_MULTIPLIER",
            DEFAULT_OUTDATED_MULTIPLIER,
        ),
        stale_multiplier=_bounded_float_config(
            "RAG_AGING_STALE_MULTIPLIER",
            DEFAULT_STALE_MULTIPLIER,
        ),
        old_multiplier=_bounded_float_config(
            "RAG_AGING_OLD_MULTIPLIER",
            DEFAULT_OLD_MULTIPLIER,
        ),
    )


def knowledge_aging_state(document, now=None, include_feedback=True):
    """Return aging state for one knowledge document without mutating it."""
    policy = knowledge_aging_policy()
    now_value = _utc_naive(now or utc_now())
    quality_status = str(getattr(document, "quality_status", "") or "").strip()
    status = str(getattr(document, "status", "") or "").strip()
    age_days = _days_since(getattr(document, "updated_at", None), now_value)
    last_confirmed_at = getattr(document, "last_confirmed_at", None)
    confirmation_anchor = last_confirmed_at or getattr(document, "created_at", None)
    unconfirmed_days = _days_since(confirmation_anchor, now_value)
    confirmation_count = max(0, int(getattr(document, "confirmation_count", 0) or 0))
    helpful_count = helpful_feedback_count_for_document(document) if include_feedback else 0
    stable = (
        confirmation_count >= policy.stable_confirmations
        or helpful_count >= policy.stable_helpful_feedback
    )
    reason = _aging_reason(
        status=status,
        quality_status=quality_status,
        stable=stable,
        age_days=age_days,
        unconfirmed_days=unconfirmed_days,
        policy=policy,
    )
    should_mark_outdated = _should_mark_outdated(
        status=status,
        quality_status=quality_status,
        stable=stable,
        age_days=age_days,
        unconfirmed_days=unconfirmed_days,
        policy=policy,
    )
    multiplier = _retrieval_multiplier(
        status=status,
        quality_status=quality_status,
        should_mark_outdated=should_mark_outdated,
        reason=reason,
        stable=stable,
        policy=policy,
    )
    return KnowledgeAgingState(
        document_id=getattr(document, "id", None),
        quality_status=quality_status,
        status=status,
        age_days=age_days,
        unconfirmed_days=unconfirmed_days,
        confirmation_count=confirmation_count,
        helpful_feedback_count=helpful_count,
        stable=stable,
        should_mark_outdated=should_mark_outdated,
        retrieval_multiplier=multiplier,
        reason=reason,
        recommendation=_review_recommendation(reason, should_mark_outdated),
    )


def retrieval_aging_signal(document):
    """Return the retrieval aging state optimized for scoring performance."""
    return knowledge_aging_state(document, include_feedback=False)


def record_knowledge_confirmation(document, now=None):
    """Record a human confirmation event on a knowledge document."""
    if not document:
        return
    timestamp = now or utc_now()
    document.last_confirmed_at = timestamp
    document.confirmation_count = int(document.confirmation_count or 0) + 1
    document.aging_checked_at = timestamp


def mark_outdated_knowledge_by_age(dry_run=False, limit=None, now=None):
    """Mark aging knowledge documents as outdated without deleting content."""
    now_value = now or utc_now()
    documents = _aging_candidate_documents(limit=limit)
    candidates = []
    for document in documents:
        state = knowledge_aging_state(document, now=now_value)
        if not state.should_mark_outdated:
            continue
        candidates.append((document, state))
        if dry_run:
            continue
        previous_updated_at = document.updated_at
        document.quality_status = "outdated"
        document.aging_checked_at = now_value
        document.updated_at = previous_updated_at

    if not dry_run:
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("knowledge_aging_mark_outdated_failed")
            raise

    return {
        "documents": len(candidates),
        "dry_run": bool(dry_run),
        "recommendations": [
            _recommendation_payload(document, state) for document, state in candidates[:10]
        ],
    }


def knowledge_aging_summary(documents=None):
    """Return aggregate aging counters for lifecycle diagnostics."""
    document_states = [
        (document, knowledge_aging_state(document)) for document in _document_items(documents)
    ]
    states = [state for _document, state in document_states]
    return {
        "enabled": True,
        "stale_candidates": sum(1 for state in states if state.should_mark_outdated),
        "stable_documents": sum(1 for state in states if state.stable),
        "weighted_documents": sum(1 for state in states if 0 < state.retrieval_multiplier < 1),
        "outdated_documents": sum(1 for state in states if state.quality_status == "outdated"),
        "review_recommendations": [
            _recommendation_payload(document, state)
            for document, state in document_states
            if state.should_mark_outdated
        ][:10],
        "policy": knowledge_aging_policy().__dict__,
    }


def helpful_feedback_count_for_document(document):
    """Return helpful feedback references for one knowledge document."""
    document_id = getattr(document, "id", None)
    if not document_id or not has_app_context():
        return 0
    limit = _positive_int_config("RAG_FEEDBACK_SCAN_LIMIT", DEFAULT_FEEDBACK_SCAN_LIMIT)
    feedback_items = AIFeedback.query.order_by(AIFeedback.created_at.desc()).limit(limit).all()
    count = 0
    for feedback in feedback_items:
        if feedback.rating not in {"helpful", "partially_helpful"}:
            continue
        if any(_source_references_document(source, document_id) for source in feedback.sources()):
            count += 1
    return count


def _aging_candidate_documents(limit=None):
    """Return documents eligible for automatic aging review."""
    query = KnowledgeDocument.query.filter(
        KnowledgeDocument.quality_status.in_(AGING_CANDIDATE_QUALITY_STATUSES),
    ).order_by(KnowledgeDocument.updated_at.asc(), KnowledgeDocument.id.asc())
    if limit:
        query = query.limit(int(limit))
    return query.all()


def _document_items(documents):
    """Return provided documents or all knowledge documents."""
    if documents is None:
        return KnowledgeDocument.query.order_by(KnowledgeDocument.id.asc()).all()
    return list(documents)


def _should_mark_outdated(
    status,
    quality_status,
    stable,
    age_days,
    unconfirmed_days,
    policy,
):
    """Return whether a document should move to outdated for review."""
    if stable or quality_status in TERMINAL_QUALITY_STATUSES:
        return False
    if quality_status not in AGING_CANDIDATE_QUALITY_STATUSES:
        return False
    if status == "stale":
        return quality_status in REVIEWED_QUALITY_STATUSES
    if quality_status in REVIEWED_QUALITY_STATUSES:
        return unconfirmed_days >= policy.stale_days or age_days >= policy.stale_days
    return unconfirmed_days >= policy.unconfirmed_days


def _aging_reason(status, quality_status, stable, age_days, unconfirmed_days, policy):
    """Return a stable reason code for one aging state."""
    if stable:
        return "stable_repeatedly_confirmed"
    if quality_status == "outdated":
        return "already_outdated"
    if quality_status == "rejected":
        return "rejected_not_aged"
    if status == "stale":
        return "source_stale"
    if quality_status in REVIEWED_QUALITY_STATUSES and unconfirmed_days >= policy.stale_days:
        return "reviewed_confirmation_expired"
    if quality_status in REVIEWED_QUALITY_STATUSES and age_days >= policy.stale_days:
        return "reviewed_content_old"
    if quality_status in {"draft", "ai_suggested"} and unconfirmed_days >= policy.unconfirmed_days:
        return "unconfirmed_too_long"
    if age_days >= policy.stale_days:
        return "content_old"
    return "fresh"


def _retrieval_multiplier(
    status,
    quality_status,
    should_mark_outdated,
    reason,
    stable,
    policy,
):
    """Return how aging should influence retrieval scoring."""
    if quality_status == "rejected":
        return 0.0
    if stable:
        return 1.0
    if quality_status == "outdated" or should_mark_outdated:
        return policy.outdated_multiplier
    if status == "stale":
        return policy.stale_multiplier
    if reason in {"reviewed_content_old", "content_old", "unconfirmed_too_long"}:
        return policy.old_multiplier
    return 1.0


def _review_recommendation(reason, should_mark_outdated):
    """Return a compact review recommendation for an aging reason."""
    if should_mark_outdated:
        return "mark_outdated_for_review"
    if reason == "already_outdated":
        return "refresh_or_reconfirm"
    if reason == "source_stale":
        return "reindex_then_review"
    if reason == "stable_repeatedly_confirmed":
        return "none"
    return "none"


def _recommendation_payload(document, state):
    """Return one admin-facing aging recommendation."""
    return {
        "id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "quality_status": state.quality_status,
        "status": state.status,
        "age_days": state.age_days,
        "unconfirmed_days": state.unconfirmed_days,
        "confirmation_count": state.confirmation_count,
        "helpful_feedback_count": state.helpful_feedback_count,
        "reason": state.reason,
        "recommendation": state.recommendation,
        "retrieval_multiplier": state.retrieval_multiplier,
    }


def _source_references_document(source, document_id):
    """Return whether a feedback source points to a knowledge document."""
    if not isinstance(source, dict):
        return False
    if str(source.get("type") or "") != "knowledge":
        return False
    try:
        return int(source.get("id")) == int(document_id)
    except (TypeError, ValueError):
        return False


def _days_since(value, now_value):
    """Return whole UTC days since a stored datetime value."""
    if not value:
        return 0
    current = _utc_naive(value)
    return max(0, (now_value - current).days)


def _utc_naive(value):
    """Return a timezone-free UTC datetime for safe comparisons."""
    if value.tzinfo:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _positive_int_config(name, default):
    """Return a positive integer config value."""
    value = current_app.config.get(name, default) if has_app_context() else default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _bounded_float_config(name, default):
    """Return a float config value clamped to the retrieval multiplier range."""
    value = current_app.config.get(name, default) if has_app_context() else default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))
