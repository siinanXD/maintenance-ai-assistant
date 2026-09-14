"""Pick the configured vector store: pgvector, local SQLAlchemy, Chroma or MongoDB Atlas."""

import logging

from app.services.vector_store_atlas import (
    MongoAtlasVectorStore,
    atlas_circuit_open,
    atlas_circuit_reason,
    open_atlas_circuit,
)
from app.services.vector_store_chroma import ChromaVectorStore
from app.services.vector_store_common import VectorStoreError, config_value, safe_fallback_reason
from app.services.vector_store_sql import (
    FallbackVectorStore,
    PgVectorKnowledgeVectorStore,
    SqlAlchemyKnowledgeVectorStore,
    is_postgresql,
)
from app.services.vector_sync_status_service import (
    record_atlas_fallback,
)

logger = logging.getLogger(__name__)


def get_vector_store():
    """Return the configured vector store with a local fallback."""
    store_name = config_value("RAG_VECTOR_STORE", "pgvector").lower()
    if store_name == "pgvector":
        if is_postgresql():
            return PgVectorKnowledgeVectorStore()
        logger.info("vector_store_fallback store=pgvector reason=non_postgresql_database")
        return SqlAlchemyKnowledgeVectorStore()
    if store_name in {"local", "sqlalchemy", "knowledge"}:
        return SqlAlchemyKnowledgeVectorStore()
    if store_name == "chroma":
        try:
            return ChromaVectorStore(
                persist_directory=config_value("CHROMA_PERSIST_DIR", "data/chroma"),
                collection_name=config_value("CHROMA_COLLECTION", "maintenance_knowledge"),
            )
        except VectorStoreError:
            logger.exception("vector_store_fallback store=chroma")
            return SqlAlchemyKnowledgeVectorStore()
    if store_name in {"mongodb_atlas", "mongo_atlas", "atlas"}:
        if atlas_circuit_open():
            return FallbackVectorStore("mongodb_atlas", atlas_circuit_reason())
        try:
            return MongoAtlasVectorStore()
        except VectorStoreError as exc:
            reason = safe_fallback_reason(exc)
            record_atlas_fallback(reason)
            logger.warning("vector_store_fallback store=mongodb_atlas reason=%s", reason)
            if reason == "connection_failed":
                open_atlas_circuit(reason)
        return FallbackVectorStore("mongodb_atlas", reason)
    logger.warning("vector_store_fallback store=%s reason=unsupported_store", store_name)
    return SqlAlchemyKnowledgeVectorStore()
