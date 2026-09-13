"""Safe source-card builders for structured AI answer rows."""

from datetime import UTC, datetime

from app.security import employee_access_level

SOURCE_CARD_LIMIT = 5

_MODULE_COUNT_SOURCES = {
    "admin_users": {
        "label": "Admin Users",
        "module": "admin_users",
        "url": "/admin/users",
    },
    "documents": {
        "label": "Dokumente",
        "module": "documents",
        "url": "/documents",
    },
    "employees": {
        "label": "Mitarbeiter",
        "module": "employees",
        "url": "/employees",
    },
    "errors": {
        "label": "Fehlerkatalog",
        "module": "errors",
        "url": "/errors",
    },
    "inventory": {
        "label": "Lager",
        "module": "inventory",
        "url": "/inventory",
    },
    "machines": {
        "label": "Maschinen",
        "module": "machines",
        "url": "/machines",
    },
    "shiftplans": {
        "label": "Schichtplanung",
        "module": "shiftplans",
        "url": "/shiftplans",
    },
    "tasks": {
        "label": "Tasks",
        "module": "tasks",
        "url": "/tasks",
    },
}


def task_source_cards(tasks, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible structured task rows."""
    return [_task_source_card(task) for task in list(tasks or [])[:limit]]


def incident_source_cards(incidents, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible structured incident rows."""
    return [_incident_source_card(incident) for incident in list(incidents or [])[:limit]]


def incident_source_cards_from_payloads(incidents, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards from already-visible incident payloads."""
    return [
        _incident_source_card_from_payload(incident) for incident in list(incidents or [])[:limit]
    ]


def machine_source_card(machine):
    """Return one compact source card for an already-visible machine row."""
    return _machine_source_card(machine) if machine else None


def inventory_source_cards(materials, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible inventory rows."""
    return [_inventory_source_card(material) for material in list(materials or [])[:limit]]


def employee_source_cards(employees, user, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible employee rows."""
    access_level = employee_access_level(user)
    return [
        _employee_source_card(employee, access_level) for employee in list(employees or [])[:limit]
    ]


def employee_document_source_cards(documents, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for visible employee document file rows."""
    return [
        _employee_document_source_card(document)
        for document in list(documents or [])[:limit]
        if document is not None
    ]


def employee_count_source_card(count, user, department=""):
    """Return one compact aggregate source card for an employee count answer."""
    if count is None:
        return None
    source = module_count_source_card("employees", count, user)
    if not source:
        return None
    safe_department = str(department or "")[:120]
    if safe_department:
        source["department"] = safe_department
        source["role_visibility"] = _role_visibility(safe_department)
    return source


def document_source_cards(documents, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible generated documents."""
    return [_document_source_card(document) for document in list(documents or [])[:limit]]


def manual_source_cards(manuals, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible machine manuals."""
    return [_manual_source_card(manual) for manual in list(manuals or [])[:limit]]


def shiftplan_entry_source_cards(entries, user=None, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible shift plan entries."""
    access_level = employee_access_level(user) if user else "basic"
    return [
        _shiftplan_entry_source_card(entry, access_level) for entry in list(entries or [])[:limit]
    ]


def shiftplan_coverage_source_cards(slots, limit=SOURCE_CARD_LIMIT):
    """Return compact source cards for already-visible shift coverage slots."""
    return [_shiftplan_coverage_source_card(slot) for slot in list(slots or [])[:limit]]


def vacation_source_cards(vacations, limit=SOURCE_CARD_LIMIT, role_visibility=""):
    """Return compact source cards for already-visible vacation rows."""
    return [
        _vacation_source_card(vacation, role_visibility)
        for vacation in list(vacations or [])[:limit]
    ]


def module_count_source_card(scope, count, user):
    """Return one compact aggregate source card for a visible module count."""
    if count is None:
        return None

    config = _MODULE_COUNT_SOURCES.get(scope)
    if not config:
        return None

    source = {
        "type": "aggregate",
        "id": None,
        "title": f"{config['label']} Anzahl",
        "module": config["module"],
        "url": config["url"],
        "source_type": "module_count",
        "source_id": None,
        "source_record_id": None,
        "source_kind": "structured_aggregate",
        "role_visibility": _module_count_role_visibility(scope, user),
        "created_at": datetime.now(UTC).isoformat(),
        "count": count,
    }
    if scope == "employees":
        source["employee_access_level"] = employee_access_level(user)
    return source


def _task_source_card(task):
    """Return one prompt-safe task source card."""
    department = _department_name(task)
    return {
        "type": "task",
        "id": task.id,
        "title": task.title,
        "module": "tasks",
        "url": "/tasks",
        "source_type": "task",
        "source_id": task.id,
        "source_record_id": task.id,
        "source_kind": "structured",
        "department": department,
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(task.created_at),
        "status": task.status.value if task.status else "",
        "priority": task.priority.value if task.priority else "",
        "due_date": task.due_date.isoformat() if task.due_date else "",
    }


def _incident_source_card(incident):
    """Return one prompt-safe incident source card."""
    department = _department_name(incident)
    return {
        "type": "error",
        "id": incident.id,
        "title": _incident_source_title(incident.error_code, incident.title),
        "module": "errors",
        "url": "/errors",
        "source_type": "error",
        "source_id": incident.id,
        "source_record_id": incident.id,
        "source_kind": "structured",
        "department": department,
        "machine": incident.machine,
        "machine_id": incident.machine_id,
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(incident.created_at),
        "status": incident.status,
        "severity": incident.severity,
        "error_code": incident.error_code,
    }


def _incident_source_card_from_payload(incident):
    """Return one prompt-safe incident source card from a public payload."""
    department = _payload_department_name(incident)
    incident_id = incident.get("id")
    return {
        "type": "error",
        "id": incident_id,
        "title": _incident_source_title(incident.get("error_code"), incident.get("title")),
        "module": "errors",
        "url": "/errors",
        "source_type": "error",
        "source_id": incident_id,
        "source_record_id": incident_id,
        "source_kind": "structured",
        "department": department,
        "machine": incident.get("machine") or "",
        "machine_id": incident.get("machine_id"),
        "role_visibility": _role_visibility(department),
        "created_at": incident.get("created_at") or "",
        "status": incident.get("status") or "",
        "severity": incident.get("severity") or "",
        "error_code": incident.get("error_code") or "",
    }


def _machine_source_card(machine):
    """Return one prompt-safe machine source card."""
    return {
        "type": "machine",
        "id": machine.id,
        "title": machine.name,
        "module": "machines",
        "url": "/machines",
        "source_type": "machine",
        "source_id": machine.id,
        "source_record_id": machine.id,
        "source_kind": "structured",
        "machine_id": machine.id,
        "machine": machine.name,
        "role_visibility": "public",
        "created_at": _isoformat(machine.created_at),
        "status": machine.status,
        "criticality": machine.criticality,
        "produced_item": machine.produced_item,
        "site_id": machine.site_id,
        "last_downtime_at": _isoformat(machine.last_downtime_at),
    }


def _inventory_source_card(material):
    """Return one prompt-safe inventory source card."""
    machine = getattr(material, "machine", None)
    return {
        "type": "inventory",
        "id": material.id,
        "title": str(getattr(material, "name", "") or "")[:160],
        "module": "inventory",
        "url": "/inventory",
        "source_type": "inventory",
        "source_id": material.id,
        "source_record_id": material.id,
        "source_kind": "structured",
        "role_visibility": "public",
        "created_at": _isoformat(material.created_at),
        "name": str(getattr(material, "name", "") or "")[:160],
        "quantity": material.quantity,
        "min_quantity": material.min_quantity,
        "criticality": str(getattr(material, "criticality", "") or "")[:40],
        "lead_time_days": material.lead_time_days,
        "manufacturer": str(getattr(material, "manufacturer", "") or "")[:160],
        "machine_id": material.machine_id,
        "machine": str(getattr(machine, "name", "") or "")[:160],
    }


def _employee_document_source_card(document):
    """Return one prompt-safe source card for an employee document file."""
    employee = getattr(document, "employee", None)
    employee_name = str(getattr(employee, "name", "") or "")[:160]
    department = str(getattr(employee, "department", "") or "")[:120]
    filename = str(getattr(document, "original_filename", "") or "")[:160]
    payload = document.to_dict() if hasattr(document, "to_dict") else {}
    download_url = str(payload.get("download_url") or "")[:240]
    return {
        "type": "employee_document",
        "id": getattr(document, "id", None),
        "title": filename or "Mitarbeiterdokument",
        "module": "employees",
        "url": download_url or "/employees",
        "source_type": "employee_document",
        "source_id": getattr(document, "id", None),
        "source_record_id": getattr(document, "id", None),
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(getattr(document, "uploaded_at", None)),
        "employee_id": getattr(document, "employee_id", None),
        "employee_name": employee_name,
        "original_filename": filename,
    }


def _employee_source_card(employee, access_level):
    """Return one prompt-safe employee source card."""
    department = str(getattr(employee, "department", "") or "")[:120]
    employee_name = str(getattr(employee, "name", "") or "")[:160]
    return {
        "type": "employee",
        "id": employee.id,
        "title": employee_name,
        "module": "employees",
        "url": "/employees",
        "source_type": "employee",
        "source_id": employee.id,
        "source_record_id": employee.id,
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(employee.created_at),
        "employee_access_level": str(access_level or "none"),
        "department": department,
    }


def _document_source_card(document):
    """Return one prompt-safe generated-document source card."""
    department = str(getattr(document, "department", "") or "")[:120]
    return {
        "type": "document",
        "id": document.id,
        "title": str(getattr(document, "title", "") or "")[:180],
        "module": "documents",
        "url": "/documents",
        "source_type": "generated_document",
        "source_id": document.id,
        "source_record_id": document.id,
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(document.created_at),
        "updated_at": _document_updated_at(document),
        "document_type": str(getattr(document, "document_type", "") or "")[:80],
        "department": department,
        "machine": str(getattr(document, "machine", "") or "")[:160],
        "machine_id": getattr(document, "machine_id", None),
        "status": str(getattr(document, "status", "") or "")[:40],
        "quality_status": str(getattr(document, "quality_status", "") or "")[:40],
    }


def _manual_source_card(manual):
    """Return one prompt-safe machine-manual source card."""
    department = str(getattr(manual, "department", "") or "")[:120]
    machine = getattr(manual, "machine", None)
    return {
        "type": "machine_manual",
        "id": manual.id,
        "title": str(getattr(manual, "title", "") or "")[:180],
        "module": "documents",
        "url": "/documents",
        "source_type": "machine_manual",
        "source_id": manual.id,
        "source_record_id": manual.id,
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(manual.created_at),
        "updated_at": _isoformat(manual.updated_at),
        "document_type": "machine_manual",
        "department": department,
        "machine": str(getattr(machine, "name", "") or "")[:160],
        "machine_id": getattr(manual, "machine_id", None),
    }


def _shiftplan_entry_source_card(entry, access_level):
    """Return one prompt-safe shift-plan entry source card."""
    plan = getattr(entry, "plan", None)
    employee = getattr(entry, "employee", None)
    machine = getattr(entry, "machine", None)
    department = str(getattr(plan, "department", "") or "")[:120]
    employee_name = str(getattr(employee, "name", "") or "")[:160] if access_level != "none" else ""
    title = (
        f"{employee_name} {entry.work_date.isoformat()} {entry.shift}".strip()
        if employee_name
        else f"Schichtplaneintrag {entry.work_date.isoformat()} {entry.shift}".strip()
    )
    return {
        "type": "shiftplan_entry",
        "id": entry.id,
        "title": title,
        "module": "shiftplans",
        "url": "/shiftplans",
        "source_type": "shiftplan_entry",
        "source_id": entry.id,
        "source_record_id": entry.id,
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(entry.created_at),
        "plan_id": entry.plan_id,
        "department": department,
        "employee_id": entry.employee_id,
        "employee_name": employee_name,
        "machine_id": entry.machine_id,
        "machine": str(getattr(machine, "name", "") or "")[:160],
        "work_date": entry.work_date.isoformat() if entry.work_date else "",
        "shift": str(getattr(entry, "shift", "") or "")[:80],
        "start_time": str(getattr(entry, "start_time", "") or "")[:5],
        "end_time": str(getattr(entry, "end_time", "") or "")[:5],
    }


def _shiftplan_coverage_source_card(slot):
    """Return one prompt-safe shift coverage source card."""
    plan = getattr(slot, "plan", None)
    machine = getattr(slot, "machine", None)
    department = str(getattr(plan, "department", "") or "")[:120]
    return {
        "type": "shiftplan_coverage",
        "id": slot.id,
        "title": f"Unterdeckung {slot.work_date.isoformat()} {slot.shift}".strip(),
        "module": "shiftplans",
        "url": "/shiftplans",
        "source_type": "shiftplan_coverage",
        "source_id": slot.id,
        "source_record_id": slot.id,
        "source_kind": "structured",
        "role_visibility": _role_visibility(department),
        "created_at": _isoformat(slot.created_at),
        "plan_id": slot.plan_id,
        "department": department,
        "machine_id": slot.machine_id,
        "machine": str(getattr(machine, "name", "") or "")[:160],
        "work_date": slot.work_date.isoformat() if slot.work_date else "",
        "shift": str(getattr(slot, "shift", "") or "")[:80],
        "required": slot.required,
        "assigned": slot.assigned,
        "missing": slot.missing,
    }


def _vacation_source_card(vacation, role_visibility):
    """Return one prompt-safe vacation source card."""
    employee = getattr(vacation, "employee", None)
    department = str(getattr(employee, "department", "") or "")[:120]
    employee_name = str(getattr(employee, "name", "") or "")[:160]
    return {
        "type": "vacation_request",
        "id": vacation.id,
        "title": _vacation_source_title(vacation, employee_name),
        "module": "vacations",
        "url": "/vacations",
        "source_type": "vacation_request",
        "source_id": vacation.id,
        "source_record_id": vacation.id,
        "source_kind": "structured",
        "role_visibility": role_visibility or _role_visibility(department),
        "created_at": _isoformat(vacation.created_at),
        "employee_id": vacation.employee_id,
        "employee_name": employee_name,
        "department": department,
        "start_date": vacation.start_date.isoformat() if vacation.start_date else "",
        "end_date": vacation.end_date.isoformat() if vacation.end_date else "",
        "days_used": vacation.days_used,
        "status": vacation.status,
        "shift_type": vacation.shift_type,
    }


def _vacation_source_title(vacation, employee_name):
    """Return a compact vacation source title."""
    start_date = vacation.start_date.isoformat() if vacation.start_date else ""
    end_date = vacation.end_date.isoformat() if vacation.end_date else ""
    return f"Urlaub {employee_name} {start_date} bis {end_date}".strip()


def _incident_source_title(error_code, title):
    """Return the compact incident source title."""
    safe_title = str(title or "").strip()
    safe_code = str(error_code or "").strip()
    return f"{safe_code} - {safe_title}" if safe_code else safe_title


def _department_name(record):
    """Return a bounded department name from a structured row."""
    department = getattr(record, "department", None)
    if isinstance(department, str):
        return department[:120]
    return str(getattr(department, "name", "") or "")[:120]


def _payload_department_name(payload):
    """Return a bounded department name from a structured row payload."""
    department = payload.get("department") if isinstance(payload, dict) else None
    if isinstance(department, dict):
        return str(department.get("name") or "")[:120]
    return str(department or "")[:120]


def _role_visibility(department):
    """Return a compact role visibility label for structured source cards."""
    return f"department:{department}" if department else "public"


def _module_count_role_visibility(scope, user):
    """Return a compact role visibility label for module count source cards."""
    if scope == "admin_users":
        return "admin_only"

    department = getattr(getattr(user, "department", None), "name", "")
    return _role_visibility(str(department or "")[:120])


def _isoformat(value):
    """Return an ISO timestamp when available."""
    return value.isoformat() if value else ""


def _document_updated_at(document):
    """Return the latest safe timestamp for a generated document."""
    version = getattr(document, "current_version", None)
    version_created_at = getattr(version, "created_at", None)
    return _isoformat(version_created_at or getattr(document, "created_at", None))
