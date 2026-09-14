"""Knowledge-gap tracking for unanswered or low-confidence AI responses."""

import hashlib
import logging
import re
from datetime import timedelta

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import KnowledgeDocument, KnowledgeGap, Machine
from app.services.knowledge_gap_actions import knowledge_gap_actions
from app.services.knowledge_gap_rows import (
    department_gap_rows,
    error_gap_rows,
    gap_detection_summary,
    gap_terms,
    machine_gap_rows,
    numeric_score,
    uncovered_error_gap_rows,
    uncovered_machine_gap_rows,
)

logger = logging.getLogger(__name__)


TRACKED_RESPONSE_TYPES = {"agent"}


# Only retrieval-backed answers can reveal missing knowledge; general model
# answers and structured data lists never create gap entries.
TRACKED_ANSWER_CATEGORIES = {"rag"}


GAP_STATUSES = {"api_key_missing", "openai_error", "fallback_used"}


DEFAULT_DEDUP_HOURS = 24


DEFAULT_LOW_CONFIDENCE_SCORE = 35


def maybe_track_knowledge_gap(question, user, result):
    """Persist a knowledge gap when an AI result has no reliable source context."""
    if not should_track_gap(result):
        return None

    try:
        gap, created = upsert_knowledge_gap(question, user, result)
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        logger.exception("knowledge_gap_persist_failed user_id=%s", getattr(user, "id", None))
        return None

    payload = gap.to_dict()
    payload["created"] = created
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["knowledge_gap_id"] = gap.id
    diagnostics["knowledge_gap_created"] = created
    result["knowledge_gap"] = payload
    return payload


def should_track_gap(result):
    """Return whether a chat result should create a knowledge-gap entry."""
    if not isinstance(result, dict):
        return False
    if result.get("type") not in TRACKED_RESPONSE_TYPES:
        return False

    diagnostics = result.get("diagnostics") or {}
    sources = result.get("sources") or []
    if diagnostics.get("status") in GAP_STATUSES or diagnostics.get("fallback_used"):
        return True
    answer_category = result.get("answer_category") or diagnostics.get("answer_category")
    if answer_category not in TRACKED_ANSWER_CATEGORIES:
        return False
    if not sources:
        return True

    knowledge_sources = [source for source in sources if source.get("type") == "knowledge"]
    if not knowledge_sources:
        return False

    scores = [numeric_score(source.get("score")) for source in knowledge_sources]
    known_scores = [score for score in scores if score is not None]
    if not known_scores:
        return False
    return max(known_scores) < low_confidence_score()


def upsert_knowledge_gap(question, user, result):
    """Create or update a recent open knowledge gap for the same normalized question."""
    normalized = normalize_question(question)
    question_hash = hash_question(normalized)
    now = utc_now()
    department = department_name(user)
    existing = recent_open_gap(question_hash, department, now)
    context_text = build_gap_context(result)
    machine = detect_machine(question)

    if existing:
        existing.last_seen_at = now
        existing.updated_at = now
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.context_text = context_text or existing.context_text
        existing.machine = machine or existing.machine
        existing.audit_event_id = (result.get("diagnostics") or {}).get("audit_event_id")
        db.session.commit()
        return existing, False

    gap = KnowledgeGap(
        question=str(question or "").strip()[:4000],
        question_hash=question_hash,
        context_text=context_text,
        machine=machine,
        department=department,
        status="open",
        occurrence_count=1,
        user_id=getattr(user, "id", None),
        audit_event_id=(result.get("diagnostics") or {}).get("audit_event_id"),
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )
    db.session.add(gap)
    db.session.commit()
    return gap, True


def recent_open_gap(question_hash, department, now):
    """Return a recent open gap with the same question hash and department."""
    cutoff = now - timedelta(hours=dedup_hours())
    query = KnowledgeGap.query.filter(
        KnowledgeGap.question_hash == question_hash,
        KnowledgeGap.status == "open",
        KnowledgeGap.last_seen_at >= cutoff,
    )
    if department:
        query = query.filter(KnowledgeGap.department == department)
    return query.order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc()).first()


