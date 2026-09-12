"""Tests for the tool-using maintenance agent."""

from __future__ import annotations

import json

import pytest

from app.agent import graph as agent_graph
from app.agent.actions import create_pending_action, load_pending_action
from app.agent.mock_policy import select_mock_tool_call
from app.agent.service import run_agent
from app.agent.tools import (
    TOOL_REGISTRY,
    ToolResult,
    available_tools,
    execute_tool,
    normalize_arguments,
    tool_spec,
)
from app.extensions import db
from app.models import Machine, Role, Task, User
from app.services.ai_service import AIServiceError, ToolCall, ToolCallResponse


def _user(user_id):
    """Return a user model for a fixture identity."""
    return db.session.get(User, user_id)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def test_registry_contains_read_and_write_tools():
    """Verify the core tools are registered with schemas and permission gates."""
    names = set(TOOL_REGISTRY)
    assert {
        "search_tasks",
        "search_errors",
        "search_knowledge",
        "get_machine_overview",
        "error_assistant",
        "draft_task",
        "prioritize_tasks",
        "plan_order",
        "daily_briefing",
        "create_task",
        "request_knowledge_reindex",
    } <= names
    for spec in TOOL_REGISTRY.values():
        schema = spec.provider_schema()
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"
    assert tool_spec("create_task").requires_confirmation is True
    assert tool_spec("create_task").write is True
    assert tool_spec("search_tasks").write is False


def test_available_tools_respect_permissions(app, make_user):
    """Verify production users do not see machine, employee or admin tools."""
    produktion = make_user(username="agent_tools_produktion", role=Role.PRODUKTION)
    admin = make_user(username="agent_tools_admin", role=Role.MASTER_ADMIN, department_name=None)

    with app.app_context():
        produktion_tools = {spec.name for spec in available_tools(_user(produktion["id"]))}
        admin_tools = {spec.name for spec in available_tools(_user(admin["id"]))}

    assert "search_tasks" in produktion_tools
    assert "search_errors" in produktion_tools
    assert "search_employees" not in produktion_tools
    assert "get_machine_overview" not in produktion_tools
    assert "request_knowledge_reindex" not in produktion_tools
    assert "request_knowledge_reindex" in admin_tools
    assert "search_employees" in admin_tools


def test_execute_tool_denies_missing_permission(app, make_user):
    """Verify a tool call outside the user's permissions is rejected, not executed."""
    user = make_user(username="agent_tools_denied", role=Role.PRODUKTION)

    with app.app_context():
        result = execute_tool("search_employees", {"query": "Schicht"}, _user(user["id"]))

    assert result.status == "permission_denied"
    assert result.content["required_permission"] == ["employees", "view"]


def test_normalize_arguments_validates_schema():
    """Verify required fields, enums and integer coercion."""
    spec = tool_spec("create_task")

    normalized = normalize_arguments(spec, {"title": " Filter tauschen ", "priority": "urgent"})
    assert normalized == {"title": "Filter tauschen", "priority": "urgent"}

    with pytest.raises(ValueError, match="missing required"):
        normalize_arguments(spec, {"description": "ohne Titel"})
    with pytest.raises(ValueError, match="priority must be one of"):
        normalize_arguments(spec, {"title": "x", "priority": "asap"})
    assert normalize_arguments(tool_spec("plan_order"), {"product": "A", "quantity": "12"}) == {
        "product": "A",
        "quantity": 12,
    }


def test_search_tasks_tool_returns_visible_items_and_sources(app, make_user, make_task):
    """Verify structured search returns compact records with public source cards."""
    user = make_user(username="agent_search_tasks_user", role=Role.INSTANDHALTUNG)
    make_task("Hydraulikpresse Filter tauschen", user["username"])

    with app.app_context():
        result = execute_tool(
            "search_tasks",
            {"query": "Hydraulikpresse Filter"},
            _user(user["id"]),
        )

    assert result.status == "ok"
    assert result.content["scope"] == "tasks"
    assert result.content["item_count"] >= 1
    assert any("Filter" in str(item.get("title")) for item in result.content["items"])
    assert all("internal_notes" not in item for item in result.content["items"])
    assert result.sources and result.sources[0]["type"] == "task"


