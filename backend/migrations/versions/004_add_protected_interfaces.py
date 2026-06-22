"""add protected_interfaces to devices

Revision ID: 004
Revises: 003
Create Date: 2026-06-22 15:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("protected_interfaces", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("devices", "protected_interfaces")
