"""SQLAlchemy domain models for this bounded area."""

from datetime import UTC, date

from app.domain_models.common import Priority, TaskStatus, utc_now
from app.extensions import db


class Task(db.Model):
    """Maintenance task with lifecycle tracking from creation to completion."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    priority = db.Column(db.Enum(Priority), nullable=False, default=Priority.NORMAL)
    status = db.Column(db.Enum(TaskStatus), nullable=False, default=TaskStatus.OPEN)
    due_date = db.Column(db.Date, nullable=False, default=date.today)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    current_worker_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    started_at = db.Column(db.DateTime)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    completed_at = db.Column(db.DateTime)
    planned_minutes = db.Column(db.Integer, nullable=False, default=0)
    actual_minutes = db.Column(db.Integer, nullable=False, default=0)
    blocked_reason = db.Column(db.String(220), nullable=False, default="")
    # Incident this work order was raised for; kept when the incident is deleted.
    error_entry_id = db.Column(
        db.Integer, db.ForeignKey("error_entry.id", ondelete="SET NULL"), index=True
    )
    reopened_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    department = db.relationship("Department", back_populates="tasks")
    error_entry = db.relationship("ErrorEntry", foreign_keys=[error_entry_id])
    creator = db.relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_tasks",
    )
    current_worker = db.relationship(
        "User",
        foreign_keys=[current_worker_id],
        back_populates="assigned_tasks",
    )
    completed_by_user = db.relationship(
        "User",
        foreign_keys=[completed_by_id],
        back_populates="completed_tasks",
    )

    __table_args__ = (
        db.Index("ix_task_department_status_due", "department_id", "status", "due_date"),
        db.Index("ix_task_status_due_id", "status", "due_date", "id"),
        db.Index("ix_task_created_at", "created_at"),
        db.Index("ix_task_updated_at", "updated_at"),
    )

    def to_dict(self):
        """Return a JSON-serializable representation of the task."""
        response_minutes = None
        if self.started_at and self.created_at:
            response_minutes = round(_minutes_between(self.created_at, self.started_at), 2)
        cycle_minutes = None
        if self.completed_at and self.created_at:
            cycle_minutes = round(_minutes_between(self.created_at, self.completed_at), 2)
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "due_date": self.due_date.isoformat(),
            "department": self.department.to_dict() if self.department else None,
            "created_by": self.created_by,
            "creator": self.creator.public_dict() if self.creator else None,
            "current_worker_id": self.current_worker_id,
            "current_worker": (self.current_worker.public_dict() if self.current_worker else None),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_by": self.completed_by_id,
            "completed_by_user": (
                self.completed_by_user.public_dict() if self.completed_by_user else None
            ),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "planned_minutes": self.planned_minutes,
            "actual_minutes": self.actual_minutes,
            "blocked_reason": self.blocked_reason,
            "reopened_count": self.reopened_count,
            "error_entry_id": self.error_entry_id,
            "error_entry": (
                {
                    "id": self.error_entry.id,
                    "error_code": self.error_entry.error_code,
                    "title": self.error_entry.title,
                    "status": self.error_entry.status,
                }
                if self.error_entry
                else None
            ),
            "response_minutes": response_minutes,
            "cycle_minutes": cycle_minutes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def _comparable_datetime(value):
    """Return a timezone-free UTC datetime for safe arithmetic."""
    if value.tzinfo:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _minutes_between(start, end):
    """Return elapsed minutes between two datetimes despite tz storage differences."""
    return (_comparable_datetime(end) - _comparable_datetime(start)).total_seconds() / 60
