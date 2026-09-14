"""Shared types, thresholds and result filtering for the vector-store backends."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from flask import current_app, has_app_context

from app.extensions import db
from app.models import (
    GeneratedDocument,
    KnowledgeDocument,
)
from app.services.knowledge_quality_service import retrieval_quality_gate_for_document
from app.services.knowledge_service import (
    can_user_read_knowledge_document,
    document_entity_metadata,
    source_url,
    stored_chunk_metadata,
    structured_source_created_at,
    structured_source_machine_id,
)
from app.services.retrieval_debug_service import (
    empty_retrieval_debug,
    retrieval_debug_decision,
)
from app.services.retrieval_scoring_service import HybridRetrievalScorer
from app.services.source_visibility_policy import (
    source_role_visibility_label,
    source_visibility_decision,
)
from app.services.technical_entity_service import entities_from_json, entities_to_json

logger = logging.getLogger(__name__)

DEFAULT_RAG_TOP_K = 4


DEFAULT_RAG_RERANK_CANDIDATE_LIMIT = 20


DEFAULT_RAG_SCAN_LIMIT = 300


DEFAULT_RAG_KEYWORD_SCAN_LIMIT = 500


DEFAULT_RAG_MAX_KEYWORD_TERMS = 8


DEFAULT_RAG_MIN_SCORE = 1


DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS = 300


RETRIEVAL_STOPWORDS = {
    "aber",
    "alle",
    "als",
    "am",
    "an",
    "auf",
    "bei",
    "bitte",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "fuer",
    "für",
    "hat",
    "hilfe",
    "hilft",
    "ich",
    "ist",
    "mit",
    "nach",
    "nicht",
    "oder",
    "und",
    "von",
    "was",
    "welche",
    "wie",
    "zu",
}


class VectorStoreError(Exception):
    """Raised when a vector store cannot complete an operation."""


@dataclass(frozen=True)
class VectorRecord:
    """One text record prepared for a vector store."""

    text: str
    metadata: dict = field(default_factory=dict)
    record_id: str = ""
    embedding: list[float] | None = None


@dataclass(frozen=True)
class VectorSearchResult:
    """One vector search result with score and metadata."""

    text: str
    score: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        """Return the search result as a JSON-serializable dictionary."""
        return {
            "text": self.text,
            "score": self.score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ChunkMetadataProxy:
    """Lightweight chunk object used for metadata reconstruction."""

    id: int | str | None = None
    chunk_index: int | str = 0
    entities_json: str = "{}"
    chunk_metadata: dict = field(default_factory=dict)

    def retrieval_metadata(self):
        """Return section-aware metadata carried by a vector result."""
        return dict(self.chunk_metadata)


class BaseVectorStore(ABC):
    """Define the vector-store contract used by retrieval services."""

    name = "base"

    @abstractmethod
    def add_documents(self, records):
        """Store vector records and return stored record ids."""

    @abstractmethod
    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Return vector-search results for query text."""

    def delete_document(self, document_id):
        """Delete records for one knowledge document when the backend supports it."""
        return 0

    def document_vector_count(self, document_id):
        """Return one document's vector count when the backend can report it."""
        return None

    def collection_vector_count(self):
        """Return the total vector count when the backend can report it."""
        return None

    def last_debug(self):
        """Return prompt-safe debug counters for the latest search."""
        return getattr(self, "_last_debug", empty_retrieval_debug(vector_store=self.name))


def knowledge_metadata(document, chunk, score=None):
    """Return metadata for a persisted knowledge chunk."""
    entities = _chunk_entities(chunk)
    source_created_at = structured_source_created_at(document)
    metadata = {
        "type": "knowledge",
        "id": document.id,
        "chunk_id": chunk.id,
        "chunk_index": chunk.chunk_index,
        "title": document.title,
        "module": "knowledge",
        "source_type": document.source_type,
        "source_id": document.source_id,
        "document_type": document_type(document),
        "department": document.department,
        "machine_id": structured_source_machine_id(document),
        "role_visibility": source_role_visibility_label(document),
        "created_at": source_created_at or document.created_at.isoformat(),
        "url": source_url(document),
        "updated_at": document.updated_at.isoformat(),
        "technical_entities": entities,
        "technical_entities_json": entities_to_json(entities),
    }
    if score is not None:
        score_metadata = score.metadata()
        metadata["score_debug"] = score_metadata
        metadata["score_components"] = score_metadata["components"]
        metadata["score_signals"] = score_metadata["signals"]
        metadata["quality_status"] = score_metadata["signals"].get("quality_status")
        metadata["quality_gate"] = score_metadata["signals"].get("quality_gate")
        metadata["quality_score_multiplier"] = score_metadata["signals"].get("quality_multiplier")
    metadata.update(_public_source_entity_metadata(document_entity_metadata(document)))
    metadata.update(stored_chunk_metadata(chunk))
    return metadata


