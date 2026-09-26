from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, ForeignKey, func, UniqueConstraint, text
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
    # S2-014：范围例外子行（设备删除时经 ORM cascade 清理，不留 orphan）
    scope_exceptions: Mapped[list["SdnScopeException"]] = relationship(
        "SdnScopeException", back_populates="device", cascade="all, delete-orphan"
    )


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
    # S1: 配置版本号，任何 mutation 递增；读取/验证不 bump
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    scope_exceptions: Mapped[list["SdnScopeException"]] = relationship(
        "SdnScopeException", back_populates="vpc", cascade="all, delete-orphan"
    )
    # S3-001：每 VPC 至多一条保障策略 + 只读评估历史（写评估只追加行，父删除级联清理）
    assurance_policy: Mapped[Optional["SdnAssurancePolicy"]] = relationship(
        "SdnAssurancePolicy", back_populates="vpc", cascade="all, delete-orphan", uselist=False
    )
    assurance_runs: Mapped[list["SdnAssuranceRun"]] = relationship(
        "SdnAssuranceRun", back_populates="vpc", cascade="all, delete-orphan"
    )
    # S3-002：每 VPC 至多一条调度窗口（父删除级联清理）
    assurance_slot: Mapped[Optional["SdnAssuranceSlot"]] = relationship(
        "SdnAssuranceSlot", back_populates="vpc", cascade="all, delete-orphan", uselist=False
    )


class SdnPortBinding(Base):
    """端口绑定关系（v3.0 SDN/VPC）

    描述"哪个交换机端口属于哪个 VPC"。
    本 change 仅建表，CRUD 端点留 sdn-port-binding。
    """
    __tablename__ = "sdn_port_bindings"
    __table_args__ = (
        # CR3: 同一 (device_id, if_index) 至多一条未释放(live)绑定；历史 unbound 行不受限。
        Index(
            "uq_sdn_port_bindings_live",
            "device_id",
            "if_index",
            unique=True,
            sqlite_where=text("status != 'unbound'"),
        ),
    )

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
    # S1: 版本号 + 不可变创建来源 + 可变最近变更者 + 关联操作
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_changed_by_operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
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
    # S1: 关联操作 + 版本号 + 认领时间/认领 attempt
    operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claimed_by_attempt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # S1-006 CR8: 配置下发完成/回读时间（因果 token，不得用 created_at 作完成证据）
    config_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    config_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
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
    # S1: 关联操作/尝试 + 采集开始/完成时间（因果窗口）
    operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    attempt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    collection_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    collection_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── v3.4 S1 终端接入：操作/尝试/单元/计划/资源声明/身份快照 ──
# 证据表对父资源（tenant/vpc/binding/device）一律存普通整数，不建外键，不随父表级联删除。
# attempts/units 仅从 operation/attempt 级联（operation 永不删，级联安全）。


