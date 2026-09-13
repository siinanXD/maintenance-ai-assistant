"""Realistic demo data for development and demos."""

import re
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

from sqlalchemy import or_
from werkzeug.datastructures import FileStorage

from app.demo_seed.assets import (
    INVENTORY_DEFINITIONS,
    INVENTORY_POLICY,
    MACHINE_DEFINITIONS,
    MACHINE_OPERATION_STATE,
)
from app.demo_seed.employees import EMPLOYEE_DATA
from app.demo_seed.knowledge import (
    ACTIVE_ERROR_STATES,
    INSPECTION_PLAN_DEFINITIONS,
    MAINTENANCE_PLAN_DEFINITIONS,
    MANUAL_DEFINITIONS,
    SHIFT_HANDOVER_DEFINITIONS,
    TRAINING_DEFINITIONS,
)
from app.demo_seed.tasks_errors import ERROR_DEFINITIONS, TASK_DEFINITIONS
from app.demo_seed.users import USER_DEFINITIONS
from app.departments.services import DEFAULT_DEPARTMENTS, ensure_default_departments
from app.extensions import db
from app.models import (
    AssistantTrainingEntry,
    Department,
    Employee,
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    KnowledgeChunk,
    KnowledgeDocument,
    Machine,
    MachineManual,
    MaintenancePlan,
    MaintenanceRecord,
    Priority,
    Role,
    ShiftHandover,
    Task,
    TaskStatus,
    User,
)
from app.permissions import upsert_default_permissions
from app.services.document_service import generate_maintenance_report, upload_machine_manual
from app.services.knowledge_service import reindex_stale_knowledge
from app.services.maintenance_tag_service import seed_maintenance_tag_library

DEMO_PASSWORD = "Demo1234!"


def seed_demo_data():
    """Create a complete, repeatable demo dataset."""
    ensure_default_departments()
    departments = _departments_by_name()
    employees = _seed_employees()
    db.session.flush()
    users = _seed_users(departments, employees)
    db.session.flush()
    for user in users.values():
        upsert_default_permissions(user)
    tag_summary = seed_maintenance_tag_library(
        created_by=users["admin"].id if users.get("admin") else None,
    )
    machines = _seed_machines()
    db.session.flush()
    _seed_inventory(machines)
    _link_employee_machines(employees, machines)
    _seed_errors(departments, machines)
    _seed_maintenance_plans(departments, users, machines)
    _seed_tasks(departments, users, machines)
    db.session.flush()
    _seed_documents(users)
    _seed_machine_manuals(users, machines)
    _seed_shift_handovers(users)
    _seed_training_entries(users)
    db.session.commit()
    knowledge_summary = reindex_stale_knowledge()
    return {
        "users": len(users),
        "employees": len(employees),
        "machines": len(machines),
        "inventory_materials": InventoryMaterial.query.count(),
        "maintenance_plans": MaintenancePlan.query.count(),
        "tasks": Task.query.count(),
        "errors": ErrorEntry.query.count(),
        "documents": GeneratedDocument.query.count(),
        "machine_manuals": MachineManual.query.count(),
        "shift_handovers": ShiftHandover.query.count(),
        "training_entries": AssistantTrainingEntry.query.count(),
        "knowledge_documents": KnowledgeDocument.query.count(),
        "knowledge_chunks": KnowledgeChunk.query.count(),
        "knowledge_documents_reindexed": knowledge_summary["indexed"],
        "maintenance_tag_entries": tag_summary["created"],
        "password": DEMO_PASSWORD,
    }


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _departments_by_name():
    """Return default departments indexed by name."""
    return {
        dep.name: dep
        for dep in Department.query.filter(Department.name.in_(DEFAULT_DEPARTMENTS)).all()
    }


