"""Structure rules for the Jinja shell and the React pages in frontend/src."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
STATIC = REPO_ROOT / "app" / "static"

# Web route, root element in its template, Vite entry that mounts into it.
PAGES = (
    ("/", "maintenance-dashboard-root", "src/dashboard/entry.tsx"),
    ("/login", "maintenance-login-root", "src/login/entry.tsx"),
    ("/tasks", "maintenance-tasks-root", "src/tasks/entry.tsx"),
    ("/errors", "maintenance-errors-root", "src/errors/entry.tsx"),
    ("/maintenance", "maintenance-plans-root", "src/maintenance/entry.tsx"),
    ("/machines", "maintenance-machines-root", "src/machines/entry.tsx"),
    ("/machines/1", "maintenance-machine-profile-root", "src/machines/entry.tsx"),
    ("/inventory", "maintenance-inventory-root", "src/inventory/entry.tsx"),
    ("/documents", "maintenance-documents-root", "src/documents/entry.tsx"),
    ("/employees", "maintenance-employees-root", "src/employees/entry.tsx"),
    ("/vacations", "maintenance-vacations-root", "src/vacations/entry.tsx"),
    ("/shiftplans", "maintenance-shiftplans-root", "src/shiftplans/entry.tsx"),
    ("/handover", "maintenance-handover-root", "src/handover/entry.tsx"),
    ("/admin/users", "maintenance-admin-users-root", "src/admin-users/entry.tsx"),
    ("/admin/ai", "maintenance-admin-ai-root", "src/admin-ai/entry.tsx"),
    ("/admin/ai/rag-board", "maintenance-admin-ai-root", "src/admin-ai/entry.tsx"),
)


def vite_entries():
    """Return the entry files listed in frontend/vite.config.ts."""
    config = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    return set(re.findall(r'"(src/[\w/-]+\.tsx)"', config))


def frontend_files(pattern):
    """Return frontend source files matching a glob pattern."""
    return sorted(FRONTEND_SRC.rglob(pattern))


@pytest.mark.parametrize(("route", "root_id", "entry"), PAGES)
def test_page_renders_one_root_mounted_by_its_entry(client, route, root_id, entry):
    """Each page template has one React root, and its Vite entry mounts into that root."""
    response = client.get(route)
    html = response.get_data(as_text=True)
    entry_path = REPO_ROOT / "frontend" / entry

    assert response.status_code == 200
    assert html.count(f'id="{root_id}"') == 1
    assert entry in vite_entries()
    assert f'"{root_id}"' in entry_path.read_text(encoding="utf-8")


def test_every_vite_entry_is_loaded_by_a_template():
    """No bundle is built that no page loads."""
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "app" / "templates").glob("*.html")
    )

    for entry in vite_entries():
        assert f'react_entrypoint("{entry}")' in templates, entry


def test_page_modules_share_one_layout():
    """Page folders hold entry.tsx, *App.tsx and plain modules; UI pieces live in components/."""
    for entry in frontend_files("entry.tsx"):
        module = entry.parent
        if module.name == "layout":
            continue
        root_tsx = {path.name for path in module.glob("*.tsx")}
        assert any(name.endswith("App.tsx") for name in root_tsx), module.name
        assert root_tsx <= {"entry.tsx"} | {
            name for name in root_tsx if name.endswith("App.tsx")
        }, f"{module.name}: move components into components/"
        for path in module.glob("*.ts"):
            assert path.name[0].islower(), f"{module.name}/{path.name}: plain modules use camelCase"


def test_shell_scripts_are_only_the_documented_globals(client):
    """base.html loads the shell scripts and the shell bundle, nothing page-specific."""
    html = client.get("/").get_data(as_text=True)
    scripts = re.findall(r'<script[^>]+src="([^"?]+)', html)

    assert [src for src in scripts if not src.startswith("/static/react/")] == [
        "/static/core/feature-registry.js",
        "/static/core/action-dialogs.js",
        "/static/auth.js",
        "/static/app.js",
    ]
    assert sorted(path.name for path in STATIC.glob("*.js")) == ["app.js", "auth.js"]
    assert sorted(path.name for path in (STATIC / "core").glob("*.js")) == [
        "action-dialogs.js",
        "feature-registry.js",
    ]


def test_feature_registry_protects_every_page(app):
    """Every page except login and API docs is guarded through feature-registry.js."""
    registry = (STATIC / "core" / "feature-registry.js").read_text(encoding="utf-8")
    routes = set(re.findall(r'route: "([^"]+)"', registry))
    prefixes = [
        prefix
        for group in re.findall(r"routePrefixes: \[([^\]]+)\]", registry)
        for prefix in re.findall(r'"([^"]+)"', group)
    ]
    public = {"/login", "/api-docs", "/m/<int:machine_id>"}
    checked = 0

    for rule in app.url_map.iter_rules():
        if rule.endpoint.split(".")[0] != "web" or rule.rule in public:
            continue
        path = re.sub(r"<[^>]+>", "1", rule.rule)
        assert path in routes or any(path.startswith(prefix) for prefix in prefixes), rule.rule
        checked += 1

    assert checked >= 15


def test_frontend_uses_the_shared_dialog_and_no_page_markers():
    """Confirmations go through action-dialogs.js; no leftovers of the old mount protocol."""
    offenders = {}
    for path in frontend_files("*.ts*"):
        text = path.read_text(encoding="utf-8")
        hits = [
            marker
            for marker in (
                "window.alert(",
                "window.prompt(",
                "markIslandMounted",
                "ReactMounted",
                "dangerouslySetInnerHTML",
            )
            if marker in text
        ]
        if "window.confirm(" in text and path.name != "runtimeBridge.ts":
            hits.append("window.confirm(")
        if hits:
            offenders[str(path.relative_to(FRONTEND_SRC))] = hits

    assert offenders == {}