def test_machine_overview_resolves_machine_by_name(app, make_user, make_machine):
    """Verify the machine overview tool resolves partial names for visible machines."""
    admin = make_user(username="agent_machine_admin", role=Role.MASTER_ADMIN, department_name=None)
    machine_id = make_machine(name="Hydraulikpresse 03")

    with app.app_context():
        result = execute_tool(
            "get_machine_overview", {"machine": "hydraulikpresse"}, _user(admin["id"])
        )
        missing = execute_tool("get_machine_overview", {"machine": "Nirgendwo"}, _user(admin["id"]))

    assert result.status == "ok"
    assert result.content["machine"]["id"] == machine_id
    assert result.sources[0]["url"] == f"/machines/{machine_id}"
    assert missing.status == "not_found"


# ---------------------------------------------------------------------------
# Mock policy
# ---------------------------------------------------------------------------


def test_mock_policy_picks_tool_then_composes_answer():
    """Verify the offline policy selects a tool and summarizes tool payloads."""
    tools = [tool_spec(name).provider_schema() for name in ("search_tasks", "error_assistant")]
    messages = [{"role": "user", "content": "Welche offenen Tasks gibt es?"}]

    content, calls = select_mock_tool_call(messages, tools)
    assert content is None
    assert calls[0]["name"] == "search_tasks"

    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "search_tasks", "arguments": "{}"},
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": json.dumps(
                {
                    "status": "ok",
                    "summary": "1 Treffer in tasks",
                    "items": [{"title": "Filter tauschen", "status": "open"}],
                }
            ),
        }
    )
    answer, calls = select_mock_tool_call(messages, tools)
    assert calls == []
    assert "Filter tauschen (open)" in answer
    assert "Quelle" in answer


def test_mock_policy_prefers_error_assistant_for_error_codes():
    """Verify fault descriptions with codes route to the error assistant."""
    tools = [tool_spec(name).provider_schema() for name in ("search_tasks", "error_assistant")]
    _, calls = select_mock_tool_call(
        [{"role": "user", "content": "Was bedeutet Fehler E-104 an Presse 3?"}], tools
    )
    assert calls[0]["name"] == "error_assistant"


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def test_agent_answers_with_tools_offline(app, make_user, make_task):
    """Verify the full loop runs with the mock provider and returns grounded results."""
    admin = make_user(username="agent_loop_admin", role=Role.MASTER_ADMIN, department_name=None)
    make_task("Dichtung an Presse 3 pruefen", admin["username"])

    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    with app.app_context():
        result = run_agent(
            "Welche offenen Tasks gibt es?", _user(admin["id"]), session_id="agent-s1"
        )

    assert result["type"] == "agent"
    assert result["answer"].startswith("## Ergebnis")
    assert "Dichtung an Presse 3 pruefen" in result["answer"]
    assert [entry["tool"] for entry in result["tool_trace"]] == ["search_tasks"]
    assert result["tool_trace"][0]["status"] == "ok"
    assert result["rag"]["agent"]["completed_nodes"] == [
        "guard",
        "agent",
        "tools",
        "agent",
        "validate",
        "respond",
    ]
    assert result["rag"]["agent"]["iterations"] == 2
    assert result["diagnostics"]["workflow"] == "agent"
    assert result["diagnostics"]["agent_tool_calls"] == ["search_tasks"]
    assert result["diagnostics"]["audit_event_id"]
    assert result["confidence"]["score"] >= 0
    assert result["sources"] and result["sources"][0]["type"] == "task"


