"""add error_message to logs table

Revision ID: 003
Revises: 002
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("logs", sa.Column("error_message", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("logs", "error_message")
