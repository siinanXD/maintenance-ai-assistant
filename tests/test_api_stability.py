"""Tests for API stability guarantees."""

import json
import re
from pathlib import Path

import pytest

from app.models import Priority, Role

REPO_ROOT = Path(__file__).resolve().parents[1]


def public_route_methods(app):
    """Return non-static Flask route rules and supported HTTP methods."""
    routes = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            routes.add((rule.rule, method))
    return routes


def interactive_data_attributes():
    """Return data attributes from template buttons and forms."""
    attributes = {}
    tag_pattern = re.compile(r"<(?:button|form)\b[^>]*>", re.IGNORECASE)
    data_pattern = re.compile(r"\b(data-[A-Za-z0-9_-]+)(?=[\s=>])")

    for template_path in (REPO_ROOT / "app" / "templates").rglob("*.html"):
        text = template_path.read_text(encoding="utf-8")
        for tag_match in tag_pattern.finditer(text):
            line_number = text.count("\n", 0, tag_match.start()) + 1
            location = f"{template_path.relative_to(REPO_ROOT)}:{line_number}"
            for data_match in data_pattern.finditer(tag_match.group(0)):
                attributes.setdefault(data_match.group(1), []).append(location)
    return attributes


def frontend_source_text():
    """Return combined template, static JavaScript and React source text.

    React islands are scanned from ``frontend/src`` so the check does not depend
    on a built ``app/static/react`` bundle being present.
    """
    source_paths = list((REPO_ROOT / "app" / "templates").rglob("*.html"))
    source_paths.extend((REPO_ROOT / "app" / "static").rglob("*.js"))
    source_paths.extend((REPO_ROOT / "frontend" / "src").rglob("*.ts"))
    source_paths.extend((REPO_ROOT / "frontend" / "src").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def module_source(*modules):
    """Return the TypeScript source of the given frontend/src modules."""
    source_paths = []
    for module in modules:
        source_paths.extend(sorted((REPO_ROOT / "frontend" / "src" / module).rglob("*.ts*")))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def frontend_ui_source_files():
    """Return frontend source files that contain user-visible UI copy."""
    source_paths = list((REPO_ROOT / "app" / "templates").rglob("*.html"))
    source_paths.extend(
        path
        for path in (REPO_ROOT / "app" / "static").rglob("*.js")
        if "react" not in path.relative_to(REPO_ROOT / "app" / "static").parts
    )
    source_paths.extend((REPO_ROOT / "frontend" / "src").rglob("*.tsx"))
    source_paths.extend((REPO_ROOT / "frontend" / "src").rglob("*.ts"))
    source_paths.append(REPO_ROOT / "app" / "static" / "css" / "input.css")
    return source_paths


def test_frontend_task_workflow_routes_exist(app):
    """Verify frontend task workflow calls match registered Flask routes."""
    routes = public_route_methods(app)
    script = module_source("tasks")

    assert ("/api/v1/tasks/<int:task_id>/start", "POST") in routes
    assert ("/api/v1/tasks/<int:task_id>/complete", "POST") in routes
    assert "`/api/v1/tasks/${taskId}/${action}`" in script
    assert '"start"' in script
    assert '"complete"' in script


def test_task_prioritization_is_manual_refresh_only():
    """Verify the React task page does not trigger AI prioritization on initial load."""
    react_source = module_source("tasks")

    assert "/api/v1/tasks/prioritize" in react_source
    assert "priorityRefreshButtons.forEach" not in react_source
    assert "await loadPriorities();" not in react_source
    assert "await refreshTaskData();\n    await refreshPriorities();" not in react_source
    assert "onClick={onRefresh}" in react_source
    assert "onRefresh={refreshPriorities}" in react_source


def test_new_ai_frontend_routes_exist(app):
    """Verify frontend AI feature calls have matching Flask routes."""
    routes = public_route_methods(app)
    script = frontend_source_text()

    expected_routes = {
        ("/api/v1/tasks/prioritize", "POST"),
        ("/api/v1/errors/similar", "POST"),
        ("/api/v1/inventory/forecast", "POST"),
        ("/api/v1/shiftplans/calendar", "GET"),
        ("/api/v1/shiftplans/models", "GET"),
        ("/api/v1/machines/<int:machine_id>/history", "GET"),
        ("/api/v1/machines/<int:machine_id>/profile", "GET"),
        ("/api/v1/machines/<int:machine_id>/assistant", "POST"),
        ("/api/v1/machines/maintenance-recommendations", "GET"),
        ("/api/v1/ai/status", "GET"),
        ("/api/v1/ai/daily-briefing", "GET"),
        ("/api/v1/ai/error-assistant", "POST"),
        ("/api/v1/admin/ai/training", "GET"),
        ("/api/v1/admin/ai/training", "POST"),
        ("/api/v1/admin/ai/training/<int:entry_id>", "PUT"),
        ("/api/v1/admin/ai/training/<int:entry_id>", "DELETE"),
        ("/api/v1/admin/ai/knowledge-network", "GET"),
        ("/api/v1/admin/ai/retrieval-telemetry", "GET"),
        ("/api/v1/admin/ai/retrieval-evaluations/run", "POST"),
        ("/api/v1/admin/ai/knowledge/status", "GET"),
        ("/api/v1/admin/ai/knowledge-gaps", "GET"),
        ("/api/v1/admin/ai/retrieval-debug", "GET"),
        ("/api/v1/admin/ai/observability", "GET"),
        ("/api/v1/sites", "GET"),
        ("/api/v1/operations/summary", "GET"),
        ("/api/v1/operations/events", "GET"),
        ("/api/v1/operations/tasks", "GET"),
        ("/api/v1/operations/machines", "GET"),
        ("/api/v1/operations/inventory", "GET"),
        ("/api/v1/operations/workforce", "GET"),
        ("/api/v1/operations/ai-quality", "GET"),
        ("/api/v1/admin/sites", "GET"),
        ("/api/v1/admin/sites", "POST"),
        ("/api/v1/admin/sites/<int:site_id>", "PUT"),
        ("/api/v1/admin/operations/aggregate", "POST"),
        ("/api/v1/documents/<int:document_id>/review", "POST"),
        ("/api/v1/employees", "GET"),
        ("/api/v1/employees", "POST"),
        ("/api/v1/employees/<int:employee_id>", "PUT"),
        ("/api/v1/employees/<int:employee_id>", "DELETE"),
        ("/api/v1/employees/<int:employee_id>/documents", "POST"),
        ("/api/v1/vacations", "GET"),
        ("/api/v1/vacations", "POST"),
        ("/api/v1/vacations/impact", "GET"),
        ("/api/v1/vacations/summary", "GET"),
        ("/api/v1/vacations/<int:request_id>/approve", "POST"),
        ("/api/v1/vacations/<int:request_id>/reject", "POST"),
        ("/api/v1/vacations/<int:request_id>/cancel", "POST"),
        ("/api/v1/health/operations", "GET"),
    }
    assert expected_routes <= routes
    assert "/api/v1/tasks/prioritize" in script
    assert "prioritizeTasks" in script
    assert 'body: { status: "open", limit: 10 }' in script
    assert "/api/v1/errors/similar" in script
    assert "/api/v1/errors/analyze" in script
    assert "`/api/v1/errors/${errorId}`" in script
    assert "`/api/v1/errors/${errorId}/close`" in script
    assert "/api/v1/inventory/forecast" in script
    assert "`${SHIFTPLANS_BASE}/models`" in script
    assert "/api/v1/ai/daily-briefing" in script
    assert "/api/v1/ai/error-assistant" in script
    assert "/api/v1/admin/ai/knowledge-network" in script
    assert "/api/v1/admin/ai/retrieval-telemetry" in script
    assert "/api/v1/admin/ai/retrieval-evaluations/run" in script
    assert "/api/v1/admin/ai/knowledge/status" in script
    assert "/api/v1/admin/ai/knowledge-gaps" in script
    assert "/api/v1/admin/ai/retrieval-debug" in script
    assert "/api/v1/admin/ai/observability" in script
    assert "/api/v1/documents/check" in script
    assert "/api/v1/documents/manuals" in script
    assert "`/api/v1/documents/${documentId}/review`" in script
    assert "`/api/v1/documents/${documentId}/summarize`" in script
    assert "`/api/v1/documents/${documentId}/versions`" in script
    assert "`/api/v1/documents/${documentId}/${action}`" in script
    assert "`/api/v1/documents/manuals/${manualId}/analyze`" in script
    assert "`/api/v1/documents/manuals/${manualId}/summarize`" in script
    assert "`/api/v1/documents/manuals/${manualId}`" in script
    assert "/api/v1/machines/maintenance-recommendations" in script
    assert "`/api/v1/machines/${machineId}/profile`" in script
    assert "`/api/v1/machines/${machineId}/history`" in script
    assert "`/api/v1/machines/${machineId}/assistant`" in script
    assert "/api/v1/employees?limit=200" in script
    assert "`/api/v1/employees/${employeeId}`" in script
    assert "`/api/v1/employees/${employeeId}/documents`" in script
    assert "/api/v1/vacations?year=" in script
    assert "/api/v1/vacations/summary?year=" in script
    assert "/api/v1/vacations/impact?" in script
    assert "`/api/v1/vacations/${requestId}/${action}`" in script
    assert "`/api/v1/vacations/${requestId}/cancel`" in script


def test_scalability_migration_contains_composite_indexes():
    """Verify the multi-site scalability migration includes critical indexes."""
    migration = (
        REPO_ROOT / "migrations" / "versions" / "d1e2f3a4b5c6_add_scalability_indexes.py"
    ).read_text(encoding="utf-8")

    assert "ix_task_department_status_due" in migration
    assert "ix_knowledge_document_source_status" in migration
    assert "ix_background_job_claim" in migration
    assert "ix_generated_document_department_created" in migration


def test_operations_migration_contains_site_and_event_tables():
    """Verify the operations migration creates site and KPI tracking structures."""
    migration = (
        REPO_ROOT / "migrations" / "versions" / "e2f3a4b5c6d7_add_sites_operations_tracking.py"
    ).read_text(encoding="utf-8")

    assert "op.create_table(" in migration
    assert '"site"' in migration
    assert '"operational_event"' in migration
    assert '"operational_kpi_aggregate"' in migration
    assert "werk-1" in migration


def test_ci_and_docker_build_react_assets():
    """Verify automated builds create React assets instead of committing them."""
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend_package = json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "npm --prefix frontend ci" in ci_workflow
    assert "npm run check:react" in ci_workflow
    assert "npm run build:react" in ci_workflow
    assert frontend_package["scripts"]["build"] == "vite build --configLoader runner"
    assert "FROM node:22-slim AS frontend-build" in dockerfile
    assert "COPY --from=frontend-build /build/app/static/react ./app/static/react" in dockerfile
    assert "/app/static/react/" in gitignore


def test_loaded_static_assets_exist(client):
    """Verify the base template references only static assets that Flask can serve."""
    html = client.get("/").get_data(as_text=True)
    expected_assets = (
        "/static/css/output.css",
        "/static/core/feature-registry.js",
        "/static/core/action-dialogs.js",
        "/static/auth.js",
        "/static/app.js",
    )

    for asset in expected_assets:
        assert asset in html
        assert client.get(asset).status_code == 200

    assert "/static/pages/" not in html
    assert not (REPO_ROOT / "app" / "static" / "pages").exists()


def test_interactive_template_data_hooks_are_wired():
    """Verify button and form data hooks are referenced by frontend code."""
    source = frontend_source_text()
    missing = {
        attribute: locations
        for attribute, locations in interactive_data_attributes().items()
        if source.count(attribute) <= len(locations)
    }

    assert missing == {}


def test_migrated_pages_use_static_modules_without_inline_scripts():
    """Verify migrated workflow pages no longer carry large inline scripts."""
    migrated_templates = (
        REPO_ROOT / "app" / "templates" / "login.html",
        REPO_ROOT / "app" / "templates" / "admin_ai.html",
        REPO_ROOT / "app" / "templates" / "handover.html",
        REPO_ROOT / "app" / "templates" / "shiftplans.html",
    )
    for template_path in migrated_templates:
        assert "<script>" not in template_path.read_text(encoding="utf-8")

    source = frontend_source_text()
    assert "window.prompt" not in source
    assert "window.alert" not in source


def test_frontend_ui_copy_has_no_encoding_artifacts():
    """Verify UI source does not reintroduce mojibake or ASCII fallback labels."""
    blocked_fragments = (
        "Ãƒ",
        "Laeuft",
        "Bestaetigen",
        "bestaetigen",
        "ueberfaellig",
        "Stoer",
        "Qualitaet",
        "spaeter",
        "gewaehl",
        "geprueft",
        "pruef",
        "Pruef",
        "koennen",
        "auswaehlen",
        "zurueck",
        "vollstaendig",
        "Handbuecher",
    )
    offenders = {}
    for source_path in frontend_ui_source_files():
        text = source_path.read_text(encoding="utf-8")
        hits = [fragment for fragment in blocked_fragments if fragment in text]
        if hits:
            offenders[str(source_path.relative_to(REPO_ROOT))] = hits

    assert offenders == {}


def test_web_routes_use_shared_design_shell(client):
    """Verify all HTML web routes render through the shared app design shell."""
    routes = (
        "/",
        "/login",
        "/api-docs",
        "/tasks",
        "/errors",
        "/admin/users",
        "/employees",
        "/shiftplans",
        "/machines",
        "/inventory",
        "/documents",
        "/handover",
        "/vacations",
    )

    for route in routes:
        response = client.get(route)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "app-main" in html
        if route == "/login":
            assert "app-shell-layout" not in html
            assert "maintenance-shell-runtime-root" not in html
            assert "maintenance-shell-sidebar-root" not in html
            assert "maintenance-login-root" in html
            assert "data-react-login-fallback" not in html
            continue

        assert "app-shell-layout" in html
        assert "maintenance-shell-runtime-root" in html
        assert "maintenance-shell-sidebar-root" in html
        assert "maintenance-shell-topbar-root" in html
        assert "maintenance-shell-chat-root" in html
        assert "data-react-shell-sidebar-fallback" in html
        assert "data-react-shell-topbar-fallback" in html
        assert "data-react-shell-chat-fallback" in html
        if route == "/":
            assert "maintenance-dashboard-root" in html
            assert "data-react-dashboard-fallback" not in html
        elif route == "/errors":
            assert "maintenance-errors-root" in html
            assert "data-react-errors-fallback" not in html
        elif route == "/tasks":
            assert "maintenance-tasks-root" in html
            assert "data-react-tasks-fallback" not in html
        elif route == "/machines":
            assert "maintenance-machines-root" in html
            assert "data-react-machines-fallback" not in html
        elif route == "/employees":
            assert "maintenance-employees-root" in html
            assert "data-react-employees-fallback" not in html
        elif route == "/inventory":
            assert "maintenance-inventory-root" in html
            assert "data-react-inventory-fallback" not in html
        elif route == "/documents":
            assert "maintenance-documents-root" in html
            assert "data-react-documents-fallback" not in html
        elif route == "/vacations":
            assert "maintenance-vacations-root" in html
            assert "data-react-vacations-fallback" not in html
        elif route == "/admin/users":
            assert "maintenance-admin-users-root" in html
            assert "data-react-admin-users-fallback" not in html
        elif route == "/shiftplans":
            assert "maintenance-shiftplans-root" in html
            assert "data-react-shiftplans-fallback" not in html
        elif route == "/handover":
            assert "maintenance-handover-root" in html
            assert "data-react-handover-fallback" not in html
        else:
            assert "page-hero" in html
            assert "app-card" in html


def test_shiftplans_page_uses_react_model_loading(client):
    """Verify the shift model dropdown is now provided by the React island."""
    html = client.get("/shiftplans").get_data(as_text=True)
    source = module_source("shiftplans")

    assert "maintenance-shiftplans-root" in html
    assert 'id="sp-shift-model"' not in html
    assert "loadShiftModels" in source
    assert "models.map" in source
    assert "beginnerModelLabel(model)" in source


def test_shiftplans_react_uses_selected_model_for_generation():
    """Verify selected model lookup drives the React generation payload."""
    source = module_source("shiftplans")

    assert "models.find" in source
    assert "draft.shiftModelKey" in source
    assert "selectedModel.key" in source
    assert "rhythm: selectedModel.display_name" in source


def test_shiftplans_react_renders_generated_plan_before_list_refresh():
    """Verify a generated draft remains visible even if list reload is stale."""
    source = module_source("shiftplans")

    assert "function plansWithFallback" in source
    assert "fallbackPlan" in source
    assert "refreshInitialData(plan.id, plan)" in source
    assert "selectedPlanIndexFor" in source


def test_core_german_ui_labels_are_not_mojibake(client):
    """Verify important German UI labels render as UTF-8, not mojibake."""
    html = client.get("/").get_data(as_text=True)
    shell_source = module_source("layout")
    source = html + module_source("dashboard") + shell_source

    assert "Schicht\u00fcbergabe" in shell_source
    assert "Men\u00fc" in shell_source
    assert "St\u00f6rung melden" in source
    assert "Schicht\u00c3\u00bcbergabe" not in source
    assert "faellig" not in source


def test_api_not_found_returns_consistent_json(client, make_user, auth_headers):
    """Verify unknown API routes return the standard JSON error shape."""
    user = make_user(username="api_not_found_user")

    response = client.get(
        "/api/does-not-exist",
        headers=auth_headers(user["username"]),
    )

    payload = response.get_json()
    assert response.status_code == 404
    assert payload["success"] is False
    assert payload["message"]
    assert payload["error"]
    assert payload["error"] != payload["message"]


def test_production_requires_strong_secrets(tmp_path):
    """Verify production startup rejects weak secret configuration."""

    class WeakProductionConfig:
        """Provide intentionally weak production settings."""

        TESTING = False
        FLASK_ENV = "production"
        SECRET_KEY = "dev-secret-change-me"
        JWT_SECRET_KEY = "short"
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        AUTO_CREATE_DATABASE = False
        AI_PROVIDER = "mock"
        OPENAI_API_KEY = ""
        OPENAI_MODEL = "test-model"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        DOCUMENTS_FOLDER = str(tmp_path / "documents")
        LOG_DIR = str(tmp_path / "logs")
        LOG_LEVEL = "INFO"
        SLOW_REQUEST_THRESHOLD_MS = 500

    from app import create_app

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(WeakProductionConfig)


def test_core_ai_and_workflow_endpoints_smoke(
    client,
    make_user,
    make_task,
    make_machine,
    make_material,
    auth_headers,
):
    """Verify core frontend API endpoints respond with authenticated requests."""
    user = make_user(
        username="api_smoke_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    machine_id = make_machine(name="Anlage Smoke")
    make_material("Smoke Sensor", 120, 0, machine_id=machine_id)
    task_id = make_task(
        "Stillstand Anlage Smoke",
        creator_username=user["username"],
        department_name="Instandhaltung",
        priority=Priority.URGENT,
        description="Anlage Smoke meldet Sensorfehler",
    )
    headers = auth_headers(user["username"])

    start_response = client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    complete_response = client.post(
        f"/api/v1/tasks/{task_id}/complete",
        headers=headers,
        json={},
    )
    briefing_response = client.get("/api/v1/ai/daily-briefing", headers=headers)
    assistant_response = client.post(
        f"/api/v1/machines/{machine_id}/assistant",
        headers=headers,
        json={"question": "Was ist wichtig?"},
    )
    forecast_response = client.post(
        "/api/v1/inventory/forecast",
        headers=headers,
        json={"status": "open", "limit": 20, "low_stock_threshold": 5},
    )

    assert start_response.status_code == 200
    assert start_response.get_json()["status"] == "in_progress"
    assert complete_response.status_code == 200
    assert complete_response.get_json()["status"] == "done"
    assert briefing_response.status_code == 200
    assert "sections" in briefing_response.get_json()
    assert assistant_response.status_code == 200
    assert assistant_response.get_json()["diagnostics"]["status"] == "local_answer"
    assert forecast_response.status_code == 200
    assert "items" in forecast_response.get_json()
