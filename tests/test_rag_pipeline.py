"""Tests for the retrieval pipeline behind search_knowledge."""

from types import SimpleNamespace

import pytest

from app.services.query_classifier_service import (
    QUERY_TYPE_HYBRID,
    QueryClassificationResult,
)
from app.services.rag_service import build_rag_context


def test_build_rag_context_runs_pipeline_steps(monkeypatch):
    """Verify context assembly preserves the existing RAG payload shape."""
    _patch_workflow_boundaries(monkeypatch)

    payload = build_rag_context(
        "Welche Stoerungen sind dringend?",
        SimpleNamespace(id=1, role="master_admin"),
        requested_scopes={"errors"},
    )

    assert payload["context"] == "Structured context\n\nKnowledge context"
    assert payload["rag"]["pipeline"] == [
        "question",
        "intent_classification",
        "retrieval",
        "context_assembly",
    ]
    assert payload["rag"]["query_classification"]["query_type"] == QUERY_TYPE_HYBRID
    assert payload["rag"]["source_count"] == 2
    assert payload["rag"]["knowledge_source_count"] == 1
    assert payload["rag"]["pipeline_trace"]["completed_steps"] == payload["rag"]["pipeline"]


def test_question_step_rejects_empty_message():
    """Verify the workflow rejects empty questions before retrieval runs."""
    from app.services.rag_service import question_step

    with pytest.raises(ValueError, match="non-empty"):
        question_step({"message": "   ", "trace": []})


def test_chat_route_runs_hybrid_retrieval_through_agent(app, client, make_user, auth_headers):
    """Verify knowledge questions reach the retrieval pipeline via the agent."""
    from app.models import Role

    user = make_user(
        username="langgraph_live_chat_user",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(user["username"]),
        json={"message": "Wie behebe ich laut Wartungswissen einen Hydraulikdruckverlust?"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["type"] == "agent"
    assert [entry["tool"] for entry in payload["tool_trace"]] == ["search_knowledge"]
    assert "retrieval" in payload["rag"]["pipeline_trace"]["completed_steps"]
    assert payload["rag"]["agent"]["completed_nodes"][:3] == ["guard", "agent", "tools"]
    assert payload["diagnostics"]["query_understanding"]["query_type"]
    assert payload["diagnostics"]["empty_retrieval"] is True
    assert payload["answer_category"] == "rag"
    assert "Keine belastbare Quelle gefunden" in payload["answer"]


def _patch_workflow_boundaries(monkeypatch):
    """Patch expensive workflow boundaries with deterministic test doubles."""
    from app.services import rag_service as workflow_module

    monkeypatch.setattr(workflow_module, "is_rag_enabled", lambda: True)
    monkeypatch.setattr(
        workflow_module,
        "classify_ai_query",
        lambda message: QueryClassificationResult(
            query_type=QUERY_TYPE_HYBRID,
            extracted_keywords=["stoerungen"],
            suggested_sources=["errors", "knowledge"],
        ),
    )
    monkeypatch.setattr(workflow_module, "retrieve_context", _fake_retrieve_context)


def _fake_retrieve_context(
    message,
    user,
    requested_scopes=None,
    conversation_context=None,
    query_classification=None,
):
    """Return a deterministic retrieval payload for workflow tests."""
    assert message == "Welche Stoerungen sind dringend?"
    assert query_classification.query_type == QUERY_TYPE_HYBRID
    return {
        "context": "Structured context\n\nKnowledge context",
        "sources": [
            {
                "type": "error",
                "id": 7,
                "title": "Kritische Stoerung",
                "score": 88,
            },
            {
                "type": "knowledge",
                "id": 4,
                "title": "Stoerungsanleitung",
                "score": 91,
                "quality_status": "admin_approved",
            },
        ],
        "data": {"errors": [{"id": 7}], "knowledge": [{"id": 4}]},
        "requested_scopes": requested_scopes or {"errors", "knowledge"},
        "allowed_scopes": {"errors", "knowledge"},
        "query_understanding": {
            "query_type": "error_analysis",
            "retrieval_strategy": {"prompt_rules": ["Use maintenance evidence."]},
        },
        "safety": {"safety_relevant": False},
        "conflicts": {"has_conflicts": False},
        "context_builder": {"sections": ["structured", "knowledge"]},
        "knowledge_links": {"links": []},
        "timeline_context": {},
        "retrieval_duration_ms": 12,
        "retrieval_debug": {"keyword_fallback_used": False},
    }
