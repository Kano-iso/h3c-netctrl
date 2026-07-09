"""add sdn tables (tenants / vpcs / port_bindings / deployments / validation_snapshots)

Revision ID: 007
Revises: 006
Create Date: 2026-07-08

v3.0 sdn-vpc-model-and-foundation:
- 新增 5 张 SDN 资源表
- split 兼容：ctrl/data 启动时通过 insp.get_table_names() 守卫跳过
"""
from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sdn_tenants" in insp.get_table_names():
        return

    op.create_table(
        "sdn_tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("rd", sa.String(50), unique=True, nullable=False),
        sa.Column("import_rt", sa.String(50), nullable=False),
        sa.Column("export_rt", sa.String(50), nullable=False),
        sa.Column("l3_vni", sa.Integer(), unique=True, nullable=False),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sdn_vpcs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("sdn_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cidr", sa.String(50), nullable=False),
        sa.Column("gateway_ip", sa.String(50), nullable=False),
        sa.Column("gateway_mac", sa.String(50), nullable=True),
        sa.Column("vni", sa.Integer(), unique=True, nullable=False),
        sa.Column("vsi_name", sa.String(100), nullable=False),
        sa.Column("vsi_interface", sa.Integer(), nullable=False),
        sa.Column("vlan_id", sa.Integer(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sdn_vpcs_tenant_id", "sdn_vpcs", ["tenant_id"])

    op.create_table(
        "sdn_port_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("sdn_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("if_index", sa.Integer(), nullable=False),
        sa.Column("interface_name", sa.String(100), nullable=False),
        sa.Column("access_vlan", sa.Integer(), nullable=True),
        sa.Column("service_instance", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sdn_port_bindings_device_id", "sdn_port_bindings", ["device_id"])
    op.create_index("ix_sdn_port_bindings_tenant_id", "sdn_port_bindings", ["tenant_id"])
    op.create_index("ix_sdn_port_bindings_vpc_id", "sdn_port_bindings", ["vpc_id"])

    op.create_table(
        "sdn_deployments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("planned_config", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sdn_deployments_vpc_id", "sdn_deployments", ["vpc_id"])
    op.create_index("ix_sdn_deployments_device_id", "sdn_deployments", ["device_id"])

    op.create_table(
        "sdn_validation_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vpc_id", sa.Integer(), sa.ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_data", sa.Text(), nullable=True),
        sa.Column("validation_result", sa.String(20), nullable=True),
        sa.Column("validation_details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sdn_validation_snapshots_vpc_id", "sdn_validation_snapshots", ["vpc_id"])
    op.create_index("ix_sdn_validation_snapshots_device_id", "sdn_validation_snapshots", ["device_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sdn_tenants" not in insp.get_table_names():
        return

    op.drop_table("sdn_validation_snapshots")
    op.drop_table("sdn_deployments")
    op.drop_table("sdn_port_bindings")
    op.drop_table("sdn_vpcs")
    op.drop_table("sdn_tenants")
