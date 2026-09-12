"""Agent tool registry built on the existing permission-aware services.

Every tool wraps a service function that already enforces visibility and
permissions. The registry adds three things on top:

- a stable JSON schema so the model can call the tool,
- an explicit permission gate evaluated against the calling user,
- prompt-safe, size-bounded results with public source cards.

Write tools are marked ``requires_confirmation``. They never execute from the
model loop directly; they return a signed pending action that the user has to
confirm through ``POST /api/v1/ai/agent/confirm``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.permissions import can_read_employee_context
from app.security import has_dashboard_permission

logger = logging.getLogger(__name__)

MAX_ITEMS = 10
MAX_TEXT_CHARS = 320
MAX_CONTEXT_CHARS = 6000
MAX_ARGUMENT_CHARS = 2000
FORBIDDEN_RESULT_KEYS = {
    "internal_note",
    "internal_notes",
    "notes",
    "private_notes",
    "password",
    "password_hash",
    "relative_path",
    "file_path",
    "storage_path",
    "diagnostics_json",
    "raw",
    "prompt",
}
SCOPE_SEARCH_TOOLS = {
    "search_tasks": ("tasks", "Wartungsaufgaben (Tasks) mit Status, Prioritaet und Faelligkeit."),
    "search_errors": ("errors", "Fehlerkatalog und Stoerungen inklusive Ursachen und Loesungen."),
    "search_machines": ("machines", "Maschinen, Anlagenstatus und Wartungsplaene."),
    "search_inventory": ("inventory", "Lagerbestand, Ersatzteile und Mindestbestaende."),
    "search_documents": ("documents", "Wartungsberichte, Dokumente und Maschinenhandbuecher."),
    "search_shift_handovers": ("shiftplans", "Schichtplaene und Schichtuebergaben."),
    "search_employees": (
        "employees",
        "Mitarbeiterdaten und Qualifikationen (nur mit Personalfreigabe).",
    ),
}


@dataclass
class ToolResult:
    """Prompt-safe result of one tool execution."""

    content: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    status: str = "ok"
    error: str = ""

    def to_model_payload(self):
        """Return the JSON payload handed back to the model."""
        payload = {"status": self.status, "summary": self.summary}
        if self.error:
            payload["error"] = self.error
        payload.update(self.content)
        return payload


@dataclass(frozen=True)
class ToolSpec:
    """Declarative description of one agent tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., ToolResult]
    permission: tuple[str, str] | None = None
    scopes: tuple[str, ...] = ()
    requires_confirmation: bool = False
    write: bool = False
    label: str = ""

    def provider_schema(self):
        """Return the OpenAI-compatible function definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_dict(self):
        """Return a redacted public description of the tool."""
        return {
            "name": self.name,
            "label": self.label or self.name,
            "description": self.description,
            "parameters": self.parameters,
            "requires_confirmation": self.requires_confirmation,
            "write": self.write,
            "scopes": list(self.scopes),
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec):
    """Register one tool spec and return it."""
    TOOL_REGISTRY[spec.name] = spec
    return spec


def tool_spec(name):
    """Return one registered tool spec or ``None``."""
    return TOOL_REGISTRY.get(str(name or ""))


def user_can_use_tool(user, spec):
    """Return whether the user passes the tool's permission gate."""
    if spec.permission is None:
        return True
    dashboard, action = spec.permission
    if dashboard == "employees" and not can_read_employee_context(user):
        return False
    try:
        return has_dashboard_permission(user, dashboard, action)
    except ValueError:
        return False


def available_tools(user):
    """Return the tools the user may call, in registration order."""
    return [spec for spec in TOOL_REGISTRY.values() if user_can_use_tool(user, spec)]


def provider_tool_schemas(specs):
    """Return provider-ready function definitions for tool specs."""
    return [spec.provider_schema() for spec in specs]


