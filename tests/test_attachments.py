"""Tests for photo and PDF attachments on incidents and tasks."""

from io import BytesIO

from app.models import Attachment, Role

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _upload(client, headers, entity_type, entity_id, content, filename="foto.png"):
    """Post one multipart upload and return the response."""
    return client.post(
        "/api/v1/attachments",
        headers=headers,
        data={
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "file": (BytesIO(content), filename),
        },
        content_type="multipart/form-data",
    )


def test_technician_uploads_lists_downloads_and_deletes_incident_photo(
    client, make_user, make_error_entry, auth_headers
):
    """Verify the full photo lifecycle on an incident."""
    user = make_user(
        username="photo_tech", role=Role.INSTANDHALTUNG, department_name="Instandhaltung"
    )
    error_id = make_error_entry(
        "Presse 3", "P3-01", "Hydraulik leckt", department_name="Instandhaltung"
    )
    headers = auth_headers(user["username"])

    uploaded = _upload(client, headers, "error", error_id, PNG_BYTES, "leck.png")
    assert uploaded.status_code == 201
    attachment = uploaded.get_json()["data"]
    assert attachment["content_type"] == "image/png"
    assert attachment["is_image"] is True
    assert attachment["filename"] == "leck.png"
    assert "stored_filename" not in attachment

    listed = client.get(
        f"/api/v1/attachments?entity_type=error&entity_id={error_id}", headers=headers
    )
    assert [item["id"] for item in listed.get_json()["data"]] == [attachment["id"]]

    downloaded = client.get(attachment["file_url"], headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "image/png"
    assert downloaded.data == PNG_BYTES
    downloaded.close()

    deleted = client.delete(f"/api/v1/attachments/{attachment['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(attachment["file_url"], headers=headers).status_code == 404


def test_upload_detects_type_from_content_not_filename(client, make_user, make_task, auth_headers):
    """Verify a renamed executable is rejected and a JPEG with a wrong name is accepted."""
    user = make_user(username="photo_type_user", role=Role.PRODUKTION)
    task_id = make_task("Sensor tauschen", user["username"])
    headers = auth_headers(user["username"])

    rejected = _upload(client, headers, "task", task_id, b"MZ\x90\x00binary", "foto.png")
    assert rejected.status_code == 415

    accepted = _upload(client, headers, "task", task_id, JPEG_BYTES, "kamera.png")
    assert accepted.status_code == 201
    assert accepted.get_json()["data"]["content_type"] == "image/jpeg"


def test_upload_rejects_oversized_files(app, client, make_user, make_task, auth_headers):
    """Verify the configured size limit is enforced."""
    user = make_user(username="photo_size_user", role=Role.PRODUKTION)
    task_id = make_task("Lager pruefen", user["username"])
    app.config["ATTACHMENT_MAX_BYTES"] = 32

    response = _upload(client, auth_headers(user["username"]), "task", task_id, PNG_BYTES)

    assert response.status_code == 413


def test_other_department_cannot_see_or_upload(client, make_user, make_task, auth_headers):
    """Verify attachments follow the owning record's department visibility."""
    owner = make_user(username="photo_owner", role=Role.PRODUKTION, department_name="Produktion")
    outsider = make_user(username="photo_outsider", role=Role.IT, department_name="IT")
    task_id = make_task("Band reinigen", owner["username"], department_name="Produktion")
    attachment = _upload(client, auth_headers(owner["username"]), "task", task_id, PNG_BYTES)
    attachment_id = attachment.get_json()["data"]["id"]
    outsider_headers = auth_headers(outsider["username"])

    assert (
        client.get(
            f"/api/v1/attachments?entity_type=task&entity_id={task_id}", headers=outsider_headers
        ).status_code
        == 404
    )
    assert _upload(client, outsider_headers, "task", task_id, PNG_BYTES).status_code == 404
    assert (
        client.get(
            f"/api/v1/attachments/{attachment_id}/file", headers=outsider_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/attachments/{attachment_id}", headers=outsider_headers).status_code
        == 404
    )


def test_read_only_user_can_view_but_not_upload(
    client, make_user, make_task, set_dashboard_permission, auth_headers
):
    """Verify uploads need write permission on the owning dashboard."""
    writer = make_user(username="photo_writer", role=Role.PRODUKTION)
    reader = make_user(username="photo_reader", role=Role.PRODUKTION)
    set_dashboard_permission(reader["username"], "tasks", can_view=True, can_write=False)
    task_id = make_task("Filter wechseln", writer["username"])
    _upload(client, auth_headers(writer["username"]), "task", task_id, PNG_BYTES)
    reader_headers = auth_headers(reader["username"])

    listed = client.get(
        f"/api/v1/attachments?entity_type=task&entity_id={task_id}", headers=reader_headers
    )
    assert listed.status_code == 200
    assert len(listed.get_json()["data"]) == 1
    assert _upload(client, reader_headers, "task", task_id, PNG_BYTES).status_code == 403


def test_deleting_task_removes_its_attachments(app, client, make_user, make_task, auth_headers):
    """Verify attachments do not outlive their task."""
    user = make_user(username="photo_cleanup_user", role=Role.PRODUKTION)
    task_id = make_task("Kette schmieren", user["username"])
    headers = auth_headers(user["username"])
    _upload(client, headers, "task", task_id, PNG_BYTES)

    assert client.delete(f"/api/v1/tasks/{task_id}", headers=headers).status_code == 204
    with app.app_context():
        assert Attachment.query.filter_by(entity_type="task", entity_id=task_id).count() == 0


def test_invalid_entity_type_is_rejected(client, make_user, auth_headers):
    """Verify only incidents and tasks accept attachments."""
    user = make_user(username="photo_entity_user", role=Role.PRODUKTION)

    response = client.get(
        "/api/v1/attachments?entity_type=machine&entity_id=1",
        headers=auth_headers(user["username"]),
    )

    assert response.status_code == 400
