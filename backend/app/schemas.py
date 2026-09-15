from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, IPvAnyNetwork


_CIDR_PATTERN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$"


# --- Device 请求/响应模型 ---

class DeviceCreate(BaseModel):
    name: str
    host: str
    port: int = 830
    username: str
    password: str
    protected_interfaces: Optional[List[int]] = None
    sdn_role: Optional[str] = Field(default=None, pattern="^(evpn_leaf|evpn_spine|access)$")


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    protected_interfaces: Optional[List[int]] = None
    sdn_role: Optional[str] = Field(default=None, pattern="^(evpn_leaf|evpn_spine|access)$")


class DeviceResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    protected_interfaces: List[int] = []
    created_at: datetime
    updated_at: datetime
    # v2.6.2 fix-backup-restore-support Task 6: 设备是否支持 SCP 推回
    # True = 不支持（如 S6850），前端可在 UI 上禁用"回滚"按钮 + 提示
    # None = 未知（未探测过 / 探测失败），前端按"未知"处理
    # False = 支持
    restore_unsupported: Optional[bool] = None
    # v3.0 sdn-vpc-netconf-schema-xml T3: 设备 platform（LSTN / RSTN / None）
    # - LSTN: H3C V7 LSTN 老芯片平台 → L2VPN 业务走 CLI-over-NETCONF
    # - RSTN: H3C V7 RSTN 新芯片平台 → L2VPN 业务走 schema 化 NETCONF
    # - None: 未识别（executor 运行时调 get_platform_for_model() 推算）
    platform: Optional[str] = None
    # v3.4 SDN/VPC: 设备业务角色，只有 evpn_leaf 可作为 VPC 编排目标
    sdn_role: Optional[str] = None

    @field_validator("protected_interfaces", mode="before")
    @classmethod
    def _parse_protected_interfaces(cls, v):
        """数据库里存的是 JSON 字符串，这里解析为 list"""
        import json
        if isinstance(v, str):
            try:
                parsed = json.loads(v or "[]")
                if not isinstance(parsed, list):
                    return []
                # 强制 int 转换，过滤无效值
                return [int(x) for x in parsed if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()]
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        if isinstance(v, list):
            return v
        return []

    model_config = {"from_attributes": True}


# --- VLAN 请求/响应模型 ---

class VLANCreate(BaseModel):
    vlan_id: int = Field(ge=1, le=4094)
    name: str


class VLANUpdate(BaseModel):
    name: str


class VLANResponse(BaseModel):
    vlan_id: int
    name: str


# --- 统一返回格式 ---

class APIResponse(BaseModel):
    success: bool
    data: Optional[object] = None
    error: Optional[str] = None
    # v2.6 i18n: error_key 给前端用 vue-i18n 查翻译；error_params 是 i18n 插值参数
    # 兼容策略：error 必填（中文降级），error_key 可选；前端优先用 error_key 翻译，找不到再 fallback 到 error
    error_key: Optional[str] = None
    error_params: Optional[dict] = None


# --- Log 响应模型 ---

class LogResponse(BaseModel):
    id: int
    device_id: int
    device_name: str
    action: str
    detail: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Asset 请求/响应模型 ---

class AssetUpdate(BaseModel):
    location: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None


# --- ZTP onboard 请求模型 ---

class ZtpOnboardRequest(BaseModel):
    host: str = Field(..., min_length=1)
    name: Optional[str] = Field(default=None, max_length=100)
    username: str = Field(default="python", min_length=1)
    # S1-023：写操作密码必须显式提交（ztp-server 从 ZTP_ADMIN_PASS 注入）。
    # 绝不提供代码内默认口令——缺失时由调用方/后端明确失败。
    password: str = Field(..., min_length=1)
    port: int = Field(default=830, ge=1, le=65535)
    platform: Optional[str] = Field(default=None, pattern="^(lstn|rstn)$")
    collect_asset: bool = True
    source: str = Field(default="ztp-server", max_length=50)


class ZtpRecoveryOverrideRequest(BaseModel):
    host: str = Field(..., min_length=1)
    name: Optional[str] = Field(default=None, max_length=100)
    platform: str = Field(default="lstn", pattern="^(lstn|rstn)$")
    hcl_t7064p15: bool = False
    username: str = Field(default="python", min_length=1)
    # S1-023：password 可为空（None）——留空表示「沿用已有 override 密码」；
    # 无既有 override 时由后端从 ZTP_ADMIN_PASS 环境注入；两者都缺失 → 明确失败。
    # 绝无代码内默认口令；API 响应也不回显明文密码（见 ztp_recovery 脱敏）。
    password: Optional[str] = Field(default=None, min_length=1)
    netconf_port: int = Field(default=830, ge=1, le=65535)
    collect_asset: bool = False


