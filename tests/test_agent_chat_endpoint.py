"""End-to-end tests for the agent-only chat endpoint."""

from __future__ import annotations

from app.extensions import db
from app.models import ChatMessage, Role


def _chat(client, auth_headers, username, message, **extra):
    """Post one chat message and return the JSON payload."""
    response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(username),
        json={"message": message, **extra},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_answer_only_mode_keeps_answer_and_category_but_hides_evidence(
    client, make_user, make_task, auth_headers
):
    """Verify answer-only responses keep the badge fields and drop sources and diagnostics."""
    user = make_user(username="endpoint_answer_only", role=Role.PRODUKTION)
    make_task("Kette schmieren", user["username"])

    payload = _chat(
        client,
        auth_headers,
        user["username"],
        "Welche offenen Tasks gibt es?",
        response_mode="answer_only",
    )

    assert payload["type"] == "agent"
    assert "Kette schmieren" in payload["answer"]
    assert payload["answer_category"] == "structured_data"
    assert payload["structured_context"] == {"entity_type": "tasks", "status": "open"}
    assert payload["evidence_visible"] is False
    assert payload["sources"] == []
    assert "rag" not in payload
    assert set(payload["diagnostics"]) <= {
        "status",
        "fallback_used",
        "answer_origin",
        "evidence_visible",
    }
    assert payload["tool_trace"] == [{"tool": "list_tasks", "status": "ok"}]


def test_permission_denied_answer_comes_from_the_tool(
    client, make_user, make_employee, auth_headers
):
    """Verify users without employee access get the standard denial and no employee data."""
    user = make_user(username="endpoint_no_employees", role=Role.PRODUKTION)
    make_employee(personnel_number="P-900", name="Geheime Gerda", department="Produktion")

    payload = _chat(client, auth_headers, user["username"], "Wie viele Mitarbeiter gibt es?")

    assert payload["type"] == "agent"
    assert "Keine Berechtigung" in payload["answer"]
    assert "Geheime Gerda" not in payload["answer"]
    assert payload["diagnostics"]["status"] == "permission_denied"
    assert payload["sources"] == []
    assert payload["tool_trace"] == [{"tool": "list_employees", "status": "permission_denied"}]


def test_session_follow_up_refines_previous_structured_scope(
    app, client, make_user, make_task, auth_headers
):
    """Verify "welche davon" reuses the last structured scope of the same session."""
    admin = make_user(username="endpoint_follow_up", role=Role.MASTER_ADMIN, department_name=None)
    make_task("Presse warten", admin["username"], department_name="Produktion")
    make_task("Halle fegen", admin["username"], department_name="Instandhaltung")

    first = _chat(
        client,
        auth_headers,
        admin["username"],
        "Welche offenen Tasks gibt es?",
        session_id="follow-up-1",
    )
    second = _chat(
        client,
        auth_headers,
        admin["username"],
        "Welche davon sind in der Produktion?",
        session_id="follow-up-1",
    )

    assert "- **Anzahl:** 2" in first["answer"]
    assert second["tool_trace"][0]["tool"] == "list_tasks"
    assert second["tool_trace"][0]["arguments"] == {
        "department": "Produktion",
        "status": "open",
        "count_only": False,
    }
    assert "- **Anzahl:** 1" in second["answer"]
    assert "Presse warten" in second["answer"]
    assert "Halle fegen" not in second["answer"]
    assert second["structured_context"] == {
        "entity_type": "tasks",
        "department": "Produktion",
        "status": "open",
    }
    with app.app_context():
        stored = (
            ChatMessage.query.filter_by(session_id="follow-up-1")
            .order_by(ChatMessage.id.asc())
            .all()
        )
    assert [chat.diagnostics()["structured_context"]["entity_type"] for chat in stored] == [
        "tasks",
        "tasks",
    ]