def _public_source_entity_metadata(metadata):
    """Return source metadata that is safe to expose in answer source cards."""
    safe = {}
    for key in ("machine", "department", "document_type"):
        value = metadata.get(key) if isinstance(metadata, dict) else None
        if value not in (None, ""):
            safe[key] = str(value)[:180]
    return safe


def _chunk_entities(chunk):
    """Return technical entities from a real or lightweight chunk object."""
    if hasattr(chunk, "entities"):
        return chunk.entities()
    return entities_from_json(getattr(chunk, "entities_json", "{}"))


def document_type(document):
    """Return a source document type when it can be resolved safely."""
    if document.source_type != "generated_document" or not document.source_id:
        return document.source_type
    generated_document = db.session.get(GeneratedDocument, document.source_id)
    if not generated_document:
        return document.source_type
    return generated_document.document_type


def flat_metadata(metadata):
    """Return Chroma-compatible primitive metadata."""
    flat = {}
    for key, value in dict(metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, str | int | float | bool):
            flat[str(key)] = value
        else:
            flat[str(key)] = str(value)
    return flat


def safe_vector_metadata(metadata):
    """Return flat vector metadata without secret-like keys."""
    blocked_fragments = ("password", "secret", "token", "api_key", "connection", "uri")
    flat = {}
    for key, value in flat_metadata(metadata).items():
        normalized_key = str(key).lower()
        if any(fragment in normalized_key for fragment in blocked_fragments):
            continue
        flat[str(key)] = value
    return flat


def safe_fallback_reason(error):
    """Return a bounded fallback reason that cannot include secrets."""
    reason = str(error or "").splitlines()[0].strip()
    allowed_prefixes = (
        "missing_config",
        "pymongo_missing",
        "connection_failed",
        "atlas_",
    )
    if not reason.startswith(allowed_prefixes):
        return "adapter_unavailable"
    return reason[:160]


def filter_visible_results(results, query_text, user=None, filters=None, limit=None, debug=None):
    """Return Chroma results still visible according to database permissions."""
    scorer = HybridRetrievalScorer(query_text=query_text)
    visible = []
    permission_filtered = 0
    quality_filtered = 0
    score_filtered = 0
    for result in results:
        document_id = result.metadata.get("id")
        try:
            document = db.session.get(KnowledgeDocument, int(document_id))
        except (TypeError, ValueError):
            continue
        if not document or document.status != "indexed":
            continue
        if not matches_filters(document, filters):
            continue
        quality_gate = retrieval_quality_gate_for_document(document)
        if not quality_gate.allowed:
            quality_filtered += 1
            log_vector_filter_decision(
                "quality",
                document,
                _chunk_for_metadata(result),
                quality_gate.reason,
            )
            continue
        if user is not None and not can_user_read_knowledge_document(user, document):
            permission_filtered += 1
            visibility = source_visibility_decision(user, document)
            log_vector_filter_decision(
                "permission",
                document,
                _chunk_for_metadata(result),
                visibility.reason,
            )
            continue
        score = scorer.score_text_result(
            text=result.text,
            document=document,
            chunk_id=result.metadata.get("chunk_id"),
            semantic_similarity=result.score,
        )
        if not score.allowed:
            score_filtered += 1
            log_vector_filter_decision(
                "score_anchor",
                document,
                _chunk_for_metadata(result),
                score.explanation,
            )
            continue
        merged_metadata = dict(result.metadata)
        merged_metadata.update(
            knowledge_metadata(
                document,
                _chunk_for_metadata(result),
                score=score,
            )
        )
        visible.append(
            VectorSearchResult(
                text=result.text,
                score=score.final_score,
                metadata=merged_metadata,
            )
        )
    visible.sort(
        key=lambda item: (item.score, item.metadata.get("updated_at", "")),
        reverse=True,
    )
    if isinstance(debug, dict):
        debug["permission_filtered"] = permission_filtered
        debug["quality_filtered"] = quality_filtered
        debug["score_filtered"] = score_filtered
        debug["score_anchor_filtered"] = score_filtered
        debug["decision_trace"] = [
            *(debug.get("decision_trace") or []),
            *filter_decisions(
                permission_filtered,
                quality_filtered,
                score_filtered,
                len(visible),
                min_score=0,
            ),
        ]
    return visible[:limit] if limit else visible


