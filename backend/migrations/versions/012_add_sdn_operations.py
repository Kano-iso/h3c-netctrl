"""add S1 terminal-access operations, attempts, units, plans, claims, identity snapshots

Revision ID: 012
Revises: 011
Create Date: 2026-09-08

S1 (next-s1-backend):
- New tables: sdn_plans, sdn_operations, sdn_attempts, sdn_attempt_units,
  sdn_resource_claims, sdn_identity_snapshots.
- Add compatible columns to existing SDN rows (version / operation linkage / causal window).
- Active-claim uniqueness rule covers held AND ambiguous via
  partial unique index (resource_key) WHERE released_at IS NULL.
- Evidence tables do NOT carry FKs to parent resources (tenant/vpc/binding/device),
  so history survives parent cascade deletion.
"""
from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"


def _has_column(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(r[1] == column_name for r in rows)


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


def _create_table_if_missing(bind, name: str, cols: list, extra: str = "") -> None:
    """Create a table if absent; if present, repair missing columns (partial-schema idempotence)."""
    if not _has_table(bind, name):
        op.create_table(name, *cols)
        if extra:
            op.execute(extra)
        return
    # CR10: 表已存在时补齐缺失列，避免部分建表后被误判完成。
    for col in cols:
        if col.primary_key:
            continue
        if _has_column(bind, name, col.name):
            continue
        c = col.copy()
        c.unique = None
        op.add_column(name, c)
        if col.unique:
            op.create_index(f"uq_{name}_{col.name}", name, [col.name], unique=True)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. 新表 ──
    _create_table_if_missing(
        bind,
        "sdn_plans",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("plan_id", sa.String(36), nullable=False, unique=True),
            sa.Column("semantic_hash", sa.String(64), nullable=False),
            sa.Column("version_snapshot_json", sa.Text(), nullable=True),
            sa.Column("scope_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="valid"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )
    _create_table_if_missing(
        bind,
        "sdn_operations",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("operation_type", sa.String(30), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("vpc_id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.String(36), nullable=True),
            sa.Column("expected_host_ip", sa.String(50), nullable=True),
            sa.Column("request_payload_json", sa.Text(), nullable=True),
            sa.Column("scope_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="planned"),
            sa.Column("active_attempt_id", sa.Integer(), nullable=True),
            sa.Column("active_started_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )
    _create_table_if_missing(
        bind,
        "sdn_attempts",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("operation_id", sa.Integer(), sa.ForeignKey("sdn_operations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("deployment_id", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="claimed"),
            sa.Column("owner", sa.String(64), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("scope_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )
    _create_table_if_missing(
        bind,
        "sdn_attempt_units",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("sdn_attempts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("unit_index", sa.Integer(), nullable=False),
            sa.Column("unit_name", sa.String(50), nullable=False),
            sa.Column("state", sa.String(20), nullable=False, server_default="not_started"),
            sa.Column("evidence_json", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )
    _create_table_if_missing(
        bind,
        "sdn_resource_claims",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("resource_key", sa.String(100), nullable=False),
            sa.Column("owner_operation_id", sa.Integer(), nullable=True),
            sa.Column("owner_attempt_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="held"),
            sa.Column("claimed_at", sa.DateTime(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )
    _create_table_if_missing(
        bind,
        "sdn_identity_snapshots",
        [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_kind", sa.String(30), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("identity_json", sa.Text(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        ],
    )

    # ── 2. 索引（缺索引补索引）──
    if _has_table(bind, "sdn_plans") and not _has_index(bind, "sdn_plans", "ix_sdn_plans_expires_at"):
        op.create_index("ix_sdn_plans_expires_at", "sdn_plans", ["expires_at"])
    if _has_table(bind, "sdn_operations") and not _has_index(bind, "sdn_operations", "ix_sdn_operations_vpc_device"):
        op.create_index("ix_sdn_operations_vpc_device", "sdn_operations", ["vpc_id", "device_id"])
    if _has_table(bind, "sdn_attempts") and not _has_index(bind, "sdn_attempts", "ix_sdn_attempts_operation_kind"):
        op.create_index("ix_sdn_attempts_operation_kind", "sdn_attempts", ["operation_id", "kind"])
    if _has_table(bind, "sdn_resource_claims") and not _has_index(bind, "sdn_resource_claims", "ix_sdn_resource_claims_key"):
        op.create_index("ix_sdn_resource_claims_key", "sdn_resource_claims", ["resource_key"])

    # ── 3. 部分唯一索引：held 与 ambiguous 都独占（released_at IS NULL）──
    if _has_table(bind, "sdn_resource_claims") and not _has_index(bind, "sdn_resource_claims", "uq_sdn_resource_claims_active"):
        op.execute(
            "CREATE UNIQUE INDEX uq_sdn_resource_claims_active "
            "ON sdn_resource_claims (resource_key) WHERE released_at IS NULL"
        )

    # ── 3b. CR3: 同一 (device_id, if_index) 至多一条 live 绑定（unbound 不受限）──
    if (
        _has_table(bind, "sdn_port_bindings")
        and _has_column(bind, "sdn_port_bindings", "device_id")
        and _has_column(bind, "sdn_port_bindings", "if_index")
        and not _has_index(bind, "sdn_port_bindings", "uq_sdn_port_bindings_live")
    ):
        op.execute(
            "CREATE UNIQUE INDEX uq_sdn_port_bindings_live "
            "ON sdn_port_bindings (device_id, if_index) WHERE status != 'unbound'"
        )

    # ── 3c. CR15: sdn_attempt_units (attempt_id, unit_index) 唯一约束 ──
    if (
        _has_table(bind, "sdn_attempt_units")
        and _has_column(bind, "sdn_attempt_units", "attempt_id")
        and _has_column(bind, "sdn_attempt_units", "unit_index")
        and not _has_index(bind, "sdn_attempt_units", "uq_attempt_unit")
    ):
        op.create_index("uq_attempt_unit", "sdn_attempt_units", ["attempt_id", "unit_index"], unique=True)

    # ── 3d. CR15: sdn_identity_snapshots (entity_kind, entity_id, created_at) 复合索引 ──
    if (
        _has_table(bind, "sdn_identity_snapshots")
        and _has_column(bind, "sdn_identity_snapshots", "entity_kind")
        and _has_column(bind, "sdn_identity_snapshots", "entity_id")
        and _has_column(bind, "sdn_identity_snapshots", "created_at")
        and not _has_index(bind, "sdn_identity_snapshots", "ix_identity_kind_id_created")
    ):
        op.create_index("ix_identity_kind_id_created", "sdn_identity_snapshots", ["entity_kind", "entity_id", "created_at"])

    # ── 4. 存量表加列 ──
    if _has_table(bind, "sdn_vpcs") and not _has_column(bind, "sdn_vpcs", "version"):
        op.add_column("sdn_vpcs", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))

    if _has_table(bind, "sdn_port_bindings"):
        for col in ("version", "created_by_operation_id", "last_changed_by_operation_id", "operation_id"):
            if not _has_column(bind, "sdn_port_bindings", col):
                if col == "version":
                    op.add_column("sdn_port_bindings", sa.Column(col, sa.Integer(), nullable=False, server_default="0"))
                else:
                    op.add_column("sdn_port_bindings", sa.Column(col, sa.Integer(), nullable=True))

    if _has_table(bind, "sdn_deployments"):
        for col in ("operation_id", "version", "claimed_at", "claimed_by_attempt_id", "config_started_at", "config_completed_at"):
            if not _has_column(bind, "sdn_deployments", col):
                if col == "version":
                    op.add_column("sdn_deployments", sa.Column(col, sa.Integer(), nullable=False, server_default="0"))
                elif col == "operation_id":
                    op.add_column("sdn_deployments", sa.Column(col, sa.Integer(), nullable=True))
                elif col in ("config_started_at", "config_completed_at", "claimed_at"):
                    # CR15: claimed_at 是 DateTime（与 ORM/design 一致），claimed_by_attempt_id 才是 Integer
                    op.add_column("sdn_deployments", sa.Column(col, sa.DateTime(), nullable=True))
                else:
                    op.add_column("sdn_deployments", sa.Column(col, sa.Integer(), nullable=True))
    if _has_table(bind, "sdn_deployments") and _has_column(bind, "sdn_deployments", "operation_id") \
            and not _has_index(bind, "sdn_deployments", "ix_sdn_deployments_operation_id"):
        op.create_index("ix_sdn_deployments_operation_id", "sdn_deployments", ["operation_id"])

    if _has_table(bind, "sdn_attempts") and not _has_column(bind, "sdn_attempts", "evidence_json"):
        op.add_column("sdn_attempts", sa.Column("evidence_json", sa.Text(), nullable=True))

    if _has_table(bind, "sdn_validation_snapshots"):
        for col in ("operation_id", "attempt_id", "collection_started_at", "collection_completed_at"):
            if not _has_column(bind, "sdn_validation_snapshots", col):
                op.add_column("sdn_validation_snapshots", sa.Column(col, sa.Integer(), nullable=True) if col in ("operation_id", "attempt_id") else sa.Column(col, sa.DateTime(), nullable=True))
    if _has_table(bind, "sdn_validation_snapshots") and _has_column(bind, "sdn_validation_snapshots", "operation_id") \
            and not _has_index(bind, "sdn_validation_snapshots", "ix_sdn_validation_snapshots_operation_id"):
        op.create_index("ix_sdn_validation_snapshots_operation_id", "sdn_validation_snapshots", ["operation_id"])

    # sdn_port_bindings.operation_id 索引
    if _has_table(bind, "sdn_port_bindings") and _has_column(bind, "sdn_port_bindings", "operation_id") \
            and not _has_index(bind, "sdn_port_bindings", "ix_sdn_port_bindings_operation_id"):
        op.create_index("ix_sdn_port_bindings_operation_id", "sdn_port_bindings", ["operation_id"])


def downgrade() -> None:
    bind = op.get_bind()

    # 反向顺序：先删部分唯一索引，再删表/列（列删除 SQLite 需批量重建，故只删新增表 + 索引，
    # 存量加列在 SQLite 下不能安全 drop，采用保守 downgrade：保留列但删新增表与索引）
    if _has_table(bind, "sdn_resource_claims") and _has_index(bind, "sdn_resource_claims", "uq_sdn_resource_claims_active"):
        op.execute("DROP INDEX IF EXISTS uq_sdn_resource_claims_active")
    if _has_table(bind, "sdn_port_bindings") and _has_index(bind, "sdn_port_bindings", "uq_sdn_port_bindings_live"):
        op.execute("DROP INDEX IF EXISTS uq_sdn_port_bindings_live")

    for t in ("sdn_identity_snapshots", "sdn_resource_claims", "sdn_attempt_units", "sdn_attempts", "sdn_operations", "sdn_plans"):
        if _has_table(bind, t):
            op.drop_table(t)
