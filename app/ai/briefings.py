"""Daily maintenance briefing sections and chat formatting."""

import logging
from datetime import date, timedelta

from app.inventory.services import forecast_inventory_risks
from app.models import (
    ErrorEntry,
    GeneratedDocument,
    Task,
    TaskStatus,
)
from app.security import has_dashboard_permission
from app.services.ai_structured_source_service import module_count_source_card
from app.services.document_service import visible_documents_query
from app.services.error_service import visible_errors_query
from app.services.incident_timeline_service import daily_briefing_timeline_section
from app.services.recurring_issue_service import analyze_recurring_issues
from app.services.retrieval_service import knowledge_context_for_chat
from app.services.task_service import visible_tasks_query

logger = logging.getLogger(__name__)


def daily_briefing(user):
    """Return a local daily maintenance briefing for the current user."""
    sections = []
    if has_dashboard_permission(user, "tasks", "view"):
        sections.append(task_briefing_section(user))
    if has_dashboard_permission(user, "inventory", "view") and has_dashboard_permission(
        user, "tasks", "view"
    ):
        sections.append(inventory_briefing_section(user))
    if has_dashboard_permission(user, "errors", "view"):
        sections.append(error_briefing_section(user))
        sections.append(recurring_issue_briefing_section(user))
        sections.append(daily_briefing_timeline_section(user))
    if has_dashboard_permission(user, "documents", "view"):
        sections.append(document_briefing_section(user))
    sections.append(rag_briefing_section(user))

    visible_sections = [section for section in sections if section]
    important_count = sum(section["count"] for section in visible_sections)
    if important_count:
        summary = f"Heute gibt es {important_count} wichtige Hinweise."
    else:
        summary = "Heute sind keine kritischen Hinweise sichtbar."
    return {
        "date": date.today().isoformat(),
        "summary": summary,
        "sections": visible_sections,
        "diagnostics": {
            "status": "local_answer",
            "provider": "local_briefing",
            "rag_source_count": sum(
                section.get("rag_source_count", 0) for section in visible_sections
            ),
        },
    }


TASK_PRIORITY_LABELS = {"urgent": "Dringend", "soon": "Bald", "normal": "Normal"}
TASK_STATUS_LABELS = {
    "open": "Offen",
    "in_progress": "In Arbeit",
    "done": "Erledigt",
    "cancelled": "Abgebrochen",
}


def task_briefing_section(user):
    """Return today's and overdue task briefing items."""
    today = date.today()
    tasks = (
        visible_tasks_query(user)
        .filter(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date.asc(), Task.id.desc())
        .limit(20)
        .all()
    )
    items = []
    for task in tasks:
        if task.due_date > today and task.priority.value != "urgent":
            continue
        items.append(
            {
                "title": task.title,
                "severity": "critical" if task.due_date < today else "high",
                "summary": (
                    f"{TASK_PRIORITY_LABELS.get(task.priority.value, task.priority.value)}, "
                    f"{TASK_STATUS_LABELS.get(task.status.value, task.status.value)}, "
                    f"fällig {task.due_date.strftime('%d.%m.%Y')}"
                ),
                "url": f"/api/tasks/{task.id}",
            }
        )
    return {
        "type": "tasks",
        "title": "Tasks",
        "count": len(items),
        "items": items[:5],
    }


def inventory_briefing_section(user):
    """Return critical inventory forecast briefing items."""
    forecast, error, _status = forecast_inventory_risks(
        {"status": "open", "limit": 20, "low_stock_threshold": 5},
        user,
    )
    if error:
        return None
    items = [
        {
            "title": item["material"]["name"],
            "severity": item["risk_level"],
            "summary": item["recommended_action"],
            "url": "/inventory",
        }
        for item in forecast.get("items", [])
        if item["risk_level"] in {"critical", "high"}
    ]
    return {
        "type": "inventory",
        "title": "Lager",
        "count": len(items),
        "items": items[:5],
    }


def error_briefing_section(user):
    """Return recently created error catalog briefing items."""
    since = date.today() - timedelta(days=1)
    entries = visible_errors_query(user)
    entries = (
        entries.filter(ErrorEntry.created_at >= since)
        .order_by(ErrorEntry.created_at.desc())
        .limit(5)
        .all()
    )
    items = [
        {
            "title": f"{entry.error_code} - {entry.title}",
            "severity": "medium",
            "summary": entry.machine,
            "url": f"/api/errors/{entry.id}",
        }
        for entry in entries
    ]
    return {
        "type": "errors",
        "title": "Neue Fehler",
        "count": len(items),
        "items": items,
    }


