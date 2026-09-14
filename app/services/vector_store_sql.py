"""Vector stores on the app database: SQLAlchemy keyword scan, pgvector, local fallback."""

import logging

from flask import has_app_context
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
from app.services.chunking_service import token_set
from app.services.embedding_service import get_embedding_provider
from app.services.knowledge_quality_service import retrieval_quality_gate_for_document
from app.services.knowledge_service import (
    can_user_read_knowledge_document,
)
from app.services.retrieval_debug_service import (
    empty_retrieval_debug,
    retrieval_debug_decision,
)
from app.services.retrieval_scoring_service import HybridRetrievalScorer
from app.services.source_visibility_policy import (
    source_visibility_decision,
)
from app.services.vector_store_common import (
    DEFAULT_RAG_KEYWORD_SCAN_LIMIT,
    DEFAULT_RAG_MAX_KEYWORD_TERMS,
    DEFAULT_RAG_MIN_SCORE,
    DEFAULT_RAG_SCAN_LIMIT,
    DEFAULT_RAG_TOP_K,
    RETRIEVAL_STOPWORDS,
    BaseVectorStore,
    VectorSearchResult,
    VectorStoreError,
    config_value,
    filter_decisions,
    knowledge_metadata,
    log_vector_filter_decision,
    matches_filters,
    optional_int,
    positive_int,
    rerank_candidate_limit,
)

logger = logging.getLogger(__name__)


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

        limit_value = positive_int(limit, config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        candidate_limit = rerank_candidate_limit(limit_value)
        scan_limit = positive_int(
            config_value("RAG_SCAN_LIMIT", DEFAULT_RAG_SCAN_LIMIT),
            DEFAULT_RAG_SCAN_LIMIT,
        )
        keyword_scan_limit = positive_int(
            config_value("RAG_KEYWORD_SCAN_LIMIT", DEFAULT_RAG_KEYWORD_SCAN_LIMIT),
            DEFAULT_RAG_KEYWORD_SCAN_LIMIT,
        )
        min_score = positive_int(
            config_value("RAG_MIN_SCORE", DEFAULT_RAG_MIN_SCORE),
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
            if not matches_filters(document, filters):
                continue
            quality_gate = retrieval_quality_gate_for_document(document)
            if not quality_gate.allowed:
                quality_filtered += 1
                log_vector_filter_decision(
                    "quality",
                    document,
                    chunk,
                    quality_gate.reason,
                )
                continue
            if not can_user_read_knowledge_document(user, document):
                permission_filtered += 1
                visibility = source_visibility_decision(user, document)
                log_vector_filter_decision(
                    "permission",
                    document,
                    chunk,
                    visibility.reason,
                )
                continue
            score = scorer.score_chunk(chunk, document)
            if not score.allowed:
                score_filtered += 1
                log_vector_filter_decision(
                    "score_anchor",
                    document,
                    chunk,
                    score.explanation,
                )
                continue
            if score.final_score < min_score:
                score_filtered += 1
                log_vector_filter_decision(
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
                    metadata=knowledge_metadata(
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
            filter_decisions(
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
            rerank_candidate_limit=candidate_limit,
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
        limit_value = positive_int(limit, config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        query_vector = self.embedding_provider.embed_text(query_text)
        candidate_limit = rerank_candidate_limit(limit_value)
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
            min_score=positive_int(
                config_value("RAG_MIN_SCORE", DEFAULT_RAG_MIN_SCORE),
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
            *filter_decisions(
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
            if not matches_filters(document, filters):
                continue
            quality_gate = retrieval_quality_gate_for_document(document)
            if not quality_gate.allowed:
                quality_filtered += 1
                log_vector_filter_decision("quality", document, chunk, quality_gate.reason)
                continue
            if not can_user_read_knowledge_document(user, document):
                permission_filtered += 1
                visibility = source_visibility_decision(user, document)
                log_vector_filter_decision("permission", document, chunk, visibility.reason)
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
                log_vector_filter_decision(
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
                    metadata=knowledge_metadata(document, chunk, score=score),
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
    parsed_machine_id = optional_int(machine_id)
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


def is_postgresql():
    """Return whether the current SQLAlchemy bind is PostgreSQL."""
    if not has_app_context():
        return False
    return db.engine.url.get_backend_name() == "postgresql"