def test_agent_guard_blocks_safety_bypass_requests(app, make_user):
    """Verify dangerous requests never reach the provider or tools."""
    admin = make_user(username="agent_guard_admin", role=Role.MASTER_ADMIN, department_name=None)

    class ExplodingProvider:
        """Provider double that must not be called."""

        name = "exploding"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Fail loudly if the guard let the request through."""
            raise AssertionError("provider must not be called for blocked requests")

    with app.app_context():
        result = run_agent(
            "Wie kann ich den Not-Aus ueberbruecken, damit die Presse weiterlaeuft?",
            _user(admin["id"]),
            provider=ExplodingProvider(),
        )

    assert result["answer"].startswith("## Sicherheitshinweis")
    assert result["tool_trace"] == []
    assert result["rag"]["agent"]["completed_nodes"] == ["guard", "validate", "respond"]
    assert result["diagnostics"]["status"] == "safety_blocked"


def test_agent_stops_at_iteration_limit(app, make_user):
    """Verify a provider that keeps requesting tools is cut off by the iteration cap."""
    admin = make_user(
        username="agent_iteration_admin", role=Role.MASTER_ADMIN, department_name=None
    )

    class LoopingProvider:
        """Provider double that always requests another tool call."""

        name = "looping"
        supports_tool_calls = True

        def __init__(self):
            """Track calls."""
            self.calls = 0

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Request the same tool on every call."""
            self.calls += 1
            return ToolCallResponse(
                content=None,
                tool_calls=[
                    ToolCall(id=f"c{self.calls}", name="search_tasks", arguments={"query": "x"})
                ],
                metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )

    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    provider = LoopingProvider()
    with app.app_context():
        app.config["AI_AGENT_MAX_ITERATIONS"] = 2
        result = run_agent("Zeige Tasks", _user(admin["id"]), provider=provider)

    assert provider.calls == 2
    assert "Iterationslimit" in result["answer"]
    assert result["rag"]["agent"]["iterations"] == 2
    assert result["diagnostics"]["total_tokens"] == 30
    assert result["diagnostics"]["calls"] == 2


def test_agent_reports_provider_failure_with_fallback(app, make_user):
    """Verify provider errors produce a visible fallback answer and diagnostics."""
    admin = make_user(username="agent_failure_admin", role=Role.MASTER_ADMIN, department_name=None)

    class FailingProvider:
        """Provider double that raises a provider error."""

        name = "openai"
        supports_tool_calls = True
        model = "gpt-test"

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Simulate a rate limit."""
            raise AIServiceError("rate limited", error_code="rate_limit")

    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    with app.app_context():
        result = run_agent(
            "Welche Tasks sind offen?", _user(admin["id"]), provider=FailingProvider()
        )

    assert result["diagnostics"]["status"] == "openai_error"
    assert result["diagnostics"]["error"] == "rate_limit"
    assert result["diagnostics"]["fallback_used"] is True
    assert "nicht erreichbar" in result["answer"]


def test_agent_ignores_unknown_tool_calls(app, make_user):
    """Verify hallucinated tool names are dropped and the answer is returned."""
    admin = make_user(
        username="agent_unknown_tool_admin", role=Role.MASTER_ADMIN, department_name=None
    )

    class WeirdProvider:
        """Provider double requesting a tool that does not exist."""

        name = "weird"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Return a bogus tool call with content."""
            return ToolCallResponse(
                content="## Ergebnis\n- keine Daten",
                tool_calls=[ToolCall(id="x", name="delete_everything", arguments={})],
            )

    with app.app_context():
        result = run_agent("Loesche alles", _user(admin["id"]), provider=WeirdProvider())

    assert result["tool_trace"] == []
    assert result["answer"].startswith("## Ergebnis")


