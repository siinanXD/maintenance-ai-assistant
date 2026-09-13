"""Order planning workflow using structured data and RAG context."""

from datetime import date

from app.models import (
    Employee,
    EmployeeMachineQualification,
    InventoryMaterial,
    Machine,
    ShiftPlanEntry,
)
from app.security import employee_access_level, has_dashboard_permission
from app.services.rag_service import build_rag_context

MAX_ORDER_QUANTITY = 1_000_000
REQUIRED_SCOPES = {"machines", "inventory", "employees"}
RAG_SCOPES = {"machines", "inventory", "employees", "documents", "shiftplans"}


def plan_order(data, user):
    """Return a production order planning preview for the requested payload."""
    payload, error = _normalize_order_payload(data, user)
    if error:
        return None, {"error": error}, 400

    missing_scopes = sorted(
        scope for scope in REQUIRED_SCOPES if not has_dashboard_permission(user, scope, "view")
    )
    if missing_scopes or employee_access_level(user) == "none":
        return (
            None,
            {
                "error": "order_planning_permission_denied",
                "message": "Missing permissions for order planning",
                "missing_scopes": missing_scopes or ["employees"],
            },
            403,
        )

    candidates = _machine_candidates(payload, user)
    rag_query = _rag_query(payload)
    rag = build_rag_context(rag_query, user, RAG_SCOPES)
    recommended = candidates[0] if candidates else None
    summary = _summary(payload, recommended, candidates)
    diagnostics = {
        "status": "local_answer",
        "workflow": "order_planning",
        "rag_enabled": rag["rag"]["enabled"],
        "rag_source_count": rag["rag"]["source_count"],
    }
    return (
        {
            "type": "order_plan",
            "request": payload,
            "summary": summary,
            "recommended_plan": recommended,
            "alternatives": candidates[1:4],
            "sources": rag["sources"],
            "diagnostics": diagnostics,
        },
        None,
        200,
    )


def _normalize_order_payload(data, user):
    """Validate and normalize order planning input data."""
    payload = data if isinstance(data, dict) else {}
    product = str(
        payload.get("product") or payload.get("produced_item") or payload.get("item") or ""
    ).strip()
    if not product:
        return None, "product is required"

    quantity, error = _positive_int(payload.get("quantity"), "quantity")
    if error:
        return None, error
    if quantity > MAX_ORDER_QUANTITY:
        return None, f"quantity must not exceed {MAX_ORDER_QUANTITY}"

    work_date, error = _parse_work_date(payload.get("due_date") or payload.get("work_date"))
    if error:
        return None, error

    department = str(payload.get("department") or "").strip()
    if not user.is_admin and user.department:
        department = user.department.name
    elif not department and user.department:
        department = user.department.name

    material_requirements, error = _normalize_material_requirements(
        payload.get("required_materials", [])
    )
    if error:
        return None, error

    return (
        {
            "product": product,
            "quantity": quantity,
            "work_date": work_date.isoformat(),
            "department": department,
            "required_materials": material_requirements,
        },
        None,
    )