def filter_decisions(
    permission_filtered,
    quality_filtered,
    score_filtered,
    visible_count,
    min_score,
):
    """Return aggregate vector retrieval decisions without source text."""
    decisions = []
    for step, count, reason in (
        ("permission_filter", permission_filtered, "source_visibility_policy_denied"),
        ("quality_filter", quality_filtered, "retrieval_quality_gate_denied"),
        ("score_anchor_filter", score_filtered, "insufficient_score_or_relevance_anchor"),
    ):
        if count:
            decisions.append(
                retrieval_debug_decision(
                    step,
                    "filtered",
                    reason,
                    {"filtered": count},
                )
            )
    decisions.append(
        retrieval_debug_decision(
            "vector_visible_candidates",
            "ok" if visible_count else "empty",
            "candidates_remaining_after_visibility_quality_and_score_filters",
            {"visible_candidates": visible_count, "min_score": min_score},
        )
    )
    return decisions


def log_vector_filter_decision(reason_type, document, chunk, reason):
    """Log one prompt-safe vector retrieval filter decision."""
    logger.debug(
        "rag_candidate_filtered reason_type=%s reason=%s document_id=%s chunk_id=%s "
        "source_type=%s quality_status=%s",
        reason_type,
        reason,
        getattr(document, "id", None),
        getattr(chunk, "id", None),
        getattr(document, "source_type", ""),
        getattr(document, "quality_status", ""),
    )


def _chunk_for_metadata(result):
    """Return a lightweight object exposing chunk metadata fields."""
    chunk_metadata = {
        key: result.metadata.get(key)
        for key in (
            "chunk_index",
            "chunk_order",
            "chunk_char_count",
            "chunk_line_count",
            "chunk_token_count",
            "chunk_block_count",
            "chunk_block_kinds",
            "source_offset",
            "source_section",
            "section_title",
            "chunking_mode",
            "semantic_group",
            "semantic_break_distance",
            "embedding_model",
            "embedding_dimensions",
        )
        if result.metadata.get(key) not in (None, "")
    }
    return ChunkMetadataProxy(
        id=result.metadata.get("chunk_id"),
        chunk_index=result.metadata.get("chunk_index", 0),
        entities_json=result.metadata.get("technical_entities_json", "{}"),
        chunk_metadata=chunk_metadata,
    )


def config_value(name, default):
    """Return a Flask config value when available, otherwise a default."""
    if has_app_context():
        return current_app.config.get(name, default)
    return default


def positive_int(value, default):
    """Return a positive integer config value."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def optional_int(value):
    """Return an integer when parsing succeeds, otherwise None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def rerank_candidate_limit(final_limit):
    """Return how many vector candidates should be fetched before final top-K trimming."""
    configured_limit = positive_int(
        config_value(
            "RAG_RERANK_CANDIDATE_LIMIT",
            DEFAULT_RAG_RERANK_CANDIDATE_LIMIT,
        ),
        DEFAULT_RAG_RERANK_CANDIDATE_LIMIT,
    )
    return max(positive_int(final_limit, DEFAULT_RAG_TOP_K), configured_limit)


def matches_filters(document, filters):
    """Return whether a knowledge document matches optional metadata filters."""
    if not filters:
        return True
    for key, value in filters.items():
        if value in (None, ""):
            continue
        if key == "document_type" and document_type(document) != value:
            return False
        if key == "department" and document.department != value:
            return False
        if key == "source_type" and document.source_type != value:
            return False
        if key == "source_id" and str(document.source_id) != str(value):
            return False
        if key == "module" and str(value) != "knowledge":
            return False
        if key == "machine_id" and str(structured_source_machine_id(document) or "") != str(value):
            return False
        if key == "role_visibility" and source_role_visibility_label(document) != str(value):
            return False
    return True
