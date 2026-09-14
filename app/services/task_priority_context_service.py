"""History and evidence behind task priorities: reports, related incidents and handovers."""

import re
from collections import defaultdict

from app.models import ErrorEntry, GeneratedDocument
from app.security import has_dashboard_permission
from app.services.error_service import visible_errors_query


def task_priority_histories(tasks, user):
    """Build compact maintenance-history context for visible task prioritization."""
    if not tasks:
        return {}
    documents_by_task = task_priority_documents_by_task(tasks, user)
    visible_errors = task_priority_visible_errors(user)
    visible_handovers = task_priority_visible_handovers(user)
    histories = {}
    for task in tasks:
        documents = documents_by_task.get(task.id, [])
        histories[task.id] = task_priority_history(
            task,
            documents,
            visible_errors,
            visible_handovers,
        )
    return histories


def task_priority_documents_by_task(tasks, user):
    """Return generated maintenance documents grouped by task when visible."""
    if not has_dashboard_permission(user, "documents", "view"):
        return {}
    task_ids = [task.id for task in tasks]
    documents = (
        GeneratedDocument.query.filter(GeneratedDocument.task_id.in_(task_ids))
        .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
        .all()
    )
    grouped = defaultdict(list)
    for document in documents:
        grouped[document.task_id].append(document)
    return grouped


def task_priority_visible_errors(user):
    """Return recent visible errors that can inform task risk without leaking data."""
    if not has_dashboard_permission(user, "errors", "view"):
        return []
    return (
        visible_errors_query(user)
        .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
        .limit(100)
        .all()
    )


def task_priority_visible_handovers(user):
    """Return recent visible handovers that can inform task risk without leaking data."""
    if not has_dashboard_permission(user, "shiftplans", "view"):
        return []
    from app.handover.services import visible_handovers_query
    from app.models import ShiftHandover

    return (
        visible_handovers_query(user)
        .order_by(ShiftHandover.shift_date.desc(), ShiftHandover.id.desc())
        .limit(100)
        .all()
    )


def task_priority_history(task, documents, visible_errors, visible_handovers=None):
    """Return one compact history payload for a task."""
    machines = task_history_machines(documents)
    related_errors = task_related_errors(task, machines, visible_errors)
    related_handovers = task_related_handovers(task, machines, visible_handovers or [])
    return {
        "maintenance_reports_count": len(documents),
        "last_maintenance_report_at": (documents[0].created_at.isoformat() if documents else None),
        "machines": machines,
        "related_error_count": len(related_errors),
        "recent_related_errors": related_errors[:3],
        "shift_handover_count": len(related_handovers),
        "recent_shift_handovers": related_handovers[:3],
        "reopened_count": task.reopened_count or 0,
        "blocked": bool(task.blocked_reason),
        "risk_signals": task_priority_history_signals(
            task,
            documents,
            related_errors,
            related_handovers,
        ),
        "source_references": task_priority_source_references(
            task,
            documents,
            related_errors,
            related_handovers,
        ),
    }


def empty_task_priority_history(task):
    """Return an empty but structurally stable task-priority history payload."""
    return {
        "maintenance_reports_count": 0,
        "last_maintenance_report_at": None,
        "machines": [],
        "related_error_count": 0,
        "recent_related_errors": [],
        "shift_handover_count": 0,
        "recent_shift_handovers": [],
        "reopened_count": task.reopened_count or 0,
        "blocked": bool(task.blocked_reason),
        "risk_signals": task_priority_history_signals(task, [], [], []),
        "source_references": task_priority_source_references(task, [], [], []),
    }


def task_history_machines(documents):
    """Return unique machine references from visible task documents."""
    machines = []
    seen = set()
    for document in documents:
        machine_id = document.machine_id
        name = str(document.machine or "").strip()
        key = (machine_id, name.lower())
        if key in seen or (not machine_id and not name):
            continue
        seen.add(key)
        machines.append({"id": machine_id, "name": name})
    return machines


