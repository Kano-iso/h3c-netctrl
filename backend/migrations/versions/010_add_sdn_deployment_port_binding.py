"""add optional port binding reference to sdn deployments

Revision ID: 010
Revises: 009
Create Date: 2026-07-19

v3.3:
- SdnDeployment can reference SdnPortBinding for port-bind / port-unbind actions.
- Idempotent guard keeps split/container migrations tolerant.
"""
from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"


def _has_column(insp, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sdn_deployments" not in insp.get_table_names():
        return

    if not _has_column(insp, "sdn_deployments", "port_binding_id"):
        # SQLite ALTER TABLE ADD COLUMN 对 inline FOREIGN KEY 兼容性较差。
        # 与 008 parent_deployment_id 保持一致：DDL 只加列/索引，应用层维护引用语义。
        op.add_column(
            "sdn_deployments",
            sa.Column("port_binding_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_sdn_deployments_port_binding_id",
            "sdn_deployments",
            ["port_binding_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sdn_deployments" not in insp.get_table_names():
        return

    if _has_column(insp, "sdn_deployments", "port_binding_id"):
        op.drop_index("ix_sdn_deployments_port_binding_id", table_name="sdn_deployments")
        op.drop_column("sdn_deployments", "port_binding_id")
