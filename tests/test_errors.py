"""Tests for error catalog workflows."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.extensions import db
from app.models import ErrorEntry, Machine, Role, User
from app.services.recurring_issue_service import analyze_recurring_issues

REPO_ROOT = Path(__file__).resolve().parents[1]


def error_react_source():
    """Return the combined React error island source."""
    source_paths = list((REPO_ROOT / "frontend" / "src" / "errors").rglob("*.ts"))
    source_paths.extend((REPO_ROOT / "frontend" / "src" / "errors").rglob("*.tsx"))
    return "\n".join(path.read_text(encoding="utf-8") for path in source_paths)


def test_error_entry_create_search_update_and_delete(client, make_user, auth_headers):
    """Verify error catalog CRUD and search behavior."""
    user = make_user(
        username="error_owner",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    create_response = client.post(
        "/api/v1/errors",
        headers=headers,
        json={
            "machine": "Maschine 3",
            "error_code": "e104",
            "title": "Sensor erkennt Produkt nicht",
            "department": "Instandhaltung",
            "solution": "Sensor reinigen",
        },
    )
    entry_id = create_response.get_json()["id"]
    search_response = client.get("/api/v1/errors/search?query=E104", headers=headers)
    update_response = client.put(
        f"/api/v1/errors/{entry_id}",
        headers=headers,
        json={"solution": "Sensor reinigen und Abstand pruefen"},
    )
    delete_response = client.delete(f"/api/v1/errors/{entry_id}", headers=headers)

    assert create_response.status_code == 201
    assert create_response.get_json()["error_code"] == "E104"
    assert search_response.status_code == 200
    assert len(search_response.get_json()) == 1
    assert update_response.status_code == 200
    assert "Abstand" in update_response.get_json()["solution"]
    assert delete_response.status_code == 204


def test_error_list_active_filter_excludes_catalog_rows(
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify dashboard active filtering ignores static catalog-only errors."""
    user = make_user(
        username="active_error_filter",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])
    make_error_entry(
        "Hydraulikpresse 03",
        "E-CAT",
        "Katalogeintrag ohne aktuelles Auftreten",
        department_name="Instandhaltung",
    )

    create_response = client.post(
        "/api/v1/errors",
        headers=headers,
        json={
            "machine": "Hydraulikpresse 03",
            "error_code": "E-ACT",
            "title": "Aktuelle Hydraulikstoerung",
            "department": "Instandhaltung",
        },
    )
    response = client.get("/api/v1/errors?active=1&limit=100", headers=headers)
    codes = [entry["error_code"] for entry in response.get_json()["data"]]

    assert create_response.status_code == 201
    assert response.status_code == 200
    assert "E-ACT" in codes
    assert "E-CAT" not in codes


