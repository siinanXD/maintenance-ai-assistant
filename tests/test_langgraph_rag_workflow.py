"""Tests for the LangGraph RAG orchestration layer."""

from types import SimpleNamespace

import pytest

from app.services.query_classifier_service import (
    QUERY_TYPE_HYBRID,
    QueryClassificationResult,
)
from app.services.rag_service import answer_with_rag, build_rag_context


class RecordingProvider:
    """AI provider test double that records answer-generation inputs."""

    name = "recording"

    def __init__(self):
        """Initialize an empty call log."""
        self.calls = []

    def answer_question(self, question, context, workflow="chat", extra_rules=None):
        """Return a deterministic answer and record the prompt inputs."""
        self.calls.append(
            {
                "question": question,
                "context": context,
                "workflow": workflow,
                "extra_rules": extra_rules,
            },
        )
        return "Provider answer with source context."


def test_build_rag_context_uses_langgraph_node_contract(monkeypatch):
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
        "structured_data_retrieval",
        "vector_retrieval",
        "context_assembly",
        "answer_generation",
        "validation",
        "trace_logging",
    ]
    assert payload["rag"]["query_classification"]["query_type"] == QUERY_TYPE_HYBRID
    assert payload["rag"]["source_count"] == 2
    assert payload["rag"]["knowledge_source_count"] == 1
    assert payload["rag"]["langgraph"]["fallback_active"] is True
    assert payload["rag"]["langgraph"]["completed_nodes"] == [
        "question",
        "intent_classification",
        "structured_data_retrieval",
        "vector_retrieval",
        "context_assembly",
        "trace_logging",
    ]


def test_answer_with_rag_runs_full_fallback_workflow(monkeypatch):
    """Verify the full workflow generates, validates, and traces an answer."""
    _patch_workflow_boundaries(monkeypatch)
    provider = RecordingProvider()

    result = answer_with_rag(
        "Welche Stoerungen sind dringend?",
        SimpleNamespace(id=1, role="master_admin"),
        requested_scopes={"errors"},
        provider=provider,
    )

    assert "Provider answer" in result["answer"]
    assert result["provider"] == "recording"
    assert result["sources"][0]["type"] == "error"
    assert result["rag"]["langgraph"]["completed_nodes"] == result["rag"]["pipeline"]
    assert result["rag"]["langgraph"]["fallback_active"] is True
    assert result["confidence"]["score"] >= 0
    assert provider.calls == [
        {
            "question": "Welche Stoerungen sind dringend?",
            "context": "Structured context\n\nKnowledge context",
            "workflow": "chat",
            "extra_rules": (
                "Use maintenance evidence. Trenne dokumentierte Ursache, "
                "Pruefung und empfohlene Massnahme klar."
            ),
        },
    ]


def test_answer_with_rag_uses_compiled_langgraph_when_available(monkeypatch):
    """Verify an available compiled graph is used before the fallback runner."""
    _patch_workflow_boundaries(monkeypatch)
    calls = []

    class FakeCompiledGraph:
        """Minimal compiled graph test double."""

        def invoke(self, state):
            """Run the fallback sequence while recording graph usage."""
            calls.append(state["message"])
            state["workflow_engine"] = "langgraph"
            return workflow_module._run_fallback_workflow(state)

    from app.services import langgraph_rag_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "_compiled_langgraph", lambda: FakeCompiledGraph())
    monkeypatch.setattr(workflow_module, "_workflow_engine_name", lambda: "langgraph")

    result = answer_with_rag(
        "Welche Stoerungen sind dringend?",
        SimpleNamespace(id=1, role="master_admin"),
        provider=RecordingProvider(),
    )

    assert calls == ["Welche Stoerungen sind dringend?"]
    assert result["rag"]["langgraph"]["engine"] == "langgraph"
    assert result["rag"]["langgraph"]["fallback_active"] is False


def test_question_node_rejects_empty_message():
    """Verify the workflow rejects empty questions before retrieval runs."""
    from app.services.langgraph_rag_workflow import question_node

    with pytest.raises(ValueError, match="non-empty"):
        question_node({"message": "   ", "trace": []})


