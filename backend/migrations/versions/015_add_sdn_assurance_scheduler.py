"""add S3-002 bounded periodic assurance: persistent due/claim slots + scheduled run audit

Revision ID: 015
Revises: 014
Create Date: 2026-09-25

S3-002 (next-s3-scheduler backend slice):
- New table: sdn_assurance_slots — one current scheduling window per VPC (named unique
  index uq_sdn_assurance_slots_vpc). Fields: slot_key (auditable window key), cadence,
  policy_version, generation (advances per window), status pending|claimed|completed|failed,
  due_at, claimed_at, claim_token + lease_expires_at (lease/takeover), run_id (fulfilling
  run), error. CHECK constraints reject new dirty data (status/cadence whitelists,
  generation >= 0). vpc_id FK to sdn_vpcs.id (ondelete=CASCADE).
- sdn_assurance_runs: SQLite table rebuild to ADD slot_key (auditable slot link) and error
  (failure reason) columns and EXTEND the status CHECK to ('started','completed','failed')
  so scheduled evaluations can record honest failure without faking completed/healthy.
- Parent deletion cleanup of slots/runs follows the project's ORM relationship cascade
  (SQLite FK pragma not enabled), consistent with SdnVpc.assurance_runs/scope_exceptions.
- Idempotent upgrade: slots created only if missing; runs rebuilt only when slot_key column
  is absent (a second upgrade is a no-op); downgrade reverses both.
"""
from alembic import op
import sqlalchemy as sa


revision = "015"
down_revision = "014"


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


def _has_column(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(
        sa.text(f"PRAGMA table_info({table_name})")
    ).fetchall()
    return any(r[1] == column_name for r in rows)


_RUNS_NEW_SCHEMA = (
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
    sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
    sa.Column("trigger", sa.String(10), nullable=False, server_default="manual"),
    sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
    sa.Column("started_at", sa.DateTime(), nullable=False),
    sa.Column("completed_at", sa.DateTime(), nullable=True),
    sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("policy_enabled", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("slot_key", sa.String(64), nullable=True),
    sa.Column("error", sa.String(500), nullable=True),
    sa.Column("facts_json", sa.Text(), nullable=False),
    sa.Column("summary_json", sa.Text(), nullable=False),
    sa.Column("items_json", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    sa.CheckConstraint(
        "trigger IN ('manual', 'scheduled', 'event')",
        name="ck_sdn_assurance_runs_trigger",
    ),
    sa.CheckConstraint(
        "status IN ('started', 'completed', 'failed')",
        name="ck_sdn_assurance_runs_status",
    ),
    sa.CheckConstraint("policy_version >= 0", name="ck_sdn_assurance_runs_policy_version"),
)


def _rebuild_runs(op, bind) -> None:
    """SQLite 重建 sdn_assurance_runs：加 slot_key/error 列 + 扩展 status CHECK + 唯一索引。"""
    old_cols = [
        "id", "vpc_id", "trigger", "status", "started_at", "completed_at",
        "policy_version", "policy_enabled", "facts_json", "summary_json",
        "items_json", "created_at",
    ]
    old_sql = ", ".join(old_cols)
    op.create_table("sdn_assurance_runs__new", *_RUNS_NEW_SCHEMA)
    bind.execute(
        sa.text(
            "INSERT INTO sdn_assurance_runs__new "
            f"({old_sql}) SELECT {old_sql} FROM sdn_assurance_runs"
        )
    )
    op.drop_table("sdn_assurance_runs")
    op.rename_table("sdn_assurance_runs__new", "sdn_assurance_runs")
    if not _has_index(bind, "sdn_assurance_runs", "ix_sdn_assurance_runs_vpc_id"):
        op.create_index("ix_sdn_assurance_runs_vpc_id", "sdn_assurance_runs", ["vpc_id"])
    _ensure_slot_key_unique_index(op, bind)


def _ensure_slot_key_unique_index(op, bind) -> None:
    """CR61：同窗口 (vpc_id, slot_key) 至多一条 run 的 DB 防御（slot_key NULL 允许多个 manual）。"""
    if not _has_index(bind, "sdn_assurance_runs", "uq_sdn_assurance_runs_vpc_slot_key"):
        op.create_index(
            "uq_sdn_assurance_runs_vpc_slot_key", "sdn_assurance_runs",
            ["vpc_id", "slot_key"], unique=True,
        )


def _rebuild_runs_legacy(op, bind) -> None:
    """反向重建：去掉 slot_key/error 列，status CHECK 还原为 ('started','completed')。

    014 不认识 failed；降级时映射为 started，保留历史行且不冒充成功。
    """
    cols = [
        "id", "vpc_id", "trigger", "status", "started_at", "completed_at",
        "policy_version", "policy_enabled", "facts_json", "summary_json",
        "items_json", "created_at",
    ]
    sql = ", ".join(cols)
    select_sql = ", ".join(
        "CASE WHEN status = 'failed' THEN 'started' ELSE status END AS status"
        if col == "status" else col
        for col in cols
    )
    op.create_table(
        "sdn_assurance_runs__new",
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
    bind.execute(
        sa.text(
            f"INSERT INTO sdn_assurance_runs__new ({sql}) "
            f"SELECT {select_sql} FROM sdn_assurance_runs"
        )
    )
    op.drop_table("sdn_assurance_runs")
    op.rename_table("sdn_assurance_runs__new", "sdn_assurance_runs")
    if not _has_index(bind, "sdn_assurance_runs", "ix_sdn_assurance_runs_vpc_id"):
        op.create_index("ix_sdn_assurance_runs_vpc_id", "sdn_assurance_runs", ["vpc_id"])


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "sdn_assurance_slots"):
        op.create_table(
            "sdn_assurance_slots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slot_key", sa.String(64), nullable=False),
            sa.Column("cadence", sa.String(10), nullable=False, server_default="manual"),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("due_at", sa.DateTime(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("claim_token", sa.String(64), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
            sa.Column("run_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('pending', 'claimed', 'completed', 'failed')",
                name="ck_sdn_assurance_slots_status",
            ),
            sa.CheckConstraint("generation >= 0", name="ck_sdn_assurance_slots_generation"),
            sa.CheckConstraint(
                "cadence IN ('manual', '10m', '30m', '1h')",
                name="ck_sdn_assurance_slots_cadence",
            ),
        )
    if not _has_index(bind, "sdn_assurance_slots", "uq_sdn_assurance_slots_vpc"):
        op.create_index("uq_sdn_assurance_slots_vpc", "sdn_assurance_slots", ["vpc_id"], unique=True)

    # runs 表升级（slot_key 缺失才重建；幂等）
    if _has_table(bind, "sdn_assurance_runs") and not _has_column(bind, "sdn_assurance_runs", "slot_key"):
        _rebuild_runs(op, bind)
    elif _has_table(bind, "sdn_assurance_runs"):
        # 已重建过（重复升级/旧 015）：确保 CR61 唯一索引存在（幂等）
        _ensure_slot_key_unique_index(op, bind)


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "sdn_assurance_slots"):
        op.drop_table("sdn_assurance_slots")

    # runs 表还原（slot_key 存在才重建；幂等）
    if _has_table(bind, "sdn_assurance_runs") and _has_column(bind, "sdn_assurance_runs", "slot_key"):
        _rebuild_runs_legacy(op, bind)
