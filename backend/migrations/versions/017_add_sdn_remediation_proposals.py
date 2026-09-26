"""add S3-004 controlled remediation proposals (no device execution)

Revision ID: 017
Revises: 016
Create Date: 2026-09-25

S3-004 (next-s3-remediation-proposal backend slice):
- New table: sdn_remediation_proposals — audit-only, non-executing repair proposals bound
  to the assurance run, VPC version at creation, target Leaf and evidence snapshot id.
  Fields: vpc_id / run_id / item_key / device_id / action (fixed
  redeploy_vpc_on_device) / category (fixed confirmed_drift) / vpc_version_at_create /
  policy_version / evidence_snapshot_id / status proposed|stale|cancelled / expires_at /
  fingerprint (stable digest) / summary_json (semantic units + preserved + boundary only,
  never raw CLI/credentials/planned_config) / created_at / updated_at.
- Named unique index uq_sdn_remediation_proposals_run_item on (run_id, item_key): at most
  one proposal per run+item, backing idempotent/concurrent create.
- FK vpc_id → sdn_vpcs.id, run_id → sdn_assurance_runs.id, device_id → devices.id
  (all ondelete=CASCADE); parent deletion cleanup follows the project ORM relationship
  cascade (SQLite FK pragma not enabled).
- Idempotent upgrade: table created only if missing (index with it); downgrade drops the
  table (index with it). No changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa


revision = "017"
down_revision = "016"


def _has_table(bind, table_name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "sdn_remediation_proposals"):
        return  # 重复升级 no-op
    op.create_table(
        "sdn_remediation_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("sdn_assurance_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_key", sa.String(128), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, server_default="redeploy_vpc_on_device"),
        sa.Column("category", sa.String(32), nullable=False, server_default="confirmed_drift"),
        sa.Column("vpc_version_at_create", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint(
            "action IN ('redeploy_vpc_on_device')",
            name="ck_sdn_remediation_proposals_action",
        ),
        sa.CheckConstraint(
            "category IN ('confirmed_drift')",
            name="ck_sdn_remediation_proposals_category",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'stale', 'cancelled')",
            name="ck_sdn_remediation_proposals_status",
        ),
        sa.CheckConstraint(
            "vpc_version_at_create >= 0",
            name="ck_sdn_remediation_proposals_vpc_version",
        ),
    )
    op.create_index(
        "uq_sdn_remediation_proposals_run_item",
        "sdn_remediation_proposals",
        ["run_id", "item_key"],
        unique=True,
    )
    op.create_index("ix_sdn_remediation_proposals_vpc_id", "sdn_remediation_proposals", ["vpc_id"])
    op.create_index("ix_sdn_remediation_proposals_device_id", "sdn_remediation_proposals", ["device_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "sdn_remediation_proposals"):
        op.drop_table("sdn_remediation_proposals")  # 索引随表删除
