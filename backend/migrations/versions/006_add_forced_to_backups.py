"""add forced column to backups

Revision ID: 006
Revises: 005
Create Date: 2026-07-06

v2.6.1 fix-asset-backup-state-sync Task 2.1-2.3:
- 在 backups 表加 forced 字段（BOOLEAN DEFAULT 0）
- 语义：标记该备份是否经由 force=true 强制备份（绕过 asset 状态校验）
- 审计字段，不参与业务逻辑（不影响下载/回滚/删除/轮转）
- downgrade 路径：op.drop_column("backups", "forced")
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"


def upgrade() -> None:
    # v2.6.1 fix-asset-backup-state-sync Task 2.2:
    # 不可空 + server_default=0 兼容已有行（v2.6.0 之前的 backup 行视为非强制）
    op.add_column(
        "backups",
        sa.Column("forced", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    # v2.6.1 fix-asset-backup-state-sync Task 2.3:
    op.drop_column("backups", "forced")
