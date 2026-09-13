"""Tests for the modular RAG service layer."""

import json
import math
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config import validate_runtime_config
from app.domain_models.common import utc_now
from app.extensions import db
from app.models import (
    AIFeedback,
    AssistantTrainingEntry,
    Department,
    ErrorEntry,
    InventoryMaterial,
    KnowledgeChunk,
    KnowledgeDocument,
    Machine,
    Priority,
    Role,
    ShiftHandover,
    Task,
    TaskStatus,
    User,
)
from app.services.chunking_service import ChunkingConfig, chunk_text
from app.services.embedding_service import (
    EmbeddingServiceError,
    HashingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    embedding_dimensions_for_provider,
    embedding_provider_status,
    get_embedding_provider,
)
from app.services.knowledge_aging_service import (
    knowledge_aging_state,
    mark_outdated_knowledge_by_age,
)
from app.services.knowledge_quality_service import (
    retrieval_quality_gate_for_status,
)
from app.services.knowledge_service import (
    chunk_vector_metadata,
    rebuild_chunks,
    search_knowledge_chunks,
)
from app.services.knowledge_source_quality_service import (
    chunk_quality_reasons,
    has_bad_ocr_signature,
    latest_chunk_quality_summary,
    reset_chunk_quality_reports,
)
from app.services.retrieval_candidate_service import (
    RetrievalCandidate,
    public_sources_from_candidates,
    vector_result_candidate,
)
from app.services.retrieval_service import knowledge_context_for_chat, retrieve_context
from app.services.technical_entity_service import extract_technical_entities
from app.services.vector_store_service import (
    _flat_metadata,
    _rerank_candidate_limit,
    get_vector_store,
)


def test_validate_runtime_config_accepts_semantic_chunking_defaults():
    """Verify supported semantic chunking settings pass startup validation."""
    validate_runtime_config(
        {
            "TESTING": True,
            "RAG_CHUNKING_MODE": "hybrid_semantic",
            "RAG_CHUNK_SIZE": 1400,
            "RAG_CHUNK_OVERLAP": 160,
            "RAG_SEMANTIC_BREAKPOINT_THRESHOLD": 0.35,
            "RAG_SEMANTIC_MIN_CHUNK_CHARS": 600,
            "RAG_SEMANTIC_TARGET_CHUNK_CHARS": 1200,
            "RAG_SEMANTIC_MAX_CHUNK_CHARS": 1800,
            "RAG_TOP_K": 4,
            "RAG_RERANK_CANDIDATE_LIMIT": 20,
            "RAG_SEMANTIC_ONLY_MIN_SIMILARITY": 0.78,
        }
    )


def test_validate_runtime_config_rejects_invalid_chunking_mode():
    """Verify unsupported chunking modes fail before indexing starts."""
    with pytest.raises(RuntimeError, match="RAG_CHUNKING_MODE"):
        validate_runtime_config(
            {
                "TESTING": True,
                "RAG_CHUNKING_MODE": "fixed_windows",
                "RAG_CHUNK_SIZE": 1400,
                "RAG_CHUNK_OVERLAP": 160,
                "RAG_SEMANTIC_BREAKPOINT_THRESHOLD": 0.35,
                "RAG_SEMANTIC_MIN_CHUNK_CHARS": 600,
                "RAG_SEMANTIC_TARGET_CHUNK_CHARS": 1200,
                "RAG_SEMANTIC_MAX_CHUNK_CHARS": 1800,
                "RAG_TOP_K": 4,
                "RAG_RERANK_CANDIDATE_LIMIT": 20,
                "RAG_SEMANTIC_ONLY_MIN_SIMILARITY": 0.78,
            }
        )


def test_validate_runtime_config_accepts_legacy_fixed_chunking_mode():
    """Verify the migration fallback chunking mode is accepted."""
    validate_runtime_config(
        {
            "TESTING": True,
            "RAG_CHUNKING_MODE": "legacy_fixed",
            "RAG_CHUNK_SIZE": 1400,
            "RAG_CHUNK_OVERLAP": 160,
            "RAG_SEMANTIC_BREAKPOINT_THRESHOLD": 0.35,
            "RAG_SEMANTIC_MIN_CHUNK_CHARS": 600,
            "RAG_SEMANTIC_TARGET_CHUNK_CHARS": 1200,
            "RAG_SEMANTIC_MAX_CHUNK_CHARS": 1800,
            "RAG_TOP_K": 4,
            "RAG_RERANK_CANDIDATE_LIMIT": 20,
            "RAG_SEMANTIC_ONLY_MIN_SIMILARITY": 0.78,
        }
    )


def test_validate_runtime_config_rejects_invalid_semantic_threshold():
    """Verify semantic breakpoint thresholds stay in the supported range."""
    with pytest.raises(RuntimeError, match="RAG_SEMANTIC_BREAKPOINT_THRESHOLD"):
        validate_runtime_config(
            {
                "TESTING": True,
                "RAG_CHUNKING_MODE": "hybrid_semantic",
                "RAG_CHUNK_SIZE": 1400,
                "RAG_CHUNK_OVERLAP": 160,
                "RAG_SEMANTIC_BREAKPOINT_THRESHOLD": 1.5,
                "RAG_SEMANTIC_MIN_CHUNK_CHARS": 600,
                "RAG_SEMANTIC_TARGET_CHUNK_CHARS": 1200,
                "RAG_SEMANTIC_MAX_CHUNK_CHARS": 1800,
                "RAG_TOP_K": 4,
                "RAG_RERANK_CANDIDATE_LIMIT": 20,
                "RAG_SEMANTIC_ONLY_MIN_SIMILARITY": 0.78,
            }
        )


def test_validate_runtime_config_rejects_invalid_semantic_only_similarity():
    """Verify semantic-only retrieval thresholds stay in the supported range."""
    with pytest.raises(RuntimeError, match="RAG_SEMANTIC_ONLY_MIN_SIMILARITY"):
        validate_runtime_config(
            {
                "TESTING": True,
                "RAG_CHUNKING_MODE": "hybrid_semantic",
                "RAG_CHUNK_SIZE": 1400,
                "RAG_CHUNK_OVERLAP": 160,
                "RAG_SEMANTIC_BREAKPOINT_THRESHOLD": 0.35,
                "RAG_SEMANTIC_MIN_CHUNK_CHARS": 600,
                "RAG_SEMANTIC_TARGET_CHUNK_CHARS": 1200,
                "RAG_SEMANTIC_MAX_CHUNK_CHARS": 1800,
                "RAG_TOP_K": 4,
                "RAG_RERANK_CANDIDATE_LIMIT": 20,
                "RAG_SEMANTIC_ONLY_MIN_SIMILARITY": 1.5,
            }
        )


def test_chunk_text_preserves_metadata_and_overlap():
    """Verify chunking returns metadata-ready overlapping chunks."""
    text = "Hydraulikfilter X900 taeglich pruefen. " * 25
    chunks = chunk_text(
        text,
        metadata={"machine_id": 7, "document_type": "manual"},
        config=ChunkingConfig(max_chars=240, overlap=40, max_chunks=10),
    )

    assert len(chunks) > 1
    assert chunks[0]["metadata"]["machine_id"] == 7
    assert chunks[0]["metadata"]["document_type"] == "manual"
    assert chunks[0]["metadata"]["chunk_index"] == 0
    assert chunks[0]["metadata"]["chunk_char_count"] == len(chunks[0]["text"])
    assert chunks[0]["metadata"]["chunk_line_count"] >= 1
    assert chunks[0]["metadata"]["chunk_token_count"] >= 1
    assert "Hydraulikfilter" in chunks[1]["text"]