def test_error_entry_rejects_duplicate_code_in_same_department(
    client,
    make_user,
    auth_headers,
):
    """Verify duplicate error codes are blocked per department."""
    user = make_user(
        username="error_duplicate_code",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])
    payload = {
        "machine": "Maschine 3",
        "error_code": "E777",
        "title": "Hydraulik Stoerung",
        "department": "Instandhaltung",
    }

    first_response = client.post("/api/v1/errors", headers=headers, json=payload)
    duplicate_response = client.post(
        "/api/v1/errors",
        headers=headers,
        json={**payload, "error_code": " e777 ", "title": "Andere Stoerung"},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_error_entry_allows_same_code_in_other_department(
    client,
    make_user,
    auth_headers,
):
    """Verify the same error code can exist in different departments."""
    maintenance = make_user(
        username="error_code_maintenance",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    production = make_user(
        username="error_code_production",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )

    first_response = client.post(
        "/api/v1/errors",
        headers=auth_headers(maintenance["username"]),
        json={
            "machine": "Maschine 3",
            "error_code": "E778",
            "title": "Hydraulik Stoerung",
            "department": "Instandhaltung",
        },
    )
    second_response = client.post(
        "/api/v1/errors",
        headers=auth_headers(production["username"]),
        json={
            "machine": "Maschine 3",
            "error_code": "E778",
            "title": "Produktions Stoerung",
            "department": "Produktion",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_error_entry_uses_canonical_machine_name(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify exact machine matches set machine_id and canonical name."""
    user = make_user(
        username="error_machine_canonical",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    with app.app_context():
        machine = Machine(name="Presse Canon 1", produced_item="Teil")
        db.session.add(machine)
        db.session.commit()
        machine_id = machine.id

    response = client.post(
        "/api/v1/errors",
        headers=auth_headers(user["username"]),
        json={
            "machine": "presse canon 1",
            "error_code": "E779",
            "title": "Sensor Stoerung",
            "department": "Instandhaltung",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["machine_id"] == machine_id
    assert response.get_json()["machine"] == "Presse Canon 1"


def test_error_entry_validates_required_fields(client, make_user, auth_headers):
    """Verify missing error entry fields return a client error."""
    user = make_user(username="error_validation")

    response = client.post(
        "/api/v1/errors",
        headers=auth_headers(user["username"]),
        json={"machine": "Maschine 1"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "missing_fields_error_code_title"
    assert "Missing fields" in response.get_json()["message"]
    assert response.get_json()["missing_information"]["status"] == "needs_information"
    assert "error_code" in response.get_json()["missing_information"]["missing_fields"]


def test_error_entry_reports_complete_missing_information_state(client, make_user, auth_headers):
    """Verify complete error payloads do not request follow-up information."""
    user = make_user(
        username="error_complete_prompts",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )

    response = client.post(
        "/api/v1/errors",
        headers=auth_headers(user["username"]),
        json={
            "machine": "Maschine 3",
            "error_code": "E104",
            "title": "Sensor meldet kein Signal",
            "description": "Maschine 3 zeigt E104 und der Sensor meldet kein Signal.",
            "possible_causes": "Sensor verschmutzt oder Kabel locker.",
            "solution": "Sensor gereinigt, Kabel geprueft und Probelauf erfolgreich.",
            "department": "Instandhaltung",
            "previous_checks": "Sensor gereinigt und Kabel geprueft.",
            "solution_result": "Probelauf erfolgreich, Stoerung behoben.",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["missing_information"]["status"] == "complete"
    assert response.get_json()["missing_information"]["missing_fields"] == []


def test_error_entry_rejects_other_department_writes(
    client,
    make_user,
    auth_headers,
):
    """Verify non-admin users cannot create error entries for other departments."""
    user = make_user(
        username="error_department_guard",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )

    response = client.post(
        "/api/v1/errors",
        headers=auth_headers(user["username"]),
        json={
            "machine": "Maschine 3",
            "error_code": "E500",
            "title": "Fremder Fehler",
            "department": "Instandhaltung",
        },
    )

    assert response.status_code == 403


def test_error_detail_is_forbidden_across_departments(
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify users cannot read error entries from another department."""
    requester = make_user(
        username="error_requester",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    entry_id = make_error_entry(
        "Maschine 9",
        "E900",
        "Fremder Fehler",
        department_name="Instandhaltung",
    )

    response = client.get(
        f"/api/v1/errors/{entry_id}",
        headers=auth_headers(requester["username"]),
    )

    assert response.status_code == 403


def test_error_analysis_validates_input_and_uses_mock_fallback(
    client,
    make_user,
    auth_headers,
):
    """Verify AI error analysis handles empty and valid descriptions deterministically."""
    user = make_user(
        username="error_analysis",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    headers = auth_headers(user["username"])

    empty_response = client.post("/api/v1/errors/analyze", headers=headers, json={})
    valid_response = client.post(
        "/api/v1/errors/analyze",
        headers=headers,
        json={"description": "Sensor meldet sporadisch kein Signal an Maschine 3"},
    )

    assert empty_response.status_code == 400
    assert valid_response.status_code == 200
    assert valid_response.get_json()["department"] == "Instandhaltung"
    assert "Sensor" in valid_response.get_json()["possible_causes"]
    assert valid_response.get_json()["missing_information"]["status"] == "needs_information"
    assert "error_code" in valid_response.get_json()["missing_information"]["missing_fields"]


def test_similar_errors_respects_department_and_sorts_matches(
    client,
    make_user,
    make_error_entry,
    auth_headers,
):
    """Verify similar error suggestions are visible and relevance-sorted."""
    user = make_user(
        username="similar_error_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Anlage 4",
        "E104",
        "Sensor erkennt Produkt nicht",
        department_name="Instandhaltung",
        description="Sensor Signal fehlt sporadisch",
        solution="Sensor reinigen",
    )
    make_error_entry(
        "Anlage 9",
        "E900",
        "Hydraulikdruck niedrig",
        department_name="Instandhaltung",
        description="Druck faellt ab",
    )
    make_error_entry(
        "Anlage 4",
        "E777",
        "Fremder Sensorfehler",
        department_name="Produktion",
    )

    response = client.post(
        "/api/v1/errors/similar",
        headers=auth_headers(user["username"]),
        json={"text": "Sensor Signal an Anlage 4 fehlt", "machine": "Anlage 4"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["results"][0]["entry"]["error_code"] == "E104"
    assert all(
        result["entry"]["department"]["name"] == "Instandhaltung" for result in payload["results"]
    )


def test_similar_errors_rejects_empty_and_invalid_limit(client, make_user, auth_headers):
    """Verify similar error suggestions validate request data."""
    user = make_user(username="similar_error_validation")
    headers = auth_headers(user["username"])

    empty_response = client.post("/api/v1/errors/similar", headers=headers, json={})
    invalid_limit = client.post(
        "/api/v1/errors/similar",
        headers=headers,
        json={"text": "Sensor", "limit": 0},
    )

    assert empty_response.status_code == 400
    assert invalid_limit.status_code == 400


def test_recurring_issue_trends_group_similar_errors(
    app,
    make_user,
    make_error_entry,
):
    """Verify recurring issue trends group similar visible fault entries."""
    user = make_user(
        username="recurring_issue_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    entry_ids = [
        make_error_entry(
            "Anlage 4",
            "E104",
            "Sensor Signal fehlt",
            department_name="Instandhaltung",
            description="Sensor Signal fehlt sporadisch an Zufuehrung.",
            solution="Sensor reinigen",
        ),
        make_error_entry(
            "Anlage 4",
            "E104",
            "Sensor erkennt Produkt nicht",
            department_name="Instandhaltung",
            description="Sensor meldet kein Signal an Zufuehrung.",
            solution="Sensor reinigen",
        ),
        make_error_entry(
            "Anlage 4",
            "E104",
            "Sensor Stoerung wiederholt",
            department_name="Instandhaltung",
            description="Produkt wird sporadisch nicht erkannt.",
            solution="Sensor reinigen",
        ),
    ]

    with app.app_context():
        now = datetime.now(UTC)
        entries = ErrorEntry.query.filter(ErrorEntry.id.in_(entry_ids)).all()
        for index, entry in enumerate(entries):
            entry.created_at = now - timedelta(days=index * 2)
        entries[0].repeat_count = 1
        db.session.commit()

        result = analyze_recurring_issues(
            User.query.filter_by(username=user["username"]).one(),
            days=14,
            min_occurrences=2,
            limit=5,
        )

    assert result["count"] == 1
    assert result["items"][0]["occurrence_count"] == 4
    assert result["items"][0]["affected_machine"] == "Anlage 4"
    assert result["items"][0]["error_code"] == "E104"
    assert result["items"][0]["common_solution"] == "Sensor reinigen"
    assert "Knowledge-Base" in result["items"][0]["recommendation"]


def test_recurring_issue_trends_ignore_unrelated_single_entries(
    app,
    make_user,
    make_error_entry,
):
    """Verify unrelated one-off errors are not reported as recurring trends."""
    user = make_user(
        username="recurring_issue_empty_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    make_error_entry(
        "Anlage 1",
        "E100",
        "Temperatur hoch",
        department_name="Instandhaltung",
        description="Spindeltemperatur hoch.",
    )
    make_error_entry(
        "Anlage 2",
        "H200",
        "Hydraulikdruck niedrig",
        department_name="Instandhaltung",
        description="Druck faellt ab.",
    )

    with app.app_context():
        result = analyze_recurring_issues(
            User.query.filter_by(username=user["username"]).one(),
            days=30,
            min_occurrences=2,
        )

    assert result["count"] == 0
    assert result["items"] == []
