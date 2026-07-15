"""add platform column to devices (v3.0 LSTN/RSTN routing)

Revision ID: 009
Revises: 008
Create Date: 2026-07-13

sdn-vpc-netconf-schema-xml T3:
- Device 表加 platform 字段（LSTN / RSTN / None）
- 业务下发按 device.platform 路由通道（LSTN 走 CLI / RSTN 走 schema XML）
- 老数据 platform=NULL 时，运行时调 get_platform_for_model() 推算
- 幂等守卫：通过 insp.get_columns() 跳过已存在字段
- 注意：config 容器无 devices 表（split 模式），本迁移在 monolith / ctrl 容器生效
"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"


def _has_column(insp, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "devices" not in insp.get_table_names():
        return

    if not _has_column(insp, "devices", "platform"):
        # SQLite ALTER TABLE ADD COLUMN 支持 nullable + 无 default
        op.add_column(
            "devices",
            sa.Column("platform", sa.String(20), nullable=True),
        )
        op.create_index("ix_devices_platform", "devices", ["platform"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "devices" not in insp.get_table_names():
        return

    if _has_column(insp, "devices", "platform"):
        op.drop_index("ix_devices_platform", table_name="devices")
        op.drop_column("devices", "platform")