def execute_tool(name, arguments, user, *, confirmed=False):
    """Execute a tool for a user with permission, argument and confirmation gates."""
    spec = tool_spec(name)
    if spec is None:
        return ToolResult(status="error", error=f"unknown_tool:{name}", summary="Unbekanntes Tool")
    if not user_can_use_tool(user, spec):
        return ToolResult(
            status="permission_denied",
            error="permission_denied",
            summary=f"Keine Berechtigung fuer {spec.label or spec.name}",
            content={"required_permission": list(spec.permission or [])},
        )
    try:
        safe_arguments = normalize_arguments(spec, arguments)
    except ValueError as exc:
        return ToolResult(status="error", error=f"invalid_arguments:{exc}", summary=str(exc))
    if spec.requires_confirmation and not confirmed:
        from app.agent.actions import create_pending_action

        pending = create_pending_action(user, spec, safe_arguments)
        return ToolResult(
            status="confirmation_required",
            summary=f"Bestaetigung erforderlich: {pending['label']}",
            content={"pending_action": pending},
        )
    started = perf_counter()
    try:
        result = spec.handler(user, safe_arguments)
    except Exception:  # pragma: no cover - defensive guard for tool failures
        logger.exception("agent_tool_failed tool=%s", spec.name)
        return ToolResult(
            status="error", error="tool_failed", summary="Tool-Ausfuehrung fehlgeschlagen"
        )
    result.content = _sanitize(result.content)
    result.content.setdefault("duration_ms", int((perf_counter() - started) * 1000))
    return result


def normalize_arguments(spec, arguments):
    """Validate arguments against the tool schema and coerce simple types."""
    payload = arguments if isinstance(arguments, dict) else {}
    properties = spec.parameters.get("properties") or {}
    required = spec.parameters.get("required") or []
    normalized = {}
    for key, schema in properties.items():
        if key not in payload or payload[key] is None:
            continue
        value = payload[key]
        expected = schema.get("type")
        if expected == "integer":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be an integer") from exc
        elif expected == "number":
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number") from exc
        elif expected == "boolean":
            value = str(value).strip().lower() in {"1", "true", "yes", "on"}
        else:
            value = str(value).strip()[:MAX_ARGUMENT_CHARS]
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{key} must be one of {', '.join(map(str, schema['enum']))}")
        normalized[key] = value
    missing = [key for key in required if not normalized.get(key)]
    if missing:
        raise ValueError(f"missing required arguments: {', '.join(missing)}")
    return normalized


# ---------------------------------------------------------------------------
# Result shaping helpers
# ---------------------------------------------------------------------------


