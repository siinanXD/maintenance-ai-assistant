"""Photos and files attached to incidents and tasks."""

from app.domain_models.common import utc_now
from app.extensions import db


class Attachment(db.Model):
    """A photo or PDF stored for one incident or task.

    ``entity_type`` and ``entity_id`` point at the owning record instead of a
    foreign key per table, so the same upload flow serves incidents and tasks.
    Visibility always follows the owning record.
    """

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(20), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(80), nullable=False, unique=True)
    content_type = db.Column(db.String(80), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    uploader = db.relationship("User", foreign_keys=[uploaded_by])

    __table_args__ = (db.Index("ix_attachment_entity", "entity_type", "entity_id"),)

    def to_dict(self):
        """Return a JSON-serializable representation without storage paths."""
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "is_image": self.content_type.startswith("image/"),
            "uploaded_by": self.uploader.public_dict() if self.uploader else None,
            "created_at": self.created_at.isoformat(),
            "file_url": f"/api/v1/attachments/{self.id}/file",
        }
