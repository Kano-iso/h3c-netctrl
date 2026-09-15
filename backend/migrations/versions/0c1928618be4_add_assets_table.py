"""add assets table (+ S1-027: 空库 bootstrap 幂等补建 devices/logs 基表)

Revision ID: 0c1928618be4
Revises: 
Create Date: 2026-06-14 17:32:03.529911

S1-027 契约修复：本迁移链是「棕地」链——002/003/004 等对 create_all 时代预建的
devices/logs 基表做 ALTER，但迁移从未创建这两张表；全新库 `alembic upgrade head`
会在 003（logs.error_message）处失败，生产新装无法启动。001 是链起点，因此在此
幂等补建缺失基表（仅基础列，后续迁移各自加列）；已有库（001 已记录在
alembic_version）不重跑、不受影响。downgrade 只回滚 assets（与 R7 保守策略一致：
SQLite 无法安全 drop 列/表所有权之外的基表，基表不属于本迁移）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c1928618be4"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _bootstrap_base_tables() -> None:
    """幂等补建迁移链依赖、但历史上只由 create_all 预建的基表（devices/logs）。

    守卫风格与 006（backups 表缺失即跳过）一致：表已存在则跳过，绝不重复建表。
    仅建「基础列」——protected_interfaces/platform/sdn_role 由 004/009/011 加，
    error_message 由 003 加。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "devices" not in tables:
        op.create_table(
            "devices",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("host", sa.String(), nullable=False),
            sa.Column("port", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("password_encrypted", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if "logs" not in tables:
        op.create_table(
            "logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("device_id", sa.Integer(), nullable=False),
            sa.Column("device_name", sa.String(), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("detail", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def upgrade() -> None:
    _bootstrap_base_tables()
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("serial_number", sa.String(), nullable=True),
        sa.Column("firmware_version", sa.String(), nullable=True),
        sa.Column("cpu_usage", sa.String(), nullable=True),
        sa.Column("memory_usage", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("tags", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )


def downgrade() -> None:
    op.drop_table("assets")
