"""Background job queue services for asynchronous maintenance workflows."""

import json
import logging
from datetime import timedelta

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import BackgroundJob, KnowledgeDocument
from app.services.knowledge_aging_service import mark_outdated_knowledge_by_age
from app.services.knowledge_service import (
    reindex_all_knowledge,
    reindex_knowledge_document,
    reindex_stale_knowledge,
    resync_atlas_knowledge,
)
from app.services.payload_parsing_service import parse_bool

logger = logging.getLogger(__name__)

JOB_RAG_REINDEX = "rag_reindex"
JOB_ATLAS_RESYNC = "atlas_resync"
JOB_KNOWLEDGE_AGING = "knowledge_aging"
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
RETRYING_STATUSES = (QUEUED,)
ACTIVE_STATUSES = (RUNNING,)
DEFAULT_JOB_LEASE_SECONDS = 900


def enqueue_rag_reindex_job(mode="stale", document_id=None, user=None):
    """Queue a RAG reindex job and return the persisted job."""
    normalized_mode = validate_reindex_mode(mode, document_id)
    payload = {"mode": normalized_mode}
    if document_id is not None:
        payload["document_id"] = int(document_id)
    existing = existing_active_job(JOB_RAG_REINDEX, payload)
    if existing:
        _log_deduplicated_job(existing, payload)
        return existing
    job = _create_background_job(JOB_RAG_REINDEX, payload, user)
    logger.info("background_job_queued id=%s type=%s payload=%s", job.id, job.job_type, payload)
    return job


def enqueue_atlas_resync_job(mode="drift_only", user=None):
    """Queue an Atlas-only vector resync job and return the persisted job."""
    payload = validate_atlas_resync_payload(mode=mode)
    existing = existing_active_job(JOB_ATLAS_RESYNC, payload)
    if existing:
        _log_deduplicated_job(existing, payload)
        return existing
    job = _create_background_job(JOB_ATLAS_RESYNC, payload, user)
    logger.info("background_job_queued id=%s type=%s payload=%s", job.id, job.job_type, payload)
    return job


def enqueue_knowledge_aging_job(dry_run=False, limit=None, user=None):
    """Queue a knowledge aging review job and return the persisted job."""
    payload = validate_knowledge_aging_payload(dry_run=dry_run, limit=limit)
    existing = existing_active_job(JOB_KNOWLEDGE_AGING, payload)
    if existing:
        _log_deduplicated_job(existing, payload)
        return existing
    job = _create_background_job(JOB_KNOWLEDGE_AGING, payload, user)
    logger.info("background_job_queued id=%s type=%s payload=%s", job.id, job.job_type, payload)
    return job


def _create_background_job(job_type, payload, user=None):
    """Persist one queued background job with a normalized payload."""
    job = BackgroundJob(
        job_type=job_type,
        status=QUEUED,
        payload_json=json.dumps(payload, sort_keys=True),
        result_json="{}",
        error_message="",
        created_by=getattr(user, "id", None),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.session.add(job)
    db.session.commit()
    return job


def existing_active_job(job_type, payload):
    """Return an already queued or running background job for the payload."""
    payload_json = json.dumps(payload, sort_keys=True)
    return (
        BackgroundJob.query.filter(
            BackgroundJob.job_type == job_type,
            BackgroundJob.status.in_((QUEUED, RUNNING)),
            BackgroundJob.payload_json == payload_json,
        )
        .order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc())
        .first()
    )


def validate_reindex_mode(mode, document_id=None):
    """Return a normalized RAG reindex mode or raise ValueError."""
    if document_id is not None:
        return "document"
    normalized = str(mode or "stale").strip().lower()
    if normalized not in {"all", "stale"}:
        raise ValueError("mode must be 'all' or 'stale'")
    return normalized


def validate_atlas_resync_payload(mode="drift_only"):
    """Return a normalized Atlas resync payload or raise ValueError."""
    normalized = str(mode or "drift_only").strip().lower()
    if normalized not in {"all", "drift_only"}:
        raise ValueError("mode must be 'all' or 'drift_only'")
    return {"mode": normalized}


def validate_knowledge_aging_payload(dry_run=False, limit=None):
    """Return a normalized knowledge aging job payload or raise ValueError."""
    payload = {
        "dry_run": parse_bool(
            dry_run,
            default=False,
            field_name="dry_run",
            empty_is_default=True,
        )
    }
    if limit not in (None, ""):
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be a positive integer") from exc
        if parsed_limit < 1:
            raise ValueError("limit must be a positive integer")
        payload["limit"] = parsed_limit
    return payload


def list_background_jobs(args):
    """Return a filtered background job query for admin views."""
    query = BackgroundJob.query
    job_type = str(args.get("job_type") or "").strip()
    status = str(args.get("status") or "").strip()
    if job_type:
        query = query.filter(BackgroundJob.job_type == job_type)
    if status:
        query = query.filter(BackgroundJob.status == status)
    return query.order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc())


def process_next_background_job():
    """Process the next queued job and return a worker summary."""
    recovered = requeue_expired_jobs()
    job = claim_next_queued_job()
    if not job:
        return {
            "processed": False,
            "reason": "no_queued_jobs",
            "recovered": recovered,
        }
    return process_background_job(job)


