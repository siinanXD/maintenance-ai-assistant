"""Tests for grounded AI prompt construction."""

from app.services.ai_prompting import build_json_prompt, build_text_messages, text_system_prompt
from app.services.ai_provider_openai import OpenAIProvider
from app.services.document_text_service import summarize_text


def test_text_system_prompt_requires_grounded_source_based_answers():
    """Verify chat prompts explicitly discourage unsupported maintenance answers."""
    prompt = text_system_prompt()

    assert "Maintenance-AI-Assistent für industrielle Instandhaltung" in prompt
    assert '"Keine belastbare Quelle gefunden."' in prompt
    assert "- Antwort:" in prompt
    assert "- Quelle:" in prompt
    assert "- Unsicherheit: niedrig / mittel / hoch" in prompt
    assert "8. Nutze nur Informationen aus Quellen mit ausreichender Relevanz." in prompt
    assert "9. Ignoriere irrelevante Kontextteile." in prompt
    assert "10. Priorisiere neuere Informationen gegenüber älteren." in prompt
    assert "[Quelle: Fehlerkatalog | ID: 42 | Maschine: Presse 3 | Datum: 2026-05-20]" in prompt
    assert "[Quelle: Task | ID: 18 | Status: offen | Priorität: dringend]" in prompt
    assert "Quelle-/Chunk-/Dokumenthinweis" not in prompt


def test_build_text_messages_keeps_context_and_question_separated():
    """Verify answer prompts preserve a clear context/question boundary."""
    messages = build_text_messages(
        "Was bedeutet Fehler E204?",
        "Quelle: Wissen #7 - Fehlerkatalog\nChunk-ID: 12\nFehler E204: Sensor pruefen.",
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Kontext:" in messages[1]["content"]
    assert "Frage:" in messages[1]["content"]
    assert "Chunk-ID: 12" in messages[1]["content"]


def test_build_text_messages_accepts_query_specific_rules():
    """Verify retrieval strategy rules are included in the system prompt."""
    messages = build_text_messages(
        "Was ist die Ursache?",
        "Quelle: Wissen #7",
        extra_rules="Trenne dokumentierte Ursache und empfohlene Massnahme klar.",
    )

    assert "Trenne dokumentierte Ursache" in messages[0]["content"]
    assert '"Keine belastbare Quelle gefunden."' in messages[0]["content"]


def test_build_json_prompt_accepts_instruction_alias():
    """Verify JSON prompts can be built with an instruction keyword."""
    prompt = build_json_prompt(
        instruction="Pruefe einen Bericht.",
        schema={"status": "string"},
    )

    assert prompt["task"] == "Pruefe einen Bericht."
    assert prompt["schema"] == {"status": "string"}


def test_document_review_prompt_requires_technical_usability(app, monkeypatch):
    """Verify document review uses the stricter maintenance report prompt."""
    captured = {}

    def _capture_completion(self, prompt, workflow):
        """Capture the prompt instead of calling OpenAI."""
        captured["prompt"] = prompt
        captured["workflow"] = workflow
        return {}

    monkeypatch.setattr(OpenAIProvider, "_json_completion", _capture_completion)
    with app.app_context():
        provider = OpenAIProvider(api_key="test-key", model="test-model")
        provider.review_document("<p>Bericht</p>", {"title": "Testbericht"})

    prompt = captured["prompt"]
    assert captured["workflow"] == "document_review"
    assert "technische Verwertbarkeit" in prompt["task"]
    assert prompt["schema"]["findings"][0]["field"] == (
        "machine|cause|action|result|notes|metadata"
    )
    assert "Bewerte nur den bereitgestellten Wartungsbericht." in prompt["rules"]
    assert "Erfinde keine fehlenden Inhalte." in prompt["rules"]
    assert "Setze quality_score niedrig" in " ".join(prompt["rules"])


def test_error_assistant_prompt_uses_catalog_context(app, monkeypatch):
    """Verify error assistant prompts are grounded in ranked catalog matches."""
    captured = {}

    def _capture_completion(self, prompt, workflow):
        """Capture the prompt instead of calling OpenAI."""
        captured["prompt"] = prompt
        captured["workflow"] = workflow
        return {}

    monkeypatch.setattr(OpenAIProvider, "_json_completion", _capture_completion)
    with app.app_context():
        provider = OpenAIProvider(api_key="test-key", model="test-model")
        provider.error_assistant_query(
            "Presse 3 Fehler E42",
            [
                {
                    "score": 87,
                    "entry": {
                        "id": 42,
                        "machine": "Presse 3",
                        "possible_causes": "Sensor verschmutzt",
                        "solution": "Sensor reinigen",
                    },
                }
            ],
        )

    prompt = captured["prompt"]
    assert captured["workflow"] == "error_assistant"
    assert "passender Fehlerkatalog-Treffer" in prompt["task"]
    assert prompt["user_query"] == "Presse 3 Fehler E42"
    assert prompt["catalog_matches"][0]["source_id"] == 42
    assert prompt["catalog_matches"][0]["machine"] == "Presse 3"
    assert prompt["catalog_matches"][0]["relevance"] == 87
    assert prompt["schema"]["uncertainty"] == "niedrig|mittel|hoch"
    assert "Erfinde keine technischen Ursachen." in prompt["rules"]
    assert "Bevorzuge Treffer mit hoher Relevanz." in prompt["rules"]


def test_document_summary_prompt_uses_structured_json(monkeypatch):
    """Verify document summaries use structured technical JSON prompts."""
    captured = {}

    class FakeProvider:
        """Provider test double for structured document summaries."""

        name = "openai"

        def _json_completion(self, prompt, workflow):
            """Capture prompt data and return a structured summary."""
            captured["prompt"] = prompt
            captured["workflow"] = workflow
            return {
                "summary": "Presse 3 Wartung dokumentiert.",
                "key_findings": ["Sensor S4 gereinigt"],
                "risks": ["Restfehler unklar"],
                "next_steps": ["Testlauf ausfuehren"],
                "affected_machines": ["Presse 3"],
                "uncertainty": "mittel",
            }

    monkeypatch.setattr(
        "app.services.document_text_service.get_ai_provider",
        lambda: FakeProvider(),
    )

    summary, status = summarize_text(
        "Presse 3 Sensor S4 gereinigt. Testlauf fehlt.",
        metadata={"document_id": 7},
    )

    prompt = captured["prompt"]
    assert status == "openai_used"
    assert captured["workflow"] == "document_summary"
    assert "Wartungsdokument technisch zusammen" in prompt["task"]
    assert prompt["document_text"] == "Presse 3 Sensor S4 gereinigt. Testlauf fehlt."
    assert prompt["metadata"] == {"document_id": 7}
    assert prompt["schema"]["uncertainty"] == "niedrig|mittel|hoch"
    assert "Erfinde keine Risiken oder Fehler." in prompt["rules"]
    assert "Presse 3 Wartung dokumentiert." in summary
    assert "Kernaussagen:" in summary
    assert "Unsicherheit: mittel" in summary
