"""Employee document metadata queries for the agent."""

from __future__ import annotations

from app.models import Employee, EmployeeDocument
from app.permissions import can_read_employee_context
from app.security import employee_access_level
from app.services.ai_question_normalizer import normalize_text
from app.services.ai_structured_source_service import (
    SOURCE_CARD_LIMIT,
    employee_count_source_card,
    employee_document_source_cards,
    employee_source_cards,
)
from app.services.visibility_query_service import visible_employees_query

from .common import (
    MAX_ANSWER_ITEMS,
    MAX_LIST_ITEMS,
    QueryOutcome,
    build_structured_context,
    denied_outcome,
)
from .employees import employee_payload_for_access_level, format_employee_list_answer

MODES = {"employees_with_documents", "stored_documents"}


def list_employee_documents(
    user,
    *,
    mode="employees_with_documents",
    department=None,
    employee=None,
    count_only=False,
):
    """Return employees with documents or the stored document files themselves."""
    if not can_read_employee_context(user):
        return denied_outcome("employees", "employees")
    mode = str(mode or "employees_with_documents").strip().lower()
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    department = str(department or "").strip() or None
    employee_record = resolve_visible_employee(user, employee)
    if employee and employee_record is None:
        return _no_such_employee(str(employee))
    if mode == "stored_documents" or employee_record is not None:
        if count_only:
            return _stored_document_count(user, department, employee_record)
        return _stored_document_list(user, department, employee_record)
    if count_only:
        return _employees_with_documents_count(user, department)
    return _employees_with_documents_list(user, department)


def resolve_visible_employee(user, reference):
    """Return a visible employee by id or (partial) name, or ``None``."""
    text = str(reference or "").strip()
    if not text:
        return None
    query = visible_employees_query(user)
    if text.isdigit():
        return query.filter(Employee.id == int(text)).first()
    normalized = normalize_text(text)
    matches = [
        employee
        for employee in query.order_by(Employee.name.asc()).all()
        if normalized
        and (
            normalize_text(employee.name) == normalized
            or normalized in normalize_text(employee.name)
        )
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(normalize_text(item.name)))


def _employees_with_documents_count(user, department):
    """Return the count of visible employees with at least one stored document."""
    count = _employees_with_documents_query(user, department).count()
    label = (
        f"Mitarbeiter mit Dokumenten in {department}"
        if department
        else "Mitarbeiter mit Dokumenten"
    )
    source = employee_count_source_card(count, user, department=department or "")
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            f"## {label}\n"
            f"- **Anzahl:** {count}\n"
            "- **Filter:** mindestens ein hinterlegtes Mitarbeiterdokument\n"
            "- **Quelle:** Strukturierte Mitarbeiterdaten"
        ),
        count=count,
        filters={"department": department} if department else {},
        sources=[source] if source else [],
        structured_context=build_structured_context(
            "employees", query="with_documents", department=department
        ),
        query="document_count",
    )


def _employees_with_documents_list(user, department):
    """Return visible employees that have at least one stored document."""
    query = _employees_with_documents_query(user, department).order_by(
        Employee.name.asc(), Employee.id.asc()
    )
    total_count = query.count()
    employees = query.limit(MAX_LIST_ITEMS).all()
    label = (
        f"mindestens ein hinterlegtes Mitarbeiterdokument in {department}"
        if department
        else "mindestens ein hinterlegtes Mitarbeiterdokument"
    )
    access_level = employee_access_level(user)
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=format_employee_list_answer(
            "Mitarbeiter mit Dokumenten",
            label,
            employees,
            "Sichtbare Mitarbeiter",
            source="Strukturierte Mitarbeiterdaten",
            total_count=total_count,
        ),
        count=total_count,
        items=[employee_payload_for_access_level(employee, access_level) for employee in employees],
        filters={"department": department} if department else {},
        sources=employee_source_cards(employees, user),
        structured_context=build_structured_context(
            "employees", query="with_documents", department=department
        ),
        extra={"returned_count": len(employees), "truncated": total_count > len(employees)},
        query="document_list",
    )


def _stored_document_count(user, department, employee):
    """Return the count of visible stored employee document files."""
    query = _visible_employee_documents_query(user, department, employee)
    count = query.count()
    sources = (
        employee_document_source_cards(
            query.order_by(EmployeeDocument.uploaded_at.desc()).limit(SOURCE_CARD_LIMIT).all()
        )
        if count
        else []
    )
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            f"## {_stored_label(department, employee)}\n"
            f"- **Anzahl:** {count}\n"
            "- **Filter:** sichtbare Mitarbeiterdokument-Dateien\n"
            "- **Quelle:** Strukturierte Mitarbeiterdaten"
        ),
        count=count,
        filters=_document_filters(department, employee),
        sources=sources,
        structured_context=_document_context("stored_document_count", department, employee),
        query="stored_document_count",
    )


