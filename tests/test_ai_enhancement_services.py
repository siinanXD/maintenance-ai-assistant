"""Tests for AI query understanding, safety, context, linking and timelines."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agent.service import run_agent
from app.extensions import db
from app.models import ChatMessage, ErrorEntry, KnowledgeChunk, KnowledgeDocument, Role, User
from app.services.ai_audit_service import create_ai_audit_event
from app.services.incident_timeline_service import incident_timeline
from app.services.knowledge_linking_service import knowledge_links_for_document
from app.services.query_classifier_service import (
    QUERY_TYPE_GENERAL,
    QUERY_TYPE_HYBRID,
    QUERY_TYPE_KNOWLEDGE_RAG,
    QUERY_TYPE_LIVE_SQL,
    QueryClassifierService,
)
from app.services.query_understanding_service import classify_query
from app.services.rag_service import build_rag_context
from app.services.technical_entity_service import entities_to_json


def _admin_user(user_id):
    """Return a user model for a fixture-created admin."""
    return db.session.get(User, user_id)


def _create_document(creator_id, title, entities, text="Knowledge chunk text"):
    """Create an indexed knowledge document for enhancement tests."""
    document = KnowledgeDocument(
        source_type="upload",
        title=title,
        original_filename=f"{title}.txt",
        department="Produktion",
        status="indexed",
        quality_status="admin_approved",
        chunk_count=1,
        is_public=True,
        created_by=creator_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(
        KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            text=text,
            token_text=text,
            entities_json=entities_to_json(entities),
        )
    )
    db.session.commit()
    return document.id


def test_query_understanding_classifies_safety_and_routes_retrieval():
    """Verify local query understanding marks safety questions and strategy metadata."""
    result = classify_query("Darf ich den Not-Aus bei Arbeiten unter Spannung ueberbruecken?")

    assert result.query_type == "safety_question"
    assert result.is_safety is True
    assert "machines" in result.recommended_scopes
    assert result.retrieval_strategy["top_k"] >= 6


def test_query_understanding_arbeit_keyword_uses_word_boundaries():
    """Verify safety questions with Arbeiten are not mis-scored via substring arbeit."""
    safety = classify_query("Darf ich den Not-Aus bei Arbeiten unter Spannung ueberbruecken?")
    tasks = classify_query("Welche Arbeiten sind heute offen?")

    assert safety.query_type == "safety_question"
    assert tasks.query_type == "task_question"


def test_query_understanding_routes_employee_questions():
    """Verify employee questions route to permission-aware employee sources."""
    result = classify_query("Welche Mitarbeiter haben Hydraulik Qualifikation?")

    assert result.query_type == "employee_question"
    assert "employees" in result.recommended_scopes
    assert "employee" in result.retrieval_strategy["source_types"]
    assert result.retrieval_strategy["prefer_structured"] is True


def test_query_understanding_routes_admin_user_role_questions():
    """Verify admin-user questions route to permission-aware role sources."""
    result = classify_query("Welche Rollen und Berechtigungen haben User im System?")

    assert result.query_type == "admin_user_question"
    assert "admin_users" in result.recommended_scopes
    assert "admin_user" in result.retrieval_strategy["source_types"]
    assert result.retrieval_strategy["prefer_structured"] is True


def test_query_understanding_routes_handover_questions():
    """Verify handover questions route to shift-handover sources."""
    result = classify_query("Was steht in der letzten Schichtuebergabe zur Presse?")

    assert result.query_type == "trend_history_question"
    assert "shiftplans" in result.recommended_scopes
    assert "shift_handover" in result.retrieval_strategy["source_types"]
    assert result.retrieval_strategy["prefer_structured"] is True


def test_query_classifier_routes_typical_live_sql_questions():
    """Verify high-level classification detects live structured-data questions."""
    classifier = QueryClassifierService()

    tasks = classifier.classify("Welche Tasks stehen heute an?")
    machines = classifier.classify("Welche Maschine ist kritisch?")
    employees = classifier.classify("Welche Mitarbeiter haben Hydraulik Qualifikation?")
    admin_users = classifier.classify("Welche Rollen haben User?")

    assert tasks.query_type == QUERY_TYPE_LIVE_SQL
    assert "tasks" in tasks.suggested_sources
    assert machines.query_type == QUERY_TYPE_LIVE_SQL
    assert "machines" in machines.suggested_sources
    assert "machine_hints" not in machines.possible_entities
    assert employees.query_type == QUERY_TYPE_LIVE_SQL
    assert "employees" in employees.suggested_sources
    assert admin_users.query_type == QUERY_TYPE_LIVE_SQL
    assert "admin_users" in admin_users.suggested_sources


def test_query_classifier_routes_hybrid_error_code_questions():
    """Verify error-code questions are treated as hybrid retrieval."""
    result = QueryClassifierService().classify("Was bedeutet Fehler E104?")

    assert result.query_type == QUERY_TYPE_HYBRID
    assert "E104" in result.possible_entities["error_codes"]
    assert {"errors", "knowledge"}.issubset(set(result.suggested_sources))


def test_query_classifier_routes_knowledge_and_general_questions():
    """Verify knowledge-only and general questions are classified separately."""
    classifier = QueryClassifierService()

    knowledge = classifier.classify("Wie l\u00f6se ich Hydraulikdruckverlust?")
    general = classifier.classify("Welche Funktionen hat diese App?")

    assert knowledge.query_type == QUERY_TYPE_KNOWLEDGE_RAG
    assert "knowledge" in knowledge.suggested_sources
    assert general.query_type == QUERY_TYPE_GENERAL
    assert general.suggested_sources == []


def test_query_classifier_returns_required_payload_fields():
    """Verify query classification returns stable routing metadata."""
    payload = QueryClassifierService().classify("Was bedeutet Fehler E104?").to_dict()

    assert set(payload) == {
        "query_type",
        "extracted_keywords",
        "possible_entities",
        "suggested_sources",
    }
    assert payload["query_type"] == QUERY_TYPE_HYBRID
    assert payload["possible_entities"]["error_codes"] == ["E104"]


def test_rag_context_adds_query_type_conflicts_links_and_context_builder(
    app,
    make_user,
    make_machine,
    make_error_entry,
):
    """Verify RAG context is dynamically assembled with metadata diagnostics."""
    admin = make_user(username="enhanced_rag_admin", role=Role.MASTER_ADMIN)
    make_machine(name="Anlage 77")
    make_error_entry(
        "Anlage 77",
        "F-77",
        "Temperatur steigt",
        solution="Kuehlung pruefen.",
    )
    make_error_entry(
        "Anlage 77",
        "F-77",
        "Temperatur erneut hoch",
        solution="Sensor tauschen.",
    )

    with app.app_context():
        first_document_id = _create_document(
            admin["id"],
            "Anlage 77 Temperatur",
            {"machines": ["Anlage 77"], "error_codes": ["F-77"]},
            text="Anlage 77 F-77 Temperatur Kuehlung Sensor.",
        )
        _create_document(
            admin["id"],
            "Anlage 77 Sensorik",
            {"machines": ["Anlage 77"], "error_codes": ["F-77"], "sensors": ["Sensor T1"]},
            text="Anlage 77 F-77 Sensor T1 Temperatur.",
        )
        payload = build_rag_context(
            "Welche Historie und Ursache hat Fehler F-77 an Anlage 77?",
            _admin_user(admin["id"]),
        )
        links = knowledge_links_for_document(first_document_id, _admin_user(admin["id"]))

    assert payload["rag"]["query_understanding"]["query_type"] in {
        "trend_history_question",
        "error_analysis",
    }
    assert payload["rag"]["query_classification"]["query_type"] == QUERY_TYPE_HYBRID
    assert payload["rag"]["conflicts"]["has_conflicts"] is True
    assert payload["rag"]["context_builder"]["sections"]
    assert links["links"]
    assert "Kuehlung pruefen" not in str(payload["rag"]["conflicts"])


def test_safety_answer_is_marked_and_audited(app, make_user):
    """Verify safety-critical chat answers receive warning and audit metadata."""
    admin = make_user(username="safety_admin", role=Role.MASTER_ADMIN)
    with app.app_context():
        result = run_agent(
            "Wie kann ich den Not-Aus ueberbruecken, wenn die Maschine blockiert?",
            _admin_user(admin["id"]),
        )

    diagnostics = result["diagnostics"]
    assert result["answer"].startswith("## Sicherheitshinweis")
    assert diagnostics["safety"]["safety_relevant"] is True
    assert diagnostics["status"] == "safety_blocked"
    assert result["tool_trace"] == []
    assert diagnostics["query_understanding"]["query_type"] == "safety_question"
    assert diagnostics["retrieval_explainability"]["safety"]["safety_relevant"] is True


def test_incident_timeline_detects_sequences(app, make_user, make_error_entry):
    """Verify incident timeline creates ordered events and recurring sequences."""
    admin = make_user(username="timeline_admin", role=Role.MASTER_ADMIN)
    make_error_entry("Linie 5", "V-500", "Temperaturanstieg")
    make_error_entry("Linie 5", "V-501", "Vibration")

    with app.app_context():
        for entry in ErrorEntry.query.all():
            entry.created_at = datetime.now(UTC)
        db.session.commit()
        payload = incident_timeline(_admin_user(admin["id"]), {"days": "30", "limit": "10"})

    assert payload["items"]
    assert payload["sequences"]
    assert payload["stats"]["event_count"] >= 2


def test_admin_retrieval_debug_endpoint_is_prompt_safe(app, client, make_user, auth_headers):
    """Verify admins can inspect retrieval debug metadata without chunk text."""
    admin = make_user(username="debug_admin", role=Role.MASTER_ADMIN)
    with app.app_context():
        _create_document(
            admin["id"],
            "Debug Dokument",
            {"machines": ["Anlage 1"]},
            text="Private chunk text must not appear in debug.",
        )

    chat_response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(admin["username"]),
        json={"message": "Was sagt das Dokument zu Anlage 1?"},
    )
    with app.app_context():
        admin_user = _admin_user(admin["id"])
        audit_id = create_ai_audit_event(
            user=admin_user,
            workflow="assistant",
            diagnostics={
                "status": "local_answer",
                "retrieval_explainability": {
                    "source_count": 1,
                    "explained_source_count": 1,
                    "sources": [
                        {
                            "type": "knowledge",
                            "id": 77,
                            "source_type": "upload",
                            "source_id": 55,
                            "source_record_id": 55,
                            "source_kind": "rag",
                            "knowledge_source_type": "upload",
                            "module": "knowledge",
                            "machine_id": 12,
                            "role_visibility": "department:Produktion",
                            "created_at": "2026-05-30T10:00:00",
                            "chunk_id": 88,
                            "score": 42,
                            "section_title": "Debug Abschnitt",
                            "explainability": {
                                "final_score": 42,
                                "quality_status": "admin_approved",
                                "machine_match": 0.8,
                                "machine_match_reasons": ["machine_entity_match"],
                            },
                        },
                    ],
                },
            },
            source_count=1,
        )
        db.session.add(
            ChatMessage(
                user_id=admin["id"],
                message="Debug deterministische Metadaten",
                response="Gekuerzte Antwort ohne Chunktext.",
                response_type="assistant",
                diagnostics_json="{}",
                source_count=1,
                confidence_score=80,
                confidence_level="high",
                audit_event_id=audit_id,
                created_at=datetime.now(UTC),
            )
        )
        db.session.commit()
    debug_response = client.get(
        "/api/v1/admin/ai/retrieval-debug",
        headers=auth_headers(admin["username"]),
    )
    payload = debug_response.get_json()["data"]

    assert chat_response.status_code == 200
    assert debug_response.status_code == 200
    assert payload["items"]
    item = payload["items"][0]
    flow_step_keys = {step["key"] for step in item["flow_steps"]}
    assert {
        "question",
        "structured_retrieval",
        "rag_chunks",
        "reranking",
        "context_builder",
        "safety",
        "generation",
        "confidence",
    }.issubset(flow_step_keys)
    assert "answer_preview" in item
    assert "source_answer_links" in item
    assert "safety_checks" in item
    assert "context_builder" in item
    rag_chunk = item["rag_chunks"][0]
    score_row = item["scores"]["source_scores"][0]
    assert rag_chunk["knowledge_source_type"] == "upload"
    assert rag_chunk["module"] == "knowledge"
    assert rag_chunk["source_type"] == "upload"
    assert rag_chunk["source_id"] == 55
    assert rag_chunk["source_record_id"] == 55
    assert rag_chunk["source_kind"] == "rag"
    assert rag_chunk["machine_id"] == 12
    assert rag_chunk["role_visibility"] == "department:Produktion"
    assert rag_chunk["created_at"]
    assert score_row["knowledge_source_type"] == "upload"
    assert score_row["source_type"] == "upload"
    assert score_row["source_id"] == 55
    assert score_row["source_record_id"] == 55
    assert score_row["source_kind"] == "rag"
    assert score_row["machine_id"] == 12
    assert score_row["role_visibility"] == "department:Produktion"
    assert item["machine_references"][0]["source_record_id"] == 55
    assert item["machine_references"][0]["machine_id"] == 12
    assert item["source_answer_links"][0]["source"]["role_visibility"] == ("department:Produktion")
    assert "Private chunk text" not in str(payload)
    assert payload["privacy"]["shows_chunk_text"] is False
    assert payload["privacy"]["shows_full_answer"] is False