def task_related_errors(task, machines, visible_errors):
    """Return visible errors related to a task by machine or technical terms."""
    tokens = task_priority_tokens(
        " ".join(
            [
                task.title or "",
                task.description or "",
                " ".join(machine.get("name") or "" for machine in machines),
            ]
        )
    )
    related = []
    for entry in visible_errors:
        if not task_error_matches(entry, tokens, machines):
            continue
        related.append(
            {
                "id": entry.id,
                "error_code": entry.error_code,
                "title": entry.title,
                "severity": entry.severity,
                "status": entry.status,
                "machine": entry.machine,
                "machine_id": entry.machine_id,
                "repeat_count": entry.repeat_count,
                "downtime_minutes": entry.downtime_minutes,
                "created_at": entry.created_at.isoformat(),
                "role_visibility": _task_priority_role_visibility(
                    entry.department.name if entry.department else "",
                ),
            }
        )
    return related


def task_related_handovers(task, machines, visible_handovers):
    """Return visible shift handovers related to a task by machine or technical terms."""
    tokens = task_priority_tokens(
        " ".join(
            [
                task.title or "",
                task.description or "",
                " ".join(machine.get("name") or "" for machine in machines),
            ]
        )
    )
    related = []
    for handover in visible_handovers:
        if not task_handover_matches(handover, tokens, machines):
            continue
        related.append(
            {
                "id": handover.id,
                "title": f"Schichtuebergabe {handover.shift_date.isoformat()}",
                "status": handover.status,
                "shift_date": handover.shift_date.isoformat(),
                "shift_type": handover.shift_type,
                "machine_id": handover.machine_id,
                "machine": handover.machine.name if handover.machine else "",
                "problem_category": handover.problem_category,
                "open_tasks": str(handover.open_tasks or "")[:220],
                "next_notes": str(handover.next_notes or "")[:220],
                "created_at": handover.created_at.isoformat() if handover.created_at else "",
                "role_visibility": _task_priority_role_visibility(handover.department),
            }
        )
    return related


def task_error_matches(entry, tokens, machines):
    """Return whether an error entry is relevant for a task-priority history."""
    machine_ids = {machine.get("id") for machine in machines if machine.get("id")}
    machine_names = {
        str(machine.get("name") or "").strip().lower()
        for machine in machines
        if machine.get("name")
    }
    if entry.machine_id and entry.machine_id in machine_ids:
        return True
    if entry.machine and entry.machine.strip().lower() in machine_names:
        return True

    haystack = " ".join(
        [
            entry.machine or "",
            entry.error_code or "",
            entry.title or "",
            entry.description or "",
            entry.symptoms or "",
            entry.possible_causes or "",
            entry.solution or "",
        ]
    ).lower()
    return any(token in haystack for token in tokens)


def task_handover_matches(handover, tokens, machines):
    """Return whether a shift handover is relevant for task-priority history."""
    machine_ids = {machine.get("id") for machine in machines if machine.get("id")}
    machine_names = {
        str(machine.get("name") or "").strip().lower()
        for machine in machines
        if machine.get("name")
    }
    if handover.machine_id and handover.machine_id in machine_ids:
        return True
    handover_machine = handover.machine.name.strip().lower() if handover.machine else ""
    if handover_machine and handover_machine in machine_names:
        return True

    haystack = " ".join(
        [
            handover.area or "",
            handover_machine,
            handover.content or "",
            handover.open_tasks or "",
            handover.machine_notes or "",
            handover.next_notes or "",
            handover.cause or "",
            handover.action_taken or "",
            handover.follow_up_task or "",
        ]
    ).lower()
    return any(token in haystack for token in tokens)


def task_priority_tokens(text):
    """Return useful technical tokens for task-history matching."""
    ignored = {
        "anlage",
        "task",
        "test",
        "pruefen",
        "prüfen",
        "wartung",
        "kontrolle",
        "normal",
    }
    return {token for token in re.findall(r"[\w-]{4,}", text.lower()) if token not in ignored}


