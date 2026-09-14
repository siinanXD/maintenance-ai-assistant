"""AI provider contract, selection and readiness; the providers live in ai_provider_*."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from flask import current_app
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


CHAT_PROVIDER_CATALOG = (
    {
        "provider": "mock",
        "status": "supported",
        "mode": "local_fallback",
        "requires_credential": False,
        "requires_base_url": False,
        "effective_fallback": "mock",
    },
    {
        "provider": "openai",
        "status": "supported",
        "mode": "external",
        "requires_credential": True,
        "requires_base_url": False,
        "effective_fallback": "mock",
    },
    {
        "provider": "openai_compatible",
        "status": "supported",
        "mode": "openai_compatible",
        "requires_credential": True,
        "requires_base_url": True,
        "effective_fallback": "mock",
    },
    {
        "provider": "gemini",
        "status": "planned",
        "mode": "unsupported",
        "requires_credential": True,
        "requires_base_url": False,
        "effective_fallback": "mock",
    },
)


def openai_error_code(error):
    """Return a safe stable category for an OpenAI SDK error."""
    error_text = str(error).lower()
    if isinstance(error, RateLimitError):
        return "rate_limit"
    if isinstance(error, AuthenticationError):
        return "authentication_error"
    if isinstance(error, PermissionDeniedError | NotFoundError | BadRequestError) and (
        "model_not_found" in error_text
        or "does not have access to model" in error_text
        or "model" in error_text
    ):
        return "model_not_allowed"
    if isinstance(error, PermissionDeniedError):
        return "permission_denied"
    if isinstance(error, NotFoundError):
        return "not_found"
    if isinstance(error, BadRequestError):
        return "bad_request"
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, APIConnectionError):
        return "connection_error"
    return "openai_error"


class AIServiceError(Exception):
    """Raised when an AI provider cannot return a usable result."""

    def __init__(self, message, error_code="openai_error"):
        """Create an AI provider error with a safe diagnostic category."""
        super().__init__(message)
        self.error_code = error_code


def log_ai_call_failure(provider_name, model, mode, error_code, exc):
    """Log expected AI provider timeouts compactly and unexpected failures fully."""
    if error_code == "timeout":
        logger.warning(
            "ai_call_failed provider=%s model=%s mode=%s error_code=%s detail=%s",
            provider_name,
            model,
            mode,
            error_code,
            exc,
        )
        return
    logger.exception(
        "ai_call_failed provider=%s model=%s mode=%s error_code=%s",
        provider_name,
        model,
        mode,
        error_code,
    )


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ToolCallResponse:
    """Provider answer for a tool-enabled chat turn."""

    content: str | None = None
    tool_calls: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BaseAIProvider(ABC):
    """Define the provider contract for AI-assisted workflows."""

    name = "base"
    supports_tool_calls = False

    def chat_with_tools(self, messages, tools, workflow="agent"):
        """Return a ``ToolCallResponse`` for provider-format messages and tool schemas.

        Providers without tool calling raise ``AIServiceError`` so the agent
        workflow can fall back visibly instead of pretending to reason.
        """
        raise AIServiceError(
            "AI provider does not support tool calling",
            error_code="unsupported_capability",
        )

    @abstractmethod
    def suggest_task(self, text, user_context=None):
        """Return a structured task suggestion for free text."""

    @abstractmethod
    def analyze_error(self, text, user_context=None):
        """Return a structured error analysis for free text."""

    @abstractmethod
    def generate_document_text(self, data):
        """Return generated maintenance report text."""

    @abstractmethod
    def answer_question(self, question, context, workflow="chat", extra_rules=None):
        """Return a natural-language answer for a question and context."""

    @abstractmethod
    def answer_general_question(self, question):
        """Return a short answer for a general hybrid-mode question."""

    @abstractmethod
    def prioritize_tasks(self, tasks, context=None):
        """Return structured prioritization results for visible tasks."""

    @abstractmethod
    def review_document(self, html_text, metadata=None):
        """Return a structured quality review for a maintenance document."""

    @abstractmethod
    def error_assistant_query(self, query, matches):
        """Return AI-enhanced causes and fixes for a fault description.

        Args:
            query:   The raw user fault description string.
            matches: List of similarity-scored catalog match dicts already
                     found by the local search.  Each dict has keys
                     ``entry``, ``score``, and ``reason``.

        Returns:
            dict with keys ``causes`` (list[str]), ``fixes`` (list[str]),
            and optionally ``summary`` (str) — or ``None`` to skip
            enhancement and keep local results unchanged.

        """


def get_ai_provider():
    """Return the configured AI provider with mock fallback."""
    # The providers subclass BaseAIProvider from this module, so they load here, not at import.
    from app.services.ai_provider_mock import MockAIProvider
    from app.services.ai_provider_openai import OpenAIProvider

    provider_name = _configured_provider_name()
    api_key = _configured_api_key()
    model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
    if provider_name == "mock":
        return MockAIProvider()
    if provider_name in {"openai", "openai_compatible"}:
        if not api_key:
            logger.warning("ai_fallback provider=%s reason=api_key_missing", provider_name)
            return MockAIProvider()
        if provider_name == "openai_compatible" and not _configured_base_url():
            logger.warning("ai_fallback provider=openai_compatible reason=base_url_missing")
            return MockAIProvider()
        return OpenAIProvider(api_key=api_key, model=model, provider_name=provider_name)
    logger.warning("ai_fallback provider=%s reason=unsupported_provider", provider_name)
    return MockAIProvider()


def ai_provider_catalog():
    """Return redacted chat-provider capabilities for admin status payloads."""
    return [dict(item) for item in CHAT_PROVIDER_CATALOG]


def ai_provider_status(provider, api_key_configured, config=None):
    """Return a redacted readiness summary for the configured chat provider."""
    config = config or current_app.config
    provider_name = str(provider or "openai").strip().lower()
    if provider_name == "mock":
        return {
            "provider": "mock",
            "ready": True,
            "mode": "local_fallback",
            "reason": "",
            "effective_provider": "mock",
            "configuration_action": "none",
            "recommended_action": "Keine Provider-Konfiguration erforderlich.",
        }
    if provider_name == "openai":
        ready = bool(api_key_configured)
        reason = "" if api_key_configured else "api_key_missing"
        return {
            "provider": "openai",
            "ready": ready,
            "mode": "external",
            "reason": reason,
            "effective_provider": "openai" if ready else "mock",
            "configuration_action": _provider_configuration_action(reason),
            "recommended_action": _provider_recommended_action(reason),
        }
    if provider_name == "openai_compatible":
        base_url_configured = bool(_configured_base_url(config))
        ready = bool(api_key_configured and base_url_configured)
        reason = ""
        if not api_key_configured:
            reason = "api_key_missing"
        elif not base_url_configured:
            reason = "base_url_missing"
        return {
            "provider": "openai_compatible",
            "ready": ready,
            "mode": "openai_compatible",
            "reason": reason,
            "base_url_configured": base_url_configured,
            "effective_provider": "openai_compatible" if ready else "mock",
            "configuration_action": _provider_configuration_action(reason),
            "recommended_action": _provider_recommended_action(reason),
        }
    reason = "unsupported_provider"
    return {
        "provider": provider_name,
        "ready": False,
        "mode": "unsupported",
        "reason": reason,
        "effective_provider": "mock",
        "configuration_action": _provider_configuration_action(reason),
        "recommended_action": _provider_recommended_action(reason),
    }


def _provider_configuration_action(reason):
    """Return a stable admin action key for one provider readiness reason."""
    actions = {
        "": "none",
        "api_key_missing": "set_openai_api_key",
        "base_url_missing": "set_ai_base_url",
        "unsupported_provider": "select_supported_provider",
    }
    return actions.get(str(reason or ""), "review_provider_configuration")


def _provider_recommended_action(reason):
    """Return a concise admin-facing provider remediation hint."""
    actions = {
        "": "Provider ist einsatzbereit.",
        "api_key_missing": "OPENAI_API_KEY setzen oder AI_PROVIDER=mock verwenden.",
        "base_url_missing": "AI_BASE_URL fuer den OpenAI-kompatiblen Endpoint setzen.",
        "unsupported_provider": ("AI_PROVIDER auf openai, openai_compatible oder mock setzen."),
    }
    return actions.get(str(reason or ""), "AI-Provider-Konfiguration pruefen.")


def _configured_provider_name(config=None):
    """Return the normalized configured chat provider name."""
    config = config or current_app.config
    return str(config.get("AI_PROVIDER", "openai") or "openai").strip().lower()


def ai_api_key_configured(config=None):
    """Return whether the OpenAI API key is configured with non-blank text."""
    return bool(_configured_api_key(config))


def _configured_api_key(config=None):
    """Return the normalized OpenAI API key, or an empty string when unset."""
    config = config or current_app.config
    return str(config.get("OPENAI_API_KEY") or "").strip()


def _configured_base_url(config=None):
    """Return the normalized AI base URL, or an empty string when unset."""
    config = config or current_app.config
    return str(config.get("AI_BASE_URL") or "").strip()