def _seed_employees():
    """Create missing demo employees and return them by personnel number."""
    employees = {}
    for row in EMPLOYEE_DATA:
        (
            personnel_number,
            first_name,
            last_name,
            birth_date,
            street,
            postal_code,
            city,
            department,
            shift_model,
            current_shift,
            team,
            salary_group,
            qualifications,
        ) = row

        emp = Employee.query.filter_by(personnel_number=personnel_number).first()
        if not emp:
            emp = Employee(
                personnel_number=personnel_number,
                name=f"{first_name} {last_name}",
                birth_date=birth_date,
                street=street,
                postal_code=postal_code,
                city=city,
                department=department,
                shift_model=shift_model,
                current_shift=current_shift,
                team=team,
                salary_group=salary_group,
                qualifications=qualifications,
            )
            db.session.add(emp)
        employees[personnel_number] = emp
    return employees


def _seed_users(departments, employees):
    """Create missing demo users and link them to employees."""
    users = {}
    for username, email, role_value, dept_name, emp_nr in USER_DEFINITIONS:
        user = User.query.filter(or_(User.username == username, User.email == email)).first()
        if not user:
            user = User(
                username=username,
                email=email,
                role=Role(role_value),
                department=departments.get(dept_name),
                is_active=True,
            )
            db.session.add(user)
        user.role = Role(role_value)
        user.department = departments.get(dept_name)
        user.is_active = True
        user.set_password(DEMO_PASSWORD)
        if emp_nr and emp_nr in employees:
            user.employee = employees[emp_nr]
        users[username] = user
    return users


def _demo_key(value):
    """Return a stable ASCII key for demo lookup tables."""
    normalized = str(value or "").strip().lower()
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "ss",
        "Ä": "a",
        "Ö": "o",
        "Ü": "u",
        "×": "x",
        "²": "2",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def _machine_by_key(machines, machine_key):
    """Return a seeded machine by normalized demo key."""
    for machine_name, machine in machines.items():
        if _demo_key(machine_name) == machine_key:
            return machine
    return None


def _seed_machines():
    """Create missing demo machines and return them by name."""
    machines = {}
    for name, produced_item, required_employees in MACHINE_DEFINITIONS:
        machine = Machine.query.filter_by(name=name).first()
        if not machine:
            machine = Machine(
                name=name,
                produced_item=produced_item,
                required_employees=required_employees,
            )
            db.session.add(machine)
        criticality, status, downtime_days = MACHINE_OPERATION_STATE.get(
            _demo_key(name),
            ("normal", "running", None),
        )
        machine.produced_item = produced_item
        machine.required_employees = required_employees
        machine.criticality = criticality
        machine.status = status
        machine.last_downtime_at = (
            datetime.now(UTC) - timedelta(days=downtime_days) if downtime_days is not None else None
        )
        machines[name] = machine
    db.session.flush()
    return machines


def _link_employee_machines(employees, machines):
    """Assign deterministic favorite machines to demo employees."""
    machine_list = list(machines.values())
    for idx, emp in enumerate(employees.values()):
        machine = machine_list[idx % len(machine_list)]
        emp.favorite_machine = machine.name
        emp.favorite_machine_id = machine.id


def _seed_inventory(machines):
    """Create or update demo inventory materials."""
    for name, unit_cost, quantity, manufacturer, machine_name in INVENTORY_DEFINITIONS:
        material = InventoryMaterial.query.filter_by(name=name, manufacturer=manufacturer).first()
        if not material:
            material = InventoryMaterial(
                name=name,
                unit_cost=unit_cost,
                quantity=quantity,
                manufacturer=manufacturer,
                machine=machines.get(machine_name),
            )
            db.session.add(material)
        else:
            material.unit_cost = unit_cost
            material.quantity = quantity
            material.manufacturer = manufacturer
            material.machine = machines.get(machine_name)
        min_quantity, criticality, lead_time_days = INVENTORY_POLICY.get(
            _demo_key(name),
            (0, "normal", 0),
        )
        material.min_quantity = min_quantity
        material.criticality = criticality
        material.lead_time_days = lead_time_days


