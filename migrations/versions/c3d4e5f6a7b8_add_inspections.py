"""Add inspection plans and maintenance records.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-13 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    """Add plan kind and legal basis, and the maintenance_record table."""
    inspector = inspect(op.get_bind())
    plan_columns = {column["name"] for column in inspector.get_columns("maintenance_plan")}
    with op.batch_alter_table("maintenance_plan") as batch:
        if "kind" not in plan_columns:
            batch.add_column(
                sa.Column(
                    "kind", sa.String(length=20), nullable=False, server_default="maintenance"
                )
            )
        if "legal_basis" not in plan_columns:
            batch.add_column(
                sa.Column("legal_basis", sa.String(length=120), nullable=False, server_default="")
            )

    if "maintenance_record" not in inspector.get_table_names():
        op.create_table(
            "maintenance_record",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("performed_on", sa.Date(), nullable=False),
            sa.Column("performed_by", sa.String(length=120), nullable=False),
            sa.Column("result", sa.String(length=20), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("follow_up_task_id", sa.Integer(), nullable=True),
            sa.Column("recorded_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["plan_id"], ["maintenance_plan.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["follow_up_task_id"], ["task.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["recorded_by"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_maintenance_record_plan_performed",
            "maintenance_record",
            ["plan_id", "performed_on"],
        )


def downgrade():
    """Remove maintenance records and plan kind columns."""
    op.drop_index("ix_maintenance_record_plan_performed", table_name="maintenance_record")
    op.drop_table("maintenance_record")
    with op.batch_alter_table("maintenance_plan") as batch:
        batch.drop_column("legal_basis")
        batch.drop_column("kind")
