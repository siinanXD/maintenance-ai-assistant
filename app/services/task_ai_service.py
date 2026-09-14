"""AI task features: prioritization and suggestions from free text in a stable shape."""

import logging

from app.models import Department, Priority, Role, Task, TaskStatus
from app.services.ai_provider_mock import MockAIProvider
from app.services.ai_service import AIServiceError, get_ai_provider
from app.services.maintenance_tag_service import suggest_tags_for_task_payload
from app.services.task_priority_context_service import (
    empty_task_priority_history,
    task_priority_histories,
    task_priority_task_reference,
)
from app.services.task_service import parse_enum, visible_tasks_query

logger = logging.getLogger(__name__)

TASK_PRIORITY_MODE_AI = "ai"
TASK_PRIORITY_MODE_LOCAL = "local"
TASK_PRIORITY_MODES = {TASK_PRIORITY_MODE_AI, TASK_PRIORITY_MODE_LOCAL}


def prioritize_visible_tasks(data, user):
    """Return non-persisted AI priorities for tasks visible to the given user.

    Returns (priorities_list, None, 200) or (None, error_dict, status) on failure.
    """
    try:
        status = parse_enum(TaskStatus, data.get("status"), None)
        limit = parse_priority_limit(data.get("limit", 20))
        priority_mode = parse_task_priority_mode(data.get("mode"))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    query = visible_tasks_query(user)
    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.due_date.asc(), Task.id.desc()).limit(limit).all()
    serialized = serialize_tasks_for_prioritization(tasks, user)
    context = {
        "role": user.role.value,
        "department": user.department.name if user.department else "",
        "history_fields": [
            "maintenance_reports_count",
            "related_error_count",
            "recent_related_errors",
            "recent_shift_handovers",
            "machines",
            "risk_signals",
        ],
    }

    if priority_mode == TASK_PRIORITY_MODE_LOCAL:
        provider_result = MockAIProvider().prioritize_tasks(serialized, context)
    else:
        try:
            provider_result = get_ai_provider().prioritize_tasks(serialized, context)
        except AIServiceError:
            logger.warning(
                "ai_fallback workflow=task_prioritization user_id=%s task_count=%s",
                user.id,
                len(serialized),
            )
            provider_result = MockAIProvider().prioritize_tasks(serialized, context)

    priorities = normalize_task_priorities(provider_result, tasks, serialized)
    return priorities, None, 200


def suggest_task_from_text(data, user):
    """Return a non-persisted AI task suggestion derived from free text.

    Returns (suggestion_dict, None, 200) or (None, error_dict, status) on failure.
    """
    text = str(data.get("text") or "").strip()
    if not text:
        return None, {"error": "text is required"}, 400
    if len(text) > 2000:
        return None, {"error": "text must not exceed 2000 characters"}, 400

    user_context = {
        "role": user.role.value,
        "department": user.department.name if user.department else "",
    }
    from app.services.retrieval_service import knowledge_context_for_chat

    rag_context, rag_sources = knowledge_context_for_chat(text, user)
    if rag_context:
        user_context["rag_context"] = rag_context
        user_context["rag_sources"] = rag_sources
    try:
        suggestion = get_ai_provider().suggest_task(text, user_context)
    except AIServiceError:
        logger.warning(
            "ai_fallback workflow=task_suggestion user_id=%s text_length=%s",
            user.id,
            len(text),
        )
        suggestion = MockAIProvider().suggest_task(text, user_context)

    normalized = normalize_task_suggestion(suggestion, text, user)
    normalized["sources"] = rag_sources
    normalized["diagnostics"] = {
        "status": "local_answer",
        "rag_source_count": len(rag_sources),
    }
    normalized["tag_suggestions"] = suggest_tags_for_task_payload(
        {
            **normalized,
            "text": text,
        }
    )
    return normalized, None, 200


def parse_priority_limit(value):
    """Parse and validate a task prioritization limit (1–100)."""
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer between 1 and 100") from exc
    if limit < 1 or limit > 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return limit


def parse_task_priority_mode(value):
    """Return the requested task priority provider mode."""
    mode = str(value or TASK_PRIORITY_MODE_AI).strip().lower()
    if mode not in TASK_PRIORITY_MODES:
        raise ValueError("mode must be one of: ai, local")
    return mode


def serialize_tasks_for_prioritization(tasks, user):
    """Return task payloads enriched with permission-safe history context."""
    histories = task_priority_histories(tasks, user)
    serialized = []
    for task in tasks:
        payload = task.to_dict()
        payload["history"] = histories.get(task.id, empty_task_priority_history(task))
        serialized.append(payload)
    return serialized