def test_chunk_text_preserves_section_headings_steps_and_tables():
    """Verify section-aware chunking keeps headings, steps, and tables together."""
    text = "\n".join(
        (
            "Wartungsschritte:",
            "1. Anlage stoppen und gegen Wiedereinschalten sichern.",
            "2. Filter X900 ausbauen und Dichtung pruefen.",
            "3. Filter X900 einsetzen und Befund dokumentieren.",
            "",
            "Ersatzteile:",
            "| Teil | Menge |",
            "| Filter X900 | 1 |",
            "| Dichtung D4 | 1 |",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(max_chars=220, overlap=40, max_chunks=5),
    )

    step_chunk = chunks[0]
    table_chunk = chunks[1]
    assert step_chunk["metadata"]["section_title"] == "Wartungsschritte"
    assert step_chunk["metadata"]["chunk_block_count"] == 1
    assert step_chunk["metadata"]["chunk_block_kinds"] == "list"
    assert "1. Anlage stoppen" in step_chunk["text"]
    assert "2. Filter X900 ausbauen" in step_chunk["text"]
    assert "3. Filter X900 einsetzen" in step_chunk["text"]
    assert table_chunk["metadata"]["section_title"] == "Ersatzteile"
    assert table_chunk["metadata"]["chunk_block_kinds"] == "table"
    assert "| Filter X900 | 1 |" in table_chunk["text"]
    assert [chunk["metadata"]["chunk_order"] for chunk in chunks] == [0, 1]
    assert [chunk["metadata"]["source_offset"] for chunk in chunks] == sorted(
        chunk["metadata"]["source_offset"] for chunk in chunks
    )


def test_semantic_chunk_text_stores_section_hierarchy_metadata():
    """Verify heading hierarchy is stored for future re-indexing and auditing."""
    text = "\n".join(
        (
            "# Hydrauliksystem",
            "Allgemeine Hinweise zur Anlage.",
            "",
            "## Sicherheit",
            "Anlage abschalten und Druck ablassen.",
            "",
            "## Wartung",
            "- Filter pruefen.",
            "- Dichtung tauschen.",
        )
    )

    chunks = chunk_text(
        text,
        metadata={"document_type": "manual"},
        config=ChunkingConfig(max_chars=400, overlap=40, max_chunks=8),
    )

    safety_chunk = next(chunk for chunk in chunks if "Druck ablassen" in chunk["text"])
    maintenance_chunk = next(chunk for chunk in chunks if "Filter pruefen" in chunk["text"])
    assert safety_chunk["metadata"]["chunk_schema_version"] == "semantic_structure_v1"
    assert safety_chunk["metadata"]["section_title"] == "Sicherheit"
    assert safety_chunk["metadata"]["parent_section_title"] == "Hydrauliksystem"
    assert safety_chunk["metadata"]["section_level"] == 2
    assert safety_chunk["metadata"]["chunk_hierarchy"] == ["Hydrauliksystem", "Sicherheit"]
    assert safety_chunk["metadata"]["hierarchy_path"] == "Hydrauliksystem > Sicherheit"
    assert maintenance_chunk["metadata"]["semantic_chunk_type"] == "maintenance_instruction"
    assert maintenance_chunk["metadata"]["document_type"] == "manual"


def test_semantic_chunk_text_marks_procedures_and_maintenance_instructions():
    """Verify procedures and maintenance instructions become explicit semantic chunks."""
    text = "\n".join(
        (
            "Wartungsanweisung:",
            "Schritt 1: Hauptschalter ausschalten.",
            "Schritt 2: Sensor S12 reinigen.",
            "Schritt 3: Testlauf dokumentieren.",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(max_chars=300, overlap=40, max_chunks=4),
    )

    assert len(chunks) == 1
    assert chunks[0]["metadata"]["section_title"] == "Wartungsanweisung"
    assert chunks[0]["metadata"]["chunk_block_kinds"] == "list"
    assert chunks[0]["metadata"]["semantic_chunk_type"] == "procedure"
    assert chunks[0]["metadata"]["semantic_boundary"] == "procedure"


def test_hybrid_semantic_chunking_splits_topic_changes():
    """Verify hybrid semantic chunking can split paragraph-level topic changes."""
    text = "\n\n".join(
        (
            "Hydraulikpumpe HP900 pruefen. Druckleitung entlueften und "
            "Manometerwert dokumentieren. Hydraulikfilter kontrollieren.",
            "Schaltschrank Temperatur pruefen. Luefter reinigen und SPS Diagnose "
            "auslesen. Elektrische Klemmen durch Fachpersonal kontrollieren.",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(
            max_chars=1000,
            overlap=40,
            max_chunks=5,
            mode="hybrid_semantic",
            semantic_breakpoint_threshold=0.05,
            semantic_min_chars=100,
            semantic_target_chars=110,
            semantic_max_chars=500,
        ),
    )

    assert len(chunks) == 2
    assert "Hydraulikpumpe" in chunks[0]["text"]
    assert "Schaltschrank" in chunks[1]["text"]
    assert chunks[0]["metadata"]["chunking_mode"] == "hybrid_semantic"
    assert chunks[0]["metadata"]["chunk_block_count"] == 1
    assert chunks[0]["metadata"]["chunk_block_kinds"] == "paragraph"
    assert chunks[1]["metadata"]["semantic_group"] == 1


def test_chunk_text_keeps_error_code_block_together():
    """Verify error-code context remains in one chunk when possible."""
    text = "\n".join(
        (
            "Fehlercode E-410",
            "Ursache: Naeherungsschalter S4 liefert kein Signal.",
            "Abhilfe: Sensorposition pruefen, Kabel sichtpruefen und Testlauf dokumentieren.",
            "",
            "Hinweis:",
            "Nur freigegebene Ersatzteile verwenden.",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(max_chars=240, overlap=40, max_chunks=5),
    )

    assert "Fehlercode E-410" in chunks[0]["text"]
    assert "Ursache: Naeherungsschalter" in chunks[0]["text"]
    assert "Abhilfe: Sensorposition" in chunks[0]["text"]
    assert chunks[0]["metadata"]["semantic_chunk_type"] == "error_catalog_entry"
    assert chunks[0]["metadata"]["semantic_boundary"] == "error_catalog_entry"


def test_chunk_text_keeps_slightly_oversized_error_code_block_intact():
    """Verify protected error-code blocks are not split just because they exceed budget."""
    text = "\n".join(
        (
            "Fehlercode FX-451",
            "Ursache: Frequenzumrichter meldet Unterspannung am Zwischenkreis.",
            "Abhilfe: Anlage sichern, Spannungsversorgung durch Fachpersonal pruefen, "
            "Klemmenplan heranziehen, Messwerte dokumentieren und erst nach Freigabe "
            "einen kontrollierten Testlauf starten.",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(max_chars=220, overlap=40, max_chunks=5),
    )

    assert len(chunks) == 1
    assert len(chunks[0]["text"]) > 220
    assert "Fehlercode FX-451" in chunks[0]["text"]
    assert "Unterspannung" in chunks[0]["text"]
    assert "kontrollierten Testlauf" in chunks[0]["text"]


def test_chunk_text_repeats_table_header_when_splitting_large_tables():
    """Verify large technical tables remain understandable after chunk splitting."""
    text = "\n".join(
        (
            "Messwerttabelle:",
            "| Fehlercode | Symptom | Pruefung |",
            "| --- | --- | --- |",
            "| TB-100 | Sensor kein Signal | Kabel pruefen und Abstand messen |",
            "| TB-101 | Druck zu niedrig | Filter und Ventil pruefen |",
            "| TB-102 | Motor zu warm | Luefter und Lastprofil pruefen |",
            "| TB-103 | SPS Timeout | Netzwerk und SPS Diagnose pruefen |",
            "| TB-104 | FU Stoerung | Frequenzumrichter Diagnose lesen |",
        )
    )

    chunks = chunk_text(
        text,
        config=ChunkingConfig(max_chars=230, overlap=40, max_chunks=8),
    )

    table_chunks = [chunk for chunk in chunks if "Fehlercode" in chunk["text"]]
    assert len(table_chunks) > 1
    assert all("| Fehlercode | Symptom | Pruefung |" in chunk["text"] for chunk in table_chunks)
    assert any("TB-104" in chunk["text"] for chunk in table_chunks)


def test_legacy_fixed_chunking_remains_available_as_migration_fallback():
    """Verify fixed-size character chunking can still be selected during migration."""
    text = "Hydraulikfilter X900 taeglich pruefen. " * 25

    chunks = chunk_text(
        text,
        metadata={"document_type": "manual"},
        config=ChunkingConfig(
            max_chars=240,
            overlap=40,
            max_chunks=10,
            mode="legacy_fixed",
        ),
    )

    assert len(chunks) > 1
    assert chunks[0]["metadata"]["document_type"] == "manual"
    assert chunks[0]["metadata"]["chunk_index"] == 0
    assert "semantic_strategy" not in chunks[0]["metadata"]
    assert "Hydraulikfilter" in chunks[1]["text"]


def test_semantic_chunking_failure_falls_back_to_structured_chunks(monkeypatch):
    """Verify semantic chunking failures keep the existing structured fallback usable."""
    from app.services import semantic_chunking_service

    def failing_semantic_chunk_text(*_args, **_kwargs):
        """Raise like a broken semantic chunker during migration."""
        raise RuntimeError("semantic chunking unavailable")

    monkeypatch.setattr(
        semantic_chunking_service,
        "semantic_chunk_text",
        failing_semantic_chunk_text,
    )
    text = "\n".join(
        (
            "Wartungsschritte:",
            "1. Anlage stoppen.",
            "2. Filter X900 pruefen.",
            "",
            "Ersatzteile:",
            "| Teil | Menge |",
            "| Filter X900 | 1 |",
        )
    )

    chunks = chunk_text(
        text,
        metadata={"document_type": "manual"},
        config=ChunkingConfig(max_chars=220, overlap=40, max_chunks=5),
    )

    assert chunks
    assert chunks[0]["metadata"]["document_type"] == "manual"
    assert chunks[0]["metadata"]["section_title"] == "Wartungsschritte"
    assert chunks[0]["metadata"]["chunk_block_kinds"] == "list"
    assert "chunk_schema_version" not in chunks[0]["metadata"]
    assert any(chunk["metadata"].get("chunk_block_kinds") == "table" for chunk in chunks)


def test_chunk_text_rejects_invalid_overlap():
    """Verify invalid chunking settings fail explicitly."""
    with pytest.raises(ValueError, match="overlap"):
        chunk_text(
            "kurzer Text",
            config=ChunkingConfig(max_chars=240, overlap=240),
        )


def test_hashing_embedding_provider_is_stable_and_normalized():
    """Verify test/fallback embeddings are deterministic and normalized."""
    provider = HashingEmbeddingProvider(dimensions=64)

    first = provider.embed_text("Hydraulikfilter X900 pruefen")
    second = provider.embed_text("Hydraulikfilter X900 pruefen")

    assert first == second
    assert len(first) == 64
    assert math.isclose(sum(value * value for value in first), 1.0)


def test_embedding_provider_status_defaults_to_openai():
    """Verify OpenAI embeddings are the RAG default provider."""
    status = embedding_provider_status({})

    assert status["provider"] == "openai"
    assert status["mode"] == "external"
    assert status["model"] == "text-embedding-3-small"
    assert status["dimensions"] == 1536
    assert status["effective_provider"] == "hashing"
    assert status["fallback_active"] is True
    assert status["production_default"] is True
    assert status["reindex_required_on_provider_change"] is True


def test_get_embedding_provider_uses_openai_as_primary_when_configured(app):
    """Verify configured OpenAI embeddings are the primary production provider."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        provider = get_embedding_provider()

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.name == "openai"
    assert provider.model == "text-embedding-3-small"
    assert provider.expected_dimensions == 1536


def test_get_embedding_provider_falls_back_to_hashing_without_openai_key(app):
    """Verify missing OpenAI credentials fall back locally without hiding the reason."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = ""
        provider = get_embedding_provider()

    assert isinstance(provider, HashingEmbeddingProvider)
    assert provider.configured_provider == "openai"
    assert provider.fallback_reason == "api_key_missing"


def test_hashing_embedding_provider_is_explicit_test_fallback():
    """Verify hashing remains available only as explicit test/offline fallback."""
    status = embedding_provider_status({"EMBEDDING_PROVIDER": "hashing"})

    assert status["provider"] == "hashing"
    assert status["effective_provider"] == "hashing"
    assert status["fallback_active"] is False
    assert status["production_default"] is False
    assert status["dimensions"] == 384
    assert "Tests/offline Fallback" in status["recommended_action"]


def test_embedding_dimension_metadata_for_supported_providers():
    """Verify known embedding dimensions are explicit for provider changes."""
    assert embedding_dimensions_for_provider("hashing", hash_dimensions=384) == 384
    assert embedding_dimensions_for_provider("openai", "text-embedding-3-small") == 1536


def test_openai_embedding_provider_rejects_unexpected_dimensions(app):
    """Verify known OpenAI embedding models validate returned vector dimensions."""
    with app.app_context():
        provider = OpenAIEmbeddingProvider(
            api_key="test-key",
            model="text-embedding-3-small",
        )
    provider.client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=lambda **_kwargs: SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 384)])
        )
    )

    with pytest.raises(EmbeddingServiceError, match="expected 1536"):
        provider.embed_text("Hydraulikfilter X900 pruefen")