def _seed_errors(departments, machines):
    """Create demo error catalog entries for each default department."""
    now = datetime.now(UTC)
    for dept_name in ("Instandhaltung", "Produktion", "IT", "Verwaltung"):
        department = departments.get(dept_name)
        if not department:
            continue
        prefix = dept_name[:3].upper()
        for error_code_base, title, cause, solution, machine_name in ERROR_DEFINITIONS:
            error_code = f"{prefix}-{error_code_base}"
            existing = ErrorEntry.query.filter_by(
                error_code=error_code, department=department
            ).first()
            machine = machines.get(machine_name)
            if not existing:
                existing = ErrorEntry(
                    error_code=error_code,
                    department=department,
                )
                db.session.add(existing)
            existing.machine = machine_name
            existing.machine_id = machine.id if machine else None
            existing.title = title
            existing.description = (
                f"{title} – aufgetreten im Bereich {dept_name}. "
                "Störung absichern, Anlage prüfen, Maßnahme dokumentieren."
            )
            existing.possible_causes = cause
            existing.solution = solution
            _apply_demo_error_state(existing, dept_name, error_code_base, now)


def _apply_demo_error_state(entry, department_name, error_code_base, now):
    """Apply repeatable active/catalog state to a seeded error entry."""
    state = ACTIVE_ERROR_STATES.get((department_name, error_code_base))
    if state:
        entry.status = state["status"]
        entry.severity = state["severity"]
        entry.cause_category = state["cause_category"]
        entry.impact = state["impact"]
        entry.downtime_minutes = state["downtime_minutes"]
        entry.production_loss_minutes = state["production_loss_minutes"]
        entry.repeat_count = state["repeat_count"]
        entry.last_seen_at = now - timedelta(hours=state["seen_hours"])
        entry.closed_at = None
        return
    entry.status = "closed"
    entry.severity = "medium"
    entry.cause_category = ""
    entry.impact = ""
    entry.downtime_minutes = 0
    entry.production_loss_minutes = 0
    entry.repeat_count = 0
    entry.last_seen_at = None
    entry.closed_at = entry.closed_at or now - timedelta(days=14)


def _seed_maintenance_plans(departments, users, machines):
    """Create recurring maintenance plans linked to departments and machines."""
    priority_map = {"urgent": Priority.URGENT, "soon": Priority.SOON, "normal": Priority.NORMAL}
    creator = users.get("admin")
    if not creator:
        return
    today = date.today()
    for (
        title,
        description,
        interval_days,
        due_days,
        priority,
        dept_name,
        machine_key,
        is_active,
    ) in MAINTENANCE_PLAN_DEFINITIONS:
        department = departments.get(dept_name)
        machine = _machine_by_key(machines, machine_key)
        if not department:
            continue
        plan = MaintenancePlan.query.filter_by(
            title=title,
            department=department,
        ).first()
        if not plan:
            plan = MaintenancePlan(
                title=title,
                department=department,
                created_by=creator.id,
                interval_days=interval_days,
                next_due_date=today + timedelta(days=due_days),
            )
            db.session.add(plan)
        plan.description = description
        plan.interval_days = interval_days
        plan.next_due_date = today + timedelta(days=due_days)
        plan.priority = priority_map[priority]
        plan.is_active = is_active
        plan.machine = machine
    _seed_inspection_plans(departments, creator, machines, today)


def _seed_inspection_plans(departments, creator, machines, today):
    """Create legally required inspections with their last documented execution."""
    for (
        title,
        legal_basis,
        description,
        interval_days,
        due_days,
        dept_name,
        machine_key,
        last_execution,
    ) in INSPECTION_PLAN_DEFINITIONS:
        department = departments.get(dept_name)
        if not department:
            continue
        plan = MaintenancePlan.query.filter_by(title=title, department=department).first()
        if not plan:
            plan = MaintenancePlan(
                title=title,
                department=department,
                created_by=creator.id,
                interval_days=interval_days,
                next_due_date=today,
            )
            db.session.add(plan)
        plan.kind = "inspection"
        plan.legal_basis = legal_basis
        plan.description = description
        plan.interval_days = interval_days
        plan.next_due_date = today + timedelta(days=due_days)
        plan.priority = Priority.NORMAL
        plan.is_active = True
        plan.machine = _machine_by_key(machines, machine_key) if machine_key else None
        if last_execution and not plan.records:
            days_ago, performed_by, result, notes = last_execution
            plan.records.append(
                MaintenanceRecord(
                    performed_on=today - timedelta(days=days_ago),
                    performed_by=performed_by,
                    result=result,
                    notes=notes,
                    recorded_by=creator.id,
                )
            )