def recurring_issue_briefing_section(user):
    """Return recurring error trends as briefing items."""
    trends = analyze_recurring_issues(user, days=30, min_occurrences=2, limit=3)
    items = [
        {
            "title": f"{item['affected_machine']} {item['error_code']}".strip(),
            "severity": item["risk_level"],
            "summary": item["recommendation"],
            "url": "/errors",
            "occurrence_count": item["occurrence_count"],
        }
        for item in trends.get("items", [])
    ]
    if not items:
        return None
    return {
        "type": "recurring_issues",
        "title": "Wiederkehrende Fehler",
        "count": len(items),
        "items": items,
        "diagnostics": trends.get("diagnostics", {}),
    }


def document_briefing_section(user):
    """Return recent document briefing items as review candidates."""
    documents = (
        visible_documents_query(user)
        .filter(GeneratedDocument.created_at >= date.today() - timedelta(days=7))
        .order_by(GeneratedDocument.created_at.desc())
        .limit(5)
        .all()
    )
    items = [
        {
            "title": document.title,
            "severity": "info",
            "summary": "Dokumentpruefung bei Bedarf ausfuehren",
            "url": document.to_dict()["detail_url"],
        }
        for document in documents
    ]
    return {
        "type": "documents",
        "title": "Dokumente",
        "count": len(items),
        "items": items,
    }


def format_daily_briefing_answer(briefing, sections, item_count):
    """Return a compact German chat answer for an existing daily briefing payload."""
    lines = [
        "## Heutige Entscheidungen",
        f"- **Datum:** {briefing.get('date')}",
        f"- **Status:** {briefing.get('summary')}",
        f"- **Anzahl:** {item_count}",
        "- **Quelle:** Daily-Briefing-Service",
    ]
    if item_count <= 0:
        lines.append("")
        lines.append("Keine Eintraege fuer heute vorhanden.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Wichtige Punkte:")
    for section in sections:
        if int(section.get("count") or 0) <= 0:
            continue
        lines.append(f"- **{section.get('title')}:** {section.get('count')}")
        for item in list(section.get("items") or [])[:3]:
            lines.append(f"  - {item.get('title')} ({item.get('severity')})")
    return "\n".join(lines)


def daily_briefing_source_cards(sections, user):
    """Return prompt-safe source cards for daily briefing sections."""
    sources = []
    for section in sections:
        scope = _briefing_section_scope(section)
        if scope:
            source = module_count_source_card(scope, int(section.get("count") or 0), user)
            if source:
                sources.append(source)
            continue
        sources.extend(_knowledge_section_source_cards(section))
    return sources


def _briefing_section_scope(section):
    """Return the dashboard scope represented by one briefing section."""
    mapping = {
        "tasks": "tasks",
        "inventory": "inventory",
        "errors": "errors",
        "recurring_issues": "errors",
        "incident_timeline": "errors",
        "documents": "documents",
    }
    return mapping.get(str((section or {}).get("type") or ""))


def _knowledge_section_source_cards(section):
    """Return lightweight source cards for knowledge briefing items."""
    if str((section or {}).get("type") or "") != "knowledge":
        return []
    cards = []
    for index, item in enumerate(list(section.get("items") or [])[:3], start=1):
        cards.append(
            {
                "type": "knowledge",
                "id": None,
                "title": str(item.get("title") or "AI-Wissenskontext")[:160],
                "module": "knowledge",
                "url": str(item.get("url") or "/admin/ai/knowledge")[:240],
                "source_type": "daily_briefing_knowledge",
                "source_id": None,
                "source_record_id": None,
                "source_kind": "daily_briefing",
                "role_visibility": "permission_scoped",
                "created_at": str(item.get("created_at") or ""),
                "score": max(1, 30 - index),
            }
        )
    return cards


def rag_briefing_section(user):
    """Return visible RAG knowledge sources relevant for today's briefing."""
    department = user.department.name if user.department else ""
    query_text = " ".join(
        part
        for part in (
            "heute kritisch stoerung wartung instandhaltung maschine",
            department,
        )
        if part
    )
    _context, sources = knowledge_context_for_chat(query_text, user, limit=3)
    if not sources:
        return None
    items = [
        {
            "title": source["title"],
            "severity": "info",
            "summary": source["reason"],
            "url": source["url"],
        }
        for source in sources
    ]
    return {
        "type": "knowledge",
        "title": "AI-Wissenskontext",
        "count": len(items),
        "items": items,
        "rag_source_count": len(sources),
    }
