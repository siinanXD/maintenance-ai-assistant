"""SQLAlchemy domain models for this bounded area."""

from datetime import date, timedelta

from app.domain_models.common import Priority, utc_now
from app.extensions import db


class Machine(db.Model):
    """Production machine with staffing requirements used by shift planning and inventory."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False)
    produced_item = db.Column(db.String(160), nullable=False, default="")
    required_employees = db.Column(db.Integer, nullable=False, default=1)
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True, index=True)
    criticality = db.Column(db.String(40), nullable=False, default="normal")
    status = db.Column(db.String(40), nullable=False, default="running")
    last_downtime_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    site = db.relationship("Site", back_populates="machines")
    materials = db.relationship("InventoryMaterial", back_populates="machine")
    maintenance_plans = db.relationship(
        "MaintenancePlan",
        back_populates="machine",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        """Return a JSON-serializable representation of the machine."""
        return {
            "id": self.id,
            "name": self.name,
            "produced_item": self.produced_item,
            "required_employees": self.required_employees,
            "site_id": self.site_id,
            "site": self.site.to_dict() if self.site else None,
            "criticality": self.criticality,
            "status": self.status,
            "last_downtime_at": (
                self.last_downtime_at.isoformat() if self.last_downtime_at else None
            ),
            "created_at": self.created_at.isoformat(),
        }


class InventoryMaterial(db.Model):
    """Spare part or consumable material tracked in inventory and linked to a machine."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    unit_cost = db.Column(db.Float, nullable=False, default=0)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    min_quantity = db.Column(db.Integer, nullable=False, default=0)
    criticality = db.Column(db.String(40), nullable=False, default="normal")
    lead_time_days = db.Column(db.Integer, nullable=False, default=0)
    manufacturer = db.Column(db.String(160), nullable=False, default="")
    site_id = db.Column(db.Integer, db.ForeignKey("site.id"), nullable=True, index=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"))
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    site = db.relationship("Site", back_populates="inventory_materials")
    machine = db.relationship("Machine", back_populates="materials")

    __table_args__ = (
        db.Index("ix_inventory_material_machine_id", "machine_id"),
        db.Index("ix_inventory_material_name", "name"),
    )

    @property
    def total_value(self):
        """Return the total material value based on unit cost and quantity."""
        return round((self.unit_cost or 0) * (self.quantity or 0), 2)

    def to_dict(self):
        """Return a JSON-serializable representation of the inventory material."""
        return {
            "id": self.id,
            "name": self.name,
            "unit_cost": self.unit_cost,
            "quantity": self.quantity,
            "min_quantity": self.min_quantity,
            "criticality": self.criticality,
            "lead_time_days": self.lead_time_days,
            "manufacturer": self.manufacturer,
            "site_id": self.site_id,
            "site": self.site.to_dict() if self.site else None,
            "machine_id": self.machine_id,
            "machine": self.machine.to_dict() if self.machine else None,
            "total_value": self.total_value,
            "is_below_minimum": self.quantity < self.min_quantity if self.min_quantity else False,
            "created_at": self.created_at.isoformat(),
        }


class InventoryMovement(db.Model):
    """One stock change: a withdrawal for a work order, a goods receipt or a correction.

    ``quantity_change`` is negative for withdrawals. The material's ``quantity``
    is updated in the same transaction, so the movements explain the stock.
    """

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(
        db.Integer, db.ForeignKey("inventory_material.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(db.Integer, db.ForeignKey("task.id", ondelete="SET NULL"))
    quantity_change = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(20), nullable=False)
    note = db.Column(db.String(200), nullable=False, default="")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    material = db.relationship("InventoryMaterial")
    task = db.relationship("Task")
    user = db.relationship("User")

    __table_args__ = (
        db.Index("ix_inventory_movement_material_created", "material_id", "created_at"),
        db.Index("ix_inventory_movement_task", "task_id"),
    )

    def to_dict(self):
        """Return a JSON-serializable representation of the movement."""
        unit_cost = self.material.unit_cost if self.material else 0
        return {
            "id": self.id,
            "material_id": self.material_id,
            "material_name": self.material.name if self.material else "",
            "task_id": self.task_id,
            "task_title": self.task.title if self.task else "",
            "quantity_change": self.quantity_change,
            "reason": self.reason,
            "note": self.note,
            "value": round(abs(self.quantity_change) * (unit_cost or 0), 2),
            "user": self.user.public_dict() if self.user else None,
            "created_at": self.created_at.isoformat(),
        }


PLAN_KIND_MAINTENANCE = "maintenance"
PLAN_KIND_INSPECTION = "inspection"
DUE_SOON_DAYS = 30


class MaintenancePlan(db.Model):
    """Recurring maintenance or legally required inspection for a machine.

    ``kind="inspection"`` marks obligations such as DGUV V3 or pressure vessel
    checks; ``legal_basis`` names the regulation. Each execution is documented
    as a ``MaintenanceRecord`` and moves ``next_due_date`` forward.
    """

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default=PLAN_KIND_MAINTENANCE)
    legal_basis = db.Column(db.String(120), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    interval_days = db.Column(db.Integer, nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    priority = db.Column(db.Enum(Priority), nullable=False, default=Priority.NORMAL)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"))
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    last_generated_task_id = db.Column(
        db.Integer,
        db.ForeignKey("task.id", ondelete="SET NULL"),
    )
    last_generated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    machine = db.relationship("Machine", back_populates="maintenance_plans")
    department = db.relationship("Department")
    creator = db.relationship("User", foreign_keys=[created_by])
    last_generated_task = db.relationship("Task", foreign_keys=[last_generated_task_id])
    records = db.relationship(
        "MaintenanceRecord",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="MaintenanceRecord.performed_on.desc(), MaintenanceRecord.id.desc()",
    )

    def due_state(self, today=None):
        """Return ``overdue``, ``due_soon`` (within 30 days) or ``ok``."""
        today = today or date.today()
        if self.next_due_date < today:
            return "overdue"
        if self.next_due_date <= today + timedelta(days=DUE_SOON_DAYS):
            return "due_soon"
        return "ok"

    __table_args__ = (
        db.Index(
            "ix_maintenance_plan_department_active_due",
            "department_id",
            "is_active",
            "next_due_date",
        ),
        db.Index("ix_maintenance_plan_machine_due", "machine_id", "next_due_date"),
    )

    def to_dict(self):
        """Return a JSON-serializable representation of the maintenance plan."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "legal_basis": self.legal_basis,
            "description": self.description,
            "interval_days": self.interval_days,
            "due_state": self.due_state() if self.is_active else "inactive",
            "last_record": self.records[0].to_dict() if self.records else None,
            "next_due_date": self.next_due_date.isoformat(),
            "priority": self.priority.value,
            "is_active": self.is_active,
            "machine_id": self.machine_id,
            "machine": self.machine.to_dict() if self.machine else None,
            "department": self.department.to_dict() if self.department else None,
            "created_by": self.created_by,
            "last_generated_task_id": self.last_generated_task_id,
            "last_generated_at": (
                self.last_generated_at.isoformat() if self.last_generated_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


RECORD_RESULTS = ("passed", "defects", "failed")


class MaintenanceRecord(db.Model):
    """Proof that a maintenance or inspection was carried out, with its result."""

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(
        db.Integer, db.ForeignKey("maintenance_plan.id", ondelete="CASCADE"), nullable=False
    )
    performed_on = db.Column(db.Date, nullable=False)
    performed_by = db.Column(db.String(120), nullable=False)
    result = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=False, default="")
    follow_up_task_id = db.Column(db.Integer, db.ForeignKey("task.id", ondelete="SET NULL"))
    recorded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    plan = db.relationship("MaintenancePlan", back_populates="records")
    follow_up_task = db.relationship("Task")
    recorder = db.relationship("User")

    __table_args__ = (db.Index("ix_maintenance_record_plan_performed", "plan_id", "performed_on"),)

    def to_dict(self):
        """Return a JSON-serializable representation of the record."""
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "performed_on": self.performed_on.isoformat(),
            "performed_by": self.performed_by,
            "result": self.result,
            "notes": self.notes,
            "follow_up_task_id": self.follow_up_task_id,
            "recorded_by": self.recorder.public_dict() if self.recorder else None,
            "created_at": self.created_at.isoformat(),
        }