def task_priority_history_signals(task, documents, related_errors, related_handovers=None):
    """Return compact risk signals derived from task and visible history."""
    signals = []
    if task.blocked_reason:
        signals.append("blocked")
    if task.reopened_count:
        signals.append("reopened")
    if documents:
        signals.append("maintenance_report_history")
    if related_errors:
        signals.append("related_error_history")
    if related_handovers:
        signals.append("shift_handover_history")
    if any(handover.get("status") == "open" for handover in related_handovers or []):
        signals.append("open_handover_history")
    if any(error.get("severity") in {"high", "critical"} for error in related_errors):
        signals.append("critical_error_history")
    if any((error.get("repeat_count") or 0) > 0 for error in related_errors):
        signals.append("recurring_error_history")
    if any((error.get("downtime_minutes") or 0) > 0 for error in related_errors):
        signals.append("downtime_history")
    return signals


def task_priority_source_references(task, documents, related_errors, related_handovers):
    """Return prompt-safe references used as task-priority evidence."""
    references = [task_priority_task_reference(task.to_dict())]
    references.extend(
        _task_priority_document_reference(document) for document in (documents or [])[:3]
    )
    references.extend(_task_priority_error_reference(entry) for entry in (related_errors or [])[:3])
    references.extend(
        _task_priority_handover_reference(handover) for handover in (related_handovers or [])[:3]
    )
    return [reference for reference in references if reference]


def task_priority_task_reference(task_payload):
    """Return a prompt-safe source reference for the prioritized task."""
    department = task_payload.get("department") if isinstance(task_payload, dict) else {}
    department_name = department.get("name") if isinstance(department, dict) else ""
    return {
        "type": "task",
        "id": task_payload.get("id") if isinstance(task_payload, dict) else None,
        "title": str(task_payload.get("title") or "")[:180]
        if isinstance(task_payload, dict)
        else "",
        "machine_id": None,
        "role_visibility": _task_priority_role_visibility(department_name),
        "created_at": task_payload.get("created_at") if isinstance(task_payload, dict) else "",
        "due_date": task_payload.get("due_date") if isinstance(task_payload, dict) else None,
    }


def _task_priority_document_reference(document):
    """Return a prompt-safe source reference for a visible maintenance report."""
    return {
        "type": "maintenance_report",
        "id": document.id,
        "title": str(document.title or "")[:180],
        "machine": document.machine,
        "machine_id": document.machine_id,
        "role_visibility": _task_priority_role_visibility(document.department),
        "created_at": document.created_at.isoformat() if document.created_at else "",
    }


def _task_priority_error_reference(entry):
    """Return a prompt-safe source reference for a visible related error."""
    return {
        "type": "error",
        "id": entry.get("id"),
        "title": str(entry.get("title") or "")[:180],
        "machine": entry.get("machine") or "",
        "machine_id": entry.get("machine_id"),
        "role_visibility": entry.get("role_visibility") or "public",
        "created_at": entry.get("created_at") or "",
        "error_code": entry.get("error_code") or "",
    }


def _task_priority_handover_reference(handover):
    """Return a prompt-safe source reference for a visible shift handover."""
    return {
        "type": "shift_handover",
        "id": handover.get("id"),
        "title": str(handover.get("title") or "")[:180],
        "machine": handover.get("machine") or "",
        "machine_id": handover.get("machine_id"),
        "role_visibility": handover.get("role_visibility") or "public",
        "created_at": handover.get("created_at") or "",
        "shift_date": handover.get("shift_date"),
    }


def _task_priority_role_visibility(department):
    """Return a prompt-safe visibility label for task-priority evidence."""
    department_name = str(department or "").strip()
    return f"department:{department_name[:120]}" if department_name else "public"