def _positive_int(value, field_name):
    """Parse a positive integer input field."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{field_name} must be a positive integer"
    if parsed <= 0:
        return None, f"{field_name} must be a positive integer"
    return parsed, None


def _parse_work_date(value):
    """Parse an optional ISO work date, defaulting to today."""
    if value in (None, ""):
        return date.today(), None
    if isinstance(value, date):
        return value, None
    try:
        return date.fromisoformat(str(value)), None
    except ValueError:
        return None, "work_date must use YYYY-MM-DD"


def _normalize_material_requirements(raw_items):
    """Validate optional bill-of-material hints from the request."""
    if raw_items in (None, ""):
        return [], None
    if not isinstance(raw_items, list):
        return None, "required_materials must be a list"

    normalized = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            return None, "required_materials entries must be objects"
        quantity_per_unit, error = _positive_int(
            raw_item.get("quantity_per_unit", raw_item.get("per_unit", 1)),
            "quantity_per_unit",
        )
        if error:
            return None, error
        normalized.append(
            {
                "material_id": raw_item.get("material_id"),
                "name": str(raw_item.get("name") or "").strip(),
                "quantity_per_unit": quantity_per_unit,
            }
        )
    return normalized, None


def _machine_candidates(payload, user):
    """Return ranked machine planning candidates for the order payload."""
    product = payload["product"]
    machines = Machine.query.order_by(Machine.name.asc()).all()
    ranked = []
    for machine in machines:
        match_score = _machine_match_score(machine, product)
        if match_score <= 0:
            continue
        material_check = _material_check(machine, payload)
        staffing = _staffing_check(machine, payload, user)
        blockers = _candidate_blockers(material_check, staffing)
        status = "feasible" if not blockers else "blocked"
        score = (
            match_score
            + (40 if material_check["status"] == "enough" else 0)
            + (40 if staffing["status"] == "covered" else 0)
            - (25 * len(blockers))
        )
        ranked.append(
            {
                "machine": machine.to_dict(),
                "match_score": int(score),
                "status": status,
                "material_check": material_check,
                "staffing": staffing,
                "blockers": blockers,
            }
        )
    return sorted(ranked, key=lambda item: item["match_score"], reverse=True)


def _machine_match_score(machine, product):
    """Return a relevance score for machine/product matching."""
    normalized_product = product.lower()
    machine_name = machine.name.lower()
    produced_item = machine.produced_item.lower()
    score = 0
    if normalized_product in produced_item:
        score += 100
    if normalized_product in machine_name:
        score += 50
    product_tokens = _tokens(product)
    machine_tokens = _tokens(f"{machine.name} {machine.produced_item}")
    score += len(product_tokens & machine_tokens) * 20
    return score


def _material_check(machine, payload):
    """Return material availability for a machine and requested quantity."""
    requirements = _material_requirements_for_machine(machine, payload)
    if not requirements:
        return {
            "status": "unknown",
            "items": [],
            "missing": [],
            "message": "Keine Materialstueckliste fuer diese Maschine hinterlegt.",
        }

    missing = []
    items = []
    for requirement in requirements:
        material = requirement["material"]
        required_quantity = payload["quantity"] * requirement["quantity_per_unit"]
        shortage = max(required_quantity - material.quantity, 0)
        item = {
            "material": material.to_dict(),
            "quantity_per_unit": requirement["quantity_per_unit"],
            "required_quantity": required_quantity,
            "available_quantity": material.quantity,
            "shortage": shortage,
            "status": "enough" if shortage == 0 else "shortage",
        }
        items.append(item)
        if shortage:
            missing.append(item)

    return {
        "status": "enough" if not missing else "shortage",
        "items": items,
        "missing": missing,
        "message": (
            "Material reicht fuer die geplante Stueckzahl."
            if not missing
            else "Material reicht nicht fuer die geplante Stueckzahl."
        ),
    }


def _material_requirements_for_machine(machine, payload):
    """Return material requirements from payload hints or machine-linked stock."""
    explicit = payload.get("required_materials") or []
    if explicit:
        return [
            {"material": material, "quantity_per_unit": item["quantity_per_unit"]}
            for item in explicit
            for material in [_find_material(item, machine)]
            if material
        ]
    return [{"material": material, "quantity_per_unit": 1} for material in machine.materials]


def _find_material(requirement, machine):
    """Resolve a material requirement by id or name, preferring linked materials."""
    material_id = requirement.get("material_id")
    if material_id not in (None, ""):
        try:
            parsed_id = int(material_id)
        except (TypeError, ValueError):
            return None
        return InventoryMaterial.query.filter_by(id=parsed_id).first()

    name = requirement.get("name")
    if not name:
        return None
    linked = [material for material in machine.materials if material.name.lower() == name.lower()]
    if linked:
        return linked[0]
    return InventoryMaterial.query.filter(InventoryMaterial.name.ilike(name)).first()


def _staffing_check(machine, payload, user):
    """Return qualified employee coverage for a machine and work date."""
    work_date = date.fromisoformat(payload["work_date"])
    qualified = _qualified_employees(machine, payload.get("department"), work_date, user)
    assigned = qualified[: machine.required_employees]
    missing_count = max(machine.required_employees - len(assigned), 0)
    return {
        "status": "covered" if missing_count == 0 else "missing_staff",
        "required_employees": machine.required_employees,
        "assigned_employees": [employee.to_dict("basic") for employee in assigned],
        "qualified_available": [employee.to_dict("basic") for employee in qualified],
        "missing_count": missing_count,
        "message": (
            "Genug qualifiziertes Personal verfuegbar."
            if missing_count == 0
            else "Nicht genug qualifiziertes Personal verfuegbar."
        ),
    }


def _qualified_employees(machine, department, work_date, user):
    """Return employees qualified and not already planned on the target date."""
    query = Employee.query.order_by(Employee.name.asc())
    if department:
        query = query.filter(Employee.department == department)
    elif not user.is_admin and user.department:
        query = query.filter(Employee.department == user.department.name)

    occupied_employee_ids = {
        row.employee_id
        for row in ShiftPlanEntry.query.filter(ShiftPlanEntry.work_date == work_date).all()
    }
    employees = [employee for employee in query.all() if employee.id not in occupied_employee_ids]
    structured = _structured_qualified_employees(machine, employees, work_date)
    if structured:
        return structured
    return [
        employee
        for employee in employees
        if _matches_legacy_employee_qualification(employee, machine)
    ]


def _structured_qualified_employees(machine, employees, work_date):
    """Return employees with valid structured machine qualifications."""
    employee_ids = {employee.id for employee in employees}
    if not employee_ids:
        return []
    qualifications = (
        EmployeeMachineQualification.query.filter(
            EmployeeMachineQualification.machine_id == machine.id,
            EmployeeMachineQualification.employee_id.in_(employee_ids),
        )
        .order_by(EmployeeMachineQualification.level.desc())
        .all()
    )
    valid_ids = {
        qualification.employee_id
        for qualification in qualifications
        if qualification.is_valid_for(work_date)
    }
    return [employee for employee in employees if employee.id in valid_ids]


def _matches_legacy_employee_qualification(employee, machine):
    """Return whether legacy employee fields indicate machine fit."""
    haystack = " ".join(
        [
            employee.qualifications or "",
            employee.favorite_machine or "",
            str(employee.favorite_machine_id or ""),
        ]
    ).lower()
    return (
        machine.name.lower() in haystack
        or machine.produced_item.lower() in haystack
        or employee.favorite_machine_id == machine.id
    )


def _candidate_blockers(material_check, staffing):
    """Return human-readable blockers for one candidate plan."""
    blockers = []
    if material_check["status"] == "shortage":
        for item in material_check["missing"]:
            blockers.append(f"{item['material']['name']}: {item['shortage']} Stueck fehlen")
    elif material_check["status"] == "unknown":
        blockers.append(material_check["message"])
    if staffing["status"] != "covered":
        blockers.append(f"{staffing['missing_count']} qualifizierte Mitarbeitende fehlen")
    return blockers


def _summary(payload, recommended, candidates):
    """Return a compact planning summary."""
    if not candidates:
        return f"Keine passende Maschine fuer {payload['product']} gefunden."
    if recommended and recommended["status"] == "feasible":
        return (
            f"Auftrag fuer {payload['quantity']}x {payload['product']} ist planbar "
            f"auf {recommended['machine']['name']}."
        )
    return (
        f"Auftrag fuer {payload['quantity']}x {payload['product']} hat Blocker "
        f"auf der besten Maschine {recommended['machine']['name']}."
    )


def _rag_query(payload):
    """Build a retrieval query for planning-relevant knowledge."""
    return (
        f"Produktionsauftrag {payload['product']} {payload['quantity']} Stueck "
        "Maschine Material Personal Qualifikation Wartungsberichte Dokumentation"
    )


def _tokens(value):
    """Return lowercase matching tokens for simple product-machine matching."""
    return {
        token for token in str(value or "").lower().replace("-", " ").split() if len(token) >= 3
    }
