"""add forced column to backups

Revision ID: 006
Revises: 005
Create Date: 2026-07-06

v2.6.1 fix-asset-backup-state-sync Task 2.1-2.3:
- 在 backups 表加 forced 字段（BOOLEAN DEFAULT 0）
- 语义：标记该备份是否经由 force=true 强制备份（绕过 asset 状态校验）
- 审计字段，不参与业务逻辑（不影响下载/回滚/删除/轮转）
- downgrade 路径：op.drop_column("backups", "forced")

v2.6.1 patch（修 ctrl / config 容器 alembic 启动卡死）：
- 3 容器 split 模式下，backups 表只存在于 data 容器
- ctrl / config 启动 alembic 跑 006 迁移时 add_column("backups") 会因表不存在抛错
- 守卫：表不存在时直接 return（alembic 仍会标 version=006，下次启动跳过此迁移）
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"


def upgrade() -> None:
    # v2.6.1 fix-asset-backup-state-sync Task 2.2:
    # 不可空 + server_default=0 兼容已有行（v2.6.0 之前的 backup 行视为非强制）
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "backups" not in insp.get_table_names():
        # backups 表不在当前 db（ctrl / config 容器不持有 backups 表）
        # → 直接跳过 add_column；alembic 框架会自动把 alembic_version 标为 006
        return
    op.add_column(
        "backups",
        sa.Column("forced", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    # v2.6.1 fix-asset-backup-state-sync Task 2.3:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "backups" not in insp.get_table_names():
        return
    op.drop_column("backups", "forced")
