"""Vector-store abstractions for RAG retrieval."""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import monotonic, perf_counter

from flask import current_app, has_app_context
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import (
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    KnowledgeChunk,
    KnowledgeDocument,
    MachineManual,
    MaintenancePlan,
    ShiftHandover,
)
from app.services.atlas_health_service import ATLAS_VECTOR_FIELD, atlas_embedding_dimensions
from app.services.chunking_service import token_set
from app.services.embedding_service import get_embedding_provider
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
from app.services.vector_sync_status_service import (
    record_atlas_error,
    record_atlas_fallback,
    record_atlas_query,
    set_atlas_vector_count,
)

logger = logging.getLogger(__name__)

DEFAULT_RAG_TOP_K = 4
DEFAULT_RAG_RERANK_CANDIDATE_LIMIT = 20
DEFAULT_RAG_SCAN_LIMIT = 300
DEFAULT_RAG_KEYWORD_SCAN_LIMIT = 500
DEFAULT_RAG_MAX_KEYWORD_TERMS = 8
DEFAULT_RAG_MIN_SCORE = 1
DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS = 300

# Circuit breaker for unreachable Atlas clusters. Building the client pings the
# cluster and waits up to MONGODB_ATLAS_TIMEOUT_MS; a single request can build
# several stores, so an unreachable cluster used to stall one page for 40 s.
_atlas_circuit = {"open_until": 0.0, "reason": ""}
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


