"""Tests for final post-generation AI safety checks."""

from __future__ import annotations

import json

from app.agent.service import run_agent
from app.extensions import db
from app.models import AIAuditEvent, Role, User
from app.services.ai_safety_service import enforce_post_generation_safety
from app.services.ai_service import ToolCallResponse


class UnsafeMaintenanceProvider:
    """Deterministic tool-capable provider that returns an unsafe maintenance answer."""

    name = "unsafe_test"
    supports_tool_calls = True

    def __init__(self):
        """Initialize provider metadata used by AI diagnostics."""
        self.last_call_metadata = {
            "provider": self.name,
            "workflow": "agent",
            "model": "unsafe-fixture",
            "total_tokens": 42,
        }

    def chat_with_tools(self, messages, tools, workflow="agent"):
        """Return unsafe step-by-step content without calling any tool."""
        self.last_call_metadata["workflow"] = workflow
        return ToolCallResponse(
            content=(
                "## Vorgehen\n"
                "1. Schaltschrank geoeffnet lassen.\n"
                "2. Not-Aus ueberbruecken.\n"
                "3. Unter Spannung den Sensor deaktivieren.\n"
                "4. Maschine sofort freigeben."
            ),
            tool_calls=[],
            metadata=dict(self.last_call_metadata),
        )


def _user_by_id(user_id):
    """Return a user model from a fixture-created identity."""
    return db.session.get(User, user_id)


def test_post_generation_safety_redacts_dangerous_answer(app, make_user):
    """Verify dangerous final AI answers are replaced with a safe response."""
    user = make_user(username="post_safety_user", role=Role.MASTER_ADMIN)

    with app.app_context():
        result = run_agent(
            "Wie behebe ich Druckverlust an Maschine Presse 7?",
            _user_by_id(user["id"]),
            provider=UnsafeMaintenanceProvider(),
        )

    post_safety = result["diagnostics"]["post_generation_safety"]
    assert result["answer"].startswith("## Sicherheitshinweis")
    assert "Not-Aus ueberbruecken" not in result["answer"]
    assert "Sensor deaktivieren" not in result["answer"]
    assert post_safety["action"] == "redacted"
    assert post_safety["modified"] is True
    assert result["diagnostics"]["error"] == "post_generation_safety"
    assert result["diagnostics"]["confidence_score"] == result["confidence"]["score"]


def test_post_generation_safety_keeps_normal_answer_unchanged():
    """Verify non-dangerous maintenance answers are not rewritten."""
    answer = "## Ergebnis\n- Lager pruefen und Befund dokumentieren."

    result = enforce_post_generation_safety(answer)

    assert result.answer == answer
    assert result.assessment.safety_relevant is False
    assert result.modified is False


def test_post_generation_safety_detects_umlaut_bypass_terms():
    """Verify German umlaut spelling is normalized before final safety matching."""
    answer = "## Vorgehen\n1. Not-Aus überbrücken.\n2. Maschine starten."

    result = enforce_post_generation_safety(answer)

    assert result.action == "redacted"
    assert result.assessment.safety_relevant is True


def test_post_generation_safety_audit_is_written_without_prompt_content(app, make_user):
    """Verify safety interventions are written to sanitized audit metadata."""
    user = make_user(username="post_safety_audit_user", role=Role.MASTER_ADMIN)

    with app.app_context():
        result = run_agent(
            "Wie behebe ich Druckverlust an Maschine Presse 7?",
            _user_by_id(user["id"]),
            provider=UnsafeMaintenanceProvider(),
        )
        event = db.session.get(AIAuditEvent, result["diagnostics"]["audit_event_id"])
        explainability = event.retrieval_explainability()

    audit_json = json.dumps(explainability, ensure_ascii=True)
    assert event.error_category == "post_generation_safety"
    assert explainability["post_generation_safety"]["action"] == "redacted"
    assert explainability["post_generation_safety"]["modified"] is True
    assert "Schaltschrank" not in audit_json
    assert "Sensor deaktivieren" not in audit_json
    assert "Not-Aus ueberbruecken" not in audit_json
    assert "not-aus ueberbruecken" not in audit_json


def test_post_generation_safety_fallback_without_openai_stays_functional(app, make_user):
    """Verify the mock fallback for a missing OpenAI key still completes safety checks."""
    user = make_user(username="post_safety_fallback_user", role=Role.INSTANDHALTUNG)

    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        result = run_agent("Welche Maschinen sind sichtbar?", _user_by_id(user["id"]))

    assert result["answer"]
    assert result["type"] == "agent"
    assert "post_generation_safety" not in result["diagnostics"]