def claim_next_queued_job():
    """Atomically claim the oldest queued job for this worker process."""
    now = utc_now()
    query = BackgroundJob.query.filter(BackgroundJob.status.in_(RETRYING_STATUSES))
    if _supports_skip_locked():
        query = query.with_for_update(skip_locked=True)
    job = query.order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc()).first()
    if not job:
        return None

    job.status = RUNNING
    job.attempts += 1
    job.locked_at = now
    job.started_at = now
    job.error_message = ""
    job.updated_at = now
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("background_job_claim_failed")
        return None
    logger.info("background_job_claimed id=%s type=%s", job.id, job.job_type)
    return job


def requeue_expired_jobs():
    """Move running jobs with an expired lease back into the queue."""
    cutoff = utc_now() - timedelta(seconds=job_lease_seconds())
    jobs = (
        BackgroundJob.query.filter(
            BackgroundJob.status.in_(ACTIVE_STATUSES),
            BackgroundJob.locked_at.isnot(None),
            BackgroundJob.locked_at < cutoff,
        )
        .order_by(BackgroundJob.locked_at.asc(), BackgroundJob.id.asc())
        .all()
    )
    if not jobs:
        return 0

    now = utc_now()
    for job in jobs:
        job.status = QUEUED if job.attempts < job.max_attempts else FAILED
        job.locked_at = None
        job.started_at = None if job.status == QUEUED else job.started_at
        job.finished_at = now if job.status == FAILED else None
        job.error_message = "Job lease expired and was released for retry."
        job.updated_at = now
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("background_job_requeue_expired_failed")
        return 0
    logger.warning("background_jobs_requeued count=%s", len(jobs))
    return len(jobs)


def job_lease_seconds():
    """Return the worker job lease duration in seconds."""
    if not has_app_context():
        return DEFAULT_JOB_LEASE_SECONDS
    try:
        value = int(
            current_app.config.get(
                "WORKER_JOB_LEASE_SECONDS",
                DEFAULT_JOB_LEASE_SECONDS,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_JOB_LEASE_SECONDS
    return max(60, value)


def _supports_skip_locked():
    """Return whether the active database dialect supports skip-locked claims."""
    return db.engine.dialect.name == "postgresql"


def process_background_job(job):
    """Run one background job and persist its final state."""
    if job.status != RUNNING or not job.locked_at:
        job.status = RUNNING
        job.attempts += 1
        job.locked_at = utc_now()
        job.started_at = job.locked_at
        job.error_message = ""
        job.updated_at = utc_now()
        db.session.commit()
    try:
        result = execute_job(job)
    except Exception as exc:
        logger.exception("background_job_failed id=%s type=%s", job.id, job.job_type)
        mark_job_failed(job, exc)
        return {"processed": True, "job": job.to_dict()}

    job.status = DONE
    job.result_json = json.dumps(result)
    job.locked_at = None
    job.finished_at = utc_now()
    job.updated_at = utc_now()
    db.session.commit()
    logger.info("background_job_done id=%s type=%s", job.id, job.job_type)
    return {"processed": True, "job": job.to_dict()}


def execute_job(job):
    """Execute a supported background job and return its result payload."""
    if job.job_type == JOB_RAG_REINDEX:
        return execute_rag_reindex_job(job.payload())
    if job.job_type == JOB_ATLAS_RESYNC:
        return execute_atlas_resync_job(job.payload())
    if job.job_type == JOB_KNOWLEDGE_AGING:
        return execute_knowledge_aging_job(job.payload())
    raise ValueError(f"Unsupported background job type: {job.job_type}")


def execute_rag_reindex_job(payload):
    """Execute a RAG reindex job from a stored payload."""
    mode = validate_reindex_mode(payload.get("mode"), payload.get("document_id"))
    if mode == "document":
        document = db.session.get(KnowledgeDocument, int(payload["document_id"]))
        if not document:
            raise ValueError("Knowledge document not found")
        return reindex_knowledge_document(document)
    if mode == "all":
        return reindex_all_knowledge()
    return reindex_stale_knowledge()


def execute_atlas_resync_job(payload):
    """Execute an Atlas resync job from a stored payload."""
    normalized = validate_atlas_resync_payload(payload.get("mode"))
    return resync_atlas_knowledge(mode=normalized["mode"])


def execute_knowledge_aging_job(payload):
    """Execute a knowledge aging job from a stored payload."""
    normalized = validate_knowledge_aging_payload(
        dry_run=payload.get("dry_run", False),
        limit=payload.get("limit"),
    )
    return mark_outdated_knowledge_by_age(
        dry_run=normalized["dry_run"],
        limit=normalized.get("limit"),
    )


def mark_job_failed(job, exc):
    """Persist a failed job state with retry awareness."""
    job.error_message = str(exc)[:1000]
    job.status = QUEUED if job.attempts < job.max_attempts else FAILED
    job.locked_at = None
    if job.status == FAILED:
        job.finished_at = utc_now()
    else:
        job.started_at = None
        job.finished_at = None
    job.updated_at = utc_now()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("background_job_failure_persist_failed id=%s", job.id)


def _log_deduplicated_job(job, payload):
    """Log that an equivalent active background job already exists."""
    logger.info(
        "background_job_deduplicated id=%s type=%s payload=%s",
        job.id,
        job.job_type,
        payload,
    )
