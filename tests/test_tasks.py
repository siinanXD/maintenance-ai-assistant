"""Tests for task workflows."""

from datetime import date, timedelta
from pathlib import Path

from app.extensions import db
from app.models import OperationalEvent, Priority, Role, ShiftHandover, TaskStatus, User
from app.services.ai_service import AIServiceError

REPO_ROOT = Path(__file__).resolve().parents[1]


def task_react_source():
    """Return the combined React task island source."""
    source_paths = list((REPO_ROOT / "frontend" / "src" / "tasks").rglob("*.ts"))
    source_paths.extend((REPO_ROOT / "frontend" / "src" / "tasks").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def test_task_create_list_filter_and_update(client, make_user, auth_headers):
    """Verify task CRUD basics and valid status or priority filtering."""
    user = make_user(
        username="task_owner",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    create_response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": "Motor pruefen",
            "description": "Motor laeuft unruhig",
            "department": "Instandhaltung",
            "due_date": "2026-05-02",
            "priority": "urgent",
        },
    )
    list_response = client.get(
        "/api/v1/tasks?status=open&priority=urgent",
        headers=headers,
    )
    task_id = create_response.get_json()["id"]
    update_response = client.put(
        f"/api/v1/tasks/{task_id}",
        headers=headers,
        json={"status": "in_progress", "priority": "soon"},
    )

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert len(list_response.get_json()["data"]) == 1
    assert update_response.status_code == 200
    assert update_response.get_json()["status"] == "in_progress"
    assert update_response.get_json()["current_worker_id"] == user["id"]


def test_task_routes_require_token(client):
    """Verify protected task routes reject unauthenticated requests."""
    response = client.get("/api/v1/tasks")

    assert response.status_code == 401


def test_task_validation_rejects_bad_payloads(client, make_user, auth_headers):
    """Verify task creation and filtering reject malformed edgecase values."""
    user = make_user(
        username="task_validation",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    missing_title = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"department": "Instandhaltung"},
    )
    blank_title = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "   ", "department": "Instandhaltung"},
    )
    bad_date = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": "Datum kaputt",
            "department": "Instandhaltung",
            "due_date": "05-02-2026",
        },
    )
    bad_filter = client.get("/api/v1/tasks?status=unknown", headers=headers)

    assert missing_title.status_code == 400
    assert blank_title.status_code == 400
    assert bad_date.status_code == 400
    assert bad_filter.status_code == 400


def test_non_admin_cannot_write_task_for_other_department(
    client,
    make_user,
    auth_headers,
):
    """Verify department-scoped users cannot create tasks for another department."""
    user = make_user(
        username="department_guard",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers(user["username"]),
        json={"title": "Fremder Task", "department": "Instandhaltung"},
    )

    assert response.status_code == 403


def test_task_detail_is_forbidden_across_departments(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify users cannot read task details from another department."""
    owner = make_user(
        username="other_task_owner",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    requester = make_user(
        username="task_requester",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    task_id = make_task(
        "Fremde Aufgabe",
        creator_username=owner["username"],
        department_name="Instandhaltung",
    )

    response = client.get(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(requester["username"]),
    )

    assert response.status_code == 403


def test_task_start_and_complete_edgecases(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify workflow endpoints handle repeated and invalid status transitions."""
    user = make_user(username="workflow_user")
    headers = auth_headers(user["username"])
    task_id = make_task("Workflow", creator_username=user["username"])
    done_task_id = make_task(
        "Already done",
        creator_username=user["username"],
        status=TaskStatus.DONE,
    )
    cancelled_task_id = make_task(
        "Cancelled",
        creator_username=user["username"],
        status=TaskStatus.CANCELLED,
    )

    start_response = client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    second_start_response = client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    complete_response = client.post(f"/api/v1/tasks/{task_id}/complete", headers=headers)
    second_complete_response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=headers,
    )
    start_done_response = client.post(f"/api/v1/tasks/{done_task_id}/start", headers=headers)
    complete_cancelled_response = client.post(
        f"/api/v1/tasks/{cancelled_task_id}/complete",
        headers=headers,
    )

    assert start_response.status_code == 200
    assert second_start_response.status_code == 409
    assert complete_response.status_code == 200
    assert complete_response.get_json()["completed_by"] == user["id"]
    assert second_complete_response.status_code == 409
    assert start_done_response.status_code == 400
    assert complete_cancelled_response.status_code == 400