def test_answer_with_rag_handles_empty_retrieval_without_sources(monkeypatch):
    """Verify empty retrieval still completes workflow diagnostics with zero sources."""
    from app.services import langgraph_rag_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "_compiled_langgraph", lambda: None)
    monkeypatch.setattr(workflow_module, "_workflow_engine_name", lambda: "fallback")
    monkeypatch.setattr(workflow_module, "is_rag_enabled", lambda: True)
    monkeypatch.setattr(
        workflow_module,
        "classify_ai_query",
        lambda message: QueryClassificationResult(
            query_type=QUERY_TYPE_HYBRID,
            extracted_keywords=["aufgaben"],
            suggested_sources=["tasks"],
        ),
    )
    monkeypatch.setattr(
        workflow_module,
        "retrieve_context",
        lambda *args, **kwargs: {
            "context": "",
            "sources": [],
            "data": {},
            "requested_scopes": {"tasks"},
            "allowed_scopes": {"tasks"},
            "query_understanding": {"query_type": "task_status"},
            "safety": {"safety_relevant": False},
            "conflicts": {"has_conflicts": False},
            "context_builder": {"sections": []},
            "knowledge_links": {"links": []},
            "timeline_context": {},
            "retrieval_duration_ms": 4,
            "retrieval_debug": {"keyword_fallback_used": False},
        },
    )
    provider = RecordingProvider()

    result = answer_with_rag(
        "Welche Aufgaben sind offen?",
        SimpleNamespace(id=1, role="master_admin"),
        requested_scopes={"tasks"},
        provider=provider,
    )

    assert result.get("sources") == []
    assert provider.calls
    assert result["rag"]["source_count"] == 0
    assert result["confidence"]["score"] >= 0


def test_chat_route_runs_full_langgraph_workflow(app, client, make_user, auth_headers):
    """Verify the live chat path executes generation and validation nodes."""
    from app.models import Role

    user = make_user(
        username="langgraph_live_chat_user",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )

    response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(user["username"]),
        json={"message": "Wie behebe ich Stoerung LG404 an Maschine Graph?"},
    )

    payload = response.get_json()
    langgraph = payload["rag"]["langgraph"]
    assert response.status_code == 200
    assert langgraph["completed_nodes"] == payload["rag"]["pipeline"]
    assert "answer_generation" in langgraph["completed_nodes"]
    assert "validation" in langgraph["completed_nodes"]
    assert payload["diagnostics"]["generation_skipped"] == "no_evidence"
    assert "Keine belastbare Quelle gefunden" in payload["answer"]


def test_chat_without_evidence_skips_provider_by_default(app, make_user, monkeypatch):
    """Verify unsourced questions stay local unless the explicit policy allows generation."""
    from app.ai.services import answer_chat
    from app.extensions import db
    from app.models import Role, User

    calls = []

    class RecordingChatProvider:
        """Provider double that records generation calls."""

        name = "openai"
        last_call_metadata = {"provider": "openai", "workflow": "chat", "model": "test"}

        def answer_question(self, question, context, workflow="chat", extra_rules=None):
            """Record the call and return a fixed answer."""
            calls.append({"question": question, "extra_rules": extra_rules})
            return "## Antwort\n- **Status:** generiert"

        def answer_general_question(self, question):
            """Return a fixed general answer."""
            return "## Allgemein"

    monkeypatch.setattr("app.ai.services.get_ai_provider", lambda: RecordingChatProvider())
    user = make_user(
        username="langgraph_evidence_gate_user",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    message = "Wie behebe ich Stoerung ZZ777 an Maschine Nirgendwo?"

    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_GENERATE_WITHOUT_EVIDENCE"] = False
        gated = answer_chat(message, db.session.get(User, user["id"]))
        app.config["AI_GENERATE_WITHOUT_EVIDENCE"] = True
        generated = answer_chat(message, db.session.get(User, user["id"]))

    assert gated["diagnostics"]["generation_skipped"] == "no_evidence"
    assert "Keine belastbare Quelle gefunden" in gated["answer"]
    assert len(calls) == 1
    assert "Ursache" in (calls[0]["extra_rules"] or "")
    assert generated["diagnostics"]["status"] == "openai_used"


def test_validation_node_attaches_confidence_and_safety(monkeypatch):
    """Verify validation enriches answers with confidence and safety metadata."""
    from app.services import langgraph_rag_workflow as workflow_module

    retrieval = _fake_retrieve_context(
        "Welche Stoerungen sind dringend?",
        SimpleNamespace(id=1, role="master_admin"),
        requested_scopes={"errors"},
        query_classification=QueryClassificationResult(
            query_type=QUERY_TYPE_HYBRID,
            extracted_keywords=["stoerungen"],
            suggested_sources=["errors"],
        ),
    )
    retrieval["rag"] = {
        "pipeline": workflow_module.LANGGRAPH_RAG_PIPELINE_STEPS,
        "safety": {"safety_relevant": False},
    }
    state = {
        "message": "Welche Stoerungen sind dringend?",
        "retrieval": retrieval,
        "answer": "Pruefe Ventil und Leitungen gemaess Fehlerkatalog.",
        "provider": RecordingProvider(),
        "trace": [],
    }

    payload = workflow_module.validation_node(state)

    assert payload["result"]["confidence"]["score"] >= 0
    assert "validation" in [item["node"] for item in payload["trace"]]


def _patch_workflow_boundaries(monkeypatch):
    """Patch expensive workflow boundaries with deterministic test doubles."""
    from app.services import langgraph_rag_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "_compiled_langgraph", lambda: None)
    monkeypatch.setattr(workflow_module, "_workflow_engine_name", lambda: "fallback")
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