def test_reindex_notice_is_documented_for_embedding_provider_changes():
    """Verify docs tell admins to reindex after embedding provider changes."""
    readme = Path("docs/AI_RAG_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert (
        "Nach Änderung des Embedding Providers müssen Knowledge-Dokumente neu indexiert werden."
        in readme
    )


def test_embedding_provider_configuration_documentation_is_current():
    """Verify configuration docs describe OpenAI default and hashing fallback."""
    config_doc = Path("docs/EMBEDDING_PROVIDER_CONFIGURATION.md").read_text(encoding="utf-8")

    assert "EMBEDDING_PROVIDER=openai" in config_doc
    assert "text-embedding-3-small" in config_doc
    assert "1536-dimensional" in config_doc
    assert "hashing" in config_doc
    assert "tests, CI and offline fallback only" in config_doc
    assert "Knowledge documents must be reindexed" in config_doc


def test_openai_compatible_embedding_provider_uses_configured_base_url(app):
    """Verify OpenAI-compatible embedding providers use the configured base URL."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai_compatible"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        provider = get_embedding_provider()

    assert provider.name == "openai_compatible"
    assert str(provider.client.base_url).rstrip("/") == "http://127.0.0.1:11434/v1"


def test_openai_embedding_provider_ignores_local_base_url(app):
    """Verify official OpenAI embeddings do not inherit local compatible base URLs."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        provider = get_embedding_provider()

    assert provider.name == "openai"
    assert str(provider.client.base_url).rstrip("/") != "http://127.0.0.1:11434/v1"


