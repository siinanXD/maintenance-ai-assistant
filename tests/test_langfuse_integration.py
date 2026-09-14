"""Tests for optional Langfuse AI tracing integration."""

import base64
import json
import os
import sys
import types
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.ai.status import ai_diagnostics, ai_status
from app.services.ai_audit_service import ai_analytics_summary
from app.services.ai_provider_openai import OpenAIProvider
from app.services.ai_provider_readiness_service import ai_readiness_summary
from app.services.ai_routing import workflow_profile
from app.services.langfuse_eval_score_service import (
    submit_automatic_eval_scores,
    submit_user_feedback_score,
)
from app.services.langfuse_metrics_service import langfuse_metrics_summary
from app.services.langfuse_service import (
    attach_langfuse_eval_io,
    configure_langfuse_environment,
    langfuse_eval_enabled,
    langfuse_observation,
    langfuse_status,
    langfuse_trace_context,
    link_langfuse_answer_trace,
    openai_langfuse_kwargs,
    submit_langfuse_scores,
)

LANGFUSE_TEST_PUBLIC_KEY = "test-public-key"
LANGFUSE_TEST_SECRET_KEY = "test-secret-placeholder"


class FakeMessage:
    """Simple OpenAI message test double."""

    content = "Testantwort"


class FakeChoice:
    """Simple OpenAI choice test double."""

    message = FakeMessage()


class FakeCompletion:
    """Simple OpenAI completion test double."""

    choices = [FakeChoice()]
    usage = {
        "prompt_tokens": 11,
        "completion_tokens": 5,
        "total_tokens": 16,
    }


class FakeUser:
    """Minimal user object for Langfuse context tests."""

    id = 42
    role = types.SimpleNamespace(value="it")


def test_langfuse_status_is_safe_when_disabled(app):
    """Verify Langfuse defaults to an inactive, redacted status."""
    with app.app_context():
        status = langfuse_status()

    assert status["enabled"] is False
    assert status["configured"] is False
    assert status["ready"] is False
    assert "secret" not in status


def test_ai_status_exposes_redacted_langfuse_readiness(app):
    """Verify AI status includes Langfuse readiness without credentials."""
    with app.app_context():
        status = ai_status()

    assert status["langfuse"]["enabled"] is False
    assert status["langfuse"]["ready"] is False
    assert status["provider_status"]["provider"] == "mock"
    assert status["provider_status"]["ready"] is True
    assert status["embedding_provider_status"]["provider"] == "hashing"
    assert status["embedding_provider_status"]["ready"] is True
    assert status["embedding_provider_status"]["effective_provider"] == "hashing"
    assert status["ready"] is True
    assert status["readiness"]["ready"] is True
    assert status["readiness"]["degraded_components"] == []
    assert "secret" not in status["langfuse"]


def test_ai_status_reports_openai_provider_readiness(app):
    """Verify OpenAI provider readiness depends only on redacted config presence."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = ""
        missing_key_status = ai_status()
        app.config["OPENAI_API_KEY"] = "   "
        whitespace_key_status = ai_status()
        app.config["OPENAI_API_KEY"] = "test-key"
        ready_status = ai_status()

    assert missing_key_status["provider_status"]["ready"] is False
    assert missing_key_status["provider_status"]["reason"] == "api_key_missing"
    assert missing_key_status["provider_status"]["configuration_action"] == "set_openai_api_key"
    assert "OPENAI_API_KEY" in missing_key_status["provider_status"]["recommended_action"]
    assert whitespace_key_status["provider_status"]["ready"] is False
    assert whitespace_key_status["provider_status"]["reason"] == "api_key_missing"
    assert whitespace_key_status["api_key_configured"] is False
    assert ready_status["provider_status"]["ready"] is True
    assert ready_status["provider_status"]["reason"] == ""
    assert ready_status["provider_status"]["configuration_action"] == "none"


def test_ai_status_normalizes_provider_name_in_readiness_snapshot(app):
    """Verify readiness snapshots expose a stable normalized provider name."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "  OpenAI_Compatible  "
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        status = ai_status()

    assert status["provider"] == "openai_compatible"
    assert status["provider_status"]["provider"] == "openai_compatible"
    assert status["provider_status"]["ready"] is True


