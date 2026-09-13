"""Store, list and delete photos and PDFs attached to incidents and tasks."""

import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Attachment, ErrorEntry, Task
from app.security import has_dashboard_permission
from app.services.document_storage_service import safe_storage_path

# entity_type -> (model, dashboard permission)
ATTACHMENT_OWNERS = {
    "error": (ErrorEntry, "errors"),
    "task": (Task, "tasks"),
}

# Detected from the first bytes, never from the client's file name or MIME header.
FILE_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"%PDF-", "application/pdf", ".pdf"),
)
MAX_ATTACHMENTS_PER_ENTITY = 20
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def detect_file_type(content):
    """Return ``(content_type, extension)`` for supported files, else ``None``."""
    for signature, content_type, extension in FILE_SIGNATURES:
        if content.startswith(signature):
            return content_type, extension
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def resolve_owner(entity_type, entity_id, user, action="view"):
    """Return the owning record when the user may perform ``action`` on it.

    Returns ``(owner, error, status)``. Records of another department look like
    missing records so their existence is not revealed.
    """
    spec = ATTACHMENT_OWNERS.get(str(entity_type or ""))
    if spec is None:
        return None, {"error": "entity_type must be 'error' or 'task'"}, 400
    model, dashboard = spec
    try:
        owner_id = int(entity_id)
    except (TypeError, ValueError):
        return None, {"error": "entity_id must be a number"}, 400
    if not has_dashboard_permission(user, dashboard, action):
        return None, {"error": "Forbidden"}, 403
    owner = db.session.get(model, owner_id)
    if owner is None or not (user.is_admin or owner.department_id == user.department_id):
        return None, {"error": "Record not found"}, 404
    return owner, None, 200


def list_attachments(entity_type, entity_id, user):
    """Return attachments of one visible record, newest first."""
    _owner, error, status = resolve_owner(entity_type, entity_id, user)
    if error:
        return None, error, status
    attachments = (
        Attachment.query.filter_by(entity_type=entity_type, entity_id=int(entity_id))
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
        .all()
    )
    return [attachment.to_dict() for attachment in attachments], None, 200


def save_attachment(entity_type, entity_id, file_storage, user):
    """Validate and store one uploaded file for a writable record."""
    owner, error, status = resolve_owner(entity_type, entity_id, user, action="write")
    if error:
        return None, error, status
    if not file_storage or not file_storage.filename:
        return None, {"error": "file is required"}, 400
    content = file_storage.read()
    if not content:
        return None, {"error": "file must not be empty"}, 400
    max_bytes = current_app.config.get("ATTACHMENT_MAX_BYTES", DEFAULT_MAX_BYTES)
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        return None, {"error": f"Datei ist größer als {limit_mb} MB"}, 413
    detected = detect_file_type(content)
    if detected is None:
        return None, {"error": "Nur Fotos (JPG, PNG, WebP) oder PDF sind erlaubt"}, 415
    existing = Attachment.query.filter_by(entity_type=entity_type, entity_id=owner.id).count()
    if existing >= MAX_ATTACHMENTS_PER_ENTITY:
        return None, {"error": f"Höchstens {MAX_ATTACHMENTS_PER_ENTITY} Dateien je Eintrag"}, 409

    content_type, extension = detected
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    path = attachment_path(entity_type, stored_filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    original = secure_filename(Path(file_storage.filename).name) or f"datei{extension}"
    attachment = Attachment(
        entity_type=entity_type,
        entity_id=owner.id,
        original_filename=original[:255],
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=len(content),
        uploaded_by=user.id,
    )
    db.session.add(attachment)
    db.session.commit()
    return attachment, None, 201


def get_visible_attachment(attachment_id, user, action="view"):
    """Return an attachment when its owning record is accessible."""
    attachment = db.session.get(Attachment, attachment_id)
    if attachment is None:
        return None, {"error": "Attachment not found"}, 404
    _owner, error, status = resolve_owner(
        attachment.entity_type, attachment.entity_id, user, action=action
    )
    if error:
        return None, error, status
    return attachment, None, 200


def delete_attachment(attachment_id, user):
    """Delete an attachment and its file; requires write access to the record."""
    attachment, error, status = get_visible_attachment(attachment_id, user, action="write")
    if error:
        return error, status
    path = attachment_path(attachment.entity_type, attachment.stored_filename)
    db.session.delete(attachment)
    db.session.commit()
    path.unlink(missing_ok=True)
    return None, 204


def delete_attachments_for(entity_type, entity_id):
    """Remove all attachments of a record that is being deleted (caller commits)."""
    attachments = Attachment.query.filter_by(entity_type=entity_type, entity_id=entity_id).all()
    for attachment in attachments:
        attachment_path(entity_type, attachment.stored_filename).unlink(missing_ok=True)
        db.session.delete(attachment)


def attachment_path(entity_type, stored_filename):
    """Return the safe absolute storage path of an attachment file."""
    base = Path(current_app.config["UPLOAD_FOLDER"]) / "attachments"
    return safe_storage_path(base, f"{entity_type}/{stored_filename}")