def test_task_create_start_complete_workflow(client, make_user, auth_headers):
    """Verify the public task workflow endpoints match the frontend contract."""
    user = make_user(
        username="workflow_create_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    create_response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": "Workflow Ende zu Ende",
            "department": "Instandhaltung",
            "priority": "normal",
            "status": "open",
        },
    )
    task_id = create_response.get_json()["id"]
    start_response = client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    complete_response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=headers,
        json={},
    )

    assert create_response.status_code == 201
    assert start_response.status_code == 200
    assert start_response.get_json()["status"] == "in_progress"
    assert complete_response.status_code == 200
    assert complete_response.get_json()["status"] == "done"
    assert complete_response.get_json()["completed_by"] == user["id"]


def test_task_payload_embeds_only_public_user_references(client, make_user, auth_headers):
    """Verify tasks do not leak emails, permission matrices or employee data of other users."""
    worker = make_user(
        username="task_privacy_worker",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(worker["username"])
    task_id = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Datenschutz pruefen", "department": "Instandhaltung", "priority": "normal"},
    ).get_json()["id"]
    client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    client.post(f"/api/v1/tasks/{task_id}/complete", headers=headers, json={})

    task = client.get(f"/api/v1/tasks/{task_id}", headers=headers).get_json()
    listed = client.get("/api/v1/tasks?limit=5", headers=headers).get_json()

    for field in ("creator", "current_worker", "completed_by_user"):
        embedded = task[field]
        if embedded is None:
            continue
        assert set(embedded) == {"id", "username", "role"}
        assert embedded["username"] == worker["username"]
    assert "permissions" not in str(listed)
    assert worker["username"] + "@" not in str(listed)


