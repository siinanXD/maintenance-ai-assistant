"""Tests for AI feature endpoints and services."""

import json
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest

from app.extensions import db
from app.models import (
    AIAuditEvent,
    AIFeedback,
    AssistantTrainingEntry,
    ChatMessage,
    EmployeeMachineQualification,
    ErrorEntry,
    GeneratedDocument,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeGap,
    Machine,
    Priority,
    RetrievalEvaluationRun,
    Role,
    User,
)
from app.services.ai_audit_service import (
    ai_analytics_summary,
    ai_user_usage_metrics,
    create_ai_audit_event,
)
from app.services.ai_confidence_service import calculate_ai_confidence
from app.services.ai_observability_service import (
    _evaluation_quality_actions,
    _observability_recommended_actions,
    ai_observability_dashboard,
)
from app.services.ai_routing import estimate_cost_usd, workflow_profile
from app.services.ai_service import get_ai_provider
from app.services.document_service import document_path
from app.services.empty_retrieval_response_service import build_empty_retrieval_answer
from app.services.knowledge_service import register_source_document
from app.services.order_planning_service import plan_order
from app.services.retrieval_telemetry_service import retrieval_quality_analytics
from app.services.vector_sync_status_service import (
    clear_vector_sync_observability,
    record_vector_sync_failure,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TASK_SOURCE_FIELDS = {
    "blocked_reason",
    "completed_by_user",
    "creator",
    "current_worker",
    "description",
}
FORBIDDEN_INCIDENT_SOURCE_FIELDS = {
    "description",
    "downtime_minutes",
    "impact",
    "possible_causes",
    "production_loss_minutes",
    "solution",
    "symptoms",
}
AGGREGATE_SOURCE_FIELDS = {
    "count",
    "created_at",
    "id",
    "module",
    "role_visibility",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "title",
    "type",
    "url",
}
MACHINE_SOURCE_FIELDS = {
    "created_at",
    "criticality",
    "id",
    "last_downtime_at",
    "machine",
    "machine_id",
    "module",
    "produced_item",
    "role_visibility",
    "site_id",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "status",
    "title",
    "type",
    "url",
}
VACATION_SOURCE_FIELDS = {
    "created_at",
    "days_used",
    "department",
    "employee_id",
    "employee_name",
    "end_date",
    "id",
    "module",
    "role_visibility",
    "shift_type",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "start_date",
    "status",
    "title",
    "type",
    "url",
}
EMPLOYEE_SOURCE_FIELDS = {
    "created_at",
    "department",
    "employee_access_level",
    "id",
    "module",
    "role_visibility",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "title",
    "type",
    "url",
}
DOCUMENT_SOURCE_FIELDS = {
    "created_at",
    "department",
    "document_type",
    "id",
    "machine",
    "machine_id",
    "module",
    "quality_status",
    "role_visibility",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "status",
    "title",
    "type",
    "updated_at",
    "url",
}
MANUAL_SOURCE_FIELDS = {
    "created_at",
    "department",
    "document_type",
    "id",
    "machine",
    "machine_id",
    "module",
    "role_visibility",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "title",
    "type",
    "updated_at",
    "url",
}
SHIFTPLAN_ENTRY_SOURCE_FIELDS = {
    "created_at",
    "department",
    "employee_id",
    "employee_name",
    "end_time",
    "id",
    "machine",
    "machine_id",
    "module",
    "plan_id",
    "role_visibility",
    "shift",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "start_time",
    "title",
    "type",
    "url",
    "work_date",
}
SHIFTPLAN_COVERAGE_SOURCE_FIELDS = {
    "assigned",
    "created_at",
    "department",
    "id",
    "machine",
    "machine_id",
    "missing",
    "module",
    "plan_id",
    "required",
    "role_visibility",
    "shift",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "title",
    "type",
    "url",
    "work_date",
}
INVENTORY_SOURCE_FIELDS = {
    "created_at",
    "criticality",
    "id",
    "lead_time_days",
    "machine",
    "machine_id",
    "manufacturer",
    "min_quantity",
    "module",
    "name",
    "quantity",
    "role_visibility",
    "source_id",
    "source_kind",
    "source_record_id",
    "source_type",
    "title",
    "type",
    "url",
}
FORBIDDEN_INVENTORY_SOURCE_FIELDS = {
    "site",
    "total_value",
    "unit_cost",
}
FORBIDDEN_SHIFTPLAN_SOURCE_FIELDS = {
    "notes",
    "preferences",
    "reason",
    "suggestion",
}
FORBIDDEN_DOCUMENT_SOURCE_FIELDS = {
    "analysis",
    "approval_comment",
    "approved_by",
    "extracted_text",
    "original_filename",
    "relative_path",
    "rejected_by",
    "rejection_comment",
    "summary",
}
FORBIDDEN_EMPLOYEE_SOURCE_FIELDS = {
    "birth_date",
    "city",
    "current_shift",
    "documents",
    "favorite_machine",
    "last_shift",
    "machine_qualifications",
    "next_shift",
    "postal_code",
    "qualifications",
    "salary_group",
    "shift_model",
    "street",
}
FORBIDDEN_VACATION_SOURCE_FIELDS = {
    "approved_by",
    "cancelled_by",
    "impact_summary",
    "notes",
    "reason",
    "representative",
    "representative_employee_id",
    "requested_by",
}


def test_calculate_ai_confidence_structured_employee_documents():
    """Verify structured employee document answers use high SQL confidence."""
    confidence = calculate_ai_confidence(
        "Welche Mitarbeiter haben Dokumente hinterlegt?",
        [{"type": "employee", "id": 1}],
        response_type="employee_document_list",
    )
    assert confidence.level == "high"
    assert confidence.score >= 70


def test_calculate_ai_confidence_structured_scope_local_answer():
    """Verify structured scope answers use high SQL confidence via local_answer."""
    confidence = calculate_ai_confidence(
        "Wie viele offene Aufgaben?",
        [{"type": "task", "id": 1}],
        response_type="structured_scope",
        result={"diagnostics": {"status": "local_answer"}},
    )
    assert confidence.level == "high"


def test_ai_confidence_scores_high_for_strong_sourced_context(app, make_user):
    """Verify strong sources, quality, machine match, and feedback yield high confidence."""
    user = make_user(username="ai_confidence_high_user")
    sources = [
        {
            "type": "knowledge",
            "id": 11,
            "chunk_id": 101,
            "title": "Presse 3 E104",
            "score": 120,
            "quality_status": "admin_approved",
            "machine_match": 1.0,
        },
        {"type": "error", "id": 12, "title": "E104", "score": 95},
        {"type": "machine", "id": 13, "title": "Presse 3", "score": 88},
    ]
    with app.app_context():
        db.session.add(
            AIFeedback(
                user_id=user["id"],
                prompt="Fehler E104 Presse 3",
                response="Sensor reinigen",
                response_type="assistant",
                rating="helpful",
                sources_json=json.dumps([sources[0]], ensure_ascii=True),
                source_count=1,
            ),
        )
        db.session.commit()

        confidence = calculate_ai_confidence(
            "Was hilft bei Fehler E104 an Presse 3?",
            sources,
            response_type="assistant",
        ).to_dict()

    assert confidence["level"] == "high"
    assert confidence["score"] >= 70
    assert confidence["factors"]["feedback"] > 0.58
    assert "hallucination detection" in confidence["method"]


def test_ai_audit_stores_sanitized_retrieval_explainability(app, make_user):
    """Verify audit explainability keeps scores and source ids but no sensitive text."""
    user = make_user(username="ai_explainability_audit_user")
    raw_explainability = {
        "source_count": 1,
        "explained_source_count": 1,
        "averages": {
            "semantic_similarity": 0.82,
            "lexical_score": 41.2,
            "machine_match": 0.9,
            "feedback_influence": 4.0,
            "recency_influence": 2.0,
        },
        "quality_status_counts": {"admin_approved": 1},
        "machine_match_count": 1,
        "feedback_influenced_count": 1,
        "recency_influenced_count": 1,
        "sources": [
            {
                "type": "knowledge",
                "id": 7,
                "source_type": "manual_training",
                "source_id": 42,
                "source_record_id": 42,
                "source_kind": "rag",
                "knowledge_source_type": "manual_training",
                "module": "knowledge",
                "machine_id": 99,
                "role_visibility": "department:Produktion",
                "employee_access_level": "shift",
                "created_at": "2026-05-30T10:00:00",
                "chunk_id": 70,
                "score": 118,
                "title": "Sensitive source title",
                "prompt": "Sensitive prompt",
                "context": "Sensitive retrieved content",
                "explainability": {
                    "semantic_similarity": 0.82,
                    "lexical_score": 41.2,
                    "lexical_similarity": 0.75,
                    "machine_match": 0.9,
                    "quality_status": "admin_approved",
                    "feedback_influence": 4.0,
                    "recency_influence": 2.0,
                },
            },
        ],
        "retrieval_debug": {
            "top_k": 4,
            "rerank_candidate_limit": 20,
            "vector_candidates_found": 12,
            "final_visible_sources": 3,
            "decision_trace": [
                {
                    "step": "vector_candidate_scan",
                    "status": "ok",
                    "reason": "candidate_pool",
                    "metrics": {"query": "Sensitive query", "candidate_count": 12},
                }
            ],
        },
    }

    with app.app_context():
        event_id = create_ai_audit_event(
            db.session.get(User, user["id"]),
            "assistant",
            {
                "status": "local_answer",
                "retrieval_explainability": raw_explainability,
            },
            source_count=1,
        )
        event = db.session.get(AIAuditEvent, event_id)
        explainability = event.retrieval_explainability()

    stored_json = json.dumps(explainability, ensure_ascii=True)
    assert explainability["explained_source_count"] == 1
    assert explainability["sources"][0]["type"] == "knowledge"
    assert explainability["sources"][0]["id"] == 7
    assert explainability["sources"][0]["source_type"] == "manual_training"
    assert explainability["sources"][0]["source_id"] == 42
    assert explainability["sources"][0]["source_record_id"] == 42
    assert explainability["sources"][0]["source_kind"] == "rag"
    assert explainability["sources"][0]["knowledge_source_type"] == "manual_training"
    assert explainability["sources"][0]["machine_id"] == 99
    assert explainability["sources"][0]["role_visibility"] == "department:Produktion"
    assert explainability["sources"][0]["employee_access_level"] == "shift"
    assert explainability["sources"][0]["explainability"]["semantic_similarity"] == 0.82
    assert explainability["retrieval_debug"]["reranking"]["candidate_limit"] == 20
    assert explainability["retrieval_debug"]["reranking"]["candidate_count"] == 12
    assert explainability["retrieval_debug"]["reranking"]["final_source_count"] == 3
    assert "query" not in explainability["retrieval_debug"]["decision_trace"][0]["metrics"]
    assert "Sensitive" not in stored_json
    assert "prompt" not in stored_json
    assert "context" not in stored_json


def test_empty_retrieval_general_question_stays_neutral():
    """Verify broad empty retrieval answers stay helpful without inventing content."""
    answer = build_empty_retrieval_answer(
        "Kannst du eine unbekannte Wartungsregel erklaeren?",
        retrieval={
            "rag": {
                "query_classification": {
                    "query_type": "GENERAL",
                    "extracted_keywords": [],
                    "possible_entities": {},
                    "suggested_sources": [],
                }
            }
        },
    )

    assert "Keine belastbare Quelle gefunden" in answer
    assert "Gepruefte Datenquellen" in answer
    assert "Tasks" in answer
    assert "Fehlerkatalog" in answer
    assert "Wahrscheinlicher Grund" in answer
    assert "keine passenden Treffer ermittelt" in answer
    assert "Ohne Quelle" in answer
    assert "konkrete Loesung" in answer
    assert "Kandidaten gefunden" not in answer


def test_empty_retrieval_answer_explains_filtered_candidates_without_counts():
    """Verify non-admin empty answers explain filtering without exposing counters."""
    answer = build_empty_retrieval_answer(
        "Was bedeutet Fehler E404?",
        retrieval={
            "rag": {
                "query_classification": {
                    "query_type": "HYBRID",
                    "extracted_keywords": ["fehler"],
                    "possible_entities": {"error_codes": ["E404"]},
                    "suggested_sources": ["errors", "knowledge"],
                },
                "retrieval_debug": {
                    "sql_candidates_found": 1,
                    "vector_candidates_found": 2,
                    "permission_filtered": 1,
                    "quality_filtered": 1,
                    "score_anchor_filtered": 1,
                    "final_visible_sources": 0,
                },
            }
        },
    )

    assert "Wahrscheinlicher Grund" in answer
    assert "Sichtbarkeits-, Qualitaets- oder Relevanzpruefung" in answer
    assert "SQL candidate count" not in answer
    assert "vector candidate count" not in answer


def test_openai_compatible_provider_uses_configured_base_url(app):
    """Verify OpenAI-compatible providers use the configured local API base URL."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai_compatible"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"

        provider = get_ai_provider()

    assert provider.name == "openai_compatible"
    assert str(provider.client.base_url).rstrip("/") == "http://127.0.0.1:11434/v1"


def test_openai_provider_ignores_local_base_url(app):
    """Verify official OpenAI mode does not inherit local compatible base URLs."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"

        provider = get_ai_provider()

    assert provider.name == "openai"
    assert str(provider.client.base_url).rstrip("/") != "http://127.0.0.1:11434/v1"


def test_unsupported_ai_provider_falls_back_to_mock(app):
    """Verify unsupported providers stay safe until dedicated adapters exist."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "gemini"
        app.config["OPENAI_API_KEY"] = "test-key"

        provider = get_ai_provider()

    assert provider.name == "mock"


def test_admin_ai_summary_is_admin_only(
    client,
    make_user,
    auth_headers,
):
    """Verify AI analytics summary is restricted to master admins."""
    admin = make_user(
        username="ai_summary_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="ai_summary_user")

    forbidden_response = client.get(
        "/api/v1/admin/ai/summary",
        headers=auth_headers(user["username"]),
    )
    forbidden_user_metrics_response = client.get(
        "/api/v1/admin/ai/users",
        headers=auth_headers(user["username"]),
    )
    admin_response = client.get(
        "/api/v1/admin/ai/summary",
        headers=auth_headers(admin["username"]),
    )
    admin_user_metrics_response = client.get(
        "/api/v1/admin/ai/users",
        headers=auth_headers(admin["username"]),
    )

    assert forbidden_response.status_code == 403
    assert forbidden_user_metrics_response.status_code == 403
    assert admin_response.status_code == 200
    assert admin_user_metrics_response.status_code == 200
    assert set(admin_response.get_json().keys()) >= {
        "average_latency_ms",
        "estimated_cost_usd",
        "events_total",
        "fallback_count",
        "feedback",
        "langfuse_metrics",
        "latest_events",
        "price_configuration",
        "total_tokens",
        "user_metrics",
        "workflow_metrics",
    }
    assert "items" in admin_user_metrics_response.get_json()["data"]


def test_ai_analytics_summary_reports_ops_readiness(app, make_user):
    """Verify AI summary exposes demo-ready operational KPIs."""
    user = make_user(username="ai_ops_summary_user")
    with app.app_context():
        actor = type("UserRef", (), {"id": user["id"]})()
        create_ai_audit_event(
            actor,
            "task_suggestion",
            {
                "status": "openai_used",
                "input_tokens": 80,
                "cached_tokens": 20,
                "output_tokens": 20,
                "total_tokens": 100,
                "latency_ms": 200,
                "estimated_cost_usd": 0.01,
            },
        )
        create_ai_audit_event(
            actor,
            "general_chat",
            {
                "status": "openai_error",
                "error": "rate_limit",
                "fallback_used": True,
                "input_tokens": 40,
                "output_tokens": 10,
                "total_tokens": 50,
                "latency_ms": 1200,
                "estimated_cost_usd": 0.005,
            },
        )
        create_ai_audit_event(
            actor,
            "general_chat",
            {
                "status": "local_answer",
                "fallback_used": True,
            },
        )
        db.session.commit()

        summary = ai_analytics_summary(days=7)

    assert summary["fallback_rate"] == 0.67
    assert summary["error_rate"] == 0.33
    assert summary["cache_rate"] == 0.17
    assert summary["cost_per_1k_tokens"] == 0.1
    assert summary["price_configuration"]["message"] == "Kosten nicht konfiguriert"
    assert summary["user_metrics"][0]["username"] == user["username"]
    assert summary["user_metrics"][0]["langfuse_user_id"] == f"user:{user['id']}"
    assert summary["user_metrics"][0]["estimated_cost_usd"] == 0.015
    assert summary["top_workflows"][0]["workflow"] == "general_chat"
    assert summary["top_workflows"][0]["errors"] == 1
    assert summary["top_errors"][0] == {"error_category": "rate_limit", "count": 1}
    assert summary["readiness"]["status"] == "critical"
    assert summary["readiness"]["reasons"]
    assert "retrieval_quality" in summary


def test_ai_user_usage_metrics_group_costs_by_user(app, make_user):
    """Verify AI usage and costs are grouped by app user for admin reporting."""
    first_user = make_user(username="ai_cost_first_user")
    second_user = make_user(username="ai_cost_second_user")
    with app.app_context():
        first_actor = type("UserRef", (), {"id": first_user["id"]})()
        second_actor = type("UserRef", (), {"id": second_user["id"]})()
        create_ai_audit_event(
            first_actor,
            "chat",
            {
                "status": "openai_used",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "estimated_cost_usd": 0.003,
            },
        )
        create_ai_audit_event(
            first_actor,
            "general_chat",
            {
                "status": "openai_error",
                "fallback_used": True,
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "estimated_cost_usd": 0.001,
                "error": "rate_limit",
            },
        )
        create_ai_audit_event(
            second_actor,
            "chat",
            {
                "status": "openai_used",
                "input_tokens": 40,
                "output_tokens": 10,
                "total_tokens": 50,
                "estimated_cost_usd": 0.01,
            },
        )
        db.session.commit()

        metrics = ai_user_usage_metrics(days=7, limit=10)

    assert metrics[0]["username"] == second_user["username"]
    assert metrics[0]["estimated_cost_usd"] == 0.01
    first_metrics = next(item for item in metrics if item["user_id"] == first_user["id"])
    assert first_metrics["langfuse_user_id"] == f"user:{first_user['id']}"
    assert first_metrics["events"] == 2
    assert first_metrics["fallback_rate"] == 0.5
    assert first_metrics["error_rate"] == 0.5
    assert first_metrics["total_tokens"] == 180
    assert first_metrics["estimated_cost_usd"] == 0.004


def test_retrieval_quality_analytics_aggregates_prompt_safe_signals(app, make_user):
    """Verify retrieval telemetry aggregates quality signals without raw content."""
    user = make_user(username="retrieval_telemetry_user")

    with app.app_context():
        used_document = KnowledgeDocument(
            source_type="upload",
            title="Telemetry Used Source",
            original_filename="used.txt",
            relative_path="uploads/used.txt",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            quality_status="admin_approved",
            is_public=True,
            chunk_count=1,
        )
        unused_document = KnowledgeDocument(
            source_type="upload",
            title="Telemetry Unused Source",
            original_filename="unused.txt",
            relative_path="uploads/unused.txt",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            quality_status="admin_approved",
            is_public=True,
            chunk_count=1,
        )
        db.session.add_all([used_document, unused_document])
        db.session.flush()
        used_text = "Sensitive used chunk text must not appear in telemetry."
        unused_text = "Sensitive unused chunk text must not appear in telemetry."
        used_chunk = KnowledgeChunk(
            document_id=used_document.id,
            chunk_index=0,
            text=used_text,
            token_text="telemetry used",
        )
        unused_chunk = KnowledgeChunk(
            document_id=unused_document.id,
            chunk_index=0,
            text=unused_text,
            token_text="telemetry unused",
            entities_json=json.dumps(
                {
                    "_chunk_metadata": {
                        "chunk_char_count": len(unused_text),
                        "chunk_line_count": 1,
                        "chunk_token_count": 8,
                        "chunk_block_count": 2,
                        "chunk_block_kinds": "list,paragraph",
                        "chunking_mode": "hybrid_semantic",
                        "section_title": "Unused Maintenance Notes",
                    }
                },
                ensure_ascii=True,
            ),
        )
        db.session.add_all([used_chunk, unused_chunk])
        db.session.flush()
        used_document_id = used_document.id
        used_chunk_id = used_chunk.id
        unused_chunk_id = unused_chunk.id
        source_payload = {
            "type": "knowledge",
            "id": used_document_id,
            "source_record_id": 44,
            "source_kind": "rag",
            "knowledge_source_type": "machine_manual",
            "module": "knowledge",
            "machine_id": 12,
            "role_visibility": "department:Produktion",
            "created_at": "2026-05-30T10:00:00",
            "chunk_id": used_chunk_id,
            "score": 12,
            "explainability": {
                "quality_status": "admin_approved",
                "final_score": 12,
            },
        }
        create_ai_audit_event(
            user=type("UserStub", (), {"id": user["id"]})(),
            workflow="general_chat",
            diagnostics={
                "status": "openai_used",
                "confidence_score": 82,
                "retrieval_explainability": {
                    "source_count": 1,
                    "explained_source_count": 1,
                    "retrieval_debug": {
                        "top_k": 4,
                        "rerank_candidate_limit": 20,
                        "vector_candidates_found": 10,
                        "final_visible_sources": 1,
                    },
                    "sources": [source_payload],
                },
            },
            source_count=1,
        )
        create_ai_audit_event(
            user=type("UserStub", (), {"id": user["id"]})(),
            workflow="general_chat",
            diagnostics={
                "status": "local_answer",
                "confidence_score": 18,
            },
            source_count=0,
        )
        db.session.add(
            AIFeedback(
                user_id=user["id"],
                prompt="Sensitive prompt must not appear.",
                response="Sensitive answer must not appear.",
                response_type="assistant",
                rating="not_helpful",
                sources_json=json.dumps(
                    [
                        {
                            "type": "knowledge",
                            "id": used_document_id,
                            "chunk_id": used_chunk_id,
                            "title": used_document.title,
                            "score": 12,
                        }
                    ],
                    ensure_ascii=True,
                ),
                source_count=1,
            )
        )
        db.session.add(
            KnowledgeGap(
                question="Sensitive gap question must not appear.",
                question_hash="a" * 64,
                occurrence_count=4,
                status="open",
                machine="Presse 3",
                department="Produktion",
                user_id=user["id"],
            )
        )
        db.session.commit()

        telemetry = retrieval_quality_analytics(days=30, limit=5)

    top_source = telemetry["source_usage"]["top_sources"][0]
    poor_source = telemetry["poor_sources"][0]
    top_gap = telemetry["knowledge_gaps"]["top_gaps"][0]
    unused_sample = telemetry["unused_chunks"]["sample"]
    telemetry_text = json.dumps(telemetry, ensure_ascii=True)

    assert top_source["id"] == used_document_id
    assert top_source["audit_uses"] == 1
    assert top_source["source_record_id"] == 44
    assert top_source["source_kind"] == "rag"
    assert top_source["knowledge_source_type"] == "machine_manual"
    assert top_source["machine_id"] == 12
    assert top_source["role_visibility"] == "department:Produktion"
    assert telemetry["source_usage"]["source_kind_distribution"]["rag"] == 1
    assert poor_source["not_helpful_feedback"] == 1
    assert poor_source["source_record_id"] == 44
    assert poor_source["source_kind"] == "rag"
    assert poor_source["knowledge_source_type"] == "machine_manual"
    assert telemetry["unsuccessful_questions"]["no_source_events"] == 1
    assert telemetry["unsuccessful_questions"]["low_confidence_events"] == 1
    assert telemetry["reranking"]["request_count"] == 1
    assert telemetry["reranking"]["average_candidate_limit"] == 20
    assert telemetry["reranking"]["average_candidate_count"] == 10
    assert telemetry["reranking"]["average_final_top_k"] == 4
    assert telemetry["reranking"]["average_final_source_count"] == 1
    assert telemetry["reranking"]["average_reduction_rate"] == 0.9
    assert top_gap["question_hash"] == "a" * 64
    assert "question" not in top_gap
    assert telemetry["negative_feedback"]["total"] == 1
    unused_item = next(item for item in unused_sample if item["chunk_id"] == unused_chunk_id)
    assert telemetry["unused_chunks"]["chunk_size_metrics"]["measured_chunk_count"] == 1
    assert telemetry["unused_chunks"]["chunk_size_metrics"]["average_char_count"] == len(
        unused_text
    )
    assert telemetry["unused_chunks"]["chunk_size_metrics"]["average_token_count"] == 8
    assert telemetry["unused_chunks"]["chunk_size_metrics"]["average_block_count"] == 2
    assert telemetry["unused_chunks"]["chunk_size_metrics"]["max_block_count"] == 2
    block_kind_distribution = {
        item["key"]: item["count"]
        for item in telemetry["unused_chunks"]["chunk_size_metrics"]["block_kind_distribution"]
    }
    assert block_kind_distribution["list"] == 1
    assert block_kind_distribution["paragraph"] == 1
    assert unused_item["chunk_char_count"] == len(unused_text)
    assert unused_item["chunk_line_count"] == 1
    assert unused_item["chunk_token_count"] == 8
    assert unused_item["chunk_block_count"] == 2
    assert unused_item["chunk_block_kinds"] == ["list", "paragraph"]
    assert unused_item["chunking_mode"] == "hybrid_semantic"
    assert unused_item["section_title"] == "Unused Maintenance Notes"
    assert "Sensitive prompt" not in telemetry_text
    assert "Sensitive answer" not in telemetry_text
    assert "Sensitive used chunk text" not in telemetry_text


def test_retrieval_slo_metrics_aggregate_operational_signals(app, make_user):
    """Verify retrieval SLO metrics combine audit, feedback, safety, and drift signals."""
    user = make_user(username="retrieval_slo_user")
    clear_vector_sync_observability()
    try:
        with app.app_context():
            stale_document = KnowledgeDocument(
                source_type="upload",
                title="SLO stale source",
                original_filename="slo-stale.txt",
                relative_path="uploads/slo-stale.txt",
                content_type="text/plain",
                department="Produktion",
                status="stale",
                quality_status="admin_approved",
                is_public=True,
                chunk_count=1,
            )
            db.session.add(stale_document)
            db.session.flush()
            record_vector_sync_failure(
                stale_document.id,
                "chroma",
                RuntimeError("sync failed"),
            )
            actor = type("UserStub", (), {"id": user["id"]})()
            create_ai_audit_event(
                user=actor,
                workflow="assistant",
                diagnostics={
                    "status": "openai_used",
                    "confidence_score": 82,
                    "retrieval_explainability": {
                        "retrieval_duration_ms": 100,
                        "safety": {"safety_relevant": False},
                    },
                },
                requested_scopes={"documents"},
                allowed_scopes={"documents"},
                source_count=1,
            )
            create_ai_audit_event(
                user=actor,
                workflow="assistant",
                diagnostics={
                    "status": "fallback_used",
                    "fallback_used": True,
                    "confidence_score": 20,
                    "retrieval_explainability": {
                        "retrieval_duration_ms": 1500,
                        "safety": {
                            "safety_relevant": True,
                            "risk_level": "high",
                            "categories": ["electrical_hazard"],
                        },
                    },
                },
                requested_scopes={"documents", "employees"},
                allowed_scopes={"documents"},
                source_count=0,
            )
            db.session.add_all(
                [
                    AIFeedback(
                        user_id=user["id"],
                        prompt="Prompt must not appear",
                        response="Answer must not appear",
                        response_type="assistant",
                        rating="not_helpful",
                        sources_json="[]",
                        source_count=0,
                    ),
                    AIFeedback(
                        user_id=user["id"],
                        prompt="Other prompt must not appear",
                        response="Other answer must not appear",
                        response_type="assistant",
                        rating="helpful",
                        sources_json="[]",
                        source_count=0,
                    ),
                ]
            )
            db.session.commit()

            telemetry = retrieval_quality_analytics(days=30, limit=5)
    finally:
        clear_vector_sync_observability()

    slo = telemetry["retrieval_slo"]
    values = slo["last_values"]
    assert values["retrieval_p95_ms"] == 1500
    assert values["no_source_rate"] == 0.5
    assert values["low_confidence_rate"] == 0.5
    assert values["permission_filtered_candidate_count"] == 1
    assert values["negative_feedback_rate"] == 0.5
    assert values["safety_risk_count"] == 1
    assert values["fallback_rate"] == 0.5
    assert values["vector_sync_failure_count"] == 1
    assert values["stale_index_count"] == 1
    assert slo["status"] == "critical"
    assert slo["trends"]["retrieval_p95_ms"]["direction"] == "up"
    assert "Prompt must not appear" not in json.dumps(slo, ensure_ascii=True)


def test_retrieval_slo_metrics_warn_on_source_metadata_gaps(app, make_user):
    """Verify retrieval SLOs flag incomplete public source metadata."""
    user = make_user(username="retrieval_slo_metadata_gap_user")
    with app.app_context():
        actor = type("UserStub", (), {"id": user["id"]})()
        create_ai_audit_event(
            user=actor,
            workflow="assistant",
            diagnostics={
                "status": "openai_used",
                "retrieval_explainability": {
                    "retrieval_duration_ms": 120,
                    "sources": [
                        {
                            "type": "knowledge",
                            "id": 10,
                            "source_type": "upload",
                            "source_id": 10,
                            "title": "Complete public metadata",
                            "module": "knowledge",
                            "role_visibility": "public",
                            "created_at": "2026-05-30T10:00:00",
                        },
                        {
                            "type": "knowledge",
                            "id": 11,
                            "title": "Missing derived metadata",
                        },
                    ],
                },
            },
            requested_scopes={"documents"},
            allowed_scopes={"documents"},
            source_count=2,
        )
        db.session.commit()

        telemetry = retrieval_quality_analytics(days=30, limit=5)

    slo = telemetry["retrieval_slo"]
    values = slo["last_values"]
    metadata_warning = next(
        warning
        for warning in slo["warnings"]
        if warning["metric"] == "source_metadata_missing_rate"
    )
    assert values["source_metadata_missing_rate"] == 0.5
    missing_fields = {
        item["field"]: item["count"] for item in values["source_metadata_missing_fields"]
    }
    assert missing_fields == {
        "module": 1,
        "role_visibility": 1,
        "created_at": 1,
    }
    assert metadata_warning["status"] == "critical"
    assert "Complete public metadata" not in json.dumps(slo, ensure_ascii=True)


def test_ai_observability_exposes_retrieval_slo_metadata_gap_warning(app, make_user):
    """Verify AI observability surfaces retrieval SLO metadata-gap warnings."""
    user = make_user(username="ai_observability_slo_gap_user")
    with app.app_context():
        actor = type("UserStub", (), {"id": user["id"]})()
        create_ai_audit_event(
            user=actor,
            workflow="assistant",
            diagnostics={
                "status": "openai_used",
                "retrieval_explainability": {
                    "retrieval_duration_ms": 100,
                    "sources": [
                        {
                            "type": "knowledge",
                            "id": 21,
                            "source_type": "upload",
                            "source_id": 21,
                            "module": "knowledge",
                            "role_visibility": "public",
                            "created_at": "2026-05-30T10:00:00",
                        },
                        {"type": "knowledge", "id": 22},
                    ],
                },
            },
            requested_scopes={"documents"},
            allowed_scopes={"documents"},
            source_count=2,
        )
        db.session.commit()

        dashboard = ai_observability_dashboard({"days": "30", "limit": "5"})

    retrieval_slo = dashboard["metrics"]["retrieval_slo"]
    metadata_warning = next(
        warning
        for warning in dashboard["metrics"]["retrieval_slo_warnings"]
        if warning["metric"] == "source_metadata_missing_rate"
    )
    assert dashboard["metrics"]["telemetry_status"] == "critical"
    assert retrieval_slo["status"] == "critical"
    assert retrieval_slo["source_metadata_missing_rate"] == 0.5
    missing_fields = {
        item["field"]: item["count"] for item in retrieval_slo["source_metadata_missing_fields"]
    }
    assert missing_fields == {
        "module": 1,
        "role_visibility": 1,
        "created_at": 1,
    }
    assert retrieval_slo["warning_count"] >= 1
    assert metadata_warning["status"] == "critical"


def test_retrieval_slo_metrics_handle_empty_data(app):
    """Verify retrieval SLO metrics return safe defaults for empty telemetry."""
    clear_vector_sync_observability()
    with app.app_context():
        telemetry = retrieval_quality_analytics(days=7, limit=5)

    slo = telemetry["retrieval_slo"]
    assert slo["status"] == "ok"
    assert slo["last_values"]["event_count"] == 0
    assert slo["last_values"]["retrieval_p95_ms"] == 0
    assert slo["last_values"]["no_source_rate"] == 0.0
    assert slo["warnings"] == []


def test_ai_observability_dashboard_combines_logs_quality_and_retrieval(
    app,
    make_user,
    make_error_entry,
):
    """Verify AI observability combines monitoring metrics and bounded debug data."""
    user = make_user(username="ai_observability_user")
    make_error_entry(
        "FU",
        "FU-000",
        "Unbekannter FU Fehler",
        description="FU Fehler ohne ausreichende Dokumentation.",
    )
    with app.app_context():
        document = KnowledgeDocument(
            source_type="upload",
            title="Observability Motor FU",
            original_filename="observability.txt",
            relative_path="uploads/observability.txt",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            quality_status="admin_approved",
            is_public=True,
            chunk_count=1,
        )
        db.session.add(document)
        db.session.flush()
        actor = type("UserStub", (), {"id": user["id"]})()
        audit_id = create_ai_audit_event(
            user=actor,
            workflow="assistant",
            diagnostics={
                "status": "openai_used",
                "latency_ms": 240,
                "input_tokens": 200,
                "output_tokens": 120,
                "total_tokens": 320,
                "estimated_cost_usd": 0.012,
                "confidence_score": 84,
                "confidence_level": "high",
                "retrieval_explainability": {
                    "retrieval_duration_ms": 42,
                    "retrieval_debug": {
                        "top_k": 4,
                        "rerank_candidate_limit": 20,
                        "vector_candidates_found": 12,
                        "final_visible_sources": 1,
                    },
                    "sources": [
                        {
                            "type": "knowledge",
                            "id": document.id,
                            "title": "Observability Motor FU",
                            "source_record_id": 123,
                            "source_kind": "rag",
                            "knowledge_source_type": "machine_manual",
                            "module": "knowledge",
                            "machine_id": 456,
                            "role_visibility": "department:Produktion",
                            "employee_access_level": "confidential",
                            "created_at": "2000-01-01T00:00:00",
                            "chunk_id": 77,
                            "score": 88,
                            "section_title": "FU Diagnose",
                            "explainability": {
                                "semantic_similarity": 0.82,
                                "final_score": 88,
                                "quality_status": "admin_approved",
                            },
                        },
                        {
                            "type": "knowledge",
                            "id": document.id,
                            "title": "Observability undated FU",
                            "source_record_id": 124,
                            "source_kind": "rag",
                            "knowledge_source_type": "machine_manual",
                            "module": "knowledge",
                            "machine_id": 456,
                            "role_visibility": "department:Produktion",
                            "chunk_id": 78,
                            "score": 20,
                            "section_title": "FU ohne Datum",
                            "explainability": {
                                "semantic_similarity": 0.82,
                            },
                        },
                    ],
                    "context_builder": {
                        "sections": [
                            {
                                "label": "Knowledge",
                                "source_count": 1,
                                "used_chars": 180,
                            }
                        ],
                        "stats": {"used_chars": 180, "max_chars": 2000},
                    },
                    "query_understanding": {"query_type": "document_question"},
                },
            },
            requested_scopes={"documents"},
            allowed_scopes={"documents"},
            source_count=1,
        )
        sourced_chat = ChatMessage(
            user_id=user["id"],
            message="Welche Dokumente helfen beim FU Fehler?",
            response="Dokument Observability Motor FU nutzen.",
            response_type="assistant",
            diagnostics_json=json.dumps(
                {
                    "confidence_score": 84,
                    "confidence_level": "high",
                    "quality_warnings": [],
                },
                ensure_ascii=True,
            ),
            source_count=1,
            confidence_score=84,
            confidence_level="high",
            audit_event_id=audit_id,
        )
        db.session.add(sourced_chat)
        db.session.add(
            ChatMessage(
                user_id=user["id"],
                message="Welche Quellen widersprechen sich beim FU Fehler?",
                response="Zwei Quellen nennen unterschiedliche naechste Schritte.",
                response_type="assistant",
                diagnostics_json=json.dumps(
                    {
                        "confidence_score": 78,
                        "confidence_level": "high",
                        "source_conflicts": {
                            "has_conflicts": True,
                            "count": 1,
                            "summary": "1 potenzielle Quellenkonflikte erkannt.",
                        },
                        "quality_warnings": [{"type": "source_conflict"}],
                    },
                    ensure_ascii=True,
                ),
                source_count=1,
                confidence_score=78,
                confidence_level="high",
            )
        )
        db.session.add(
            ChatMessage(
                user_id=user["id"],
                message="Welche Ursache hat der unbekannte Fehler FU-000?",
                response="Keine belegte Antwort vorhanden.",
                response_type="assistant",
                diagnostics_json=json.dumps(
                    {
                        "confidence_score": 18,
                        "confidence_level": "low",
                        "empty_retrieval": True,
                        "hallucination_warning": True,
                        "knowledge_gap_id": 321,
                        "knowledge_gap_created": True,
                        "quality_warnings": [
                            {"type": "empty_retrieval"},
                            {"type": "hallucination_risk"},
                        ],
                    },
                    ensure_ascii=True,
                ),
                source_count=0,
                confidence_score=18,
                confidence_level="low",
            )
        )
        db.session.flush()
        db.session.add(
            AIFeedback(
                user_id=user["id"],
                chat_message_id=sourced_chat.id,
                audit_event_id=audit_id,
                prompt="Welche Dokumente helfen beim FU Fehler?",
                response="Dokument Observability Motor FU nutzen.",
                response_type="assistant",
                rating="not_helpful",
                sources_json="[]",
                source_count=1,
            )
        )
        db.session.add(
            AIFeedback(
                user_id=user["id"],
                prompt="Welche Dokumente helfen beim FU Fehler?",
                response="Dokument Observability Motor FU nutzen.",
                response_type="assistant",
                rating="helpful",
                sources_json="[]",
                source_count=1,
            )
        )
        db.session.add(
            KnowledgeGap(
                question="Welche FU Dokumentation fehlt?",
                question_hash="b" * 64,
                occurrence_count=2,
                status="open",
                machine="FU",
                department="Produktion",
                user_id=user["id"],
            )
        )
        db.session.add(
            RetrievalEvaluationRun(
                query_count=4,
                recall_at_k=0.75,
                mrr=0.5,
                ndcg_at_k=0.625,
                keyword_query_count=2,
                keyword_hit_rate=0.5,
                permission_leak_count=1,
                forbidden_source_hit_count=1,
                no_result_count=1,
                no_result_rate=0.25,
                expected_no_result_count=1,
                expected_no_result_success_count=1,
                expected_no_result_success_rate=1.0,
                unexpected_no_result_count=1,
                unexpected_no_result_rate=0.3333,
                min_source_count_fail_count=1,
                min_source_count_pass_rate=0.75,
                query_type_expected_count=3,
                query_type_match_count=2,
                query_type_accuracy=0.6667,
                source_metadata_count=4,
                source_id_coverage_rate=1.0,
                source_type_coverage_rate=1.0,
                source_pair_coverage_rate=0.75,
                metadata_pair_coverage_rate=0.5,
            )
        )
        db.session.commit()

        dashboard = ai_observability_dashboard(
            {"days": "30", "limit": "5", "chat_message_id": str(sourced_chat.id)}
        )

    assert dashboard["metrics"]["average_response_ms"] == 240
    assert dashboard["metrics"]["p95_response_ms"] == 240
    assert dashboard["metrics"]["average_retrieval_ms"] == 42
    assert dashboard["metrics"]["p95_retrieval_ms"] == 42
    assert dashboard["metrics"]["latency"] == {
        "average_response_ms": 240,
        "p95_response_ms": 240,
        "average_retrieval_ms": 42,
        "p95_retrieval_ms": 42,
    }
    assert dashboard["metrics"]["total_requests"] == 1
    assert dashboard["metrics"]["successful_requests"] == 1
    assert dashboard["metrics"]["failed_requests"] == 0
    assert dashboard["metrics"]["request_success_rate"] == 1
    assert dashboard["metrics"]["average_final_top_k"] == 1
    assert dashboard["metrics"]["average_tokens"] == 320
    assert dashboard["metrics"]["token_usage"] == {
        "input_tokens": 200,
        "output_tokens": 120,
        "cached_tokens": 0,
        "total_tokens": 320,
        "average_tokens": 320,
        "cache_rate": 0.0,
    }
    assert dashboard["metrics"]["provider_ready"] is True
    assert dashboard["metrics"]["provider_readiness_status"] == "ok"
    assert dashboard["metrics"]["provider_degraded_component_count"] == 0
    assert dashboard["metrics"]["provider_next_action_type"] == ""
    assert dashboard["metrics"]["cost_windows"]["month"] == 0.012
    assert dashboard["metrics"]["costs"] == {
        "day": 0.012,
        "week": 0.012,
        "month": 0.012,
        "estimated_cost_usd": 0.012,
        "cost_per_1k_tokens": 0.0375,
    }
    assert dashboard["metrics"]["price_configuration"]["message"] == "Kosten nicht konfiguriert"
    assert dashboard["metrics"]["failed_request_count"] == 0
    assert dashboard["metrics"]["retrieval_hit_rate"] == 1
    assert dashboard["metrics"]["source_freshness"]["stale_source_count"] == 1
    assert dashboard["metrics"]["stale_source_count"] == 1
    assert dashboard["metrics"]["stale_source_rate"] == 1
    assert dashboard["metrics"]["undated_source_count"] == 1
    assert dashboard["metrics"]["retrieval_action_count"] == 3
    assert dashboard["metrics"]["retrieval_critical_action_count"] == 0
    assert dashboard["metrics"]["retrieval_high_action_count"] == 1
    assert dashboard["metrics"]["evaluation_action_count"] == 4
    assert dashboard["metrics"]["evaluation_critical_action_count"] == 1
    assert dashboard["metrics"]["evaluation_high_action_count"] == 1
    assert dashboard["metrics"]["evaluation_quality_gate_status"] == "fail"
    assert dashboard["metrics"]["evaluation_quality_gate_passed"] is False
    assert dashboard["metrics"]["evaluation_blocking_count"] == 2
    assert dashboard["metrics"]["evaluation_warning_count"] >= 1
    assert dashboard["metrics"]["evaluation_quality_gate_issue_count"] == (
        dashboard["metrics"]["evaluation_blocking_count"]
        + dashboard["metrics"]["evaluation_warning_count"]
    )
    assert dashboard["metrics"]["source_metadata_gap_count"] == 2
    assert dashboard["metrics"]["source_metadata_gap_fields"] == [
        "source_pair",
        "metadata_pair",
    ]
    assert dashboard["metrics"]["source_metadata_min_coverage_rate"] == 0.5
    assert dashboard["metrics"]["empty_retrieval_count"] == 1
    assert dashboard["metrics"]["no_answer_count"] == 1
    assert dashboard["metrics"]["no_answer_rate"] == 0.3333
    assert dashboard["metrics"]["source_conflict_count"] == 1
    assert dashboard["metrics"]["source_conflict_rate"] == 0.3333
    assert dashboard["metrics"]["answer_quality_distribution"] == {
        "grounded": 1,
        "conflicting_sources": 1,
        "no_answer": 1,
    }
    answer_quality_rows = {
        row["status"]: row for row in dashboard["metrics"]["answer_quality_distribution_rows"]
    }
    assert answer_quality_rows["grounded"]["rate"] == 0.3333
    assert answer_quality_rows["conflicting_sources"]["count"] == 1
    assert dashboard["metrics"]["answer_quality_reason_distribution"] == {
        "sources_available": 1,
        "source_conflict_detected": 1,
        "empty_retrieval_hallucination_guard": 1,
    }
    reason_rows = {
        row["status_reason"]: row
        for row in dashboard["metrics"]["answer_quality_reason_distribution_rows"]
    }
    assert reason_rows["source_conflict_detected"]["count"] == 1
    assert reason_rows["empty_retrieval_hallucination_guard"]["rate"] == 0.3333
    answer_quality_actions = {
        action["type"]: action for action in dashboard["metrics"]["answer_quality_actions"]
    }
    assert dashboard["metrics"]["answer_quality_action_count"] == 2
    assert answer_quality_actions["review_no_answer_guarded_questions"]["priority"] == "high"
    assert answer_quality_actions["review_no_answer_guarded_questions"]["count"] == 1
    assert (
        answer_quality_actions["review_conflicting_answer_sources"]["target"]
        == "source_conflict_detected"
    )
    answer_quality_action_summary = dashboard["metrics"]["answer_quality_action_summary"]
    assert answer_quality_action_summary["total"] == 2
    assert answer_quality_action_summary["high_priority_count"] == 1
    assert answer_quality_action_summary["next_action_type"] == "review_no_answer_guarded_questions"
    assert dashboard["metrics"]["primary_warning_distribution"] == {
        "none": 1,
        "source_conflict": 1,
        "hallucination_risk": 1,
    }
    primary_warning_rows = {
        row["warning_type"]: row
        for row in dashboard["metrics"]["primary_warning_distribution_rows"]
    }
    assert primary_warning_rows["source_conflict"]["count"] == 1
    assert primary_warning_rows["hallucination_risk"]["rate"] == 0.3333
    assert dashboard["metrics"]["uncertainty_distribution"] == {
        "low": 1,
        "medium": 1,
        "high": 1,
    }
    uncertainty_rows = {
        row["uncertainty"]: row for row in dashboard["metrics"]["uncertainty_distribution_rows"]
    }
    assert uncertainty_rows["high"]["count"] == 1
    assert uncertainty_rows["medium"]["rate"] == 0.3333
    assert dashboard["metrics"]["high_uncertainty_count"] == 1
    assert dashboard["metrics"]["high_uncertainty_rate"] == 0.3333
    assert dashboard["metrics"]["uncertain_answer_count"] == 2
    assert dashboard["metrics"]["uncertain_answer_rate"] == 0.6667
    assert dashboard["metrics"]["low_confidence_answers"] == 1
    assert dashboard["metrics"]["low_confidence_answer_count"] == 1
    assert dashboard["metrics"]["low_confidence_rate"] == 0.3333
    assert dashboard["metrics"]["reranking_request_count"] == 1
    assert dashboard["metrics"]["average_rerank_candidate_limit"] == 20
    assert dashboard["metrics"]["average_rerank_candidate_count"] == 12
    assert dashboard["metrics"]["average_rerank_reduction_rate"] == 0.9167
    assert dashboard["metrics"]["reranking"]["average_final_top_k"] == 4
    assert dashboard["metrics"]["reranking"]["average_final_source_count"] == 1
    assert dashboard["metrics"]["hallucination_warning_count"] == 1
    assert dashboard["metrics"]["positive_feedback_count"] == 1
    assert dashboard["metrics"]["negative_feedback_count"] == 1
    assert dashboard["metrics"]["source_distribution"]["knowledge"] == 2
    assert dashboard["metrics"]["source_kind_distribution"]["rag"] == 2
    assert dashboard["metrics"]["top_questions"][0]["count"] == 1
    assert dashboard["metrics"]["frequent_questions"][0]["count"] == 1
    assert any(item["term"] == "fehler" for item in dashboard["metrics"]["frequent_search_terms"])
    assert dashboard["metrics"]["most_used_documents"][0]["source_id"] == document.id
    assert dashboard["metrics"]["knowledge_gaps"]["open_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["recurring_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["machine_gap_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["error_gap_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["uncovered_error_gap_count"] == 0
    assert dashboard["metrics"]["knowledge_gaps"]["critical_uncovered_error_gap_count"] == 0
    assert dashboard["metrics"]["knowledge_gaps"]["uncovered_machine_gap_count"] == 0
    assert dashboard["metrics"]["knowledge_gaps"]["critical_uncovered_machine_gap_count"] == 0
    assert dashboard["metrics"]["knowledge_gaps"]["uncovered_error_gaps"] == []
    assert dashboard["metrics"]["knowledge_gaps"]["uncovered_machine_gaps"] == []
    assert dashboard["metrics"]["knowledge_gaps"]["department_gap_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["uncertain_question_gap_count"] == 1
    assert dashboard["metrics"]["knowledge_gaps"]["high_uncertainty_answer_count"] == 1
    uncertain_gap = dashboard["metrics"]["knowledge_gaps"]["uncertain_question_gaps"][0]
    assert uncertain_gap["question"] == "Welche Ursache hat der unbekannte Fehler FU-000?"
    assert uncertain_gap["answer_uncertainty"] == "high"
    assert uncertain_gap["no_answer_count"] == 1
    assert uncertain_gap["knowledge_gap_id"] == 321
    uncertain_action = dashboard["metrics"]["knowledge_gaps"]["uncertain_question_actions"][0]
    assert dashboard["metrics"]["knowledge_gaps"]["uncertain_question_action_count"] == 1
    assert uncertain_action["type"] == "review_uncertain_answer_gap"
    assert uncertain_action["priority"] == "high"
    assert uncertain_action["target"] == uncertain_gap["question"]
    assert uncertain_action["target_id"] == 321
    assert uncertain_action["next_steps"]
    assert any(
        action["type"] == "review_uncertain_answer_gap"
        for action in dashboard["metrics"]["knowledge_gaps"]["recommended_actions"]
    )
    assert dashboard["metrics"]["knowledge_gaps"]["machine_gaps"][0]["machine"] == "FU"
    error_gap = dashboard["metrics"]["knowledge_gaps"]["error_gaps"][0]
    assert error_gap["error_code"] == "FU-000"
    assert error_gap["machine"] == "FU"
    assert error_gap["coverage"] == "thin"
    department_gap = dashboard["metrics"]["knowledge_gaps"]["department_gaps"][0]
    assert department_gap["department"] == "Produktion"
    assert any(
        item["term"] == "dokumentation"
        for item in dashboard["metrics"]["knowledge_gaps"]["frequent_terms"]
    )
    assert dashboard["metrics"]["knowledge_gaps"]["recommended_actions"][0]["type"] in {
        "thin_machine_documentation",
        "missing_machine_documentation",
    }
    assert dashboard["metrics"]["knowledge_gaps"]["action_count"] >= 1
    assert dashboard["metrics"]["knowledge_gaps"]["high_priority_action_count"] >= 0
    action_priorities = {
        item["key"]
        for item in dashboard["metrics"]["knowledge_gaps"]["action_priority_distribution"]
    }
    action_types = {
        item["key"] for item in dashboard["metrics"]["knowledge_gaps"]["action_type_distribution"]
    }
    assert {"medium"} <= action_priorities or {"high"} <= action_priorities
    assert {
        dashboard["metrics"]["knowledge_gaps"]["recommended_actions"][0]["type"]
    } <= action_types
    assert dashboard["recommended_actions"][0]["type"] == "fix_permission_leaks"
    assert dashboard["recommended_actions"][0]["action_source"] == "evaluation"
    assert dashboard["recommended_actions"][0]["rank"] == 1
    assert dashboard["recommended_actions"][0]["rank_label"] == "P1"
    assert dashboard["next_best_action"]["type"] == "fix_permission_leaks"
    assert dashboard["next_best_action"]["rank"] == 1
    assert dashboard["recommended_actions"][1]["type"] == "improve_retrieval_coverage"
    assert dashboard["recommended_actions"][1]["rank"] == 2
    assert any(
        action["action_source"] == "retrieval_quality"
        and action["type"] == "review_low_quality_retrieval_hits"
        for action in dashboard["recommended_actions"]
    )
    assert any(
        action["action_source"] == "knowledge_gap" for action in dashboard["recommended_actions"]
    )
    recommended_summary = dashboard["recommended_action_summary"]
    assert recommended_summary["total"] == 5
    assert recommended_summary["critical_priority_count"] == 1
    assert recommended_summary["high_priority_count"] == 3
    assert recommended_summary["medium_priority_count"] == 1
    assert recommended_summary["next_action_type"] == "fix_permission_leaks"
    assert recommended_summary["next_action_priority"] == "critical"
    assert recommended_summary["next_action_source"] == "evaluation"
    assert recommended_summary["answer_quality_action_count"] == 2
    assert recommended_summary["answer_quality_high_action_count"] == 1
    assert (
        recommended_summary["answer_quality_next_action_type"]
        == "review_no_answer_guarded_questions"
    )
    assert recommended_summary["answer_quality_next_action_priority"] == "high"
    recommended_sources = {item["key"] for item in recommended_summary["type_distribution"]}
    recommended_action_sources = {
        item["key"]: item["count"] for item in recommended_summary["source_distribution"]
    }
    assert {
        "fix_permission_leaks",
        "improve_retrieval_coverage",
        "review_low_quality_retrieval_hits",
    } <= recommended_sources
    assert recommended_action_sources["evaluation"] == 3
    assert recommended_action_sources["retrieval_quality"] == 1
    assert recommended_action_sources["knowledge_gap"] == 1
    assert dashboard["langfuse_metrics"]["available"] is False
    assert dashboard["langfuse_metrics"]["status"] == "disabled"
    assert dashboard["privacy"]["source_ids_visible"] is False
    assert dashboard["privacy"]["source_metadata_aggregates_visible"] is True
    assert dashboard["quality_metrics"]["retrieval_hit_rate"] == 1
    assert dashboard["quality_metrics"]["average_similarity_score"] == 0.82
    assert dashboard["quality_metrics"]["recall_at_k"] == 0.75
    assert dashboard["quality_metrics"]["keyword_hit_rate"] == 0.5
    assert dashboard["quality_metrics"]["keyword_query_count"] == 2
    assert dashboard["quality_metrics"]["no_result_rate"] == 0.25
    assert dashboard["quality_metrics"]["no_result_count"] == 1
    assert dashboard["quality_metrics"]["expected_no_result_count"] == 1
    assert dashboard["quality_metrics"]["expected_no_result_success_count"] == 1
    assert dashboard["quality_metrics"]["expected_no_result_success_rate"] == 1.0
    assert dashboard["quality_metrics"]["unexpected_no_result_count"] == 1
    assert dashboard["quality_metrics"]["unexpected_no_result_rate"] == 0.3333
    assert dashboard["quality_metrics"]["min_source_count_fail_count"] == 1
    assert dashboard["quality_metrics"]["min_source_count_pass_rate"] == 0.75
    assert dashboard["quality_metrics"]["query_type_expected_count"] == 3
    assert dashboard["quality_metrics"]["query_type_match_count"] == 2
    assert dashboard["quality_metrics"]["query_type_accuracy"] == 0.6667
    assert dashboard["quality_metrics"]["permission_leak_count"] == 1
    assert dashboard["quality_metrics"]["forbidden_source_hit_count"] == 1
    assert dashboard["quality_metrics"]["evaluation_quality_gate"]["status"] == "fail"
    assert dashboard["quality_metrics"]["evaluation_quality_gate"]["passed"] is False
    assert (
        dashboard["quality_metrics"]["evaluation_quality_gate"]["blocking"][0]["metric"]
        == "permission_leak_count"
    )
    assert dashboard["quality_metrics"]["evaluation_blocking_count"] == 2
    assert "permission_leak_count" in dashboard["quality_metrics"]["evaluation_blocking_metrics"]
    blocking_rows = {
        item["metric"]: item for item in dashboard["quality_metrics"]["evaluation_blocking_rows"]
    }
    assert blocking_rows["permission_leak_count"]["value"] == 1
    assert blocking_rows["permission_leak_count"]["threshold"] == 0
    assert (
        blocking_rows["permission_leak_count"]["reason"]
        == "retrieved_forbidden_or_invisible_source"
    )
    assert dashboard["quality_metrics"]["evaluation_warning_count"] >= 1
    assert "keyword_hit_rate" in dashboard["quality_metrics"]["evaluation_warning_metrics"]
    warning_rows = {
        item["metric"]: item for item in dashboard["quality_metrics"]["evaluation_warning_rows"]
    }
    assert warning_rows["keyword_hit_rate"]["value"] == 0.5
    assert warning_rows["keyword_hit_rate"]["threshold"] == 0.6
    assert warning_rows["keyword_hit_rate"]["reason"] == "expected_keywords_missing"
    evaluation_actions = {
        item["type"]: item for item in dashboard["quality_metrics"]["evaluation_actions"]
    }
    assert evaluation_actions["fix_permission_leaks"]["priority"] == "critical"
    assert evaluation_actions["fix_permission_leaks"]["count"] == 1
    coverage_action = evaluation_actions["improve_retrieval_coverage"]
    assert coverage_action["unexpected_no_result_count"] == 1
    assert coverage_action["min_source_count_fail_count"] == 1
    evaluation_action_summary = dashboard["quality_metrics"]["evaluation_action_summary"]
    assert evaluation_action_summary["total"] == 4
    assert evaluation_action_summary["critical_priority_count"] == 1
    assert evaluation_action_summary["high_priority_count"] == 1
    assert evaluation_action_summary["medium_priority_count"] == 2
    assert evaluation_action_summary["next_action_type"] == "fix_permission_leaks"
    assert evaluation_action_summary["next_action_priority"] == "critical"
    evaluation_action_types = {
        item["key"] for item in evaluation_action_summary["type_distribution"]
    }
    assert {
        "fix_permission_leaks",
        "improve_retrieval_coverage",
        "complete_evaluation_source_metadata",
        "review_evaluation_warnings",
    } <= evaluation_action_types
    warning_action = evaluation_actions["review_evaluation_warnings"]
    assert warning_action["count"] >= 1
    assert "keyword_hit_rate" in warning_action["warning_metrics"]
    assert dashboard["quality_metrics"]["source_metadata_count"] == 4
    assert dashboard["quality_metrics"]["source_id_coverage_rate"] == 1.0
    assert dashboard["quality_metrics"]["source_type_coverage_rate"] == 1.0
    assert dashboard["quality_metrics"]["source_pair_coverage_rate"] == 0.75
    assert dashboard["quality_metrics"]["metadata_pair_coverage_rate"] == 0.5
    metadata_gaps = {
        item["field"]: item for item in dashboard["quality_metrics"]["source_metadata_gaps"]
    }
    assert "source_id" not in metadata_gaps
    assert "source_type" not in metadata_gaps
    assert metadata_gaps["source_pair"]["missing_rate"] == 0.25
    assert metadata_gaps["metadata_pair"]["missing_rate"] == 0.5
    metadata_action = evaluation_actions["complete_evaluation_source_metadata"]
    assert metadata_action["fields"] == ["source_pair", "metadata_pair"]
    top_hit = dashboard["retrieval_monitoring"]["top_hits"][0]
    assert top_hit["title"] == "Observability Motor FU"
    assert top_hit["source_record_id"] == 123
    assert top_hit["source_kind"] == "rag"
    assert top_hit["knowledge_source_type"] == "machine_manual"
    assert top_hit["machine_id"] == 456
    assert top_hit["role_visibility"] == "department:Produktion"
    assert top_hit["source_created_at"] == "2000-01-01T00:00:00"
    assert top_hit["source_age_days"] >= 180
    assert top_hit["retrieved_at"]
    assert top_hit["employee_access_level"] == "confidential"
    source_freshness = dashboard["retrieval_monitoring"]["source_freshness"]
    assert source_freshness["stale_threshold_days"] == 180
    assert source_freshness["measured_source_count"] == 1
    assert source_freshness["undated_source_count"] == 1
    assert source_freshness["stale_source_count"] == 1
    assert source_freshness["stale_source_rate"] == 1
    assert source_freshness["oldest_source_age_days"] >= 180
    stale_source = dashboard["retrieval_monitoring"]["stale_sources"][0]
    assert stale_source["title"] == "Observability Motor FU"
    assert stale_source["source_age_days"] >= 180
    assert stale_source["stale_threshold_days"] == 180
    undated_source = dashboard["retrieval_monitoring"]["undated_sources"][0]
    assert undated_source["source_record_id"] == 124
    assert undated_source["section_title"] == "FU ohne Datum"
    assert undated_source["source_created_at"] == ""
    assert undated_source["source_age_days"] is None
    metadata_actions = {
        item["type"]: item for item in dashboard["retrieval_monitoring"]["metadata_quality_actions"]
    }
    stale_action = metadata_actions["review_stale_sources"]
    assert stale_action["count"] == 1
    assert stale_action["stale_threshold_days"] == 180
    assert stale_action["sample_sources"][0]["title"] == "Observability Motor FU"
    undated_action = metadata_actions["complete_source_dates"]
    assert undated_action["count"] == 1
    assert undated_action["sample_sources"][0]["source_record_id"] == 124
    quality_action = dashboard["retrieval_monitoring"]["retrieval_quality_actions"][0]
    assert quality_action["type"] == "review_low_quality_retrieval_hits"
    assert quality_action["priority"] == "high"
    assert quality_action["count"] == 2
    assert quality_action["low_score_count"] == 1
    assert quality_action["sample_sources"][0]["title"] == "Observability Motor FU"
    action_summary = dashboard["retrieval_monitoring"]["action_summary"]
    assert action_summary["total"] == 3
    assert action_summary["critical_priority_count"] == 0
    assert action_summary["high_priority_count"] == 1
    assert action_summary["medium_priority_count"] == 2
    assert action_summary["next_action_type"] == "review_low_quality_retrieval_hits"
    assert action_summary["next_action_priority"] == "high"
    action_types = {item["key"] for item in action_summary["type_distribution"]}
    assert {
        "review_low_quality_retrieval_hits",
        "review_stale_sources",
        "complete_source_dates",
    } <= action_types
    assert dashboard["retrieval_monitoring"]["top_hits"][0]["label"].startswith(
        "Observability Motor FU",
    )
    sourced_log = next(
        item
        for item in dashboard["ai_logs"]
        if item["user_question"] == "Welche Dokumente helfen beim FU Fehler?"
    )
    no_answer_log = next(
        item
        for item in dashboard["ai_logs"]
        if item["user_question"] == "Welche Ursache hat der unbekannte Fehler FU-000?"
    )
    conflict_log = next(
        item
        for item in dashboard["ai_logs"]
        if item["user_question"] == "Welche Quellen widersprechen sich beim FU Fehler?"
    )
    assert sourced_log["answer_quality"]["status"] == "grounded"
    assert sourced_log["answer_quality"]["uncertainty"] == "low"
    assert sourced_log["confidence"]["uncertainty"] == "low"
    assert sourced_log["answer_quality"]["source_count"] == 1
    assert sourced_log["answer_quality_label"] == "good"
    assert sourced_log["sources"][0]["title"] == "Observability Motor FU"
    assert sourced_log["sources"][0]["source_record_id"] == 123
    assert sourced_log["sources"][0]["source_kind"] == "rag"
    assert sourced_log["sources"][0]["knowledge_source_type"] == "machine_manual"
    assert sourced_log["sources"][0]["machine_id"] == 456
    assert sourced_log["sources"][0]["role_visibility"] == "department:Produktion"
    assert sourced_log["sources"][0]["employee_access_level"] == "confidential"
    assert no_answer_log["answer_quality"]["status"] == "no_answer"
    assert no_answer_log["confidence"]["uncertainty"] == "high"
    assert no_answer_log["answer_quality_label"] == "risk"
    assert no_answer_log["knowledge_gap_id"] == 321
    assert no_answer_log["knowledge_gap_created"] is True
    assert conflict_log["answer_quality"]["status"] == "conflicting_sources"
    assert conflict_log["answer_quality_label"] == "conflict"
    assert conflict_log["answer_quality"]["uncertainty"] == "medium"
    assert conflict_log["confidence"]["uncertainty"] == "medium"
    assert dashboard["debug_tools"]["prompt_blueprint"]["system_prompt"]
    assert dashboard["debug_tools"]["request_analysis"]["retrieval"]["source_count"] == 1
    assert dashboard["debug_tools"]["request_analysis"]["answer_quality"]["status"] == ("grounded")
    assert dashboard["debug_tools"]["request_analysis"]["confidence"]["uncertainty"] == "low"
    available = {item["question"]: item for item in dashboard["debug_tools"]["available_requests"]}
    assert (
        available["Welche Ursache hat der unbekannte Fehler FU-000?"]["answer_uncertainty"]
        == "high"
    )


def test_ai_observability_dashboard_exposes_failed_requests_without_prompts(
    app,
    make_user,
):
    """Verify failed AI requests are visible as metadata-only admin rows."""
    user = make_user(username="ai_observability_failed_user")
    with app.app_context():
        actor = type("UserStub", (), {"id": user["id"]})()
        create_ai_audit_event(
            user=actor,
            workflow="general_chat",
            diagnostics={
                "status": "openai_error",
                "error": "rate_limit",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "model_tier": "balanced",
                "fallback_used": True,
                "latency_ms": 1800,
                "total_tokens": 25,
            },
            source_count=0,
        )
        create_ai_audit_event(
            user=actor,
            workflow="general_chat",
            diagnostics={
                "status": "unsupported_provider",
                "error": "AI_PROVIDER is not supported by a dedicated adapter yet",
                "provider": "mock",
                "fallback_used": True,
                "latency_ms": 10,
                "total_tokens": 0,
            },
            source_count=0,
        )
        create_ai_audit_event(
            user=actor,
            workflow="general_chat",
            diagnostics={
                "status": "base_url_missing",
                "provider": "mock",
                "fallback_used": True,
                "latency_ms": 5,
                "total_tokens": 0,
            },
            source_count=0,
        )
        db.session.commit()

        dashboard = ai_observability_dashboard({"days": "30", "limit": "5"})

    failed = next(item for item in dashboard["failed_requests"] if item["status"] == "openai_error")
    unsupported = next(
        item for item in dashboard["failed_requests"] if item["status"] == "unsupported_provider"
    )
    missing_base_url = next(
        item for item in dashboard["failed_requests"] if item["status"] == "base_url_missing"
    )
    serialized = json.dumps(dashboard["failed_requests"], ensure_ascii=True)
    reason_counts = {
        item["reason"]: item["count"]
        for item in dashboard["metrics"]["failure_reason_distribution"]
    }
    assert dashboard["metrics"]["failed_request_count"] == 3
    assert dashboard["metrics"]["total_requests"] == 3
    assert dashboard["metrics"]["successful_requests"] == 0
    assert dashboard["metrics"]["failed_requests"] == 3
    assert dashboard["metrics"]["request_success_rate"] == 0
    assert dashboard["metrics"]["token_usage"]["total_tokens"] == 25
    assert dashboard["metrics"]["latency"]["p95_response_ms"] == 1800
    assert reason_counts["rate_limit"] == 1
    assert reason_counts["unsupported_provider"] == 1
    assert reason_counts["base_url_missing"] == 1
    assert failed["workflow"] == "general_chat"
    assert failed["status"] == "openai_error"
    assert failed["failure_reason"] == "rate_limit"
    assert failed["error_category"] == "rate_limit"
    assert failed["fallback_used"] is True
    assert failed["latency_ms"] == 1800
    assert unsupported["failure_reason"] == "unsupported_provider"
    assert unsupported["error_category"] == (
        "AI_PROVIDER is not supported by a dedicated adapter yet"
    )
    assert missing_base_url["failure_reason"] == "base_url_missing"
    assert missing_base_url["error_category"] == ""
    assert "prompt" not in serialized.lower()
    assert "question" not in serialized.lower()
    assert "answer" not in serialized.lower()


def test_admin_ai_observability_endpoint_is_admin_only(
    client,
    make_user,
    auth_headers,
):
    """Verify AI observability endpoint is restricted to master admins."""
    admin = make_user(
        username="ai_observability_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="ai_observability_regular")

    forbidden_response = client.get(
        "/api/v1/admin/ai/observability",
        headers=auth_headers(user["username"]),
    )
    admin_response = client.get(
        "/api/v1/admin/ai/observability?days=30&limit=5",
        headers=auth_headers(admin["username"]),
    )

    payload = admin_response.get_json()["data"]
    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 200
    assert set(payload.keys()) >= {
        "provider_readiness",
        "metrics",
        "retrieval_monitoring",
        "ai_logs",
        "failed_requests",
        "quality_metrics",
        "recommended_actions",
        "next_best_action",
        "recommended_action_summary",
        "debug_tools",
        "langfuse_metrics",
        "metric_catalog",
        "privacy",
    }
    catalog_keys = {item["key"] for item in payload["metric_catalog"]}
    assert {
        "frequent_questions",
        "frequent_search_terms",
        "average_final_top_k",
        "average_tokens",
        "cost_windows",
        "provider_ready",
        "provider_readiness_status",
        "provider_degraded_component_count",
        "provider_next_action_type",
        "failed_request_count",
        "retrieval_hit_rate",
        "source_freshness",
        "no_answer_rate",
        "recall_at_k",
        "mrr",
        "keyword_hit_rate",
        "no_result_rate",
        "min_source_count_pass_rate",
        "query_type_accuracy",
        "permission_leak_count",
        "evaluation_quality_gate_status",
        "evaluation_quality_gate_issue_count",
        "evaluation_blocking_count",
        "evaluation_warning_count",
        "source_metadata_gap_count",
        "source_metadata_min_coverage_rate",
        "answer_quality_reason_distribution",
        "answer_quality_action_count",
        "retrieval_action_count",
        "evaluation_action_count",
        "feedback",
        "most_used_documents",
        "knowledge_gaps",
    } <= catalog_keys
    assert payload["provider_readiness"]["provider_status"]["provider"] == "mock"
    assert payload["provider_readiness"]["readiness"]["next_action"] is None
    assert not any(
        action["action_source"] == "provider_readiness" for action in payload["recommended_actions"]
    )
    assert payload["privacy"]["raw_chunk_text_visible"] is False


def test_ai_observability_includes_provider_readiness_actions(app):
    """Verify observability exposes provider readiness remediation without secrets."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "gemini"
        app.config["OPENAI_API_KEY"] = "test-secret-key"
        dashboard = ai_observability_dashboard({"days": "30", "limit": "5"})

    provider_readiness = dashboard["provider_readiness"]
    next_action = provider_readiness["readiness"]["next_action"]
    serialized = str(provider_readiness)
    assert provider_readiness["ready"] is False
    assert provider_readiness["provider"] == "gemini"
    assert provider_readiness["provider_status"]["effective_provider"] == "mock"
    assert dashboard["metrics"]["provider_ready"] is False
    assert dashboard["metrics"]["provider_readiness_status"] == "degraded"
    assert dashboard["metrics"]["provider_degraded_component_count"] == 1
    assert dashboard["metrics"]["provider_next_action_type"] == ("select_supported_provider")
    assert next_action["component"] == "provider"
    assert next_action["configuration_action"] == "select_supported_provider"
    assert "AI_PROVIDER" in next_action["recommended_action"]
    assert dashboard["next_best_action"]["action_source"] == "provider_readiness"
    assert dashboard["next_best_action"]["type"] == "select_supported_provider"
    assert dashboard["next_best_action"]["priority"] == "critical"
    assert dashboard["next_best_action"]["rank"] == 1
    assert dashboard["recommended_action_summary"]["next_action_source"] == "provider_readiness"
    assert "test-secret-key" not in serialized
    assert "api_key" not in serialized.lower().replace("api_key_configured", "")


def test_ai_observability_provider_action_outranks_evaluation_action():
    """Verify provider outages are ranked before other critical admin actions."""
    provider_readiness = {
        "ready": False,
        "readiness": {
            "next_action": {
                "component": "provider",
                "reason": "unsupported_provider",
                "configuration_action": "select_supported_provider",
                "recommended_action": "AI_PROVIDER korrigieren.",
            }
        },
    }
    quality_metrics = {
        "evaluation_actions": [
            {
                "type": "fix_permission_leaks",
                "priority": "critical",
                "target": "permission_leak_count",
            }
        ]
    }

    actions = _observability_recommended_actions(
        {"knowledge_gaps": {}},
        {},
        quality_metrics,
        provider_readiness,
        limit=5,
    )

    assert actions[0]["action_source"] == "provider_readiness"
    assert actions[0]["type"] == "select_supported_provider"
    assert actions[0]["rank"] == 1
    assert actions[1]["action_source"] == "evaluation"
    assert actions[1]["type"] == "fix_permission_leaks"
    assert actions[1]["rank"] == 2


def test_ai_observability_evaluation_warning_action_targets_chunk_structure():
    """Verify chunk-structure evaluation warnings get specific admin guidance."""
    actions = _evaluation_quality_actions(
        latest_eval={"query_count": 1},
        quality_gate={
            "warnings": [
                {
                    "metric": "block_metadata_coverage_rate",
                    "value": 0.5,
                    "threshold": 0.8,
                    "reason": "chunk_structure_metadata_incomplete",
                }
            ]
        },
        source_metadata_gaps=[],
    )

    warning_action = actions[0]
    assert warning_action["type"] == "review_evaluation_warnings"
    assert warning_action["warning_metrics"] == ["block_metadata_coverage_rate"]
    assert warning_action["focus_areas"] == ["chunk_structure_metadata"]
    assert "Chunk-Strukturmetadaten" in warning_action["recommended_action"]
    assert any("chunk_block_count" in step for step in warning_action["next_steps"])
    assert any(
        "block_metadata_coverage_rate" in criterion
        for criterion in warning_action["success_criteria"]
    )


def test_admin_retrieval_telemetry_endpoint_is_admin_only(
    client,
    make_user,
    auth_headers,
):
    """Verify retrieval telemetry is exposed only to master admins."""
    admin = make_user(
        username="retrieval_telemetry_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="retrieval_telemetry_regular")

    forbidden_response = client.get(
        "/api/v1/admin/ai/retrieval-telemetry",
        headers=auth_headers(user["username"]),
    )
    admin_response = client.get(
        "/api/v1/admin/ai/retrieval-telemetry?days=30&limit=5",
        headers=auth_headers(admin["username"]),
    )

    payload = admin_response.get_json()["data"]
    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 200
    assert set(payload.keys()) >= {
        "retrieval_slo",
        "retrieval_evaluation_history",
        "source_usage",
        "poor_sources",
        "unsuccessful_questions",
        "knowledge_gaps",
        "negative_feedback",
        "unused_chunks",
    }


def test_admin_ai_events_are_filterable(
    client,
    make_user,
    auth_headers,
):
    """Verify admin AI event search filters metadata without prompts."""
    admin = make_user(
        username="ai_events_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="ai_events_user")
    with client.application.app_context():
        event_id = create_ai_audit_event(
            type("UserRef", (), {"id": user["id"]})(),
            "general_chat",
            {
                "status": "openai_error",
                "error": "rate_limit",
                "total_tokens": 10,
            },
        )
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/events?error=rate_limit",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["items"][0]["id"] == event_id
    assert payload["items"][0]["error_category"] == "rate_limit"
    assert "prompt" not in payload["items"][0]


def test_admin_training_crud_marks_knowledge_stale_and_deletes_document(
    client,
    make_user,
    auth_headers,
):
    """Verify master admins can maintain manual assistant training entries."""
    admin = make_user(
        username="training_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="training_user")
    admin_headers = auth_headers(admin["username"])

    forbidden_response = client.get(
        "/api/v1/admin/ai/training",
        headers=auth_headers(user["username"]),
    )
    invalid_response = client.post(
        "/api/v1/admin/ai/training",
        headers=admin_headers,
        json={"answer": "Ohne Titel"},
    )
    create_response = client.post(
        "/api/v1/admin/ai/training",
        headers=admin_headers,
        json={
            "title": "Hydraulikfilter X900",
            "question": "Wie wird X900 gepflegt?",
            "answer": "Hydraulikfilter X900 taeglich pruefen und Befund dokumentieren.",
            "keywords": ["Hydraulikfilter", "X900", "Filterpflege"],
            "category": "wartung",
            "department": "Produktion",
            "priority": 80,
        },
    )
    entry_id = create_response.get_json()["data"]["id"]
    update_response = client.put(
        f"/api/v1/admin/ai/training/{entry_id}",
        headers=admin_headers,
        json={"answer": "X900 je Schicht pruefen.", "priority": 90},
    )
    list_response = client.get(
        "/api/v1/admin/ai/training?q=X900",
        headers=admin_headers,
    )

    assert forbidden_response.status_code == 403
    assert invalid_response.status_code == 400
    assert invalid_response.get_json()["missing_information"]["status"] == "needs_information"
    assert create_response.status_code == 201
    assert create_response.get_json()["data"]["keywords"] == "Hydraulikfilter, X900, Filterpflege"
    assert (
        create_response.get_json()["data"]["missing_information"]["status"] == "needs_information"
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["priority"] == 90
    assert list_response.get_json()["data"]["pagination"]["total"] == 1
    with client.application.app_context():
        document = KnowledgeDocument.query.filter_by(
            source_type="manual_training",
            source_id=entry_id,
        ).one()
        assert document.status == "stale"

    delete_response = client.delete(
        f"/api/v1/admin/ai/training/{entry_id}",
        headers=admin_headers,
    )

    assert delete_response.status_code == 200
    with client.application.app_context():
        assert db.session.get(AssistantTrainingEntry, entry_id) is None
        assert (
            KnowledgeDocument.query.filter_by(
                source_type="manual_training",
                source_id=entry_id,
            ).first()
            is None
        )


def test_training_active_state_controls_knowledge_document(
    client,
    make_user,
    auth_headers,
):
    """Verify inactive manual training is removed from RAG sources."""
    admin = make_user(
        username="training_active_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    headers = auth_headers(admin["username"])
    create_response = client.post(
        "/api/v1/admin/ai/training",
        headers=headers,
        json={
            "title": "Aktives Training",
            "question": "Wie pruefe ich Training aktiv?",
            "answer": "Training aktiv pruefen und Quelle reindexieren.",
            "is_active": True,
        },
    )
    entry_id = create_response.get_json()["data"]["id"]

    inactive_response = client.put(
        f"/api/v1/admin/ai/training/{entry_id}",
        headers=headers,
        json={"is_active": False},
    )
    with client.application.app_context():
        inactive_document = KnowledgeDocument.query.filter_by(
            source_type="manual_training",
            source_id=entry_id,
        ).first()

    active_response = client.put(
        f"/api/v1/admin/ai/training/{entry_id}",
        headers=headers,
        json={"is_active": True},
    )
    with client.application.app_context():
        active_document = KnowledgeDocument.query.filter_by(
            source_type="manual_training",
            source_id=entry_id,
        ).one()

    assert create_response.status_code == 201
    assert inactive_response.status_code == 200
    assert inactive_document is None
    assert active_response.status_code == 200
    assert active_document.status == "pending"


def test_admin_training_missing_information_complete_state(
    client,
    make_user,
    auth_headers,
):
    """Verify complete manual knowledge entries do not need follow-up prompts."""
    admin = make_user(
        username="training_prompt_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/admin/ai/training",
        headers=auth_headers(admin["username"]),
        json={
            "title": "Maschine 3 E104 Sensor Signal",
            "question": "Was tun bei E104 an Maschine 3, wenn der Sensor kein Signal meldet?",
            "answer": (
                "Maschine 3 sichern, Sensor gereinigt, Kabel geprueft und "
                "Probelauf erfolgreich. Stoerung behoben."
            ),
            "keywords": ["Maschine 3", "E104", "Sensor"],
            "category": "stoerung",
            "department": "Instandhaltung",
            "priority": 80,
        },
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["missing_information"]["status"] == "complete"
    assert response.get_json()["data"]["missing_information"]["missing_fields"] == []


def test_generated_knowledge_documents_default_to_ai_suggested(app):
    """Verify generated knowledge is never implicitly admin-approved."""
    with app.app_context():
        register_source_document(
            source_type="generated_document",
            source_id=99,
            title="AI Wartungsbericht",
            department="Instandhaltung",
            url_path="/documents",
        )
        db.session.commit()

        document = KnowledgeDocument.query.filter_by(
            source_type="generated_document",
            source_id=99,
        ).one()
        assert document.quality_status == "ai_suggested"


def test_master_admin_can_update_knowledge_quality_status(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify master admins can approve a knowledge document explicitly."""
    admin = make_user(
        username="knowledge_quality_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    with app.app_context():
        document = KnowledgeDocument(
            source_type="upload",
            title="Hydraulik Anleitung",
            original_filename="hydraulik.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="draft",
        )
        rejected_document = KnowledgeDocument(
            source_type="upload",
            title="Blockierte OCR Quelle",
            original_filename="ocr.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="low_quality",
        )
        db.session.add_all([document, rejected_document])
        db.session.commit()
        document_id = document.id
        rejected_document_id = rejected_document.id

    response = client.put(
        f"/api/v1/admin/ai/knowledge/{document_id}/quality-status",
        headers=auth_headers(admin["username"]),
        json={"quality_status": "admin_approved"},
    )
    rejected_response = client.put(
        f"/api/v1/admin/ai/knowledge/{rejected_document_id}/quality-status",
        headers=auth_headers(admin["username"]),
        json={"quality_status": "rejected"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["quality_status"] == "admin_approved"
    assert rejected_response.status_code == 200
    assert rejected_response.get_json()["data"]["quality_status"] == "rejected"
    with app.app_context():
        assert db.session.get(KnowledgeDocument, document_id).quality_status == "admin_approved"
        assert db.session.get(KnowledgeDocument, rejected_document_id).quality_status == "rejected"


def test_technician_quality_status_permissions_are_scoped(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify technicians can confirm local knowledge but cannot approve it."""
    technician = make_user(
        username="knowledge_quality_tech",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    with app.app_context():
        own_document = KnowledgeDocument(
            source_type="upload",
            title="Eigener Eintrag",
            original_filename="own.txt",
            content_type="text/plain",
            department="Instandhaltung",
            status="indexed",
            quality_status="draft",
        )
        foreign_document = KnowledgeDocument(
            source_type="upload",
            title="Fremder Eintrag",
            original_filename="foreign.txt",
            content_type="text/plain",
            department="Produktion",
            status="indexed",
            quality_status="draft",
        )
        db.session.add_all([own_document, foreign_document])
        db.session.commit()
        own_id = own_document.id
        foreign_id = foreign_document.id

    headers = auth_headers(technician["username"])
    confirm_response = client.put(
        f"/api/v1/admin/ai/knowledge/{own_id}/quality-status",
        headers=headers,
        json={"quality_status": "technician_confirmed"},
    )
    approve_response = client.put(
        f"/api/v1/admin/ai/knowledge/{own_id}/quality-status",
        headers=headers,
        json={"quality_status": "admin_approved"},
    )
    foreign_response = client.put(
        f"/api/v1/admin/ai/knowledge/{foreign_id}/quality-status",
        headers=headers,
        json={"quality_status": "outdated"},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.get_json()["data"]["quality_status"] == "technician_confirmed"
    assert approve_response.status_code == 403
    assert foreign_response.status_code == 403


def test_knowledge_reindex_registers_generated_documents(
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify reindex adds generated documents to the local knowledge base."""
    admin = make_user(
        username="knowledge_reindex_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    task_id = make_task("Wartung X900", creator_username=admin["username"])
    make_document(task_id=task_id, created_by=admin["id"], department="Produktion")

    response = client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["documents"] >= 1


def test_knowledge_reindex_reports_outdated_database_schema(
    client,
    make_user,
    auth_headers,
    monkeypatch,
):
    """Verify reindex returns actionable diagnostics when migrations are missing."""
    admin = make_user(
        username="knowledge_schema_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    schema_status = {
        "ok": False,
        "missing_tables": [],
        "missing_columns": {"generated_document": ["status"]},
        "migration_command": "flask --app run:app db upgrade",
    }
    monkeypatch.setattr(
        "app.admin.routes.database_schema_status",
        lambda: schema_status,
    )

    response = client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 503
    assert payload["error"] == "database_schema_outdated"
    assert payload["data"]["missing_columns"]["generated_document"] == ["status"]
    assert "db upgrade" in payload["message"]


def test_knowledge_status_reports_rag_index_diagnostics(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify admins can inspect RAG index readiness and source diagnostics."""
    admin = make_user(
        username="knowledge_status_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    make_task(
        "Status RAG Hydraulik",
        creator_username=admin["username"],
        department_name="Instandhaltung",
        description="Hydraulikstatus fuer RAG Diagnose.",
    )
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )
    with client.application.app_context():
        db.session.add(
            KnowledgeDocument(
                source_type="upload",
                title="Fehlerhafte RAG Quelle",
                original_filename="broken.txt",
                status="error",
                error_message="Text konnte nicht extrahiert werden.",
                created_by=admin["id"],
            )
        )
        db.session.add(
            KnowledgeDocument(
                source_type="manual_training",
                title="Veraltete Trainingsquelle",
                original_filename="",
                status="stale",
                created_by=admin["id"],
            )
        )
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/knowledge/status",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["documents"] >= 1
    assert payload["indexed"] >= 1
    assert payload["searchable_documents"] >= 1
    assert payload["chunks"] >= 1
    assert "stale" in payload
    assert "pending" in payload
    assert payload["diagnostics"]["rag_enabled"] is True
    assert payload["diagnostics"]["vector_store"] == "local"
    assert set(payload["chunk_quality"]) == {
        "accepted_chunks",
        "total_chunks_seen",
        "skipped_empty_chunks",
        "skipped_short_chunks",
        "skipped_duplicate_chunks",
        "skipped_low_quality_chunks",
        "skipped_bad_ocr_chunks",
        "affected_documents",
    }
    assert 0 <= payload["readiness_score"] < 100
    assert payload["readiness_reasons"]
    assert any(item["status"] == "error" for item in payload["problem_documents"])
    assert any(item["status"] == "stale" for item in payload["problem_documents"])
    assert any(item["source_type"] == "task" for item in payload["source_types"])


def test_task_update_marks_rag_source_stale_and_reindex_recovers(
    app,
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify changed source data becomes stale and can be reindexed granularly."""
    admin = make_user(
        username="knowledge_stale_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="knowledge_stale_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Stale RAG Task",
        creator_username=user["username"],
        department_name="Instandhaltung",
        description="Alter RAG Inhalt",
    )
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    update_response = client.put(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(user["username"]),
        json={"title": "Aktualisierter Stale RAG Task"},
    )
    stale_response = client.get(
        "/api/v1/admin/ai/knowledge/status",
        headers=auth_headers(admin["username"]),
    )
    stale_reindex_response = client.post(
        "/api/v1/admin/ai/knowledge/reindex?mode=stale",
        headers=auth_headers(admin["username"]),
    )

    with app.app_context():
        db.session.expire_all()
        document = KnowledgeDocument.query.filter_by(
            source_type="task",
            source_id=task_id,
        ).one()
        document_id = document.id
        assert document.status == "indexed"
        assert document.title == "Aktualisierter Stale RAG Task"

    single_reindex_response = client.post(
        f"/api/v1/admin/ai/knowledge/{document_id}/reindex",
        headers=auth_headers(admin["username"]),
    )

    assert update_response.status_code == 200
    assert stale_response.status_code == 200
    assert stale_response.get_json()["data"]["stale"] >= 1
    assert stale_reindex_response.status_code == 200
    assert stale_reindex_response.get_json()["data"]["documents"] == 1
    assert single_reindex_response.status_code == 200
    assert single_reindex_response.get_json()["data"]["status"] == "indexed"


def test_order_plan_selects_machine_staff_and_material(
    app,
    make_user,
    make_machine,
    make_material,
    make_employee,
):
    """Verify the order planner checks machine fit, staffing and stock."""
    admin = make_user(
        username="order_plan_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(
        name="Deckel Linie 1",
        produced_item="Deckel",
        required_employees=2,
    )
    make_material("Deckel Rohling", 1.5, 12, machine_id=machine_id)
    first_employee_id = make_employee(
        personnel_number="OP-001",
        name="Anna Plan",
        department="Produktion",
        qualifications="Deckel Linie",
    )
    second_employee_id = make_employee(
        personnel_number="OP-002",
        name="Ben Plan",
        department="Produktion",
        qualifications="Deckel Linie",
    )
    with app.app_context():
        db.session.add(
            EmployeeMachineQualification(
                employee_id=first_employee_id,
                machine_id=machine_id,
                level="trained",
            )
        )
        db.session.add(
            EmployeeMachineQualification(
                employee_id=second_employee_id,
                machine_id=machine_id,
                level="expert",
            )
        )
        db.session.commit()

    with app.app_context():
        payload, error, _status = plan_order(
            {
                "product": "Deckel",
                "quantity": 10,
                "department": "Produktion",
                "work_date": "2026-05-18",
            },
            db.session.get(User, admin["id"]),
        )

    recommended = payload["recommended_plan"]
    assert error is None
    assert payload["type"] == "order_plan"
    assert recommended["machine"]["id"] == machine_id
    assert recommended["status"] == "feasible"
    assert recommended["material_check"]["status"] == "enough"
    assert recommended["staffing"]["status"] == "covered"
    assert len(recommended["staffing"]["assigned_employees"]) == 2
    assert payload["diagnostics"]["workflow"] == "order_planning"


def test_order_plan_reports_material_shortage(
    app,
    make_user,
    make_machine,
    make_material,
    make_employee,
):
    """Verify the order planner exposes missing stock as a blocker."""
    admin = make_user(
        username="order_shortage_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    machine_id = make_machine(name="Gehaeuse Linie", produced_item="Gehaeuse")
    make_material("Gehaeuse Rohling", 2.0, 3, machine_id=machine_id)
    make_employee(
        personnel_number="OP-003",
        name="Cara Plan",
        department="Produktion",
        qualifications="Gehaeuse Linie",
    )

    with app.app_context():
        payload, error, _status = plan_order(
            {"product": "Gehaeuse", "quantity": 5, "department": "Produktion"},
            db.session.get(User, admin["id"]),
        )

    recommended = payload["recommended_plan"]
    assert error is None
    assert recommended["status"] == "blocked"
    assert recommended["material_check"]["status"] == "shortage"
    assert recommended["material_check"]["missing"][0]["shortage"] == 2
    assert "fehlen" in recommended["blockers"][0]


def test_ai_workflow_routing_uses_balanced_defaults(app):
    """Verify workflow routing selects models, temperature and output budgets."""
    with app.app_context():
        app.config["OPENAI_MODEL_FAST"] = "fast-test-model"
        app.config["OPENAI_MODEL_BALANCED"] = "balanced-test-model"
        app.config["OPENAI_MODEL_QUALITY"] = "quality-test-model"

        task_profile = workflow_profile("task_suggestion")
        priority_profile = workflow_profile("task_prioritization")
        chat_profile = workflow_profile("chat")
        quality_profile = workflow_profile("quality_analysis")

    assert task_profile.model == "fast-test-model"
    assert task_profile.tier == "fast"
    assert task_profile.temperature == 0.1
    assert priority_profile.model == "fast-test-model"
    assert priority_profile.timeout_seconds == 6.0
    assert priority_profile.max_retries == 0
    assert chat_profile.model == "balanced-test-model"
    assert chat_profile.tier == "balanced"
    assert chat_profile.max_tokens == 750
    assert quality_profile.model == "quality-test-model"
    assert quality_profile.tier == "quality"


def test_ai_workflow_routing_falls_back_to_configured_model(app):
    """Verify missing tier overrides use the configured base model."""
    with app.app_context():
        for key in ("OPENAI_MODEL_FAST", "OPENAI_MODEL_BALANCED", "OPENAI_MODEL_QUALITY"):
            app.config.pop(key, None)

        task_profile = workflow_profile("task_suggestion")
        chat_profile = workflow_profile("chat")
        quality_profile = workflow_profile("quality_analysis")

    assert task_profile.model == "test-model"
    assert chat_profile.model == "test-model"
    assert quality_profile.model == "test-model"


def test_ai_audit_stores_usage_metrics_without_content(app, monkeypatch):
    """Verify audit events store usage metadata but no prompts or answers."""
    monkeypatch.setenv("AI_PRICE_TEST_MODEL_INPUT_PER_1M", "1")
    monkeypatch.setenv("AI_PRICE_TEST_MODEL_OUTPUT_PER_1M", "2")

    with app.app_context():
        cost = estimate_cost_usd("test-model", 1000, 500)
        event_id = create_ai_audit_event(
            None,
            "assistant",
            {
                "status": "openai_used",
                "provider": "openai",
                "model": "test-model",
                "model_tier": "balanced",
                "temperature": 0.2,
                "latency_ms": 123,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cached_tokens": 0,
                "total_tokens": 1500,
                "estimated_cost_usd": cost,
            },
        )
        event = db.session.get(AIAuditEvent, event_id)
        assert event.model == "test-model"
        assert event.model_tier == "balanced"
        assert event.temperature == 0.2
        assert event.latency_ms == 123
        assert event.input_tokens == 1000
        assert event.output_tokens == 500
        assert event.estimated_cost_usd == 0.002
        assert not hasattr(event, "prompt")
        assert not hasattr(event, "response")


def test_ai_feedback_validates_rating_and_required_text(
    client,
    make_user,
    auth_headers,
):
    """Verify AI feedback validation and persistence response shape."""
    user = make_user(username="ai_feedback_user")
    headers = auth_headers(user["username"])

    invalid_rating = client.post(
        "/api/v1/ai/feedback",
        headers=headers,
        json={"prompt": "p", "response": "r", "rating": "ok"},
    )
    missing_text = client.post(
        "/api/v1/ai/feedback",
        headers=headers,
        json={"rating": "helpful", "prompt": "", "response": "r"},
    )
    valid_response = client.post(
        "/api/v1/ai/feedback",
        headers=headers,
        json={
            "prompt": "Was bedeutet E104?",
            "response": "Sensor pruefen",
            "rating": "helpful",
            "comment": "Passt",
        },
    )

    assert invalid_rating.status_code == 400
    assert missing_text.status_code == 400
    assert valid_response.status_code == 201
    assert valid_response.get_json()["rating"] == "helpful"


def test_ai_feedback_stores_source_and_chunk_metadata(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify feedback stores source and chunk links without mutating knowledge."""
    user = make_user(username="ai_feedback_sources_user")
    with app.app_context():
        event_id = create_ai_audit_event(
            user=type("UserStub", (), {"id": user["id"]})(),
            workflow="assistant",
            diagnostics={"status": "local_answer"},
            source_count=1,
        )
        db.session.commit()

    response = client.post(
        "/api/v1/ai/feedback",
        headers=auth_headers(user["username"]),
        json={
            "prompt": "Wie behebe ich E104?",
            "response": "Sensor pruefen.",
            "rating": "not_helpful",
            "audit_event_id": event_id,
            "sources": [
                {
                    "type": "knowledge",
                    "id": 7,
                    "chunk_id": 13,
                    "title": "Sensor Manual",
                    "module": "knowledge",
                    "score": 42,
                }
            ],
        },
    )
    payload = response.get_json()

    with app.app_context():
        feedback_entry = db.session.get(AIFeedback, payload["id"])
        stored_source = feedback_entry.sources()[0]
        stored_audit_event_id = feedback_entry.audit_event_id

    assert response.status_code == 201
    assert payload["source_count"] == 1
    assert payload["review_status"] == "open"
    assert stored_source["id"] == 7
    assert stored_source["chunk_id"] == 13
    assert stored_audit_event_id == event_id


def test_ai_status_is_admin_only_and_redacted(app, client, make_user, auth_headers):
    """Verify AI status requires admin access and never exposes API keys."""
    admin = make_user(
        username="ai_status_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(username="ai_status_user")
    with app.app_context():
        from app.ai import status as ai_status_module

        app.config["AI_PROVIDER"] = "mock"
        app.config["OPENAI_API_KEY"] = ""
        ai_status_module.LAST_OPENAI_ERROR = None

    forbidden_response = client.get(
        "/api/v1/ai/status",
        headers=auth_headers(user["username"]),
    )
    admin_response = client.get(
        "/api/v1/ai/status",
        headers=auth_headers(admin["username"]),
    )

    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 200
    assert "api_key" not in str(admin_response.get_json()).lower().replace(
        "api_key_configured",
        "",
    )
    payload = admin_response.get_json()
    assert payload["api_key_configured"] is False
    assert payload["provider_status"]["provider"] == "mock"
    assert payload["provider_status"]["configuration_action"] == "none"
    assert "Provider" in payload["provider_status"]["recommended_action"]
    assert any(
        item["provider"] == "openai_compatible" and item["status"] == "supported"
        for item in payload["provider_catalog"]
    )
    assert any(
        item["provider"] == "gemini"
        and item["status"] == "planned"
        and item["effective_fallback"] == "mock"
        for item in payload["provider_catalog"]
    )
    assert payload["embedding_provider_status"]["provider"] == "hashing"
    assert payload["embedding_provider_status"]["configuration_action"] == "none"
    assert "Embedding" in payload["embedding_provider_status"]["recommended_action"]
    assert any(
        item["provider"] == "hashing" and item["status"] == "supported"
        for item in payload["embedding_provider_catalog"]
    )
    assert any(
        item["provider"] == "openai_compatible"
        and item["requires_base_url"] is True
        and item["effective_fallback"] == "hashing"
        for item in payload["embedding_provider_catalog"]
    )
    assert payload["readiness"]["ready"] is True
    assert payload["readiness"]["degraded_components"] == []
    assert payload["readiness"]["actions"] == []
    assert payload["readiness"]["next_action"] is None


def test_ai_status_reports_effective_provider_for_unsupported_provider(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify admin AI status shows safe fallback for unsupported providers."""
    admin = make_user(
        username="ai_status_unsupported_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    with app.app_context():
        app.config["AI_PROVIDER"] = "gemini"
        app.config["OPENAI_API_KEY"] = "test-key"

    response = client.get(
        "/api/v1/ai/status",
        headers=auth_headers(admin["username"]),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["provider"] == "gemini"
    assert payload["provider_status"]["provider"] == "gemini"
    assert payload["provider_status"]["reason"] == "unsupported_provider"
    assert payload["provider_status"]["effective_provider"] == "mock"
    assert payload["provider_status"]["configuration_action"] == "select_supported_provider"
    assert "AI_PROVIDER" in payload["provider_status"]["recommended_action"]
    gemini_entry = next(
        item for item in payload["provider_catalog"] if item["provider"] == "gemini"
    )
    assert gemini_entry["status"] == "planned"
    assert gemini_entry["mode"] == "unsupported"
    assert payload["readiness"]["ready"] is False
    assert "provider" in payload["readiness"]["degraded_components"]
    assert payload["readiness"]["next_action"]["component"] == "provider"
    assert (
        payload["readiness"]["next_action"]["configuration_action"] == "select_supported_provider"
    )
    assert "AI_PROVIDER" in payload["readiness"]["next_action"]["recommended_action"]


def test_daily_briefing_respects_permissions_and_uses_local_fallback(
    client,
    make_user,
    make_task,
    make_error_entry,
    auth_headers,
):
    """Verify daily briefing returns only permitted local sections."""
    user = make_user(
        username="briefing_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    make_task(
        "Ueberfaelliger Task",
        creator_username=user["username"],
        department_name="Produktion",
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
    )
    make_error_entry(
        "Anlage Briefing",
        "E555",
        "Neuer Fehler",
        department_name="Produktion",
    )

    response = client.get(
        "/api/v1/ai/daily-briefing",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    section_types = {section["type"] for section in payload["sections"]}
    assert response.status_code == 200
    assert payload["diagnostics"]["status"] == "local_answer"
    assert "tasks" in section_types
    assert "errors" in section_types
    assert "documents" not in section_types


def test_daily_briefing_includes_recurring_issue_trends(
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify daily briefing surfaces recurring visible error trends."""
    user = make_user(
        username="briefing_recurring_issue_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Anlage Trend",
        "TR104",
        "Sensor Signal fehlt",
        department_name="Instandhaltung",
        description="Sensor Signal fehlt sporadisch.",
        solution="Sensor reinigen",
    )
    make_error_entry(
        "Anlage Trend",
        "TR104",
        "Sensor erkennt Produkt nicht",
        department_name="Instandhaltung",
        description="Sensor meldet kein Signal.",
        solution="Sensor reinigen",
    )

    response = client.get(
        "/api/v1/ai/daily-briefing",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    recurring_section = next(
        section for section in payload["sections"] if section["type"] == "recurring_issues"
    )
    assert response.status_code == 200
    assert recurring_section["count"] == 1
    assert recurring_section["items"][0]["occurrence_count"] == 2
    assert "Anlage Trend" in recurring_section["items"][0]["title"]


def test_daily_briefing_includes_rag_knowledge_section_after_reindex(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify daily briefing can include visible indexed RAG context."""
    admin = make_user(
        username="briefing_rag_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="briefing_rag_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_task(
        "Kritische Wartung Maschine RAG",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Maschine RAG braucht Wartung wegen Stoerung.",
    )
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    response = client.get(
        "/api/v1/ai/daily-briefing",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    section_types = {section["type"] for section in payload["sections"]}
    assert response.status_code == 200
    assert "knowledge" in section_types
    assert payload["diagnostics"]["rag_source_count"] >= 1


def test_daily_briefing_returns_no_sections_without_permissions(
    client,
    make_user,
    make_task,
    make_error_entry,
    set_dashboard_permission,
    auth_headers,
):
    """Verify daily briefing does not expose sections without dashboard rights."""
    user = make_user(
        username="briefing_no_rights_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    make_task(
        "Verdeckter Briefing Task",
        creator_username=user["username"],
        department_name="Produktion",
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
    )
    make_error_entry(
        "Anlage Briefing Sperre",
        "E556",
        "Verdeckter Fehler",
        department_name="Produktion",
    )
    set_dashboard_permission(user["username"], "tasks", can_view=False)
    set_dashboard_permission(user["username"], "errors", can_view=False)

    response = client.get(
        "/api/v1/ai/daily-briefing",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["sections"] == []
    assert payload["summary"] == "Heute sind keine kritischen Hinweise sichtbar."


def test_admin_can_list_knowledge_gaps(app, client, make_user, auth_headers):
    """Verify master admins can inspect tracked knowledge gaps."""
    admin = make_user(
        username="knowledge_gap_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    with app.app_context():
        gap = KnowledgeGap(
            question="Wie behebe ich Fehler X?",
            question_hash="abc",
            context_text="Keine Quellen",
            machine="Anlage X",
            department="Instandhaltung",
            status="open",
        )
        db.session.add(gap)
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/knowledge-gaps",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["open_count"] == 1
    assert payload["items"][0]["question"] == "Wie behebe ich Fehler X?"


def test_admin_knowledge_gaps_include_detection_summary(
    app,
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify knowledge-gap admin data includes actionable coverage detection."""
    admin = make_user(
        username="knowledge_gap_detection_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    make_error_entry(
        "Presse 42",
        "P42-HYD",
        "Hydraulikdruck faellt ab",
        description="Presse 42 verliert Hydraulikdruck.",
    )
    uncovered_error_id = make_error_entry(
        "Mixer 7",
        "M7-TEMP",
        "Temperatur zu hoch",
        description="Mixer 7 ueberhitzt wiederholt.",
    )
    with app.app_context():
        uncovered_error = db.session.get(ErrorEntry, uncovered_error_id)
        uncovered_error.severity = "critical"
        uncovered_error.repeat_count = 4
        uncovered_error.downtime_minutes = 45
        uncovered_machine = Machine(
            name="Kritische Presse 77",
            produced_item="Hydraulikteil",
            required_employees=2,
            criticality="critical",
            status="offline",
        )
        db.session.add_all(
            [
                uncovered_machine,
                KnowledgeGap(
                    question="Wie behebe ich Druckverlust an Presse 42?",
                    question_hash="gap-detect-1",
                    context_text="Keine Quellen",
                    machine="Presse 42",
                    department="Instandhaltung",
                    status="open",
                    occurrence_count=3,
                ),
                KnowledgeGap(
                    question="Welche Dichtung braucht Presse 42?",
                    question_hash="gap-detect-2",
                    context_text="Keine Quellen",
                    machine="Presse 42",
                    department="Instandhaltung",
                    status="open",
                    occurrence_count=1,
                ),
                KnowledgeDocument(
                    source_type="machine_manual",
                    title="Presse 99 Handbuch",
                    original_filename="presse-99.pdf",
                    department="Instandhaltung",
                    status="indexed",
                    is_public=True,
                ),
            ]
        )
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/knowledge-gaps?limit=10",
        headers=auth_headers(admin["username"]),
    )

    payload = response.get_json()["data"]
    detection = payload["detection"]
    machine_gap = detection["machine_gaps"][0]
    error_gap = detection["error_gaps"][0]
    action = detection["knowledge_gap_actions"][0]
    assert response.status_code == 200
    assert detection["summary"]["open_gap_count"] == 2
    assert detection["summary"]["recurring_gap_count"] == 1
    assert detection["summary"]["error_gap_count"] == 1
    assert detection["summary"]["uncovered_error_gap_count"] == 1
    assert detection["summary"]["critical_uncovered_error_gap_count"] == 1
    assert detection["summary"]["uncovered_machine_gap_count"] == 1
    assert detection["summary"]["critical_uncovered_machine_gap_count"] == 1
    assert machine_gap["machine"] == "Presse 42"
    assert machine_gap["coverage"] == "missing"
    assert machine_gap["document_count"] == 0
    assert machine_gap["related_error_count"] == 1
    assert error_gap["error_code"] == "P42-HYD"
    assert error_gap["machine"] == "Presse 42"
    assert error_gap["coverage"] == "missing"
    assert error_gap["open_gap_count"] == 2
    assert action["type"] == "missing_machine_documentation"
    assert action["priority"] == "high"
    assert action["target_type"] == "machine"
    assert action["machine"] == "Presse 42"
    assert action["next_steps"]
    assert "Fehlerhistorie" in " ".join(action["next_steps"])
    assert action["success_criteria"]
    assert any(
        item["type"] == "missing_error_documentation"
        and item["target"] == "P42-HYD"
        and item["target_type"] == "error_entry"
        and item["error_id"]
        and item["title"] == "Hydraulikdruck faellt ab"
        and item["next_steps"]
        for item in detection["knowledge_gap_actions"]
    )
    uncovered_gap = detection["uncovered_error_gaps"][0]
    assert uncovered_gap["error_code"] == "M7-TEMP"
    assert uncovered_gap["priority"] == "high"
    assert "kein passendes Fehler-Knowledge-Dokument" in uncovered_gap["reason"]
    uncovered_machine_gap = detection["uncovered_machine_gaps"][0]
    assert uncovered_machine_gap["machine"] == "Kritische Presse 77"
    assert uncovered_machine_gap["priority"] == "high"
    assert "maschinenspezifische Knowledge-Quelle" in uncovered_machine_gap["reason"]
    assert any(
        item["type"] == "missing_high_impact_error_documentation"
        and item["target"] == "M7-TEMP"
        and item["target_id"] == uncovered_error_id
        and "High-Impact-Fehler" in item["next_steps"][0]
        and item["success_criteria"]
        for item in detection["knowledge_gap_actions"]
    )
    assert any(
        item["type"] == "missing_high_impact_machine_documentation"
        and item["target"] == "Kritische Presse 77"
        and item["target_type"] == "machine"
        and item["next_steps"]
        and item["success_criteria"]
        for item in detection["knowledge_gap_actions"]
    )


def test_admin_knowledge_gap_detection_respects_error_specific_documents(
    app,
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify high-impact errors with specific knowledge docs are not flagged."""
    admin = make_user(
        username="knowledge_gap_error_coverage_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    error_id = make_error_entry(
        "Ofen 3",
        "O3-HEAT",
        "Temperaturregelung instabil",
        description="Ofen 3 faellt wegen instabiler Regelung aus.",
    )
    with app.app_context():
        error_entry = db.session.get(ErrorEntry, error_id)
        error_entry.severity = "high"
        error_entry.repeat_count = 5
        covered_machine = Machine(
            name="Ofen 3",
            produced_item="Waermebehandlung",
            required_employees=1,
            criticality="high",
            status="running",
        )
        db.session.add(covered_machine)
        db.session.flush()
        db.session.add(
            KnowledgeDocument(
                source_type="error_catalog",
                source_id=error_id,
                title="O3-HEAT Fehlerleitfaden",
                original_filename="o3-heat.md",
                department="Produktion",
                status="indexed",
                is_public=True,
            )
        )
        db.session.add(
            KnowledgeDocument(
                source_type="machine_manual",
                source_id=covered_machine.id,
                title="Ofen 3 Maschinenhandbuch",
                original_filename="ofen-3.pdf",
                department="Produktion",
                status="indexed",
                is_public=True,
            )
        )
        db.session.commit()

    response = client.get(
        "/api/v1/admin/ai/knowledge-gaps?limit=10",
        headers=auth_headers(admin["username"]),
    )

    detection = response.get_json()["data"]["detection"]
    assert response.status_code == 200
    assert detection["summary"]["uncovered_error_gap_count"] == 0
    assert detection["summary"]["uncovered_machine_gap_count"] == 0
    assert detection["uncovered_error_gaps"] == []
    assert detection["uncovered_machine_gaps"] == []


def test_document_path_rejects_storage_escape(app):
    """Verify document path resolution blocks traversal outside document storage."""
    with app.app_context():
        document = GeneratedDocument(
            task_id=1,
            document_type="maintenance_report",
            title="Bad path",
            relative_path="../outside.html",
            department="Produktion",
            machine="",
            created_by=1,
        )

        with pytest.raises(ValueError, match="escapes document storage"):
            document_path(document)


def test_generated_document_download_uses_temp_storage(
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify generated documents are listed and downloaded from test storage."""
    user = make_user(
        username="document_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Dokument Task",
        creator_username=user["username"],
        department_name="Instandhaltung",
    )
    document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    list_response = client.get("/api/v1/documents", headers=headers)
    download_response = client.get(
        f"/api/v1/documents/{document_id}/download",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.get_json()[0]["id"] == document_id
    assert download_response.status_code == 200
    assert b"report" in download_response.data


def test_document_review_only_allows_visible_documents(
    app,
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify users can only review documents visible to their department."""
    user = make_user(
        username="document_review_visible",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Review sichtbar",
        creator_username=user["username"],
        department_name="Instandhaltung",
    )
    visible_document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Instandhaltung",
        machine="Anlage Review",
    )
    hidden_document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        relative_path="2026/05/task_hidden/maintenance_report.html",
        department="Produktion",
        machine="Anlage Review",
    )
    _write_report(
        app,
        visible_document_id,
        {
            "Maschine": "Anlage Review",
            "Ursache": "Sensor verschmutzt",
            "Durchgefuehrte Massnahme": "Sensor gereinigt",
            "Ergebnis": "Anlage laeuft stabil",
            "Notizen": "Nachkontrolle eingeplant",
        },
    )
    headers = auth_headers(user["username"])

    visible_response = client.post(
        f"/api/v1/documents/{visible_document_id}/review",
        headers=headers,
    )
    hidden_response = client.post(
        f"/api/v1/documents/{hidden_document_id}/review",
        headers=headers,
    )

    assert visible_response.status_code == 200
    assert hidden_response.status_code == 404


def test_document_review_missing_file_returns_404(
    app,
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify document review reports missing files explicitly."""
    user = make_user(
        username="document_review_missing",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Review Datei fehlt",
        creator_username=user["username"],
        department_name="Instandhaltung",
    )
    document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Instandhaltung",
    )
    _delete_document_file(app, document_id)

    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        headers=auth_headers(user["username"]),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "document_file_not_found"
    assert response.get_json()["message"] == "Document file not found"


def test_document_review_local_fallback_finds_missing_required_fields(
    app,
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify local review detects incomplete maintenance report fields."""
    user = make_user(
        username="document_review_incomplete",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Review unvollstaendig",
        creator_username=user["username"],
        department_name="Instandhaltung",
    )
    document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Instandhaltung",
    )
    _write_report(
        app,
        document_id,
        {
            "Maschine": "-",
            "Ursache": "",
            "Durchgefuehrte Massnahme": "-",
            "Ergebnis": "",
            "Notizen": "-",
        },
    )

    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    fields = {finding["field"] for finding in payload["findings"]}
    assert response.status_code == 200
    assert payload["diagnostics"]["status"] == "local_answer"
    assert payload["status"] == "incomplete"
    assert fields == {
        "Maschine",
        "Ursache",
        "Durchgefuehrte Massnahme",
        "Ergebnis",
        "Notizen",
    }


def test_document_review_scores_complete_report_higher(
    app,
    client,
    make_user,
    make_task,
    make_document,
    auth_headers,
):
    """Verify complete reports receive better local review scores."""
    user = make_user(
        username="document_review_score",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    task_id = make_task(
        "Review Score",
        creator_username=user["username"],
        department_name="Instandhaltung",
    )
    incomplete_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        relative_path="2026/05/task_score_incomplete/maintenance_report.html",
        department="Instandhaltung",
    )
    complete_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        relative_path="2026/05/task_score_complete/maintenance_report.html",
        department="Instandhaltung",
    )
    _write_report(
        app,
        incomplete_id,
        {
            "Maschine": "-",
            "Ursache": "-",
            "Durchgefuehrte Massnahme": "-",
            "Ergebnis": "-",
            "Notizen": "-",
        },
    )
    _write_report(
        app,
        complete_id,
        {
            "Maschine": "Anlage 12",
            "Ursache": "Druckschwankung in der Versorgung",
            "Durchgefuehrte Massnahme": "Dichtung ersetzt und Druck geprueft",
            "Ergebnis": "Anlage arbeitet wieder im Sollbereich",
            "Notizen": "Ersatzdichtung nachbestellen",
        },
    )
    headers = auth_headers(user["username"])

    incomplete_response = client.post(
        f"/api/v1/documents/{incomplete_id}/review",
        headers=headers,
    )
    complete_response = client.post(
        f"/api/v1/documents/{complete_id}/review",
        headers=headers,
    )

    assert incomplete_response.status_code == 200
    assert complete_response.status_code == 200
    assert (
        complete_response.get_json()["quality_score"]
        > incomplete_response.get_json()["quality_score"]
    )
    assert complete_response.get_json()["status"] == "good"


def test_uploaded_document_check_validates_and_reviews_file(
    client,
    make_user,
    auth_headers,
):
    """Verify uploaded document checking handles missing, invalid and valid files."""
    user = make_user(
        username="document_upload_check",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    missing_response = client.post("/api/v1/documents/check", headers=headers)
    invalid_response = client.post(
        "/api/v1/documents/check",
        headers=headers,
        data={"file": (BytesIO(b"binary"), "report.pdf")},
        content_type="multipart/form-data",
    )
    valid_response = client.post(
        "/api/v1/documents/check",
        headers=headers,
        data={
            "file": (
                BytesIO(
                    b"Maschine: Anlage 7\n"
                    b"Ursache: Sensor verschmutzt\n"
                    b"Durchgefuehrte Massnahme: Sensor gereinigt\n"
                    b"Ergebnis: Anlage laeuft\n"
                    b"Notizen: Nachkontrolle geplant\n"
                ),
                "report.txt",
            ),
        },
        content_type="multipart/form-data",
    )

    payload = valid_response.get_json()
    assert missing_response.status_code == 400
    assert invalid_response.status_code == 400
    assert valid_response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["diagnostics"]["status"] == "local_answer"
    assert payload["data"]["status"] == "good"


def test_complete_task_can_generate_maintenance_report(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify completing a task can generate document metadata and a temp file."""
    user = make_user(username="report_user")
    task_id = make_task("Bericht Task", creator_username=user["username"])

    response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=auth_headers(user["username"]),
        json={"generate_report": True, "machine": "Anlage 7", "result": "OK"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "done"
    assert payload["generated_document"]["machine"] == "Anlage 7"


def test_search_returns_only_dashboards_visible_to_user(
    client,
    make_user,
    make_task,
    make_error_entry,
    make_document,
    auth_headers,
):
    """Verify knowledge search respects dashboard permissions and department filters."""
    user = make_user(
        username="search_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    task_id = make_task(
        "Anlage Sensor pruefen",
        creator_username=user["username"],
        department_name="Produktion",
    )
    make_error_entry(
        "Anlage Sensor",
        "E111",
        "Sensorfehler",
        department_name="Produktion",
    )
    make_document(task_id=task_id, created_by=user["id"], department="Produktion")

    response = client.get(
        "/api/v1/search?q=Anlage",
        headers=auth_headers(user["username"]),
    )

    result_types = {result["type"] for result in response.get_json()["results"]}
    visible_results = response.get_json()["results"]
    task_result = next(result for result in visible_results if result["type"] == "task")
    error_result = next(result for result in visible_results if result["type"] == "error")
    assert response.status_code == 200
    assert "task" in result_types
    assert "error" in result_types
    assert "document" not in result_types
    assert task_result["entity_id"] == task_id
    assert task_result["ui_url"].startswith("/tasks?search=")
    assert task_result["url"] == f"/api/tasks/{task_id}"
    assert error_result["ui_url"].startswith("/errors?search=")
    assert "status" in error_result


def test_search_results_include_ui_links_for_core_entities(
    client,
    make_user,
    make_task,
    make_error_entry,
    make_document,
    auth_headers,
):
    """Verify search results expose UI deeplinks without removing API URLs."""
    user = make_user(
        username="search_admin_user",
        role=Role.MASTER_ADMIN,
        department_name="Produktion",
    )
    task_id = make_task(
        "Anlage Hydraulik pruefen",
        creator_username=user["username"],
        department_name="Produktion",
    )
    error_id = make_error_entry(
        "Anlage Hydraulik",
        "HYD-42",
        "Hydraulikdruck faellt",
        department_name="Produktion",
    )
    document_id = make_document(
        task_id=task_id,
        created_by=user["id"],
        department="Produktion",
        machine="Anlage Hydraulik",
    )

    response = client.get(
        "/api/v1/search?q=Anlage",
        headers=auth_headers(user["username"]),
    )

    results_by_type = {result["type"]: result for result in response.get_json()["results"]}
    assert response.status_code == 200
    assert results_by_type["task"]["entity_id"] == task_id
    assert results_by_type["task"]["ui_url"].startswith("/tasks?search=")
    assert results_by_type["task"]["url"] == f"/api/tasks/{task_id}"
    assert results_by_type["error"]["entity_id"] == error_id
    assert results_by_type["error"]["ui_url"].startswith("/errors?search=")
    assert results_by_type["error"]["url"] == f"/api/errors/{error_id}"
    assert results_by_type["document"]["entity_id"] == document_id
    assert results_by_type["document"]["ui_url"].startswith("/documents?search=")
    assert results_by_type["document"]["url"].startswith("/api/v1/documents/")


def test_search_requires_query(client, make_user, auth_headers):
    """Verify search rejects missing query text."""
    user = make_user(username="search_empty_user")

    response = client.get("/api/v1/search?q=   ", headers=auth_headers(user["username"]))

    assert response.status_code == 400


def _write_report(app, document_id, rows):
    """Write a generated report table for a test document."""
    with app.app_context():
        document = db.session.get(GeneratedDocument, document_id)
        table_rows = "\n".join(
            f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows.items()
        )
        document_path(document).write_text(
            f"<html><body><table>{table_rows}</table></body></html>",
            encoding="utf-8",
        )


def _delete_document_file(app, document_id):
    """Delete the stored file for a test document."""
    with app.app_context():
        document = db.session.get(GeneratedDocument, document_id)
        path = document_path(document)
        if path.exists():
            path.unlink()