def _sanitize(value, depth=0):
    """Return a JSON-safe, size-bounded copy without forbidden keys."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item, depth + 1)
            for key, item in value.items()
            if str(key) not in FORBIDDEN_RESULT_KEYS
        }
    if isinstance(value, list | tuple | set):
        return [_sanitize(item, depth + 1) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, str):
        return value if len(value) <= MAX_CONTEXT_CHARS else value[:MAX_CONTEXT_CHARS]
    if isinstance(value, bool | int | float) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:MAX_TEXT_CHARS]


def compact_record(record, limit=MAX_TEXT_CHARS):
    """Return only scalar fields of a serialized record with bounded strings."""
    if not isinstance(record, dict):
        return {}
    compact = {}
    for key, value in record.items():
        if key in FORBIDDEN_RESULT_KEYS:
            continue
        if isinstance(value, str):
            compact[key] = value if len(value) <= limit else value[:limit] + "..."
        elif isinstance(value, bool | int | float) or value is None:
            compact[key] = value
        elif isinstance(value, dict) and "name" in value:
            compact[key] = value.get("name")
    return compact


def compact_records(records, limit=MAX_ITEMS):
    """Return compact records for a list of serialized rows."""
    return [compact_record(record) for record in list(records or [])[:limit]]


def compact_sources(sources, limit=MAX_ITEMS):
    """Return public source cards limited to prompt-safe fields."""
    allowed = {
        "type",
        "source_type",
        "id",
        "source_id",
        "title",
        "module",
        "url",
        "machine",
        "machine_id",
        "error_code",
        "document_id",
        "chunk_id",
        "quality_status",
        "score",
        "normalized_score",
        "created_at",
        "count",
    }
    cards = []
    for source in list(sources or [])[:limit]:
        if not isinstance(source, dict):
            continue
        cards.append({key: source[key] for key in allowed if key in source})
    return cards


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


def _scoped_search_handler(scope):
    """Return a handler that searches one dashboard scope through structured retrieval."""

    def handler(user, arguments):
        from app.services.ai_retrieval import retrieve_ai_context

        query = arguments["query"]
        retrieval = retrieve_ai_context(query, user, {scope})
        data = retrieval.get("data") or {}
        items = []
        for key, rows in data.items():
            if isinstance(rows, list):
                items.extend({"kind": key, **compact_record(row)} for row in rows)
        status_filter = str(arguments.get("status") or "").strip().lower()
        if status_filter:
            items = [
                item for item in items if str(item.get("status") or "").lower() == status_filter
            ]
        items = items[:MAX_ITEMS]
        sources = compact_sources(retrieval.get("sources") or [])
        return ToolResult(
            content={"scope": scope, "items": items, "item_count": len(items)},
            sources=sources,
            summary=f"{len(items)} Treffer in {scope}",
        )

    return handler


for _tool_name, (_scope, _description) in SCOPE_SEARCH_TOOLS.items():
    register_tool(
        ToolSpec(
            name=_tool_name,
            label=_tool_name.replace("_", " ").title(),
            description=(
                f"Durchsucht {_description} Nur sichtbare, freigegebene Datensaetze. "
                "Nutze eine kurze Suchanfrage mit Maschine, Code oder Stichwort."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Suchanfrage oder Stichwoerter."},
                    "status": {
                        "type": "string",
                        "description": "Optionaler Statusfilter, z. B. open, in_progress, done.",
                    },
                },
                "required": ["query"],
            },
            handler=_scoped_search_handler(_scope),
            permission=(_scope, "view"),
            scopes=(_scope,),
        )
    )


def _search_knowledge(user, arguments):
    """Search indexed knowledge chunks (manuals, reports, training entries)."""
    from app.services.retrieval_service import knowledge_context_for_chat

    context, sources = knowledge_context_for_chat(arguments["query"], user)
    context_text = str(context or "")[:MAX_CONTEXT_CHARS]
    cards = compact_sources(sources)
    return ToolResult(
        content={"context": context_text, "sources": cards, "source_count": len(cards)},
        sources=cards,
        summary=f"{len(cards)} Wissensquellen gefunden",
    )


register_tool(
    ToolSpec(
        name="search_knowledge",
        label="Wissenssuche",
        description=(
            "Semantische Suche in indexiertem Wartungswissen: Handbuecher, Berichte, "
            "Fehlerkatalog-Wissen und Trainingseintraege. Liefert Kontexttext mit Quellen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Frage oder Stichwoerter."},
            },
            "required": ["query"],
        },
        handler=_search_knowledge,
        scopes=("documents",),
    )
)


def _resolve_machine(user, reference):
    """Return a visible machine by id or (partial) name."""
    from app.models import Machine
    from app.services.visibility_query_service import visible_machines_query

    query = visible_machines_query(user)
    text = str(reference or "").strip()
    if text.isdigit():
        machine = query.filter(Machine.id == int(text)).first()
        if machine:
            return machine
    exact = query.filter(Machine.name.ilike(text)).first()
    if exact:
        return exact
    return query.filter(Machine.name.ilike(f"%{text}%")).order_by(Machine.name.asc()).first()


def _machine_overview(user, arguments):
    """Return a compact machine profile with open work, errors, plans and materials."""
    from app.machines.services import build_machine_profile

    machine = _resolve_machine(user, arguments["machine"])
    if machine is None:
        return ToolResult(
            status="not_found",
            error="machine_not_found",
            summary="Keine sichtbare Maschine gefunden",
            content={"machine": arguments["machine"]},
        )
    profile = build_machine_profile(machine, user)
    content = {
        "machine": compact_record(profile.get("machine") or {}),
        "kpis": compact_record(profile.get("kpis") or {}),
        "open_tasks": compact_records(profile.get("open_tasks"), 5),
        "active_errors": compact_records(profile.get("active_errors"), 5),
        "maintenance_plans": compact_records(profile.get("maintenance_plans"), 5),
        "materials": compact_records(profile.get("materials"), 5),
        "shift_handovers": compact_records(profile.get("shift_handovers"), 3),
    }
    source = {
        "type": "machine",
        "id": machine.id,
        "title": machine.name,
        "module": "machines",
        "url": f"/machines/{machine.id}",
    }
    return ToolResult(content=content, sources=[source], summary=f"Profil fuer {machine.name}")


register_tool(
    ToolSpec(
        name="get_machine_overview",
        label="Maschinenprofil",
        description=(
            "Liefert das Profil einer Maschine: Status, KPIs, offene Tasks, aktive "
            "Stoerungen, Wartungsplaene, Material und letzte Uebergaben."
        ),
        parameters={
            "type": "object",
            "properties": {
                "machine": {"type": "string", "description": "Maschinenname oder ID."},
            },
            "required": ["machine"],
        },
        handler=_machine_overview,
        permission=("machines", "view"),
        scopes=("machines", "tasks", "errors"),
    )
)


def _error_assistant(user, arguments):
    """Return catalog matches, causes, fixes and a root-cause analysis."""
    from app.services.error_assistant_service import run_error_assistant

    result, error, status = run_error_assistant({"query": arguments["query"]}, user)
    if error:
        return ToolResult(status="error", error=str(error.get("error") or status), summary="Fehler")
    matches = [
        {
            "score": match.get("score"),
            "reason": match.get("reason"),
            **compact_record(match.get("entry") or {}),
        }
        for match in list(result.get("matches") or [])[:5]
        if isinstance(match, dict)
    ]
    rca = result.get("root_cause_analysis") or {}
    content = {
        "matches": matches,
        "causes": [str(item)[:MAX_TEXT_CHARS] for item in list(result.get("causes") or [])[:5]],
        "fixes": [str(item)[:MAX_TEXT_CHARS] for item in list(result.get("fixes") or [])[:5]],
        "root_cause_confidence": compact_record(rca.get("confidence") or {}),
        "next_steps": compact_records(rca.get("next_steps"), 5),
    }
    sources = compact_sources(
        [
            {
                "type": "error",
                "id": match.get("id"),
                "title": match.get("title"),
                "error_code": match.get("error_code"),
                "machine": match.get("machine"),
                "module": "errors",
            }
            for match in matches
        ]
        + list((rca.get("evidence") or {}).get("rag_sources") or [])
    )
    return ToolResult(content=content, sources=sources, summary=f"{len(matches)} Katalogtreffer")


register_tool(
    ToolSpec(
        name="error_assistant",
        label="Stoerungsassistent",
        description=(
            "Analysiert eine Stoerungsbeschreibung oder einen Fehlercode gegen den "
            "Fehlerkatalog und liefert Ursachen, Massnahmen und eine Ursachenanalyse."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Stoerungsbeschreibung, Fehlercode und Maschine.",
                },
            },
            "required": ["query"],
        },
        handler=_error_assistant,
        permission=("errors", "view"),
        scopes=("errors",),
    )
)


def _draft_task(user, arguments):
    """Return a non-persisted task draft from free text."""
    from app.services.task_service import suggest_task_from_text

    suggestion, error, status = suggest_task_from_text({"text": arguments["text"]}, user)
    if error:
        return ToolResult(status="error", error=str(error.get("error") or status), summary="Fehler")
    sources = compact_sources(suggestion.get("sources") or [])
    draft = compact_record(suggestion)
    return ToolResult(
        content={"draft": draft, "persisted": False},
        sources=sources,
        summary=f"Task-Entwurf: {draft.get('title', '')}",
    )


register_tool(
    ToolSpec(
        name="draft_task",
        label="Task-Entwurf",
        description=(
            "Erstellt aus Freitext einen Wartungs-Task-Entwurf (Titel, Prioritaet, "
            "Massnahme). Speichert nichts; zum Anlegen create_task nutzen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Beschreibung der Arbeit."},
            },
            "required": ["text"],
        },
        handler=_draft_task,
        permission=("tasks", "write"),
        scopes=("tasks",),
    )
)


def _prioritize_tasks(user, arguments):
    """Return read-only priority scores for visible tasks."""
    from app.services.task_service import prioritize_visible_tasks

    payload = {"limit": arguments.get("limit") or 10}
    if arguments.get("status"):
        payload["status"] = arguments["status"]
    priorities, error, status = prioritize_visible_tasks(payload, user)
    if error:
        return ToolResult(status="error", error=str(error.get("error") or status), summary="Fehler")
    items = compact_records(priorities, MAX_ITEMS)
    sources = compact_sources(
        [
            {
                "type": "task",
                "id": item.get("task_id"),
                "title": item.get("title"),
                "module": "tasks",
            }
            for item in items
            if item.get("task_id")
        ]
    )
    return ToolResult(
        content={"priorities": items, "count": len(items)},
        sources=sources,
        summary=f"{len(items)} Tasks priorisiert",
    )


register_tool(
    ToolSpec(
        name="prioritize_tasks",
        label="Task-Priorisierung",
        description=(
            "Bewertet sichtbare Tasks nach Risiko, Faelligkeit und Historie und "
            "liefert eine Rangfolge mit Begruendung."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optionaler Statusfilter (open, in_progress).",
                },
                "limit": {"type": "integer", "description": "Maximale Anzahl (1-20)."},
            },
            "required": [],
        },
        handler=_prioritize_tasks,
        permission=("tasks", "view"),
        scopes=("tasks",),
    )
)


def _plan_order(user, arguments):
    """Return a production order planning preview."""
    from app.services.order_planning_service import plan_order

    payload = {"product": arguments["product"], "quantity": arguments["quantity"]}
    if arguments.get("due_date"):
        payload["due_date"] = arguments["due_date"]
    plan, error, status = plan_order(payload, user)
    if error:
        tool_status = "permission_denied" if status == 403 else "error"
        return ToolResult(
            status=tool_status,
            error=str(error.get("error") or status),
            summary=str(error.get("message") or error.get("error") or "Planung fehlgeschlagen"),
        )
    recommended = plan.get("recommended_plan") or {}
    content = {
        "summary": str(plan.get("summary") or "")[:MAX_CONTEXT_CHARS],
        "recommended_plan": _sanitize(recommended),
        "alternatives": _sanitize(plan.get("alternatives") or []),
    }
    return ToolResult(
        content=content,
        sources=compact_sources(plan.get("sources") or []),
        summary="Auftragsplanung erstellt",
    )


register_tool(
    ToolSpec(
        name="plan_order",
        label="Auftragsplanung",
        description=(
            "Plant einen Produktionsauftrag: passende Maschine, Materialpruefung und "
            "Personalbedarf fuer ein Produkt und eine Stueckzahl."
        ),
        parameters={
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Produkt oder Artikel."},
                "quantity": {"type": "integer", "description": "Stueckzahl."},
                "due_date": {"type": "string", "description": "Optionales Datum (YYYY-MM-DD)."},
            },
            "required": ["product", "quantity"],
        },
        handler=_plan_order,
        permission=("machines", "view"),
        scopes=("machines", "inventory", "employees"),
    )
)


def _daily_briefing(user, arguments):
    """Return today's briefing sections for the user."""
    from app.ai.briefings import daily_briefing

    briefing = daily_briefing(user)
    sections = []
    for section in list(briefing.get("sections") or [])[:8]:
        if not isinstance(section, dict):
            continue
        compact = {key: value for key, value in compact_record(section).items()}
        items = section.get("items") or section.get("entries") or []
        if isinstance(items, list):
            compact["items"] = [
                compact_record(item) if isinstance(item, dict) else str(item)[:MAX_TEXT_CHARS]
                for item in items[:5]
            ]
        sections.append(compact)
    return ToolResult(
        content={
            "date": briefing.get("date"),
            "summary": briefing.get("summary"),
            "sections": sections,
        },
        summary=str(briefing.get("summary") or "Briefing erstellt"),
    )


