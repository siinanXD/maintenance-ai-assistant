"""Chroma vector store backend."""

import uuid

from app.services.embedding_service import get_embedding_provider
from app.services.retrieval_debug_service import (
    empty_retrieval_debug,
    retrieval_debug_decision,
)
from app.services.vector_store_common import (
    DEFAULT_RAG_TOP_K,
    BaseVectorStore,
    VectorSearchResult,
    VectorStoreError,
    config_value,
    filter_visible_results,
    flat_metadata,
    positive_int,
    rerank_candidate_limit,
)


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
        metadatas = [flat_metadata(record.metadata) for record in safe_records]
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
        limit_value = positive_int(limit, config_value("RAG_TOP_K", DEFAULT_RAG_TOP_K))
        query_embedding = self.embedding_provider.embed_text(query_text)
        candidate_limit = rerank_candidate_limit(limit_value)
        response = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_limit,
            where=flat_metadata(filters or {}) or None,
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