def test_openai_compatible_embedding_provider_falls_back_without_base_url(app):
    """Verify local embeddings remain available when local base URL is missing."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai_compatible"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = ""
        provider = get_embedding_provider()

    assert isinstance(provider, HashingEmbeddingProvider)
    assert provider.configured_provider == "openai_compatible"
    assert provider.fallback_reason == "base_url_missing"


def test_embedding_api_calls_are_centralized_in_embedding_service():
    """Verify retrieval/indexing code does not call embedding APIs directly."""
    service_dir = Path("app/services")
    direct_callers = []
    for path in service_dir.glob("*.py"):
        if path.name == "embedding_service.py":
            continue
        source = path.read_text(encoding="utf-8")
        if ".embeddings.create" in source:
            direct_callers.append(path.name)

    assert direct_callers == []


def test_technical_entity_extraction_combines_catalog_and_rules(app):
    """Verify chunk entity extraction finds machine, error, part, and maintenance signals."""
    with app.app_context():
        department = Department.query.filter_by(name="Instandhaltung").first()
        if not department:
            department = Department(name="Instandhaltung")
        machine = Machine(name="Presse 3", produced_item="Hydraulikteil")
        db.session.add_all([department, machine])
        db.session.flush()
        db.session.add_all(
            [
                InventoryMaterial(
                    name="Hydraulikfilter X900",
                    unit_cost=19.5,
                    quantity=3,
                    machine_id=machine.id,
                ),
                ErrorEntry(
                    machine="Presse 3",
                    error_code="E104",
                    title="Drucksensor meldet kein Signal",
                    department_id=department.id,
                ),
            ],
        )
        db.session.commit()

        entities = extract_technical_entities(
            "Presse 3 meldet Fehler E104 am Drucksensor S12. "
            "Hydraulikfilter X900 reinigen und Ventil pruefen in Instandhaltung.",
        )

    assert "Presse 3" in entities["machines"]
    assert "E104" in entities["error_codes"]
    assert "Hydraulikfilter X900" in entities["inventory_parts"]
    assert "Instandhaltung" in entities["areas"]
    assert "ventil" in entities["components"]
    assert "reinigen" in entities["maintenance_terms"]
    assert any("sensor" in value.lower() for value in entities["sensors"])


def test_rebuild_chunks_persists_technical_entities(app):
    """Verify KnowledgeChunk stores technical entities during indexing."""
    with app.app_context():
        machine = Machine(name="Presse 7", produced_item="Hydraulikteil")
        db.session.add(machine)
        db.session.flush()
        db.session.add(
            InventoryMaterial(
                name="Hydraulikfilter X900",
                unit_cost=21.0,
                quantity=2,
                machine_id=machine.id,
            ),
        )
        document = KnowledgeDocument(
            source_type="upload",
            title="Presse 7 Wartung",
            original_filename="presse-7.txt",
            relative_path="uploads/presse-7.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        rebuild_chunks(
            document,
            "Presse 7 meldet Fehler E-10 am Sensor S12. "
            "Hydraulikfilter X900 tauschen und Ventil pruefen.",
        )
        db.session.commit()

        chunk = KnowledgeChunk.query.filter_by(document_id=document.id).one()
        entities = chunk.entities()
        metadata = chunk_vector_metadata(document, chunk)

    assert "Presse 7" in entities["machines"]
    assert "E-10" in entities["error_codes"]
    assert "Hydraulikfilter X900" in entities["inventory_parts"]
    assert "technical_entities" in metadata
    assert metadata["technical_entities"]["error_codes"] == ["E-10"]
    assert "hydraulikfilter" in chunk.token_text
    assert chunk.embedding is not None


def test_rebuild_chunks_persists_section_metadata(app):
    """Verify indexed chunks keep section metadata for retrieval explainability."""
    with app.app_context():
        document = KnowledgeDocument(
            source_type="upload",
            title="Presse 9 Abschnittstest",
            original_filename="presse-9.txt",
            relative_path="uploads/presse-9.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        rebuild_chunks(
            document,
            "\n".join(
                (
                    "Wartungsschritte:",
                    "1. Presse 9 stoppen.",
                    "2. Sensor S12 reinigen.",
                    "3. Testlauf dokumentieren.",
                )
            ),
        )
        db.session.commit()

        chunk = KnowledgeChunk.query.filter_by(document_id=document.id).one()
        chunk_metadata = chunk.retrieval_metadata()
        vector_metadata = chunk_vector_metadata(document, chunk)

    assert chunk_metadata["section_title"] == "Wartungsschritte"
    assert chunk_metadata["chunk_order"] == 0
    assert chunk_metadata["chunk_block_count"] == 1
    assert chunk_metadata["chunk_block_kinds"] == "list"
    assert chunk_metadata["chunk_schema_version"] == "semantic_structure_v1"
    assert chunk_metadata["semantic_chunk_type"] == "procedure"
    assert chunk_metadata["chunk_hierarchy"] == ["Wartungsschritte"]
    assert chunk_metadata["hierarchy_path"] == "Wartungsschritte"
    assert chunk_metadata["chunk_char_count"] == len(chunk.text)
    assert chunk_metadata["chunk_line_count"] == 4
    assert chunk_metadata["chunk_token_count"] >= 8
    assert vector_metadata["section_title"] == "Wartungsschritte"
    assert vector_metadata["source_section"] == "section-1"
    assert vector_metadata["chunk_char_count"] == len(chunk.text)
    assert vector_metadata["chunk_line_count"] == 4
    assert vector_metadata["chunk_token_count"] >= 8
    assert vector_metadata["chunk_block_count"] == 1
    assert vector_metadata["chunk_block_kinds"] == "list"
    assert "wartungsschritte" in chunk.token_text


def test_chunk_vector_metadata_includes_safe_source_scope_metadata(
    app,
    make_machine,
    make_error_entry,
):
    """Verify external vector records keep safe source scope metadata."""
    machine_id = make_machine(name="Presse Vector Meta", produced_item="Servo")
    error_id = make_error_entry(
        "Presse Vector Meta",
        "VM-100",
        "Vector Metadata Stoerung",
        department_name="Produktion",
        description="VM-100 Sensor pruefen.",
    )
    source_created_at = utc_now() - timedelta(days=5)

    with app.app_context():
        error_entry = db.session.get(ErrorEntry, error_id)
        error_entry.machine_id = machine_id
        error_entry.created_at = source_created_at
        document = KnowledgeDocument(
            source_type="error_entry",
            source_id=error_id,
            title="VM-100 Vector Metadata",
            original_filename="vm-100.txt",
            relative_path="",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        rebuild_chunks(
            document,
            "VM-100 Vector Metadata Sensor Stoerung an Presse Vector Meta.",
        )
        db.session.commit()

        chunk = KnowledgeChunk.query.filter_by(document_id=document.id).one()
        metadata = chunk_vector_metadata(document, chunk)

    assert metadata["source_type"] == "error_entry"
    assert metadata["source_id"] == error_id
    assert metadata["machine_id"] == machine_id
    assert metadata["role_visibility"] == "department:Produktion"
    assert metadata["created_at"].startswith(source_created_at.date().isoformat())
    assert metadata["module"] == "knowledge"


def test_flat_metadata_omits_none_values_for_chroma():
    """Verify Chroma metadata normalization does not emit unsupported None values."""
    metadata = _flat_metadata(
        {
            "id": 7,
            "machine_id": None,
            "role_visibility": "department:Produktion",
            "technical_entities": {"machines": ["Presse 7"]},
        }
    )

    assert metadata["id"] == 7
    assert metadata["role_visibility"] == "department:Produktion"
    assert "machine_id" not in metadata
    assert "Presse 7" in metadata["technical_entities"]


def test_rebuild_chunks_marks_document_error_when_embedding_fails(app):
    """Verify indexing fails visibly when chunk embeddings cannot be created."""

    class BrokenEmbeddingProvider:
        """Embedding provider test double that fails explicitly."""

        name = "broken"

        def embed_texts(self, texts):
            """Raise an embedding failure for every call."""
            raise RuntimeError("embedding unavailable")

    with app.app_context():
        document = KnowledgeDocument(
            source_type="upload",
            title="Embedding Fehler",
            original_filename="embedding.txt",
            relative_path="uploads/embedding.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        with patch(
            "app.services.embedding_service.get_embedding_provider",
            return_value=BrokenEmbeddingProvider(),
        ):
            rebuild_chunks(
                document,
                "Fehlercode EMB-100\nUrsache: Sensor liefert kein Signal.\n"
                "Loesung: Sensor reinigen und Testlauf dokumentieren.",
            )

    assert document.status == "error"
    assert document.chunk_count == 0
    assert "Embedding provider failed" in document.error_message


def test_pgvector_store_falls_back_to_local_on_sqlite(app):
    """Verify SQLite development uses local retrieval when pgvector is configured."""
    with app.app_context():
        app.config["RAG_VECTOR_STORE"] = "pgvector"
        store = get_vector_store()

    assert store.name == "local_knowledge"


def test_rebuild_chunks_deduplicates_and_skips_low_quality_chunks(app):
    """Verify source-quality filtering avoids duplicate and weak chunks."""
    with app.app_context():
        reset_chunk_quality_reports()
        document = KnowledgeDocument(
            source_type="upload",
            title="Qualitaetstest",
            original_filename="quality.txt",
            relative_path="uploads/quality.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()
        useful_chunk = (
            "Fehlercode QG-100\n"
            "Ursache: Sensor S12 liefert kein Signal.\n"
            "Loesung: Sensor reinigen und Testlauf dokumentieren."
        )

        with patch(
            "app.services.knowledge_service.build_text_chunks",
            return_value=[
                {"text": useful_chunk, "metadata": {"chunk_order": 0}},
                {"text": useful_chunk, "metadata": {"chunk_order": 1}},
                {"text": "OK", "metadata": {"chunk_order": 2}},
            ],
        ):
            rebuild_chunks(document, "ignored")
        db.session.commit()

        chunks = KnowledgeChunk.query.filter_by(document_id=document.id).all()
        summary = latest_chunk_quality_summary()

    assert len(chunks) == 1
    assert document.chunk_count == 1
    assert "QG-100" in chunks[0].text
    assert summary["skipped_duplicate_chunks"] == 1
    assert summary["skipped_low_quality_chunks"] == 1
    assert summary["affected_documents"] == 1


def test_rebuild_chunks_preserves_short_technical_chunks(app):
    """Verify compact technical chunks are retained when they carry evidence."""
    with app.app_context():
        reset_chunk_quality_reports()
        document = KnowledgeDocument(
            source_type="upload",
            title="Kurzer Fehlercode",
            original_filename="short.txt",
            relative_path="uploads/short.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        with patch(
            "app.services.knowledge_service.build_text_chunks",
            return_value=[{"text": "Fehlercode FX-1", "metadata": {}}],
        ):
            rebuild_chunks(document, "ignored")
        db.session.commit()

        chunk = KnowledgeChunk.query.filter_by(document_id=document.id).one()

    assert chunk.text == "Fehlercode FX-1"
    assert document.chunk_count == 1


def test_chunk_quality_detects_empty_short_duplicate_and_bad_ocr(app):
    """Verify chunk-quality diagnostics expose concrete rejection signals."""
    bad_ocr_text = "%%%%% ##### ||||| " * 5 + "\ufffd\ufffd"

    assert chunk_quality_reasons("") == {"empty"}
    assert "too_short" in chunk_quality_reasons("OK")
    assert has_bad_ocr_signature(bad_ocr_text) is True

    with app.app_context():
        reset_chunk_quality_reports()
        document = KnowledgeDocument(
            source_type="upload",
            title="OCR Qualitaetstest",
            original_filename="ocr.txt",
            relative_path="uploads/ocr.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="draft",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()

        with patch(
            "app.services.knowledge_service.build_text_chunks",
            return_value=[
                {"text": "", "metadata": {"chunk_order": 0}},
                {"text": "OK", "metadata": {"chunk_order": 1}},
                {"text": bad_ocr_text, "metadata": {"chunk_order": 2}},
            ],
        ):
            rebuild_chunks(document, "ignored")
        db.session.commit()

        summary = latest_chunk_quality_summary()
        chunk_count = document.chunk_count
        quality_status = document.quality_status

    assert chunk_count == 0
    assert quality_status == "low_quality"
    assert summary["skipped_empty_chunks"] == 1
    assert summary["skipped_short_chunks"] == 1
    assert summary["skipped_bad_ocr_chunks"] == 1
    assert summary["skipped_low_quality_chunks"] == 3


def test_chunk_quality_marks_duplicate_sources_without_overriding_reviewed(app):
    """Verify automatic duplicate status only affects unreviewed sources."""
    useful_chunk = (
        "Fehlercode DUP-100\n"
        "Ursache: Sensor S12 liefert kein Signal.\n"
        "Loesung: Sensor reinigen und Testlauf dokumentieren."
    )
    with app.app_context():
        reset_chunk_quality_reports()
        duplicate_document = KnowledgeDocument(
            source_type="upload",
            title="Duplikat Quelle",
            original_filename="duplicate.txt",
            relative_path="uploads/duplicate.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="draft",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        approved_document = KnowledgeDocument(
            source_type="upload",
            title="Freigegebene Quelle",
            original_filename="approved.txt",
            relative_path="uploads/approved.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="admin_approved",
            is_public=True,
            chunk_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add_all([duplicate_document, approved_document])
        db.session.flush()

        duplicate_payloads = [
            {"text": useful_chunk, "metadata": {"chunk_order": index}} for index in range(3)
        ]
        with patch(
            "app.services.knowledge_service.build_text_chunks",
            return_value=duplicate_payloads,
        ):
            rebuild_chunks(duplicate_document, "ignored")
            rebuild_chunks(approved_document, "ignored")
        db.session.commit()
        duplicate_quality_status = duplicate_document.quality_status
        approved_quality_status = approved_document.quality_status

    assert duplicate_quality_status == "duplicate"
    assert approved_quality_status == "admin_approved"


def test_rag_knowledge_context_respects_document_permissions(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify RAG knowledge retrieval is permission-aware."""
    user_data = make_user(
        username="rag_context_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    blocked_data = make_user(
        username="rag_context_blocked",
        role=Role.PRODUKTION,
        department_name="Instandhaltung",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    set_dashboard_permission(blocked_data["username"], "documents", can_view=False)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        blocked = db.session.get(User, blocked_data["id"])
        document = KnowledgeDocument(
            source_type="upload",
            title="Hydraulikfilter X900",
            original_filename="manual.txt",
            relative_path="uploads/manual.txt",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            is_public=True,
            chunk_count=1,
            created_by=user.id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(document)
        db.session.flush()
        db.session.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=0,
                text="Hydraulikfilter X900 muss taeglich geprueft werden.",
                token_text="hydraulikfilter x900 taeglich pruefen",
                created_at=utc_now(),
            )
        )
        db.session.commit()

        context, sources = knowledge_context_for_chat("Hydraulikfilter X900", user)
        blocked_context, blocked_sources = knowledge_context_for_chat(
            "Hydraulikfilter X900",
            blocked,
        )

    assert "Hydraulikfilter X900" in context
    assert sources[0]["type"] == "knowledge"
    assert blocked_context == ""
    assert blocked_sources == []


