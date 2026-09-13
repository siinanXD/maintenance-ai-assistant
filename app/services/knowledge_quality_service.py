"""Quality-status workflow for AI knowledge documents."""

import logging
from dataclasses import dataclass

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import Role, utc_now
from app.extensions import db

logger = logging.getLogger(__name__)

KNOWLEDGE_QUALITY_STATUSES = {
    "draft",
    "ai_suggested",
    "technician_confirmed",
    "admin_approved",
    "low_quality",
    "duplicate",
    "outdated",
    "rejected",
}
AI_SUGGESTED_SOURCE_TYPES = {"generated_document"}
TECHNICIAN_STATUSES = {
    "technician_confirmed",
    "low_quality",
    "duplicate",
    "outdated",
}
MANUAL_REVIEWED_STATUSES = {
    "technician_confirmed",
    "admin_approved",
    "outdated",
    "rejected",
}


@dataclass(frozen=True)
class RetrievalQualityGate:
    """Describe how a knowledge quality status affects retrieval."""

    status: str
    allowed: bool
    score_multiplier: float
    reason: str


RETRIEVAL_QUALITY_GATES = {
    "admin_approved": RetrievalQualityGate(
        status="admin_approved",
        allowed=True,
        score_multiplier=1.0,
        reason="admin_approved",
    ),
    "technician_confirmed": RetrievalQualityGate(
        status="technician_confirmed",
        allowed=True,
        score_multiplier=1.0,
        reason="technician_confirmed",
    ),
    "ai_suggested": RetrievalQualityGate(
        status="ai_suggested",
        allowed=True,
        score_multiplier=0.45,
        reason="ai_suggested_weighted",
    ),
    "outdated": RetrievalQualityGate(
        status="outdated",
        allowed=True,
        score_multiplier=0.35,
        reason="outdated_weighted",
    ),
    "low_quality": RetrievalQualityGate(
        status="low_quality",
        allowed=True,
        score_multiplier=0.08,
        reason="low_quality_strongly_weighted",
    ),
    "duplicate": RetrievalQualityGate(
        status="duplicate",
        allowed=True,
        score_multiplier=0.05,
        reason="duplicate_strongly_weighted",
    ),
    "draft": RetrievalQualityGate(
        status="draft",
        allowed=True,
        score_multiplier=0.15,
        reason="draft_strongly_weighted",
    ),
    "rejected": RetrievalQualityGate(
        status="rejected",
        allowed=False,
        score_multiplier=0.0,
        reason="rejected_blocked",
    ),
}
UNKNOWN_RETRIEVAL_QUALITY_GATE = RetrievalQualityGate(
    status="unknown",
    allowed=False,
    score_multiplier=0.0,
    reason="unknown_quality_status_blocked",
)
STRICT_ALLOWED_QUALITY_STATUSES = {"admin_approved", "technician_confirmed"}


def default_quality_status_for_source(source_type):
    """Return the initial quality status for a knowledge source type."""
    if str(source_type or "").strip() in AI_SUGGESTED_SOURCE_TYPES:
        return "ai_suggested"
    return "draft"


def retrieval_quality_gate_for_status(status):
    """Return the retrieval gate rule for a quality status."""
    normalized_status = str(status or "").strip().lower()
    gate = RETRIEVAL_QUALITY_GATES.get(
        normalized_status,
        UNKNOWN_RETRIEVAL_QUALITY_GATE,
    )
    if _strict_quality_gate_enabled() and normalized_status not in STRICT_ALLOWED_QUALITY_STATUSES:
        return RetrievalQualityGate(
            status=gate.status,
            allowed=False,
            score_multiplier=0.0,
            reason="strict_quality_gate_blocked",
        )
    return gate


def retrieval_quality_gate_for_document(document):
    """Return the retrieval gate rule for a knowledge document."""
    if document is None:
        return UNKNOWN_RETRIEVAL_QUALITY_GATE
    return retrieval_quality_gate_for_status(getattr(document, "quality_status", ""))


