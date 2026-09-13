"""Workflow service helpers."""

import logging

from app.security import has_dashboard_permission
from app.services.document_service import generate_maintenance_report
from app.services.error_service import close_error_entry
from app.services.task_service import complete_task

logger = logging.getLogger(__name__)


def complete_task_workflow(task, user, payload=None):
    """Complete a task, optionally close its incident and generate a report.

    ``close_error_entry`` closes the incident the work order was raised for.
    The permission is checked before anything changes, so a refused request
    leaves the task open.
    """
    payload = payload or {}
    entry = task.error_entry if payload.get("close_error_entry") else None
    if entry is not None and entry.status != "closed":
        if not has_dashboard_permission(user, "errors", "write"):
            return None, None, {"error": "Keine Berechtigung, die Stoerung zu schliessen"}, 403
    else:
        entry = None

    updated, error, status = complete_task(task, user)
    if error:
        return None, None, error, status
    if entry is not None:
        close_error_entry(entry, user)

    document = None
    if payload.get("generate_report"):
        try:
            document = generate_maintenance_report(updated, user, payload)
        except (OSError, ValueError) as exc:
            logger.exception(
                "maintenance_report_generation_failed task_id=%s user_id=%s",
                task.id,
                user.id,
            )
            return updated, None, {"error": str(exc)}, 500

    return updated, document, None, status
