"""OpenAI and OpenAI-compatible chat provider with tool calls, JSON and text modes."""

import json
import logging

from openai import (
    OpenAIError,
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
    openai_client_options,
    workflow_profile,
)
from app.services.ai_service import (
    AIServiceError,
    BaseAIProvider,
    ToolCall,
    ToolCallResponse,
    log_ai_call_failure,
    openai_error_code,
)
from app.services.langfuse_service import (
    langfuse_observation,
    normalize_observation_metadata,
    openai_client_class,
    openai_langfuse_kwargs,
)

logger = logging.getLogger(__name__)


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
