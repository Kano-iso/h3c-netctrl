"""replace cpu_usage/memory_usage with software_package

Revision ID: 002
Revises: 0c1928618be4
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "0c1928618be4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("software_package", sa.String(), nullable=True))
    op.drop_column("assets", "cpu_usage")
    op.drop_column("assets", "memory_usage")


def downgrade() -> None:
    op.add_column("assets", sa.Column("cpu_usage", sa.String(), nullable=True))
    op.add_column("assets", sa.Column("memory_usage", sa.String(), nullable=True))
    op.drop_column("assets", "software_package")
