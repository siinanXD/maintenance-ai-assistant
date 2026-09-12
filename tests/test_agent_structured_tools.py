"""Tests for the parameter-driven structured agent tools."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agent.queries.common import build_structured_context
from app.agent.tools import TOOL_REGISTRY, available_tools, execute_tool, tool_spec
from app.extensions import db
from app.models import (
    EmployeeDocument,
    ErrorEntry,
    InventoryMaterial,
    Priority,
    Role,
    ShiftPlan,
    ShiftPlanCoverageSlot,
    ShiftPlanEntry,
    TaskStatus,
    User,
    VacationRequest,
)

STRUCTURED_TOOLS = (
    "list_tasks",
    "list_incidents",
    "count_records",
    "list_employees",
    "list_employee_documents",
    "list_vacations",
    "list_documents",
    "list_shift_entries",
    "list_inventory",
    "machine_incident_report",
)


def _user(user_id):
    """Return a user model for a fixture identity."""
    return db.session.get(User, user_id)


def _admin(make_user, username):
    """Create a master admin without department."""
    return make_user(username=username, role=Role.MASTER_ADMIN, department_name=None)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_structured_tools_are_registered_with_schemas():
    """Verify every structured tool exists with an object schema and a label."""
    for name in STRUCTURED_TOOLS:
        spec = TOOL_REGISTRY[name]
        assert spec.parameters["type"] == "object"
        assert spec.label
        assert spec.write is False
    assert tool_spec("machine_incident_report").extra_permissions == (("errors", "view"),)
    assert tool_spec("count_records").parameters["required"] == ["scope"]


def test_structured_tools_follow_permissions(app, make_user):
    """Verify tool availability follows dashboard permissions and employee access."""
    produktion = make_user(username="st_produktion", role=Role.PRODUKTION)
    admin = _admin(make_user, "st_admin")

    with app.app_context():
        produktion_tools = {spec.name for spec in available_tools(_user(produktion["id"]))}
        admin_tools = {spec.name for spec in available_tools(_user(admin["id"]))}

    assert {"list_tasks", "list_incidents", "count_records", "list_vacations"} <= produktion_tools
    assert "list_employees" not in produktion_tools
    assert "machine_incident_report" not in produktion_tools
    assert "list_inventory" not in produktion_tools
    assert set(STRUCTURED_TOOLS) <= admin_tools


def test_permission_denied_carries_answer_markdown(app, make_user):
    """Verify a denied structured tool returns the standard German denial text."""
    produktion = make_user(username="st_denied", role=Role.PRODUKTION)

    with app.app_context():
        result = execute_tool("list_employees", {}, _user(produktion["id"]))
        count = execute_tool("count_records", {"scope": "employees"}, _user(produktion["id"]))
        admin_users = execute_tool(
            "count_records", {"scope": "admin_users"}, _user(produktion["id"])
        )

    assert result.status == "permission_denied"
    assert "Keine Berechtigung" in result.content["answer_markdown"]
    assert count.status == "permission_denied"
    assert count.content["required_permission"] == ["employees", "view"]
    assert admin_users.status == "permission_denied"


# ---------------------------------------------------------------------------
# Tasks and incidents
# ---------------------------------------------------------------------------


def test_list_tasks_filters_status_priority_and_due(app, make_user, make_task):
    """Verify task filters and the count-only answer."""
    user = make_user(username="st_tasks_user", role=Role.INSTANDHALTUNG)
    make_task("Filter tauschen", user["username"], department_name="Produktion")
    make_task(
        "Dringend: Presse pruefen",
        user["username"],
        department_name="Produktion",
        priority=Priority.URGENT,
    )
    make_task(
        "Erledigt: Riemen",
        user["username"],
        department_name="Produktion",
        status=TaskStatus.DONE,
    )
    make_task(
        "Ueberfaellig",
        user["username"],
        department_name="Produktion",
        due_date_value=date.today() - timedelta(days=3),
    )

    with app.app_context():
        open_result = execute_tool("list_tasks", {"status": "open"}, _user(user["id"]))
        urgent = execute_tool("list_tasks", {"priority": "urgent"}, _user(user["id"]))
        due_today = execute_tool(
            "list_tasks", {"due": "today", "count_only": True}, _user(user["id"])
        )
        overdue = execute_tool("list_tasks", {"due": "overdue"}, _user(user["id"]))
        other_department = execute_tool(
            "list_tasks", {"department": "Instandhaltung"}, _user(user["id"])
        )

    assert open_result.status == "ok"
    assert open_result.content["count"] == 3
    assert open_result.content["answer_markdown"].startswith("## Tasks\n- **Anzahl:** 3")
    assert open_result.content["structured_context"] == {"entity_type": "tasks", "status": "open"}
    assert open_result.sources[0]["type"] == "task"
    assert urgent.content["count"] == 1
    assert urgent.content["items"][0]["title"] == "Dringend: Presse pruefen"
    assert due_today.content["count"] == 3
    assert "Sichtbare Treffer" not in due_today.content["answer_markdown"]
    assert due_today.content["answer_markdown"].startswith("## Heutige Tasks")
    assert overdue.content["count"] == 1
    assert overdue.content["items"][0]["title"] == "Ueberfaellig"
    assert other_department.content["count"] == 0
    assert "Keine passenden" in other_department.content["answer_markdown"]


def test_list_incidents_filters_and_groups_by_machine(app, make_user, make_error_entry):
    """Verify incident filters, severity, and the machine aggregation."""
    user = make_user(username="st_incidents_user", role=Role.INSTANDHALTUNG)
    make_error_entry("Presse 3", "E-100", "Druckverlust", department_name="Produktion")
    make_error_entry("Presse 3", "E-101", "Leckage", department_name="Produktion")
    make_error_entry("Ofen 1", "E-200", "Ueberhitzung", department_name="Produktion")
    with app.app_context():
        critical = db.session.get(ErrorEntry, 3)
        critical.severity = "critical"
        db.session.commit()

    with app.app_context():
        everything = execute_tool("list_incidents", {}, _user(user["id"]))
        critical_only = execute_tool(
            "list_incidents", {"severity": "critical", "count_only": True}, _user(user["id"])
        )
        by_machine = execute_tool("list_incidents", {"group_by": "machine"}, _user(user["id"]))
        machine_filter = execute_tool("list_incidents", {"machine": "Ofen"}, _user(user["id"]))

    assert everything.content["count"] == 3
    assert everything.content["entity_type"] == "incidents"
    assert critical_only.content["count"] == 1
    assert "## Stoerungen nach Maschine" in by_machine.content["answer_markdown"]
    assert by_machine.content["aggregation"]["top"]["machine"] == "Presse 3"
    assert by_machine.content["aggregation"]["top"]["count"] == 2
    assert machine_filter.content["count"] == 1


def test_count_records_counts_visible_rows_per_scope(app, make_user, make_task, make_machine):
    """Verify count_records respects visibility and admin-only scopes."""
    admin = _admin(make_user, "st_count_admin")
    produktion = make_user(username="st_count_produktion", role=Role.PRODUKTION)
    make_task("A", produktion["username"], department_name="Produktion")
    make_task("B", produktion["username"], department_name="Produktion")
    make_machine(name="Zaehl-Anlage")

    with app.app_context():
        tasks = execute_tool("count_records", {"scope": "tasks"}, _user(produktion["id"]))
        machines = execute_tool("count_records", {"scope": "machines"}, _user(admin["id"]))
        admin_users = execute_tool("count_records", {"scope": "admin_users"}, _user(admin["id"]))
        invalid = execute_tool("count_records", {"scope": "unicorns"}, _user(admin["id"]))

    assert tasks.content["count"] == 2
    assert tasks.content["answer_markdown"] == "## Tasks\n- **Gesamt:** 2\n- **Quelle:** Tasks"
    assert tasks.sources[0]["type"] == "module_count" or tasks.sources[0]["module"] == "tasks"
    assert machines.content["count"] == 1
    assert admin_users.content["count"] == 2
    assert invalid.status == "error"


# ---------------------------------------------------------------------------
# Employees, documents, vacations
# ---------------------------------------------------------------------------


def test_list_employees_redacts_fields_by_access_level(
    app, make_user, make_employee, set_dashboard_permission
):
    """Verify department filters, counts and shift-level field visibility."""
    hr = make_user(username="st_hr", role=Role.PERSONALABTEILUNG, department_name="Produktion")
    admin = _admin(make_user, "st_hr_admin")
    basic = make_user(username="st_basic", role=Role.PRODUKTION)
    set_dashboard_permission(
        basic["username"], "employees", can_view=True, employee_access_level="basic"
    )
    make_employee(personnel_number="P-1", name="Anna Arbeit", department="Produktion")
    make_employee(personnel_number="P-2", name="Ben Bauer", department="Produktion")
    make_employee(personnel_number="P-3", name="Cara Chef", department="Instandhaltung")

    with app.app_context():
        hr_all = execute_tool("list_employees", {}, _user(hr["id"]))
        admin_all = execute_tool("list_employees", {}, _user(admin["id"]))
        hr_count = execute_tool(
            "list_employees", {"department": "Produktion", "count_only": True}, _user(hr["id"])
        )
        basic_list = execute_tool(
            "list_employees", {"department": "Produktion"}, _user(basic["id"])
        )
        team_lead = execute_tool("list_employees", {"role": "team_lead"}, _user(hr["id"]))

    assert hr_all.content["count"] == 2
    assert admin_all.content["count"] == 3
    assert hr_all.content["structured_context"] == {
        "entity_type": "employees",
        "query": "total_list",
    }
    assert hr_count.content["count"] == 2
    assert "- **Bereich:** Produktion" in hr_count.content["answer_markdown"]
    assert basic_list.content["count"] == 2
    assert "qualifications" not in basic_list.content["items"][0]
    assert "personnel_number" in basic_list.content["items"][0]
    assert team_lead.content["reason"] == "team_lead_field_missing"


def test_list_employees_availability_uses_approved_vacations(app, make_user, make_employee):
    """Verify absent/available filters use approved vacations only."""
    hr = make_user(
        username="st_hr_avail", role=Role.PERSONALABTEILUNG, department_name="Produktion"
    )
    absent_id = make_employee(personnel_number="P-10", name="Urlaub Ute", department="Produktion")
    make_employee(personnel_number="P-11", name="Da Dieter", department="Produktion")
    tomorrow = date.today() + timedelta(days=1)
    with app.app_context():
        db.session.add(
            VacationRequest(
                employee_id=absent_id,
                start_date=tomorrow,
                end_date=tomorrow,
                days_used=1,
                status="approved",
            )
        )
        db.session.add(
            VacationRequest(
                employee_id=absent_id,
                start_date=date.today(),
                end_date=date.today(),
                days_used=1,
                status="pending",
            )
        )
        db.session.commit()

    with app.app_context():
        absent = execute_tool(
            "list_employees", {"availability": "absent_tomorrow"}, _user(hr["id"])
        )
        available_today = execute_tool(
            "list_employees", {"availability": "available_today"}, _user(hr["id"])
        )
        absences = execute_tool(
            "list_vacations", {"scope": "absences", "time_range": "tomorrow"}, _user(hr["id"])
        )
        pending = execute_tool(
            "list_vacations", {"scope": "pending", "count_only": True}, _user(hr["id"])
        )

    assert absent.content["count"] == 1
    assert absent.content["items"][0]["name"] == "Urlaub Ute"
    assert available_today.content["count"] == 2
    assert absences.content["count"] == 1
    assert "## Abwesenheiten" in absences.content["answer_markdown"]
    assert pending.content["count"] == 1
    assert pending.content["answer_markdown"].startswith(
        "## Offene Urlaubsantraege\n- **Anzahl:** 1"
    )


def test_list_vacations_own_scope_works_without_employee_permission(app, make_user, make_employee):
    """Verify own vacation scopes only need the user-employee link, not employees:view."""
    user = make_user(username="st_own_vacation", role=Role.PRODUKTION)
    employee_id = make_employee(personnel_number="P-20", name="Eigen Emil", department="Produktion")
    with app.app_context():
        account = _user(user["id"])
        account.employee_id = employee_id
        db.session.add(
            VacationRequest(
                employee_id=employee_id,
                start_date=date.today() + timedelta(days=10),
                end_date=date.today() + timedelta(days=12),
                days_used=3,
                status="pending",
            )
        )
        db.session.commit()

    with app.app_context():
        own = execute_tool("list_vacations", {"scope": "own_pending"}, _user(user["id"]))
        latest = execute_tool("list_vacations", {"scope": "own_latest"}, _user(user["id"]))
        invalid = execute_tool(
            "list_vacations", {"scope": "absences", "date_from": "gestern"}, _user(user["id"])
        )

    assert own.content["count"] == 1
    assert "Offene Antraege:** 1" in own.content["answer_markdown"]
    assert "- **Status:** offen" in latest.content["answer_markdown"]
    assert invalid.status == "error"


def test_list_employee_documents_counts_and_lists_files(app, make_user, make_employee):
    """Verify employees-with-documents and stored-document modes."""
    hr = make_user(username="st_hr_docs", role=Role.PERSONALABTEILUNG, department_name="Produktion")
    with_docs = make_employee(personnel_number="P-30", name="Doku Dana", department="Produktion")
    make_employee(personnel_number="P-31", name="Ohne Otto", department="Produktion")
    with app.app_context():
        db.session.add(
            EmployeeDocument(
                employee_id=with_docs,
                original_filename="zertifikat.pdf",
                stored_filename="x.pdf",
            )
        )
        db.session.commit()

    with app.app_context():
        employees = execute_tool("list_employee_documents", {}, _user(hr["id"]))
        count = execute_tool("list_employee_documents", {"count_only": True}, _user(hr["id"]))
        stored = execute_tool(
            "list_employee_documents",
            {"mode": "stored_documents", "employee": "Dana"},
            _user(hr["id"]),
        )
        unknown = execute_tool(
            "list_employee_documents",
            {"mode": "stored_documents", "employee": "Niemand"},
            _user(hr["id"]),
        )

    assert employees.content["count"] == 1
    assert employees.content["items"][0]["name"] == "Doku Dana"
    assert count.content["answer_markdown"].startswith(
        "## Mitarbeiter mit Dokumenten\n- **Anzahl:** 1"
    )
    assert stored.content["count"] == 1
    assert "zertifikat.pdf" in stored.content["answer_markdown"]
    assert stored.content["structured_context"]["employee_name"] == "Doku Dana"
    assert unknown.content["count"] == 0
    assert "Kein sichtbarer Mitarbeiter" in unknown.content["answer_markdown"]


# ---------------------------------------------------------------------------
# Documents, shift plans, inventory, machines
# ---------------------------------------------------------------------------


def test_list_documents_filters_metadata(app, make_user, make_task, make_document):
    """Verify recent, this-week, department and machine document filters."""
    user = _admin(make_user, "st_docs_admin")
    scoped = make_user(username="st_docs_scoped", role=Role.INSTANDHALTUNG)
    task_id = make_task("Doku-Task", user["username"], department_name="Produktion")
    make_document(task_id, user["id"], relative_path="2026/09/a.html", department="Produktion")
    make_document(
        task_id,
        user["id"],
        relative_path="2026/09/b.html",
        department="Instandhaltung",
        machine="Ofen 1",
    )

    with app.app_context():
        recent = execute_tool("list_documents", {"filter": "recent"}, _user(user["id"]))
        this_week = execute_tool("list_documents", {"filter": "this_week"}, _user(user["id"]))
        by_department = execute_tool(
            "list_documents",
            {"filter": "department", "department": "Produktion"},
            _user(user["id"]),
        )
        by_machine = execute_tool(
            "list_documents", {"filter": "machine", "machine": "Ofen"}, _user(user["id"])
        )
        missing = execute_tool("list_documents", {"filter": "machine"}, _user(user["id"]))
        scoped_recent = execute_tool("list_documents", {"filter": "recent"}, _user(scoped["id"]))

    assert scoped_recent.content["count"] == 1
    assert recent.content["count"] == 2
    assert this_week.content["count"] == 2
    assert by_department.content["count"] == 1
    assert by_machine.content["count"] == 1
    assert "relative_path" not in by_machine.content["items"][0]
    assert by_machine.content["structured_context"]["machine"] == "Ofen"
    assert missing.status == "error"


def test_list_shift_entries_uses_published_plans_and_redacts_names(
    app, make_user, make_employee, make_machine, set_dashboard_permission
):
    """Verify entries, counts and undercoverage come from published plans only."""
    planner = make_user(
        username="st_planner", role=Role.PERSONALABTEILUNG, department_name="Produktion"
    )
    viewer = make_user(username="st_shift_viewer", role=Role.PRODUKTION)
    set_dashboard_permission(viewer["username"], "shiftplans", can_view=True)
    employee_id = make_employee(
        personnel_number="P-40", name="Schicht Sabine", department="Produktion"
    )
    machine_id = make_machine(name="Schicht-Anlage")
    tomorrow = date.today() + timedelta(days=1)
    next_monday = date.today() + timedelta(days=7 - date.today().weekday())
    with app.app_context():
        published = ShiftPlan(
            title="Plan",
            start_date=date.today(),
            days=7,
            department="Produktion",
            status="published",
        )
        draft = ShiftPlan(
            title="Entwurf",
            start_date=date.today(),
            days=7,
            department="Produktion",
            status="draft",
        )
        db.session.add_all([published, draft])
        db.session.flush()
        db.session.add(
            ShiftPlanEntry(
                plan_id=published.id,
                employee_id=employee_id,
                machine_id=machine_id,
                work_date=tomorrow,
                shift="Frueh",
                start_time="06:00",
                end_time="14:00",
            )
        )
        db.session.add(
            ShiftPlanEntry(
                plan_id=draft.id,
                employee_id=employee_id,
                machine_id=machine_id,
                work_date=tomorrow,
                shift="Spaet",
                start_time="14:00",
                end_time="22:00",
            )
        )
        db.session.add(
            ShiftPlanCoverageSlot(
                plan_id=published.id,
                machine_id=machine_id,
                work_date=next_monday,
                shift="Nacht",
                required=2,
                assigned=1,
                missing=1,
            )
        )
        db.session.commit()

    with app.app_context():
        entries = execute_tool(
            "list_shift_entries", {"time_range": "tomorrow"}, _user(planner["id"])
        )
        early = execute_tool(
            "list_shift_entries",
            {"shift": "early", "date": tomorrow.isoformat()},
            _user(planner["id"]),
        )
        late = execute_tool("list_shift_entries", {"shift": "late"}, _user(planner["id"]))
        count = execute_tool(
            "list_shift_entries", {"mode": "count", "shift": "early"}, _user(planner["id"])
        )
        understaffed = execute_tool(
            "list_shift_entries", {"mode": "understaffed"}, _user(planner["id"])
        )
        redacted = execute_tool(
            "list_shift_entries", {"time_range": "tomorrow"}, _user(viewer["id"])
        )
        bad_shift = execute_tool("list_shift_entries", {"shift": "mittag"}, _user(planner["id"]))

    assert entries.content["count"] == 1
    assert "Schicht Sabine" in entries.content["answer_markdown"]
    assert early.content["count"] == 1
    assert late.content["count"] == 0
    assert count.content["count"] == 1
    assert understaffed.content["count"] == 1
    assert "fehlen 1" in understaffed.content["answer_markdown"]
    assert "Mitarbeiter nicht sichtbar" in redacted.content["answer_markdown"]
    assert redacted.content["items"][0]["employee"] is None
    assert bad_shift.status == "error"


def test_list_inventory_filters_low_stock_critical_and_machine(
    app, make_user, make_material, make_machine
):
    """Verify inventory filters and count-only mode."""
    user = make_user(username="st_inventory_user", role=Role.INSTANDHALTUNG)
    machine_id = make_machine(name="Presse 9")
    low_id = make_material("Dichtung", 5.0, 1, machine_id=machine_id)
    critical_id = make_material("Ventil", 50.0, 20)
    make_material("Schrauben", 0.1, 500)
    with app.app_context():
        db.session.get(InventoryMaterial, low_id).min_quantity = 5
        db.session.get(InventoryMaterial, critical_id).criticality = "critical"
        db.session.commit()

    with app.app_context():
        low = execute_tool("list_inventory", {"filter": "low_stock"}, _user(user["id"]))
        critical = execute_tool("list_inventory", {"filter": "critical"}, _user(user["id"]))
        by_machine = execute_tool(
            "list_inventory", {"filter": "machine", "machine": "Presse 9"}, _user(user["id"])
        )
        count = execute_tool("list_inventory", {"count_only": True}, _user(user["id"]))

    assert low.content["count"] == 1
    assert low.content["items"][0]["name"] == "Dichtung"
    assert low.content["items"][0]["is_below_minimum"] is True
    assert critical.content["items"][0]["name"] == "Ventil"
    assert by_machine.content["count"] == 1
    assert count.content["count"] == 3
    assert count.content["answer_markdown"].startswith("## Lager\n- **Sichtbare Artikel:** 3")


def test_machine_incident_report_needs_both_permissions(
    app, make_user, make_machine, make_error_entry, set_dashboard_permission
):
    """Verify the machine report resolves names and requires machines and errors access."""
    admin = _admin(make_user, "st_machine_admin")
    limited = make_user(username="st_machine_limited", role=Role.PRODUKTION)
    set_dashboard_permission(limited["username"], "machines", can_view=True)
    set_dashboard_permission(limited["username"], "errors", can_view=False)
    machine_id = make_machine(name="Hydraulikpresse 03")
    make_error_entry(
        "Hydraulikpresse 03", "INS-E-103", "Druck faellt ab", department_name="Produktion"
    )
    with app.app_context():
        entry = ErrorEntry.query.first()
        entry.machine_id = machine_id
        entry.downtime_minutes = 45
        db.session.commit()

    with app.app_context():
        assert "machine_incident_report" not in {
            spec.name for spec in available_tools(_user(limited["id"]))
        }
        denied = execute_tool(
            "machine_incident_report", {"machine": "Hydraulik"}, _user(limited["id"])
        )
        report = execute_tool(
            "machine_incident_report", {"machine": "hydraulikpresse"}, _user(admin["id"])
        )
        ranking = execute_tool("machine_incident_report", {}, _user(admin["id"]))
        unknown = execute_tool(
            "machine_incident_report", {"machine": "Nirgendwo"}, _user(admin["id"])
        )

    assert denied.status == "permission_denied"
    assert report.content["count"] == 1
    assert report.content["answer_markdown"].startswith("## Stoerungen an Hydraulikpresse 03")
    assert report.sources[0]["type"] == "machine"
    assert ranking.content["aggregation"]["top"]["total_downtime_minutes"] == 45
    assert "## Maschinenausfallzeit" in ranking.content["answer_markdown"]
    assert unknown.content["count"] == 0


# ---------------------------------------------------------------------------
# Knowledge tool and helpers
# ---------------------------------------------------------------------------


def test_search_knowledge_uses_hybrid_pipeline_and_empty_retrieval_text(
    app, make_user, make_error_entry
):
    """Verify the knowledge tool returns hybrid diagnostics and grounded no-answer text."""
    admin = _admin(make_user, "st_knowledge_admin")

    with app.app_context():
        empty = execute_tool(
            "search_knowledge",
            {"query": "Wie behebe ich Stoerung ZZ999 an Maschine Nirgendwo?"},
            _user(admin["id"]),
        )

    make_error_entry(
        "Presse 3", "E-104", "Sensor erkennt Produkt nicht", solution="Sensor reinigen."
    )

    with app.app_context():
        found = execute_tool(
            "search_knowledge", {"query": "Fehler E-104 Presse 3 Sensor"}, _user(admin["id"])
        )

    assert found.status == "ok"
    assert found.content["source_count"] >= 1
    assert found.content["empty_retrieval"] is False
    assert found.rag.get("query_understanding")
    assert "retrieval_debug" in found.rag
    assert empty.content["empty_retrieval"] is True
    assert empty.content["answer_markdown"].startswith("## Keine belastbare Quelle gefunden")
    assert "Gepruefte Datenquellen" in empty.content["answer_markdown"]


def test_build_structured_context_keeps_known_fields_only():
    """Verify structured context only carries whitelisted, bounded fields."""
    context = build_structured_context(
        "tasks", department="Produktion", status="open", secret="x", machine="A" * 200
    )

    assert context["entity_type"] == "tasks"
    assert context["department"] == "Produktion"
    assert "secret" not in context
    assert len(context["machine"]) == 120
    assert build_structured_context("") == {}


@pytest.mark.parametrize(
    "scope", ["tasks", "errors", "machines", "inventory", "documents", "shiftplans"]
)
def test_count_records_admin_sees_all_scopes(app, make_user, scope):
    """Verify master admins can count every non-employee scope."""
    admin = _admin(make_user, f"st_count_scope_{scope}")

    with app.app_context():
        result = execute_tool("count_records", {"scope": scope}, _user(admin["id"]))

    assert result.status == "ok"
    assert result.content["count"] == 0