# ── v3.0 SDN/VPC Schema ──

class SdnTenantCreate(BaseModel):
    """创建租户请求。RD/RT/L3VNI 由系统自动分配。"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class SdnTenantUpdate(BaseModel):
    """更新租户请求。仅允许修改 description。"""
    description: Optional[str] = Field(default=None, max_length=500)


class SdnTenantResponse(BaseModel):
    id: int
    name: str
    rd: str
    import_rt: str
    export_rt: str
    l3_vni: int
    auto_assigned: bool
    description: Optional[str] = None
    vpc_count: int = 0  # 关联 VPC 数量（列表/详情用）
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SdnVpcCreate(BaseModel):
    """创建 VPC 请求。VNI/Vsi-interface/VLAN 由系统自动分配。"""
    name: str = Field(..., min_length=1, max_length=100)
    tenant_id: int = Field(..., ge=1)
    cidr: str = Field(..., pattern=_CIDR_PATTERN)
    gateway_ip: Optional[str] = None  # 不传则取 CIDR 最后一个可用地址
    gateway_mac: Optional[str] = None  # 不传则从 VNI 推导
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("cidr")
    @classmethod
    def _validate_cidr_range(cls, v: str) -> str:
        """前缀长度 /8~/30，避免无意义网段。"""
        from app.utils.sdn_allocator import validate_cidr
        err = validate_cidr(v)
        if err:
            raise ValueError(err)
        return v


class SdnVpcResponse(BaseModel):
    id: int
    name: str
    tenant_id: int
    tenant_name: str
    cidr: str
    gateway_ip: str
    gateway_mac: Optional[str] = None
    vni: int
    vsi_name: str
    vsi_interface: int
    vlan_id: Optional[int] = None
    auto_assigned: bool
    status: str
    description: Optional[str] = None
    binding_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── v3.3 SDN/VPC Port Binding Schema ──

class SdnPortBindingCreate(BaseModel):
    """创建端口绑定请求。

    service_instance 优先；不传时默认走 access_vlan fallback（取 VPC 自动分配 VLAN）。
    """
    device_id: int = Field(..., ge=1)
    vpc_id: int = Field(..., ge=1)
    if_index: int = Field(..., ge=1)
    interface_name: str = Field(..., min_length=1, max_length=100)
    access_vlan: Optional[int] = Field(default=None, ge=1, le=4094)
    service_instance: Optional[int] = Field(default=None, ge=1, le=4094)


class SdnPortBindingDeployRequest(BaseModel):
    """端口绑定下发请求。"""
    mode: str = Field(default="auto", pattern="^(auto|service_instance|access_vlan)$")


class SdnPortBindingResponse(BaseModel):
    id: int
    device_id: int
    tenant_id: int
    tenant_name: str
    vpc_id: int
    vpc_name: str
    if_index: int
    interface_name: str
    access_vlan: Optional[int] = None
    service_instance: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SdnVpcFabricOperationRequest(BaseModel):
    """VPC 级 Fabric 编排请求。

    device_ids 不传时按默认 EVPN Fabric 成员选择；auto_apply 默认 false，先生成计划，人工确认后再 apply。
    """
    device_ids: Optional[List[int]] = None
    auto_apply: bool = False
    include_port_bindings: bool = True


class SdnVpcExpansionRequest(BaseModel):
    """已有 VPC 扩容接入口请求。

    扩容继承 VPC 的 CIDR/网关；expected_host_ip 仅用于扩容完成时的 ping 校验。
    """
    device_id: int = Field(..., ge=1)
    if_index: int = Field(..., ge=1)
    interface_name: str = Field(..., min_length=1, max_length=100)
    access_vlan: Optional[int] = Field(default=None, ge=1, le=4094)
    service_instance: Optional[int] = Field(default=None, ge=1, le=4094)
    expected_host_ip: Optional[str] = Field(default=None, min_length=7, max_length=45)
    auto_apply: bool = True


class SdnVpcExpansionCompleteRequest(BaseModel):
    """已有 VPC 扩容完成校验请求。"""
    expected_host_ip: Optional[str] = Field(default=None, min_length=7, max_length=45)
    force_validation: bool = True


# ── v3.0 SDN/VPC Deployment Schema（sdn-vpc-deployment-api）──

class SdnDeploymentCreate(BaseModel):
    """创建 deployment 请求。

    系统会调 VPCConfigPlanner 根据 vpc_id 自动生成 planned_config。
    action: "create" | "delete"
    unit: 可选；v3.0 unit 拆分（"vsi-l2" | "port-bind" | "l3vpn" | "vsi-l3"
          | "global" | "port-unbind" | "vpc-create-all"）；默认 "vpc-create-all"
          兼容老数据（全量下发）
    parent_deployment_id: 可选；unit 间依赖；同 vpc 同 action 下，parent 必须
          先 success 才能 apply 当前 unit
    """
    vpc_id: int = Field(..., ge=1)
    device_id: int = Field(..., ge=1)
    action: str = Field(..., pattern="^(create|delete)$")
    unit: Optional[str] = Field(
        default="vpc-create-all",
        pattern="^(vsi-l2|port-bind|l3vpn|vsi-l3|global|port-unbind|vpc-create-all)$",
    )
    parent_deployment_id: Optional[int] = Field(default=None, ge=1)
    port_binding_id: Optional[int] = Field(default=None, ge=1)


class SdnDeploymentResponse(BaseModel):
    """Deployment 响应。planned_config 是 JSON 字符串（list[dict]）。"""
    id: int
    vpc_id: int
    device_id: int
    action: str
    unit: str = "vpc-create-all"
    parent_deployment_id: Optional[int] = None
    port_binding_id: Optional[int] = None
    planned_config: Optional[str] = None  # JSON 字符串
    status: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SdnDeploymentUpdate(BaseModel):
    """更新 deployment 状态（vpc-apply 下发后回写）。"""
    status: Optional[str] = Field(default=None, pattern="^(pending|running|success|failed|unknown)$")
    error: Optional[str] = None


# ── S1 终端接入 Schema（next-s1-backend）──

class SdnAccessPreviewRequest(BaseModel):
    """服务端接入预览请求。持久化一条计划，不写设备/不建绑定/部署/操作。"""
    device_id: int = Field(..., ge=1)
    if_index: int = Field(..., ge=1)
    interface_name: str = Field(..., min_length=1, max_length=100)
    access_vlan: Optional[int] = Field(default=None, ge=1, le=4094)
    service_instance: Optional[int] = Field(default=None, ge=1, le=4094)
    expected_host_ip: Optional[str] = Field(default=None, min_length=7, max_length=45)
    # S1-027: 前端以语义 mode "l2"（L2 接入）请求；plan_port_bind 将其归一化为 auto。
    mode: Optional[str] = Field(default="auto", pattern="^(auto|service_instance|access_vlan|l2)$")


class SdnAccessExecuteRequest(BaseModel):
    """终端接入执行请求。携带 plan_id + 归一化请求字段 + 幂等键。

    执行只接受服务端 plan_id，不接受客户端 preview_fingerprint。
    归一化请求字段用于服务端重算请求 fingerprint（幂等）与 scope 校验。
    """
    idempotency_key: str = Field(..., min_length=8, max_length=64)
    plan_id: str = Field(..., min_length=1, max_length=36)
    device_id: int = Field(..., ge=1)
    if_index: int = Field(..., ge=1)
    interface_name: str = Field(..., min_length=1, max_length=100)
    access_vlan: Optional[int] = Field(default=None, ge=1, le=4094)
    service_instance: Optional[int] = Field(default=None, ge=1, le=4094)
    expected_host_ip: Optional[str] = Field(default=None, min_length=7, max_length=45)
    auto_apply: bool = False
    mode: Optional[str] = Field(default="auto", pattern="^(auto|service_instance|access_vlan|l2)$")


class SdnAccessCompleteRequest(BaseModel):
    """终端接入完成/验证请求。显式 POST，可 force 采集。"""
    expected_host_ip: Optional[str] = Field(default=None, min_length=7, max_length=45)
    force_validation: bool = True


class SdnWithdrawRequest(BaseModel):
    """终端接入撤回请求。"""
    reason: Optional[str] = Field(default=None, max_length=500)