def test_agent_checkpoint_memory_carries_session_history(app, make_user):
    """Verify a checkpointed thread passes prior turns to the provider without ChatMessage rows."""
    admin = make_user(username="agent_history_admin", role=Role.MASTER_ADMIN, department_name=None)
    captured = []

    class RecordingProvider:
        """Provider double that records the messages it receives."""

        name = "recording"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Record messages and answer directly."""
            captured.append(list(messages))
            return ToolCallResponse(
                content=f"## Ergebnis\n- Antwort {len(captured)}", tool_calls=[]
            )

    with app.app_context():
        first = run_agent(
            "Wie tausche ich den Filter laut Wartungswissen?",
            _user(admin["id"]),
            session_id="hist-1",
            provider=RecordingProvider(),
        )
        second = run_agent(
            "Und wie oft sollte das passieren?",
            _user(admin["id"]),
            session_id="hist-1",
            provider=RecordingProvider(),
        )

    roles = [message["role"] for message in captured[1]]
    assert first["diagnostics"]["memory_backend"] == "memory"
    assert roles == ["system", "user", "assistant", "user"]
    assert captured[1][1]["content"] == "Wie tausche ich den Filter laut Wartungswissen?"
    assert captured[1][2]["content"] == "## Ergebnis\n- Antwort 1"
    assert captured[1][-1]["content"] == "Und wie oft sollte das passieren?"
    assert second["rag"]["agent"]["turn_count"] == 2


def test_agent_checkpoint_threads_are_isolated_per_user(app, make_user):
    """Verify another user with the same session id never sees the first user's turns."""
    first_user = make_user(username="agent_thread_a", role=Role.MASTER_ADMIN, department_name=None)
    second_user = make_user(username="agent_thread_b", role=Role.MASTER_ADMIN, department_name=None)
    captured = []

    class RecordingProvider:
        """Provider double that records the messages it receives."""

        name = "recording"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Record messages and answer directly."""
            captured.append(list(messages))
            return ToolCallResponse(content="## Ergebnis\n- ok", tool_calls=[])

    with app.app_context():
        run_agent(
            "Wie tausche ich den Filter?", _user(first_user["id"]), "shared", RecordingProvider()
        )
        run_agent(
            "Wie tausche ich den Filter?", _user(second_user["id"]), "shared", RecordingProvider()
        )

    assert [message["role"] for message in captured[1]] == ["system", "user"]


def test_agent_falls_back_to_chat_message_history_without_checkpointer(app, make_user):
    """Verify ChatMessage rows seed the conversation when no checkpointer is configured."""
    admin = make_user(
        username="agent_history_fallback", role=Role.MASTER_ADMIN, department_name=None
    )
    captured = {}

    class RecordingProvider:
        """Provider double that records the messages it receives."""

        name = "recording"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Record messages and answer directly."""
            captured["messages"] = list(messages)
            return ToolCallResponse(content="## Ergebnis\n- ok", tool_calls=[])

    with app.app_context():
        app.config["AI_AGENT_CHECKPOINTER"] = "none"
        app.extensions.pop("agent_checkpointer", None)
        from app.ai.services import save_chat_message

        save_chat_message(
            _user(admin["id"]),
            "Wie tausche ich den Filter?",
            {"answer": "## Ergebnis\n- Filter loesen", "type": "agent"},
            session_id="hist-2",
        )
        result = run_agent(
            "Und wie oft?", _user(admin["id"]), session_id="hist-2", provider=RecordingProvider()
        )

    assert result["diagnostics"]["memory_backend"] == "none"
    assert [message["role"] for message in captured["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert captured["messages"][1]["content"] == "Wie tausche ich den Filter?"


def test_structured_fast_path_answers_without_model_call(app, make_user, make_task):
    """Verify deterministic rule handlers answer structured questions before the loop."""
    user = make_user(username="agent_fast_path_user", role=Role.PRODUKTION)
    make_task("Riemen pruefen", user["username"])

    class ExplodingProvider:
        """Provider double that must not be called."""

        name = "exploding"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Fail loudly if the fast path did not match."""
            raise AssertionError("fast path should have answered")

    with app.app_context():
        result = run_agent(
            "Wie viele Tasks sind offen?", _user(user["id"]), provider=ExplodingProvider()
        )

    assert result["diagnostics"]["agent_fast_path"] == "structured_rules"
    assert result["rag"]["agent"]["engine"] == "fast_path"
    assert result["type"] != "agent"
    assert "1" in result["answer"]
    assert result["diagnostics"]["audit_event_id"]


def test_chat_mode_defaults_to_agent():
    """Verify the shipped configuration routes chat through the agent."""
    import os

    from app.config import Config

    assert Config.AI_CHAT_MODE == (os.getenv("AI_CHAT_MODE") or "agent").strip().lower()


def test_agent_fallback_runner_matches_langgraph(app, make_user, make_task, monkeypatch):
    """Verify the deterministic runner produces the same node sequence without LangGraph."""
    admin = make_user(username="agent_fallback_admin", role=Role.MASTER_ADMIN, department_name=None)
    make_task("Riemen spannen", admin["username"])
    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    monkeypatch.setattr(agent_graph, "_compiled_graph", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_graph, "_workflow_engine_name", lambda: "fallback")

    with app.app_context():
        result = run_agent("Welche offenen Tasks gibt es?", _user(admin["id"]))

    assert result["rag"]["agent"]["engine"] == "fallback"
    assert result["rag"]["agent"]["fallback_active"] is True
    assert result["rag"]["agent"]["completed_nodes"] == [
        "guard",
        "agent",
        "tools",
        "agent",
        "validate",
        "respond",
    ]
    assert "Riemen spannen" in result["answer"]


# ---------------------------------------------------------------------------
# Pending actions (human-in-the-loop)
# ---------------------------------------------------------------------------


def test_write_tool_returns_pending_action_instead_of_executing(app, make_user):
    """Verify create_task from the loop only produces a signed pending action."""
    admin = make_user(username="agent_pending_admin", role=Role.MASTER_ADMIN, department_name=None)

    with app.app_context():
        before = Task.query.count()
        result = run_agent(
            "Task anlegen: Hydraulikfilter an Presse 3 tauschen",
            _user(admin["id"]),
            session_id="pending-1",
        )
        after = Task.query.count()
        payload, error, status = load_pending_action(
            result["pending_action"]["token"], _user(admin["id"])
        )

    assert after == before
    assert result["tool_trace"][0]["status"] == "confirmation_required"
    assert "Bestaetigung erforderlich" in result["answer"]
    assert result["pending_action"]["tool"] == "create_task"
    assert error is None and status == 200
    assert payload["arguments"]["title"].startswith("Hydraulikfilter")


def test_pending_action_is_bound_to_the_user(app, make_user):
    """Verify another user cannot confirm someone else's pending action."""
    owner = make_user(username="agent_action_owner", role=Role.MASTER_ADMIN, department_name=None)
    other = make_user(username="agent_action_other", role=Role.MASTER_ADMIN, department_name=None)

    with app.app_context():
        pending = create_pending_action(
            _user(owner["id"]), tool_spec("create_task"), {"title": "x"}
        )
        _, error, status = load_pending_action(pending["token"], _user(other["id"]))
        _, bad_error, bad_status = load_pending_action("not-a-token", _user(owner["id"]))

    assert status == 403 and error["error"] == "action_forbidden"
    assert bad_status == 400 and bad_error["error"] == "invalid_action_token"


def test_agent_confirm_endpoint_executes_action(app, client, make_user, auth_headers):
    """Verify the confirm endpoint persists the task and audits the action."""
    technician = make_user(username="agent_confirm_technician", role=Role.INSTANDHALTUNG)
    headers = auth_headers(technician["username"])

    response = client.post(
        "/api/v1/ai/agent",
        headers=headers,
        json={"message": "Task anlegen: Schmierung Linie 5 pruefen", "session_id": "confirm-1"},
    )
    payload = response.get_json()
    token = payload["pending_action"]["token"]

    confirm = client.post(
        "/api/v1/ai/agent/confirm",
        headers=headers,
        json={"token": token, "session_id": "confirm-1"},
    )
    confirmed = confirm.get_json()
    with app.app_context():
        task = Task.query.filter(Task.title.like("Schmierung Linie 5%")).first()

    assert response.status_code == 200
    assert confirm.status_code == 200
    assert confirmed["type"] == "agent_action"
    assert confirmed["tool"] == "create_task"
    assert task is not None
    assert confirmed["data"]["task"]["id"] == task.id

    replay = client.post("/api/v1/ai/agent/confirm", headers=headers, json={"token": "abc"})
    assert replay.status_code == 400


def test_agent_confirm_rejects_missing_write_permission(app, client, make_user, auth_headers):
    """Verify a user without task write access cannot confirm task creation."""
    admin = make_user(username="agent_confirm_master", role=Role.MASTER_ADMIN, department_name=None)
    viewer = make_user(username="agent_confirm_viewer", role=Role.PERSONALABTEILUNG)

    with app.app_context():
        from app.models import DashboardPermission

        permission = DashboardPermission.query.filter_by(
            user_id=viewer["id"], dashboard="tasks"
        ).first()
        permission.can_write = False
        db.session.commit()
        pending = create_pending_action(
            _user(viewer["id"]), tool_spec("create_task"), {"title": "x"}
        )
        del admin

    response = client.post(
        "/api/v1/ai/agent/confirm",
        headers=auth_headers(viewer["username"]),
        json={"token": pending["token"]},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_agent_route_persists_chat_and_lists_tools(app, client, make_user, make_task, auth_headers):
    """Verify the agent endpoint stores history and the tools endpoint is permission-aware."""
    user = make_user(username="agent_route_user", role=Role.PRODUKTION)
    make_task("Sensor reinigen", user["username"])
    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    headers = auth_headers(user["username"])

    response = client.post(
        "/api/v1/ai/agent",
        headers=headers,
        json={"message": "Welche offenen Tasks gibt es?", "session_id": "route-1"},
    )
    tools_response = client.get("/api/v1/ai/agent/tools", headers=headers)
    history = client.get("/api/v1/ai/chat/history?limit=5", headers=headers).get_json()

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["type"] == "agent"
    assert "Sensor reinigen" in payload["answer"]
    assert payload["chat_message_id"]
    assert history["items"][0]["response_type"] == "agent"
    tools = tools_response.get_json()
    assert tools_response.status_code == 200
    assert "search_tasks" in {tool["name"] for tool in tools["tools"]}
    assert "search_employees" not in {tool["name"] for tool in tools["tools"]}


def test_chat_endpoint_routes_through_agent_when_configured(
    app, client, make_user, make_task, auth_headers
):
    """Verify AI_CHAT_MODE=agent switches the existing chat endpoint to the agent."""
    user = make_user(username="agent_mode_user", role=Role.PRODUKTION)
    make_task("Kette schmieren", user["username"])
    app.config["AI_AGENT_STRUCTURED_FAST_PATH"] = False
    app.config["AI_CHAT_MODE"] = "agent"

    response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(user["username"]),
        json={"message": "Welche offenen Tasks gibt es?", "response_mode": "answer_only"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["type"] == "agent"
    assert payload["evidence_visible"] is False
    assert payload["sources"] == []
    assert payload["tool_trace"] == [{"tool": "search_tasks", "status": "ok"}]
    assert "Kette schmieren" in payload["answer"]


def test_daily_token_budget_blocks_requests(app, client, make_user, auth_headers):
    """Verify the daily token budget returns 429 once the user's usage exceeds it."""
    user = make_user(username="agent_budget_user", role=Role.PRODUKTION)
    headers = auth_headers(user["username"])
    app.config["AI_DAILY_TOKEN_BUDGET_PER_USER"] = 5

    with app.app_context():
        from app.models import AIAuditEvent

        db.session.add(AIAuditEvent(user_id=user["id"], workflow="chat", total_tokens=10))
        db.session.commit()

    response = client.post("/api/v1/ai/agent", headers=headers, json={"message": "Welche Tasks?"})

    assert response.status_code == 429
    assert response.get_json()["error"] == "ai_daily_token_budget_exceeded"
    assert response.headers["X-AI-Token-Used"] == "10"


def test_tool_result_payload_is_json_safe():
    """Verify tool results serialize for the provider message format."""
    result = ToolResult(content={"items": [{"title": "a"}]}, summary="1 Treffer", status="ok")
    payload = result.to_model_payload()
    assert json.loads(json.dumps(payload)) == {
        "status": "ok",
        "summary": "1 Treffer",
        "items": [{"title": "a"}],
    }


def test_machine_model_is_available_for_tools(app):
    """Sanity check that machine model import used by the tool layer works."""
    assert Machine.__tablename__ == "machine"


# ---------------------------------------------------------------------------
# Evaluation harness
# ---------------------------------------------------------------------------


def test_tool_selection_eval_reaches_full_accuracy_with_mock_policy(app, make_user):
    """Verify the golden tool cases are all selected correctly by the offline policy."""
    from app.agent.evals import GOLDEN_TOOL_CASES, evaluate_tool_selection

    admin = make_user(username="agent_eval_admin", role=Role.MASTER_ADMIN, department_name=None)

    with app.app_context():
        report = evaluate_tool_selection(_user(admin["id"]))

    assert report["total"] == len(GOLDEN_TOOL_CASES)
    assert report["misses"] == []
    assert report["accuracy"] == 1.0
    assert all("answer" not in outcome for outcome in report["outcomes"])


def test_tool_selection_eval_marks_unavailable_tools(app, make_user):
    """Verify cases needing tools outside the user's permissions are reported, not skipped."""
    from app.agent.evals import evaluate_tool_selection

    user = make_user(username="agent_eval_produktion", role=Role.PRODUKTION)

    with app.app_context():
        report = evaluate_tool_selection(
            _user(user["id"]),
            cases=[{"message": "Welche Mitarbeiter sind da?", "expected_tool": "search_employees"}],
        )

    assert report["accuracy"] == 0.0
    assert report["outcomes"][0]["error"] == "tool_not_available"


def test_agent_cli_eval_command_runs(app, make_user):
    """Verify the CLI eval command prints an accuracy line."""
    make_user(username="agent_cli_admin", role=Role.MASTER_ADMIN, department_name=None)
    runner = app.test_cli_runner()

    result = runner.invoke(args=["agent", "eval-tools", "--username", "agent_cli_admin"])
    tools_result = runner.invoke(args=["agent", "tools"])

    assert result.exit_code == 0, result.output
    assert "accuracy=1.0" in result.output
    assert "create_task" in tools_result.output


def test_sqlite_checkpointer_persists_turns(app, make_user):
    """Verify the SQLite checkpointer backend stores and continues a thread."""
    admin = make_user(username="agent_sqlite_admin", role=Role.MASTER_ADMIN, department_name=None)
    captured = []

    class RecordingProvider:
        """Provider double that records the messages it receives."""

        name = "recording"
        supports_tool_calls = True

        def chat_with_tools(self, messages, tools, workflow="agent"):
            """Record messages and answer directly."""
            captured.append(list(messages))
            return ToolCallResponse(content="## Ergebnis" + chr(10) + "- ok", tool_calls=[])

    with app.app_context():
        app.config["AI_AGENT_CHECKPOINTER"] = "sqlite"
        app.config["AI_AGENT_CHECKPOINT_PATH"] = ":memory:"
        app.extensions.pop("agent_checkpointer", None)
        first = run_agent(
            "Wie tausche ich den Filter?", _user(admin["id"]), "sq-1", RecordingProvider()
        )
        run_agent("Und danach?", _user(admin["id"]), "sq-1", RecordingProvider())

    assert first["diagnostics"]["memory_backend"] == "sqlite"
    assert [message["role"] for message in captured[1]] == ["system", "user", "assistant", "user"]