def test_ai_readiness_summary_reports_last_error_action():
    """Verify last AI errors become explicit admin readiness actions."""
    provider_status = {
        "ready": True,
        "configuration_action": "none",
        "recommended_action": "Provider bereit.",
    }
    embedding_status = {
        "ready": True,
        "configuration_action": "none",
        "recommended_action": "Embedding bereit.",
    }

    readiness = ai_readiness_summary(
        provider_status,
        embedding_status,
        last_error="configuration_missing",
    )

    assert readiness["ready"] is False
    assert readiness["degraded_components"] == ["last_error"]
    assert readiness["next_action"]["component"] == "last_error"
    assert readiness["next_action"]["configuration_action"] == "review_last_ai_error"
    assert "Admin-Log" in readiness["next_action"]["recommended_action"]


def test_workflow_profile_ignores_blank_model_overrides(app, monkeypatch):
    """Verify blank model overrides fall back to the configured routing defaults."""
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_BALANCED", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_GENERAL_CHAT", raising=False)
    with app.app_context():
        app.config["OPENAI_MODEL"] = "   "
        app.config["OPENAI_MODEL_BALANCED"] = "   "
        app.config["OPENAI_MODEL_GENERAL_CHAT"] = "   "
        profile = workflow_profile("general_chat", legacy_model="   ")

    assert profile.model == "gpt-4o-mini"