def normalize_task_priorities(provider_result, tasks, serialized_tasks=None):
    """Normalize provider priority output and attach full task payloads."""
    provider_items = _provider_priority_items(provider_result)
    priority_by_task_id = {
        int(item["task_id"]): item for item in provider_items if _has_valid_task_id(item)
    }
    fallback_payloads = serialized_tasks or [task.to_dict() for task in tasks]
    fallback_items = MockAIProvider().prioritize_tasks(fallback_payloads, {})["priorities"]
    fallback_by_task_id = {item["task_id"]: item for item in fallback_items}
    serialized_by_task_id = {
        int(item["id"]): item for item in fallback_payloads if _has_valid_payload_id(item)
    }

    normalized = []
    for task in tasks:
        item = priority_by_task_id.get(task.id, fallback_by_task_id[task.id])
        serialized_task = serialized_by_task_id.get(task.id, {})
        evidence_counts = task_priority_evidence_counts(serialized_task)
        normalized.append(
            {
                "task": task.to_dict(),
                "score": _clamped_score(item.get("score")),
                "risk_level": _valid_risk_level(item.get("risk_level")),
                "reason": str(item.get("reason") or "").strip()[:500],
                "recommended_action": str(item.get("recommended_action") or "").strip()[:500],
                "confidence": task_priority_confidence(item, evidence_counts),
                "evidence_counts": evidence_counts,
                "evidence_references": task_priority_evidence_references(serialized_task),
                "next_steps": task_priority_next_steps(serialized_task),
            }
        )

    return sorted(normalized, key=lambda item: item["score"], reverse=True)


def task_priority_confidence(provider_item, evidence_counts):
    """Return confidence and uncertainty for one task-priority suggestion."""
    counts = evidence_counts if isinstance(evidence_counts, dict) else {}
    score = 35
    score += min(25, int(counts.get("risk_signals") or 0) * 6)
    score += min(15, int(counts.get("related_errors") or 0) * 5)
    score += min(10, int(counts.get("maintenance_reports") or 0) * 4)
    score += min(8, int(counts.get("shift_handovers") or 0) * 4)
    score += min(5, int(counts.get("machines") or 0) * 3)
    if str((provider_item or {}).get("reason") or "").strip():
        score += 5
    score = max(0, min(95, score))
    level = _task_priority_confidence_level(score)
    return {
        "score": score,
        "level": level,
        "uncertainty": _task_priority_uncertainty(level),
        "reason": _task_priority_confidence_reason(counts),
        "uses_only_visible_sources": bool(counts.get("uses_only_visible_sources", True)),
    }


def _task_priority_confidence_level(score):
    """Return a coarse confidence level for a task-priority suggestion."""
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _task_priority_uncertainty(level):
    """Return an uncertainty label aligned with the confidence level."""
    if level == "high":
        return "low"
    if level == "medium":
        return "medium"
    return "high"


def _task_priority_confidence_reason(evidence_counts):
    """Return a short explanation for task-priority confidence."""
    if int(evidence_counts.get("related_errors") or 0) and int(
        evidence_counts.get("maintenance_reports") or 0
    ):
        return "Fehlerhistorie und Wartungsberichte stuetzen die Priorisierung."
    if int(evidence_counts.get("related_errors") or 0):
        return "Sichtbare Fehlerhistorie stuetzt die Priorisierung."
    if int(evidence_counts.get("shift_handovers") or 0):
        return "Schichtuebergaben liefern zusaetzlichen Kontext."
    if int(evidence_counts.get("risk_signals") or 0):
        return "Task-Signale stuetzen die Priorisierung, Quellenlage ist begrenzt."
    return "Geringe Zusatzhistorie; Priorisierung basiert hauptsaechlich auf Task-Daten."


def task_priority_evidence_counts(serialized_task):
    """Return public evidence counters for a prioritized task response."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if not isinstance(history, dict):
        history = {}
    recent_related_errors = history.get("recent_related_errors")
    recent_shift_handovers = history.get("recent_shift_handovers")
    machines = history.get("machines")
    risk_signals = history.get("risk_signals")
    return {
        "maintenance_reports": _safe_count(history.get("maintenance_reports_count")),
        "related_errors": _safe_count(history.get("related_error_count")),
        "recent_related_errors": len(recent_related_errors or []),
        "shift_handovers": _safe_count(history.get("shift_handover_count")),
        "recent_shift_handovers": len(recent_shift_handovers or []),
        "machines": len(machines or []),
        "risk_signals": len(risk_signals or []),
        "blocked": bool(history.get("blocked")),
        "reopened_count": _safe_count(history.get("reopened_count")),
        "uses_only_visible_sources": True,
    }


def task_priority_evidence_references(serialized_task):
    """Return prompt-safe source references for a prioritized task response."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if isinstance(history, dict) and isinstance(history.get("source_references"), list):
        return history["source_references"][:8]
    return [task_priority_task_reference(serialized_task)] if serialized_task else []