def _stored_document_list(user, department, employee):
    """Return visible employee document files with employee metadata."""
    query = _visible_employee_documents_query(user, department, employee).order_by(
        Employee.name.asc(), EmployeeDocument.uploaded_at.desc()
    )
    total_count = query.count()
    documents = query.limit(MAX_LIST_ITEMS).all()
    access_level = employee_access_level(user)
    items = []
    for document in documents:
        payload = document.to_dict()
        if document.employee:
            payload["employee_name"] = document.employee.name
            payload["employee_department"] = document.employee.department
            payload["employee"] = employee_payload_for_access_level(document.employee, access_level)
        items.append(payload)
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=_format_stored_document_answer(
            _stored_label(department, employee), documents, total_count
        ),
        count=total_count,
        items=items,
        filters=_document_filters(department, employee),
        sources=employee_document_source_cards(documents),
        structured_context=_document_context("stored_document_list", department, employee),
        extra={"returned_count": len(documents), "truncated": total_count > len(documents)},
        query="stored_document_list",
    )


def _no_such_employee(reference):
    """Return a grounded no-result outcome for an unknown employee name."""
    return QueryOutcome(
        entity_type="employees",
        scope="employees",
        answer_markdown=(
            "## Hinterlegte Mitarbeiterdokumente\n"
            f"- **Filter:** {reference}\n"
            "- **Status:** Kein sichtbarer Mitarbeiter mit diesem Namen gefunden\n"
            "- **Quelle:** Strukturierte Mitarbeiterdaten"
        ),
        filters={"employee": reference},
        structured_context=build_structured_context("employees"),
        query="stored_document_list",
    )


def _employees_with_documents_query(user, department):
    """Return visible employees with documents, optionally filtered by department."""
    query = (
        visible_employees_query(user)
        .join(EmployeeDocument, EmployeeDocument.employee_id == Employee.id)
        .distinct()
    )
    if department:
        query = query.filter(Employee.department.ilike(department))
    return query


def _visible_employee_documents_query(user, department, employee):
    """Return employee document rows visible through employee dashboard access."""
    query = EmployeeDocument.query.join(Employee, EmployeeDocument.employee_id == Employee.id)
    query = query.filter(
        EmployeeDocument.employee_id.in_(visible_employees_query(user).with_entities(Employee.id))
    )
    if department:
        query = query.filter(Employee.department.ilike(department))
    if employee is not None:
        query = query.filter(EmployeeDocument.employee_id == employee.id)
    return query


def _stored_label(department, employee):
    """Return the German label for stored document answers."""
    if employee is not None:
        return f"hinterlegte Dokumente fuer {employee.name}"
    if department:
        return f"hinterlegte Mitarbeiterdokumente in {department}"
    return "hinterlegte Mitarbeiterdokumente"


def _document_filters(department, employee):
    """Return public filters for document answers."""
    filters = {}
    if department:
        filters["department"] = department
    if employee is not None:
        filters["employee"] = employee.name
    return filters


def _document_context(query, department, employee):
    """Return structured memory for employee document answers."""
    fields = {"query": query, "department": department}
    if employee is not None:
        fields["employee_id"] = employee.id
        fields["employee_name"] = employee.name
    return build_structured_context("employees", **fields)


def _format_stored_document_answer(label, documents, total_count):
    """Return a compact German answer listing stored employee document files."""
    lines = [
        "## Hinterlegte Mitarbeiterdokumente",
        f"- **Filter:** {label}",
        f"- **Anzahl:** {total_count}",
        "- **Quelle:** Strukturierte Mitarbeiterdaten",
    ]
    if total_count > len(documents):
        lines.append(
            f"- **Hinweis:** {len(documents)} von {total_count} sichtbaren Dokumenten angezeigt"
        )
    if not documents:
        lines.append("")
        lines.append("Keine sichtbaren Mitarbeiterdokumente fuer diese Anfrage gefunden.")
        return "\n".join(lines)
    lines.append("")
    lines.append("Sichtbare Dokumente:")
    for document in documents[:MAX_ANSWER_ITEMS]:
        employee = document.employee
        employee_label = employee.name if employee else f"Mitarbeiter #{document.employee_id}"
        uploaded = (
            document.uploaded_at.strftime("%d.%m.%Y")
            if getattr(document, "uploaded_at", None)
            else ""
        )
        uploaded_label = f", {uploaded}" if uploaded else ""
        lines.append(f"- {document.original_filename} ({employee_label}{uploaded_label})")
    if len(documents) > MAX_ANSWER_ITEMS:
        lines.append(f"- ... {len(documents) - MAX_ANSWER_ITEMS} weitere sichtbare Dokumente")
    return "\n".join(lines)
