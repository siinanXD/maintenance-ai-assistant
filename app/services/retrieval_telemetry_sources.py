"""Per-source retrieval usage and feedback: hits, poor sources, chunk usage and sizes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge_metadata_service import stored_chunk_metadata
from app.services.retrieval_telemetry_common import (
    NEGATIVE_RATINGS,
    PARTIAL_RATINGS,
    POSITIVE_RATINGS,
    average,
    bounded_string,
    chunk_block_kinds,
    counter_payload,
    db_get_knowledge_document,
    low_source_score,
    metadata_int_values,
    optional_float,
    optional_int,
)


@dataclass
class SourceTelemetry:
    """Aggregate retrieval usage and feedback for one source reference."""

    source_type: str
    source_id: int | None
    chunk_id: int | None
    title: str = ""
    source_record_id: int | None = None
    source_kind: str = ""
    knowledge_source_type: str = ""
    module: str = ""
    machine_id: int | None = None
    role_visibility: str = ""
    created_at: str = ""
    audit_uses: int = 0
    helpful_feedback: int = 0
    partially_helpful_feedback: int = 0
    not_helpful_feedback: int = 0
    low_score_uses: int = 0
    score_total: float = 0.0
    score_count: int = 0
    workflows: Counter = field(default_factory=Counter)
    quality_statuses: Counter = field(default_factory=Counter)

    @property
    def feedback_count(self):
        """Return total feedback count linked to this source."""
        return self.helpful_feedback + self.partially_helpful_feedback + self.not_helpful_feedback

    @property
    def average_score(self):
        """Return average retrieval score for this source."""
        if not self.score_count:
            return None
        return round(self.score_total / self.score_count, 2)

    @property
    def negative_rate(self):
        """Return negative feedback rate for this source."""
        if not self.feedback_count:
            return 0
        return round(self.not_helpful_feedback / self.feedback_count, 2)

    def add_score(self, score, low_score_threshold):
        """Add one retrieval score sample to this source."""
        numeric_score = optional_float(score)
        if numeric_score is None:
            return
        self.score_total += numeric_score
        self.score_count += 1
        if numeric_score <= low_score_threshold:
            self.low_score_uses += 1

    def add_feedback(self, rating):
        """Add one feedback rating to this source."""
        if rating in POSITIVE_RATINGS:
            self.helpful_feedback += 1
        elif rating in PARTIAL_RATINGS:
            self.partially_helpful_feedback += 1
        elif rating in NEGATIVE_RATINGS:
            self.not_helpful_feedback += 1

    def to_dict(self):
        """Return a prompt-safe telemetry payload for this source."""
        return {
            "type": self.source_type,
            "id": self.source_id,
            "chunk_id": self.chunk_id,
            "title": _source_title(self),
            "source_record_id": self.source_record_id,
            "source_kind": self.source_kind,
            "knowledge_source_type": self.knowledge_source_type,
            "module": self.module,
            "machine_id": self.machine_id,
            "role_visibility": self.role_visibility,
            "created_at": self.created_at,
            "audit_uses": self.audit_uses,
            "feedback_count": self.feedback_count,
            "helpful_feedback": self.helpful_feedback,
            "partially_helpful_feedback": self.partially_helpful_feedback,
            "not_helpful_feedback": self.not_helpful_feedback,
            "negative_rate": self.negative_rate,
            "low_score_uses": self.low_score_uses,
            "average_score": self.average_score,
            "top_workflows": counter_payload(self.workflows),
            "quality_status_counts": dict(self.quality_statuses),
        }


def source_telemetry(events, feedback_entries):
    """Return source telemetry keyed by type, document id and chunk id."""
    source_stats = {}
    low_score_threshold = low_source_score()
    for event in events:
        for source in _audit_sources(event):
            stat = _source_stat(source_stats, source)
            if not stat:
                continue
            stat.audit_uses += 1
            stat.workflows[str(event.workflow or "unknown")] += 1
            stat.add_score(_source_score(source), low_score_threshold)
            quality_status = _source_quality_status(source)
            if quality_status:
                stat.quality_statuses[quality_status] += 1
    for feedback in feedback_entries:
        rating = str(feedback.rating or "").strip()
        for source in feedback.sources():
            stat = _source_stat(source_stats, source)
            if not stat:
                continue
            stat.add_feedback(rating)
            stat.add_score(_source_score(source), low_score_threshold)
    return source_stats


def _audit_sources(event):
    """Return sanitized retrieval sources from one audit event."""
    explainability = event.retrieval_explainability()
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    return sources if isinstance(sources, list) else []


def _source_stat(source_stats, source):
    """Return or create telemetry stats for one source payload."""
    key = _source_key(source)
    if not key:
        return None
    if key not in source_stats:
        source_stats[key] = SourceTelemetry(
            source_type=key[0],
            source_id=key[1],
            chunk_id=key[2],
            title=bounded_string(source.get("title"), 220),
        )
    elif not source_stats[key].title and source.get("title"):
        source_stats[key].title = bounded_string(source.get("title"), 220)
    _merge_source_metadata(source_stats[key], source)
    return source_stats[key]


def _merge_source_metadata(stat, source):
    """Merge prompt-safe source metadata into an aggregate telemetry row."""
    if stat.source_record_id is None:
        stat.source_record_id = optional_int(source.get("source_record_id"))
    if not stat.source_kind:
        stat.source_kind = bounded_string(source.get("source_kind"), 80)
    if not stat.knowledge_source_type:
        stat.knowledge_source_type = bounded_string(source.get("knowledge_source_type"), 80)
    if not stat.module:
        stat.module = bounded_string(source.get("module"), 80)
    if stat.machine_id is None:
        stat.machine_id = optional_int(source.get("machine_id"))
    if not stat.role_visibility:
        stat.role_visibility = bounded_string(source.get("role_visibility"), 140)
    if not stat.created_at:
        stat.created_at = bounded_string(source.get("created_at"), 40)


def _source_key(source):
    """Return a stable source aggregation key."""
    if not isinstance(source, dict):
        return None
    source_type = bounded_string(source.get("type") or "knowledge", 80)
    source_id = optional_int(source.get("id"))
    chunk_id = optional_int(source.get("chunk_id"))
    if source_id is None and chunk_id is None:
        return None
    return source_type, source_id, chunk_id


def _source_score(source):
    """Return the most specific score available on a source payload."""
    if not isinstance(source, dict):
        return None
    explainability = source.get("explainability")
    if isinstance(explainability, dict) and explainability.get("final_score") is not None:
        return explainability.get("final_score")
    return source.get("score")


def _source_quality_status(source):
    """Return source quality status from explainability or direct metadata."""
    if not isinstance(source, dict):
        return ""
    explainability = source.get("explainability")
    if isinstance(explainability, dict) and explainability.get("quality_status"):
        return bounded_string(explainability.get("quality_status"), 80)
    return bounded_string(source.get("quality_status"), 80)


def source_usage_summary(source_stats, limit):
    """Return frequently used source telemetry."""
    sources = sorted(
        source_stats.values(),
        key=lambda stat: (
            stat.audit_uses,
            stat.feedback_count,
            stat.score_count,
        ),
        reverse=True,
    )
    return {
        "used_source_count": sum(1 for stat in sources if stat.audit_uses > 0),
        "referenced_source_count": len(sources),
        "source_kind_distribution": _source_kind_distribution(sources),
        "top_sources": [stat.to_dict() for stat in sources[:limit] if stat.audit_uses > 0],
    }


def _source_kind_distribution(sources):
    """Return source usage counts grouped by retrieval source kind."""
    return dict(
        Counter(
            bounded_string(stat.source_kind, 80) or "unknown"
            for stat in sources
            if stat.audit_uses > 0
        )
    )


def poor_source_summary(source_stats, limit):
    """Return source telemetry that suggests poor retrieval quality."""
    poor_sources = [
        stat
        for stat in source_stats.values()
        if stat.not_helpful_feedback > 0 or stat.low_score_uses > 0
    ]
    poor_sources.sort(
        key=lambda stat: (
            stat.not_helpful_feedback,
            stat.negative_rate,
            stat.low_score_uses,
            stat.audit_uses,
        ),
        reverse=True,
    )
    return [stat.to_dict() for stat in poor_sources[:limit]]


def unused_chunk_summary(used_chunk_ids, limit):
    """Return indexed chunks with no telemetry reference in the selected window."""
    chunks = (
        KnowledgeChunk.query.join(KnowledgeDocument)
        .filter(KnowledgeDocument.status == "indexed")
        .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.id.asc())
        .all()
    )
    unused_chunks = [chunk for chunk in chunks if chunk.id not in used_chunk_ids]
    return {
        "total": len(unused_chunks),
        "referenced_chunk_count": len(used_chunk_ids),
        "chunk_size_metrics": _chunk_size_metrics(unused_chunks),
        "sample": [_chunk_payload(chunk) for chunk in unused_chunks[:limit]],
    }


def _chunk_size_metrics(chunks):
    """Return content-safe size metrics for chunk coverage diagnostics."""
    metadata_rows = [stored_chunk_metadata(chunk) for chunk in chunks]
    char_counts = metadata_int_values(metadata_rows, "chunk_char_count")
    token_counts = metadata_int_values(metadata_rows, "chunk_token_count")
    line_counts = metadata_int_values(metadata_rows, "chunk_line_count")
    block_counts = metadata_int_values(metadata_rows, "chunk_block_count")
    block_kind_counter = Counter()
    for metadata in metadata_rows:
        block_kind_counter.update(chunk_block_kinds(metadata))
    return {
        "measured_chunk_count": len(char_counts),
        "average_char_count": average(char_counts),
        "max_char_count": max(char_counts, default=0),
        "average_token_count": average(token_counts),
        "max_token_count": max(token_counts, default=0),
        "average_line_count": average(line_counts),
        "max_line_count": max(line_counts, default=0),
        "average_block_count": average(block_counts),
        "max_block_count": max(block_counts, default=0),
        "block_kind_distribution": counter_payload(block_kind_counter, limit=10),
    }


def collect_used_chunk_ids(source_stats):
    """Return chunk ids referenced by retrieval or feedback telemetry."""
    return {
        stat.chunk_id
        for stat in source_stats.values()
        if stat.source_type == "knowledge" and stat.chunk_id is not None
    }


def _chunk_payload(chunk):
    """Return a content-safe unused chunk payload."""
    document = chunk.document
    chunk_metadata = stored_chunk_metadata(chunk)
    return {
        "chunk_id": chunk.id,
        "document_id": chunk.document_id,
        "chunk_index": chunk.chunk_index,
        "chunk_char_count": optional_int(chunk_metadata.get("chunk_char_count")),
        "chunk_line_count": optional_int(chunk_metadata.get("chunk_line_count")),
        "chunk_token_count": optional_int(chunk_metadata.get("chunk_token_count")),
        "chunk_block_count": optional_int(chunk_metadata.get("chunk_block_count")),
        "chunk_block_kinds": chunk_block_kinds(chunk_metadata),
        "chunking_mode": bounded_string(chunk_metadata.get("chunking_mode"), 80),
        "section_title": bounded_string(chunk_metadata.get("section_title"), 180),
        "document_title": bounded_string(getattr(document, "title", ""), 220),
        "source_type": getattr(document, "source_type", ""),
        "quality_status": getattr(document, "quality_status", ""),
        "document_status": getattr(document, "status", ""),
        "updated_at": document.updated_at.isoformat() if document and document.updated_at else None,
    }


def _source_title(stat):
    """Return a source title from telemetry or current knowledge metadata."""
    if stat.title:
        return stat.title
    if stat.source_type != "knowledge" or stat.source_id is None:
        return ""
    document = db_get_knowledge_document(stat.source_id)
    return bounded_string(getattr(document, "title", ""), 220)
