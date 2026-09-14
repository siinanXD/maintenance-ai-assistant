"""Retrieved sources of one golden query, reduced to safe metadata and search text."""

from app.extensions import db
from app.models import ErrorEntry, MaintenancePlan, ShiftHandover, Task
from app.services.retrieval_evaluation_common import (
    RETRIEVAL_MODE_FULL,
    chunk_block_kinds,
    normalized_strings,
    optional_int,
    safe_created_at,
)
from app.services.retrieval_service import retrieve_context, retrieve_vector_chunks


def build_retrieved_sources(golden_query, user, top_k, retrieval_mode):
    """Return retrieved source payloads for the selected evaluation mode."""
    if retrieval_mode == RETRIEVAL_MODE_FULL:
        retrieval = retrieve_context(golden_query.query, user)
        sources = (retrieval.get("sources") or [])[:top_k]
        return [
            _retrieved_public_source(source, rank=index + 1) for index, source in enumerate(sources)
        ]
    results = retrieve_vector_chunks(golden_query.query, user, limit=top_k)
    return [
        _retrieved_vector_source(result, rank=index + 1) for index, result in enumerate(results)
    ]


def _retrieved_public_source(source, rank):
    """Return a compact source payload from one public retrieval source."""
    metadata = dict(source or {})
    title = str(metadata.get("title") or "")
    payload = {
        "rank": rank,
        "source_id": optional_int(metadata.get("id")),
        "source_type": str(metadata.get("type") or ""),
        "metadata_source_id": optional_int(metadata.get("source_id")),
        "metadata_source_type": str(metadata.get("source_type") or ""),
        "source_record_id": optional_int(metadata.get("source_record_id")),
        "chunk_id": optional_int(metadata.get("chunk_id")),
        "title": title,
        "content": _source_search_excerpt(
            _public_source_search_text(metadata, fallback_text=title)
        ),
        "score": round(float(metadata.get("score", 0.0) or 0.0), 4),
        "quality_status": metadata.get("quality_status"),
    }
    payload.update(_retrieved_safe_source_metadata(metadata))
    payload.update(_retrieved_chunk_metadata(metadata))
    return payload


def _public_source_search_text(metadata, fallback_text=""):
    """Return in-memory keyword text for a public retrieval source."""
    source_types = {
        str(metadata.get("type") or ""),
        str(metadata.get("source_type") or ""),
    }
    if "task" in source_types:
        return " ".join(
            part
            for part in (
                fallback_text,
                _task_search_text(metadata),
            )
            if str(part or "").strip()
        )
    if source_types & {"error", "error_entry"}:
        return " ".join(
            part
            for part in (
                fallback_text,
                _error_entry_search_text(metadata),
            )
            if str(part or "").strip()
        )
    if "maintenance_plan" in source_types:
        return " ".join(
            part
            for part in (
                fallback_text,
                _maintenance_plan_search_text(metadata),
            )
            if str(part or "").strip()
        )
    if "shift_handover" in source_types:
        return " ".join(
            part
            for part in (
                fallback_text,
                _shift_handover_search_text(metadata),
            )
            if str(part or "").strip()
        )
    return str(fallback_text or "")


def _task_search_text(metadata):
    """Return searchable task text for full retrieval keyword checks."""
    task_id = _public_record_id(metadata, "task")
    if not task_id:
        return ""
    task = db.session.get(Task, task_id)
    if not task:
        return ""
    return " ".join(
        str(part or "").strip()
        for part in (
            task.title,
            task.description,
            task.blocked_reason,
            task.status.value if task.status else "",
            task.priority.value if task.priority else "",
            task.due_date.isoformat() if task.due_date else "",
            task.department.name if task.department else "",
        )
        if str(part or "").strip()
    )


def _error_entry_search_text(metadata):
    """Return searchable error-entry text for full retrieval keyword checks."""
    entry_id = _public_record_id(metadata, "error", "error_entry")
    if not entry_id:
        return ""
    entry = db.session.get(ErrorEntry, entry_id)
    if not entry:
        return ""
    return " ".join(
        str(part or "").strip()
        for part in (
            entry.machine,
            entry.error_code,
            entry.title,
            entry.description,
            entry.symptoms,
            entry.possible_causes,
            entry.solution,
            entry.status,
            entry.severity,
            entry.cause_category,
            entry.impact,
            entry.department.name if entry.department else "",
        )
        if str(part or "").strip()
    )