def list_knowledge_gaps(args):
    """Return filtered knowledge-gap entries for admin views."""
    query = KnowledgeGap.query
    status = str(args.get("status") or "").strip()
    q = str(args.get("q") or "").strip()
    if status:
        query = query.filter(KnowledgeGap.status == status)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (KnowledgeGap.question.ilike(pattern))
            | (KnowledgeGap.context_text.ilike(pattern))
            | (KnowledgeGap.machine.ilike(pattern))
            | (KnowledgeGap.department.ilike(pattern))
        )
    return query.order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc())


def knowledge_gap_detection(args=None):
    """Return structured knowledge-gap clusters and coverage recommendations."""
    args = args or {}
    limit = _bounded_int(args.get("limit"), 20, 1, 100)
    gaps = (
        list_knowledge_gaps({**args, "status": args.get("status") or "open"})
        .limit(
            limit,
        )
        .all()
    )
    documents = KnowledgeDocument.query.filter(
        KnowledgeDocument.status.in_(("indexed", "ready", "processed")),
    ).all()
    error_gaps = error_gap_rows(gaps, documents)
    uncovered_error_gaps = uncovered_error_gap_rows(documents)
    uncovered_machine_gaps = uncovered_machine_gap_rows(documents)
    return {
        "summary": gap_detection_summary(
            gaps,
            error_gaps,
            uncovered_error_gaps,
            uncovered_machine_gaps,
        ),
        "machine_gaps": machine_gap_rows(gaps, documents),
        "uncovered_machine_gaps": uncovered_machine_gaps,
        "error_gaps": error_gaps,
        "uncovered_error_gaps": uncovered_error_gaps,
        "department_gaps": department_gap_rows(gaps),
        "frequent_terms": gap_terms(gaps),
        "knowledge_gap_actions": knowledge_gap_actions(
            gaps,
            documents,
            error_gaps,
            uncovered_error_gaps,
            uncovered_machine_gaps,
        ),
    }


def build_gap_context(result):
    """Build a compact admin-facing context string for a low-confidence answer."""
    diagnostics = result.get("diagnostics") or {}
    sources = result.get("sources") or []
    source_titles = ", ".join(str(source.get("title") or "") for source in sources[:3])
    parts = [
        f"Antworttyp: {result.get('type') or 'assistant'}",
        f"Diagnostics: {diagnostics.get('status') or 'unknown'}",
        f"Fallback: {bool(diagnostics.get('fallback_used'))}",
        f"Quellen: {len(sources)}",
    ]
    if source_titles:
        parts.append(f"Beste Quellen: {source_titles}")
    return " | ".join(parts)[:4000]


def detect_machine(question):
    """Return a machine name detected from known machines or simple wording."""
    text = str(question or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for machine in Machine.query.order_by(Machine.name.asc()).limit(200).all():
        if machine.name and machine.name.lower() in lowered:
            return machine.name[:160]
    match = re.search(r"\b(?:maschine|anlage)\s+([a-zA-Z0-9_-]+)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0)[:160]


def department_name(user):
    """Return the user's department name when available."""
    department = getattr(user, "department", None)
    return (department.name if department else "")[:120]


def normalize_question(question):
    """Return a normalized question string for duplicate detection."""
    return re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", str(question or "").lower()).strip()


def hash_question(normalized_question):
    """Return a stable short hash for a normalized question."""
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


def dedup_hours():
    """Return the duplicate detection window in hours."""
    if not has_app_context():
        return DEFAULT_DEDUP_HOURS
    try:
        value = int(current_app.config.get("KNOWLEDGE_GAP_DEDUP_HOURS", DEFAULT_DEDUP_HOURS))
    except (TypeError, ValueError):
        return DEFAULT_DEDUP_HOURS
    return max(1, value)


def low_confidence_score():
    """Return the minimum acceptable source score before tracking a gap."""
    if not has_app_context():
        return DEFAULT_LOW_CONFIDENCE_SCORE
    try:
        value = int(
            current_app.config.get(
                "KNOWLEDGE_GAP_LOW_CONFIDENCE_SCORE",
                DEFAULT_LOW_CONFIDENCE_SCORE,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_LOW_CONFIDENCE_SCORE
    return max(0, value)


def _bounded_int(value, default, minimum, maximum):
    """Return an integer constrained to a safe range."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))