def automatic_quality_status_from_chunk_report(document, report):
    """Return a safe automatic quality status suggestion after indexing."""
    current_status = normalize_existing_quality_status(
        getattr(document, "quality_status", None),
        getattr(document, "source_type", ""),
    )
    if current_status in MANUAL_REVIEWED_STATUSES:
        return current_status
    if report is None or int(getattr(report, "total_chunks_seen", 0) or 0) <= 0:
        return current_status
    accepted_chunks = int(getattr(report, "accepted_chunks", 0) or 0)
    duplicate_chunks = int(getattr(report, "skipped_duplicate_chunks", 0) or 0)
    low_quality_chunks = int(getattr(report, "skipped_low_quality_chunks", 0) or 0)
    bad_ocr_chunks = int(getattr(report, "skipped_bad_ocr_chunks", 0) or 0)
    empty_chunks = int(getattr(report, "skipped_empty_chunks", 0) or 0)
    short_chunks = int(getattr(report, "skipped_short_chunks", 0) or 0)
    total_rejected = duplicate_chunks + low_quality_chunks

    if accepted_chunks <= 0 and duplicate_chunks and not low_quality_chunks:
        return "duplicate"
    if accepted_chunks <= 0 and total_rejected:
        return "low_quality"
    if bad_ocr_chunks:
        return "low_quality"
    if duplicate_chunks >= max(2, accepted_chunks) and low_quality_chunks <= duplicate_chunks:
        return "duplicate"
    if (empty_chunks + short_chunks) >= max(2, accepted_chunks * 2):
        return "low_quality"
    return current_status


def change_knowledge_quality_status(document, requested_status, user):
    """Persist a validated quality-status transition for a knowledge document."""
    try:
        next_status = normalize_quality_status(requested_status)
        validate_quality_status_permission(document, next_status, user)
        previous_status = document.quality_status or default_quality_status_for_source(
            document.source_type
        )
        document.quality_status = next_status
        if next_status in {"technician_confirmed", "admin_approved"}:
            from app.services.knowledge_aging_service import record_knowledge_confirmation

            record_knowledge_confirmation(document)
        document.updated_at = utc_now()
        db.session.commit()
        logger.info(
            "knowledge_quality_status_changed document_id=%s from=%s to=%s user_id=%s",
            document.id,
            previous_status,
            next_status,
            getattr(user, "id", None),
        )
        return document.to_dict(), None, 200
    except ValueError as exc:
        db.session.rollback()
        return None, {"error": str(exc)}, 400
    except PermissionError as exc:
        db.session.rollback()
        return None, {"error": str(exc)}, 403
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception(
            "knowledge_quality_status_update_failed document_id=%s user_id=%s",
            getattr(document, "id", None),
            getattr(user, "id", None),
        )
        return None, {"error": "Database error while updating knowledge quality status"}, 500


def normalize_quality_status(value):
    """Return a normalized supported quality status or raise ValueError."""
    status = str(value or "").strip().lower()
    if status not in KNOWLEDGE_QUALITY_STATUSES:
        valid = ", ".join(sorted(KNOWLEDGE_QUALITY_STATUSES))
        raise ValueError(f"quality_status must be one of: {valid}")
    return status


def normalize_existing_quality_status(value, source_type=""):
    """Return a supported current quality status without raising."""
    status = str(value or "").strip().lower()
    if status in KNOWLEDGE_QUALITY_STATUSES:
        return status
    return default_quality_status_for_source(source_type)


def validate_quality_status_permission(document, requested_status, user):
    """Raise PermissionError when a user cannot assign the requested status."""
    if not user:
        raise PermissionError("Forbidden")
    if requested_status == "admin_approved" and user.role != Role.MASTER_ADMIN:
        raise PermissionError("Only master admins may approve knowledge entries")
    if user.role == Role.MASTER_ADMIN:
        return
    if user.role == Role.INSTANDHALTUNG and requested_status in TECHNICIAN_STATUSES:
        if _same_department_or_unscoped(document, user):
            return
        raise PermissionError("Technicians may only update knowledge for their department")
    raise PermissionError("Forbidden")


def mark_quality_outdated_if_reviewed(document):
    """Mark previously reviewed knowledge as outdated after source content changes."""
    if not document:
        return
    if document.quality_status in {"technician_confirmed", "admin_approved"}:
        document.quality_status = "outdated"


def _same_department_or_unscoped(document, user):
    """Return whether a document is unscoped or belongs to the user's department."""
    document_department = str(getattr(document, "department", "") or "").strip().lower()
    if not document_department:
        return True
    user_department = ""
    if getattr(user, "department", None):
        user_department = str(user.department.name or "").strip().lower()
    return document_department == user_department


def _strict_quality_gate_enabled():
    """Return whether only reviewed knowledge may be retrieved."""
    if has_app_context():
        return bool(current_app.config.get("RAG_STRICT_QUALITY_GATE", False))
    return False