def _seed_tasks(departments, users, machines):
    """Create demo tasks across departments and workflow states."""
    today = date.today()
    now = datetime.now(UTC)

    priority_map = {"urgent": Priority.URGENT, "soon": Priority.SOON, "normal": Priority.NORMAL}
    status_map = {
        "open": TaskStatus.OPEN,
        "in_progress": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE,
    }
    creator = users.get("admin")

    for (
        title,
        description,
        prio_str,
        status_str,
        due_days,
        dept_name,
        _machine_name,
        worker_username,
    ) in TASK_DEFINITIONS:
        department = departments.get(dept_name)
        existing = Task.query.filter_by(title=title, department=department).first()
        status = status_map[status_str]
        worker = users.get(worker_username) if worker_username else None

        task = existing or Task(title=title, department=department)
        task.description = description
        task.priority = priority_map[prio_str]
        task.status = status
        task.due_date = today + timedelta(days=due_days)
        task.department = department
        if not existing:
            task.created_by = creator.id if creator else None

        task.current_worker_id = None
        task.completed_by_id = None
        task.started_at = None
        task.completed_at = None

        if status == TaskStatus.IN_PROGRESS and worker:
            task.current_worker_id = worker.id
            task.started_at = now - timedelta(hours=abs(due_days) * 3 + 2)

        if status == TaskStatus.DONE and worker:
            task.current_worker_id = worker.id
            task.started_at = now - timedelta(days=abs(due_days) + 1)
            task.completed_by_id = worker.id
            task.completed_at = now - timedelta(days=abs(due_days))

        _apply_task_operational_details(task, prio_str, status_str, due_days)
        if not existing:
            db.session.add(task)


def _apply_task_operational_details(task, priority_name, status_name, due_days):
    """Add realistic planning, effort and blocker metadata to a demo task."""
    base_minutes = {"urgent": 180, "soon": 120, "normal": 75}[priority_name]
    task.planned_minutes = base_minutes
    if status_name == "done":
        task.actual_minutes = max(30, base_minutes + (abs(due_days) * 8) - 12)
    elif status_name == "in_progress":
        task.actual_minutes = max(15, round(base_minutes * 0.45))
    else:
        task.actual_minutes = 0
    if "Dichtungssatz" in task.description or "Lager-Kit" in task.description:
        task.blocked_reason = "Wartet auf Ersatzteilfreigabe oder Materialbereitstellung."
    elif task.priority == Priority.URGENT and task.status == TaskStatus.OPEN:
        task.blocked_reason = "Stillstandsfenster muss mit Produktion abgestimmt werden."
    else:
        task.blocked_reason = ""
    task.reopened_count = 1 if task.status == TaskStatus.IN_PROGRESS and due_days <= 0 else 0


def _seed_documents(users):
    """Generate demo maintenance reports for completed tasks."""
    creator = users.get("admin")
    completed_tasks = (
        Task.query.filter(Task.status == TaskStatus.DONE).order_by(Task.id.asc()).limit(8).all()
    )
    for task in completed_tasks:
        existing = GeneratedDocument.query.filter_by(task_id=task.id).first()
        if existing:
            _enrich_generated_document(existing, creator)
            continue
        machine_name = _machine_for_task(task)
        document = generate_maintenance_report(
            task,
            creator,
            {
                "machine": machine_name,
                "cause": "Planmäßige Wartung oder gemeldete Störung laut Schichtbuch.",
                "action": (
                    "Prüfung durchgeführt, Befund dokumentiert, "
                    "Verschleißteile getauscht und Anlage freigegeben."
                ),
                "result": "Anlage läuft im Sollbereich, alle Grenzwerte eingehalten.",
                "notes": "Nächste Fälligkeitstermin in Wartungskalender eingetragen.",
            },
        )
        _enrich_generated_document(document, creator)