def test_ai_status_reports_openai_compatible_base_url_requirement(app):
    """Verify local OpenAI-compatible providers require a configured base URL."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai_compatible"
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["AI_BASE_URL"] = ""
        missing_base_url_status = ai_status()
        app.config["AI_BASE_URL"] = "   "
        whitespace_base_url_status = ai_status()
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        ready_status = ai_status()

    assert missing_base_url_status["provider_status"]["ready"] is False
    assert missing_base_url_status["provider_status"]["reason"] == "base_url_missing"
    assert missing_base_url_status["provider_status"]["base_url_configured"] is False
    assert missing_base_url_status["provider_status"]["configuration_action"] == "set_ai_base_url"
    assert "AI_BASE_URL" in missing_base_url_status["provider_status"]["recommended_action"]
    assert whitespace_base_url_status["provider_status"]["ready"] is False
    assert whitespace_base_url_status["provider_status"]["reason"] == "base_url_missing"
    assert whitespace_base_url_status["provider_status"]["base_url_configured"] is False
    assert ready_status["provider_status"]["ready"] is True
    assert ready_status["provider_status"]["base_url_configured"] is True
    assert ready_status["provider_status"]["configuration_action"] == "none"


def test_ai_status_reports_unsupported_provider_without_crashing(app):
    """Verify unsupported providers are visibly not ready until implemented."""
    with app.app_context():
        app.config["AI_PROVIDER"] = "gemini"
        app.config["OPENAI_API_KEY"] = "test-key"
        status = ai_status()

    assert status["provider_status"]["provider"] == "gemini"
    assert status["provider_status"]["ready"] is False
    assert status["provider_status"]["reason"] == "unsupported_provider"
    assert status["provider_status"]["configuration_action"] == "select_supported_provider"
    assert "AI_PROVIDER" in status["provider_status"]["recommended_action"]
    assert status["ready"] is False
    assert status["readiness"]["status"] == "degraded"
    assert status["readiness"]["degraded_components"] == ["provider"]
    assert status["readiness"]["reasons"] == ["unsupported_provider"]


def test_ai_status_reports_openai_compatible_embedding_readiness(app):
    """Verify embedding provider readiness is visible without exposing secrets."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "openai_compatible"
        app.config["OPENAI_API_KEY"] = "   "
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        missing_key_status = ai_status()
        app.config["OPENAI_API_KEY"] = "test-key"
        app.config["OPENAI_EMBEDDING_MODEL"] = "   "
        missing_model_status = ai_status()
        app.config["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        app.config["AI_BASE_URL"] = ""
        missing_base_url_status = ai_status()
        app.config["AI_BASE_URL"] = "   "
        whitespace_base_url_status = ai_status()
        app.config["AI_BASE_URL"] = "http://127.0.0.1:11434/v1"
        ready_status = ai_status()

    missing_key = missing_key_status["embedding_provider_status"]
    missing_model = missing_model_status["embedding_provider_status"]
    missing = missing_base_url_status["embedding_provider_status"]
    whitespace = whitespace_base_url_status["embedding_provider_status"]
    ready = ready_status["embedding_provider_status"]
    assert missing_key["ready"] is False
    assert missing_key["reason"] == "api_key_missing"
    assert missing_key["api_key_configured"] is False
    assert missing_key["configuration_action"] == "set_openai_api_key"
    assert "OPENAI_API_KEY" in missing_key["recommended_action"]
    assert missing_model["ready"] is False
    assert missing_model["reason"] == "embedding_model_missing"
    assert missing_model["model_configured"] is False
    assert missing_model["configuration_action"] == "set_openai_embedding_model"
    assert "OPENAI_EMBEDDING_MODEL" in missing_model["recommended_action"]
    assert missing["provider"] == "openai_compatible"
    assert missing["ready"] is False
    assert missing["reason"] == "base_url_missing"
    assert missing["effective_provider"] == "hashing"
    assert missing["base_url_configured"] is False
    assert missing["configuration_action"] == "set_ai_base_url"
    assert "AI_BASE_URL" in missing["recommended_action"]
    assert whitespace["ready"] is False
    assert whitespace["reason"] == "base_url_missing"
    assert whitespace["base_url_configured"] is False
    assert missing_base_url_status["ready"] is False
    assert missing_base_url_status["readiness"]["degraded_components"] == ["embedding_provider"]
    assert missing_base_url_status["readiness"]["reasons"] == ["embedding_base_url_missing"]
    assert missing_base_url_status["readiness"]["next_action"]["component"] == (
        "embedding_provider"
    )
    assert (
        missing_base_url_status["readiness"]["next_action"]["configuration_action"]
        == "set_ai_base_url"
    )
    assert (
        "AI_BASE_URL" in missing_base_url_status["readiness"]["next_action"]["recommended_action"]
    )
    assert ready["ready"] is True
    assert ready["effective_provider"] == "openai_compatible"
    assert ready["base_url_configured"] is True
    assert ready["configuration_action"] == "none"
    assert ready_status["ready"] is True


def test_ai_status_reports_unsupported_embedding_provider_fallback(app):
    """Verify unsupported embedding providers are visible while falling back locally."""
    with app.app_context():
        app.config["EMBEDDING_PROVIDER"] = "gemini"
        status = ai_status()

    embedding_status = status["embedding_provider_status"]
    assert embedding_status["provider"] == "gemini"
    assert embedding_status["ready"] is False
    assert embedding_status["reason"] == "unsupported_provider"
    assert embedding_status["effective_provider"] == "hashing"
    assert embedding_status["configuration_action"] == "select_supported_embedding_provider"
    assert "EMBEDDING_PROVIDER" in embedding_status["recommended_action"]
    assert status["ready"] is False
    assert status["readiness"]["degraded_components"] == ["embedding_provider"]
    assert status["readiness"]["reasons"] == ["embedding_unsupported_provider"]


def test_ai_diagnostics_carries_langfuse_trace_metadata(app):
    """Verify Langfuse trace identifiers flow into AI diagnostics."""
    with app.app_context():
        diagnostics = ai_diagnostics(
            "openai_used",
            metadata={
                "provider": "openai",
                "model": "test-model",
                "langfuse_enabled": True,
                "langfuse_trace_id": "trace-123",
                "langfuse_observation_id": "obs-456",
                "langfuse_host": "https://cloud.langfuse.com",
            },
        )

    assert diagnostics["langfuse_enabled"] is True
    assert diagnostics["langfuse_trace_id"] == "trace-123"
    assert diagnostics["langfuse_observation_id"] == "obs-456"
    assert diagnostics["langfuse_host"] == "https://cloud.langfuse.com"


def test_openai_provider_keeps_langfuse_disabled_calls_standard(app, monkeypatch):
    """Verify disabled Langfuse does not add wrapper-specific OpenAI kwargs."""
    captured = {}

    class FakeCompletions:
        """Capture OpenAI completion kwargs for assertions."""

        def create(self, **kwargs):
            """Return a fake completion and record call kwargs."""
            captured.update(kwargs)
            return FakeCompletion()

    class FakeChat:
        """Expose a completions client like the OpenAI SDK."""

        completions = FakeCompletions()

    class FakeClient:
        """Minimal OpenAI client test double."""

        chat = FakeChat()

        def __init__(self, **kwargs):
            """Accept OpenAI client construction kwargs."""
            self.kwargs = kwargs

        def with_options(self, **kwargs):
            """Return self for per-request client options."""
            self.kwargs.update(kwargs)
            return self

    monkeypatch.setattr("app.services.ai_provider_openai.openai_client_class", lambda: FakeClient)

    with app.app_context():
        provider = OpenAIProvider(api_key="test-key", model="test-model")
        answer = provider.answer_general_question("Hallo?")

    assert answer == "Testantwort"
    assert "name" not in captured
    assert "metadata" not in captured
    assert provider.last_call_metadata["langfuse_enabled"] is False


def test_langfuse_kwargs_follow_best_practices_when_ready(app, monkeypatch):
    """Verify configured Langfuse adds safe tags, user, and session metadata."""
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        app.config["GITHUB_REPOSITORY"] = "siinanXD/MaintanaceAIsisst"
        app.config["GITHUB_SHA"] = "046316cf89ca29e0b3f6608b9fbbffede7103782"
        app.config["GITHUB_REF_NAME"] = "master"
        profile = workflow_profile("general_chat")
        with langfuse_trace_context(
            "general_chat",
            user=FakeUser(),
            session_id="session-123",
            metadata={"source_count": 2},
            tags=["chat"],
        ):
            kwargs = openai_langfuse_kwargs("general_chat", profile)

    assert kwargs["name"] == "maintenance-ai.general_chat"
    assert kwargs["metadata"]["langfuse_tags"] == [
        "general_chat",
        profile.tier,
        profile.model,
        "chat",
    ]
    assert kwargs["metadata"]["langfuse_user_id"] == "user:42"
    assert kwargs["metadata"]["langfuse_user_role"] == "it"
    assert kwargs["metadata"]["langfuse_session_id"] == "session-123"
    assert kwargs["metadata"]["sourcecount"] == "2"
    assert kwargs["metadata"]["repository"] == "siinanXD/MaintanaceAIsisst"
    assert kwargs["metadata"]["commit"] == "046316cf89ca29e0b3f6608b9fbbffede7103782"
    assert kwargs["metadata"]["branch"] == "master"


def test_langfuse_propagates_user_before_root_span(app, monkeypatch):
    """Verify Langfuse user attributes are active before the root span starts."""
    calls = []

    class FakeSpan:
        """Minimal Langfuse span test double."""

        def update(self, **kwargs):
            """Record span updates."""
            calls.append(("span_update", kwargs))

    class FakeSpanContext:
        """Record span context manager ordering."""

        def __enter__(self):
            """Enter a fake span context."""
            calls.append(("span_enter", None))
            return FakeSpan()

        def __exit__(self, exc_type, exc, traceback):
            """Exit a fake span context."""
            calls.append(("span_exit", None))

    class FakePropagateContext:
        """Record propagation context manager ordering."""

        def __init__(self, kwargs):
            """Store propagation kwargs."""
            self.kwargs = kwargs

        def __enter__(self):
            """Enter a fake propagation context."""
            calls.append(("propagate_enter", self.kwargs))

        def __exit__(self, exc_type, exc, traceback):
            """Exit a fake propagation context."""
            calls.append(("propagate_exit", None))

    class FakeClient:
        """Minimal Langfuse client test double."""

        def start_as_current_observation(self, **kwargs):
            """Return a fake root span context manager."""
            calls.append(("start_span", kwargs))
            return FakeSpanContext()

        def get_current_trace_id(self):
            """Return a fake trace id."""
            return "trace-1"

        def get_current_observation_id(self):
            """Return a fake observation id."""
            return "obs-1"

    def fake_propagate_attributes(**kwargs):
        """Return a fake propagation context manager."""
        return FakePropagateContext(kwargs)

    fake_langfuse = types.SimpleNamespace(
        get_client=lambda: FakeClient(),
        propagate_attributes=fake_propagate_attributes,
    )
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        profile = workflow_profile("general_chat")
        with langfuse_trace_context("general_chat", user=FakeUser(), session_id="session-123"):
            with langfuse_observation("general_chat", profile) as observation:
                observation["runner"](lambda: calls.append(("call", None)) or "ok")

    ordered_names = [name for name, _value in calls]
    assert ordered_names.index("propagate_enter") < ordered_names.index("span_enter")
    propagation = calls[ordered_names.index("propagate_enter")][1]
    assert propagation["user_id"] == "user:42"
    assert propagation["session_id"] == "session-123"
    assert propagation["metadata"]["userrole"] == "it"


def test_langfuse_metadata_drops_sensitive_fields(app, monkeypatch):
    """Verify Langfuse metadata never carries prompt, answer, chunk text or secrets."""
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        profile = workflow_profile("chat")
        with langfuse_trace_context(
            "chat",
            user=FakeUser(),
            session_id="session-123",
            metadata={
                "source_count": 2,
                "raw_prompt": "Wie repariere ich E104?",
                "raw_answer": "Geheime Antwort",
                "chunk_text": "Privater Chunktext",
                "private_path": "C:/secret/private.txt",
                "api_secret": "sk-secret",
            },
        ):
            kwargs = openai_langfuse_kwargs("chat", profile)

    serialized = json.dumps(kwargs["metadata"], ensure_ascii=True).lower()
    assert kwargs["metadata"]["sourcecount"] == "2"
    assert "prompt" not in serialized
    assert "antwort" not in serialized
    assert "chunktext" not in serialized
    assert "private.txt" not in serialized
    assert "sk-secret" not in serialized


def test_langfuse_answer_trace_link_sends_only_safe_references(app, monkeypatch):
    """Verify answer trace references are linked to Langfuse without raw content."""
    calls = []

    class FakeSpan:
        """Minimal Langfuse span for answer trace linking."""

        def update(self, **kwargs):
            """Record metadata updates."""
            calls.append(("span_update", kwargs))

    class FakeSpanContext:
        """Context manager for a fake answer trace link span."""

        def __enter__(self):
            """Return a fake span."""
            calls.append(("span_enter", None))
            return FakeSpan()

        def __exit__(self, exc_type, exc, traceback):
            """Record span exit."""
            calls.append(("span_exit", None))

    class FakeClient:
        """Minimal Langfuse client for answer trace link tests."""

        def start_as_current_observation(self, **kwargs):
            """Record the created span arguments."""
            calls.append(("start_span", kwargs))
            return FakeSpanContext()

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    chat_message = types.SimpleNamespace(
        id=77,
        user_id=42,
        session_id="session-123",
        audit_event_id=12,
        user=FakeUser(),
    )
    answer_trace = types.SimpleNamespace(
        id=5,
        answer_id="ans_public123",
        audit_event=types.SimpleNamespace(latency_ms=321),
        workflow="chat",
        model="gpt-4o-mini",
        model_tier="balanced",
        input_tokens=120,
        output_tokens=40,
        cached_tokens=10,
        total_tokens=170,
        estimated_cost_usd=0.0123456,
        confidence_score=87,
        confidence_level="high",
        source_count=3,
        chunk_count=2,
    )
    diagnostics = {
        "langfuse_trace_id": "1234567890abcdef1234567890abcdef",
        "langfuse_observation_id": "fedcba0987654321",
        "prompt": "do not send",
        "answer": "do not send",
    }

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        linked = link_langfuse_answer_trace(diagnostics, chat_message, answer_trace)

    assert linked is True
    start_span = next(value for name, value in calls if name == "start_span")
    assert start_span["name"] == "maintenance-ai.answer_trace_link"
    assert start_span["input"] == {"kind": "answer_trace_link"}
    assert start_span["trace_context"] == {
        "trace_id": "1234567890abcdef1234567890abcdef",
        "parent_span_id": "fedcba0987654321",
    }
    update = next(value for name, value in calls if name == "span_update")
    metadata = update["metadata"]
    assert metadata["answerid"] == "ans_public123"
    assert metadata["answertraceid"] == "5"
    assert metadata["chatmessageid"] == "77"
    assert metadata["userid"] == "user:42"
    assert metadata["userrole"] == "it"
    assert metadata["sessionid"] == "session-123"
    assert metadata["sourcecount"] == "3"
    assert metadata["chunkcount"] == "2"
    assert metadata["model"] == "gpt-4o-mini"
    assert metadata["inputtokens"] == "120"
    assert metadata["outputtokens"] == "40"
    assert metadata["cachedtokens"] == "10"
    assert metadata["totaltokens"] == "170"
    assert metadata["estimatedcostusd"] == "0.012346"
    assert metadata["latencyms"] == "321"
    assert metadata["retrievalused"] == "True"
    assert metadata["confidencescore"] == "87"
    assert metadata["confidencelevel"] == "high"
    serialized = json.dumps(update, ensure_ascii=True).lower()
    assert "do not send" not in serialized
    assert "prompt" not in serialized
    assert "raw" not in serialized


def test_langfuse_answer_trace_link_is_optional_without_config(app):
    """Verify missing Langfuse configuration does not break answer processing."""
    chat_message = types.SimpleNamespace(id=77, user_id=42, session_id="session-123")
    answer_trace = types.SimpleNamespace(id=5, answer_id="ans_public123")

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = False
        linked = link_langfuse_answer_trace(
            {"langfuse_trace_id": "1234567890abcdef1234567890abcdef"},
            chat_message,
            answer_trace,
        )

    assert linked is False


def test_langfuse_tracking_documentation_lists_safe_metadata():
    """Verify docs describe Langfuse as a safe external observability sink."""
    root = Path(__file__).resolve().parents[1]
    docs = (root / "docs" / "AI_ANSWER_TRACEABILITY.md").read_text(encoding="utf-8")

    for value in (
        "inputtokens",
        "outputtokens",
        "cachedtokens",
        "totaltokens",
        "estimatedcostusd",
        "latencyms",
        "retrievalused",
        "confidencescore",
        "confidencelevel",
    ):
        assert value in docs
    assert "Langfuse ist ein externer Observability-Sink" in docs
    assert "`AIAnswerTrace` bleibt System of Record" in docs


def test_langfuse_environment_uses_current_base_url_names(app, monkeypatch):
    """Verify Langfuse receives current and legacy base URL environment names."""
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_BASE_URL"] = "https://us.cloud.langfuse.com"
        app.config["LANGFUSE_HOST"] = "https://legacy.example.test"
        app.config["LANGFUSE_TRACING_ENVIRONMENT"] = "development"
        configure_langfuse_environment()

    assert os.environ["LANGFUSE_BASE_URL"] == "https://us.cloud.langfuse.com"
    assert os.environ["LANGFUSE_HOST"] == "https://us.cloud.langfuse.com"
    assert os.environ["LANGFUSE_TRACING_ENVIRONMENT"] == "development"


def test_langfuse_metrics_summary_uses_metrics_api_v2(app):
    """Verify Langfuse cost metrics are loaded from the Metrics API safely."""
    captured_queries = []

    def fake_http_get(url, authorization_header, timeout):
        """Return deterministic Langfuse Metrics API responses."""
        parsed_url = urlparse(url)
        query = parse_qs(parsed_url.query)["query"][0]
        captured_queries.append(query)
        assert parsed_url.path == "/api/public/v2/metrics"
        assert timeout == 3.0
        assert authorization_header == (
            "Basic "
            + base64.b64encode(
                f"{LANGFUSE_TEST_PUBLIC_KEY}:{LANGFUSE_TEST_SECRET_KEY}".encode("ascii")
            ).decode("ascii")
        )
        if "providedModelName" in query:
            return {
                "data": [
                    {
                        "providedModelName": "gpt-4o-mini",
                        "count_count": "4",
                        "totalTokens_sum": "1500",
                        "totalCost_sum": "0.0123",
                        "latency_avg": "244",
                    }
                ]
            }
        if "traceName" in query:
            return {
                "data": [
                    {
                        "traceName": "maintenance-ai.chat",
                        "count_count": "4",
                        "totalTokens_sum": "1500",
                        "totalCost_sum": "0.0123",
                        "latency_avg": "244",
                    }
                ]
            }
        return {
            "data": [
                {
                    "count_count": "4",
                    "totalTokens_sum": "1500",
                    "totalCost_sum": "0.0123",
                    "latency_avg": "244",
                }
            ]
        }

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        app.config["LANGFUSE_BASE_URL"] = "https://cloud.langfuse.com"
        metrics = langfuse_metrics_summary(days=7, http_get=fake_http_get)

    assert len(captured_queries) == 3
    assert metrics["available"] is True
    assert metrics["total_cost_usd"] == 0.0123
    assert metrics["total_tokens"] == 1500
    assert metrics["observation_count"] == 4
    assert metrics["average_latency_ms"] == 244
    assert metrics["models"][0]["model"] == "gpt-4o-mini"
    assert metrics["workflows"][0]["workflow"] == "maintenance-ai.chat"


def test_ai_summary_includes_unavailable_langfuse_metrics(app):
    """Verify AI summary exposes Langfuse metrics status without requiring Langfuse."""
    with app.app_context():
        summary = ai_analytics_summary(days=7)

    assert summary["langfuse_metrics"]["available"] is False
    assert summary["langfuse_metrics"]["status"] == "disabled"


def test_langfuse_eval_disabled_by_default(app):
    """Verify automatic eval scores stay off unless explicitly enabled."""
    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        assert langfuse_eval_enabled() is False
        assert (
            submit_automatic_eval_scores(
                {"langfuse_trace_id": "trace-abc"},
                {"answer": "Antwort"},
            )
            == 0
        )


def test_submit_langfuse_scores_calls_create_score(app, monkeypatch):
    """Verify score payloads are forwarded to the Langfuse client."""
    calls = []

    class FakeClient:
        """Minimal Langfuse client for score submission tests."""

        def create_score(self, **kwargs):
            """Record one score submission."""
            calls.append(kwargs)

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        submitted = submit_langfuse_scores(
            "trace-abc",
            [
                {
                    "name": "hallucination-risk",
                    "value": 1.0,
                    "data_type": "BOOLEAN",
                }
            ],
        )

    assert submitted == 1
    assert calls[0]["name"] == "hallucination-risk"
    assert calls[0]["trace_id"] == "trace-abc"
    assert calls[0]["data_type"] == "BOOLEAN"


def test_submit_automatic_eval_scores_maps_hallucination_and_retrieval(app, monkeypatch):
    """Verify automatic eval scores include hallucination and retrieval metrics."""
    calls = []

    class FakeClient:
        """Minimal Langfuse client for automatic eval score tests."""

        def create_score(self, **kwargs):
            """Record one score submission."""
            calls.append(kwargs)

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    diagnostics = {
        "langfuse_trace_id": "trace-abc",
        "hallucination_warning": True,
        "empty_retrieval": True,
        "retrieval_used": True,
        "retrieval_duration_ms": 180,
        "retrieval_explainability": {
            "source_count": 2,
            "explained_source_count": 2,
            "averages": {"final_score": 72.5, "semantic_similarity": 0.81},
            "machine_match_count": 1,
        },
        "confidence_score": 65,
    }
    result = {
        "answer": "Kurze Antwort",
        "question": "Wie repariere ich E104?",
        "answer_quality": {"status": "no_answer", "no_answer": True},
        "confidence": {"score": 65},
        "sources": [{"type": "document", "title": "Handbuch A", "module": "docs"}],
    }

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        app.config["LANGFUSE_EVAL_ENABLED"] = True
        app.config["LANGFUSE_EVAL_CAPTURE_IO"] = False
        submitted = submit_automatic_eval_scores(diagnostics, result)

    assert submitted >= 5
    score_names = {call["name"] for call in calls}
    assert "hallucination-risk" in score_names
    assert "empty-retrieval" in score_names
    assert "no-answer" in score_names
    assert "retrieval-avg-final-score" in score_names
    assert "confidence" in score_names
    assert calls[0]["trace_id"] == "trace-abc"


def test_submit_user_feedback_score_maps_ratings(app, monkeypatch):
    """Verify user feedback ratings are converted into Langfuse scores."""
    calls = []

    class FakeClient:
        """Minimal Langfuse client for feedback score tests."""

        def create_score(self, **kwargs):
            """Record one score submission."""
            calls.append(kwargs)

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    chat_message = types.SimpleNamespace(
        diagnostics=lambda: {"langfuse_trace_id": "trace-feedback"},
    )
    feedback_entry = types.SimpleNamespace(
        rating="partially_helpful",
        comment="Quellen waren unklar",
    )

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        linked = submit_user_feedback_score(chat_message, feedback_entry)

    assert linked is True
    assert len(calls) == 2
    numeric = next(call for call in calls if call["name"] == "user-feedback")
    categorical = next(call for call in calls if call["name"] == "user-feedback-rating")
    assert numeric["value"] == 0.5
    assert categorical["value"] == "partially_helpful"
    assert "Quellen waren unklar" in numeric["comment"]


def test_attach_langfuse_eval_io_skipped_without_capture_flag(app, monkeypatch):
    """Verify eval IO is not sent unless LANGFUSE_EVAL_CAPTURE_IO is enabled."""
    calls = []

    class FakeClient:
        """Minimal Langfuse client for eval IO tests."""

        def start_as_current_observation(self, **kwargs):
            """Record span creation attempts."""
            calls.append(kwargs)
            raise AssertionError("eval IO should not be created")

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        app.config["LANGFUSE_EVAL_ENABLED"] = True
        app.config["LANGFUSE_EVAL_CAPTURE_IO"] = False
        attached = attach_langfuse_eval_io(
            "trace-abc",
            {"hallucination_warning": True},
            {"answer": "Antwort", "question": "Frage"},
        )

    assert attached is False
    assert calls == []


def test_attach_langfuse_eval_io_omits_chunk_text(app, monkeypatch):
    """Verify eval IO contains bounded text but never raw chunk content."""
    calls = []

    class FakeSpan:
        """Minimal Langfuse span for eval IO tests."""

        def update(self, **kwargs):
            """Record span updates."""
            calls.append(("update", kwargs))

    class FakeSpanContext:
        """Context manager for eval IO span tests."""

        def __enter__(self):
            """Return a fake span."""
            return FakeSpan()

        def __exit__(self, exc_type, exc, traceback):
            """Ignore span exit."""

    class FakeClient:
        """Minimal Langfuse client for eval IO span tests."""

        def start_as_current_observation(self, **kwargs):
            """Record span creation."""
            calls.append(("start", kwargs))
            return FakeSpanContext()

    fake_langfuse = types.SimpleNamespace(get_client=lambda: FakeClient())
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setattr("app.services.langfuse_service._langfuse_available", lambda: True)

    with app.app_context():
        app.config["LANGFUSE_ENABLED"] = True
        app.config["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_TEST_PUBLIC_KEY
        app.config["LANGFUSE_SECRET_KEY"] = LANGFUSE_TEST_SECRET_KEY
        app.config["LANGFUSE_EVAL_ENABLED"] = True
        app.config["LANGFUSE_EVAL_CAPTURE_IO"] = True
        attached = attach_langfuse_eval_io(
            "trace-abc",
            {"hallucination_warning": True, "empty_retrieval": True},
            {
                "answer": "Antworttext",
                "question": "Frage zum Fehler",
                "sources": [
                    {
                        "type": "document",
                        "title": "Handbuch",
                        "chunk_text": "Geheimer Chunk",
                    }
                ],
            },
        )

    assert attached is True
    start = next(value for name, value in calls if name == "start")
    serialized = json.dumps(start, ensure_ascii=True).lower()
    assert start["name"] == "maintenance-ai.eval_io"
    assert start["input"]["question"] == "Frage zum Fehler"
    assert "geheimer chunk" not in serialized
    assert "chunktext" not in serialized


def test_ai_diagnostics_preserves_langfuse_trace_metadata(app):
    """Verify rebuilding diagnostics keeps Langfuse trace identifiers."""
    payload = ai_diagnostics(
        "local_answer",
        metadata={
            "langfuse_enabled": True,
            "langfuse_trace_id": "trace-preserve",
            "langfuse_observation_id": "obs-preserve",
            "langfuse_host": "https://cloud.langfuse.com",
        },
    )

    assert payload["langfuse_trace_id"] == "trace-preserve"
    assert payload["langfuse_observation_id"] == "obs-preserve"
    assert payload["langfuse_host"] == "https://cloud.langfuse.com"


def test_langfuse_evaluation_documentation_exists():
    """Verify Langfuse evaluation setup is documented."""
    root = Path(__file__).resolve().parents[1]
    docs = (root / "docs" / "LANGFUSE_EVALUATION.md").read_text(encoding="utf-8")
    assert "LANGFUSE_EVAL_ENABLED" in docs
    assert "user-feedback" in docs
    assert "hallucination-risk" in docs
    assert "LLM-as-a-Judge" in docs