class SdnScopeException(Base):
    """VPC + EVPN Leaf 粒度的范围例外（S2-014，业务上下文）。

    例外不是设备事实、健康状态或配置动作：只记录「该 Leaf 当前有意不纳入」或「因维护
    暂时暂停」的业务原因。同一 VPC + device 最多一条当前记录（数据库唯一约束保证）；
    清除 = 直接删除该行，不级联删除 operation/deployment/snapshot 历史（删除子行不会
    向上级联父对象）；父 VPC/device 删除时经 ORM relationship cascade（项目既有 SQLite
    级联方式，FK ondelete=CASCADE 声明一致）清理例外子行，不留下 orphan。过期例外在
    读取时返回 state=expired（畸形历史稳定降级 state=invalid），不自动删除、不写库。
    写操作只改数据库，零设备 I/O。CHECK 约束阻止新脏数据（非法 type / 空 reason /
    version<1）。
    """
    __tablename__ = "sdn_scope_exceptions"
    __table_args__ = (
        UniqueConstraint("vpc_id", "device_id", name="uq_sdn_scope_exceptions_live"),
        CheckConstraint(
            "exception_type IN ('intentional_exclusion', 'maintenance_pause')",
            name="ck_sdn_scope_exceptions_type",
        ),
        CheckConstraint("LENGTH(reason) > 0", name="ck_sdn_scope_exceptions_reason_nonempty"),
        CheckConstraint("version >= 1", name="ck_sdn_scope_exceptions_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    exception_type: Mapped[str] = mapped_column(String(30), nullable=False)  # intentional_exclusion / maintenance_pause
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 项目既有级联方式：ORM relationship cascade（SQLite FK pragma 未开，声明 FK 仅描述性）
    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="scope_exceptions")
    device: Mapped["Device"] = relationship("Device", back_populates="scope_exceptions")


class SdnAssurancePolicy(Base):
    """VPC 保障策略（S3-001，业务意图，非设备事实/配置动作）。

    每 VPC 至多一条（vpc_id 唯一约束）；enabled 决定自动保障是否开启，cadence 只记录
    产品意图（本包不实现 scheduler）；response_mode 固定 observe_only（本包不做任何
    下发/修复）。version 用于乐观并发（PUT 需携带当前版本，冲突即拒绝；GET 缺失时返回
    明确默认值但不写库）。
    """
    __tablename__ = "sdn_assurance_policies"
    __table_args__ = (
        Index("uq_sdn_assurance_policies_vpc", "vpc_id", unique=True),
        CheckConstraint(
            "cadence IN ('manual', '10m', '30m', '1h')",
            name="ck_sdn_assurance_policies_cadence",
        ),
        CheckConstraint(
            "response_mode = 'observe_only'",
            name="ck_sdn_assurance_policies_response_mode",
        ),
        CheckConstraint("version >= 1", name="ck_sdn_assurance_policies_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cadence: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    response_mode: Mapped[str] = mapped_column(String(20), default="observe_only", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="assurance_policy")


class SdnAssuranceRun(Base):
    """VPC 保障评估运行（S3-001 只读历史 + S3-002 scheduled 审计）。

    manual 恒为 completed；scheduled 运行保留可审计的 slot_key（对应
    sdn_assurance_slots 的窗口）与完成/失败状态（status ∈ started/completed/failed，
    error 记录失败原因）。facts_json/summary_json/items_json 是脱敏快照（不含原始配置/
    CLI/凭据/error）。写评估只追加行：并发多次 manual run 各自完整、互不覆盖；scheduled
    由 scheduler 经 slot CAS 保证同一窗口至多一条 completed；不写
    deployment/binding/operation/snapshot/claim，零设备 I/O。
    """
    __tablename__ = "sdn_assurance_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('manual', 'scheduled', 'event')",
            name="ck_sdn_assurance_runs_trigger",
        ),
        CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name="ck_sdn_assurance_runs_status",
        ),
        CheckConstraint("policy_version >= 0", name="ck_sdn_assurance_runs_policy_version"),
        # CR61 DB 防御：同一窗口（vpc_id, slot_key）至多一条 run；slot_key NULL（manual）
        # 在 SQLite 中允许多行，互不影响。scheduled 的原子路径正常不会触发，这里兜底
        # 防"同 slot_key 重复历史"。
        Index("uq_sdn_assurance_runs_vpc_slot_key", "vpc_id", "slot_key", unique=True),
        # S3-003 DB 防御：同源事件至多一条 event run（event_key NULL 允许多个
        # manual/scheduled）；同一源事件重试不重复历史。
        Index("uq_sdn_assurance_runs_event_key", "event_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # S3-002：scheduled 运行对应 sdn_assurance_slots 的窗口 key（manual 为 NULL）
    slot_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # S3-002：失败原因（仅 status=failed 时非空；不伪造 completed/healthy）
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # S3-003：event 运行的稳定去重 key（snapshot:{id} / scope-exc:{id}:v{ver} / :cleared），
    # 仅含稳定内部 ID/版本，不含凭据/原始 CLI；manual/scheduled 为 NULL。
    event_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="assurance_runs")


class SdnAssuranceSlot(Base):
    """VPC 保障调度窗口（S3-002，持久化 due/claim）。

    每个 VPC 至多一条当前窗口（vpc_id 具名唯一索引）。status:
    - pending：到期（due_at <= now）可被任何 scheduler tick 认领；
    - claimed：某 tick 已认领（claim_token + lease_expires_at）；lease 未过期不可接管，
      lease 过期可由其他 tick 接管（崩溃恢复，同一代际新 token）；
    - completed / failed：窗口终结，下一 tick 推进到下一代际窗口（generation+1，due 锚定
      终结时刻 + cadence，不补跑无限历史）。
    CAS 语义：认领/完成都按 (id, generation[, claim_token]) 条件更新并校验受影响行数——
    并发双 tick 对同一 VPC/同一窗口至多一个 completed scheduled run；旧代际迟到
    （token 或 generation 不匹配）不能覆盖新代际。失败/崩溃不永久饿死后续周期。
    写操作零设备 I/O。
    """
    __tablename__ = "sdn_assurance_slots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'completed', 'failed')",
            name="ck_sdn_assurance_slots_status",
        ),
        CheckConstraint("generation >= 0", name="ck_sdn_assurance_slots_generation"),
        CheckConstraint(
            "cadence IN ('manual', '10m', '30m', '1h')",
            name="ck_sdn_assurance_slots_cadence",
        ),
        # 与迁移 015 具名索引一致（ORM create_all 与 alembic 同构）
        Index("uq_sdn_assurance_slots_vpc", "vpc_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vpc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_vpcs.id", ondelete="CASCADE"), nullable=False
    )
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cadence: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    vpc: Mapped["SdnVpc"] = relationship("SdnVpc", back_populates="assurance_slot")