def test_local_hybrid_retrieval_finds_keyword_match_beyond_recent_scan(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify lexical candidate expansion prevents recent-only retrieval misses."""
    user_data = make_user(
        username="rag_keyword_candidate_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_SCAN_LIMIT"] = 1
    app.config["RAG_KEYWORD_SCAN_LIMIT"] = 10

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        old_timestamp = utc_now() - timedelta(days=20)
        new_timestamp = utc_now()
        old_document = _create_quality_gate_document(
            title="KWS900 Pumpenlager Wartung",
            quality_status="admin_approved",
            created_by=user.id,
            text="KWS900 Pumpenlager mit Messuhr pruefen und Schmierung dokumentieren.",
            token_text="kws900 pumpenlager messuhr pruefen schmierung dokumentieren",
            updated_at=old_timestamp,
        )
        _create_quality_gate_document(
            title="KWS901 Neuer irrelevanter Hinweis",
            quality_status="admin_approved",
            created_by=user.id,
            text="KWS901 Verpackungsbereich reinigen und Sichtpruefung dokumentieren.",
            token_text="kws901 verpackungsbereich reinigen sichtpruefung dokumentieren",
            updated_at=new_timestamp,
        )
        db.session.commit()

        context, sources = knowledge_context_for_chat(
            "KWS900 Pumpenlager Messuhr",
            user,
            limit=1,
        )

    assert sources[0]["id"] == old_document.id
    assert sources[0]["title"] == "KWS900 Pumpenlager Wartung"
    assert "Pumpenlager" in context


def test_legacy_knowledge_chunk_search_uses_shared_retrieval_pipeline():
    """Verify old knowledge search no longer performs keyword-only retrieval."""
    user = object()
    candidate = RetrievalCandidate(
        source_type="knowledge",
        source_id=42,
        title="Pipeline Quelle",
        content="Hydraulikfilter Pipeline Kontext",
        module="knowledge",
        url="/admin/ai",
        raw_score=88,
        normalized_score=70,
        explanation="88 RAG-Trefferpunkte",
        metadata={"chunk_id": 7, "source_kind": "rag", "section_title": "Wartung"},
    )

    with patch(
        "app.services.retrieval_service.retrieve_knowledge_candidates",
        return_value=[candidate],
    ) as shared_retrieval:
        results = search_knowledge_chunks("Hydraulikfilter", user=user, limit=1)

    shared_retrieval.assert_called_once_with("Hydraulikfilter", user, limit=1)
    assert results == [
        {
            "type": "knowledge",
            "id": 42,
            "chunk_id": 7,
            "title": "Pipeline Quelle",
            "module": "knowledge",
            "url": "/admin/ai",
            "reason": "88 RAG-Trefferpunkte",
            "score": 88,
            "context": "Hydraulikfilter Pipeline Kontext",
            "source_kind": "rag",
            "section_title": "Wartung",
        }
    ]


def test_retrieve_context_keeps_structured_data_when_rag_disabled(
    app,
    make_user,
    set_dashboard_permission,
    make_task,
):
    """Verify structured retrieval remains available when RAG is disabled."""
    user_data = make_user(
        username="rag_disabled_structured_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "tasks", can_view=True)
    make_task(
        "RD900 RAG deaktiviert",
        user_data["username"],
        department_name="Produktion",
        description="RD900 strukturierter Task bleibt ohne RAG sichtbar.",
    )
    app.config["RAG_ENABLED"] = False

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        payload = retrieve_context(
            "RD900 strukturierter Task",
            user,
            requested_scopes={"tasks"},
        )

    assert "RD900 RAG deaktiviert" in payload["context"]
    assert any(source["type"] == "task" for source in payload["sources"])
    assert payload["data"]["tasks"]
    assert "knowledge" not in payload["data"]


@pytest.mark.parametrize(
    ("quality_status", "expected_visible"),
    [
        ("admin_approved", True),
        ("technician_confirmed", True),
        ("ai_suggested", True),
        ("draft", True),
        ("outdated", True),
        ("low_quality", True),
        ("duplicate", True),
        ("rejected", False),
    ],
)
def test_rag_retrieval_quality_gate_filters_each_status(
    app,
    make_user,
    set_dashboard_permission,
    quality_status,
    expected_visible,
):
    """Verify the central retrieval gate handles every quality status."""
    user_data = make_user(
        username=f"rag_quality_{quality_status}",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        title = f"QG900 {quality_status}"
        _create_quality_gate_document(
            title=title,
            quality_status=quality_status,
            created_by=user.id,
        )
        db.session.commit()

        context, sources = knowledge_context_for_chat("QG900 Hydraulik Servo", user)

    matching_sources = [source for source in sources if source["title"] == title]
    assert bool(matching_sources) is expected_visible
    if expected_visible:
        assert "Hydraulik Servo" in context
    else:
        assert context == ""


def test_rag_retrieval_quality_gate_weights_lower_quality_statuses(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify weak quality statuses are downranked while rejected is blocked."""
    user_data = make_user(
        username="rag_quality_weighting_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        for quality_status in (
            "admin_approved",
            "technician_confirmed",
            "ai_suggested",
            "outdated",
            "draft",
            "low_quality",
            "duplicate",
            "rejected",
        ):
            _create_quality_gate_document(
                title=f"QG901 {quality_status}",
                quality_status=quality_status,
                created_by=user.id,
            )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "QG901 Hydraulik Servo",
            user,
            limit=10,
        )

    score_by_title = {source["title"]: source["score"] for source in sources}
    assert "QG901 rejected" not in score_by_title
    assert score_by_title["QG901 admin_approved"] == score_by_title["QG901 technician_confirmed"]
    assert score_by_title["QG901 admin_approved"] > score_by_title["QG901 ai_suggested"]
    assert score_by_title["QG901 ai_suggested"] > score_by_title["QG901 outdated"]
    assert score_by_title["QG901 outdated"] > score_by_title["QG901 draft"]
    assert score_by_title["QG901 draft"] > score_by_title["QG901 low_quality"]
    assert score_by_title["QG901 low_quality"] > score_by_title["QG901 duplicate"]


def test_retrieval_quality_gate_exposes_problem_quality_statuses():
    """Verify low-quality statuses are weakly retrievable and rejected is blocked."""
    low_quality_gate = retrieval_quality_gate_for_status("low_quality")
    duplicate_gate = retrieval_quality_gate_for_status("duplicate")
    rejected_gate = retrieval_quality_gate_for_status("rejected")

    assert low_quality_gate.allowed is True
    assert duplicate_gate.allowed is True
    assert rejected_gate.allowed is False
    assert duplicate_gate.score_multiplier < low_quality_gate.score_multiplier
    assert (
        low_quality_gate.score_multiplier
        < retrieval_quality_gate_for_status("draft").score_multiplier
    )