def _maintenance_plan_search_text(metadata):
    """Return searchable maintenance-plan text for evaluation keyword metrics."""
    plan_id = _public_record_id(metadata, "maintenance_plan")
    if not plan_id:
        return ""
    plan = db.session.get(MaintenancePlan, plan_id)
    if not plan:
        return ""
    return " ".join(
        str(part or "").strip()
        for part in (
            plan.title,
            plan.description,
            plan.priority.value if plan.priority else "",
            plan.next_due_date.isoformat() if plan.next_due_date else "",
            plan.department.name if plan.department else "",
            plan.machine.name if plan.machine else "",
            "aktiv" if plan.is_active else "inaktiv",
        )
        if str(part or "").strip()
    )


def _shift_handover_search_text(metadata):
    """Return searchable shift-handover text for evaluation keyword metrics."""
    handover_id = _public_record_id(metadata, "shift_handover")
    if not handover_id:
        return ""
    handover = db.session.get(ShiftHandover, handover_id)
    if not handover:
        return ""
    return " ".join(
        str(part or "").strip()
        for part in (
            handover.department,
            handover.area,
            handover.shift_type,
            handover.status,
            handover.content,
            handover.open_tasks,
            handover.machine_notes,
            handover.next_notes,
            handover.safety_notes,
            handover.material_notes,
            handover.cause,
            handover.action_taken,
            handover.follow_up_task,
        )
        if str(part or "").strip()
    )


def _public_record_id(metadata, *source_types):
    """Return the best matching record id from a public retrieval source."""
    expected_types = set(normalized_strings(source_types))
    public_source_type = str(metadata.get("type") or "")
    metadata_source_type = str(metadata.get("source_type") or "")
    public_source_id = optional_int(metadata.get("id"))
    metadata_source_id = optional_int(metadata.get("source_id"))
    source_record_id = optional_int(metadata.get("source_record_id"))
    if metadata_source_type in expected_types:
        return metadata_source_id or source_record_id or public_source_id
    if public_source_type in expected_types:
        return public_source_id or source_record_id or metadata_source_id
    return source_record_id or metadata_source_id or public_source_id


def _retrieved_vector_source(result, rank):
    """Return a compact source payload from one vector result."""
    metadata = dict(getattr(result, "metadata", {}) or {})
    source_type = str(metadata.get("source_type") or metadata.get("document_type") or "")
    payload = {
        "rank": rank,
        "source_id": optional_int(metadata.get("id")),
        "source_type": source_type,
        "metadata_source_id": optional_int(metadata.get("source_id")),
        "metadata_source_type": source_type,
        "source_record_id": optional_int(metadata.get("source_id")),
        "chunk_id": optional_int(metadata.get("chunk_id")),
        "title": str(metadata.get("title") or ""),
        "content": _source_search_excerpt(getattr(result, "text", "") or ""),
        "score": round(float(getattr(result, "score", 0.0) or 0.0), 4),
        "quality_status": metadata.get("quality_status"),
    }
    payload.update(_retrieved_safe_source_metadata(metadata))
    payload.update(_retrieved_chunk_metadata(metadata))
    return payload


def _retrieved_safe_source_metadata(metadata):
    """Return prompt-safe source metadata fields for evaluation diagnostics."""
    return {
        "module": str(metadata.get("module") or "")[:80],
        "machine_id": optional_int(metadata.get("machine_id")),
        "role_visibility": str(metadata.get("role_visibility") or "")[:160],
        "created_at": safe_created_at(metadata.get("created_at")),
    }


def _retrieved_chunk_metadata(metadata):
    """Return prompt-safe chunk segmentation metadata for evaluation output."""
    return {
        "chunk_char_count": optional_int(metadata.get("chunk_char_count")),
        "chunk_line_count": optional_int(metadata.get("chunk_line_count")),
        "chunk_token_count": optional_int(metadata.get("chunk_token_count")),
        "chunk_block_count": optional_int(metadata.get("chunk_block_count")),
        "chunk_block_kinds": chunk_block_kinds(metadata.get("chunk_block_kinds")),
        "chunking_mode": str(metadata.get("chunking_mode") or "")[:80],
        "section_title": str(metadata.get("section_title") or "")[:180],
    }


def collect_source_ids(source):
    """Return all safe public and metadata source IDs for matching."""
    return {
        source.get("source_id"),
        source.get("metadata_source_id"),
        source.get("source_record_id"),
    } - {None}


def collect_source_types(source):
    """Return all safe public and metadata source types for matching."""
    return {
        str(source.get("source_type") or ""),
        str(source.get("metadata_source_type") or ""),
    } - {""}


def source_role_visibility(source):
    """Return prompt-safe role visibility labels for permission checks."""
    return {
        str(source.get("role_visibility") or ""),
        str(source.get("metadata_role_visibility") or ""),
    } - {""}


def _source_search_excerpt(text):
    """Return bounded retrieved text for in-memory evaluation keyword checks."""
    return str(text or "").strip()[:1000]