def _enrich_generated_document(document, user):
    """Attach review-ready demo metadata to a generated maintenance document."""
    document.status = "approved"
    document.summary_status = "completed"
    document.summary = (
        f"Freigegebener Wartungsbericht fuer {document.machine or 'Anlage'}; "
        "Massnahme abgeschlossen, Befund und Folgepruefung dokumentiert."
    )
    document.quality_score = 88
    document.quality_status = "checked"
    document.quality_checked_at = datetime.now(UTC)
    if user:
        document.approved_by = user.id
        document.approved_at = datetime.now(UTC)
        document.approval_comment = "Demo-Freigabe: vollstaendig und nachvollziehbar."


def _seed_machine_manuals(users, machines):
    """Create compact machine manuals that can be indexed by RAG."""
    creator = users.get("admin") or next(iter(users.values()), None)
    if not creator:
        return
    for machine_key, department, filename, title, content in MANUAL_DEFINITIONS:
        existing = MachineManual.query.filter_by(original_filename=filename).first()
        if existing:
            existing.title = title
            existing.department = department
            existing.summary = content.splitlines()[0] if content else title
            existing.summary_status = "completed"
            existing.analysis = _manual_analysis_text(title, content)
            existing.analysis_status = "completed"
            continue
        machine = _machine_by_key(machines, machine_key)
        file_storage = FileStorage(
            stream=BytesIO(content.encode("utf-8")),
            filename=filename,
            content_type="text/plain",
        )
        upload_machine_manual(
            file_storage,
            creator,
            machine_id=machine.id if machine else None,
            department=department,
        )
        manual = MachineManual.query.filter_by(original_filename=filename).first()
        if manual:
            manual.title = title
            manual.summary = content.splitlines()[0] if content else title
            manual.summary_status = "completed"
            manual.analysis = _manual_analysis_text(title, content)
            manual.analysis_status = "completed"


def _manual_analysis_text(title, content):
    """Return a short local analysis for seeded manuals."""
    return (
        f"{title}: Demo-Manual mit relevanten Fehlercodes, Sicherheitsfolge, "
        f"Ersatzteilhinweisen und freigegebenen Pruefschritten. Inhalt: {content[:500]}"
    )


def _seed_shift_handovers(users):
    """Create realistic digital shift handover records."""
    today = date.today()
    for (
        department,
        day_offset,
        shift_type,
        status,
        username,
        content,
        open_tasks,
        machine_notes,
        next_notes,
    ) in SHIFT_HANDOVER_DEFINITIONS:
        shift_date = today + timedelta(days=day_offset)
        existing = ShiftHandover.query.filter_by(
            department=department,
            shift_date=shift_date,
            shift_type=shift_type,
        ).first()
        user = users.get(username)
        if not existing:
            existing = ShiftHandover(
                department=department,
                shift_date=shift_date,
                shift_type=shift_type,
            )
            db.session.add(existing)
        existing.status = status
        existing.handed_over_by = user.id if user else None
        existing.handed_over_at = datetime.now(UTC) if status == "completed" else None
        existing.content = content
        existing.open_tasks = open_tasks
        existing.machine_notes = machine_notes
        existing.next_notes = next_notes


def _seed_training_entries(users):
    """Create curated demo assistant training entries for source-backed questions."""
    creator = users.get("admin")
    for (
        title,
        question,
        answer,
        keywords,
        category,
        department,
        priority,
        is_active,
    ) in TRAINING_DEFINITIONS:
        entry = AssistantTrainingEntry.query.filter_by(
            title=title,
            category=category,
        ).first()
        if not entry:
            entry = AssistantTrainingEntry(
                title=title,
                category=category,
                created_by=creator.id if creator else None,
            )
            db.session.add(entry)
        entry.question = question
        entry.answer = answer
        entry.keywords = keywords
        entry.department = department
        entry.priority = priority
        entry.is_active = is_active


def _machine_for_task(task):
    """Infer the most likely machine name for a demo task."""
    task_text = f"{task.title} {task.description}".lower()
    for name, _, _ in MACHINE_DEFINITIONS:
        if name.lower() in task_text:
            return name
        first_token = name.lower().split()[0]
        if len(first_token) > 4 and first_token in task_text:
            return name
    return MACHINE_DEFINITIONS[task.id % len(MACHINE_DEFINITIONS)][0]
