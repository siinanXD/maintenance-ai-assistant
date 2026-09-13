"""Machine service helpers."""

import io
import logging
from datetime import date
from urllib.parse import quote_plus

import segno
from flask import current_app
from sqlalchemy import or_, select

from app.handover.services import visible_handovers_query
from app.inventory.services import forecast_inventory_risks
from app.machines.maintenance_services import visible_maintenance_plans_query
from app.models import (
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    MachineManual,
    MaintenancePlan,
    ShiftHandover,
    Task,
    TaskStatus,
)
from app.security import has_dashboard_permission
from app.services.ai_service import AIServiceError, get_ai_provider
from app.services.document_service import visible_documents_query, visible_manuals_query
from app.services.error_service import visible_errors_query
from app.services.langfuse_service import langfuse_trace_context
from app.services.retrieval_service import knowledge_context_for_chat
from app.services.task_service import visible_tasks_query

logger = logging.getLogger(__name__)
ACTIVE_ERROR_STATUSES = {"open", "in_progress"}
COMPLETED_TASK_STATUSES = {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}


def machine_qr_svg(machine, host_url):
    """Return an SVG QR code pointing at the machine's short link.

    ``PUBLIC_BASE_URL`` wins over the request host so labels printed from a
    reverse-proxied or local session still open the production address.
    """
    base_url = (current_app.config.get("PUBLIC_BASE_URL") or host_url).rstrip("/")
    qr = segno.make(f"{base_url}/m/{machine.id}", error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=8, border=2, xmldecl=False, dark="#141715")
    return buffer.getvalue()


