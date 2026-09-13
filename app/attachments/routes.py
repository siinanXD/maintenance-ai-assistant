"""Attachment API: photos and PDFs for incidents and tasks."""

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.responses import service_error_response, success_response
from app.security import current_user
from app.services.attachment_service import (
    attachment_path,
    delete_attachment,
    get_visible_attachment,
    list_attachments,
    save_attachment,
)
from app.services.operations_tracking_service import record_event

attachments_bp = Blueprint("attachments", __name__)


@attachments_bp.get("")
@jwt_required()
def index():
    """List attachments of one incident or task (``entity_type``, ``entity_id``)."""
    items, error, status = list_attachments(
        request.args.get("entity_type"), request.args.get("entity_id"), current_user()
    )
    if error:
        return service_error_response(error, status)
    return success_response(items, message="Attachments loaded")


@attachments_bp.post("")
@jwt_required()
def upload():
    """Upload one file as multipart form data (``entity_type``, ``entity_id``, ``file``)."""
    user = current_user()
    entity_type = request.form.get("entity_type")
    attachment, error, status = save_attachment(
        entity_type, request.form.get("entity_id"), request.files.get("file"), user
    )
    if error:
        return service_error_response(error, status)
    record_event(
        "attachment.uploaded",
        "errors" if entity_type == "error" else "tasks",
        entity_type=entity_type,
        entity_id=attachment.entity_id,
        user=user,
        metadata={"content_type": attachment.content_type, "size_bytes": attachment.size_bytes},
        commit=True,
    )
    return success_response(attachment.to_dict(), 201, "Attachment uploaded")


@attachments_bp.get("/<int:attachment_id>/file")
@jwt_required()
def download(attachment_id):
    """Return the stored file with its detected content type."""
    attachment, error, status = get_visible_attachment(attachment_id, current_user())
    if error:
        return service_error_response(error, status)
    return send_file(
        attachment_path(attachment.entity_type, attachment.stored_filename),
        mimetype=attachment.content_type,
        download_name=attachment.original_filename,
        max_age=0,
    )


@attachments_bp.delete("/<int:attachment_id>")
@jwt_required()
def remove(attachment_id):
    """Delete one attachment."""
    error, status = delete_attachment(attachment_id, current_user())
    if error:
        return service_error_response(error, status)
    return "", 204