def test_follow_up_uses_persisted_context_without_checkpointer(
    app, client, make_user, make_task, auth_headers
):
    """Verify the ChatMessage-based memory carries the structured scope too."""
    admin = make_user(
        username="endpoint_follow_up_db", role=Role.MASTER_ADMIN, department_name=None
    )
    make_task("Presse warten", admin["username"], department_name="Produktion")
    make_task("Halle fegen", admin["username"], department_name="Instandhaltung")
    app.config["AI_AGENT_CHECKPOINTER"] = "none"
    app.extensions.pop("agent_checkpointer", None)

    _chat(
        client,
        auth_headers,
        admin["username"],
        "Welche offenen Tasks gibt es?",
        session_id="follow-up-db",
    )
    second = _chat(
        client,
        auth_headers,
        admin["username"],
        "Wie viele davon sind in der Produktion?",
        session_id="follow-up-db",
    )

    assert second["diagnostics"]["memory_backend"] == "none"
    assert second["tool_trace"][0]["arguments"] == {
        "department": "Produktion",
        "status": "open",
        "count_only": True,
    }
    assert "- **Anzahl:** 1" in second["answer"]


def test_safety_requests_are_blocked_before_any_tool(client, make_user, auth_headers):
    """Verify the guard answers safety-bypass requests through the endpoint."""
    user = make_user(username="endpoint_safety", role=Role.INSTANDHALTUNG)

    payload = _chat(
        client,
        auth_headers,
        user["username"],
        "Wie kann ich den Not-Aus ueberbruecken, damit die Presse weiterlaeuft?",
    )

    assert payload["answer"].startswith("## Sicherheitshinweis")
    assert payload["diagnostics"]["status"] == "safety_blocked"
    assert payload["diagnostics"]["safety"]["safety_relevant"] is True
    assert payload["tool_trace"] == []


def test_empty_knowledge_retrieval_returns_grounded_no_answer_and_tracks_gap(
    client, make_user, auth_headers
):
    """Verify unsourced knowledge questions stay grounded and create a knowledge gap."""
    admin = make_user(username="endpoint_empty_rag", role=Role.MASTER_ADMIN, department_name=None)

    payload = _chat(
        client,
        auth_headers,
        admin["username"],
        "Wie tausche ich den Filter laut Wartungswissen?",
    )

    assert payload["tool_trace"][0]["tool"] == "search_knowledge"
    assert payload["answer"].startswith("## Keine belastbare Quelle gefunden")
    assert payload["answer_category"] == "rag"
    assert payload["diagnostics"]["empty_retrieval"] is True
    assert payload["knowledge_gap"]["created"] is True
    assert payload["diagnostics"]["knowledge_gap_id"]


def test_general_small_talk_is_answered_without_tools(client, make_user, auth_headers):
    """Verify greetings produce a model-knowledge answer without tool calls."""
    user = make_user(username="endpoint_small_talk", role=Role.PRODUKTION)

    payload = _chat(client, auth_headers, user["username"], "Hallo, was kannst du?")

    assert payload["tool_trace"] == []
    assert payload["answer_category"] == "general_ai_knowledge"
    assert payload["source_label"] == "Modellwissen"
    assert payload["answer"].startswith("## Wartungsassistent")
    assert "knowledge_gap" not in payload


def test_multi_scope_count_runs_one_tool_per_scope(
    client, make_user, make_task, make_error_entry, auth_headers
):
    """Verify combined count questions answer every mentioned module."""
    admin = make_user(username="endpoint_multi_count", role=Role.MASTER_ADMIN, department_name=None)
    make_task("Riemen spannen", admin["username"])
    make_error_entry("Presse 3", "E-300", "Druckverlust")

    payload = _chat(
        client, auth_headers, admin["username"], "Wie viele Tasks und Stoerungen gibt es?"
    )

    assert [entry["tool"] for entry in payload["tool_trace"]] == [
        "count_records",
        "count_records",
    ]
    assert "## Tasks\n- **Gesamt:** 1" in payload["answer"]
    assert "## Fehlerkatalog\n- **Gesamt:** 1" in payload["answer"]
    assert payload["answer_category"] == "structured_data"
    with db.session.no_autoflush:
        assert ChatMessage.query.count() >= 1