def test_task_workflow_errors_use_consistent_payload(client, make_user, auth_headers):
    """Verify workflow errors expose success, short error code and message."""
    user = make_user(username="workflow_error_shape")

    response = client.post(
        "/api/v1/tasks/999/start",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 404
    assert payload["success"] is False
    assert payload["message"] == "Task not found"
    assert payload["error"] == "task_not_found"


def test_today_tasks_only_returns_current_date(client, make_user, make_task, auth_headers):
    """Verify the today endpoint filters visible tasks by server date."""
    user = make_user(username="today_user")
    make_task(
        "Heute",
        creator_username=user["username"],
        due_date_value=date.today(),
    )
    make_task(
        "Nicht heute",
        creator_username=user["username"],
        due_date_value=date.today() + timedelta(days=1),
    )

    response = client.get("/api/v1/tasks/today", headers=auth_headers(user["username"]))

    assert response.status_code == 200
    assert [task["title"] for task in response.get_json()] == ["Heute"]


def test_prioritize_tasks_only_returns_visible_department(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify task prioritization respects department visibility."""
    requester = make_user(
        username="priority_requester",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    other_user = make_user(
        username="priority_other",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_task(
        "Eigener Task",
        creator_username=requester["username"],
        department_name="Produktion",
    )
    make_task(
        "Fremder Task",
        creator_username=other_user["username"],
        department_name="Instandhaltung",
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(requester["username"]),
        json={"status": "open"},
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert [item["task"]["title"] for item in payload] == ["Eigener Task"]


def test_prioritize_tasks_rejects_invalid_filters(client, make_user, auth_headers):
    """Verify task prioritization rejects invalid status and limit values."""
    user = make_user(username="priority_validation")
    headers = auth_headers(user["username"])

    bad_status = client.post(
        "/api/v1/tasks/prioritize",
        headers=headers,
        json={"status": "unknown"},
    )
    bad_limit = client.post(
        "/api/v1/tasks/prioritize",
        headers=headers,
        json={"limit": 0},
    )
    bad_mode = client.post(
        "/api/v1/tasks/prioritize",
        headers=headers,
        json={"mode": "remote"},
    )

    assert bad_status.status_code == 400
    assert bad_limit.status_code == 400
    assert bad_mode.status_code == 400


def test_prioritize_tasks_sorts_urgent_overdue_before_normal(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify local prioritization ranks urgent overdue tasks first."""
    user = make_user(username="priority_sort")
    make_task(
        "Normaler Rundgang",
        creator_username=user["username"],
        priority=Priority.NORMAL,
        due_date_value=date.today() + timedelta(days=5),
        description="Routinepruefung",
    )
    make_task(
        "Stillstand an Anlage 4",
        creator_username=user["username"],
        priority=Priority.URGENT,
        due_date_value=date.today() - timedelta(days=1),
        description="Anlage steht seit gestern mit Sensorfehler",
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"status": "open"},
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload[0]["task"]["title"] == "Stillstand an Anlage 4"
    assert payload[0]["score"] > payload[1]["score"]
    assert payload[0]["risk_level"] in {"high", "critical"}


def test_prioritize_tasks_uses_local_fallback_without_openai_key(
    client,
    make_user,
    make_task,
    auth_headers,
):
    """Verify task prioritization works with the configured local provider."""
    user = make_user(username="priority_fallback")
    make_task(
        "Sensor pruefen",
        creator_username=user["username"],
        priority=Priority.SOON,
        description="Sensor meldet sporadisch kein Signal",
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert len(payload) == 1
    assert set(payload[0]) == {
        "task",
        "score",
        "risk_level",
        "reason",
        "recommended_action",
        "confidence",
        "evidence_counts",
        "evidence_references",
        "next_steps",
    }
    assert payload[0]["confidence"]["level"] in {"low", "medium", "high"}
    assert payload[0]["confidence"]["uncertainty"] in {"low", "medium", "high"}
    assert payload[0]["confidence"]["uses_only_visible_sources"] is True


def test_prioritize_tasks_local_mode_skips_ai_provider(
    client,
    make_user,
    make_task,
    auth_headers,
    monkeypatch,
):
    """Verify local mode never calls the configured AI provider."""

    def failing_provider():
        """Fail if local mode tries to create a remote provider."""
        raise AssertionError("AI provider must not be called in local mode")

    user = make_user(username="priority_local_mode")
    make_task(
        "Lokale Dashboard-Prioritaet",
        creator_username=user["username"],
        priority=Priority.URGENT,
        description="Presse steht und muss lokal priorisiert werden",
    )
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        failing_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1, "mode": "local"},
    )

    payload = response.get_json()["data"]
    event = (
        OperationalEvent.query.filter_by(event_type="ai.tasks_prioritized")
        .order_by(OperationalEvent.id.desc())
        .first()
    )
    assert response.status_code == 200
    assert len(payload) == 1
    assert payload[0]["task"]["title"] == "Lokale Dashboard-Prioritaet"
    assert event.metadata_dict()["priority_mode"] == "local"


def test_prioritize_tasks_default_mode_uses_ai_provider(
    client,
    make_user,
    make_task,
    auth_headers,
    monkeypatch,
):
    """Verify default task prioritization mode remains AI-backed."""

    class RecordingProvider:
        """Record whether the AI provider was used."""

        called = False

        def prioritize_tasks(self, tasks, context=None):
            """Return a deterministic remote-style priority response."""
            self.called = True
            return {
                "priorities": [
                    {
                        "task_id": tasks[0]["id"],
                        "score": 99,
                        "risk_level": "critical",
                        "reason": "AI-Modus genutzt.",
                        "recommended_action": "Sofort pruefen.",
                    }
                ]
            }

    provider = RecordingProvider()

    def recording_provider():
        """Return the provider used to assert default AI mode."""
        return provider

    user = make_user(username="priority_default_ai")
    make_task(
        "AI Default Prioritaet",
        creator_username=user["username"],
        priority=Priority.NORMAL,
        description="Routine mit AI Provider",
    )
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        recording_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    event = (
        OperationalEvent.query.filter_by(event_type="ai.tasks_prioritized")
        .order_by(OperationalEvent.id.desc())
        .first()
    )
    assert response.status_code == 200
    assert provider.called is True
    assert payload[0]["score"] == 99
    assert payload[0]["confidence"]["level"] in {"low", "medium", "high"}
    assert payload[0]["confidence"]["uncertainty"] in {"low", "medium", "high"}
    assert event.metadata_dict()["priority_mode"] == "ai"


def test_prioritize_tasks_sends_history_context_to_provider(
    client,
    make_user,
    make_task,
    make_document,
    make_error_entry,
    set_dashboard_permission,
    auth_headers,
    monkeypatch,
):
    """Verify AI task prioritization receives maintenance history context."""

    class RecordingProvider:
        """Record task payloads passed to the provider."""

        def __init__(self):
            """Initialize captured provider inputs."""
            self.tasks = []
            self.context = {}

        def prioritize_tasks(self, tasks, context=None):
            """Return a deterministic response after recording the payload."""
            self.tasks = tasks
            self.context = context or {}
            return {
                "priorities": [
                    {
                        "task_id": tasks[0]["id"],
                        "score": 72,
                        "risk_level": "high",
                        "reason": "History-Kontext genutzt.",
                        "recommended_action": "Historie pruefen.",
                    }
                ]
            }

    provider = RecordingProvider()

    def recording_provider():
        """Return the recording provider."""
        return provider

    user = make_user(username="priority_history_provider")
    set_dashboard_permission(user["username"], "documents", can_view=True)
    task_id = make_task(
        "Hydraulikfilter wechseln",
        creator_username=user["username"],
        priority=Priority.NORMAL,
        due_date_value=date.today() + timedelta(days=5),
        description="Presse 9 meldet Druckabfall am Hydraulikfilter",
    )
    make_document(
        task_id=task_id,
        created_by=user["id"],
        relative_path="2026/05/task_priority_history/report.html",
        machine="Presse 9",
    )
    make_error_entry(
        "Presse 9",
        "HY-9",
        "Hydraulikdruck faellt ab",
        description="Druckabfall am Hydraulikfilter",
        possible_causes="Filter zugesetzt oder Leckage",
    )
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        recording_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    history = provider.tasks[0]["history"]
    assert response.status_code == 200
    assert payload[0]["score"] == 72
    assert "history" not in payload[0]["task"]
    assert payload[0]["confidence"] == {
        "score": 64,
        "level": "medium",
        "uncertainty": "medium",
        "reason": "Fehlerhistorie und Wartungsberichte stuetzen die Priorisierung.",
        "uses_only_visible_sources": True,
    }
    assert payload[0]["evidence_counts"] == {
        "maintenance_reports": 1,
        "related_errors": 1,
        "recent_related_errors": 1,
        "shift_handovers": 0,
        "recent_shift_handovers": 0,
        "machines": 1,
        "risk_signals": 2,
        "blocked": False,
        "reopened_count": 0,
        "uses_only_visible_sources": True,
    }
    evidence_references = payload[0]["evidence_references"]
    assert {source["type"] for source in evidence_references} >= {
        "task",
        "maintenance_report",
        "error",
    }
    report_reference = next(
        source for source in evidence_references if source["type"] == "maintenance_report"
    )
    error_reference = next(source for source in evidence_references if source["type"] == "error")
    assert report_reference["machine"] == "Presse 9"
    assert report_reference["role_visibility"]
    assert report_reference["created_at"]
    assert error_reference["error_code"] == "HY-9"
    assert error_reference["role_visibility"]
    assert "description" not in error_reference
    assert "solution" not in error_reference
    next_steps = payload[0]["next_steps"]
    next_step_types = {step["type"] for step in next_steps}
    assert "review_related_errors" in next_step_types
    assert "review_maintenance_reports" in next_step_types
    assert all(step["title"] and step["detail"] for step in next_steps)
    assert all(step["urgency"] in {"high", "medium", "low"} for step in next_steps)
    assert history["maintenance_reports_count"] == 1
    assert history["related_error_count"] == 1
    assert history["recent_related_errors"][0]["error_code"] == "HY-9"
    assert history["source_references"][0]["type"] == "task"
    assert "related_error_history" in history["risk_signals"]
    assert "history_fields" in provider.context
    assert "recent_shift_handovers" in provider.context["history_fields"]


def test_prioritize_tasks_sends_shift_handover_history_to_provider(
    app,
    client,
    make_user,
    make_task,
    make_machine,
    set_dashboard_permission,
    auth_headers,
    monkeypatch,
):
    """Verify task prioritization can use visible shift handover history."""

    class RecordingProvider:
        """Record task payloads passed to the provider."""

        def __init__(self):
            """Initialize captured provider inputs."""
            self.tasks = []

        def prioritize_tasks(self, tasks, context=None):
            """Return a deterministic response after recording the payload."""
            self.tasks = tasks
            return {
                "priorities": [
                    {
                        "task_id": tasks[0]["id"],
                        "score": 81,
                        "risk_level": "high",
                        "reason": "Schichtuebergabe zeigt wiederkehrenden Druckverlust.",
                        "recommended_action": "Uebergabe pruefen.",
                    }
                ]
            }

    provider = RecordingProvider()

    def recording_provider():
        """Return the recording provider."""
        return provider

    user = make_user(username="priority_handover_history")
    set_dashboard_permission(user["username"], "shiftplans", can_view=True)
    machine_id = make_machine(name="Presse 11")
    task_id = make_task(
        "Presse 11 Druckverlust pruefen",
        creator_username=user["username"],
        priority=Priority.SOON,
        description="Druckverlust an Presse 11 nach Spaetschicht pruefen",
    )
    with app.app_context():
        db_user = db.session.get(User, user["id"])
        handover = ShiftHandover(
            department="Produktion",
            area="Presse",
            machine_id=machine_id,
            shift_date=date.today(),
            shift_type="Spaet",
            status="open",
            handed_over_by=db_user.id,
            content="Presse 11 hatte Druckverlust.",
            open_tasks="Druckverlust pruefen.",
            machine_notes="Hydraulikdruck faellt sporadisch ab.",
            next_notes="Task in der Fruehschicht priorisieren.",
        )
        db.session.add(handover)
        db.session.commit()
        handover_id = handover.id
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        recording_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    history = provider.tasks[0]["history"]
    assert response.status_code == 200
    assert provider.tasks[0]["id"] == task_id
    assert payload[0]["evidence_counts"]["shift_handovers"] == 1
    assert payload[0]["evidence_counts"]["recent_shift_handovers"] == 1
    handover_reference = next(
        source for source in payload[0]["evidence_references"] if source["type"] == "shift_handover"
    )
    assert handover_reference["id"] == handover_id
    assert handover_reference["machine_id"] == machine_id
    assert handover_reference["role_visibility"] == "department:Produktion"
    assert "open_tasks" not in handover_reference
    assert "next_notes" not in handover_reference
    assert any(step["type"] == "review_shift_handover" for step in payload[0]["next_steps"])
    assert history["shift_handover_count"] == 1
    assert history["recent_shift_handovers"][0]["id"] == handover_id
    assert "shift_handover_history" in history["risk_signals"]
    assert "open_handover_history" in history["risk_signals"]


def test_prioritize_tasks_excludes_handover_history_without_permission(
    app,
    client,
    make_user,
    make_task,
    make_machine,
    set_dashboard_permission,
    auth_headers,
    monkeypatch,
):
    """Verify task prioritization does not leak handover history without permission."""

    class RecordingProvider:
        """Record task payloads passed to the provider."""

        def __init__(self):
            """Initialize captured provider inputs."""
            self.tasks = []

        def prioritize_tasks(self, tasks, context=None):
            """Return a deterministic response after recording the payload."""
            self.tasks = tasks
            return {
                "priorities": [
                    {
                        "task_id": tasks[0]["id"],
                        "score": 40,
                        "risk_level": "medium",
                        "reason": "Keine Uebergabehistorie sichtbar.",
                        "recommended_action": "Normal planen.",
                    }
                ]
            }

    provider = RecordingProvider()

    def recording_provider():
        """Return the recording provider."""
        return provider

    user = make_user(username="priority_no_handover_history")
    set_dashboard_permission(user["username"], "shiftplans", can_view=False)
    machine_id = make_machine(name="Presse 12")
    make_task(
        "Presse 12 Druckverlust pruefen",
        creator_username=user["username"],
        priority=Priority.SOON,
        description="Druckverlust an Presse 12 nach Spaetschicht pruefen",
    )
    with app.app_context():
        db_user = db.session.get(User, user["id"])
        db.session.add(
            ShiftHandover(
                department="Produktion",
                area="Presse",
                machine_id=machine_id,
                shift_date=date.today(),
                shift_type="Spaet",
                status="open",
                handed_over_by=db_user.id,
                content="Diese Uebergabe darf ohne Recht nicht in Priorisierung erscheinen.",
                open_tasks="Druckverlust pruefen.",
            )
        )
        db.session.commit()
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        recording_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    history = provider.tasks[0]["history"]
    assert response.status_code == 200
    assert payload[0]["evidence_counts"]["shift_handovers"] == 0
    assert payload[0]["evidence_counts"]["recent_shift_handovers"] == 0
    assert history["shift_handover_count"] == 0
    assert history["recent_shift_handovers"] == []
    assert "shift_handover_history" not in history["risk_signals"]


def test_prioritize_tasks_excludes_error_history_without_permission(
    client,
    make_user,
    make_task,
    make_error_entry,
    set_dashboard_permission,
    auth_headers,
    monkeypatch,
):
    """Verify task prioritization does not leak error history without permission."""

    class RecordingProvider:
        """Record task payloads passed to the provider."""

        def __init__(self):
            """Initialize captured provider inputs."""
            self.tasks = []

        def prioritize_tasks(self, tasks, context=None):
            """Return a deterministic response after recording the payload."""
            self.tasks = tasks
            return {
                "priorities": [
                    {
                        "task_id": tasks[0]["id"],
                        "score": 35,
                        "risk_level": "low",
                        "reason": "Keine Fehlerhistorie sichtbar.",
                        "recommended_action": "Normal planen.",
                    }
                ]
            }

    provider = RecordingProvider()

    def recording_provider():
        """Return the recording provider."""
        return provider

    user = make_user(username="priority_no_error_history")
    set_dashboard_permission(user["username"], "errors", can_view=False)
    make_task(
        "Hydraulikfilter pruefen",
        creator_username=user["username"],
        priority=Priority.NORMAL,
        description="Presse 10 meldet Druckabfall",
    )
    make_error_entry(
        "Presse 10",
        "HY-10",
        "Hydraulikdruck faellt ab",
        description="Druckabfall am Hydraulikfilter",
    )
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        recording_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    history = provider.tasks[0]["history"]
    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload[0]["evidence_counts"]["related_errors"] == 0
    assert payload[0]["evidence_counts"]["recent_related_errors"] == 0
    assert payload[0]["evidence_counts"]["uses_only_visible_sources"] is True
    assert history["related_error_count"] == 0
    assert history["recent_related_errors"] == []
    assert "related_error_history" not in history["risk_signals"]


def test_prioritize_tasks_uses_local_fallback_on_provider_error(
    client,
    make_user,
    make_task,
    auth_headers,
    monkeypatch,
):
    """Verify provider timeouts fall back to local priorities."""

    class FailingProvider:
        """Provide a deterministic provider failure for prioritization."""

        def prioritize_tasks(self, tasks, context=None):
            """Raise a timeout-like AI service error."""
            raise AIServiceError("timeout", error_code="timeout")

    def failing_provider():
        """Return a provider that always fails prioritization."""
        return FailingProvider()

    user = make_user(username="priority_provider_timeout")
    make_task(
        "Kritische Presse prüfen",
        creator_username=user["username"],
        priority=Priority.URGENT,
        description="Presse steht wegen Hydraulikfehler",
    )
    monkeypatch.setattr(
        "app.services.task_service.get_ai_provider",
        failing_provider,
    )

    response = client.post(
        "/api/v1/tasks/prioritize",
        headers=auth_headers(user["username"]),
        json={"limit": 1},
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert len(payload) == 1
    assert payload[0]["task"]["title"] == "Kritische Presse prüfen"
    assert payload[0]["score"] > 0


def test_task_suggestion_includes_rag_sources_after_reindex(
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify task suggestions can use indexed RAG sources without persisting data."""
    admin = make_user(
        username="task_suggest_rag_admin",
        role=Role.MASTER_ADMIN,
        department_name=None,
    )
    user = make_user(
        username="task_suggest_rag_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Anlage Task RAG",
        "TR900",
        "Hydraulikfilter Problem",
        department_name="Instandhaltung",
        possible_causes="Hydraulikfilter zugesetzt",
        solution="Filter pruefen und austauschen",
    )
    client.post(
        "/api/v1/admin/ai/knowledge/reindex",
        headers=auth_headers(admin["username"]),
    )

    response = client.post(
        "/api/v1/tasks/suggest",
        headers=auth_headers(user["username"]),
        json={"text": "Anlage Task RAG hat Hydraulikfilter Druckverlust"},
    )

    payload = response.get_json()["data"]
    assert response.status_code == 200
    assert payload["diagnostics"]["rag_source_count"] >= 1
    assert any(source["type"] == "knowledge" for source in payload["sources"])
    assert payload["status"] == "open"


def test_task_page_contains_priority_ui(client):
    """Verify task prioritization is exposed on the task page."""
    response = client.get("/tasks")
    html = response.get_data(as_text=True)
    react_source = task_react_source()

    assert response.status_code == 200
    assert "maintenance-tasks-root" in html
    assert "data-react-tasks-fallback" not in html
    assert "data-task-priority-list" in react_source
    assert "data-task-priority-refresh" in react_source
    assert "Priorisierung konnte nicht geladen werden." in react_source
