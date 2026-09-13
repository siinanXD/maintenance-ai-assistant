"""SQLAlchemy domain models for this bounded area."""

from werkzeug.security import check_password_hash, generate_password_hash

from app.domain_models.common import Role, utc_now
from app.extensions import db


class User(db.Model):
    """Application user with role, department assignment, and dashboard permissions."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(Role), nullable=False, default=Role.PRODUKTION)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    department = db.relationship("Department", back_populates="users")
    employee = db.relationship("Employee", foreign_keys=[employee_id])
    created_tasks = db.relationship(
        "Task",
        foreign_keys="Task.created_by",
        back_populates="creator",
    )
    assigned_tasks = db.relationship(
        "Task",
        foreign_keys="Task.current_worker_id",
        back_populates="current_worker",
    )
    completed_tasks = db.relationship(
        "Task",
        foreign_keys="Task.completed_by_id",
        back_populates="completed_by_user",
    )
    dashboard_permissions = db.relationship(
        "DashboardPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Return whether the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        """Return whether the user has the master administrator role."""
        return self.role == Role.MASTER_ADMIN

    def public_dict(self):
        """Return the user reference other records may embed.

        Records such as tasks are readable by everyone with the matching
        dashboard permission. They must not carry the referenced user's email,
        permission matrix or linked employee record; to_dict() stays reserved
        for the user themself and for user administration.
        """
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
        }

    def to_dict(self):
        """Return a JSON-serializable representation of the user."""
        from app.permissions import serialize_permissions

        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "department": self.department.to_dict() if self.department else None,
            "employee": self.employee.to_dict("basic") if self.employee else None,
            "employee_id": self.employee_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "permissions": serialize_permissions(self),
        }


class TokenBlocklist(db.Model):
    """Stores revoked JWT JTIs so logout is enforced server-side."""

    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, unique=True, index=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def __repr__(self):
        """Return a concise debug representation."""
        return f"<TokenBlocklist jti={self.jti}>"
