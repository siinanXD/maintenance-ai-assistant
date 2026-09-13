"""Link tasks to incidents and record stock movements.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-13 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    """Add task.error_entry_id and the inventory_movement table."""
    inspector = inspect(op.get_bind())
    task_columns = {column["name"] for column in inspector.get_columns("task")}
    if "error_entry_id" not in task_columns:
        with op.batch_alter_table("task") as batch:
            batch.add_column(sa.Column("error_entry_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_task_error_entry_id",
                "error_entry",
                ["error_entry_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index("ix_task_error_entry_id", ["error_entry_id"])

    if "inventory_movement" not in inspector.get_table_names():
        op.create_table(
            "inventory_movement",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("material_id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=True),
            sa.Column("quantity_change", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=20), nullable=False),
            sa.Column("note", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["material_id"], ["inventory_material.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_inventory_movement_material_created",
            "inventory_movement",
            ["material_id", "created_at"],
        )
        op.create_index("ix_inventory_movement_task", "inventory_movement", ["task_id"])


def downgrade():
    """Remove stock movements and the task-incident link."""
    op.drop_index("ix_inventory_movement_task", table_name="inventory_movement")
    op.drop_index("ix_inventory_movement_material_created", table_name="inventory_movement")
    op.drop_table("inventory_movement")
    with op.batch_alter_table("task") as batch:
        batch.drop_index("ix_task_error_entry_id")
        batch.drop_constraint("fk_task_error_entry_id", type_="foreignkey")
        batch.drop_column("error_entry_id")