register_tool(
    ToolSpec(
        name="daily_briefing",
        label="Tagesbriefing",
        description="Liefert das heutige Wartungsbriefing mit wichtigen Hinweisen pro Bereich.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_daily_briefing,
        scopes=("tasks", "errors", "inventory", "documents"),
    )
)


# ---------------------------------------------------------------------------
# Write tools (confirmation required)
# ---------------------------------------------------------------------------


def _create_task(user, arguments):
    """Persist a new task after explicit user confirmation."""
    from app.services.task_service import create_task

    payload = {
        "title": arguments["title"],
        "description": arguments.get("description") or "",
        "priority": arguments.get("priority") or "normal",
    }
    if arguments.get("due_date"):
        payload["due_date"] = arguments["due_date"]
    if arguments.get("department"):
        payload["department"] = arguments["department"]
    task, error, status = create_task(payload, user)
    if error:
        tool_status = "permission_denied" if status == 403 else "error"
        return ToolResult(
            status=tool_status, error=str(error.get("error") or status), summary="Fehler"
        )
    record = compact_record(task.to_dict())
    return ToolResult(
        content={"task": record, "persisted": True},
        sources=[{"type": "task", "id": task.id, "title": task.title, "module": "tasks"}],
        summary=f"Task #{task.id} angelegt: {task.title}",
    )