def test_hybrid_rag_scoring_promotes_helpful_feedback(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify helpful feedback and successful usage improve ranking."""
    user_data = make_user(
        username="rag_feedback_scoring_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        timestamp = utc_now()
        plain = _create_quality_gate_document(
            title="FB900 Plain",
            quality_status="admin_approved",
            created_by=user.id,
            text="FB900 Hydraulik Servo Ablauf pruefen.",
            token_text="fb900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        plain_title = plain.title
        helpful = _create_quality_gate_document(
            title="FB900 Helpful",
            quality_status="admin_approved",
            created_by=user.id,
            text="FB900 Hydraulik Servo Ablauf pruefen.",
            token_text="fb900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        db.session.flush()
        helpful_chunk = helpful.chunks[0]
        db.session.add(
            AIFeedback(
                user_id=user.id,
                prompt="FB900",
                response="Quelle war hilfreich",
                response_type="assistant",
                rating="helpful",
                sources_json=json.dumps(
                    [
                        {
                            "type": "knowledge",
                            "id": helpful.id,
                            "chunk_id": helpful_chunk.id,
                            "title": helpful.title,
                        }
                    ]
                ),
                source_count=1,
            )
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "FB900 Hydraulik Servo",
            user,
            limit=2,
        )

    titles = [source["title"] for source in sources]
    assert plain_title in titles
    assert titles[0] == "FB900 Helpful"
    assert sources[0]["score"] > sources[1]["score"]


def test_hybrid_rag_scoring_promotes_machine_relevance(
    app,
    make_user,
    make_machine,
    set_dashboard_permission,
):
    """Verify explicit machine matches improve ranking."""
    user_data = make_user(
        username="rag_machine_scoring_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    make_machine(name="Presse 3", produced_item="Servo")

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        timestamp = utc_now()
        _create_quality_gate_document(
            title="MR900 Presse 4",
            quality_status="admin_approved",
            created_by=user.id,
            text="Presse 4 MR900 Hydraulik Servo Ablauf pruefen.",
            token_text="presse mr900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        _create_quality_gate_document(
            title="MR900 Presse 3",
            quality_status="admin_approved",
            created_by=user.id,
            text="Presse 3 MR900 Hydraulik Servo Ablauf pruefen.",
            token_text="presse mr900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "Presse 3 MR900 Hydraulik Servo",
            user,
            limit=2,
        )

    assert sources[0]["title"] == "MR900 Presse 3"
    assert sources[0]["score"] > sources[1]["score"]


def test_rag_sources_include_explainability_without_debug_flag(
    app,
    make_user,
    make_machine,
    set_dashboard_permission,
):
    """Verify public RAG sources include stable explainability metadata."""
    app.config["RAG_SCORE_DEBUG"] = False
    user_data = make_user(
        username="rag_explainability_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    make_machine(name="Presse 3", produced_item="Servo")

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        _create_quality_gate_document(
            title="EX900 Presse 3",
            quality_status="admin_approved",
            created_by=user.id,
            text="Presse 3 EX900 Hydraulik Servo Wartung pruefen.",
            token_text="presse 3 ex900 hydraulik servo wartung pruefen",
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "Presse 3 EX900 Hydraulik Servo",
            user,
            limit=1,
        )

    explainability = sources[0]["explainability"]
    assert "score_debug" not in sources[0]
    assert explainability["semantic_similarity"] >= 0
    assert explainability["lexical_score"] > 0
    assert explainability["machine_match"] > 0
    assert explainability["quality_status"] == "admin_approved"
    assert "feedback_influence" in explainability
    assert "recency_influence" in explainability


def test_rag_sources_include_safe_source_metadata(
    app,
    make_user,
    make_machine,
    make_error_entry,
    set_dashboard_permission,
):
    """Verify public RAG source cards expose safe chunk and source metadata."""
    user_data = make_user(
        username="rag_safe_metadata_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    machine_id = make_machine(name="Presse Meta", produced_item="Servo")
    error_id = make_error_entry(
        "Presse Meta",
        "META-100",
        "Metadata Stoerung",
        department_name="Produktion",
        description="Sensor meldet sporadisch kein Signal.",
        possible_causes="Sensor verschmutzt.",
        solution="Sensor reinigen und Abstand pruefen.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        db.session.get(ErrorEntry, error_id).machine_id = machine_id
        document = _create_quality_gate_document(
            title="META-100 Presse Meta",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=error_id,
            text="META-100 Sensor Stoerung Presse Meta pruefen.",
            token_text="meta 100 sensor stoerung presse pruefen",
        )
        document.chunks[0].entities_json = json.dumps(
            {
                "_chunk_metadata": {
                    "chunk_block_count": 2,
                    "chunk_block_kinds": "error_code,paragraph",
                    "chunking_mode": "hybrid_semantic",
                }
            },
            ensure_ascii=True,
        )
        db.session.commit()

        context, sources = knowledge_context_for_chat(
            "META-100 Presse Meta Sensor Stoerung",
            user,
            limit=1,
        )

    source = sources[0]
    assert source["source_type"] == "error_entry"
    assert source["source_id"] == error_id
    assert source["title"] == "META-100 Presse Meta"
    assert source["module"] == "knowledge"
    assert source["machine_id"] == machine_id
    assert source["role_visibility"] == "department:Produktion"
    assert source["created_at"]
    assert source["chunk_id"]
    assert source["chunk_block_count"] == 2
    assert source["chunk_block_kinds"] == ["error_code", "paragraph"]
    assert source["chunking_mode"] == "hybrid_semantic"
    assert "Chunk-Struktur: 2 Block(s), Arten: error_code, paragraph" in context


def test_vector_result_candidate_normalizes_chunk_structure_metadata():
    """Verify vector-store string metadata becomes stable public source fields."""
    result = type(
        "VectorResult",
        (),
        {
            "score": 90,
            "text": "META-200 Listenpunkt und Fehlercode.",
            "metadata": {
                "type": "knowledge",
                "id": 7,
                "chunk_id": 13,
                "chunk_block_count": "2",
                "chunk_block_kinds": "list, error_code",
                "title": "META-200",
                "module": "knowledge",
                "source_type": "machine_manual",
                "source_id": 5,
            },
        },
    )()

    public_source = public_sources_from_candidates([vector_result_candidate(result)])[0]

    assert public_source["chunk_block_count"] == 2
    assert public_source["chunk_block_kinds"] == ["list", "error_code"]


def test_rag_sources_include_shift_handover_metadata(
    app,
    make_user,
    make_machine,
    set_dashboard_permission,
):
    """Verify shift handover RAG sources expose safe metadata."""
    user_data = make_user(
        username="rag_handover_metadata_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "shiftplans", can_view=True)
    machine_id = make_machine(name="Presse Handover Meta", produced_item="Servo")

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        handover = ShiftHandover(
            department="Produktion",
            shift_date=utc_now().date(),
            shift_type="Spaet",
            status="open",
            handed_over_by=user.id,
            machine_id=machine_id,
            content="Presse Handover Meta braucht Kontrolle.",
            open_tasks="Hydraulikpruefung offen.",
            machine_notes="Sensorabgleich beobachten.",
            next_notes="Druck im ersten Auftrag pruefen.",
        )
        db.session.add(handover)
        db.session.flush()
        _create_quality_gate_document(
            title="Handover Meta Presse",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="shift_handover",
            source_id=handover.id,
            text="Presse Handover Meta Sensorabgleich Hydraulikpruefung.",
            token_text="presse handover meta sensorabgleich hydraulikpruefung",
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "Presse Handover Meta Sensorabgleich Hydraulikpruefung",
            user,
            limit=1,
        )

    source = sources[0]
    assert source["source_type"] == "shift_handover"
    assert source["source_id"] == handover.id
    assert source["machine_id"] == machine_id
    assert source["machine"] == "Presse Handover Meta"
    assert source["role_visibility"] == "department:Produktion"
    assert source["created_at"]
    assert source["url"] == "/handover"


def test_rag_shift_handover_source_id_visibility_blocks_foreign_department(
    app,
    make_user,
    make_machine,
    set_dashboard_permission,
):
    """Verify RAG source-id checks block foreign shift handover chunks."""
    user_data = make_user(
        username="rag_handover_foreign_source_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    foreign_user_data = make_user(
        username="rag_handover_foreign_source_owner",
        role=Role.IT,
        department_name="IT",
    )
    set_dashboard_permission(user_data["username"], "shiftplans", can_view=True)
    machine_id = make_machine(name="Presse Foreign Handover", produced_item="Servo")

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        foreign_handover = ShiftHandover(
            department="IT",
            shift_date=utc_now().date(),
            shift_type="Nacht",
            status="open",
            handed_over_by=foreign_user_data["id"],
            machine_id=machine_id,
            content="Presse Foreign Handover nur fuer IT sichtbar.",
            open_tasks="IT Diagnose offen.",
            machine_notes="ForeignToken900 Sensor pruefen.",
            next_notes="Nicht fuer Produktion freigeben.",
        )
        db.session.add(foreign_handover)
        db.session.flush()
        _create_quality_gate_document(
            title="Foreign Handover Source",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="shift_handover",
            source_id=foreign_handover.id,
            text="ForeignToken900 Presse Foreign Handover Sensor Diagnose.",
            token_text="foreigntoken900 presse foreign handover sensor diagnose",
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "ForeignToken900 Presse Foreign Handover Sensor Diagnose",
            user,
            limit=1,
        )

    assert sources == []


def test_rag_sources_include_task_source_created_at(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify task RAG sources use safe metadata from the original task."""
    user_data = make_user(
        username="rag_task_metadata_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "tasks", can_view=True)
    task_created_at = utc_now() - timedelta(days=3)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        task = Task(
            title="Task Metadata Quelle",
            description="TM-100 Hydraulikpruefung an Taskquelle.",
            priority=Priority.URGENT,
            status=TaskStatus.OPEN,
            due_date=task_created_at.date(),
            department=user.department,
            created_by=user.id,
            created_at=task_created_at,
            updated_at=task_created_at,
        )
        db.session.add(task)
        db.session.flush()
        task_id = task.id
        _create_quality_gate_document(
            title="TM-100 Task Metadata",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="task",
            source_id=task_id,
            text="TM-100 Task Metadata Hydraulikpruefung pruefen.",
            token_text="tm 100 task metadata hydraulikpruefung pruefen",
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "TM-100 Task Metadata Hydraulikpruefung",
            user,
            limit=1,
        )

    source = sources[0]
    assert source["source_type"] == "task"
    assert source["source_id"] == task_id
    assert source["department"] == "Produktion"
    assert source["role_visibility"] == "department:Produktion"
    assert source["created_at"].startswith(task_created_at.date().isoformat())
    assert source["url"] == "/tasks"


def test_vector_store_labels_private_department_visibility(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify private knowledge sources expose prompt-safe visibility metadata."""
    admin_data = make_user(
        username="rag_private_visibility_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    set_dashboard_permission(admin_data["username"], "documents", can_view=True)
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        admin = db.session.get(User, admin_data["id"])
        _create_quality_gate_document(
            title="PV-100 Private Sichtbarkeit",
            quality_status="admin_approved",
            created_by=admin.id,
            text="PV-100 Private Sichtbarkeit pruefen.",
            token_text="pv 100 private sichtbarkeit pruefen",
            is_public=False,
        )
        db.session.commit()

        results = get_vector_store().similarity_search(
            "PV-100 Private Sichtbarkeit",
            admin,
            limit=1,
            filters={"role_visibility": "private:department:Produktion"},
        )

    assert results
    assert results[0].metadata["role_visibility"] == "private:department:Produktion"


def test_vector_store_filters_by_safe_machine_metadata(
    app,
    make_user,
    make_machine,
    make_error_entry,
    set_dashboard_permission,
):
    """Verify hybrid vector search honors safe machine metadata filters."""
    user_data = make_user(
        username="rag_machine_filter_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    set_dashboard_permission(user_data["username"], "machines", can_view=True)
    set_dashboard_permission(user_data["username"], "shiftplans", can_view=True)
    presse_10_id = make_machine(name="Presse 10", produced_item="Servo")
    presse_11_id = make_machine(name="Presse 11", produced_item="Servo")
    matching_error_id = make_error_entry(
        "Presse 10",
        "MF-100",
        "Maschinenfilter Treffer",
        department_name="Produktion",
        description="Servo meldet MF-100.",
    )
    other_error_id = make_error_entry(
        "Presse 11",
        "MF-100",
        "Maschinenfilter Fremdtreffer",
        department_name="Produktion",
        description="Servo meldet MF-100.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        db.session.get(ErrorEntry, matching_error_id).machine_id = presse_10_id
        db.session.get(ErrorEntry, other_error_id).machine_id = presse_11_id
        matching_handover = ShiftHandover(
            department="Produktion",
            shift_date=utc_now().date(),
            shift_type="Spaet",
            status="open",
            handed_over_by=user.id,
            machine_id=presse_10_id,
            machine_notes="MF-100 Servo Maschinenfilter an Presse 10 beobachten.",
        )
        other_handover = ShiftHandover(
            department="Produktion",
            shift_date=utc_now().date(),
            shift_type="Nacht",
            status="open",
            handed_over_by=user.id,
            machine_id=presse_11_id,
            machine_notes="MF-100 Servo Maschinenfilter an Presse 11 beobachten.",
        )
        db.session.add_all([matching_handover, other_handover])
        db.session.flush()
        _create_quality_gate_document(
            title="MF-100 Maschine Presse 10",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="machine",
            source_id=presse_10_id,
            text="MF-100 Servo Maschinenfilter Stammdaten Presse 10.",
            token_text="mf 100 servo maschinenfilter stammdaten presse 10",
        )
        _create_quality_gate_document(
            title="MF-100 Maschine Presse 11",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="machine",
            source_id=presse_11_id,
            text="MF-100 Servo Maschinenfilter Stammdaten Presse 11.",
            token_text="mf 100 servo maschinenfilter stammdaten presse 11",
        )
        _create_quality_gate_document(
            title="MF-100 Presse 10",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=matching_error_id,
            text="MF-100 Servo Maschinenfilter Presse 10 pruefen.",
            token_text="mf 100 servo maschinenfilter presse 10 pruefen",
        )
        _create_quality_gate_document(
            title="MF-100 Presse 11",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=other_error_id,
            text="MF-100 Servo Maschinenfilter Presse 11 pruefen.",
            token_text="mf 100 servo maschinenfilter presse 11 pruefen",
        )
        _create_quality_gate_document(
            title="MF-100 Handover Presse 10",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="shift_handover",
            source_id=matching_handover.id,
            text="MF-100 Servo Maschinenfilter Presse 10 im Handover.",
            token_text="mf 100 servo maschinenfilter presse 10 handover",
        )
        _create_quality_gate_document(
            title="MF-100 Handover Presse 11",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="shift_handover",
            source_id=other_handover.id,
            text="MF-100 Servo Maschinenfilter Presse 11 im Handover.",
            token_text="mf 100 servo maschinenfilter presse 11 handover",
        )
        db.session.commit()

        results = get_vector_store().similarity_search(
            "MF-100 Servo Maschinenfilter",
            user=user,
            limit=5,
            filters={
                "machine_id": presse_10_id,
                "module": "knowledge",
                "role_visibility": "department:Produktion",
            },
        )

    assert results
    assert {result.metadata["title"] for result in results} == {
        "MF-100 Maschine Presse 10",
        "MF-100 Presse 10",
        "MF-100 Handover Presse 10",
    }
    assert all(result.metadata["machine_id"] == presse_10_id for result in results)


def test_rag_rerank_candidate_limit_fetches_more_than_final_top_k(app):
    """Verify the rerank candidate limit is distinct from the final answer top K."""
    with app.app_context():
        app.config["RAG_TOP_K"] = 4
        app.config["RAG_RERANK_CANDIDATE_LIMIT"] = 20

        assert _rerank_candidate_limit(app.config["RAG_TOP_K"]) == 20
        assert _rerank_candidate_limit(30) == 30


def test_machine_aware_retrieval_prefers_same_error_machine(
    app,
    make_user,
    make_machine,
    make_error_entry,
    set_dashboard_permission,
):
    """Verify RAG ranking prefers the same machine over another machine."""
    user_data = make_user(
        username="rag_same_machine_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    app.config["RAG_SCORE_DEBUG"] = True
    presse_7_id = make_machine(name="Presse 7", produced_item="Servo")
    presse_8_id = make_machine(name="Presse 8", produced_item="Servo")
    same_error_id = make_error_entry(
        "Presse 7",
        "E104",
        "Sensor Signal Stoerung",
        department_name="Produktion",
        description="Sensor Signal fehlt sporadisch.",
        possible_causes="Sensor verschmutzt.",
        solution="Sensor reinigen und Abstand pruefen.",
    )
    other_error_id = make_error_entry(
        "Presse 8",
        "E104",
        "Sensor Signal Stoerung",
        department_name="Produktion",
        description="Sensor Signal fehlt sporadisch.",
        possible_causes="Sensor verschmutzt.",
        solution="Sensor reinigen und Abstand pruefen.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        db.session.get(ErrorEntry, same_error_id).machine_id = presse_7_id
        db.session.get(ErrorEntry, other_error_id).machine_id = presse_8_id
        timestamp = utc_now()
        _create_quality_gate_document(
            title="E104 Presse 8",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=other_error_id,
            text="E104 Sensor Signal Stoerung pruefen.",
            token_text="e104 sensor signal stoerung pruefen",
            updated_at=timestamp,
        )
        _create_quality_gate_document(
            title="E104 Presse 7",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=same_error_id,
            text="E104 Sensor Signal Stoerung pruefen.",
            token_text="e104 sensor signal stoerung pruefen",
            updated_at=timestamp,
        )
        db.session.commit()

        context, sources = knowledge_context_for_chat(
            "Was hilft bei Fehler E104 an Presse 7?",
            user,
            limit=2,
        )

    assert sources[0]["title"] == "E104 Presse 7"
    assert sources[0]["score"] > sources[1]["score"]
    assert "Maschinenkontext:" in context
    assert "same_machine" in sources[0]["score_debug"]["signals"]["machine_match_reasons"]
    assert "same_error_code" in sources[0]["score_debug"]["signals"]["machine_match_reasons"]


def test_rag_retrieval_penalizes_conflicting_error_codes(
    app,
    make_user,
    make_error_entry,
    set_dashboard_permission,
):
    """Verify exact error-code matches outrank chunks with conflicting codes."""
    user_data = make_user(
        username="rag_error_alignment_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    app.config["RAG_SCORE_DEBUG"] = True
    exact_error_id = make_error_entry(
        "Presse 5",
        "E204",
        "Drucksensor Stoerung",
        department_name="Produktion",
        description="Drucksensor meldet sporadisch kein Signal.",
        possible_causes="Sensorleitung oder Steckverbinder lose.",
        solution="E204 Diagnose ausfuehren und Steckverbinder pruefen.",
    )
    wrong_error_id = make_error_entry(
        "Presse 5",
        "E999",
        "Drucksensor Stoerung",
        department_name="Produktion",
        description="Drucksensor meldet sporadisch kein Signal.",
        possible_causes="Sensorleitung oder Steckverbinder lose.",
        solution="E999 Diagnose ausfuehren und Steckverbinder pruefen.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        timestamp = utc_now()
        _create_quality_gate_document(
            title="E999 Drucksensor",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=wrong_error_id,
            text="Fehler E999 Drucksensor Stoerung an Presse 5 pruefen.",
            token_text="fehler e999 drucksensor stoerung presse 5 pruefen",
            updated_at=timestamp,
        )
        _create_quality_gate_document(
            title="E204 Drucksensor",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=exact_error_id,
            text="Fehler E204 Drucksensor Stoerung an Presse 5 pruefen.",
            token_text="fehler e204 drucksensor stoerung presse 5 pruefen",
            updated_at=timestamp,
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "Presse 5 Fehler E204 Drucksensor Stoerung",
            user,
            limit=2,
        )

    assert sources[0]["title"] == "E204 Drucksensor"
    assert sources[0]["score"] > sources[1]["score"]
    assert sources[0]["score_debug"]["signals"]["error_code_alignment"] == "exact_error_code"
    assert sources[1]["score_debug"]["signals"]["error_code_alignment"] == "conflicting_error_code"


def test_machine_aware_retrieval_uses_series_and_similar_error_code(
    app,
    make_user,
    make_machine,
    make_error_entry,
    set_dashboard_permission,
):
    """Verify related machine series and similar error codes improve ranking."""
    user_data = make_user(
        username="rag_machine_series_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    app.config["RAG_SCORE_DEBUG"] = True
    make_machine(name="Presse 9", produced_item="Servo")
    presse_4_id = make_machine(name="Presse 4", produced_item="Servo")
    ofen_4_id = make_machine(name="Ofen 4", produced_item="Servo")
    series_error_id = make_error_entry(
        "Presse 4",
        "E105",
        "Sensor Signal Stoerung",
        department_name="Produktion",
        description="Sensor Signal fehlt sporadisch.",
        possible_causes="Sensor verschmutzt.",
        solution="Sensor reinigen und Abstand pruefen.",
    )
    other_error_id = make_error_entry(
        "Ofen 4",
        "Z880",
        "Sensor Signal Stoerung",
        department_name="Produktion",
        description="Sensor Signal fehlt sporadisch.",
        possible_causes="Sensor verschmutzt.",
        solution="Sensor reinigen und Abstand pruefen.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        db.session.get(ErrorEntry, series_error_id).machine_id = presse_4_id
        db.session.get(ErrorEntry, other_error_id).machine_id = ofen_4_id
        timestamp = utc_now()
        _create_quality_gate_document(
            title="Z880 Ofen 4",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=other_error_id,
            text="Sensor Signal Stoerung pruefen.",
            token_text="sensor signal stoerung pruefen",
            updated_at=timestamp,
        )
        _create_quality_gate_document(
            title="E105 Presse 4",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="error_entry",
            source_id=series_error_id,
            text="Sensor Signal Stoerung pruefen.",
            token_text="sensor signal stoerung pruefen",
            updated_at=timestamp,
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "Fehler E104 an Presse 9 Sensor Signal",
            user,
            limit=2,
        )

    reasons = sources[0]["score_debug"]["signals"]["machine_match_reasons"]
    assert sources[0]["title"] == "E105 Presse 4"
    assert sources[0]["score"] > sources[1]["score"]
    assert "same_machine_series" in reasons
    assert "similar_error_code" in reasons


def test_hybrid_rag_scoring_promotes_recent_sources(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify recency is part of the final retrieval score."""
    user_data = make_user(
        username="rag_recency_scoring_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        now = utc_now()
        _create_quality_gate_document(
            title="RC900 Alt",
            quality_status="admin_approved",
            created_by=user.id,
            text="RC900 Hydraulik Servo Ablauf pruefen.",
            token_text="rc900 hydraulik servo ablauf pruefen",
            updated_at=now - timedelta(days=180),
        )
        _create_quality_gate_document(
            title="RC900 Neu",
            quality_status="admin_approved",
            created_by=user.id,
            text="RC900 Hydraulik Servo Ablauf pruefen.",
            token_text="rc900 hydraulik servo ablauf pruefen",
            updated_at=now,
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "RC900 Hydraulik Servo",
            user,
            limit=2,
        )

    assert sources[0]["title"] == "RC900 Neu"
    assert sources[0]["score"] > sources[1]["score"]


def test_knowledge_aging_marks_old_reviewed_document_outdated(app, make_user):
    """Verify old reviewed knowledge can be moved to outdated for review."""
    user_data = make_user(
        username="rag_aging_outdated_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )

    with app.app_context():
        app.config["KNOWLEDGE_AGING_STALE_DAYS"] = 30
        old_timestamp = utc_now() - timedelta(days=120)
        document = _create_quality_gate_document(
            title="AG900 Alt",
            quality_status="admin_approved",
            created_by=user_data["id"],
            updated_at=old_timestamp,
        )
        document.last_confirmed_at = old_timestamp
        document.confirmation_count = 1
        db.session.commit()

        result = mark_outdated_knowledge_by_age(now=utc_now())
        refreshed = db.session.get(KnowledgeDocument, document.id)
        quality_status = refreshed.quality_status
        aging_checked_at = refreshed.aging_checked_at

    assert result["documents"] == 1
    assert quality_status == "outdated"
    assert aging_checked_at is not None


def test_knowledge_aging_keeps_repeatedly_confirmed_document_stable(app, make_user):
    """Verify repeated confirmations protect old knowledge from automatic aging."""
    user_data = make_user(
        username="rag_aging_stable_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )

    with app.app_context():
        app.config["KNOWLEDGE_AGING_STALE_DAYS"] = 30
        app.config["KNOWLEDGE_AGING_STABLE_CONFIRMATIONS"] = 3
        old_timestamp = utc_now() - timedelta(days=180)
        document = _create_quality_gate_document(
            title="AG901 Stabil",
            quality_status="admin_approved",
            created_by=user_data["id"],
            updated_at=old_timestamp,
        )
        document.last_confirmed_at = old_timestamp
        document.confirmation_count = 3
        db.session.commit()

        state = knowledge_aging_state(document, now=utc_now())
        result = mark_outdated_knowledge_by_age(now=utc_now())
        refreshed = db.session.get(KnowledgeDocument, document.id)
        quality_status = refreshed.quality_status

    assert state.stable is True
    assert state.retrieval_multiplier == 1.0
    assert result["documents"] == 0
    assert quality_status == "admin_approved"


def test_rag_retrieval_downranks_old_unconfirmed_sources(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify aging reduces retrieval strength without blocking the source."""
    user_data = make_user(
        username="rag_aging_weight_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_SCORE_DEBUG"] = True

    with app.app_context():
        app.config["KNOWLEDGE_AGING_STALE_DAYS"] = 30
        user = db.session.get(User, user_data["id"])
        old_timestamp = utc_now() - timedelta(days=120)
        old_document = _create_quality_gate_document(
            title="AG902 Alt",
            quality_status="admin_approved",
            created_by=user.id,
            text="AG902 Hydraulik Servo Ablauf pruefen.",
            token_text="ag902 hydraulik servo ablauf pruefen",
            updated_at=old_timestamp,
        )
        old_document.last_confirmed_at = old_timestamp
        old_document.confirmation_count = 1
        _create_quality_gate_document(
            title="AG902 Neu",
            quality_status="admin_approved",
            created_by=user.id,
            text="AG902 Hydraulik Servo Ablauf pruefen.",
            token_text="ag902 hydraulik servo ablauf pruefen",
            updated_at=utc_now(),
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "AG902 Hydraulik Servo",
            user,
            limit=2,
        )

    score_by_title = {source["title"]: source["score"] for source in sources}
    old_source = next(source for source in sources if source["title"] == "AG902 Alt")
    aging_signals = old_source["score_debug"]["signals"]
    assert sources[0]["title"] == "AG902 Neu"
    assert score_by_title["AG902 Neu"] > score_by_title["AG902 Alt"]
    assert aging_signals["aging_multiplier"] < 1
    assert old_source["explainability"]["aging_influence"] < 0


def test_hybrid_rag_scoring_uses_source_priority_and_debug_fields(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify source priority can affect ranking and debug fields are optional."""
    user_data = make_user(
        username="rag_priority_scoring_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_SCORE_DEBUG"] = True

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        training = AssistantTrainingEntry(
            title="SP900 Training",
            question="Wie SP900 pruefen?",
            answer="SP900 Hydraulik Servo Ablauf pruefen.",
            keywords="SP900, Hydraulik, Servo",
            department="Produktion",
            is_active=True,
            priority=95,
            created_by=user.id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(training)
        db.session.flush()
        timestamp = utc_now()
        _create_quality_gate_document(
            title="SP900 Upload",
            quality_status="admin_approved",
            created_by=user.id,
            text="SP900 Hydraulik Servo Ablauf pruefen.",
            token_text="sp900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        _create_quality_gate_document(
            title="SP900 Training",
            quality_status="admin_approved",
            created_by=user.id,
            source_type="manual_training",
            source_id=training.id,
            text="SP900 Hydraulik Servo Ablauf pruefen.",
            token_text="sp900 hydraulik servo ablauf pruefen",
            updated_at=timestamp,
        )
        db.session.commit()

        _context, sources = knowledge_context_for_chat(
            "SP900 Hydraulik Servo",
            user,
            limit=2,
        )

    assert sources[0]["title"] == "SP900 Training"
    assert sources[0]["score"] > sources[1]["score"]
    assert "score_debug" in sources[0]
    assert "components" in sources[0]["score_debug"]
    assert "source_priority" in sources[0]["score_debug"]["components"]


def _create_quality_gate_document(
    title,
    quality_status,
    created_by,
    source_type="upload",
    source_id=None,
    text="QG900 QG901 Hydraulik Servo Spezialverfahren Qualitaetsgate.",
    token_text="qg900 qg901 hydraulik servo spezialverfahren qualitaetsgate",
    updated_at=None,
    is_public=True,
):
    """Create an indexed knowledge document with one deterministic matching chunk."""
    timestamp = updated_at or utc_now()
    document = KnowledgeDocument(
        source_type=source_type,
        source_id=source_id,
        title=title,
        original_filename=f"{title}.txt",
        relative_path=f"uploads/{title}.txt",
        content_type="text/plain",
        department="Produktion",
        status="indexed",
        quality_status=quality_status,
        is_public=is_public,
        chunk_count=1,
        created_by=created_by,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(
        KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            text=text,
            token_text=token_text,
            created_at=timestamp,
        )
    )
    return document
