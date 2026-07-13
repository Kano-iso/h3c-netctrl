"""add unit and parent_deployment_id to sdn_deployments (v3.0 unit split)

Revision ID: 008
Revises: 007
Create Date: 2026-07-13

sdn-vpc-netconf-schema-xml T0.5:
- SdnDeployment 加 unit 字段（vsi-l2 / port-bind / l3vpn / vsi-l3 / global / port-unbind / vpc-create-all）
- SdnDeployment 加 parent_deployment_id 字段（unit 间依赖：vsi-l2 → vsi-l3）
- 老数据兼容：unit 默认 "vpc-create-all"
- 幂等守卫：通过 insp.get_columns() 跳过已存在字段
- 注意：config 容器无 devices 表，batch_alter_table 模式会 reflect 失败，
  改用 op.add_column + op.create_index（SQLite 3.46.1 支持 ADD COLUMN with default）
"""
from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"


def _has_column(insp, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sdn_deployments" not in insp.get_table_names():
        return

    if not _has_column(insp, "sdn_deployments", "unit"):
        op.add_column(
            "sdn_deployments",
            sa.Column(
                "unit",
                sa.String(30),
                nullable=False,
                server_default=sa.text("'vpc-create-all'"),
            ),
        )
        op.create_index("ix_sdn_deployments_unit", "sdn_deployments", ["unit"])

    if not _has_column(insp, "sdn_deployments", "parent_deployment_id"):
        # SQLite ALTER TABLE ADD COLUMN 不支持 inline FOREIGN KEY（必须表重建）
        # split 容器兼容：parent_deployment_id 在 config 容器下没有 sdn_deployments 行可指向
        # （仅做逻辑引用，应用层兜底；ForeignKey 约束在 ORM 层表达，DDL 层不加）
        op.add_column(
            "sdn_deployments",
            sa.Column("parent_deployment_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_sdn_deployments_parent_deployment_id",
            "sdn_deployments",
            ["parent_deployment_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sdn_deployments" not in insp.get_table_names():
        return

    if _has_column(insp, "sdn_deployments", "parent_deployment_id"):
        op.drop_index("ix_sdn_deployments_parent_deployment_id", table_name="sdn_deployments")
        op.drop_column("sdn_deployments", "parent_deployment_id")
    if _has_column(insp, "sdn_deployments", "unit"):
        op.drop_index("ix_sdn_deployments_unit", table_name="sdn_deployments")
        op.drop_column("sdn_deployments", "unit")