class SdnPlan(Base):
    """服务端预览计划（S1）

    plan_id 服务端生成不可变；semantic_hash 用于 stale 检测（≠ 请求 fingerprint）。
    预览只写这一条，不写设备、不建 binding/deployment/operation。
    """
    __tablename__ = "sdn_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_snapshot_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="valid", nullable=False)  # valid/consumed/expired/superseded
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SdnOperation(Base):
    """终端接入/撤回操作（S1）

    无公开删除路径，永久保留。tenant_id/vpc_id/device_id 为普通整数（无外键）。
    plan_id 存 sdn_plans.plan_id 字符串（按值引用，非外键）。
    """
    __tablename__ = "sdn_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)  # terminal_access / terminal_withdraw
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vpc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    expected_host_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    request_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False)
    # planned/applied/claimed/awaiting_wiring/applying/awaiting_validation/validating/succeeded/degraded/failed/withdrawn/withdrawing/reconciling/unknown
    # CR30: 当前动作代际令牌——准入时绑定 phase+attempt，收尾 CAS 匹配后原子清空（持久化于 DB，非进程内）
    active_attempt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SdnAttempt(Base):
    """执行/验证/对账尝试（S1）

    attempts 从 operation 级联（operation 永不删）；deployment_id 为普通整数（无外键）。
    """
    __tablename__ = "sdn_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # execute / validate / reconcile
    status: Mapped[str] = mapped_column(String(20), default="claimed", nullable=False)
    # claimed / running / succeeded / failed_known / unknown
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scope_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # S1-007 CR17: validate/reconcile attempt 的四维证据 + 网关 ping 结果
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SdnAttemptUnit(Base):
    """逐单元执行状态（S1）

    state: not_started / started / succeeded / failed_known / unknown
    设备 I/O 前写 started，I/O 后写终态 + evidence。
    """
    __tablename__ = "sdn_attempt_units"
    __table_args__ = (
        UniqueConstraint("attempt_id", "unit_index", name="uq_attempt_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sdn_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_name: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="not_started", nullable=False)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SdnResourceClaim(Base):
    """未释放资源声明（S1）

    互斥靠部分唯一索引 (resource_key) WHERE released_at IS NULL（在迁移 012 建立），
    覆盖 held 与 ambiguous：两者的 released_at 均为 NULL，都独占该资源。
    """
    __tablename__ = "sdn_resource_claims"
    __table_args__ = (
        Index(
            "uq_sdn_resource_claims_active",
            "resource_key",
            unique=True,
            sqlite_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    owner_operation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner_attempt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="held", nullable=False)  # held / released / ambiguous
    claimed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SdnIdentitySnapshot(Base):
    """父对象/受影响后代的身份快照（S1）

    父硬删除前写入；删除后历史仍可追溯。
    """
    __tablename__ = "sdn_identity_snapshots"
    __table_args__ = (
        Index("ix_identity_kind_id_created", "entity_kind", "entity_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_kind: Mapped[str] = mapped_column(String(30), nullable=False)  # tenant/vpc/device/binding/deployment/snapshot
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    identity_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
