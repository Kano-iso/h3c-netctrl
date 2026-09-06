from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    """异步任务记录（v24-feat-async-backup-status）

    存储备份/回滚等耗时操作的异步任务状态。
    - task_type: "backup" | "restore"
    - status: pending → running → success/failed/cancelled
    - progress: 0-100 整数
    - result_json: 任务结果 JSON 字符串（如备份返回的 backups 列表）
    """
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "backup" | "restore"
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=830)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    # 受保护的接口（JSON 字符串列表，存 if_index），配置时会被拦截
    protected_interfaces: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    # v3.0 sdn-vpc-netconf-schema-xml T3: 设备 platform 缓存
    # - LSTN: H3C V7 LSTN 老芯片平台（S6850 / S6805 / S6825）→ L2VPN 业务走 CLI-over-NETCONF
    # - RSTN: H3C V7 RSTN 新芯片平台（V9850 / S9820 / S12500R）→ L2VPN 业务走 schema 化 NETCONF
    # - None: 老数据 / 未识别 → 运行时调 get_platform_for_model() 推算
    # 详见 design.md T1.13d + T1.13e 探针结论
    platform: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    # v3.4 SDN/VPC: 业务角色，独立于 platform 下发通道。
    # - evpn_leaf: 已加入 EVPN Fabric，可作为 VPC 下发/扩容目标
    # - evpn_spine / access / None: 不作为 VPC 业务目标
    sdn_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)

    # 一对一关联资产信息
    asset: Mapped["Asset"] = relationship("Asset", back_populates="device", uselist=False, cascade="all, delete-orphan")
    # 一对多关联备份（设备删除时 CASCADE 清理）
    backups: Mapped[list["Backup"]] = relationship("Backup", back_populates="device", cascade="all, delete-orphan")


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=True)
    serial_number: Mapped[str] = mapped_column(String, nullable=True)
    firmware_version: Mapped[str] = mapped_column(String, nullable=True)
    software_package: Mapped[str] = mapped_column(String, nullable=True)
    location: Mapped[str] = mapped_column(String, nullable=True)
    tags: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="unknown")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 反向关联设备
    device: Mapped["Device"] = relationship("Device", back_populates="asset")


class Backup(Base):
    """配置备份记录（v2.2）

    存储设备 startup.cfg / running.cfg 备份元数据，文件本身存 /data/backups/{device_id}/。
    - locked=True 备份不参与轮转（永久保留直到用户主动解锁/删除）
    - 设备删除时 CASCADE 清理（连带删除磁盘文件由 backup.py 路由处理）
    """
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # 容器内绝对路径
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "startup" | "running"
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # 字节
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 hex
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # v2.6.1 fix-asset-backup-state-sync Task 2.4: 审计字段
    # - True: 经由 force=true 强制备份（绕过 asset 状态校验）
    # - False: 正常备份（asset online）
    # 不参与业务逻辑（不影响下载/回滚/删除/轮转），仅供审计查询
    forced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # 反向关联设备
    device: Mapped["Device"] = relationship("Device", back_populates="backups")

    __table_args__ = (
        # 复合索引：按设备 + 时间排序（列表/轮转查询）
        Index("ix_backups_device_created", "device_id", "created_at"),
    )


# ── v3.0 SDN/VPC 资源模型 ──

class SdnTenant(Base):
    """租户（v3.0 SDN/VPC）

    租户是网络隔离域，对应设备上的 ip vpn-instance 与 RD/RT 语义。
    一个租户下可有多个 VPC。
    - rd / import_rt / export_rt / l3_vni: 系统自动分配（auto_assigned=True）
    - 删除租户时 CASCADE 删除其下所有 VPC、绑定、部署、快照
    """
    __tablename__ = "sdn_tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    rd: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    import_rt: Mapped[str] = mapped_column(String(50), nullable=False)
    export_rt: Mapped[str] = mapped_column(String(50), nullable=False)
    l3_vni: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    auto_assigned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 一对多关联 VPC
    vpcs: Mapped[list["SdnVpc"]] = relationship(
        "SdnVpc", back_populates="tenant", cascade="all, delete-orphan"
    )


class SdnVpc(Base):
    """VPC（v3.0 SDN/VPC）

    项目内 VPC 等同于交换机侧一个可接入业务子网。
    - vni: 设备侧 L2VNI，fabric 全局唯一（设备能力验证前保守策略）
    - vsi_name / vsi_interface / vlan_id: 系统自动分配
    - gateway_ip: 默认取 CIDR 最后一个可用地址
    - gateway_mac: 分布式网关 MAC，默认自动生成
    - status: pending → deploying → active → degraded → failed
    """
    __tablename__ = "sdn_vpcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cidr: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_ip: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_mac: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vni: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    vsi_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vsi_interface: Mapped[int] = mapped_column(Integer, nullable=False)
    vlan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_assigned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 反向关联
    tenant: Mapped["SdnTenant"] = relationship("SdnTenant", back_populates="vpcs")
    port_bindings: Mapped[list["SdnPortBinding"]] = relationship(
        "SdnPortBinding", back_populates="vpc", cascade="all, delete-orphan"
    )
    deployments: Mapped[list["SdnDeployment"]] = relationship(
        "SdnDeployment", back_populates="vpc", cascade="all, delete-orphan"
    )


class SdnPortBinding(Base):
    """端口绑定关系（v3.0 SDN/VPC）

    描述"哪个交换机端口属于哪个 VPC"。
    本 change 仅建表，CRUD 端点留 sdn-port-binding。
    """
    __tablename__ = "sdn_port_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    if_index: Mapped[int] = mapped_column(Integer, nullable=False)
    interface_name: Mapped[str] = mapped_column(String(100), nullable=False)
    access_vlan: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    service_instance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 关联
    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="port_bindings")
    deployments: Mapped[list["SdnDeployment"]] = relationship(
        "SdnDeployment", back_populates="port_binding"
    )


class SdnDeployment(Base):
    """配置下发记录（v3.0 SDN/VPC）

    记录每次 VPC 配置下发的计划、状态和错误信息。
    - action: "create" | "delete" | "port_bind" | "port_unbind" | "gateway_delete"
    - planned_config: JSON 格式的计划配置命令序列
    - unit: v3.0 unit 拆分（"vsi-l2" | "port-bind" | "l3vpn" | "vsi-l3"
            | "global" | "port-unbind" | "vpc-create-all"）
            老数据兼容：默认 "vpc-create-all"（未拆分的全量下发）
    - parent_deployment_id: unit 间依赖（vsi-l2 必须先于 vsi-l3）；
            同 vpc 同 action 下，parent 先 success 才能 apply 当前 unit
    """
    __tablename__ = "sdn_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="vpc-create-all", index=True
    )
    parent_deployment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sdn_deployments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    port_binding_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sdn_port_bindings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    planned_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 关联
    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="deployments")
    port_binding: Mapped[Optional["SdnPortBinding"]] = relationship(
        "SdnPortBinding", back_populates="deployments"
    )
    # 自关联：unit 间依赖（vsi-l2 → vsi-l3 等）
    parent: Mapped[Optional["SdnDeployment"]] = relationship(
        "SdnDeployment", remote_side="SdnDeployment.id", foreign_keys=[parent_deployment_id]
    )


class SdnValidationSnapshot(Base):
    """状态采集与校验快照（v3.0 SDN/VPC）

    存储从设备 display 命令采集到的状态快照和校验结果。
    - snapshot_data: JSON 格式的采集结果
    - validation_result: active / degraded / failed
    - validation_details: JSON 格式的逐项校验结果
    """
    __tablename__ = "sdn_validation_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    validation_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
