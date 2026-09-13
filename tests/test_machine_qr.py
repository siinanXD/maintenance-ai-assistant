"""Tests for machine QR labels and their short link."""

from app.models import Role


def test_machine_qr_code_is_svg_for_the_short_link(
    app, client, make_user, make_machine, auth_headers
):
    """Verify the QR endpoint returns an SVG that encodes the configured public address."""
    user = make_user(username="qr_viewer", role=Role.INSTANDHALTUNG)
    machine_id = make_machine(name="Presse QR 1")
    app.config["PUBLIC_BASE_URL"] = "https://werk.example.test/"

    response = client.get(
        f"/api/v1/machines/{machine_id}/qr.svg", headers=auth_headers(user["username"])
    )

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert response.data.startswith(b"<svg")
    assert b"<path" in response.data


def test_machine_qr_code_encodes_public_short_link(app, monkeypatch, make_machine):
    """Verify the label points at PUBLIC_BASE_URL/m/<id>, not the request host."""
    from app.extensions import db
    from app.machines import services
    from app.models import Machine

    encoded = []
    real_make = services.segno.make
    monkeypatch.setattr(
        services.segno,
        "make",
        lambda content, **kwargs: encoded.append(content) or real_make(content, **kwargs),
    )
    machine_id = make_machine(name="Presse QR 3")
    app.config["PUBLIC_BASE_URL"] = "https://werk.example.test/"

    with app.app_context():
        services.machine_qr_svg(db.session.get(Machine, machine_id), "http://localhost:5050/")

    assert encoded == [f"https://werk.example.test/m/{machine_id}"]


def test_machine_qr_code_requires_machine_permission(
    client, make_user, make_machine, set_dashboard_permission, auth_headers
):
    """Verify users without machine access cannot fetch labels."""
    user = make_user(username="qr_blocked", role=Role.PRODUKTION)
    set_dashboard_permission(user["username"], "machines", can_view=False)
    machine_id = make_machine(name="Presse QR 2")

    response = client.get(
        f"/api/v1/machines/{machine_id}/qr.svg", headers=auth_headers(user["username"])
    )

    assert response.status_code == 403


def test_short_link_redirects_to_machine_page(client):
    """Verify the address printed on the label opens the machine page."""
    response = client.get("/m/7")

    assert response.status_code == 302
    assert response.headers["Location"] == "/machines/7"
