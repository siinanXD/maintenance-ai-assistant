"""MongoDB Atlas Vector Search backend with a circuit breaker for unreachable clusters."""

import logging
import uuid
from time import monotonic, perf_counter

from app.services.atlas_health_service import ATLAS_VECTOR_FIELD, atlas_embedding_dimensions
from app.services.embedding_service import get_embedding_provider
from app.services.retrieval_debug_service import (
    empty_retrieval_debug,
    retrieval_debug_decision,
)
from app.services.vector_store_common import (
    DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS,
    DEFAULT_RAG_TOP_K,
    BaseVectorStore,
    VectorSearchResult,
    VectorStoreError,
    config_value,
    filter_visible_results,
    optional_int,
    positive_int,
    rerank_candidate_limit,
    safe_vector_metadata,
)
from app.services.vector_store_sql import SqlAlchemyKnowledgeVectorStore
from app.services.vector_sync_status_service import (
    record_atlas_error,
    record_atlas_fallback,
    record_atlas_query,
    set_atlas_vector_count,
)

logger = logging.getLogger(__name__)

# Circuit breaker for unreachable Atlas clusters. Building the client pings the
# cluster and waits up to MONGODB_ATLAS_TIMEOUT_MS; a single request can build
# several stores, so an unreachable cluster used to stall one page for 40 s.
_atlas_circuit = {"open_until": 0.0, "reason": ""}


class MongoAtlasVectorStore(BaseVectorStore):
    """Use MongoDB Atlas Vector Search as an external candidate store."""

    name = "mongodb_atlas"

    def __init__(self, embedding_provider=None):
        """Initialize the Atlas Vector Search adapter from Flask config."""
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.uri = str(config_value("MONGODB_ATLAS_URI", "") or "").strip()
        self.database_name = str(config_value("MONGODB_ATLAS_DATABASE", "") or "").strip()
        self.collection_name = str(
            config_value("MONGODB_ATLAS_VECTOR_COLLECTION", "") or ""
        ).strip()
        self.index_name = str(config_value("MONGODB_ATLAS_VECTOR_INDEX", "") or "").strip()
        self.timeout_ms = positive_int(
            config_value("MONGODB_ATLAS_TIMEOUT_MS", 3000),
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
                metadata = safe_vector_metadata(record.metadata)
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
        parsed_id = optional_int(document_id)
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
        parsed_id = optional_int(document_id)
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
        limit_value = positive_int(limit, config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        candidate_limit = rerank_candidate_limit(limit_value)
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
        results = filter_visible_results(
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


def atlas_circuit_reason():
    """Return why Atlas is skipped right now, empty when the circuit is closed."""
    return _atlas_circuit["reason"] if atlas_circuit_open() else ""


def atlas_circuit_open():
    """Return whether Atlas connections are currently skipped after a failure."""
    return monotonic() < _atlas_circuit["open_until"]


def open_atlas_circuit(reason):
    """Skip Atlas connection attempts for the configured cooldown."""
    cooldown = positive_int(
        config_value("MONGODB_ATLAS_RETRY_COOLDOWN_SECONDS", DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS),
        DEFAULT_ATLAS_RETRY_COOLDOWN_SECONDS,
    )
    _atlas_circuit["open_until"] = monotonic() + cooldown
    _atlas_circuit["reason"] = reason
    logger.warning("atlas_circuit_open reason=%s cooldown_seconds=%s", reason, cooldown)


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
