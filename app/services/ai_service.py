"""AI provider implementations and normalization helpers."""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from flask import current_app
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from app.services.ai_prompting import (
    build_general_messages,
    build_json_messages,
    build_json_prompt,
    build_text_messages,
)
from app.services.ai_routing import (
    call_timer,
    completion_metadata,
    elapsed_ms,
    local_metadata,
    openai_client_options,
    workflow_profile,
)
from app.services.langfuse_service import (
    langfuse_observation,
    normalize_observation_metadata,
    openai_client_class,
    openai_langfuse_kwargs,
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


class MockAIProvider(BaseAIProvider):
    """Provide deterministic local AI-like results without external services."""

    name = "mock"
    supports_tool_calls = True

    def chat_with_tools(self, messages, tools, workflow="agent"):
        """Select tools with deterministic keyword rules and summarize tool results."""
        from app.agent.mock_policy import select_mock_tool_call

        self.last_call_metadata = local_metadata(self.name, workflow)
        content, calls = select_mock_tool_call(messages, tools)
        return ToolCallResponse(
            content=content,
            tool_calls=[
                ToolCall(id=call["id"], name=call["name"], arguments=dict(call["arguments"]))
                for call in calls
            ],
            metadata=dict(self.last_call_metadata),
        )

    def suggest_task(self, text, user_context=None):
        """Return a deterministic task suggestion from free text."""
        self.last_call_metadata = local_metadata(self.name, "task_suggestion")
        department = _department_from_text(text, user_context)
        priority = "urgent" if _contains_any(text, ["not-halt", "stillstand"]) else "soon"
        machine = _extract_machine(text)
        title = _short_title(text, prefix="Pruefung")
        return {
            "title": title,
            "description": text.strip(),
            "department": department,
            "priority": priority,
            "status": "open",
            "possible_cause": _cause_from_text(text),
            "recommended_action": (
                f"{machine} sicher pruefen, Befund dokumentieren und "
                "bei Bedarf Instandhaltung informieren."
            ),
        }

    def analyze_error(self, text, user_context=None):
        """Return a deterministic error analysis from free text."""
        self.last_call_metadata = local_metadata(self.name, "error_analysis")
        machine = _extract_machine(text)
        return {
            "machine": machine,
            "title": _short_title(text, prefix="Stoerung"),
            "description": text.strip(),
            "possible_causes": _cause_from_text(text),
            "solution": (
                "Anlage sichern, Sichtpruefung durchfuehren, betroffene "
                "Komponenten pruefen und Ergebnis im Fehlerkatalog dokumentieren."
            ),
            "department": _department_from_text(text, user_context),
        }

    def generate_document_text(self, data):
        """Return a deterministic maintenance report text."""
        self.last_call_metadata = local_metadata(self.name, "document_text")
        return (
            f"Wartungsbericht fuer Task {data.get('task_id')}: "
            f"{data.get('title')}. Ergebnis: {data.get('result') or 'erledigt'}."
        )

    def answer_question(self, question, context, workflow="chat", extra_rules=None):
        """Return a cautious local answer for a question and context."""
        self.last_call_metadata = local_metadata(self.name, workflow)
        if not context.strip():
            return (
                "## Ergebnis\n"
                "- **Status:** Keine passende Grundlage gefunden\n"
                "- **Naechster Schritt:** Daten oder Suchbegriff pruefen"
            )
        return (
            "## Ergebnis\n"
            "- **Status:** Freigegebene Daten geprueft\n"
            "- **Hinweis:** Frage bitte konkreter nach Tasks, Fehlern, "
            "Maschinen, Lager, Dokumenten oder Mitarbeitern"
        )

    def answer_general_question(self, question):
        """Return a deterministic local answer for general hybrid mode."""
        self.last_call_metadata = local_metadata(self.name, "general_chat")
        return (
            "## Allgemeine Antwort\n"
            "- **Status:** Allgemeine AI-Antwort ist lokal nicht verfuegbar\n"
            "- **Naechster Schritt:** OpenAI API-Key und Verbindung pruefen"
        )

    def prioritize_tasks(self, tasks, context=None):
        """Return deterministic task priorities without external services."""
        self.last_call_metadata = local_metadata(self.name, "task_prioritization")
        priorities = [_score_task_priority(task) for task in tasks]
        return {"priorities": priorities}

    def review_document(self, html_text, metadata=None):
        """Return a simple placeholder document review for local mode."""
        self.last_call_metadata = local_metadata(self.name, "document_review")
        return {
            "quality_score": 0,
            "status": "incomplete",
            "findings": [],
            "recommendations": [],
        }

    def error_assistant_query(self, query, matches):
        """Return None — local similarity results are sufficient in mock mode."""
        return None


class OpenAIProvider(BaseAIProvider):
    """Use OpenAI for AI-assisted workflows."""

    name = "openai"
    supports_tool_calls = True

    def __init__(self, api_key, model, provider_name="openai"):
        """Initialize the OpenAI provider."""
        client_class = openai_client_class()
        self.name = provider_name
        self.client = client_class(
            api_key=api_key,
            **openai_client_options(allow_base_url=self.name == "openai_compatible"),
        )
        self.legacy_model = model
        self.model = model
        self.last_call_metadata = {}

    def _client_for_profile(self, profile):
        """Return an OpenAI client configured for one workflow profile."""
        return self.client.with_options(
            **openai_client_options(
                profile,
                allow_base_url=self.name == "openai_compatible",
            )
        )

    def suggest_task(self, text, user_context=None):
        """Return a structured task suggestion for free text."""
        prompt = build_json_prompt(
            "Erstelle einen professionellen deutschen Wartungs-Task-Vorschlag.",
            {
                "title": "string",
                "description": "string",
                "department": "string",
                "priority": "urgent|soon|normal",
                "status": "open",
                "possible_cause": "string",
                "recommended_action": "string",
            },
            payload={
                "input": text,
                "user_context": user_context or {},
            },
            rules=[
                "Der Vorschlag ist ein read-only Entwurf.",
                "Schreibe keine Daten und behaupte keine Speicherung.",
            ],
        )
        return self._json_completion(prompt, "task_suggestion")

    def analyze_error(self, text, user_context=None):
        """Return a structured error analysis for free text."""
        prompt = build_json_prompt(
            "Analysiere eine deutsche Maschinenstoerung als strukturierten Entwurf.",
            {
                "machine": "string",
                "title": "string",
                "description": "string",
                "possible_causes": "string",
                "solution": "string",
                "department": "string",
            },
            payload={
                "input": text,
                "user_context": user_context or {},
            },
            rules=[
                "Formuliere fachlich vorsichtig.",
                "Der Eintrag wird nicht gespeichert.",
            ],
        )
        return self._json_completion(prompt, "error_analysis")

    def generate_document_text(self, data):
        """Return generated maintenance report text."""
        messages, prompt_metadata = build_text_messages(
            "Formuliere einen kurzen, sachlichen Wartungsbericht.",
            json.dumps(data, ensure_ascii=True),
            extra_rules=(
                "Formuliere kurze, sachliche Wartungsberichte aus den "
                "bereitgestellten Taskdaten."
            ),
            workflow="document_text",
            include_metadata=True,
        )
        return self._text_completion(messages, "document_text", prompt_metadata=prompt_metadata)

    def answer_question(self, question, context, workflow="chat", extra_rules=None):
        """Return a natural-language answer for a question and context."""
        messages, prompt_metadata = build_text_messages(
            question,
            context,
            extra_rules=extra_rules,
            workflow=workflow,
            include_metadata=True,
        )
        return self._text_completion(messages, workflow, prompt_metadata=prompt_metadata)

    def answer_general_question(self, question):
        """Return a short natural-language answer for general hybrid mode."""
        messages, prompt_metadata = build_general_messages(question, include_metadata=True)
        return self._text_completion(messages, "general_chat", prompt_metadata=prompt_metadata)

    def prioritize_tasks(self, tasks, context=None):
        """Return AI-generated task priorities as structured JSON."""
        prompt = build_json_prompt(
            "Priorisiere sichtbare Wartungsaufgaben nach Risiko und Faelligkeit.",
            {
                "priorities": [
                    {
                        "task_id": "integer",
                        "score": "integer 0-100",
                        "risk_level": "low|medium|high|critical",
                        "reason": "short German reason",
                        "recommended_action": "short German next action",
                    }
                ]
            },
            payload={
                "tasks": tasks,
                "context": context or {},
            },
            rules=[
                "Nutze nur die bereitgestellten Tasks.",
                "Beruecksichtige history nur als Kontext fuer Risiko und Begruendung.",
                "Nutze keine Mitarbeiterdaten.",
                "Jeder task_id-Wert muss aus der Eingabe stammen.",
                "Erklaere hohe Scores mit konkreten Signalen wie Faelligkeit, "
                "Historie oder Blockade.",
            ],
        )
        return self._json_completion(prompt, "task_prioritization")

    def error_assistant_query(self, query, matches):
        """Return AI-enhanced fault analysis from catalog matches."""
        catalog_context = []
        for match in matches[:3]:
            match_payload = match if isinstance(match, dict) else {}
            entry = match_payload.get("entry")
            entry = entry if isinstance(entry, dict) else {}
            catalog_context.append(
                {
                    "source_id": match_payload.get("id") or entry.get("id"),
                    "machine": match_payload.get("machine") or entry.get("machine"),
                    "relevance": match_payload.get("score"),
                    "entry": entry,
                }
            )

        prompt = build_json_prompt(
            instruction=(
                "Analysiere eine technische Stoerungsbeschreibung anhand "
                "passender Fehlerkatalog-Treffer."
            ),
            schema={
                "summary": "short German technical summary",
                "causes": [
                    {
                        "cause": "string",
                        "confidence": "low|medium|high",
                        "source_id": "string",
                    }
                ],
                "fixes": [
                    {
                        "step": "string",
                        "priority": "high|medium|low",
                    }
                ],
                "uncertainty": "niedrig|mittel|hoch",
            },
            payload={
                "user_query": query,
                "catalog_matches": catalog_context,
            },
            rules=[
                "Nutze primaer die Fehlerkatalog-Treffer.",
                "Erfinde keine technischen Ursachen.",
                "Wenn keine ausreichenden Informationen vorhanden sind, "
                "weise auf Unsicherheit hin.",
                "Bevorzuge Treffer mit hoher Relevanz.",
                "Gib konkrete technische Pruefschritte.",
                "Vermeide allgemeine Standardantworten.",
                "Nutze vorsichtige Formulierungen bei geringer Sicherheit.",
            ],
        )
        return self._json_completion(prompt, "error_assistant")

    def review_document(self, html_text, metadata=None):
        """Return an AI-generated maintenance document quality review."""
        prompt = build_json_prompt(
            instruction=(
                "Pruefe einen deutschen Wartungsbericht auf Vollstaendigkeit, "
                "konkrete Nachvollziehbarkeit und technische Verwertbarkeit."
            ),
            schema={
                "quality_score": "integer 0-100",
                "status": "good|needs_review|incomplete",
                "findings": [
                    {
                        "field": "machine|cause|action|result|notes|metadata",
                        "severity": "info|warning|critical",
                        "message": "short German message",
                    }
                ],
                "recommendations": ["short German recommendation"],
            },
            payload={
                "metadata": metadata or {},
                "html_text": html_text[:12000],
            },
            rules=[
                "Bewerte nur den bereitgestellten Wartungsbericht.",
                "Erfinde keine fehlenden Inhalte.",
                "Pruefe Maschine, Ursache, durchgefuehrte Massnahme, Ergebnis und Notizen.",
                "Markiere fehlende oder unklare Angaben konkret.",
                "Gib kurze, umsetzbare Empfehlungen.",
                "Setze quality_score niedrig, wenn Ursache, Massnahme oder Ergebnis fehlen.",
            ],
        )
        return self._json_completion(prompt, "document_review")

    def chat_with_tools(self, messages, tools, workflow="agent"):
        """Run one tool-enabled chat turn and return content and tool calls."""
        profile = workflow_profile(workflow, self.legacy_model)
        self.model = profile.model
        logger.info(
            "ai_call provider=%s model=%s tier=%s mode=tools message_count=%s tool_count=%s",
            self.name,
            profile.model,
            profile.tier,
            len(messages),
            len(tools or []),
        )
        try:
            completion, latency_ms, trace_metadata = self._chat_completion(
                profile,
                workflow,
                messages,
                tools=tools,
            )
            self.last_call_metadata = completion_metadata(
                self.name,
                profile,
                completion,
                latency_ms,
            )
            self.last_call_metadata.update(trace_metadata)
            choice_message = completion.choices[0].message
            return ToolCallResponse(
                content=getattr(choice_message, "content", None),
                tool_calls=_parse_tool_calls(getattr(choice_message, "tool_calls", None)),
                metadata=dict(self.last_call_metadata),
            )
        except (OpenAIError, TypeError, AttributeError, IndexError) as exc:
            error_code = (
                openai_error_code(exc) if isinstance(exc, OpenAIError) else "invalid_response"
            )
            log_ai_call_failure(self.name, self.model, "tools", error_code, exc)
            raise AIServiceError(
                "AI provider failed to return a tool-enabled response",
                error_code=error_code,
            ) from exc

    def _json_completion(self, prompt, workflow):
        """Call OpenAI and parse a JSON object response."""
        profile = workflow_profile(workflow, self.legacy_model)
        self.model = profile.model
        logger.info(
            "ai_call provider=%s model=%s tier=%s mode=json task=%s",
            self.name,
            profile.model,
            profile.tier,
            prompt.get("task", "unknown"),
        )
        try:
            messages, prompt_metadata = build_json_messages(
                prompt,
                workflow=workflow,
                include_metadata=True,
            )
            completion, latency_ms, trace_metadata = self._chat_completion(
                profile,
                workflow,
                messages,
                response_format={"type": "json_object"},
            )
            self.last_call_metadata = completion_metadata(
                self.name,
                profile,
                completion,
                latency_ms,
            )
            self.last_call_metadata.update(prompt_metadata)
            self.last_call_metadata.update(trace_metadata)
            return json.loads(completion.choices[0].message.content)
        except (OpenAIError, TypeError, json.JSONDecodeError) as exc:
            error_code = (
                openai_error_code(exc) if isinstance(exc, OpenAIError) else "invalid_response"
            )
            log_ai_call_failure(
                self.name,
                self.model,
                "json",
                error_code,
                exc,
            )
            raise AIServiceError(
                "AI provider failed to return valid JSON",
                error_code=error_code,
            ) from exc

    def _text_completion(self, messages, workflow, prompt_metadata=None):
        """Call OpenAI and return text content."""
        profile = workflow_profile(workflow, self.legacy_model)
        self.model = profile.model
        logger.info(
            "ai_call provider=%s model=%s tier=%s mode=text message_count=%s",
            self.name,
            profile.model,
            profile.tier,
            len(messages),
        )
        try:
            completion, latency_ms, trace_metadata = self._chat_completion(
                profile,
                workflow,
                messages,
            )
            self.last_call_metadata = completion_metadata(
                self.name,
                profile,
                completion,
                latency_ms,
            )
            self.last_call_metadata.update(prompt_metadata or {})
            self.last_call_metadata.update(trace_metadata)
            return completion.choices[0].message.content
        except OpenAIError as exc:
            error_code = openai_error_code(exc)
            log_ai_call_failure(
                self.name,
                self.model,
                "text",
                error_code,
                exc,
            )
            raise AIServiceError(
                "AI provider failed to return text",
                error_code=error_code,
            ) from exc

    def _chat_completion(self, profile, workflow, messages, response_format=None, tools=None):
        """Call Chat Completions with optional Langfuse tracing metadata."""
        call_kwargs = {
            "model": profile.model,
            "messages": messages,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
        }
        if response_format:
            call_kwargs["response_format"] = response_format
        if tools:
            call_kwargs["tools"] = list(tools)
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(openai_langfuse_kwargs(workflow, profile))

        started_at = call_timer()
        with langfuse_observation(workflow, profile) as observation:

            def _call_completion():
                """Execute the OpenAI chat completion request."""
                return self._client_for_profile(profile).chat.completions.create(
                    **call_kwargs,
                )

            runner = observation.get("runner") if observation else None
            if runner:
                completion = runner(_call_completion)
            else:
                completion = _call_completion()

        return (
            completion,
            elapsed_ms(started_at),
            normalize_observation_metadata(observation),
        )


def _parse_tool_calls(raw_calls):
    """Return normalized ``ToolCall`` objects from a provider message."""
    calls = []
    for index, raw in enumerate(raw_calls or []):
        function = _get_value(raw, "function", None)
        name = str(_get_value(function, "name", "") or "").strip()
        if not name:
            continue
        raw_arguments = _get_value(function, "arguments", "{}")
        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            try:
                arguments = json.loads(raw_arguments or "{}")
            except (TypeError, ValueError):
                arguments = {}
        call_id = str(_get_value(raw, "id", "") or f"call-{index + 1}")
        calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _get_value(source, key, default=None):
    """Return an attribute or mapping value from a provider object."""
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def get_ai_provider():
    """Return the configured AI provider with mock fallback."""
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


def ai_provider_fallback_reason(config=None):
    """Return why the configured provider would fall back to mock, if any."""
    config = config or current_app.config
    provider_name = _configured_provider_name(config)
    if provider_name == "mock":
        return ""
    if provider_name == "openai":
        return "" if ai_api_key_configured(config) else "api_key_missing"
    if provider_name == "openai_compatible":
        if not ai_api_key_configured(config):
            return "api_key_missing"
        if not _configured_base_url(config):
            return "base_url_missing"
        return ""
    return "unsupported_provider"


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


def provider_fallback_error_message(reason):
    """Return a safe user-facing configuration message for provider fallback."""
    if reason == "base_url_missing":
        return "AI_BASE_URL is required for AI_PROVIDER=openai_compatible"
    if reason == "unsupported_provider":
        return "AI_PROVIDER is not supported by a dedicated adapter yet"
    return "OPENAI_API_KEY is not configured in .env"


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


def _contains_any(text, needles):
    """Return whether text contains any of the provided needles."""
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _extract_machine(text):
    """Extract a simple machine label from free text."""
    match = re.search(r"(maschine|anlage)\s*[\w-]+", text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return "Unbekannte Maschine"


def _department_from_text(text, user_context=None):
    """Infer a responsible department from text or user context."""
    lowered = text.lower()
    if _contains_any(lowered, ["lager", "geraeusch", "leck", "motor", "sensor"]):
        return "Instandhaltung"
    if user_context and user_context.get("department"):
        return user_context["department"]
    return "Produktion"


def _cause_from_text(text):
    """Infer a plausible cause from free text."""
    lowered = text.lower()
    if "sensor" in lowered:
        return "Sensor verschmutzt, falsch ausgerichtet oder Kabelverbindung gestoert."
    if "lager" in lowered or "geraeusch" in lowered:
        return "Lager verschlissen, Schmierung unzureichend oder mechanische Unwucht."
    if "leck" in lowered or "druck" in lowered:
        return "Leckage, Dichtung defekt oder Druckversorgung instabil."
    return "Ursache noch unklar; strukturierte Sichtpruefung erforderlich."


def _short_title(text, prefix):
    """Create a short German title from free text."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return f"{prefix} erforderlich"
    return f"{prefix}: {cleaned[:80]}"


def _score_task_priority(task):
    """Return a local priority score for a serialized task."""
    score = 0
    reasons = []
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()

    priority_score, priority_reason = _priority_score(task.get("priority"))
    score += priority_score
    reasons.append(priority_reason)

    history_score, history_reason = _history_score(task.get("history"))
    score += history_score
    if history_reason:
        reasons.append(history_reason)

    due_score, due_reason = _due_date_score(task.get("due_date"))
    score += due_score
    if due_reason:
        reasons.append(due_reason)

    status_score, status_reason = _status_score(task.get("status"))
    score += status_score
    reasons.append(status_reason)

    keyword_score, keyword_reason = _keyword_score(text)
    score += keyword_score
    if keyword_reason:
        reasons.append(keyword_reason)

    normalized_score = max(0, min(100, score))
    risk_level = _risk_level(normalized_score)
    return {
        "task_id": task.get("id"),
        "score": normalized_score,
        "risk_level": risk_level,
        "reason": "; ".join(reasons[:4]),
        "recommended_action": _recommended_priority_action(risk_level, task.get("history")),
    }


def _priority_score(priority):
    """Return score contribution and reason for a task priority."""
    if priority == "urgent":
        return 45, "Prioritaet urgent"
    if priority == "soon":
        return 30, "Prioritaet soon"
    return 15, "Prioritaet normal"


def _status_score(status):
    """Return score contribution and reason for a task status."""
    if status == "in_progress":
        return 15, "Task ist bereits in Arbeit"
    if status == "open":
        return 10, "Task ist offen"
    return 0, f"Status {status or 'unbekannt'}"


def _due_date_score(due_date_value):
    """Return score contribution and reason for the due date."""
    if not due_date_value:
        return 0, ""
    try:
        days_until_due = (date.fromisoformat(due_date_value) - date.today()).days
    except ValueError:
        return 0, ""

    if days_until_due < 0:
        return 25, "Faelligkeit ist ueberfaellig"
    if days_until_due == 0:
        return 18, "Faelligkeit ist heute"
    if days_until_due <= 2:
        return 10, "Faelligkeit innerhalb von zwei Tagen"
    if days_until_due <= 7:
        return 5, "Faelligkeit innerhalb einer Woche"
    return 0, ""


def _keyword_score(text):
    """Return score contribution and reason for risk keywords."""
    keyword_groups = [
        (
            ["not-halt", "stillstand", "ausfall", "steht"],
            25,
            "kritischer Anlagenzustand",
        ),
        (["leck", "druck", "hydraulik", "pneumatik"], 18, "Leckage oder Druckproblem"),
        (["sensor", "lichttaster", "signal"], 12, "Sensorik betroffen"),
        (["lager", "geraeusch", "motor", "unwucht"], 10, "mechanische Symptome"),
    ]
    for keywords, score, reason in keyword_groups:
        if _contains_any(text, keywords):
            return score, reason
    return 0, ""


def _history_score(history):
    """Return score contribution and reason from maintenance history context."""
    if not isinstance(history, dict):
        return 0, ""

    score = 0
    signals = set(history.get("risk_signals") or [])
    related_errors = history.get("recent_related_errors") or []
    related_error_count = _safe_int(history.get("related_error_count"))
    reports_count = _safe_int(history.get("maintenance_reports_count"))
    reopened_count = _safe_int(history.get("reopened_count"))
    reasons = []

    if history.get("blocked"):
        score += 20
        reasons.append("Task ist blockiert")
    if reopened_count:
        score += min(15, reopened_count * 5)
        reasons.append(f"{reopened_count} Wiedereroeffnung(en)")
    if related_error_count:
        score += min(20, related_error_count * 8)
        reasons.append(f"{related_error_count} verwandte Stoerung(en)")
    if "critical_error_history" in signals:
        score += 12
        reasons.append("kritische Fehlerhistorie")
    if "recurring_error_history" in signals:
        score += 8
        reasons.append("wiederkehrende Fehlerhistorie")
    if "downtime_history" in signals:
        score += 6
        reasons.append("Ausfallzeit in Historie")
    if reports_count:
        score += min(8, reports_count * 4)
        reasons.append(f"{reports_count} Wartungsbericht(e)")

    highest_severity = _highest_related_error_severity(related_errors)
    if highest_severity and highest_severity not in {"low", "medium"}:
        reasons.append(f"hoechste Stoerungsschwere {highest_severity}")

    if not reasons:
        return 0, ""
    return score, "Historie: " + ", ".join(reasons[:3])


def _safe_int(value):
    """Return an integer value for scoring or zero for malformed input."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _highest_related_error_severity(errors):
    """Return the highest severity label from related error payloads."""
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    severities = [
        str(error.get("severity") or "").lower() for error in errors if isinstance(error, dict)
    ]
    if not severities:
        return ""
    return max(severities, key=lambda severity: severity_order.get(severity, 0))


def _risk_level(score):
    """Return the risk level for a numeric task score."""
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _recommended_priority_action(risk_level, history=None):
    """Return a German next-action recommendation for a risk level."""
    signals = set(history.get("risk_signals") or []) if isinstance(history, dict) else set()
    if "critical_error_history" in signals or "downtime_history" in signals:
        return (
            "Vor Start Stoerungshistorie pruefen, Anlage absichern und "
            "naechste Massnahme dokumentieren."
        )
    if history and history.get("blocked"):
        return "Blocker klaeren, Verantwortliche informieren und Termin neu bewerten."
    actions = {
        "critical": "Sofort pruefen, Anlage sichern und Instandhaltung informieren.",
        "high": "Zeitnah einplanen und Ursache vor Schichtende dokumentieren.",
        "medium": "Im Tagesplan beruecksichtigen und Befund erfassen.",
        "low": "Nach aktuellen dringenden Tasks bearbeiten.",
    }
    return actions[risk_level]
