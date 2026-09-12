"""Document metadata queries for the agent."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.models import GeneratedDocument, MachineManual
from app.security import has_dashboard_permission
from app.services.ai_question_normalizer import normalize_text
from app.services.ai_structured_source_service import (
    document_source_cards,
    manual_source_cards,
)
from app.services.document_service import visible_documents_query, visible_manuals_query

from .common import (
    MAX_LIST_ITEMS,
    QueryOutcome,
    aggregate_or_row_sources,
    build_structured_context,
    denied_outcome,
    format_structured_list_answer,
    machine_name,
)

FILTERS = {"recent", "outdated", "this_week", "department", "machine", "all"}
OUTDATED_STATUSES = {"outdated", "stale", "veraltet"}


def list_documents(user, *, filter="recent", department=None, machine=None):
    """Return visible generated documents and manuals for one metadata filter."""
    if not has_dashboard_permission(user, "documents", "view"):
        return denied_outcome("documents", "documents")
    document_filter = str(filter or "recent").strip().lower()
    if document_filter not in FILTERS:
        raise ValueError(f"unsupported filter: {document_filter}")
    department = str(department or "").strip()
    machine = str(machine or "").strip()
    if document_filter == "department" and not department:
        raise ValueError("department is required for filter=department")
    if document_filter == "machine" and not machine:
        raise ValueError("machine is required for filter=machine")

    if document_filter == "outdated":
        items = [
            _document_item(document)
            for document in visible_documents_query(user).limit(MAX_LIST_ITEMS).all()
            if _is_outdated(document)
        ]
        title = "Veraltete Dokumente"
    elif document_filter == "this_week":
        items = _this_week_items(user)
        title = "Diese Woche hochgeladen"
    elif document_filter == "department":
        items = _department_items(user, department)
        title = f"Dokumente {department}"
    elif document_filter == "machine":
        items = _machine_items(user, machine)
        title = f"Dokumente zu {machine}"
    else:
        items = _recent_items(user)
        title = "Zuletzt geaenderte Dokumente"
    if department and document_filter != "department":
        items = [
            item
            for item in items
            if normalize_text(department) in normalize_text(item.get("department") or "")
        ]
    if machine and document_filter != "machine":
        items = [
            item
            for item in items
            if normalize_text(machine) in normalize_text(item.get("machine") or "")
        ]
    documents = [item["record"] for item in items if item["kind"] == "generated_document"]
    manuals = [item["record"] for item in items if item["kind"] == "machine_manual"]
    public_items = [
        {key: value for key, value in item.items() if key != "record"} for item in items
    ]
    filters = {"filter": document_filter}
    if department:
        filters["department"] = department
    if machine:
        filters["machine"] = machine
    return QueryOutcome(
        entity_type="documents",
        scope="documents",
        answer_markdown=format_structured_list_answer(
            title=title,
            label="sichtbare Dokumente",
            items=public_items,
            count_label="Sichtbare Dokumente",
            formatter=lambda item: (
                f"- {item['title']} ({item['department']}"
                f"{', Maschine ' + item['machine'] if item.get('machine') else ''})"
            ),
            source="Strukturierte Dokument-Metadaten",
            overflow_suffix="weitere sichtbare Dokumente",
            empty_message="Keine sichtbaren Dokumente fuer diese Anfrage gefunden.",
        ),
        count=len(public_items),
        items=public_items,
        filters=filters,
        sources=aggregate_or_row_sources(
            document_source_cards(documents) + manual_source_cards(manuals),
            "documents",
            len(items),
            user,
        ),
        structured_context=build_structured_context(
            "documents",
            query=f"document_{document_filter}",
            department=department,
            machine=machine,
        ),
        query=document_filter,
    )


def _recent_items(user):
    """Return recently changed visible document metadata."""
    documents = visible_documents_query(user).limit(MAX_LIST_ITEMS).all()
    manuals = visible_manuals_query(user).limit(MAX_LIST_ITEMS).all()
    return sorted(
        [_document_item(document) for document in documents]
        + [_manual_item(manual) for manual in manuals],
        key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        reverse=True,
    )[:MAX_LIST_ITEMS]


def _this_week_items(user):
    """Return documents created during the current calendar week."""
    monday = date.today() - timedelta(days=date.today().weekday())
    start = datetime.combine(monday, time.min)
    documents = (
        visible_documents_query(user)
        .filter(GeneratedDocument.created_at >= start)
        .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    manuals = (
        visible_manuals_query(user)
        .filter(MachineManual.created_at >= start)
        .order_by(MachineManual.created_at.desc(), MachineManual.id.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    return sorted(
        [_document_item(document) for document in documents]
        + [_manual_item(manual) for manual in manuals],
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )[:MAX_LIST_ITEMS]


def _department_items(user, department):
    """Return document metadata items for one department."""
    documents = (
        visible_documents_query(user)
        .filter(GeneratedDocument.department.ilike(department))
        .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    manuals = (
        visible_manuals_query(user)
        .filter(MachineManual.department.ilike(department))
        .order_by(MachineManual.created_at.desc(), MachineManual.id.desc())
        .limit(MAX_LIST_ITEMS)
        .all()
    )
    return [_document_item(document) for document in documents] + [
        _manual_item(manual) for manual in manuals
    ]


def _machine_items(user, machine):
    """Return document metadata items for one machine name."""
    documents = [
        document
        for document in visible_documents_query(user).limit(MAX_LIST_ITEMS).all()
        if normalize_text(machine) in normalize_text(document.machine)
    ]
    manuals = [
        manual
        for manual in visible_manuals_query(user).limit(MAX_LIST_ITEMS).all()
        if normalize_text(machine) in normalize_text(machine_name(manual))
    ]
    return [_document_item(document) for document in documents] + [
        _manual_item(manual) for manual in manuals
    ]


def _document_item(document):
    """Return safe generated-document metadata."""
    version = getattr(document, "current_version", None)
    updated_at = getattr(version, "created_at", None) or getattr(document, "created_at", None)
    return {
        "kind": "generated_document",
        "id": document.id,
        "title": document.title,
        "document_type": document.document_type,
        "department": document.department,
        "machine": document.machine,
        "machine_id": document.machine_id,
        "status": document.status,
        "quality_status": document.quality_status,
        "created_at": document.created_at.isoformat() if document.created_at else "",
        "updated_at": updated_at.isoformat() if updated_at else "",
        "record": document,
    }


def _manual_item(manual):
    """Return safe machine-manual metadata."""
    return {
        "kind": "machine_manual",
        "id": manual.id,
        "title": manual.title,
        "document_type": "machine_manual",
        "department": manual.department,
        "machine": machine_name(manual),
        "machine_id": manual.machine_id,
        "created_at": manual.created_at.isoformat() if manual.created_at else "",
        "updated_at": manual.updated_at.isoformat() if manual.updated_at else "",
        "record": manual,
    }


def _is_outdated(document):
    """Return whether structured metadata marks a document as outdated."""
    return (
        str(getattr(document, "status", "") or "").lower() in OUTDATED_STATUSES
        or str(getattr(document, "quality_status", "") or "").lower() in OUTDATED_STATUSES
    )
