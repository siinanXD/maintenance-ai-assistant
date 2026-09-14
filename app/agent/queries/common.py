"""Shared result envelope and formatting helpers for structured queries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app

from app.services.ai_prompting import permission_denied_answer

MAX_ANSWER_ITEMS = 10
MAX_LIST_ITEMS = 20
MAX_SHIFTPLAN_LIST_ITEMS = 30
STRUCTURED_CONTEXT_FIELD_KEYS = (
    "entity_type",
    "department",
    "status",
    "time_range",
    "machine",
    "query",
    "shift",
    "employee_id",
    "employee_name",
)
DASHBOARD_SCOPE_LABELS = {
    "tasks": "Tasks",
    "errors": "Fehlerkatalog",
    "employees": "Mitarbeiter",
    "machines": "Maschinen",
    "inventory": "Lager",
    "documents": "Dokumente",
    "shiftplans": "Schichtplanung",
    "admin_users": "Admin Users",
}


@dataclass
class QueryOutcome:
    """Deterministic, prompt-safe outcome of one structured query."""

    entity_type: str
    scope: str
    answer_markdown: str
    count: int = 0
    items: list = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    structured_context: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    denied: bool = False
    query: str = ""

    def summary(self):
        """Return a short trace line."""
        if self.denied:
            return f"Keine Berechtigung fuer {DASHBOARD_SCOPE_LABELS.get(self.scope, self.scope)}"
        return f"{self.count} Treffer ({self.entity_type})"


def denied_outcome(entity_type, scope, label=None):
    """Return a permission-denied outcome with the standard German answer."""
    return QueryOutcome(
        entity_type=entity_type,
        scope=scope,
        answer_markdown=permission_denied_answer(
            label or DASHBOARD_SCOPE_LABELS.get(scope, scope), scope
        ),
        denied=True,
        structured_context=build_structured_context(entity_type),
    )


def build_structured_context(entity_type, **fields):
    """Return a compact structured memory payload for chat diagnostics."""
    context = {"entity_type": str(entity_type or "").strip()}
    for key in STRUCTURED_CONTEXT_FIELD_KEYS:
        if key == "entity_type":
            continue
        value = fields.get(key)
        if value in (None, ""):
            continue
        context[key] = str(value).strip()[:120]
    if not context.get("entity_type"):
        return {}
    return context


def format_structured_list_answer(
    *,
    title: str,
    label: str,
    items: Sequence[Any],
    count_label: str,
    formatter: Callable[[Any], str],
    source: str = "Strukturierte Daten",
    total_count: int | None = None,
    overflow_suffix: str = "weitere Eintraege",
    empty_message: str = "Keine sichtbaren Eintraege fuer diese Anfrage gefunden.",
) -> str:
    """Return a compact German markdown list answer for structured rows."""
    visible_total = total_count if total_count is not None else len(items)
    lines = [
        f"## {title}",
        f"- **Filter:** {label}",
        f"- **{count_label}:** {visible_total}",
        f"- **Quelle:** {source}",
    ]
    if total_count is not None and total_count > len(items):
        lines.append(
            f"- **Hinweis:** {len(items)} von {total_count} sichtbaren Eintraegen angezeigt"
        )
    if not items:
        lines.append("")
        lines.append(empty_message)
        return "\n".join(lines)
    lines.append("")
    lines.append("Sichtbare Eintraege:")
    for item in items[:MAX_ANSWER_ITEMS]:
        lines.append(formatter(item))
    if len(items) > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {len(items) - MAX_ANSWER_ITEMS} {overflow_suffix}")
    return "\n".join(lines)


def aggregate_or_row_sources(row_sources, scope, count, user):
    """Return row source cards, or one aggregate module card when no rows exist."""
    from app.services.ai_structured_source_service import module_count_source_card

    if row_sources:
        return row_sources
    aggregate = module_count_source_card(scope, count, user)
    return [aggregate] if aggregate else []


def plant_timezone():
    """Return the timezone in which "today" and "tomorrow" are meant (PLANT_TIMEZONE)."""
    return ZoneInfo(current_app.config.get("PLANT_TIMEZONE", "Europe/Berlin"))


def plant_today():
    """Return today's calendar date at the plant, independent of the server clock."""
    return datetime.now(plant_timezone()).date()


def plant_day_start_utc(day):
    """Return the UTC timestamp (naive, like stored columns) at which a plant day starts."""
    local_start = datetime.combine(day, time.min, tzinfo=plant_timezone())
    return local_start.astimezone(UTC).replace(tzinfo=None)


def day_bounds(day):
    """Return UTC bounds [start, next start) of one plant calendar day for timestamp columns."""
    return plant_day_start_utc(day), plant_day_start_utc(day + timedelta(days=1))


def today_bounds():
    """Return UTC bounds of today at the plant."""
    return day_bounds(plant_today())


def yesterday_bounds():
    """Return UTC bounds of yesterday at the plant."""
    return day_bounds(plant_today() - timedelta(days=1))


def tomorrow():
    """Return tomorrow's plant calendar date."""
    return plant_today() + timedelta(days=1)


def next_week_bounds():
    """Return the next calendar week as an inclusive date range."""
    today = plant_today()
    next_monday = today + timedelta(days=7 - today.weekday())
    return next_monday, next_monday + timedelta(days=6)


def parse_iso_date(value):
    """Return a date for an ISO string or ``None`` when empty; raise on invalid input."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid date: {text}; expected YYYY-MM-DD") from exc


def filter_summary(filters, keys):
    """Return human-readable filter labels for an answer header."""
    labels = [f"{key}={filters[key]}" for key in keys if filters.get(key)]
    return ", ".join(labels) if labels else "keine Zusatzfilter"


def machine_name(record):
    """Return the linked machine name of a record with a ``machine`` relationship."""
    machine = getattr(record, "machine", None)
    return str(getattr(machine, "name", "") or "")
