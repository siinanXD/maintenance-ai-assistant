"""Tests for vector-store drift and synchronization observability."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import KnowledgeChunk, KnowledgeDocument, Role
from app.services import vector_store_service
from app.services.knowledge_indexing_service import sync_vector_store_document
from app.services.knowledge_service import knowledge_index_status
from app.services.vector_store_service import (
    MongoAtlasVectorStore,
    VectorRecord,
    get_vector_store,
)
from app.services.vector_sync_status_service import (
    clear_vector_sync_observability,
    record_atlas_error,
    record_atlas_query,
    record_vector_sync_failure,
    set_atlas_vector_count,
)


@pytest.fixture(autouse=True)
def clear_vector_sync_state():
    """Keep in-process vector sync telemetry isolated per test."""
    clear_vector_sync_observability()
    yield
    clear_vector_sync_observability()


def test_vector_store_status_detects_stale_documents(app):
    """Verify stale documents are visible and trigger a reindex recommendation."""
    with app.app_context():
        _create_knowledge_document(
            title="VS900 stale source",
            status="stale",
            chunk_count=1,
            chunk_rows=0,
        )
        db.session.commit()

        vector_status = knowledge_index_status()["vector_store"]

    assert vector_status["stale_document_count"] == 1
    assert vector_status["pending_reindex_count"] == 1
    assert vector_status["reindex_recommended"] is True
    assert "stale_documents" in vector_status["reindex_reasons"]
    assert vector_status["stale_documents"][0]["source_type"] == "upload"
    assert "title" not in vector_status["stale_documents"][0]


def test_vector_store_status_detects_declared_chunk_mismatch(app):
    """Verify declared chunk counts and persisted chunks are compared."""
    with app.app_context():
        document = _create_knowledge_document(
            title="VS901 chunk mismatch",
            status="indexed",
            chunk_count=2,
            chunk_rows=1,
        )
        db.session.commit()

        vector_status = knowledge_index_status()["vector_store"]

    mismatch = vector_status["chunk_mismatches"][0]
    assert vector_status["chunk_mismatch_count"] == 1
    assert vector_status["chunk_vector_count_mismatch"] is True
    assert vector_status["reindex_recommended"] is True
    assert "chunk_count_mismatch" in vector_status["reindex_reasons"]
    assert mismatch["id"] == document.id
    assert mismatch["declared_chunk_count"] == 2
    assert mismatch["db_chunk_count"] == 1


def test_vector_store_status_detects_missing_chunks(app):
    """Verify indexed documents without persisted chunks are reported."""
    with app.app_context():
        document = _create_knowledge_document(
            title="VS902 missing chunks",
            status="indexed",
            chunk_count=1,
            chunk_rows=0,
        )
        db.session.commit()

        vector_status = knowledge_index_status()["vector_store"]

    missing = vector_status["missing_chunks"][0]
    assert vector_status["missing_chunk_count"] == 1
    assert vector_status["reindex_recommended"] is True
    assert "missing_chunks" in vector_status["reindex_reasons"]
    assert missing["id"] == document.id
    assert missing["declared_chunk_count"] == 1
    assert missing["db_chunk_count"] == 0


def test_vector_store_status_exposes_sync_failures_without_content(app):
    """Verify external sync failures are visible without document text or titles."""
    with app.app_context():
        record_vector_sync_failure(
            document_id=321,
            store_name="chroma",
            error=RuntimeError("sync failed for backend"),
        )

        vector_status = knowledge_index_status()["vector_store"]

    failure = vector_status["sync_failures"][0]
    assert vector_status["vector_sync_failure_count"] == 1
    assert vector_status["last_failed_sync"]["document_id"] == 321
    assert vector_status["reindex_recommended"] is True
    assert "vector_sync_failures" in vector_status["reindex_reasons"]
    assert failure["store"] == "chroma"
    assert "document_text" not in failure
    assert "title" not in failure


def test_vector_store_status_exposes_atlas_observability(app):
    """Verify Atlas metrics are visible even when Atlas falls back locally."""
    app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
    with app.app_context():
        record_atlas_query(42)
        record_atlas_error(RuntimeError("atlas timeout with secret mongodb://hidden"))
        set_atlas_vector_count(7)
        record_vector_sync_failure(
            document_id=654,
            store_name="mongodb_atlas",
            error=RuntimeError("atlas sync failed"),
        )

        vector_status = knowledge_index_status()["vector_store"]

    assert vector_status["configured_store"] == "mongodb_atlas"
    assert vector_status["fallback_active"] is True
    assert vector_status["external_sync_required"] is True
    assert vector_status["reindex_recommended"] is True
    assert vector_status["atlas_queries"] == 1
    assert vector_status["atlas_errors"] == 1
    assert vector_status["atlas_latency"] == 42
    assert vector_status["atlas_fallbacks"] == 1
    assert vector_status["atlas_sync_failures"] == 1
    assert vector_status["atlas_vector_count"] == 7
    assert vector_status["atlas_reindex_required"] is True
    assert vector_status["atlas"]["privacy"]["stores_secrets"] is False
    assert "hidden" not in str(vector_status["atlas"])


def test_vector_store_status_works_when_rag_is_disabled(app):
    """Verify RAG-disabled status still reports structured index diagnostics."""
    app.config["RAG_ENABLED"] = False
    with app.app_context():
        _create_knowledge_document(
            title="VS903 rag disabled",
            status="indexed",
            chunk_count=1,
            chunk_rows=1,
        )
        db.session.commit()

        status = knowledge_index_status()

    assert status["diagnostics"]["rag_enabled"] is False
    assert status["vector_store"]["store"] == "local_knowledge"
    assert status["vector_store"]["expected_vector_count"] == 1
    assert status["vector_store"]["reindex_recommended"] is False


def test_admin_knowledge_status_includes_vector_observability(
    client,
    make_user,
    auth_headers,
):
    """Verify the admin status endpoint exposes vector drift metadata."""
    admin = make_user(
        username="vector_status_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    with client.application.app_context():
        _create_knowledge_document(
            title="VS904 admin status",
            status="indexed",
            chunk_count=1,
            chunk_rows=1,
        )
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/knowledge/status",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    vector_status = payload["vector_store"]
    assert response.status_code == 200
    assert vector_status["store"] == "local_knowledge"
    assert vector_status["expected_vector_count"] == 1
    assert vector_status["missing_chunk_count"] == 0
    assert vector_status["privacy"]["exposes_document_text"] is False


def test_admin_ai_dashboard_contains_atlas_metric_hooks():
    """Verify the Admin AI technical dashboard renders Atlas KPI hooks."""
    root = Path(__file__).resolve().parents[1]
    section_source = (
        root / "frontend" / "src" / "admin-ai" / "components" / "AdminAiTechnicalDiagnostics.tsx"
    ).read_text(encoding="utf-8")
    model_source = (root / "frontend" / "src" / "admin-ai" / "adminAiTechnicalModel.ts").read_text(
        encoding="utf-8"
    )

    for key in (
        "atlas_queries",
        "atlas_errors",
        "atlas_latency",
        "atlas_fallbacks",
        "atlas_sync_failures",
        "atlas_vector_count",
        "atlas_reindex_required",
    ):
        assert key in section_source
        assert key in model_source


def test_atlas_vector_store_is_selected_when_configured(app, monkeypatch):
    """Verify mongodb_atlas creates the Atlas adapter when config is complete."""
    fake_collection = _install_fake_pymongo(monkeypatch)
    _configure_atlas(app)

    with app.app_context():
        store = get_vector_store()

    assert isinstance(store, MongoAtlasVectorStore)
    assert store.name == "mongodb_atlas"
    assert store.collection is fake_collection


def test_atlas_missing_config_falls_back_locally(app):
    """Verify missing Atlas configuration activates the local fallback."""
    app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
    app.config["MONGODB_ATLAS_URI"] = ""

    with app.app_context():
        store = get_vector_store()
        vector_status = knowledge_index_status()["vector_store"]

    assert store.name == "local_knowledge"
    assert vector_status["fallback_active"] is True
    assert vector_status["atlas_fallbacks"] == 1
    assert vector_status["atlas_reindex_required"] is True


def test_atlas_connection_error_fallback_does_not_leak_secret(app, monkeypatch, caplog):
    """Verify connection failures fall back without logging the Atlas URI."""
    secret_uri = "mongodb+srv://app_user:secret-password@example.mongodb.net"
    _install_fake_pymongo(
        monkeypatch,
        client_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret_uri)),
    )
    _configure_atlas(app, uri=secret_uri)

    with app.app_context(), caplog.at_level("WARNING"):
        store = get_vector_store()

    assert store.name == "local_knowledge"
    assert "secret-password" not in caplog.text
    assert secret_uri not in caplog.text
    assert "connection_failed" in caplog.text


def test_unreachable_atlas_is_tried_once_then_skipped_until_cooldown_ends(app, monkeypatch):
    """Verify one connection failure stops further Atlas pings for the cooldown."""
    attempts = []

    def failing_client(*_args, **_kwargs):
        attempts.append(1)
        raise RuntimeError("server selection timeout")

    _install_fake_pymongo(monkeypatch, client_factory=failing_client)
    _configure_atlas(app)
    app.config["MONGODB_ATLAS_RETRY_COOLDOWN_SECONDS"] = 300

    with app.app_context():
        stores = [get_vector_store() for _ in range(4)]

    assert len(attempts) == 1
    assert all(store.name == "local_knowledge" for store in stores)
    assert vector_store_service.atlas_circuit_open() is True

    vector_store_service.reset_atlas_circuit()
    with app.app_context():
        get_vector_store()

    assert len(attempts) == 2


def test_missing_atlas_config_does_not_open_the_circuit(app):
    """Verify only connection failures pause Atlas; config errors fail fast anyway."""
    app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
    app.config["MONGODB_ATLAS_URI"] = ""

    with app.app_context():
        get_vector_store()

    assert vector_store_service.atlas_circuit_open() is False


def test_atlas_upsert_contains_safe_payload_and_existing_embedding(app, monkeypatch):
    """Verify Atlas upserts stable records without secret-like metadata keys."""
    fake_collection = _install_fake_pymongo(monkeypatch)
    _configure_atlas(app)
    embedding = [0.01] * 1536

    with app.app_context():
        store = MongoAtlasVectorStore()
        stored_ids = store.add_documents(
            [
                VectorRecord(
                    text="Presse 7 Hydraulik pruefen",
                    record_id="knowledge:7:0",
                    embedding=embedding,
                    metadata={
                        "id": 7,
                        "chunk_id": 99,
                        "title": "Presse 7",
                        "api_key": "should-not-be-stored",
                    },
                )
            ]
        )

    payload = fake_collection.replacements[0][1]
    assert stored_ids == ["knowledge:7:0"]
    assert payload["record_id"] == "knowledge:7:0"
    assert payload["document_id"] == 7
    assert payload["chunk_id"] == 99
    assert payload["text"] == "Presse 7 Hydraulik pruefen"
    assert payload["embedding"] == embedding
    assert "api_key" not in payload["metadata"]


def test_sync_vector_store_document_reuses_chunk_embeddings(app, monkeypatch):
    """Verify vector-store sync passes existing KnowledgeChunk embeddings through."""
    fake_store = _RecordingAtlasStore()
    monkeypatch.setattr(
        "app.services.vector_store_service.get_vector_store",
        lambda: fake_store,
    )
    app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
    embedding = [0.02] * 1536

    with app.app_context():
        document = _create_knowledge_document(
            title="VS905 atlas sync",
            status="indexed",
            chunk_count=0,
            chunk_rows=0,
        )
        chunk = KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            text="Atlas Sync verwendet vorhandenes Embedding.",
            token_text="atlas sync vorhandenes embedding",
            embedding=embedding,
            created_at=utc_now(),
        )
        db.session.add(chunk)
        db.session.flush()

        sync_vector_store_document(document, [chunk])

    assert fake_store.deleted_document_ids == [document.id]
    assert len(fake_store.records) == 1
    assert fake_store.records[0].embedding == embedding
    assert fake_store.records[0].record_id == f"knowledge:{document.id}:0"


def test_atlas_retrieval_builds_vector_search_pipeline(app, monkeypatch):
    """Verify Atlas retrieval sends the expected $vectorSearch pipeline."""
    fake_collection = _install_fake_pymongo(monkeypatch)
    _configure_atlas(app)

    with app.app_context():
        app.config["RAG_TOP_K"] = 4
        app.config["RAG_RERANK_CANDIDATE_LIMIT"] = 20
        store = MongoAtlasVectorStore(
            embedding_provider=SimpleNamespace(embed_text=lambda _text: [0.03] * 1536)
        )
        results = store.similarity_search("Hydraulikdruck E104", user=None, limit=4)

    pipeline = fake_collection.pipelines[0]
    vector_stage = pipeline[0]["$vectorSearch"]
    assert results == []
    assert vector_stage["index"] == "knowledge_vector_index"
    assert vector_stage["path"] == "embedding"
    assert vector_stage["queryVector"] == [0.03] * 1536
    assert vector_stage["numCandidates"] == 20
    assert vector_stage["limit"] == 20
    assert pipeline[1]["$project"]["score"] == {"$meta": "vectorSearchScore"}


def test_atlas_similarity_search_applies_metadata_prefilter(app, monkeypatch):
    """Verify Atlas vector search passes safe metadata pre-filters."""
    fake_collection = _install_fake_pymongo(monkeypatch)
    _configure_atlas(app)

    with app.app_context():
        store = MongoAtlasVectorStore(
            embedding_provider=SimpleNamespace(embed_text=lambda _text: [0.03] * 1536)
        )
        store.similarity_search(
            "Hydraulikdruck E104",
            user=None,
            limit=4,
            filters={"department": "Produktion", "machine_id": 4},
        )

    vector_stage = fake_collection.pipelines[0][0]["$vectorSearch"]
    assert vector_stage["filter"] == {
        "$and": [
            {"metadata.department": "Produktion"},
            {"metadata.machine_id": 4},
        ]
    }


def test_atlas_candidates_still_pass_sql_status_gate(app, monkeypatch):
    """Verify Atlas candidates are rejected when SQL source status is not indexed."""
    fake_collection = _install_fake_pymongo(monkeypatch)
    _configure_atlas(app)

    with app.app_context():
        document = _create_knowledge_document(
            title="VS906 draft atlas source",
            status="draft",
            chunk_count=1,
            chunk_rows=1,
        )
        db.session.commit()
        fake_collection.aggregate_results = [
            {
                "record_id": f"knowledge:{document.id}:0",
                "document_id": document.id,
                "chunk_id": 1,
                "text": "Draft source must not be returned.",
                "metadata": {"id": document.id, "chunk_id": 1},
                "score": 0.98,
            }
        ]
        store = MongoAtlasVectorStore(
            embedding_provider=SimpleNamespace(embed_text=lambda _text: [0.04] * 1536)
        )
        results = store.similarity_search("draft source", user=None, limit=4)

    assert results == []
    assert store.last_debug()["vector_candidates_found"] == 1


def test_atlas_vector_count_diagnostics_detect_mismatch(app, monkeypatch):
    """Verify Atlas counts participate in vector drift diagnostics."""
    fake_collection = _install_fake_pymongo(monkeypatch, collection_count=0)
    _configure_atlas(app)

    with app.app_context():
        _create_knowledge_document(
            title="VS907 atlas count mismatch",
            status="indexed",
            chunk_count=1,
            chunk_rows=1,
        )
        db.session.commit()

        vector_status = knowledge_index_status()["vector_store"]

    assert fake_collection.count_filters
    assert vector_status["store"] == "mongodb_atlas"
    assert vector_status["actual_vector_count"] == 0
    assert vector_status["expected_vector_count"] == 1
    assert vector_status["chunk_vector_count_mismatch"] is True
    assert "vector_count_mismatch" in vector_status["reindex_reasons"]
    assert vector_status["atlas_vector_count"] == 0


def test_atlas_configuration_is_documented():
    """Verify README, docs and env examples include Atlas setup and reindex notes."""
    root = Path(__file__).resolve().parents[1]
    readme = (root / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    env_minimal = (root / ".env.minimal.example").read_text(encoding="utf-8")
    env_production = (root / ".env.production.example").read_text(encoding="utf-8")
    atlas_doc = (root / "docs" / "MONGODB_ATLAS_VECTOR_SEARCH.md").read_text(encoding="utf-8")
    observability_doc = (root / "docs" / "AI_OBSERVABILITY.md").read_text(encoding="utf-8")

    for source in (readme, env_example, env_production, atlas_doc):
        assert "MONGODB_ATLAS_URI" in source
        assert "MONGODB_ATLAS_VECTOR_COLLECTION" in source
        assert "knowledge_vectors" in source
    assert ".env.production.example" in env_minimal
    assert "RAG_STRICT_QUALITY_GATE" in env_production
    assert ".env.production.example" in readme
    assert "Dimensions: 1536" in atlas_doc
    assert "Similarity: cosine" in atlas_doc
    assert "Knowledge documents must be fully reindexed" in atlas_doc
    for key in (
        "atlas_queries",
        "atlas_errors",
        "atlas_latency",
        "atlas_fallbacks",
        "atlas_sync_failures",
        "atlas_vector_count",
        "atlas_reindex_required",
    ):
        assert key in observability_doc
    normalized_observability_doc = " ".join(observability_doc.split())
    assert "do not increment or duplicate AI request counters" in normalized_observability_doc


def _create_knowledge_document(
    *,
    title,
    status,
    chunk_count,
    chunk_rows,
    source_type="upload",
):
    """Create one knowledge document with a controlled chunk-count shape."""
    now = utc_now()
    document = KnowledgeDocument(
        source_type=source_type,
        title=title,
        original_filename=f"{title}.txt",
        relative_path=f"knowledge/{title}.txt",
        content_type="text/plain",
        department="Produktion",
        status=status,
        quality_status="admin_approved",
        is_public=True,
        chunk_count=chunk_count,
        created_at=now,
        updated_at=now,
    )
    db.session.add(document)
    db.session.flush()
    for index in range(chunk_rows):
        db.session.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                text=f"{title} chunk {index}",
                token_text=f"{title.lower()} chunk {index}",
                created_at=now,
            )
        )
    return document


def _configure_atlas(app, uri="mongodb+srv://user:password@example.mongodb.net"):
    """Configure Atlas settings for tests without using a real network."""
    app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
    app.config["MONGODB_ATLAS_URI"] = uri
    app.config["MONGODB_ATLAS_DATABASE"] = "maintenance_ai"
    app.config["MONGODB_ATLAS_VECTOR_COLLECTION"] = "knowledge_vectors"
    app.config["MONGODB_ATLAS_VECTOR_INDEX"] = "knowledge_vector_index"
    app.config["MONGODB_ATLAS_TIMEOUT_MS"] = 100
    app.config["EMBEDDING_PROVIDER"] = "openai"
    app.config["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
    app.config["RAG_EMBEDDING_DIMENSIONS"] = 1536


def _install_fake_pymongo(monkeypatch, client_factory=None, collection_count=0):
    """Install a fake pymongo module and return its collection double."""
    fake_collection = _FakeAtlasCollection(collection_count=collection_count)

    class FakeDatabase:
        """Minimal fake MongoDB database."""

        def __getitem__(self, _collection_name):
            """Return the fake collection."""
            return fake_collection

    class FakeAdmin:
        """Minimal fake MongoDB admin database."""

        def command(self, _command_name):
            """Pretend ping succeeded."""
            return {"ok": 1}

    class FakeClient:
        """Minimal fake MongoClient."""

        admin = FakeAdmin()

        def __init__(self, *_args, **_kwargs):
            """Initialize the fake client."""

        def __getitem__(self, _database_name):
            """Return the fake database."""
            return FakeDatabase()

    factory = client_factory or FakeClient
    pymongo_module = ModuleType("pymongo")
    pymongo_module.MongoClient = factory
    monkeypatch.setitem(sys.modules, "pymongo", pymongo_module)
    return fake_collection


class _FakeAtlasCollection:
    """In-memory collection double for Atlas adapter tests."""

    def __init__(self, collection_count=0):
        """Initialize fake collection state."""
        self.collection_count = collection_count
        self.replacements = []
        self.pipelines = []
        self.aggregate_results = []
        self.deleted_filters = []
        self.count_filters = []

    def replace_one(self, query, payload, upsert=False):
        """Record one upsert operation."""
        self.replacements.append((query, payload, upsert))
        return SimpleNamespace(upserted_id=payload["record_id"])

    def delete_many(self, query):
        """Record one delete operation."""
        self.deleted_filters.append(query)
        return SimpleNamespace(deleted_count=1)

    def count_documents(self, query):
        """Return configured counts for diagnostics."""
        self.count_filters.append(query)
        return self.collection_count

    def aggregate(self, pipeline):
        """Record and return fake vector-search candidates."""
        self.pipelines.append(pipeline)
        return list(self.aggregate_results)


class _RecordingAtlasStore:
    """Fake Atlas store that records synced vector records."""

    name = "mongodb_atlas"

    def __init__(self):
        """Initialize recorded calls."""
        self.deleted_document_ids = []
        self.records = []

    def delete_document(self, document_id):
        """Record deleted document ids."""
        self.deleted_document_ids.append(document_id)
        return 1

    def add_documents(self, records):
        """Record vector records and return their ids."""
        self.records = list(records)
        return [record.record_id for record in self.records]