register_tool(
    ToolSpec(
        name="create_task",
        label="Task anlegen",
        description=(
            "Legt einen neuen Wartungs-Task an. Die Ausfuehrung braucht eine explizite "
            "Bestaetigung des Nutzers; das Tool liefert zuerst eine Vorschau."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Kurzer Task-Titel."},
                "description": {"type": "string", "description": "Beschreibung der Arbeit."},
                "priority": {
                    "type": "string",
                    "enum": ["urgent", "soon", "normal"],
                    "description": "Prioritaet.",
                },
                "due_date": {"type": "string", "description": "Faelligkeit (YYYY-MM-DD)."},
                "department": {
                    "type": "string",
                    "description": "Abteilung; Standard ist die eigene Abteilung des Nutzers.",
                },
            },
            "required": ["title"],
        },
        handler=_create_task,
        permission=("tasks", "write"),
        scopes=("tasks",),
        requires_confirmation=True,
        write=True,
    )
)


def _request_knowledge_reindex(user, arguments):
    """Queue a RAG reindex job after explicit confirmation."""
    from app.services.background_job_service import enqueue_rag_reindex_job

    mode = arguments.get("mode") or "stale"
    job = enqueue_rag_reindex_job(mode=mode, user=user)
    record = compact_record(job.to_dict())
    return ToolResult(
        content={"job": record, "mode": mode},
        summary=f"Reindex-Job #{job.id} ({mode}) eingeplant",
    )


register_tool(
    ToolSpec(
        name="request_knowledge_reindex",
        label="Wissen neu indexieren",
        description=(
            "Plant einen Hintergrundjob, der veraltete oder alle Wissensdokumente neu "
            "indexiert. Nur fuer KI-Administration, mit Bestaetigung."
        ),
        parameters={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["stale", "all"],
                    "description": "stale = nur veraltete Dokumente, all = komplett.",
                },
            },
            "required": [],
        },
        handler=_request_knowledge_reindex,
        permission=("admin_ai", "write"),
        scopes=("documents",),
        requires_confirmation=True,
        write=True,
    )
)