class SqlAlchemyKnowledgeVectorStore(BaseVectorStore):
    """Use persisted knowledge chunks as the local vector-search backend."""

    name = "local_knowledge"

    def __init__(self, embedding_provider=None):
        """Initialize the local knowledge vector adapter."""
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self._last_debug = empty_retrieval_debug(vector_store=self.name)

    def add_documents(self, records):
        """Reject direct writes because knowledge indexing owns persistence."""
        raise VectorStoreError(
            "SqlAlchemyKnowledgeVectorStore is read-only; use knowledge indexing"
        )

    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Return ranked visible knowledge chunks for query text."""
        self._last_debug = empty_retrieval_debug(vector_store=self.name, filters=filters or {})
        if not query_text or user is None:
            return []

        query_tokens = token_set(query_text)
        if not query_tokens:
            return []

        limit_value = _positive_int(limit, _config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        rerank_candidate_limit = _rerank_candidate_limit(limit_value)
        scan_limit = _positive_int(
            _config_value("RAG_SCAN_LIMIT", DEFAULT_RAG_SCAN_LIMIT),
            DEFAULT_RAG_SCAN_LIMIT,
        )
        keyword_scan_limit = _positive_int(
            _config_value("RAG_KEYWORD_SCAN_LIMIT", DEFAULT_RAG_KEYWORD_SCAN_LIMIT),
            DEFAULT_RAG_KEYWORD_SCAN_LIMIT,
        )
        min_score = _positive_int(
            _config_value("RAG_MIN_SCORE", DEFAULT_RAG_MIN_SCORE),
            DEFAULT_RAG_MIN_SCORE,
        )
        query_vector = self.embedding_provider.embed_text(query_text)
        scorer = HybridRetrievalScorer(
            query_text=query_text,
            query_vector=query_vector,
            embedding_provider=self.embedding_provider,
        )
        base_query = KnowledgeChunk.query.join(KnowledgeDocument).filter(
            KnowledgeDocument.status == "indexed"
        )
        base_query = _apply_db_filters(base_query, filters)
        keyword_chunks, recent_chunks = _candidate_chunk_sets(
            base_query=base_query,
            query_tokens=query_tokens,
            recent_limit=scan_limit,
            keyword_limit=keyword_scan_limit,
        )
        chunks = _deduplicate_chunks([*keyword_chunks, *recent_chunks])
        scorer.prime_chunk_vectors(chunks)
        decisions = [
            retrieval_debug_decision(
                "vector_candidate_scan",
                "ok" if chunks else "empty",
                "assembled_keyword_and_recent_chunk_candidates",
                {
                    "keyword_candidates": len(keyword_chunks),
                    "recent_candidates": len(recent_chunks),
                    "unique_candidates": len(chunks),
                },
            )
        ]

        results = []
        permission_filtered = 0
        score_filtered = 0
        quality_filtered = 0
        for chunk in chunks:
            document = chunk.document
            if not _matches_filters(document, filters):
                continue
            quality_gate = retrieval_quality_gate_for_document(document)
            if not quality_gate.allowed:
                quality_filtered += 1
                _log_vector_filter_decision(
                    "quality",
                    document,
                    chunk,
                    quality_gate.reason,
                )
                continue
            if not can_user_read_knowledge_document(user, document):
                permission_filtered += 1
                visibility = source_visibility_decision(user, document)
                _log_vector_filter_decision(
                    "permission",
                    document,
                    chunk,
                    visibility.reason,
                )
                continue
            score = scorer.score_chunk(chunk, document)
            if not score.allowed:
                score_filtered += 1
                _log_vector_filter_decision(
                    "score_anchor",
                    document,
                    chunk,
                    score.explanation,
                )
                continue
            if score.final_score < min_score:
                score_filtered += 1
                _log_vector_filter_decision(
                    "score_anchor",
                    document,
                    chunk,
                    "below_min_score",
                )
                continue
            results.append(
                VectorSearchResult(
                    text=chunk.text,
                    score=score.final_score,
                    metadata=_knowledge_metadata(
                        document,
                        chunk,
                        score=score,
                    ),
                )
            )

        results.sort(
            key=lambda item: (item.score, item.metadata.get("updated_at", "")),
            reverse=True,
        )
        decisions.extend(
            _filter_decisions(
                permission_filtered,
                quality_filtered,
                score_filtered,
                len(results),
                min_score,
            )
        )
        logger.info(
            "rag_local_retrieval query_tokens=%s candidate_count=%s result_count=%s "
            "permission_filtered=%s quality_filtered=%s score_filtered=%s min_score=%s",
            len(query_tokens),
            len(chunks),
            len(results),
            permission_filtered,
            quality_filtered,
            score_filtered,
            min_score,
        )
        self._last_debug = empty_retrieval_debug(
            keyword_candidates_found=len(keyword_chunks),
            vector_candidates_found=len(chunks),
            permission_filtered=permission_filtered,
            quality_filtered=quality_filtered,
            score_filtered=score_filtered,
            score_anchor_filtered=score_filtered,
            vector_store=self.name,
            filters=filters or {},
            top_k=limit_value,
            rerank_candidate_limit=rerank_candidate_limit,
            decision_trace=decisions,
        )
        return results[:limit_value]

    def document_vector_count(self, document_id):
        """Return the local persisted chunk count for one knowledge document."""
        try:
            parsed_id = int(document_id)
        except (TypeError, ValueError):
            return None
        return KnowledgeChunk.query.filter_by(document_id=parsed_id).count()

    def collection_vector_count(self):
        """Return the local persisted chunk count for indexed knowledge documents."""
        return (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(KnowledgeDocument.status == "indexed")
            .count()
        )


class PgVectorKnowledgeVectorStore(BaseVectorStore):
    """Use PostgreSQL pgvector embeddings stored on knowledge chunks."""

    name = "pgvector"

    def __init__(self, embedding_provider=None):
        """Initialize the pgvector knowledge vector adapter."""
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self._last_debug = empty_retrieval_debug(vector_store=self.name)

    def add_documents(self, records):
        """Reject direct writes because knowledge indexing owns chunk embeddings."""
        raise VectorStoreError("PgVectorKnowledgeVectorStore is indexed via KnowledgeChunk")

    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Return pgvector-ranked visible knowledge chunks for query text."""
        self._last_debug = empty_retrieval_debug(vector_store=self.name, filters=filters or {})
        if not query_text or user is None:
            return []
        limit_value = _positive_int(limit, _config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        query_vector = self.embedding_provider.embed_text(query_text)
        candidate_limit = _rerank_candidate_limit(limit_value)
        try:
            raw_rows = self._candidate_rows(query_vector, candidate_limit, filters)
        except SQLAlchemyError:
            logger.exception("pgvector_retrieval_failed fallback=local")
            fallback = SqlAlchemyKnowledgeVectorStore(self.embedding_provider)
            results = fallback.similarity_search(
                query_text,
                user=user,
                limit=limit,
                filters=filters,
            )
            self._last_debug = fallback.last_debug()
            return results

        results, debug_counts = self._visible_results(
            raw_rows,
            query_text=query_text,
            user=user,
            filters=filters,
            min_score=_positive_int(
                _config_value("RAG_MIN_SCORE", DEFAULT_RAG_MIN_SCORE),
                DEFAULT_RAG_MIN_SCORE,
            ),
        )
        results.sort(
            key=lambda item: (item.score, item.metadata.get("updated_at", "")),
            reverse=True,
        )
        decisions = [
            retrieval_debug_decision(
                "vector_candidate_scan",
                "ok" if raw_rows else "empty",
                "pgvector_similarity_candidates_returned",
                {"unique_candidates": len(raw_rows)},
            ),
            *_filter_decisions(
                debug_counts["permission_filtered"],
                debug_counts["quality_filtered"],
                debug_counts["score_filtered"],
                len(results),
                debug_counts["min_score"],
            ),
        ]
        self._last_debug = empty_retrieval_debug(
            vector_candidates_found=len(raw_rows),
            permission_filtered=debug_counts["permission_filtered"],
            quality_filtered=debug_counts["quality_filtered"],
            score_filtered=debug_counts["score_filtered"],
            score_anchor_filtered=debug_counts["score_filtered"],
            vector_store=self.name,
            filters=filters or {},
            top_k=limit_value,
            rerank_candidate_limit=candidate_limit,
            decision_trace=decisions,
        )
        return results[:limit_value]

    def document_vector_count(self, document_id):
        """Return the stored embedding count for one knowledge document."""
        try:
            parsed_id = int(document_id)
        except (TypeError, ValueError):
            return None
        return (
            KnowledgeChunk.query.filter_by(document_id=parsed_id)
            .filter(KnowledgeChunk.embedding.isnot(None))
            .count()
        )

    def collection_vector_count(self):
        """Return the stored embedding count for indexed knowledge documents."""
        return (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(KnowledgeDocument.status == "indexed")
            .filter(KnowledgeChunk.embedding.isnot(None))
            .count()
        )

    def _candidate_rows(self, query_vector, limit_value, filters):
        """Return pgvector candidate chunks with cosine distance."""
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
        query = (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(KnowledgeDocument.status == "indexed")
            .filter(KnowledgeChunk.embedding.isnot(None))
        )
        query = _apply_db_filters(query, filters)
        return (
            query.with_entities(KnowledgeChunk, distance)
            .order_by(distance.asc(), KnowledgeDocument.updated_at.desc())
            .limit(limit_value)
            .all()
        )

    def _visible_results(self, raw_rows, query_text, user, filters, min_score):
        """Return visible scored pgvector results and prompt-safe filter counts."""
        scorer = HybridRetrievalScorer(query_text=query_text)
        results = []
        permission_filtered = 0
        quality_filtered = 0
        score_filtered = 0
        for chunk, distance in raw_rows:
            document = chunk.document
            if not _matches_filters(document, filters):
                continue
            quality_gate = retrieval_quality_gate_for_document(document)
            if not quality_gate.allowed:
                quality_filtered += 1
                _log_vector_filter_decision("quality", document, chunk, quality_gate.reason)
                continue
            if not can_user_read_knowledge_document(user, document):
                permission_filtered += 1
                visibility = source_visibility_decision(user, document)
                _log_vector_filter_decision("permission", document, chunk, visibility.reason)
                continue
            semantic_similarity = max(0.0, 1.0 - float(distance or 0.0))
            score = scorer.score_text_result(
                text=chunk.text,
                document=document,
                chunk_id=chunk.id,
                semantic_similarity=semantic_similarity,
                token_text=chunk.token_text,
            )
            if not score.allowed or score.final_score < min_score:
                score_filtered += 1
                _log_vector_filter_decision(
                    "score_anchor",
                    document,
                    chunk,
                    score.explanation if score.allowed else "insufficient_relevance_anchor",
                )
                continue
            results.append(
                VectorSearchResult(
                    text=chunk.text,
                    score=score.final_score,
                    metadata=_knowledge_metadata(document, chunk, score=score),
                )
            )
        return results, {
            "permission_filtered": permission_filtered,
            "quality_filtered": quality_filtered,
            "score_filtered": score_filtered,
            "min_score": min_score,
        }


class FallbackVectorStore(SqlAlchemyKnowledgeVectorStore):
    """Local vector store that preserves diagnostics for configured fallbacks."""

    def __init__(self, configured_store, fallback_reason, embedding_provider=None):
        """Initialize the local fallback with prompt-safe fallback metadata."""
        super().__init__(embedding_provider=embedding_provider)
        self.configured_store = str(configured_store or "")
        self.fallback_reason = str(fallback_reason or "fallback")
        self._annotate_debug()

    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Run local retrieval and mark the configured-store fallback in debug."""
        results = super().similarity_search(
            query_text,
            user=user,
            limit=limit,
            filters=filters,
        )
        self._annotate_debug()
        return results

    def _annotate_debug(self):
        """Attach fallback diagnostics to the latest local retrieval debug payload."""
        if not isinstance(self._last_debug, dict):
            return
        self._last_debug["fallback_active"] = True
        self._last_debug["fallback_reason"] = self.fallback_reason
        self._last_debug["vector_store_diagnostics"] = {
            "configured_store": self.configured_store,
            "active_store": self.name,
            "fallback_active": True,
            "fallback_reason": self.fallback_reason,
        }


class ChromaVectorStore(BaseVectorStore):
    """Use Chroma as a persistent vector-store backend."""

    name = "chroma"

    def __init__(self, persist_directory, collection_name, embedding_provider=None):
        """Initialize the Chroma vector store lazily."""
        try:
            import chromadb
        except ImportError as exc:
            raise VectorStoreError("chromadb is not installed") from exc

        if not persist_directory:
            raise VectorStoreError("Chroma persist directory is required")
        if not collection_name:
            raise VectorStoreError("Chroma collection name is required")

        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self._last_debug = empty_retrieval_debug(vector_store=self.name)

    def add_documents(self, records):
        """Store vector records in Chroma and return their ids."""
        safe_records = [record for record in records if record.text.strip()]
        if not safe_records:
            return []

        ids = [record.record_id or uuid.uuid4().hex for record in safe_records]
        documents = [record.text for record in safe_records]
        embeddings = self.embedding_provider.embed_texts(documents)
        metadatas = [_flat_metadata(record.metadata) for record in safe_records]
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return ids

    def delete_document(self, document_id):
        """Delete all Chroma records for one knowledge document id."""
        if document_id is None:
            return 0
        self.collection.delete(where={"id": int(document_id)})
        return 1

    def document_vector_count(self, document_id):
        """Return the Chroma record count for one knowledge document."""
        try:
            parsed_id = int(document_id)
        except (TypeError, ValueError):
            return None
        response = self.collection.get(where={"id": parsed_id})
        return len(response.get("ids") or [])

    def collection_vector_count(self):
        """Return the total Chroma record count for the collection."""
        return int(self.collection.count())

    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Return Chroma vector-search results for query text."""
        self._last_debug = empty_retrieval_debug(vector_store=self.name, filters=filters or {})
        if not query_text:
            return []
        limit_value = _positive_int(limit, _config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        query_embedding = self.embedding_provider.embed_text(query_text)
        candidate_limit = _rerank_candidate_limit(limit_value)
        response = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_limit,
            where=_flat_metadata(filters or {}) or None,
        )
        raw_results = _chroma_results(response)
        debug = empty_retrieval_debug(
            vector_candidates_found=len(raw_results),
            vector_store=self.name,
            filters=filters or {},
            top_k=limit_value,
            rerank_candidate_limit=candidate_limit,
            decision_trace=[
                retrieval_debug_decision(
                    "vector_candidate_scan",
                    "ok" if raw_results else "empty",
                    "chroma_similarity_candidates_returned",
                    {"unique_candidates": len(raw_results)},
                )
            ],
        )
        results = _filter_visible_results(
            raw_results,
            query_text=query_text,
            user=user,
            filters=filters,
            limit=limit_value,
            debug=debug,
        )
        self._last_debug = debug
        return results


class MongoAtlasVectorStore(BaseVectorStore):
    """Use MongoDB Atlas Vector Search as an external candidate store."""

    name = "mongodb_atlas"

    def __init__(self, embedding_provider=None):
        """Initialize the Atlas Vector Search adapter from Flask config."""
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.uri = str(_config_value("MONGODB_ATLAS_URI", "") or "").strip()
        self.database_name = str(_config_value("MONGODB_ATLAS_DATABASE", "") or "").strip()
        self.collection_name = str(
            _config_value("MONGODB_ATLAS_VECTOR_COLLECTION", "") or ""
        ).strip()
        self.index_name = str(_config_value("MONGODB_ATLAS_VECTOR_INDEX", "") or "").strip()
        self.timeout_ms = _positive_int(
            _config_value("MONGODB_ATLAS_TIMEOUT_MS", 3000),
            3000,
        )
        self._last_debug = empty_retrieval_debug(vector_store=self.name)
        self._validate_configuration()
        self.client = self._build_client()
        self.collection = self.client[self.database_name][self.collection_name]

    def add_documents(self, records):
        """Upsert vector records into Atlas using existing chunk embeddings."""
        safe_records = [record for record in records if str(record.text or "").strip()]
        if not safe_records:
            return []

        stored_ids = []
        try:
            for record in safe_records:
                record_id = record.record_id or uuid.uuid4().hex
                metadata = _safe_vector_metadata(record.metadata)
                embedding = _atlas_embedding(record.embedding)
                payload = {
                    "record_id": record_id,
                    "document_id": metadata.get("id"),
                    "chunk_id": metadata.get("chunk_id"),
                    "text": record.text,
                    ATLAS_VECTOR_FIELD: embedding,
                    "metadata": metadata,
                }
                self.collection.replace_one(
                    {"record_id": record_id},
                    payload,
                    upsert=True,
                )
                stored_ids.append(record_id)
            return stored_ids
        except Exception as exc:
            record_atlas_error(exc)
            raise VectorStoreError("atlas_upsert_failed") from exc

    def delete_document(self, document_id):
        """Delete all Atlas records for one knowledge document id."""
        parsed_id = _optional_int(document_id)
        if parsed_id is None:
            return 0
        try:
            response = self.collection.delete_many({"document_id": parsed_id})
            return int(getattr(response, "deleted_count", 0) or 0)
        except Exception as exc:
            record_atlas_error(exc)
            raise VectorStoreError("atlas_delete_failed") from exc

    def document_vector_count(self, document_id):
        """Return the Atlas vector count for one knowledge document."""
        parsed_id = _optional_int(document_id)
        if parsed_id is None:
            return None
        try:
            return int(self.collection.count_documents({"document_id": parsed_id}))
        except Exception as exc:
            record_atlas_error(exc)
            raise VectorStoreError("atlas_document_count_failed") from exc

    def collection_vector_count(self):
        """Return the Atlas vector count for the collection."""
        try:
            vector_count = int(self.collection.count_documents({}))
            set_atlas_vector_count(vector_count)
            return vector_count
        except Exception as exc:
            record_atlas_error(exc)
            raise VectorStoreError("atlas_collection_count_failed") from exc

    def similarity_search(self, query_text, user=None, limit=None, filters=None):
        """Return Atlas candidates after applying SQL permissions and quality gates."""
        self._last_debug = empty_retrieval_debug(vector_store=self.name, filters=filters or {})
        if not query_text:
            return []
        limit_value = _positive_int(limit, _config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        candidate_limit = _rerank_candidate_limit(limit_value)
        try:
            query_embedding = _atlas_embedding(self.embedding_provider.embed_text(query_text))
            pipeline = self._vector_search_pipeline(
                query_embedding,
                candidate_limit,
                filters=filters,
            )
            started_at = perf_counter()
            documents = list(self.collection.aggregate(pipeline))
            record_atlas_query((perf_counter() - started_at) * 1000)
        except Exception as exc:
            record_atlas_error(exc)
            return self._fallback_similarity_search(
                "query_failed",
                query_text=query_text,
                user=user,
                limit=limit_value,
                filters=filters,
            )

        raw_results = [_atlas_result(document) for document in documents]
        debug = empty_retrieval_debug(
            vector_candidates_found=len(raw_results),
            vector_store=self.name,
            filters=filters or {},
            top_k=limit_value,
            rerank_candidate_limit=candidate_limit,
            fallback_active=False,
            fallback_reason="",
            vector_store_diagnostics={
                "configured_store": self.name,
                "active_store": self.name,
                "fallback_active": False,
            },
            decision_trace=[
                retrieval_debug_decision(
                    "vector_candidate_scan",
                    "ok" if raw_results else "empty",
                    "mongodb_atlas_similarity_candidates_returned",
                    {"unique_candidates": len(raw_results)},
                )
            ],
        )
        results = _filter_visible_results(
            raw_results,
            query_text=query_text,
            user=user,
            filters=filters,
            limit=limit_value,
            debug=debug,
        )
        self._last_debug = debug
        return results

    def _validate_configuration(self):
        """Validate required Atlas settings without exposing secret values."""
        missing = []
        if not self.uri:
            missing.append("MONGODB_ATLAS_URI")
        if not self.database_name:
            missing.append("MONGODB_ATLAS_DATABASE")
        if not self.collection_name:
            missing.append("MONGODB_ATLAS_VECTOR_COLLECTION")
        if not self.index_name:
            missing.append("MONGODB_ATLAS_VECTOR_INDEX")
        if missing:
            raise VectorStoreError(f"missing_config:{','.join(missing)}")

    def _build_client(self):
        """Create and ping a pymongo client without logging connection details."""
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise VectorStoreError("pymongo_missing") from exc

        try:
            client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_ms,
                connectTimeoutMS=self.timeout_ms,
                socketTimeoutMS=self.timeout_ms,
            )
            client.admin.command("ping")
            return client
        except Exception as exc:
            record_atlas_error(exc)
            raise VectorStoreError("connection_failed") from exc

    def _vector_search_pipeline(self, query_embedding, candidate_limit, filters=None):
        """Return the Atlas Vector Search pipeline for candidate retrieval only."""
        vector_search = {
            "index": self.index_name,
            "path": ATLAS_VECTOR_FIELD,
            "queryVector": query_embedding,
            "numCandidates": candidate_limit,
            "limit": candidate_limit,
        }
        atlas_filter = _atlas_vector_search_filter(filters)
        if atlas_filter:
            vector_search["filter"] = atlas_filter
        return [
            {"$vectorSearch": vector_search},
            {
                "$project": {
                    "_id": 0,
                    "record_id": 1,
                    "document_id": 1,
                    "chunk_id": 1,
                    "text": 1,
                    "metadata": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

    def _fallback_similarity_search(self, reason, query_text, user, limit, filters):
        """Run the local SQL vector store and mark the Atlas fallback explicitly."""
        record_atlas_fallback(reason)
        logger.warning("vector_store_fallback store=mongodb_atlas reason=%s", reason)
        fallback = SqlAlchemyKnowledgeVectorStore(self.embedding_provider)
        results = fallback.similarity_search(
            query_text,
            user=user,
            limit=limit,
            filters=filters,
        )
        debug = fallback.last_debug()
        if isinstance(debug, dict):
            debug["fallback_active"] = True
            debug["fallback_reason"] = reason
            debug["vector_store_diagnostics"] = {
                "configured_store": self.name,
                "active_store": fallback.name,
                "fallback_active": True,
                "fallback_reason": reason,
            }
        self._last_debug = debug
        return results


def reset_atlas_circuit():
    """Close the Atlas circuit breaker so the next request tries the cluster again."""
    _atlas_circuit["open_until"] = 0.0
    _atlas_circuit["reason"] = ""


def atlas_circuit_open():
    """Return whether Atlas connections are currently skipped after a failure."""
    return monotonic() < _atlas_circuit["open_until"]


def _open_atlas_circuit(reason):
    """Skip Atlas connection attempts for the configured cooldown."""
    cooldown = _positive_int(
        _config_value("MONGODB_ATLAS_RETRY_COOLDOWN_SECONDS", DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS),
        DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS,
    )
    _atlas_circuit["open_until"] = monotonic() + cooldown
    _atlas_circuit["reason"] = reason
    logger.warning("atlas_circuit_open reason=%s cooldown_seconds=%s", reason, cooldown)


def get_vector_store():
    """Return the configured vector store with a local fallback."""
    store_name = _config_value("RAG_VECTOR_STORE", "pgvector").lower()
    if store_name == "pgvector":
        if _is_postgresql():
            return PgVectorKnowledgeVectorStore()
        logger.info("vector_store_fallback store=pgvector reason=non_postgresql_database")
        return SqlAlchemyKnowledgeVectorStore()
    if store_name in {"local", "sqlalchemy", "knowledge"}:
        return SqlAlchemyKnowledgeVectorStore()
    if store_name == "chroma":
        try:
            return ChromaVectorStore(
                persist_directory=_config_value("CHROMA_PERSIST_DIR", "data/chroma"),
                collection_name=_config_value("CHROMA_COLLECTION", "maintenance_knowledge"),
            )
        except VectorStoreError:
            logger.exception("vector_store_fallback store=chroma")
            return SqlAlchemyKnowledgeVectorStore()
    if store_name in {"mongodb_atlas", "mongo_atlas", "atlas"}:
        if atlas_circuit_open():
            return FallbackVectorStore("mongodb_atlas", _atlas_circuit["reason"])
        try:
            return MongoAtlasVectorStore()
        except VectorStoreError as exc:
            reason = _safe_fallback_reason(exc)
            record_atlas_fallback(reason)
            logger.warning("vector_store_fallback store=mongodb_atlas reason=%s", reason)
            if reason == "connection_failed":
                _open_atlas_circuit(reason)
        return FallbackVectorStore("mongodb_atlas", reason)
    logger.warning("vector_store_fallback store=%s reason=unsupported_store", store_name)
    return SqlAlchemyKnowledgeVectorStore()


def _knowledge_metadata(document, chunk, score=None):
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
        "document_type": _document_type(document),
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


def _document_type(document):
    """Return a source document type when it can be resolved safely."""
    if document.source_type != "generated_document" or not document.source_id:
        return document.source_type
    generated_document = db.session.get(GeneratedDocument, document.source_id)
    if not generated_document:
        return document.source_type
    return generated_document.document_type


def _matches_filters(document, filters):
    """Return whether a knowledge document matches optional metadata filters."""
    if not filters:
        return True
    for key, value in filters.items():
        if value in (None, ""):
            continue
        if key == "document_type" and _document_type(document) != value:
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


def _apply_db_filters(query, filters):
    """Apply safe document-level filters before candidate scanning."""
    if not filters:
        return query
    source_type = filters.get("source_type")
    if source_type not in (None, ""):
        query = query.filter(KnowledgeDocument.source_type == str(source_type))
    department = filters.get("department")
    if department not in (None, ""):
        query = query.filter(KnowledgeDocument.department == str(department))
    source_id = filters.get("source_id")
    if source_id not in (None, ""):
        query = query.filter(KnowledgeDocument.source_id == source_id)
    machine_id = filters.get("machine_id")
    if machine_id not in (None, ""):
        query = query.filter(_machine_source_filter(machine_id))
    return query


def _machine_source_filter(machine_id):
    """Return a document filter for source models with direct machine links."""
    parsed_machine_id = _optional_int(machine_id)
    if parsed_machine_id is None:
        return KnowledgeDocument.id.is_(None)
    return or_(
        (
            (KnowledgeDocument.source_type == "machine")
            & (KnowledgeDocument.source_id == parsed_machine_id)
        ),
        (
            (KnowledgeDocument.source_type == "error_entry")
            & KnowledgeDocument.source_id.in_(
                db.session.query(ErrorEntry.id).filter(ErrorEntry.machine_id == parsed_machine_id)
            )
        ),
        (
            (KnowledgeDocument.source_type == "generated_document")
            & KnowledgeDocument.source_id.in_(
                db.session.query(GeneratedDocument.id).filter(
                    GeneratedDocument.machine_id == parsed_machine_id
                )
            )
        ),
        (
            (KnowledgeDocument.source_type == "inventory_material")
            & KnowledgeDocument.source_id.in_(
                db.session.query(InventoryMaterial.id).filter(
                    InventoryMaterial.machine_id == parsed_machine_id
                )
            )
        ),
        (
            (KnowledgeDocument.source_type == "maintenance_plan")
            & KnowledgeDocument.source_id.in_(
                db.session.query(MaintenancePlan.id).filter(
                    MaintenancePlan.machine_id == parsed_machine_id
                )
            )
        ),
        (
            (KnowledgeDocument.source_type == "machine_manual")
            & KnowledgeDocument.source_id.in_(
                db.session.query(MachineManual.id).filter(
                    MachineManual.machine_id == parsed_machine_id
                )
            )
        ),
        (
            (KnowledgeDocument.source_type == "shift_handover")
            & KnowledgeDocument.source_id.in_(
                db.session.query(ShiftHandover.id).filter(
                    ShiftHandover.machine_id == parsed_machine_id
                )
            )
        ),
    )


def _candidate_chunk_sets(base_query, query_tokens, recent_limit, keyword_limit):
    """Return keyword and recent candidate chunks before de-duplication."""
    recent_chunks = (
        base_query.order_by(
            KnowledgeDocument.updated_at.desc(),
            KnowledgeChunk.chunk_index.asc(),
        )
        .limit(recent_limit)
        .all()
    )
    keyword_chunks = _keyword_candidate_chunks(base_query, query_tokens, keyword_limit)
    return keyword_chunks, recent_chunks


def _keyword_candidate_chunks(base_query, query_tokens, keyword_limit):
    """Return chunks matched by informative query tokens before scoring."""
    terms = _informative_query_terms(query_tokens)
    if not terms:
        return []
    filters = [KnowledgeChunk.token_text.ilike(f"%{term}%") for term in terms]
    return (
        base_query.filter(or_(*filters))
        .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.chunk_index.asc())
        .limit(keyword_limit)
        .all()
    )


def _informative_query_terms(query_tokens):
    """Return bounded query tokens useful for lexical candidate expansion."""
    terms = [str(token).lower() for token in query_tokens if _is_informative_query_token(token)]
    terms.sort(key=lambda token: (not _looks_like_code_token(token), -len(token), token))
    return terms[:DEFAULT_RAG_MAX_KEYWORD_TERMS]


def _is_informative_query_token(token):
    """Return whether a query token is useful enough for DB prefiltering."""
    value = str(token or "").strip().lower()
    if len(value) < 3 or value in RETRIEVAL_STOPWORDS:
        return False
    return True


def _looks_like_code_token(token):
    """Return whether a token looks like an error code or technical identifier."""
    value = str(token or "")
    return any(char.isdigit() for char in value)


def _deduplicate_chunks(chunks):
    """Return chunks without duplicate database ids while preserving order."""
    seen = set()
    unique_chunks = []
    for chunk in chunks:
        key = getattr(chunk, "id", None)
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(chunk)
    return unique_chunks


def _flat_metadata(metadata):
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


def _safe_vector_metadata(metadata):
    """Return flat vector metadata without secret-like keys."""
    blocked_fragments = ("password", "secret", "token", "api_key", "connection", "uri")
    flat = {}
    for key, value in _flat_metadata(metadata).items():
        normalized_key = str(key).lower()
        if any(fragment in normalized_key for fragment in blocked_fragments):
            continue
        flat[str(key)] = value
    return flat


def _atlas_embedding(embedding):
    """Return a validated Atlas embedding vector."""
    expected_dimensions = atlas_embedding_dimensions()
    if not isinstance(embedding, list) or not embedding:
        raise VectorStoreError("atlas_embedding_missing")
    if len(embedding) != expected_dimensions:
        raise VectorStoreError(f"atlas_embedding_dimensions_expected_{expected_dimensions}")
    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        raise VectorStoreError("atlas_embedding_invalid") from exc


def _atlas_vector_search_filter(filters):
    """Return an Atlas metadata pre-filter for vector search when filters are set."""
    if not isinstance(filters, dict) or not filters:
        return None

    clauses = []
    department = str(filters.get("department") or "").strip()
    if department:
        clauses.append({"metadata.department": department})

    machine_id = filters.get("machine_id")
    if machine_id not in (None, ""):
        try:
            clauses.append({"metadata.machine_id": int(machine_id)})
        except (TypeError, ValueError):
            pass

    quality_status = str(filters.get("quality_status") or "").strip()
    if quality_status:
        clauses.append({"metadata.quality_status": quality_status})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _atlas_result(document):
    """Return one Atlas document as a normalized vector-search result."""
    metadata = dict(document.get("metadata") or {})
    if document.get("document_id") not in (None, ""):
        metadata.setdefault("id", document.get("document_id"))
    if document.get("chunk_id") not in (None, ""):
        metadata.setdefault("chunk_id", document.get("chunk_id"))
    if document.get("record_id") not in (None, ""):
        metadata.setdefault("record_id", document.get("record_id"))
    return VectorSearchResult(
        text=str(document.get("text") or ""),
        score=float(document.get("score") or 0.0),
        metadata=metadata,
    )


def _safe_fallback_reason(error):
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


def _chroma_results(response):
    """Return normalized Chroma query results."""
    documents = (response.get("documents") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    results = []
    for index, document in enumerate(documents):
        distance = distances[index] if index < len(distances) else 0
        metadata = metadatas[index] if index < len(metadatas) else {}
        results.append(
            VectorSearchResult(
                text=document,
                score=max(0.0, 1.0 - float(distance)),
                metadata=metadata or {},
            )
        )
    return results


def _filter_visible_results(results, query_text, user=None, filters=None, limit=None, debug=None):
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
        if not _matches_filters(document, filters):
            continue
        quality_gate = retrieval_quality_gate_for_document(document)
        if not quality_gate.allowed:
            quality_filtered += 1
            _log_vector_filter_decision(
                "quality",
                document,
                _chunk_for_metadata(result),
                quality_gate.reason,
            )
            continue
        if user is not None and not can_user_read_knowledge_document(user, document):
            permission_filtered += 1
            visibility = source_visibility_decision(user, document)
            _log_vector_filter_decision(
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
            _log_vector_filter_decision(
                "score_anchor",
                document,
                _chunk_for_metadata(result),
                score.explanation,
            )
            continue
        merged_metadata = dict(result.metadata)
        merged_metadata.update(
            _knowledge_metadata(
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
            *_filter_decisions(
                permission_filtered,
                quality_filtered,
                score_filtered,
                len(visible),
                min_score=0,
            ),
        ]
    return visible[:limit] if limit else visible


def _filter_decisions(
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


def _log_vector_filter_decision(reason_type, document, chunk, reason):
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


def _config_value(name, default):
    """Return a Flask config value when available, otherwise a default."""
    if has_app_context():
        return current_app.config.get(name, default)
    return default


def _positive_int(value, default):
    """Return a positive integer config value."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_int(value):
    """Return an integer when parsing succeeds, otherwise None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rerank_candidate_limit(final_limit):
    """Return how many vector candidates should be fetched before final top-K trimming."""
    configured_limit = _positive_int(
        _config_value(
            "RAG_RERANK_CANDIDATE_LIMIT",
            DEFAULT_RAG_RERANK_CANDIDATE_LIMIT,
        ),
        DEFAULT_RAG_RERANK_CANDIDATE_LIMIT,
    )
    return max(_positive_int(final_limit, DEFAULT_RAG_TOP_K), configured_limit)


def _is_postgresql():
    """Return whether the current SQLAlchemy bind is PostgreSQL."""
    if not has_app_context():
        return False
    return db.engine.url.get_backend_name() == "postgresql"
