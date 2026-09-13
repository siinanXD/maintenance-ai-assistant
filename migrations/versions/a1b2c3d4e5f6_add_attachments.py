"""Add photo and PDF attachments for incidents and tasks.

Revision ID: a1b2c3d4e5f6
Revises: f7b8c9d0e1f2
Create Date: 2026-09-13 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "a1b2c3d4e5f6"
down_revision = "f7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    """Create the attachment table."""
    if "attachment" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "attachment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=80), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_attachment_entity", "attachment", ["entity_type", "entity_id"])


def downgrade():
    """Drop the attachment table."""
    op.drop_index("ix_attachment_entity", table_name="attachment")
    op.drop_table("attachment")