def machine_list_signals(machines, user):
    """Return open task, active error and last error signals per machine id.

    Loads the visible tasks and errors once and matches them to machines the
    same way the machine profile does, so list cards and profiles agree.
    """
    signals = {
        machine.id: {"open_tasks": 0, "active_errors": 0, "last_error": ""} for machine in machines
    }
    if not machines:
        return signals
    if has_dashboard_permission(user, "tasks", "view"):
        open_tasks = (
            visible_tasks_query(user)
            .filter(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
            .limit(1000)
            .all()
        )
        for task in open_tasks:
            text = f"{task.title} {task.description}".lower()
            for machine in machines:
                if machine.name and machine.name.lower() in text:
                    signals[machine.id]["open_tasks"] += 1
    if has_dashboard_permission(user, "errors", "view"):
        errors = (
            visible_errors_query(user)
            .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
            .limit(1000)
            .all()
        )
        for error in errors:
            for machine in machines:
                if not _error_matches_machine(error, machine):
                    continue
                machine_signals = signals[machine.id]
                if not machine_signals["last_error"]:
                    machine_signals["last_error"] = error.title
                if error.status in ACTIVE_ERROR_STATUSES:
                    machine_signals["active_errors"] += 1
    return signals


def _error_matches_machine(error, machine):
    """Return whether an error entry belongs to the machine."""
    if error.machine_id is not None:
        return error.machine_id == machine.id
    return bool(machine.name) and machine.name.lower() in (error.machine or "").lower()


def build_machine_history(machine, user):
    """Build a read-only maintenance history for one machine."""
    task_items = _task_timeline(machine, user)
    error_items = _error_timeline(machine, user)
    document_items = _document_timeline(machine, user)
    timeline = sorted(
        task_items + error_items + document_items,
        key=lambda item: item["date"] or "",
        reverse=True,
    )
    source_counts = {
        "tasks": len(task_items),
        "errors": len(error_items),
        "documents": len(document_items),
        "total": len(timeline),
    }
    return {
        "machine": machine.to_dict(),
        "summary": _machine_summary(machine, timeline, source_counts),
        "source_counts": source_counts,
        "timeline": timeline,
    }


def build_machine_profile(machine, user):
    """Build a machine-centered operational profile from visible source data."""
    tasks = _machine_profile_tasks(machine, user)
    errors = _machine_profile_errors(machine, user)
    documents = _machine_profile_documents(machine, user)
    manuals = _machine_profile_manuals(machine, user)
    maintenance_plans = _machine_profile_maintenance_plans(machine, user)
    handovers = _machine_profile_handovers(machine, user)
    materials = _machine_profile_materials(machine, user)
    timeline = _machine_profile_timeline(
        tasks,
        errors,
        documents,
        manuals,
        maintenance_plans,
        handovers,
    )
    active_errors = [error for error in errors if error["status"] in ACTIVE_ERROR_STATUSES]
    open_tasks = [task for task in tasks if task["status"] not in COMPLETED_TASK_STATUSES]
    return {
        "machine": machine.to_dict(),
        "permissions": _machine_profile_permissions(user),
        "kpis": _machine_profile_kpis(
            machine,
            open_tasks,
            active_errors,
            errors,
            documents,
            manuals,
            maintenance_plans,
            handovers,
            materials,
        ),
        "open_tasks": open_tasks[:8],
        "active_errors": active_errors[:8],
        "error_history": errors[:12],
        "documents": {
            "reports": documents[:8],
            "manuals": manuals[:8],
            "total": len(documents) + len(manuals),
        },
        "maintenance_plans": maintenance_plans[:8],
        "shift_handovers": handovers[:8],
        "materials": materials[:8],
        "timeline": timeline[:18],
    }


def answer_machine_assistant(machine, user, data):
    """Answer a machine-specific question from visible maintenance context."""
    question = str(data.get("question") or "").strip()
    if not question:
        return None, {"error": "question is required"}, 400
    if len(question) > 1000:
        return None, {"error": "question must not exceed 1000 characters"}, 400

    history = build_machine_history(machine, user)
    forecast = _machine_forecast_context(machine, user)
    provider = get_ai_provider()
    rag_context, rag_sources = _machine_rag_context(machine, question, user)
    context = _assistant_context(machine, history, forecast, rag_context)
    context_payload = _assistant_context_payload(history, forecast, rag_sources)

    if provider.name == "mock":
        return (
            {
                "answer": _local_machine_answer(machine, history, forecast, rag_sources),
                "diagnostics": {"status": "local_answer", "provider": provider.name},
                "context": context_payload,
                "sources": rag_sources,
            },
            None,
            200,
        )

    try:
        with langfuse_trace_context(
            "machine_assistant",
            user=user,
            metadata={
                "machine_id": machine.id,
                "rag_source_count": len(rag_sources),
            },
            tags=["machine", "rag"],
        ):
            answer = _answer_question_with_workflow(
                provider,
                question,
                context,
                "machine_assistant",
            )
    except AIServiceError:
        logger.warning(
            "ai_fallback workflow=machine_assistant user_id=%s machine_id=%s",
            user.id,
            machine.id,
        )
        return (
            {
                "answer": _local_machine_answer(machine, history, forecast, rag_sources),
                "diagnostics": {"status": "fallback_used", "provider": provider.name},
                "context": context_payload,
                "sources": rag_sources,
            },
            None,
            200,
        )

    return (
        {
            "answer": answer,
            "diagnostics": {
                "status": "openai_used",
                "provider": provider.name,
                **getattr(provider, "last_call_metadata", {}),
            },
            "context": context_payload,
            "sources": rag_sources,
        },
        None,
        200,
    )


def _task_timeline(machine, user):
    """Return visible task timeline items for a machine."""
    if not has_dashboard_permission(user, "tasks", "view"):
        return []
    needle = f"%{machine.name}%"
    tasks = (
        visible_tasks_query(user)
        .filter(or_(Task.title.ilike(needle), Task.description.ilike(needle)))
        .order_by(Task.updated_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "type": "task",
            "date": task.updated_at.isoformat(),
            "title": task.title,
            "status": task.status.value,
            "summary": task.description,
            "url": _ui_search_url("tasks", task.title),
        }
        for task in tasks
    ]


def _error_timeline(machine, user):
    """Return visible error timeline items for a machine."""
    if not has_dashboard_permission(user, "errors", "view"):
        return []
    errors = (
        visible_errors_query(user)
        .filter(ErrorEntry.machine.ilike(f"%{machine.name}%"))
        .order_by(ErrorEntry.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "type": "error",
            "date": entry.created_at.isoformat(),
            "title": f"{entry.error_code} - {entry.title}",
            "status": entry.status,
            "summary": entry.solution or entry.description,
            "url": _ui_search_url("errors", entry.error_code or entry.title),
        }
        for entry in errors
    ]


def _document_timeline(machine, user):
    """Return visible document timeline items for a machine."""
    if not has_dashboard_permission(user, "documents", "view"):
        return []
    documents = (
        visible_documents_query(user)
        .filter(GeneratedDocument.machine.ilike(f"%{machine.name}%"))
        .order_by(GeneratedDocument.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "type": "document",
            "date": document.created_at.isoformat(),
            "title": document.title,
            "status": document.document_type,
            "summary": f"{document.department} {document.machine}".strip(),
            "url": _ui_search_url("documents", document.title),
        }
        for document in documents
    ]


def _machine_profile_permissions(user):
    """Return section-level visibility used by the machine profile UI."""
    dashboards = ("tasks", "errors", "documents", "shiftplans", "inventory")
    return {
        dashboard: has_dashboard_permission(user, dashboard, "view") for dashboard in dashboards
    }


def _machine_profile_tasks(machine, user):
    """Return visible task rows that can be related to the machine."""
    if not has_dashboard_permission(user, "tasks", "view"):
        return []
    tasks = (
        visible_tasks_query(user)
        .filter(_task_machine_filter(machine))
        .order_by(Task.status.asc(), Task.due_date.asc(), Task.updated_at.desc())
        .limit(40)
        .all()
    )
    return [_profile_task_payload(task, machine) for task in tasks]


def _task_machine_filter(machine):
    """Return a tolerant SQLAlchemy filter for machine-related tasks."""
    needle = f"%{machine.name}%"
    generated_task_ids = select(MaintenancePlan.last_generated_task_id).where(
        MaintenancePlan.machine_id == machine.id,
        MaintenancePlan.last_generated_task_id.isnot(None),
    )
    return or_(
        Task.title.ilike(needle),
        Task.description.ilike(needle),
        Task.id.in_(generated_task_ids),
    )


def _profile_task_payload(task, machine):
    """Return a compact task payload for the machine profile."""
    payload = task.to_dict()
    payload["machine_match"] = _task_match_reason(task, machine)
    payload["ui_url"] = _ui_search_url("tasks", task.title)
    return payload


def _task_match_reason(task, machine):
    """Return how a task was associated with the machine."""
    haystack = f"{task.title} {task.description}".lower()
    if machine.name.lower() in haystack:
        return "Maschinenname im Task"
    return "Wartungsplan oder historischer Bezug"


def _machine_profile_errors(machine, user):
    """Return visible error entries linked to the machine."""
    if not has_dashboard_permission(user, "errors", "view"):
        return []
    errors = (
        visible_errors_query(user)
        .filter(
            or_(
                ErrorEntry.machine_id == machine.id,
                ErrorEntry.machine.ilike(f"%{machine.name}%"),
            )
        )
        .order_by(ErrorEntry.created_at.desc(), ErrorEntry.id.desc())
        .limit(50)
        .all()
    )
    return [_profile_error_payload(error) for error in errors]


def _profile_error_payload(error):
    """Return a compact error payload for the machine profile."""
    payload = error.to_dict()
    payload["ui_url"] = _ui_search_url("errors", error.error_code or error.title)
    return payload


def _machine_profile_documents(machine, user):
    """Return visible generated reports linked to the machine."""
    if not has_dashboard_permission(user, "documents", "view"):
        return []
    documents = (
        visible_documents_query(user)
        .filter(
            or_(
                GeneratedDocument.machine_id == machine.id,
                GeneratedDocument.machine.ilike(f"%{machine.name}%"),
            )
        )
        .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
        .limit(30)
        .all()
    )
    return [_profile_document_payload(document) for document in documents]


def _profile_document_payload(document):
    """Return a compact generated document payload for the machine profile."""
    payload = document.to_dict()
    payload["ui_url"] = _ui_search_url("documents", document.title)
    return payload


def _machine_profile_manuals(machine, user):
    """Return visible uploaded machine manuals linked to the machine."""
    if not has_dashboard_permission(user, "documents", "view"):
        return []
    manuals = (
        visible_manuals_query(user)
        .filter(MachineManual.machine_id == machine.id)
        .order_by(MachineManual.updated_at.desc(), MachineManual.id.desc())
        .limit(30)
        .all()
    )
    return [_profile_manual_payload(manual) for manual in manuals]


def _profile_manual_payload(manual):
    """Return a compact machine manual payload for the machine profile."""
    payload = manual.to_dict()
    payload["ui_url"] = _ui_search_url("documents", manual.title)
    return payload


def _machine_profile_maintenance_plans(machine, user):
    """Return visible maintenance plans for the machine."""
    if not has_dashboard_permission(user, "machines", "view"):
        return []
    plans = (
        visible_maintenance_plans_query(user)
        .filter(MaintenancePlan.machine_id == machine.id)
        .order_by(
            MaintenancePlan.is_active.desc(),
            MaintenancePlan.next_due_date.asc(),
            MaintenancePlan.id.desc(),
        )
        .limit(30)
        .all()
    )
    return [_profile_maintenance_payload(plan) for plan in plans]


def _profile_maintenance_payload(plan):
    """Return a compact maintenance plan payload for the machine profile."""
    payload = plan.to_dict()
    payload["is_due"] = plan.is_active and plan.next_due_date <= date.today()
    payload["ui_url"] = "/machines"
    return payload


def _machine_profile_handovers(machine, user):
    """Return visible shift handovers linked to the machine."""
    if not has_dashboard_permission(user, "shiftplans", "view"):
        return []
    handovers = (
        visible_handovers_query(user)
        .filter(ShiftHandover.machine_id == machine.id)
        .order_by(ShiftHandover.shift_date.desc(), ShiftHandover.id.desc())
        .limit(30)
        .all()
    )
    return [_profile_handover_payload(handover) for handover in handovers]


def _profile_handover_payload(handover):
    """Return a compact handover payload for the machine profile."""
    payload = handover.to_dict()
    payload["ui_url"] = "/handover"
    return payload


def _machine_profile_materials(machine, user):
    """Return visible inventory materials linked to the machine."""
    if not has_dashboard_permission(user, "inventory", "view"):
        return []
    materials = (
        InventoryMaterial.query.filter(InventoryMaterial.machine_id == machine.id)
        .order_by(InventoryMaterial.quantity.asc(), InventoryMaterial.name.asc())
        .limit(30)
        .all()
    )
    return [material.to_dict() for material in materials]


def _machine_profile_kpis(
    machine,
    open_tasks,
    active_errors,
    errors,
    documents,
    manuals,
    maintenance_plans,
    handovers,
    materials,
):
    """Return headline KPIs for the machine profile."""
    critical_errors = [
        error for error in active_errors if error.get("severity") in {"critical", "high"}
    ]
    due_maintenance = [plan for plan in maintenance_plans if plan.get("is_due")]
    low_stock = [
        material
        for material in materials
        if material.get("min_quantity")
        and int(material.get("quantity") or 0) <= int(material.get("min_quantity") or 0)
    ]
    downtime_minutes = sum(int(error.get("downtime_minutes") or 0) for error in errors)
    return {
        "open_tasks": len(open_tasks),
        "active_errors": len(active_errors),
        "critical_errors": len(critical_errors),
        "documents": len(documents) + len(manuals),
        "maintenance_due": len(due_maintenance),
        "shift_handovers": len(handovers),
        "low_stock_materials": len(low_stock),
        "downtime_minutes": downtime_minutes,
        "status": machine.status,
        "criticality": machine.criticality,
        "last_downtime_at": (
            machine.last_downtime_at.isoformat() if machine.last_downtime_at else None
        ),
    }


def _machine_profile_timeline(
    tasks,
    errors,
    documents,
    manuals,
    maintenance_plans,
    handovers,
):
    """Return one chronological profile timeline across visible source types."""
    items = []
    items.extend(_timeline_items(tasks, "task", "Aufgabe", "updated_at", "title"))
    items.extend(_timeline_items(errors, "error", "Stoerung", "created_at", "title"))
    items.extend(_timeline_items(documents, "document", "Dokument", "created_at", "title"))
    items.extend(_timeline_items(manuals, "manual", "Handbuch", "updated_at", "title"))
    items.extend(
        _timeline_items(
            maintenance_plans,
            "maintenance",
            "Wartung",
            "next_due_date",
            "title",
        )
    )
    items.extend(
        _timeline_items(
            handovers,
            "handover",
            "Uebergabe",
            "shift_date",
            "shift_type",
        )
    )
    return sorted(items, key=lambda item: item["date"] or "", reverse=True)


def _timeline_items(items, item_type, label, date_key, title_key):
    """Map serialized profile rows to timeline entries."""
    return [
        {
            "type": item_type,
            "label": label,
            "date": item.get(date_key),
            "title": item.get(title_key) or label,
            "status": item.get("status") or item.get("priority") or "",
            "summary": _timeline_summary(item),
            "ui_url": item.get("ui_url") or "",
        }
        for item in items
    ]


def _timeline_summary(item):
    """Return the first useful short summary field from a serialized row."""
    for key in (
        "description",
        "solution",
        "summary",
        "machine_status",
        "action_taken",
        "produced_item",
    ):
        if item.get(key):
            return str(item[key])
    return ""


def _ui_search_url(route, query):
    """Return a UI search URL for a source record."""
    return f"/{route}?search={quote_plus(str(query or '').strip())}"


def _machine_summary(machine, timeline, source_counts):
    """Return an AI or local summary for the machine history."""
    provider = get_ai_provider()
    if provider.name == "mock":
        return {
            "text": _local_machine_summary(machine, timeline, source_counts),
            "diagnostics": {"status": "local_answer", "provider": provider.name},
        }

    context = _summary_context(machine, timeline, source_counts)
    try:
        with langfuse_trace_context(
            "machine_summary",
            metadata={"machine_id": machine.id},
            tags=["machine"],
        ):
            answer = _answer_question_with_workflow(
                provider,
                (
                    "Fasse diese Maschinenhistorie auf Deutsch in maximal "
                    "3 kurzen Saetzen zusammen."
                ),
                context,
                "machine_summary",
            )
    except AIServiceError:
        logger.warning(
            "ai_fallback workflow=machine_summary machine_id=%s",
            machine.id,
        )
        return {
            "text": _local_machine_summary(machine, timeline, source_counts),
            "diagnostics": {"status": "fallback_used", "provider": provider.name},
        }

    return {
        "text": answer,
        "diagnostics": {
            "status": "openai_used",
            "provider": provider.name,
            **getattr(provider, "last_call_metadata", {}),
        },
    }


def _answer_question_with_workflow(provider, question, context, workflow):
    """Call a provider with workflow metadata while keeping old stubs compatible."""
    try:
        return provider.answer_question(question, context, workflow=workflow)
    except TypeError as exc:
        if "workflow" not in str(exc):
            raise
        return provider.answer_question(question, context)


def _local_machine_summary(machine, timeline, source_counts):
    """Return a deterministic local machine history summary."""
    open_tasks = [
        item
        for item in timeline
        if item["type"] == "task" and item["status"] != TaskStatus.DONE.value
    ]
    latest_error = next((item for item in timeline if item["type"] == "error"), None)
    latest_document = next(
        (item for item in timeline if item["type"] == "document"),
        None,
    )
    parts = [
        (
            f"{machine.name} hat {source_counts['tasks']} Tasks, "
            f"{source_counts['errors']} Fehler und "
            f"{source_counts['documents']} Dokumente in der Historie."
        ),
        f"Offene Tasks: {len(open_tasks)}.",
    ]
    if latest_error:
        parts.append(f"Letzter Fehler: {latest_error['title']}.")
    if latest_document:
        parts.append(f"Letztes Dokument: {latest_document['title']}.")
    return " ".join(parts)


def _summary_context(machine, timeline, source_counts):
    """Return compact context text for an AI machine summary."""
    rows = [
        f"Maschine: {machine.name}",
        f"Tasks: {source_counts['tasks']}",
        f"Fehler: {source_counts['errors']}",
        f"Dokumente: {source_counts['documents']}",
    ]
    for item in timeline[:10]:
        rows.append(
            " | ".join(
                [
                    f"Typ: {item['type']}",
                    f"Datum: {item['date']}",
                    f"Titel: {item['title']}",
                    f"Status: {item['status']}",
                    f"Zusammenfassung: {item['summary']}",
                ]
            )
        )
    return "\n".join(rows)


def _machine_forecast_context(machine, user):
    """Return inventory forecast items related to a machine when permitted."""
    if not (
        has_dashboard_permission(user, "inventory", "view")
        and has_dashboard_permission(user, "tasks", "view")
    ):
        return []
    forecast, error, _status = forecast_inventory_risks(
        {"status": "open", "limit": 20, "low_stock_threshold": 5},
        user,
    )
    if error:
        return []
    return [
        item
        for item in forecast.get("items", [])
        if item.get("machine", {}).get("id") == machine.id
    ]


def _machine_rag_context(machine, question, user):
    """Return RAG context and sources for a machine-specific question."""
    query_text = " ".join(
        part
        for part in (
            machine.name,
            machine.produced_item,
            question,
        )
        if part
    )
    return knowledge_context_for_chat(query_text, user)


def _assistant_context(machine, history, forecast, rag_context=""):
    """Return compact context text for machine assistant answers."""
    rows = [
        f"Maschine: {machine.name}",
        f"Historie: {history['source_counts']}",
        f"Zusammenfassung: {history['summary']['text']}",
    ]
    for item in history["timeline"][:15]:
        rows.append(
            " | ".join(
                [
                    f"Typ: {item['type']}",
                    f"Datum: {item['date']}",
                    f"Titel: {item['title']}",
                    f"Status: {item['status']}",
                    f"Details: {item['summary']}",
                ]
            )
        )
    for item in forecast[:10]:
        rows.append(
            " | ".join(
                [
                    "Typ: lager",
                    f"Material: {item['material']['name']}",
                    f"Risiko: {item['risk_level']}",
                    f"Empfehlung: {item['recommended_action']}",
                ]
            )
        )
    if rag_context:
        rows.append("RAG-Kontext:")
        rows.append(rag_context)
    return "\n".join(rows)


def _assistant_context_payload(history, forecast, rag_sources):
    """Return safe context metadata for machine assistant responses."""
    return {
        "source_counts": history["source_counts"],
        "forecast_items": len(forecast),
        "rag_source_count": len(rag_sources),
    }


def _local_machine_answer(machine, history, forecast, rag_sources=None):
    """Return a deterministic machine assistant answer."""
    rag_sources = rag_sources or []
    counts = history["source_counts"]
    lines = [
        f"{machine.name}: {counts['tasks']} Tasks, {counts['errors']} Fehler, "
        f"{counts['documents']} Dokumente sichtbar."
    ]
    open_task = next(
        (
            item
            for item in history["timeline"]
            if item["type"] == "task" and item["status"] != TaskStatus.DONE.value
        ),
        None,
    )
    if open_task:
        lines.append(f"Naechster Task: {open_task['title']} ({open_task['status']}).")
    if forecast:
        lines.append(
            f"Lagerhinweis: {forecast[0]['material']['name']} " f"ist {forecast[0]['risk_level']}."
        )
    if rag_sources:
        titles = ", ".join(source["title"] for source in rag_sources[:3])
        lines.append(f"RAG-Kontext: {len(rag_sources)} Quellen gefunden ({titles}).")
    if counts["total"] == 0:
        if rag_sources:
            lines.append("Keine klassische Historie gefunden; RAG-Quellen pruefen.")
        else:
            lines.append("Keine Historie gefunden; Maschine und Taskdaten pruefen.")
    return " ".join(lines)
