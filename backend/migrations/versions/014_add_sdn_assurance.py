"""add S3-001 VPC assurance policy + read-only evaluation runs

Revision ID: 014
Revises: 013
Create Date: 2026-09-25

S3-001 (next-s3-assurance backend slice):
- New table: sdn_assurance_policies (at most one per VPC, unique vpc_id; enabled +
  cadence(manual/10m/30m/1h) + response_mode fixed observe_only + optimistic version).
  vpc_id FK to sdn_vpcs.id (ondelete=CASCADE). CHECK constraints reject new dirty data:
  cadence whitelist, response_mode fixed, version >= 1.
- New table: sdn_assurance_runs (append-only read-only evaluation history; trigger
  manual|scheduled|event with write path allowing only manual for now; status
  started|completed; policy_version/policy_enabled snapshot; whitelisted JSON facts/
  summary/items). vpc_id FK ondelete=CASCADE, index on vpc_id.
- Parent deletion cleanup of policy/run children follows the project's ORM relationship
  cascade (SQLite FK pragma is not enabled), consistent with SdnVpc.port_bindings and
  SdnVpc.scope_exceptions. Deleting a policy/run row never cascades up to the parent VPC.
- Idempotent upgrade: create tables/indexes only if missing; empty-DB and old-DB both safe.
"""
from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"


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

    if not _has_table(bind, "sdn_assurance_policies"):
        op.create_table(
            "sdn_assurance_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("cadence", sa.String(10), nullable=False, server_default="manual"),
            sa.Column("response_mode", sa.String(20), nullable=False, server_default="observe_only"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.CheckConstraint(
                "cadence IN ('manual', '10m', '30m', '1h')",
                name="ck_sdn_assurance_policies_cadence",
            ),
            sa.CheckConstraint(
                "response_mode = 'observe_only'",
                name="ck_sdn_assurance_policies_response_mode",
            ),
            sa.CheckConstraint("version >= 1", name="ck_sdn_assurance_policies_version"),
        )
    # 每 VPC 至多一条策略：具名唯一索引（与 013 的 uq_sdn_scope_exceptions_live 同款
    # 做法——SQLite 的 table UniqueConstraint 只会生成 sqlite_autoindex，具名唯一
    # 索引才是可声明、可幂等校验的约束载体）。
    if not _has_index(bind, "sdn_assurance_policies", "uq_sdn_assurance_policies_vpc"):
        op.create_index(
            "uq_sdn_assurance_policies_vpc",
            "sdn_assurance_policies",
            ["vpc_id"],
            unique=True,
        )

    if not _has_table(bind, "sdn_assurance_runs"):
        op.create_table(
            "sdn_assurance_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("trigger", sa.String(10), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("policy_enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("facts_json", sa.Text(), nullable=False),
            sa.Column("summary_json", sa.Text(), nullable=False),
            sa.Column("items_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.CheckConstraint(
                "trigger IN ('manual', 'scheduled', 'event')",
                name="ck_sdn_assurance_runs_trigger",
            ),
            sa.CheckConstraint(
                "status IN ('started', 'completed')",
                name="ck_sdn_assurance_runs_status",
            ),
            sa.CheckConstraint("policy_version >= 0", name="ck_sdn_assurance_runs_policy_version"),
        )

    if not _has_index(bind, "sdn_assurance_runs", "ix_sdn_assurance_runs_vpc_id"):
        op.create_index("ix_sdn_assurance_runs_vpc_id", "sdn_assurance_runs", ["vpc_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "sdn_assurance_runs"):
        op.drop_table("sdn_assurance_runs")
    if _has_table(bind, "sdn_assurance_policies"):
        op.drop_table("sdn_assurance_policies")
