"""Tool-selection evaluation harness for the maintenance agent.

Golden cases map a user message to the tool the agent is expected to call
first. The harness runs the provider's tool selection against the tool
schemas visible to a user and reports accuracy plus per-case outcomes.
Persisted output stays metadata-only: no raw answers, only tool names.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.tools import available_tools, provider_tool_schemas
from app.services.ai_service import AIServiceError, get_ai_provider

GOLDEN_TOOL_CASES = (
    {"message": "Welche offenen Tasks gibt es heute?", "expected_tool": "search_tasks"},
    {
        "message": "Was bedeutet Fehler INS-E-103 an Hydraulikpresse 03?",
        "expected_tool": "error_assistant",
    },
    {
        "message": "Presse 3 verliert Hydraulikdruck, Stoerung seit heute",
        "expected_tool": "error_assistant",
    },
    {
        "message": "Welche Materialien sind unter Mindestbestand?",
        "expected_tool": "search_inventory",
    },
    {
        "message": "Was steht im Handbuch zur Hydraulikpresse bei Druckverlust?",
        "expected_tool": "search_documents",
    },
    {
        "message": "Wie ist der Status von Maschine Spritzgussanlage 04?",
        "expected_tool": "get_machine_overview",
    },
    {
        "message": "Priorisiere die offenen Aufgaben nach Risiko",
        "expected_tool": "prioritize_tasks",
    },
    {"message": "Gib mir das Briefing fuer heute", "expected_tool": "daily_briefing"},
    {"message": "Task anlegen: Dichtung an Presse 3 tauschen", "expected_tool": "create_task"},
    {
        "message": "Mach mir einen Vorschlag fuer einen Task zur Schmierung",
        "expected_tool": "draft_task",
    },
    {
        "message": "Plane einen Auftrag fuer 500 Stueck Gehaeuse auf einer Maschine",
        "expected_tool": "plan_order",
    },
    {
        "message": "Was wurde in der letzten Schicht uebergeben?",
        "expected_tool": "search_shift_handovers",
    },
    {
        "message": "Welche Mitarbeiter haben die Qualifikation Hydraulik?",
        "expected_tool": "search_employees",
    },
    {
        "message": "Wie tausche ich den Filter laut Wartungswissen?",
        "expected_tool": "search_knowledge",
    },
)


@dataclass(frozen=True)
class ToolSelectionOutcome:
    """Result of one golden tool-selection case."""

    message: str
    expected_tool: str
    selected_tool: str
    correct: bool
    error: str = ""

    def to_dict(self):
        """Return a JSON-safe outcome without raw model output."""
        return {
            "message": self.message,
            "expected_tool": self.expected_tool,
            "selected_tool": self.selected_tool,
            "correct": self.correct,
            "error": self.error,
        }


def evaluate_tool_selection(user, cases=None, provider=None):
    """Return accuracy and per-case outcomes for tool selection."""
    provider = provider or get_ai_provider()
    tools = available_tools(user)
    schemas = provider_tool_schemas(tools)
    available_names = {spec.name for spec in tools}
    outcomes = []
    for case in cases or GOLDEN_TOOL_CASES:
        expected = str(case.get("expected_tool") or "")
        message = str(case.get("message") or "")
        if expected not in available_names:
            outcomes.append(
                ToolSelectionOutcome(message, expected, "", False, error="tool_not_available")
            )
            continue
        try:
            response = provider.chat_with_tools(
                [{"role": "user", "content": message}],
                schemas,
                workflow="agent",
            )
            selected = response.tool_calls[0].name if response.tool_calls else ""
            error = ""
        except AIServiceError as exc:
            selected = ""
            error = exc.error_code
        outcomes.append(
            ToolSelectionOutcome(message, expected, selected, selected == expected, error=error)
        )
    correct = sum(1 for outcome in outcomes if outcome.correct)
    total = len(outcomes)
    return {
        "provider": getattr(provider, "name", "unknown"),
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "tool_count": len(tools),
        "outcomes": [outcome.to_dict() for outcome in outcomes],
        "misses": [outcome.to_dict() for outcome in outcomes if not outcome.correct],
    }
