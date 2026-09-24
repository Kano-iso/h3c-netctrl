"""add S2-014 VPC scope exceptions (business context, not device fact/config action)

Revision ID: 013
Revises: 012
Create Date: 2026-09-23

S2-014 (next-s1-backend):
- New table: sdn_scope_exceptions (VPC + EVPN Leaf granularity; one current row per
  (vpc_id, device_id) enforced by unique index uq_sdn_scope_exceptions_live).
- vpc_id / device_id carry FKs to sdn_vpcs.id / devices.id (ondelete=CASCADE). Deleting
  an exception row never cascades up to parents (child delete does not touch parents);
  parent deletion cleanup of exception children is driven by the project's ORM
  relationship cascade (SQLite FK pragma is not enabled in this project), consistent
  with SdnVpc.port_bindings/deployments and Device.asset/backups.
- CHECK constraints reject new dirty data: exception_type whitelist, non-empty reason,
  version >= 1. Malformed historical rows read as state=invalid (serializer).
- Idempotent upgrade: create table/index only if missing; empty-DB and old-DB both safe.
"""
from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"


def _has_table(bind, table_name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def _has_index(bind, table_name: str, index_name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND name=:n"),
        {"t": table_name, "n": index_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    # 新表（幂等：已存在则跳过，不重写旧迁移/不重建）。
    if not _has_table(bind, "sdn_scope_exceptions"):
        op.create_table(
            "sdn_scope_exceptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("exception_type", sa.String(30), nullable=False),
            sa.Column("reason", sa.String(200), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.CheckConstraint(
                "exception_type IN ('intentional_exclusion', 'maintenance_pause')",
                name="ck_sdn_scope_exceptions_type",
            ),
            sa.CheckConstraint("LENGTH(reason) > 0", name="ck_sdn_scope_exceptions_reason_nonempty"),
            sa.CheckConstraint("version >= 1", name="ck_sdn_scope_exceptions_version"),
        )
    # 关键唯一约束/索引（幂等：已存在则跳过）。
    if _has_table(bind, "sdn_scope_exceptions"):
        if not _has_index(bind, "sdn_scope_exceptions", "uq_sdn_scope_exceptions_live"):
            op.create_index(
                "uq_sdn_scope_exceptions_live",
                "sdn_scope_exceptions",
                ["vpc_id", "device_id"],
                unique=True,
            )
        if not _has_index(bind, "sdn_scope_exceptions", "ix_sdn_scope_exceptions_vpc"):
            op.create_index(
                "ix_sdn_scope_exceptions_vpc", "sdn_scope_exceptions", ["vpc_id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "sdn_scope_exceptions"):
        return
    for index_name in ("uq_sdn_scope_exceptions_live", "ix_sdn_scope_exceptions_vpc"):
        if _has_index(bind, "sdn_scope_exceptions", index_name):
            op.execute(f"DROP INDEX IF EXISTS {index_name}")
    op.drop_table("sdn_scope_exceptions")
