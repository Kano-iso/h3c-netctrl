"""add SDN role column to devices

Revision ID: 011
Revises: 010
Create Date: 2026-07-19

v3.4:
- Device.platform remains the device-template routing hint (LSTN/RSTN).
- Device.sdn_role records the business role used by SDN/VPC orchestration.
- Only sdn_role="evpn_leaf" is eligible for VPC deploy/withdraw/binding.
"""
from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"


def _has_column(insp, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "devices" not in insp.get_table_names():
        return

    if not _has_column(insp, "devices", "sdn_role"):
        op.add_column(
            "devices",
            sa.Column("sdn_role", sa.String(20), nullable=True),
        )
        op.create_index("ix_devices_sdn_role", "devices", ["sdn_role"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "devices" not in insp.get_table_names():
        return

    if _has_column(insp, "devices", "sdn_role"):
        op.drop_index("ix_devices_sdn_role", table_name="devices")
        op.drop_column("devices", "sdn_role")