def task_priority_next_steps(serialized_task):
    """Return structured next steps from visible task-priority evidence."""
    history = serialized_task.get("history") if isinstance(serialized_task, dict) else {}
    if not isinstance(history, dict):
        history = {}
    steps = []
    if history.get("blocked"):
        steps.append(
            task_priority_step(
                "resolve_blocker",
                "Blocker klaeren",
                (
                    "Blockierten Task zuerst mit Ursache, Verantwortlichem "
                    "und naechstem Termin klaeren."
                ),
                "task",
                "high",
            )
        )
    if history.get("recent_related_errors"):
        steps.append(
            task_priority_step(
                "review_related_errors",
                "Fehlerhistorie pruefen",
                "Sichtbare verwandte Fehler auf Ursache, Wiederholung und Stillstand auswerten.",
                "error",
                "high",
            )
        )
    if history.get("recent_shift_handovers"):
        steps.append(
            task_priority_step(
                "review_shift_handover",
                "Schichtuebergabe beruecksichtigen",
                "Offene Hinweise aus sichtbaren Uebergaben in die Task-Reihenfolge einbeziehen.",
                "shift_handover",
                "medium",
            )
        )
    if _safe_count(history.get("maintenance_reports_count")):
        steps.append(
            task_priority_step(
                "review_maintenance_reports",
                "Wartungsberichte abgleichen",
                (
                    "Letzte sichtbare Wartungsberichte gegen Task-Beschreibung "
                    "und Anlagenbezug pruefen."
                ),
                "maintenance_report",
                "medium",
            )
        )
    if _safe_count(history.get("reopened_count")):
        steps.append(
            task_priority_step(
                "check_reopened_task",
                "Wiedereroeffnung klaeren",
                (
                    "Wiedereroeffnete Aufgabe auf unvollstaendige Ursache "
                    "oder fehlende Abnahme pruefen."
                ),
                "task",
                "medium",
            )
        )
    if not steps:
        steps.append(
            task_priority_step(
                "execute_task",
                "Task planmaessig bearbeiten",
                (
                    "Keine zusaetzlichen Risikosignale gefunden; nach "
                    "Faelligkeit und Prioritaet einplanen."
                ),
                "task",
                "low",
            )
        )
    return steps[:4]


def task_priority_step(step_type, title, detail, source_type, urgency):
    """Return one bounded next-step payload for task prioritization."""
    return {
        "type": str(step_type or "")[:80],
        "title": str(title or "")[:160],
        "detail": str(detail or "")[:500],
        "source_type": str(source_type or "")[:80],
        "urgency": str(urgency or "medium")[:40],
    }


def normalize_task_suggestion(suggestion, original_text, user):
    """Validate and normalize an AI task suggestion into a stable dict."""
    suggestion = suggestion or {}
    department_name = suggestion.get("department")
    if user.role != Role.MASTER_ADMIN and user.department:
        department_name = user.department.name
    if not Department.query.filter_by(name=department_name).first():
        department_name = user.department.name if user.department else "Instandhaltung"

    priority = suggestion.get("priority", Priority.NORMAL.value)
    if priority not in {item.value for item in Priority}:
        priority = Priority.NORMAL.value

    status = suggestion.get("status", TaskStatus.OPEN.value)
    if status not in {item.value for item in TaskStatus}:
        status = TaskStatus.OPEN.value

    title = str(suggestion.get("title") or original_text[:80]).strip()
    return {
        "title": title[:160],
        "description": str(suggestion.get("description") or original_text).strip(),
        "department": department_name,
        "priority": priority,
        "status": status,
        "possible_cause": str(suggestion.get("possible_cause") or "").strip(),
        "recommended_action": str(suggestion.get("recommended_action") or "").strip(),
    }


def _provider_priority_items(provider_result):
    """Extract the priority list from a dict or list provider response."""
    if isinstance(provider_result, list):
        return provider_result
    if isinstance(provider_result, dict):
        priorities = provider_result.get("priorities", [])
        if isinstance(priorities, list):
            return priorities
    return []


def _has_valid_task_id(item):
    """Return True if the item dict contains a parseable task_id."""
    if not isinstance(item, dict):
        return False
    try:
        int(item.get("task_id"))
    except (TypeError, ValueError):
        return False
    return True


def _has_valid_payload_id(item):
    """Return True if the item dict contains a parseable serialized task id."""
    if not isinstance(item, dict):
        return False
    try:
        int(item.get("id"))
    except (TypeError, ValueError):
        return False
    return True


def _clamped_score(value):
    """Clamp a score value to the public 0–100 range."""
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _safe_count(value):
    """Return a non-negative integer counter from a possibly invalid value."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _valid_risk_level(value):
    """Return a supported risk level, falling back to 'low'."""
    if value in {"low", "medium", "high", "critical"}:
        return value
    return "low"
