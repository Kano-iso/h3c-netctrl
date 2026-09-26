"""add S3-003 event-triggered assurance: dedup event_key on assurance runs

Revision ID: 016
Revises: 015
Create Date: 2026-09-25

S3-003 (next-s3-event-assurance backend slice):
- sdn_assurance_runs: add nullable event_key (String 128) — stable internal source-event
  id/version for trigger=event audit runs (snapshot:{id} / scope-exc:{id}:v{ver} /
  scope-exc:{id}:cleared). manual/scheduled runs leave it NULL and are unaffected.
- Named unique index uq_sdn_assurance_runs_event_key: the same source event retried never
  duplicates history (SQLite treats NULLs as distinct, so multiple manual/scheduled rows
  stay allowed). This is the DB-level defense backing the event hook's dedup.
- Idempotent upgrade: add column only if missing, create index only if missing; downgrade
  reverses (drop index, SQLite table rebuild without the column, preserving the 015 schema
  including uq_sdn_assurance_runs_vpc_slot_key / ix_sdn_assurance_runs_vpc_id).
"""
from alembic import op
import sqlalchemy as sa


revision = "016"
down_revision = "015"


def _has_index(bind, table_name: str, index_name: str) -> bool:
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND name=:n"),
        {"t": table_name, "n": index_name},
    ).fetchone()
    return row is not None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(r[1] == column_name for r in rows)


# 015 schema（无 event_key）——降级重建目标，索引在重建后补齐。
_RUNS_015_SCHEMA = (
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


def _rebuild_runs_without_event_key(op, bind) -> None:
    """SQLite 重建 sdn_assurance_runs 回到 015 schema（去掉 event_key 列）。"""
    cols = [
        "id", "vpc_id", "trigger", "status", "started_at", "completed_at",
        "policy_version", "policy_enabled", "slot_key", "error",
        "facts_json", "summary_json", "items_json", "created_at",
    ]
    sql = ", ".join(cols)
    op.create_table("sdn_assurance_runs__new", *_RUNS_015_SCHEMA)
    bind.execute(
        sa.text(f"INSERT INTO sdn_assurance_runs__new ({sql}) SELECT {sql} FROM sdn_assurance_runs")
    )
    op.drop_table("sdn_assurance_runs")
    op.rename_table("sdn_assurance_runs__new", "sdn_assurance_runs")
    if not _has_index(bind, "sdn_assurance_runs", "ix_sdn_assurance_runs_vpc_id"):
        op.create_index("ix_sdn_assurance_runs_vpc_id", "sdn_assurance_runs", ["vpc_id"])
    if not _has_index(bind, "sdn_assurance_runs", "uq_sdn_assurance_runs_vpc_slot_key"):
        op.create_index(
            "uq_sdn_assurance_runs_vpc_slot_key", "sdn_assurance_runs",
            ["vpc_id", "slot_key"], unique=True,
        )


def _ensure_event_key_index(op, bind) -> None:
    if not _has_index(bind, "sdn_assurance_runs", "uq_sdn_assurance_runs_event_key"):
        op.create_index(
            "uq_sdn_assurance_runs_event_key", "sdn_assurance_runs", ["event_key"], unique=True
        )


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "sdn_assurance_runs", "event_key"):
        _ensure_event_key_index(op, bind)  # 已加过列（重复升级）→ 只补索引
        return
    op.add_column(
        "sdn_assurance_runs",
        sa.Column("event_key", sa.String(128), nullable=True),
    )
    _ensure_event_key_index(op, bind)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "sdn_assurance_runs", "event_key"):
        return  # 未升级过 → no-op
    if _has_index(bind, "sdn_assurance_runs", "uq_sdn_assurance_runs_event_key"):
        op.drop_index("uq_sdn_assurance_runs_event_key", table_name="sdn_assurance_runs")
    _rebuild_runs_without_event_key(op, bind)
