"""SDN/VPC 路由（v3.0）

端点：
- POST   /api/sdn/tenants                  创建租户
- GET    /api/sdn/tenants                  租户列表
- GET    /api/sdn/tenants/{id}             租户详情
- PATCH  /api/sdn/tenants/{id}             更新租户 description
- DELETE /api/sdn/tenants/{id}             删除租户（CASCADE 清理 VPC / binding / deployment / snapshot）
- POST   /api/sdn/vpcs                     创建 VPC
- GET    /api/sdn/vpcs                     VPC 列表（可按 tenant_id 过滤）
- GET    /api/sdn/vpcs/{id}                VPC 详情
- POST   /api/sdn/deployments              创建 deployment（调 planner 生成 planned_config）
- GET    /api/sdn/deployments              deployment 列表（按 vpc_id / device_id / action 过滤）
- GET    /api/sdn/deployments/{id}         deployment 详情（apply 前查 planned_config）
- PATCH  /api/sdn/deployments/{id}         更新 status / error（补偿 / 排错用，业务下发走 apply）
- POST   /api/sdn/deployments/{id}/apply   业务配置下发（NETCONF，替代 ops-toolkit vpc-apply.sh）
- POST   /api/sdn/vpcs/{id}/devices/{id}/validation/sync  display 状态同步
- GET    /api/sdn/vpcs/{id}/devices/{id}/validation/latest 最近一次 display 快照
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, SdnAttempt, SdnDeployment, SdnOperation, SdnPortBinding, SdnScopeException, SdnTenant, SdnValidationSnapshot, SdnVpc
from app.schemas import (
    APIResponse,
    SdnDeploymentCreate,
    SdnDeploymentResponse,
    SdnDeploymentUpdate,
    SdnPortBindingCreate,
    SdnPortBindingDeployRequest,
    SdnPortBindingResponse,
    SdnTenantCreate,
    SdnTenantResponse,
    SdnTenantUpdate,
    SdnVpcCreate,
    SdnVpcExpansionCompleteRequest,
    SdnVpcExpansionRequest,
    SdnVpcFabricOperationRequest,
    SdnVpcResponse,
)
from app.i18n_keys import err, error_response
from app.services.sdn_deployment_executor import SdnDeploymentError, SdnDeploymentExecutor
from app.services.sdn_state_projection import (
    SNAPSHOT_TTL_SECONDS,
    SCOPE_AMBIGUOUS,
    SCOPE_NOT_TARGETED,
    SCOPE_TARGETED,
    SCOPE_WITHDRAWN,
    aggregate_vpc,
    baseline_unavailable_transition,
    build_leaf_projection,
    build_scope_member,
    build_transition,
)
from app.services.sdn_validation_collector import SdnValidationCollector
from app.services.sdn_attention import attention_projection
from app.services.sdn_operation_service import (
    SdnOperationError,
    acquire_claims,
    device_port_key,
    release_claims,
    snapshot_identity,
    tenant_key,
    vpc_device_key,
    vpc_key,
    AttemptUnitHooks,
    ensure_legacy_apply_operation,
)
from app.services.sdn_device_adapter import (
    H3cV7Adapter,
    UNIT_VSI_L3,
)
from app.services.vpc_config_planner import VPCConfigPlanner
from app.utils.device_access import get_device_with_password, get_devices_batch
from app.utils.sdn_allocator import SdnAllocator

logger = logging.getLogger("app")

router = APIRouter(prefix="/api/sdn", tags=["sdn"])


# ─────────── 内部辅助 ───────────

def _acquire_resource_claims(db: Session, keys: list[str]) -> list[str]:
    """CR9 复用守卫：按 rank 序认领一组资源（旧入口用合成 owner attempt_id=-1），成功后立即 commit。

    调用方需在 finally 里 release_claims(db, acquired, owner_attempt_id=-1)。
    """
    acquired = acquire_claims(db, keys, attempt_id=-1)
    db.commit()
    return acquired

def _tenant_to_response(tenant: SdnTenant, vpc_count: int = 0) -> SdnTenantResponse:
    return SdnTenantResponse(
        id=tenant.id,
        name=tenant.name,
        rd=tenant.rd,
        import_rt=tenant.import_rt,
        export_rt=tenant.export_rt,
        l3_vni=tenant.l3_vni,
        auto_assigned=tenant.auto_assigned,
        description=tenant.description,
        vpc_count=vpc_count,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


def _vpc_to_response(vpc: SdnVpc, tenant: SdnTenant, binding_count: int = 0) -> SdnVpcResponse:
    return SdnVpcResponse(
        id=vpc.id,
        name=vpc.name,
        tenant_id=vpc.tenant_id,
        tenant_name=tenant.name if tenant else "",
        cidr=vpc.cidr,
        gateway_ip=vpc.gateway_ip,
        gateway_mac=vpc.gateway_mac,
        vni=vpc.vni,
        vsi_name=vpc.vsi_name,
        vsi_interface=vpc.vsi_interface,
        vlan_id=vpc.vlan_id,
        auto_assigned=vpc.auto_assigned,
        status=vpc.status,
        description=vpc.description,
        binding_count=binding_count,
        created_at=vpc.created_at,
        updated_at=vpc.updated_at,
    )


def _binding_to_response(
    binding: SdnPortBinding,
    vpc: Optional[SdnVpc] = None,
    tenant: Optional[SdnTenant] = None,
) -> SdnPortBindingResponse:
    """SdnPortBinding ORM → SdnPortBindingResponse。"""
    vpc = vpc or binding.vpc
    tenant = tenant or (vpc.tenant if vpc else None)
    return SdnPortBindingResponse(
        id=binding.id,
        device_id=binding.device_id,
        tenant_id=binding.tenant_id,
        tenant_name=tenant.name if tenant else "",
        vpc_id=binding.vpc_id,
        vpc_name=vpc.name if vpc else "",
        if_index=binding.if_index,
        interface_name=binding.interface_name,
        access_vlan=binding.access_vlan,
        service_instance=binding.service_instance,
        status=binding.status,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _parse_protected_interfaces(device: Device) -> set[int]:
    """解析 Device.protected_interfaces JSON，失败时按空集合处理。"""
    if isinstance(device.protected_interfaces, list):
        return {int(x) for x in device.protected_interfaces if str(x).lstrip("-").isdigit()}
    try:
        parsed = json.loads(device.protected_interfaces or "[]")
    except (TypeError, json.JSONDecodeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {int(x) for x in parsed if str(x).lstrip("-").isdigit()}


def _create_sdn_deployment(
    db: Session,
    *,
    vpc_id: int,
    device_id: int,
    action: str,
    planned_config: str,
    unit: str = "vpc-create-all",
    parent_deployment_id: Optional[int] = None,
    port_binding_id: Optional[int] = None,
) -> SdnDeployment:
    """创建 deployment 记录，统一补齐 v3.3 新字段。"""
    # S1-016: 固化 VPC 版本因果——deployment 携带创建时的 vpc.version，
    # 使 _l2_ready_status 能证明「当前 VPC 配置」与「成功 create 部署」一致（不伪造）。
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    deployment = SdnDeployment(
        vpc_id=vpc_id,
        device_id=device_id,
        action=action,
        unit=unit,
        parent_deployment_id=parent_deployment_id,
        port_binding_id=port_binding_id,
        planned_config=planned_config,
        status="pending",
        version=vpc.version if vpc is not None else 0,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def _is_sdn_fabric_member(device: Device) -> bool:
    """判断设备是否可作为 SDN/VPC 编排目标。

    设备名和型号只能说明“像 Leaf”或“可能支持 EVPN”；platform 只能说明
    下发通道是 LSTN/RSTN，也不能证明它已经接入当前 EVPN fabric。v3.4 起
    只信独立业务角色 sdn_role，避免把接入交换机误卷入 VPC 下发。
    """
    return (getattr(device, "sdn_role", None) or "").lower() == "evpn_leaf"


def _resolve_fabric_targets(
    db: Session,
    device_ids: Optional[List[int]],
) -> tuple[list[Device], Optional[APIResponse]]:
    """解析 VPC 级编排目标设备。

    device_ids 为空时选择默认 EVPN Fabric 成员；显式传入时逐个校验存在和准入。
    """
    if device_ids:
        seen = set()
        ordered_ids = []
        for device_id in device_ids:
            if device_id in seen:
                continue
            seen.add(device_id)
            ordered_ids.append(device_id)
        found = {d.id: d for d in get_devices_batch(db, ordered_ids)}
        missing = [device_id for device_id in ordered_ids if device_id not in found]
        if missing:
            return [], error_response(err.SDN_DEVICE_NOT_FOUND, params={"id": missing[0]})
        targets = [found[device_id] for device_id in ordered_ids]
        invalid = [device for device in targets if not _is_sdn_fabric_member(device)]
        if invalid:
            return [], error_response(
                err.OPERATION_FAILED,
                params={"error": f"device {invalid[0].id} is not an EVPN fabric member"},
            )
        return targets, None

    try:
        devices = db.query(Device).order_by(Device.id).all()
    except Exception as e:
        logger.warning(f"本地 Device 表不可用，Fabric 目标选择走内部 API: {e}")
        try:
            from app.internal_api import get_devices
            resp = get_devices()
            if not resp.get("success"):
                return [], error_response(err.OPERATION_FAILED, params={"error": "failed to load devices"})
            from app.utils.device_access import _wrap_device_dict
            devices = [_wrap_device_dict(d) for d in resp.get("data", [])]
        except Exception as api_error:
            logger.error(f"Fabric 目标选择内部 API 失败: {api_error}")
            return [], error_response(err.OPERATION_FAILED, params={"error": str(api_error)})
    targets = [d for d in devices if _is_sdn_fabric_member(d)]
    if not targets:
        return [], error_response(err.OPERATION_FAILED, params={"error": "no EVPN fabric target devices found"})
    return targets, None


def _get_device_metadata(db: Session, device_id: int) -> tuple[Optional[object], Optional[APIResponse]]:
    """获取设备元数据，不解密密码（CR7：复用 device_access 显式分派，不靠异常）。"""
    from app.utils.device_access import get_device_metadata
    device, error = get_device_metadata(db, device_id)
    if error is not None:
        return None, error_response(err.SDN_DEVICE_NOT_FOUND, params={"id": device_id})
    return device, None


def _apply_if_requested(
    db: Session,
    deployments: list[SdnDeployment],
    auto_apply: bool,
) -> list[SdnDeployment]:
    """按创建顺序执行 deployments。auto_apply=false 时只返回计划。"""
    if not auto_apply:
        return deployments
    executor = SdnDeploymentExecutor()
    applied = []
    for deployment in deployments:
        applied.append(executor.execute(db, deployment.id))
    return applied


def _get_sdn_fabric_device_or_error(db: Session, device_id: int) -> tuple[Optional[object], Optional[APIResponse]]:
    """获取设备元数据并校验只能选择 EVPN Fabric 成员。"""
    device, device_error = _get_device_metadata(db, device_id)
    if device_error is not None:
        return None, device_error
    if not _is_sdn_fabric_member(device):
        return None, error_response(err.OPERATION_FAILED, params={"error": "only EVPN fabric devices can be selected"})
    return device, None


def _ping_from_vpc_gateway(db: Session, vpc: SdnVpc, device_id: int, host_ip: str) -> tuple[dict, Optional[APIResponse]]:
    """从 VPC 网关源地址 ping 新接入主机。"""
    device, password, device_err = get_device_with_password(db, device_id)
    if device_err is not None:
        return {}, device_err
    if not password:
        return {}, error_response(err.OPERATION_FAILED, params={"error": "device password unavailable"})

    from app.services.sdn_device_adapter import SDN_L3VPN_NAME
    from app.utils.ssh_executor import SSHExecutor

    command = f"ping -a {vpc.gateway_ip} -vpn-instance {SDN_L3VPN_NAME} {host_ip}"
    ssh = SSHExecutor(device.host, 22, device.username, password, timeout=30)
    results = ssh.execute_commands([command], delay_ms=300)
    result = results[0] if results else {"success": False, "output": "", "error": "no ping result"}
    output = result.get("output", "")
    success = bool(result.get("success")) and (
        "0.0% packet loss" in output
        or " 0% packet loss" in output
        or "received, 0.0% packet loss" in output
    )
    return {
        "command": command,
        "success": success,
        "output": output,
        "error": result.get("error"),
    }, None


# ─────────── 租户 ───────────

@router.post("/tenants", response_model=APIResponse)
def create_tenant(payload: SdnTenantCreate, db: Session = Depends(get_db)):
    """创建租户。RD/RT/L3VNI 由系统自动分配。"""
    # 名称查重
    existing = db.query(SdnTenant).filter(SdnTenant.name == payload.name).first()
    if existing:
        return error_response(err.SDN_TENANT_NAME_EXISTS, params={"name": payload.name})

    # 先 commit 一个空 tenant 占 id，以便 RD/RT 用 tenant.id 派生
    tenant = SdnTenant(
        name=payload.name,
        rd="pending",  # 临时占位，flush 后改写
        import_rt="pending",
        export_rt="pending",
        l3_vni=0,  # 临时占位
        auto_assigned=True,
        description=payload.description,
    )
    db.add(tenant)
    try:
        db.flush()  # 取 id
    except IntegrityError:
        db.rollback()
        return error_response(err.SDN_TENANT_NAME_EXISTS, params={"name": payload.name})

    # 分配 RD / RT（基于已分配的 id）
    rd = SdnAllocator.allocate_rd(tenant.id)
    import_rt, export_rt = SdnAllocator.allocate_rt(tenant.id)
    tenant.rd = rd
    tenant.import_rt = import_rt
    tenant.export_rt = export_rt

    # 分配 L3VNI（基于 DB 当前 max）
    l3_vni = SdnAllocator.allocate_l3vni(db)
    tenant.l3_vni = l3_vni

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return error_response(err.SDN_TENANT_RD_EXISTS, params={"rd": rd})

    db.refresh(tenant)
    logger.info(f"sdn: created tenant id={tenant.id} name={tenant.name} rd={rd} l3_vni={l3_vni}")
    return APIResponse(success=True, data=_tenant_to_response(tenant, vpc_count=0).model_dump(mode="json"))


@router.get("/tenants", response_model=APIResponse)
def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """租户列表（分页，含每个租户的 vpc_count）。"""
    total = db.query(func.count(SdnTenant.id)).scalar() or 0
    tenants = db.query(SdnTenant).order_by(SdnTenant.id).offset(skip).limit(limit).all()
    # 一次查所有 vpc_count（N+1 优化）
    counts = dict(
        db.query(SdnVpc.tenant_id, func.count(SdnVpc.id))
        .group_by(SdnVpc.tenant_id)
        .all()
    )
    items = [_tenant_to_response(t, vpc_count=counts.get(t.id, 0)).model_dump(mode="json") for t in tenants]
    return APIResponse(success=True, data={"total": total, "tenants": items})


@router.get("/tenants/{tenant_id}", response_model=APIResponse)
def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    """租户详情。"""
    tenant = db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first()
    if not tenant:
        return error_response(err.SDN_TENANT_NOT_FOUND, params={"id": tenant_id})
    vpc_count = db.query(func.count(SdnVpc.id)).filter(SdnVpc.tenant_id == tenant_id).scalar() or 0
    return APIResponse(success=True, data=_tenant_to_response(tenant, vpc_count=vpc_count).model_dump(mode="json"))


@router.patch("/tenants/{tenant_id}", response_model=APIResponse)
def update_tenant(tenant_id: int, payload: SdnTenantUpdate, db: Session = Depends(get_db)):
    """更新租户（仅 description）。"""
    tenant = db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first()
    if not tenant:
        return error_response(err.SDN_TENANT_NOT_FOUND, params={"id": tenant_id})
    if payload.description is not None:
        tenant.description = payload.description
    db.commit()
    db.refresh(tenant)
    vpc_count = db.query(func.count(SdnVpc.id)).filter(SdnVpc.tenant_id == tenant_id).scalar() or 0
    return APIResponse(success=True, data=_tenant_to_response(tenant, vpc_count=vpc_count).model_dump(mode="json"))


@router.delete("/tenants/{tenant_id}", response_model=APIResponse)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    """删除租户（CR9：先认领 tenant/VPC claim，再快照证据 + CASCADE 删除，最后释放）。"""
    tenant = db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first()
    if not tenant:
        return error_response(err.SDN_TENANT_NOT_FOUND, params={"id": tenant_id})

    vpcs = db.query(SdnVpc).filter(SdnVpc.tenant_id == tenant_id).all()
    bindings = (
        db.query(SdnPortBinding)
        .filter(SdnPortBinding.vpc_id.in_([v.id for v in vpcs]))
        .all()
        if vpcs else []
    )
    claims = [tenant_key(tenant_id)]
    claims += [vpc_key(v.id) for v in vpcs]
    claims += [vpc_device_key(b.vpc_id, b.device_id) for b in bindings]

    # 认领：并发 mutation 会被唯一索引挡住，delete 要么全拿要么拒绝（不留半删）
    try:
        acquired = acquire_claims(db, claims, attempt_id=-1)
        db.commit()
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    # S1: 父删除前写身份快照（父 + 受影响后代），使历史在级联后仍可追溯
    snapshot_identity(db, entity_kind="tenant", entity_id=tenant.id, identity={
        "name": tenant.name, "rd": tenant.rd, "l3_vni": tenant.l3_vni,
    }, deleted=True)
    for vpc in vpcs:
        snapshot_identity(db, entity_kind="vpc", entity_id=vpc.id, identity={
            "name": vpc.name, "cidr": vpc.cidr, "vni": vpc.vni, "gateway_ip": vpc.gateway_ip,
        }, deleted=True)
        for binding in db.query(SdnPortBinding).filter(SdnPortBinding.vpc_id == vpc.id).all():
            snapshot_identity(db, entity_kind="binding", entity_id=binding.id, identity={
                "device_id": binding.device_id, "if_index": binding.if_index,
                "interface_name": binding.interface_name,
            }, deleted=True)
    db.flush()

    db.delete(tenant)
    db.commit()
    release_claims(db, acquired, owner_attempt_id=-1)
    db.commit()
    return APIResponse(success=True, data={"deleted": tenant_id})


# ─────────── VPC ───────────

@router.post("/vpcs", response_model=APIResponse)
def create_vpc(payload: SdnVpcCreate, db: Session = Depends(get_db)):
    """创建 VPC。VNI/Vsi-interface/VLAN/gateway 由系统自动分配。"""
    # 租户存在性校验
    tenant = db.query(SdnTenant).filter(SdnTenant.id == payload.tenant_id).first()
    if not tenant:
        return error_response(err.SDN_VPC_TENANT_NOT_FOUND, params={"tenant_id": payload.tenant_id})

    # 分配 VNI
    vni = SdnAllocator.allocate_l2vni(db)
    vsi_interface = SdnAllocator.allocate_vsi_interface(db)
    vlan_id = SdnAllocator.allocate_vlan(db)

    # gateway_ip 默认值
    gateway_ip = payload.gateway_ip or SdnAllocator.derive_gateway_ip(payload.cidr)
    # gateway_mac 默认值（用分配的 VNI 推导）
    gateway_mac = payload.gateway_mac or SdnAllocator.derive_gateway_mac(vni)

    vpc = SdnVpc(
        name=payload.name,
        tenant_id=payload.tenant_id,
        cidr=payload.cidr,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        vni=vni,
        vsi_name="pending",  # 临时占位，flush 后用 vpc.id 重算（ADR-103 vpc{id:04d}）
        vsi_interface=vsi_interface,
        vlan_id=vlan_id,
        auto_assigned=True,
        status="pending",
        description=payload.description,
    )
    db.add(vpc)
    try:
        db.flush()  # 拿 vpc.id
        vpc.vsi_name = SdnAllocator.build_vsi_name(vpc.id)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # 唯一约束冲突：VNI
        if "vni" in str(e.orig).lower() or "unique" in str(e.orig).lower():
            return error_response(err.SDN_VPC_VNI_EXISTS, params={"vni": vni})
        return error_response(err.SDN_ALLOCATION_FAILED, params={"error": str(e.orig)})

    db.refresh(vpc)
    logger.info(
        f"sdn: created vpc id={vpc.id} name={vpc.name} tenant={tenant.name} "
        f"vni={vni} vsi_interface={vsi_interface} vlan_id={vlan_id}"
    )
    return APIResponse(success=True, data=_vpc_to_response(vpc, tenant).model_dump(mode="json"))


@router.get("/vpcs", response_model=APIResponse)
def list_vpcs(
    tenant_id: int | None = Query(None, description="按租户过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """VPC 列表（可按 tenant_id 过滤）。"""
    q = db.query(SdnVpc)
    if tenant_id is not None:
        q = q.filter(SdnVpc.tenant_id == tenant_id)
    total = q.count()
    vpcs = q.order_by(SdnVpc.id).offset(skip).limit(limit).all()

    # 一次查 tenant 名称（N+1 优化）
    tenant_ids = {v.tenant_id for v in vpcs}
    tenants = {
        t.id: t
        for t in db.query(SdnTenant).filter(SdnTenant.id.in_(tenant_ids)).all()
    } if tenant_ids else {}

    vpc_ids = [v.id for v in vpcs]
    binding_counts = {
        vpc_id: count
        for vpc_id, count in db.query(SdnPortBinding.vpc_id, func.count(SdnPortBinding.id))
        .filter(SdnPortBinding.vpc_id.in_(vpc_ids))
        .group_by(SdnPortBinding.vpc_id)
        .all()
    } if vpc_ids else {}

    items = [
        _vpc_to_response(v, tenants.get(v.tenant_id), binding_count=binding_counts.get(v.id, 0)).model_dump(mode="json")
        for v in vpcs
    ]
    return APIResponse(success=True, data={"total": total, "vpcs": items})


@router.get("/vpcs/{vpc_id}", response_model=APIResponse)
def get_vpc(vpc_id: int, db: Session = Depends(get_db)):
    """VPC 详情。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    binding_count = db.query(func.count(SdnPortBinding.id)).filter(SdnPortBinding.vpc_id == vpc.id).scalar() or 0
    return APIResponse(success=True, data=_vpc_to_response(vpc, tenant, binding_count=binding_count).model_dump(mode="json"))


# ─────────── VPC 级 Fabric 编排 ───────────

@router.post("/vpcs/{vpc_id}/deploy", response_model=APIResponse)
def deploy_vpc_to_fabric(
    vpc_id: int,
    payload: SdnVpcFabricOperationRequest = SdnVpcFabricOperationRequest(),
    db: Session = Depends(get_db),
):
    """VPC 级部署编排：把一个用户动作展开为多台 EVPN 节点的 create/port-bind deployments。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    if not tenant:
        return error_response(err.SDN_VPC_TENANT_NOT_FOUND, params={"tenant_id": vpc.tenant_id})

    targets, target_error = _resolve_fabric_targets(db, payload.device_ids)
    if target_error is not None:
        return target_error

    # CR9: 认领 tenant + vpc + 各 vpc-device，串行化并发 deploy/withdraw/redeploy
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id)]
    keys += [vpc_device_key(vpc.id, d.id) for d in targets]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        deployments: list[SdnDeployment] = []
        target_ids = {d.id for d in targets}
        bindings_by_device: dict[int, list[SdnPortBinding]] = {}
        if payload.include_port_bindings:
            bindings = (
                db.query(SdnPortBinding)
                .filter(
                    SdnPortBinding.vpc_id == vpc.id,
                    SdnPortBinding.device_id.in_(target_ids),
                    SdnPortBinding.status.in_(("planned", "pending", "failed")),
                )
                .order_by(SdnPortBinding.id)
                .all()
            )
            for binding in bindings:
                bindings_by_device.setdefault(binding.device_id, []).append(binding)

        for device in targets:
            vpc_units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
            vpc_deployment = _create_sdn_deployment(
                db,
                vpc_id=vpc.id,
                device_id=device.id,
                action="create",
                unit="vpc-create-all",
                planned_config=VPCConfigPlanner.serialize(vpc_units),
            )
            deployments.append(vpc_deployment)

            for binding in bindings_by_device.get(device.id, []):
                bind_units = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
                bind_deployment = _create_sdn_deployment(
                    db,
                    vpc_id=vpc.id,
                    device_id=device.id,
                    action="port_bind",
                    unit="port-bind",
                    parent_deployment_id=vpc_deployment.id,
                    port_binding_id=binding.id,
                    planned_config=VPCConfigPlanner.serialize(bind_units),
                )
                binding.status = "pending"
                deployments.append(bind_deployment)

        vpc.status = "deploying" if payload.auto_apply else "planned"
        db.commit()

        deployments = _apply_if_requested(db, deployments, payload.auto_apply)
        items = [_deployment_to_response(d).model_dump(mode="json") for d in deployments]
        return APIResponse(
            success=True,
            data={
                "vpc_id": vpc.id,
                "operation": "deploy",
                "auto_apply": payload.auto_apply,
                "target_device_ids": [d.id for d in targets],
                "total": len(items),
                "deployments": items,
            },
        )
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/vpcs/{vpc_id}/withdraw", response_model=APIResponse)
def withdraw_vpc_from_fabric(
    vpc_id: int,
    payload: SdnVpcFabricOperationRequest = SdnVpcFabricOperationRequest(),
    db: Session = Depends(get_db),
):
    """VPC 级撤回编排：按设备先解绑端口，再撤回 VPC。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})

    targets, target_error = _resolve_fabric_targets(db, payload.device_ids)
    if target_error is not None:
        return target_error

    # CR9: 认领 tenant + vpc + 各 vpc-device
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id)]
    keys += [vpc_device_key(vpc.id, d.id) for d in targets]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        deployments: list[SdnDeployment] = []
        target_ids = {d.id for d in targets}
        bindings_by_device: dict[int, list[SdnPortBinding]] = {}
        if payload.include_port_bindings:
            bindings = (
                db.query(SdnPortBinding)
                .filter(
                    SdnPortBinding.vpc_id == vpc.id,
                    SdnPortBinding.device_id.in_(target_ids),
                    SdnPortBinding.status != "unbound",
                )
                .order_by(SdnPortBinding.id)
                .all()
            )
            for binding in bindings:
                bindings_by_device.setdefault(binding.device_id, []).append(binding)

        for device in targets:
            parent_id = None
            for binding in bindings_by_device.get(device.id, []):
                unbind_units = planner.plan_port_unbind(binding, vpc, dry_run=True)
                unbind_deployment = _create_sdn_deployment(
                    db,
                    vpc_id=vpc.id,
                    device_id=device.id,
                    action="port_unbind",
                    unit="port-unbind",
                    parent_deployment_id=parent_id,
                    port_binding_id=binding.id,
                    planned_config=VPCConfigPlanner.serialize(unbind_units),
                )
                parent_id = unbind_deployment.id
                deployments.append(unbind_deployment)

            delete_units = planner.plan_vpc_delete(vpc, dry_run=True)
            delete_deployment = _create_sdn_deployment(
                db,
                vpc_id=vpc.id,
                device_id=device.id,
                action="delete",
                unit="vpc-create-all",
                parent_deployment_id=parent_id,
                planned_config=VPCConfigPlanner.serialize(delete_units),
            )
            deployments.append(delete_deployment)

        vpc.status = "withdrawing" if payload.auto_apply else "withdraw_planned"
        db.commit()

        deployments = _apply_if_requested(db, deployments, payload.auto_apply)
        items = [_deployment_to_response(d).model_dump(mode="json") for d in deployments]
        return APIResponse(
            success=True,
            data={
                "vpc_id": vpc.id,
                "operation": "withdraw",
                "auto_apply": payload.auto_apply,
                "target_device_ids": [d.id for d in targets],
                "total": len(items),
                "deployments": items,
            },
        )
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/vpcs/{vpc_id}/devices/{device_id}/redeploy", response_model=APIResponse)
def redeploy_vpc_on_device(
    vpc_id: int,
    device_id: int,
    auto_apply: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """补回某台 EVPN 节点上的完整 VPC 配置。

    对应单节点 VPC 撤回的反向动作。所有参数来自 VPC 定义，不允许调用方
    重新填写 RD/VNI/网关，避免同一个 VPC 在不同设备上的标准配置漂移。
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    if not tenant:
        return error_response(err.SDN_VPC_TENANT_NOT_FOUND, params={"tenant_id": vpc.tenant_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, device_id)
    if device_error is not None:
        return device_error

    # CR9: 认领 tenant + vpc + vpc-device
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, device_id)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
        deployment = _create_sdn_deployment(
            db,
            vpc_id=vpc.id,
            device_id=device_id,
            action="create",
            unit="vpc-create-all",
            planned_config=VPCConfigPlanner.serialize(units),
        )
        applied = _apply_if_requested(db, [deployment], auto_apply)[0]
        if auto_apply:
            vpc.status = "active" if applied.status == "success" else "degraded"
        else:
            vpc.status = "planned"
        db.commit()
        db.refresh(vpc)
        db.refresh(applied)
        return APIResponse(
            success=True,
            data={
                "vpc": _vpc_to_response(vpc, tenant, binding_count=len(vpc.port_bindings)).model_dump(mode="json"),
                "deployment": _deployment_to_response(applied).model_dump(mode="json"),
            },
        )
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


# ── v3.0 SDN/VPC Deployment 端点（sdn-vpc-deployment-api）──

def _deployment_to_response(d: SdnDeployment) -> SdnDeploymentResponse:
    """SdnDeployment ORM → SdnDeploymentResponse。"""
    return SdnDeploymentResponse(
        id=d.id,
        vpc_id=d.vpc_id,
        device_id=d.device_id,
        action=d.action,
        unit=d.unit,
        parent_deployment_id=d.parent_deployment_id,
        port_binding_id=d.port_binding_id,
        planned_config=d.planned_config,
        status=d.status,
        error=d.error,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _check_device_exists(device_id: int) -> Optional[APIResponse]:
    """校验设备是否存在。

    优先本地查（monolith 模式 / 单测）；split 模式下本地无 devices 表，走 internal API 调 ctrl。
    返回: None = 存在；APIResponse(success=False) = 不存在
    """
    # 1. 尝试本地查（monolith 模式）
    try:
        from app.database import SessionLocal
        with SessionLocal() as db:
            exists = db.query(Device).filter(Device.id == device_id).first()
        if exists is not None:
            return None
    except Exception as e:
        logger.warning(f"本地 Device 表不可用，走内部 API: {e}")

    # 2. split 模式：走 internal API 调 ctrl 容器
    try:
        from app.internal_api import get_device
        resp = get_device(device_id)
        if resp.get("success"):
            return None
    except Exception as e:
        logger.error(f"内部 API 查设备失败: {e}")

    return error_response(err.SDN_DEVICE_NOT_FOUND, params={"id": device_id})


@router.post("/deployments", response_model=APIResponse)
def create_deployment(body: SdnDeploymentCreate, db: Session = Depends(get_db)):
    """创建 deployment，调 VPCConfigPlanner 自动生成 planned_config。

    流程：
    1. 校验 vpc 存在
    2. 校验 device 存在
    3. 调 planner.plan_vpc_create(vpc, tenant) 或 plan_vpc_delete(vpc) 生成命令列表
    4. 序列化为 JSON 字符串存入 planned_config
    5. 创建 SdnDeployment 记录（status=pending）
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == body.vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": body.vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    if not tenant:
        return error_response(err.SDN_VPC_TENANT_NOT_FOUND, params={"tenant_id": vpc.tenant_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, body.device_id)
    if device_error is not None:
        return device_error

    # 调 planner 生成命令
    planner = VPCConfigPlanner(H3cV7Adapter())
    if body.action == "create":
        commands = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    else:  # delete
        commands = planner.plan_vpc_delete(vpc, dry_run=True)

    # 序列化为 JSON 字符串
    planned_json = VPCConfigPlanner.serialize(commands)

    deployment = _create_sdn_deployment(
        db,
        vpc_id=body.vpc_id,
        device_id=body.device_id,
        action=body.action,
        planned_config=planned_json,
        unit=body.unit or "vpc-create-all",
        parent_deployment_id=body.parent_deployment_id,
        port_binding_id=body.port_binding_id,
    )
    return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))


@router.get("/deployments", response_model=APIResponse)
def list_deployments(
    vpc_id: Optional[int] = Query(default=None, ge=1),
    device_id: Optional[int] = Query(default=None, ge=1),
    action: Optional[str] = Query(default=None, pattern="^(create|delete|port_bind|port_unbind|gateway_delete)$"),
    db: Session = Depends(get_db),
):
    """Deployment 列表，支持按 vpc_id / device_id / action 过滤。"""
    q = db.query(SdnDeployment)
    if vpc_id is not None:
        q = q.filter(SdnDeployment.vpc_id == vpc_id)
    if device_id is not None:
        q = q.filter(SdnDeployment.device_id == device_id)
    if action is not None:
        q = q.filter(SdnDeployment.action == action)

    items = [_deployment_to_response(d).model_dump(mode="json") for d in q.order_by(SdnDeployment.id.desc()).all()]
    return APIResponse(success=True, data={"total": len(items), "deployments": items})


@router.get("/deployments/{deployment_id}", response_model=APIResponse)
def get_deployment(deployment_id: int, db: Session = Depends(get_db)):
    """Deployment 详情（vpc-apply 用此端点读 planned_config）。"""
    d = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
    if not d:
        return error_response(err.SDN_DEPLOYMENT_NOT_FOUND, params={"id": deployment_id})
    return APIResponse(success=True, data=_deployment_to_response(d).model_dump(mode="json"))


# ── v3.3 SDN/VPC Port Binding 与细粒度撤回端点 ──

@router.post("/port-bindings", response_model=APIResponse)
def create_port_binding(payload: SdnPortBindingCreate, db: Session = Depends(get_db)):
    """创建端口绑定关系（仅入库，不立即下发）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == payload.vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": payload.vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    device, device_error = _get_sdn_fabric_device_or_error(db, payload.device_id)
    if device_error is not None:
        return device_error
    if payload.if_index in _parse_protected_interfaces(device):
        return error_response(err.INTERFACE_PROTECTED_BLOCKED)

    # S1: 层级 claim（tenant < vpc < vpc-device < device-port），串行化同 VPC/端口 mutation
    # 旧入口无 operation，用稳定合成 owner 令牌（attempt_id=-1），释放时只释放该令牌
    try:
        acquired = acquire_claims(
            db,
            [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, payload.device_id), device_port_key(payload.device_id, payload.if_index)],
            attempt_id=-1,
        )
        db.commit()
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    conflict = (
        db.query(SdnPortBinding)
        .filter(
            SdnPortBinding.device_id == payload.device_id,
            SdnPortBinding.if_index == payload.if_index,
            SdnPortBinding.status != "unbound",
        )
        .first()
    )
    if conflict:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()
        return error_response(
            err.SDN_PORT_BINDING_CONFLICT,
            params={"device_id": payload.device_id, "interface_name": payload.interface_name},
        )

    access_vlan = payload.access_vlan
    service_instance = payload.service_instance
    if access_vlan is None and service_instance is None:
        access_vlan = vpc.vlan_id

    binding = SdnPortBinding(
        device_id=payload.device_id,
        tenant_id=vpc.tenant_id,
        vpc_id=vpc.id,
        if_index=payload.if_index,
        interface_name=payload.interface_name,
        access_vlan=access_vlan,
        service_instance=service_instance,
        status="planned",
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    release_claims(db, acquired, owner_attempt_id=-1)
    db.commit()
    return APIResponse(success=True, data=_binding_to_response(binding, vpc, tenant).model_dump(mode="json"))


@router.get("/port-bindings", response_model=APIResponse)
def list_port_bindings(
    vpc_id: Optional[int] = Query(default=None, ge=1),
    device_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    """端口绑定列表，支持按 VPC / 设备过滤。"""
    q = db.query(SdnPortBinding)
    if vpc_id is not None:
        q = q.filter(SdnPortBinding.vpc_id == vpc_id)
    if device_id is not None:
        q = q.filter(SdnPortBinding.device_id == device_id)
    bindings = q.order_by(SdnPortBinding.id.desc()).all()
    items = [_binding_to_response(b).model_dump(mode="json") for b in bindings]
    return APIResponse(success=True, data={"total": len(items), "port_bindings": items})


@router.get("/port-bindings/{binding_id}", response_model=APIResponse)
def get_port_binding(binding_id: int, db: Session = Depends(get_db)):
    """端口绑定详情。"""
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.id == binding_id).first()
    if not binding:
        return error_response(err.SDN_PORT_BINDING_NOT_FOUND, params={"id": binding_id})
    return APIResponse(success=True, data=_binding_to_response(binding).model_dump(mode="json"))


@router.delete("/port-bindings/{binding_id}", response_model=APIResponse)
def delete_port_binding(binding_id: int, db: Session = Depends(get_db)):
    """删除未激活或已解绑的端口绑定；active 绑定需先生成解绑 deployment。"""
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.id == binding_id).first()
    if not binding:
        return error_response(err.SDN_PORT_BINDING_NOT_FOUND, params={"id": binding_id})
    if binding.status == "active":
        return error_response(err.OPERATION_FAILED, params={"error": "active binding must be undeployed first"})

    # S1: 父删除前写身份快照
    snapshot_identity(db, entity_kind="binding", entity_id=binding.id, identity={
        "device_id": binding.device_id, "vpc_id": binding.vpc_id,
        "if_index": binding.if_index, "interface_name": binding.interface_name,
    }, deleted=True)
    db.flush()

    try:
        acquired = acquire_claims(
            db,
            [tenant_key(binding.tenant_id), vpc_key(binding.vpc_id), vpc_device_key(binding.vpc_id, binding.device_id), device_port_key(binding.device_id, binding.if_index)],
            attempt_id=-1,
        )
        db.commit()
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    db.delete(binding)
    db.commit()
    release_claims(db, acquired, owner_attempt_id=-1)
    db.commit()
    return APIResponse(success=True, data={"deleted": binding_id})


@router.post("/port-bindings/{binding_id}/deploy", response_model=APIResponse)
def deploy_port_binding(
    binding_id: int,
    payload: SdnPortBindingDeployRequest = SdnPortBindingDeployRequest(),
    db: Session = Depends(get_db),
):
    """为端口绑定生成下发 deployment。"""
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.id == binding_id).first()
    if not binding:
        return error_response(err.SDN_PORT_BINDING_NOT_FOUND, params={"id": binding_id})
    vpc = db.query(SdnVpc).filter(SdnVpc.id == binding.vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": binding.vpc_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, binding.device_id)
    if device_error is not None:
        return device_error

    # CR9: 认领 tenant + vpc + vpc-device + device-port
    keys = [tenant_key(binding.tenant_id), vpc_key(binding.vpc_id),
            vpc_device_key(binding.vpc_id, binding.device_id),
            device_port_key(binding.device_id, binding.if_index)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        units = planner.plan_port_bind(binding, vpc, mode=payload.mode, dry_run=True)
        deployment = _create_sdn_deployment(
            db,
            vpc_id=binding.vpc_id,
            device_id=binding.device_id,
            action="port_bind",
            unit="port-bind",
            port_binding_id=binding.id,
            planned_config=VPCConfigPlanner.serialize(units),
        )
        binding.status = "pending"
        db.commit()
        db.refresh(deployment)
        return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/port-bindings/{binding_id}/undeploy", response_model=APIResponse)
def undeploy_port_binding(binding_id: int, db: Session = Depends(get_db)):
    """为端口绑定生成解绑 deployment。"""
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.id == binding_id).first()
    if not binding:
        return error_response(err.SDN_PORT_BINDING_NOT_FOUND, params={"id": binding_id})
    vpc = db.query(SdnVpc).filter(SdnVpc.id == binding.vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": binding.vpc_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, binding.device_id)
    if device_error is not None:
        return device_error

    # CR9: 认领 tenant + vpc + vpc-device + device-port
    keys = [tenant_key(binding.tenant_id), vpc_key(binding.vpc_id),
            vpc_device_key(binding.vpc_id, binding.device_id),
            device_port_key(binding.device_id, binding.if_index)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        units = planner.plan_port_unbind(binding, vpc, dry_run=True)
        deployment = _create_sdn_deployment(
            db,
            vpc_id=binding.vpc_id,
            device_id=binding.device_id,
            action="port_unbind",
            unit="port-unbind",
            port_binding_id=binding.id,
            planned_config=VPCConfigPlanner.serialize(units),
        )
        return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/vpcs/{vpc_id}/expansions", response_model=APIResponse)
def start_vpc_expansion(vpc_id: int, payload: SdnVpcExpansionRequest, db: Session = Depends(get_db)):
    """已有 VPC 扩容接入口。

    用户选择 EVPN 节点 + 接口后，平台创建端口绑定并生成 port_bind deployment。
    auto_apply=true 时立即下发，成功后进入 expanding，等待用户接线和配置主机 IP。
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    device, device_error = _get_sdn_fabric_device_or_error(db, payload.device_id)
    if device_error is not None:
        return device_error
    if payload.if_index in _parse_protected_interfaces(device):
        return error_response(err.INTERFACE_PROTECTED_BLOCKED)

    # CR9: 先认领再冲突检查+插入，避免 check-then-insert 竞态
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id),
            vpc_device_key(vpc.id, payload.device_id),
            device_port_key(payload.device_id, payload.if_index)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        conflict = (
            db.query(SdnPortBinding)
            .filter(
                SdnPortBinding.device_id == payload.device_id,
                SdnPortBinding.if_index == payload.if_index,
                SdnPortBinding.status != "unbound",
            )
            .first()
        )
        if conflict:
            return error_response(
                err.SDN_PORT_BINDING_CONFLICT,
                params={"device_id": payload.device_id, "interface_name": payload.interface_name},
            )

        access_vlan = payload.access_vlan
        service_instance = payload.service_instance
        if access_vlan is None and service_instance is None:
            service_instance = vpc.vlan_id

        binding = SdnPortBinding(
            device_id=payload.device_id,
            tenant_id=vpc.tenant_id,
            vpc_id=vpc.id,
            if_index=payload.if_index,
            interface_name=payload.interface_name,
            access_vlan=access_vlan,
            service_instance=service_instance,
            status="pending",
        )
        db.add(binding)
        db.commit()
        db.refresh(binding)

        planner = VPCConfigPlanner(H3cV7Adapter())
        units = planner.plan_port_bind(binding, vpc, mode="auto", dry_run=True)
        deployment = _create_sdn_deployment(
            db,
            vpc_id=vpc.id,
            device_id=payload.device_id,
            action="port_bind",
            unit="port-bind",
            port_binding_id=binding.id,
            planned_config=VPCConfigPlanner.serialize(units),
        )
        applied = _apply_if_requested(db, [deployment], payload.auto_apply)[0]
        if applied.status == "success":
            binding.status = "expanding"
            vpc.status = "expanding"
        else:
            binding.status = "failed"
            vpc.status = "degraded"
        db.commit()
        db.refresh(binding)
        db.refresh(vpc)
        db.refresh(applied)

        return APIResponse(
            success=True,
            data={
                "vpc": _vpc_to_response(vpc, tenant, binding_count=len(vpc.port_bindings)).model_dump(mode="json"),
                "binding": _binding_to_response(binding, vpc, tenant).model_dump(mode="json"),
                "deployment": _deployment_to_response(applied).model_dump(mode="json"),
                "expected_host_ip": payload.expected_host_ip,
                "next_status": binding.status,
            },
        )
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/vpcs/{vpc_id}/expansions/{binding_id}/complete", response_model=APIResponse)
def complete_vpc_expansion(
    vpc_id: int,
    binding_id: int,
    payload: SdnVpcExpansionCompleteRequest,
    db: Session = Depends(get_db),
):
    """扩容完成校验。

    expected_host_ip 为空时只同步 display 状态；提供 IP 时从 VPC 网关发起 ping。
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    binding = (
        db.query(SdnPortBinding)
        .filter(SdnPortBinding.id == binding_id, SdnPortBinding.vpc_id == vpc_id)
        .first()
    )
    if not binding:
        return error_response(err.SDN_PORT_BINDING_NOT_FOUND, params={"id": binding_id})

    ping_result = None
    if payload.expected_host_ip:
        ping_result, ping_error = _ping_from_vpc_gateway(db, vpc, binding.device_id, payload.expected_host_ip)
        if ping_error is not None:
            return ping_error

    collector = SdnValidationCollector()
    snapshot, validation_error, cached = collector.sync(
        db,
        vpc_id,
        binding.device_id,
        force=payload.force_validation,
        min_interval_seconds=0 if payload.force_validation else collector.DEFAULT_MIN_INTERVAL_SECONDS,
    )
    if validation_error is not None:
        return error_response(err.OPERATION_FAILED, params=validation_error.get("params"))

    validation = collector.to_response(snapshot, cached=cached)
    expansion_success = validation["validation_result"] == "active"
    if ping_result is not None:
        expansion_success = expansion_success and bool(ping_result["success"])

    binding.status = "active" if expansion_success else "failed"
    vpc.status = "active" if expansion_success else "degraded"
    db.commit()
    db.refresh(binding)
    db.refresh(vpc)

    return APIResponse(
        success=True,
        data={
            "success": expansion_success,
            "vpc": _vpc_to_response(vpc, tenant, binding_count=len(vpc.port_bindings)).model_dump(mode="json"),
            "binding": _binding_to_response(binding, vpc, tenant).model_dump(mode="json"),
            "ping": ping_result,
            "validation": validation,
        },
    )


@router.post("/vpcs/{vpc_id}/devices/{device_id}/gateway/deploy", response_model=APIResponse)
def deploy_vpc_gateway(
    vpc_id: int,
    device_id: int,
    auto_apply: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """加回某台 EVPN 节点上某个 VPC 的三层网关。

    对应 gateway undeploy 的反向动作。只下发 Vsi-interface/L3VNI/VPN binding
    与 `gateway vsi-interface` 绑定，不重新创建 L2 VSI/EVPN。
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    if not tenant:
        return error_response(err.SDN_VPC_TENANT_NOT_FOUND, params={"tenant_id": vpc.tenant_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, device_id)
    if device_error is not None:
        return device_error

    # CR9: 认领 tenant + vpc + vpc-device
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, device_id)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        units = [u for u in planner.plan_vpc_create(vpc, tenant, dry_run=True) if u.name == UNIT_VSI_L3]
        deployment = _create_sdn_deployment(
            db,
            vpc_id=vpc_id,
            device_id=device_id,
            action="create",
            unit=UNIT_VSI_L3,
            planned_config=VPCConfigPlanner.serialize(units),
        )
        applied = _apply_if_requested(db, [deployment], auto_apply)[0]
        if auto_apply:
            vpc.status = "active" if applied.status == "success" else "degraded"
        else:
            vpc.status = "planned"
        db.commit()
        db.refresh(vpc)
        db.refresh(applied)
        return APIResponse(
            success=True,
            data={
                "vpc": _vpc_to_response(vpc, tenant, binding_count=len(vpc.port_bindings)).model_dump(mode="json"),
                "deployment": _deployment_to_response(applied).model_dump(mode="json"),
            },
        )
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.post("/vpcs/{vpc_id}/devices/{device_id}/gateway/undeploy", response_model=APIResponse)
def undeploy_vpc_gateway(vpc_id: int, device_id: int, db: Session = Depends(get_db)):
    """生成 VPC 三层网关撤回 deployment，仅删除 Vsi-interface，不删除 L2 VSI/EVPN。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    _, device_error = _get_sdn_fabric_device_or_error(db, device_id)
    if device_error is not None:
        return device_error

    # CR9: 认领 tenant + vpc + vpc-device
    keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, device_id)]
    try:
        acquired = _acquire_resource_claims(db, keys)
    except SdnOperationError as e:
        return error_response(err.SDN_RESOURCE_BUSY, params=e.params)

    try:
        planner = VPCConfigPlanner(H3cV7Adapter())
        units = [u for u in planner.plan_vpc_delete(vpc, dry_run=True) if u.name == UNIT_VSI_L3]
        deployment = _create_sdn_deployment(
            db,
            vpc_id=vpc_id,
            device_id=device_id,
            action="gateway_delete",
            unit=UNIT_VSI_L3,
            planned_config=VPCConfigPlanner.serialize(units),
        )
        db.commit()
        return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))
    finally:
        release_claims(db, acquired, owner_attempt_id=-1)
        db.commit()


@router.patch("/deployments/{deployment_id}", response_model=APIResponse)
def update_deployment(
    deployment_id: int,
    body: SdnDeploymentUpdate,
    db: Session = Depends(get_db),
):
    """更新 deployment 状态（vpc-apply 下发后回写 status / error）。

    v3.0 sdn-vpc-deployment-executor 起,业务下发走 POST .../apply 端点,
    此 PATCH 端点保留供外部系统直接改状态 (如排错 / 补偿)。
    """
    d = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
    if not d:
        return error_response(err.SDN_DEPLOYMENT_NOT_FOUND, params={"id": deployment_id})

    # CR9: 限制 PATCH —— 终态历史不可改写；running 不可退回 pending（不可反认领）
    if body.status is not None:
        terminal = {"success", "failed", "unknown"}
        if d.status in terminal and body.status != d.status:
            return error_response(
                err.SDN_DEPLOYMENT_NOT_PENDING,
                params={"id": deployment_id, "status": d.status},
            )
        if d.status == "running" and body.status == "pending":
            return error_response(
                err.SDN_DEPLOYMENT_NOT_PENDING,
                params={"id": deployment_id, "status": d.status},
            )
        d.status = body.status
    if body.error is not None:
        d.error = body.error
    db.commit()
    db.refresh(d)
    return APIResponse(success=True, data=_deployment_to_response(d).model_dump(mode="json"))


# ── v3.0 sdn-vpc-deployment-executor: 业务配置下发端点 ──

@router.post("/deployments/{deployment_id}/apply", response_model=APIResponse)
def apply_deployment(deployment_id: int, db: Session = Depends(get_db)):
    """业务配置下发端点（替代 ops-toolkit vpc-apply.sh）

    链路: frontend → config 容器 → SdnDeploymentExecutor → NetconfClient → 设备

    行为:
    1. 调 SdnDeploymentExecutor.execute()
    2. 校验错 → 返回对应 HTTP 状态码 + error_key
    3. NETCONF 失败 → 200 + status=failed (业务视为已尝试下发)
    4. 成功 → 200 + status=success
    """
    executor = SdnDeploymentExecutor()
    # CR2: legacy apply 复用同一 attempt/unit 追踪（无 operation 则建系统 operation）
    d = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
    if d is None:
        return error_response(err.SDN_DEPLOYMENT_NOT_FOUND, params={"id": deployment_id})
    attempt_id = ensure_legacy_apply_operation(db, d)
    hooks = AttemptUnitHooks(db, attempt_id, operation_id=d.operation_id)
    try:
        deployment = executor.execute(db, deployment_id, unit_hooks=hooks)
    except SdnDeploymentError as e:
        # 校验类错误（status_code 由 error 决定）
        logger.warning(
            f"sdn apply: deployment {deployment_id} 校验失败: {e.error_key} {e.params}"
        )
        # err_key 既可能是 Python 名 (SDN_DEVICE_NOT_WRITABLE) 也可能是 i18n key (device.not_found)
        # SDN_ 前缀的用 getattr 查 err, 其他前缀 (device./vlan./common.) 直接当 i18n key 透传
        if e.error_key.startswith("SDN_"):
            err_attr = getattr(err, e.error_key, err.OPERATION_FAILED)
        else:
            # 透传 i18n key（构造一个伪 I18nKey-like 对象，error_response 会接受字符串）
            err_attr = e.error_key
        return error_response(err_attr, params=e.params)

    return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))


# ── v3.3 display 状态采集与二次校验 ──

@router.post("/vpcs/{vpc_id}/devices/{device_id}/validation/sync", response_model=APIResponse)
def sync_vpc_validation(
    vpc_id: int,
    device_id: int,
    force: bool = Query(default=False),
    min_interval_seconds: int = Query(default=600, ge=0, le=86400),
    db: Session = Depends(get_db),
):
    """同步一个 VPC 在一台设备上的 display 状态。

    默认 600 秒内复用最近快照，避免页面刷新造成设备 SSH 高频访问。
    人工排障需要实时刷新时传 force=true。
    """
    collector = SdnValidationCollector()
    snapshot, error, cached = collector.sync(
        db,
        vpc_id,
        device_id,
        force=force,
        min_interval_seconds=min_interval_seconds,
    )
    if error is not None:
        if error["key"] == "sdn.vpc_not_found":
            return error_response(err.SDN_VPC_NOT_FOUND, params=error.get("params"))
        if error["key"] == "device.not_found":
            return error_response(err.DEVICE_NOT_FOUND, params=error.get("params"))
        return error_response(err.OPERATION_FAILED, params=error.get("params"))
    return APIResponse(success=True, data=collector.to_response(snapshot, cached=cached))


@router.get("/vpcs/{vpc_id}/devices/{device_id}/validation/latest", response_model=APIResponse)
def get_latest_vpc_validation(vpc_id: int, device_id: int, db: Session = Depends(get_db)):
    """读取最近一次 display 状态快照，不触发设备访问。"""
    snapshot = (
        db.query(SdnValidationSnapshot)
        .filter(
            SdnValidationSnapshot.vpc_id == vpc_id,
            SdnValidationSnapshot.device_id == device_id,
        )
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )
    if not snapshot:
        return APIResponse(success=True, data=None)
    return APIResponse(success=True, data=SdnValidationCollector.to_response(snapshot))


# ── S2-001/S2-004 VPC 目标态 / 观测态 / 差异投影（只读，不触发设备 I/O、不写库）──

# 共享查询/序列化助手（S2-004 抽取；不改变既有 endpoint 行为）。

def _load_projection_context(db: Session, vpc_id: int):
    """载入 VPC 投影上下文（vpc/tenant/vpc_dict/tenant_dict）；VPC 不存在 → None。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return None
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    vpc_dict = {
        "id": vpc.id,
        "name": vpc.name,
        "version": vpc.version,
        "vni": vpc.vni,
        "vsi_name": vpc.vsi_name,
        "vsi_interface": vpc.vsi_interface,
    }
    tenant_dict = {"id": tenant.id, "l3_vni": tenant.l3_vni} if tenant else {"id": None, "l3_vni": None}
    return vpc, tenant, vpc_dict, tenant_dict


def _projection_target_devices(db: Session, vpc_id: int) -> list:
    """该 VPC 的部署/绑定/快照所覆盖的设备 = 可操作目标集合的候选。"""
    target_ids: set[int] = set()
    for model in (SdnDeployment, SdnPortBinding, SdnValidationSnapshot):
        rows = db.query(model.device_id).filter(model.vpc_id == vpc_id).distinct().all()
        target_ids.update(int(r[0]) for r in rows if r[0] is not None)
    return db.query(Device).filter(Device.id.in_(target_ids)).all() if target_ids else []


def _serialize_binding_row(b) -> dict:
    return {
        "id": b.id,
        "if_index": b.if_index,
        "interface_name": b.interface_name,
        "access_vlan": b.access_vlan,
        "service_instance": b.service_instance,
        "status": b.status,
        "version": b.version,
    }


def _serialize_bindings(db: Session, vpc_id: int, device_id: int) -> list:
    binding_rows = (
        db.query(SdnPortBinding)
        .filter(SdnPortBinding.vpc_id == vpc_id, SdnPortBinding.device_id == device_id)
        .order_by(SdnPortBinding.id.asc())
        .all()
    )
    return [_serialize_binding_row(b) for b in binding_rows]


def _serialize_deployment_row(d) -> dict:
    return {
        "id": d.id,
        "action": d.action,
        "unit": d.unit,
        "status": d.status,
        "version": d.version,
        "config_completed_at": d.config_completed_at,
    }


def _serialize_deployments(db: Session, vpc_id: int, device_id: int) -> list:
    deployment_rows = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.vpc_id == vpc_id, SdnDeployment.device_id == device_id)
        .order_by(SdnDeployment.id.asc())
        .all()
    )
    return [_serialize_deployment_row(d) for d in deployment_rows]


def _decode_snapshot(snap):
    """解码快照载荷与元数据；畸形 JSON 稳定降级为 None（不抛异常、不改写快照）。"""
    snapshot_payload = None
    snapshot_meta: dict = {}
    if snap is not None:
        collected_at = snap.collection_completed_at or snap.created_at
        snapshot_meta = {"snapshot_id": snap.id, "collected_at": collected_at}
        try:
            snapshot_payload = json.loads(snap.snapshot_data) if snap.snapshot_data else None
        except (TypeError, json.JSONDecodeError):
            snapshot_payload = None
    return snapshot_payload, snapshot_meta


def _projection_excluded_entry(device) -> dict:
    return {
        "device_id": device.id,
        "device_name": device.name,
        "device_host": device.host,
        "sdn_role": device.sdn_role,
        "reason": "not_evpn_leaf",
    }


def _projection_device_dict(device) -> dict:
    return {"id": device.id, "name": device.name, "host": device.host, "sdn_role": device.sdn_role}


def _snapshot_correlation(snap, operation, attempt, vpc_id: int, device_id: int) -> dict:
    """历史快照 → 脱敏操作关联（S2-006）。

    只表达「证据归属/时间相关」：operation/attempt 与快照引用、与当前时间线
    （vpc_id/device_id）一致才 linked；零引用 unlinked；dangling 引用 missing；
    operation 属于另一 VPC/设备或 attempt 属于另一 operation → mismatch。
    绝不宣称操作导致状态变化。linked 时只返回白名单摘要，不携带
    request_payload_json/scope_json/idempotency_key/fingerprint/owner/凭据。
    """
    op_id = snap.operation_id
    at_id = snap.attempt_id
    if op_id is None and at_id is None:
        return {"operation_id": None, "attempt_id": None, "status": "unlinked", "operation": None, "attempt": None}

    # 稳定优先级（dangling 优先，不被后续归属判定覆盖）：
    # 1) 任何被引用实体不存在 → missing；
    # 2) 引用实体都存在但归属/作用域不一致（operation 跨 VPC/设备、attempt 属于另一
    #    operation、或有 attempt 引用而无对应的 operation 引用可核对）→ mismatch；
    # 3) 全部一致 → linked。
    if op_id is not None and operation is None:
        status = "missing"  # dangling operation 引用
    elif at_id is not None and attempt is None:
        status = "missing"  # dangling attempt 引用
    elif op_id is not None and (operation.vpc_id != vpc_id or operation.device_id != device_id):
        status = "mismatch"  # operation 属于另一 VPC/设备
    elif at_id is not None and (op_id is None or attempt.operation_id != op_id):
        status = "mismatch"  # attempt 属于另一 operation 或无对应的 operation 引用可核对
    else:
        status = "linked"

    operation_summary = None
    attempt_summary = None
    if status == "linked":
        if operation is not None:
            operation_summary = {
                "id": operation.id,
                "operation_type": operation.operation_type,
                "status": operation.status,
                "expected_host_ip": operation.expected_host_ip,
                "created_at": operation.created_at,
                "updated_at": operation.updated_at,
            }
        if attempt is not None:
            attempt_summary = {
                "id": attempt.id,
                "kind": attempt.kind,
                "status": attempt.status,
                "started_at": attempt.started_at,
                "completed_at": attempt.completed_at,
            }
    return {
        "operation_id": op_id,
        "attempt_id": at_id,
        "status": status,
        "operation": operation_summary,
        "attempt": attempt_summary,
    }


def _latest_snapshot(db: Session, vpc_id: int, device_id: int):
    return (
        db.query(SdnValidationSnapshot)
        .filter(
            SdnValidationSnapshot.vpc_id == vpc_id,
            SdnValidationSnapshot.device_id == device_id,
        )
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )


def build_projection_payload(db: Session, vpc_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """S2 状态投影载荷（只读、零设备 I/O、零 DB 写）。

    state-projection 端点与 S3 assurance 手动评估共用同一份事实（同一次
    projection/attention）。VPC 不存在 → None。本函数不触发 SSH/NETCONF、不写库、
    不刷新时间戳；仅投影已持久化的期望记录（VPC/binding/deployment）与最近验证快照。
    非 evpn_leaf 设备不进健康分母，仅作 excluded 呈现。
    """
    ctx = _load_projection_context(db, vpc_id)
    if ctx is None:
        return None
    vpc, tenant, vpc_dict, tenant_dict = ctx
    now = now or datetime.utcnow()

    devices = _projection_target_devices(db, vpc_id)
    leaves: list[dict] = []
    excluded: list[dict] = []
    for device in devices:
        if not _is_sdn_fabric_member(device):
            excluded.append(_projection_excluded_entry(device))
            continue

        bindings = _serialize_bindings(db, vpc_id, device.id)
        snap = _latest_snapshot(db, vpc_id, device.id)
        snapshot_payload, snapshot_meta = _decode_snapshot(snap)
        deployments = _serialize_deployments(db, vpc_id, device.id)

        leaves.append(
            build_leaf_projection(
                device=_projection_device_dict(device),
                vpc=vpc_dict,
                tenant=tenant_dict,
                bindings=bindings,
                deployments=deployments,
                snapshot=snapshot_payload,
                snapshot_meta=snapshot_meta,
                now=now,
            )
        )

    leaf_aggregates = [leaf["aggregate"] for leaf in leaves]

    # S2-012: VPC EVPN Leaf 范围覆盖投影（只读、additive；顶层 scope，既有
    # leaves/excluded/aggregate 不变）。枚举当前数据库全部 sdn_role=evpn_leaf 设备；
    # deployment/binding/snapshot 各一次批量查询按 device_id 分组，避免逐 Leaf N+1；
    # 分类复用 resolve_base_lifecycle（build_scope_member），snapshot 单独不能证明
    # targeted；零 DB 写、零 SSH/NETCONF、零隐式采集。
    scope_members: list[dict] = []
    scope_summary = {
        "eligible": 0,
        SCOPE_TARGETED: 0,
        SCOPE_WITHDRAWN: 0,
        SCOPE_NOT_TARGETED: 0,
        SCOPE_AMBIGUOUS: 0,
        "active_exception": 0,
    }
    # 与全项目唯一成员准入 `_is_sdn_fabric_member` 保持同一 lower 语义，避免
    # 角色值大小写不同时 scope 与实际准入分裂。
    scope_devices = [
        device for device in db.query(Device).order_by(Device.id.asc()).all()
        if _is_sdn_fabric_member(device)
    ]
    if scope_devices:
        vpc_version = vpc_dict.get("version")
        deployments_by_device: dict[int, list] = {}
        for row in db.query(SdnDeployment).filter(SdnDeployment.vpc_id == vpc_id).all():
            deployments_by_device.setdefault(row.device_id, []).append(_serialize_deployment_row(row))
        bindings_by_device: dict[int, list] = {}
        for row in db.query(SdnPortBinding).filter(SdnPortBinding.vpc_id == vpc_id).all():
            bindings_by_device.setdefault(row.device_id, []).append(_serialize_binding_row(row))
        snapshot_counts = dict(
            db.query(SdnValidationSnapshot.device_id, func.count(SdnValidationSnapshot.id))
            .filter(SdnValidationSnapshot.vpc_id == vpc_id)
            .group_by(SdnValidationSnapshot.device_id)
            .all()
        )
        scope_summary["eligible"] = len(scope_devices)
        for device in scope_devices:
            member = build_scope_member(
                {"id": device.id, "name": device.name, "host": device.host},
                deployments=deployments_by_device.get(device.id, []),
                bindings=bindings_by_device.get(device.id, []),
                snapshot_count=snapshot_counts.get(device.id, 0),
                vpc_version=vpc_version,
            )
            scope_summary[member["classification"]] = scope_summary.get(member["classification"], 0) + 1
            scope_members.append(member)
        # S2-014: additive 附加范围例外白名单（无例外为 null；过期例外 state=expired）。
        # 例外是业务上下文，绝不改变 classification/reason_code/desired_base_state 的
        # 事实语义，也不从 scope 分母移除设备；active_exception 只统计有效例外。
        exceptions_by_device = {
            r.device_id: _serialize_scope_exception(r)
            for r in db.query(SdnScopeException).filter(SdnScopeException.vpc_id == vpc_id).all()
        }
        for member in scope_members:
            exc = exceptions_by_device.get(member["device_id"])
            member["exception"] = exc
            if exc is not None and exc["state"] == "active":
                scope_summary["active_exception"] += 1

    # S2-016: 可行动关注队列（只读、additive、顶层 attention）。复用本请求已加载的
    # scope members（含 S2-014 exception 白名单）与 leaves（device_id → aggregate/
    # observed 引用）批量组装，零额外查询、零 DB 写、零 SSH/NETCONF、零隐式采集。
    attention = attention_projection(
        vpc_id=vpc_id,
        members=scope_members,
        leaves_by_device={leaf.get("device_id"): leaf for leaf in leaves},
    )

    return {
        "vpc": vpc_dict,
        "snapshot_ttl_seconds": SNAPSHOT_TTL_SECONDS,
        "leaves": leaves,
        "excluded": excluded,
        "aggregate": aggregate_vpc(leaf_aggregates),
        "scope": {"members": scope_members, "summary": scope_summary},
        "attention": attention,
    }


@router.get("/vpcs/{vpc_id}/state-projection", response_model=APIResponse)
def get_vpc_state_projection(vpc_id: int, db: Session = Depends(get_db)):
    """单个 VPC 的目标态/观测态/差异投影（S2-001，只读）。

    只读语义：不触发 SSH/NETCONF、不写库、不刷新时间戳；仅投影已持久化的期望记录
    （VPC/binding/deployment）与最近验证快照。非 evpn_leaf 设备不进健康分母，仅作
    excluded 呈现。载荷由 build_projection_payload 统一构建（S3 手动评估复用同份事实）。
    """
    data = build_projection_payload(db, vpc_id)
    if data is None:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    return APIResponse(success=True, data=data)


@router.get("/vpcs/{vpc_id}/state-projection/history", response_model=APIResponse)
def get_vpc_state_projection_history(
    vpc_id: int,
    device_id: int | None = Query(None, description="可选：只看指定设备"),
    limit: int = Query(10, ge=1, le=50, description="每台设备最多返回的历史快照点数"),
    db: Session = Depends(get_db),
):
    """设备快照时间线（S2-004/S2-006，只读）。

    只读语义：不触发 SSH/NETCONF、不写库、不刷新时间戳；只读取已有 validation snapshots。
    每个历史点都是「历史设备快照与当前目标态的比较」——desired 复用当前 deployment/binding
    生命周期并标记 basis=current_target，绝不冒充历史目标态。坏快照保留为 unknown，不跳过、
    不改写。
    每点 correlation（S2-006）只表达「证据归属/时间相关」：operation/attempt 与快照引用及
    当前时间线一致才 linked（脱敏白名单摘要）；零引用 unlinked；dangling missing；跨
    VPC/设备/operation mismatch。绝不宣称操作导致状态变化。
    """
    ctx = _load_projection_context(db, vpc_id)
    if ctx is None:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    vpc, tenant, vpc_dict, tenant_dict = ctx

    devices = _projection_target_devices(db, vpc_id)
    if device_id is not None:
        devices = [d for d in devices if d.id == device_id]

    now = datetime.utcnow()
    timelines: list[dict] = []
    excluded: list[dict] = []
    window: list[tuple] = []  # (device, snapshots)：当前返回窗口，避免逐点 N+1 关联查询
    for device in devices:
        if not _is_sdn_fabric_member(device):
            excluded.append(_projection_excluded_entry(device))
            continue

        snapshots = (
            db.query(SdnValidationSnapshot)
            .filter(
                SdnValidationSnapshot.vpc_id == vpc_id,
                SdnValidationSnapshot.device_id == device.id,
            )
            .order_by(SdnValidationSnapshot.id.desc())
            .limit(limit)
            .all()
        )
        window.append((device, snapshots))

    # 批量读取窗口涉及的 operation/attempt（一次查询，避免逐点 N+1）。
    op_ids = {s.operation_id for _, snaps in window for s in snaps if s.operation_id is not None}
    at_ids = {s.attempt_id for _, snaps in window for s in snaps if s.attempt_id is not None}
    operations = {o.id: o for o in db.query(SdnOperation).filter(SdnOperation.id.in_(op_ids)).all()} if op_ids else {}
    attempts = {a.id: a for a in db.query(SdnAttempt).filter(SdnAttempt.id.in_(at_ids)).all()} if at_ids else {}

    for device, snapshots in window:
        device_dict = _projection_device_dict(device)
        bindings = _serialize_bindings(db, vpc_id, device.id)
        deployments = _serialize_deployments(db, vpc_id, device.id)

        points: list[dict] = []
        for snap in snapshots:
            snapshot_payload, snapshot_meta = _decode_snapshot(snap)
            leaf = build_leaf_projection(
                device=device_dict,
                vpc=vpc_dict,
                tenant=tenant_dict,
                bindings=bindings,
                deployments=deployments,
                snapshot=snapshot_payload,
                snapshot_meta=snapshot_meta,
                now=now,
            )
            point = dict(leaf)
            point["desired"] = {**leaf["desired"], "basis": "current_target"}
            point["snapshot_id"] = snap.id
            point["collected_at"] = snapshot_meta.get("collected_at")
            point["validation_result"] = snap.validation_result
            point["correlation"] = _snapshot_correlation(
                snap,
                operations.get(snap.operation_id),
                attempts.get(snap.attempt_id),
                vpc_id,
                device.id,
            )
            points.append(point)
        # S2-010: 每个较新的点与紧邻较旧点比较给出 transition_from_prior（同一 current_target
        # 基准）；窗口最旧点明确 baseline_unavailable，不拿窗口外状态或当前实时状态补造基线。
        # 只读纯投影，零 I/O、零写库、零隐式采集。
        for i, point in enumerate(points):
            if i == len(points) - 1:
                point["transition_from_prior"] = baseline_unavailable_transition(point)
            else:
                point["transition_from_prior"] = build_transition(points[i + 1], point)
        timelines.append(
            {
                "device_id": device.id,
                "device_name": device.name,
                "device_host": device.host,
                "sdn_role": device.sdn_role,
                "points": points,
            }
        )

    latest_aggregates = [t["points"][0]["aggregate"] for t in timelines if t["points"]]
    return APIResponse(
        success=True,
        data={
            "vpc": vpc_dict,
            "desired_basis": "current_target",
            "timelines": timelines,
            "excluded": excluded,
            "aggregate": aggregate_vpc(latest_aggregates),
        },
    )


# ─────────── S2-014 VPC 范围例外（业务上下文，零设备 I/O）───────────

SCOPE_EXCEPTION_TYPES = frozenset({"intentional_exclusion", "maintenance_pause"})
SCOPE_EXCEPTION_REASON_MAX = 200


def _parse_expires_at(value) -> Optional[datetime]:
    """把过期时间解析为 UTC naive datetime（与项目既有 DateTime 一致）。

    接受标准 Z、±HH:MM offset 与无时区 ISO：aware 统一换算为 UTC 后去掉 tzinfo 存库；
    无时区输入按 UTC naive。格式非法抛 ValueError（由调用方映射 EXPIRES_INVALID）。
    """
    if value is None or value == "":
        return None
    s = str(value).strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _serialize_scope_exception(row, now: Optional[datetime] = None) -> dict:
    """范围例外白名单序列化（ISO 时间；只返回业务字段，绝不携带凭据/原始配置/快照/owner/fingerprint）。

    合法记录（type 白名单、reason 非空且 ≤200、expires_at 为 None 或 datetime、
    version 为正整数）：未过期 state=active，过期 state=expired（读取时判定，
    不自动删除、不写库）。任何畸形字段（非法 type、空/超长 reason、非 datetime
    expires_at、非法/缺失 version 等）→ 稳定返回脱敏白名单且 state=invalid，
    绝不 active、绝不计入 active_exception、绝不 500；有效/过期旧语义不变。
    """
    now = now or datetime.utcnow()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    vpc_id = getattr(row, "vpc_id", None)
    device_id = getattr(row, "device_id", None)
    exception_type = getattr(row, "exception_type", None)
    reason = getattr(row, "reason", None)
    expires_at = getattr(row, "expires_at", None)
    version = getattr(row, "version", None)
    created_at = getattr(row, "created_at", None)
    updated_at = getattr(row, "updated_at", None)

    if isinstance(expires_at, datetime) and expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)

    valid = (
        exception_type in SCOPE_EXCEPTION_TYPES
        and isinstance(reason, str)
        and 0 < len(reason) <= SCOPE_EXCEPTION_REASON_MAX
        and (expires_at is None or isinstance(expires_at, datetime))
        and isinstance(version, int)
        and not isinstance(version, bool)
        and version >= 1
    )
    if not valid:
        state = "invalid"
    elif expires_at is None:
        state = "active"
    else:
        state = "expired" if expires_at <= now else "active"

    return {
        "vpc_id": vpc_id,
        "device_id": device_id,
        "exception_type": exception_type,
        "reason": reason if isinstance(reason, str) else None,
        "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else None,
        "state": state,
        "version": version,
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
        "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
    }


@router.get("/vpcs/{vpc_id}/scope-exceptions", response_model=APIResponse)
def list_vpc_scope_exceptions(vpc_id: int, db: Session = Depends(get_db)):
    """读取某 VPC 全部范围例外（S2-014，只读；过期项以 state=expired 返回，不删除）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    rows = (
        db.query(SdnScopeException)
        .filter(SdnScopeException.vpc_id == vpc_id)
        .order_by(SdnScopeException.device_id.asc(), SdnScopeException.id.asc())
        .all()
    )
    return APIResponse(
        success=True,
        data={"vpc_id": vpc_id, "exceptions": [_serialize_scope_exception(r) for r in rows]},
    )


@router.put("/vpcs/{vpc_id}/devices/{device_id}/scope-exception", response_model=APIResponse)
def upsert_vpc_scope_exception(vpc_id: int, device_id: int, body: dict, db: Session = Depends(get_db)):
    """新建或替换某 VPC/Leaf 的范围例外（S2-014；唯一约束 + 短事务，写库零设备 I/O）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return error_response(err.SDN_DEVICE_NOT_FOUND, params={"id": device_id})
    if not _is_sdn_fabric_member(device):
        return error_response(err.SDN_DEVICE_NOT_FABRIC_MEMBER, params={"device_id": device_id})

    exception_type = body.get("exception_type")
    if exception_type not in SCOPE_EXCEPTION_TYPES:
        return error_response(err.SDN_SCOPE_EXCEPTION_INVALID_TYPE, params={"exception_type": exception_type})
    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return error_response(err.SDN_SCOPE_EXCEPTION_REASON_REQUIRED)
    reason = reason.strip()
    if len(reason) > SCOPE_EXCEPTION_REASON_MAX:
        return error_response(err.SDN_SCOPE_EXCEPTION_REASON_TOO_LONG, params={"max_length": SCOPE_EXCEPTION_REASON_MAX})

    expires_at = None
    if body.get("expires_at") not in (None, ""):
        try:
            expires_at = _parse_expires_at(body.get("expires_at"))
        except (TypeError, ValueError):
            return error_response(err.SDN_SCOPE_EXCEPTION_EXPIRES_INVALID, params={"expires_at": body.get("expires_at")})
        if expires_at is None:
            return error_response(err.SDN_SCOPE_EXCEPTION_EXPIRES_INVALID, params={"expires_at": body.get("expires_at")})
        if expires_at <= datetime.utcnow():
            return error_response(err.SDN_SCOPE_EXCEPTION_EXPIRES_IN_PAST)

    def _apply(row):
        row.exception_type = exception_type
        row.reason = reason
        row.expires_at = expires_at
        row.version = (row.version or 0) + 1

    existing = (
        db.query(SdnScopeException)
        .filter(SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id)
        .first()
    )
    try:
        if existing is not None:
            _apply(existing)
        else:
            db.add(SdnScopeException(
                vpc_id=vpc_id, device_id=device_id, exception_type=exception_type,
                reason=reason, expires_at=expires_at, version=1,
            ))
        db.commit()
    except IntegrityError:
        # 并发替换：唯一约束拦截后回滚，重新读取既有行并原地更新（短事务，不产生第二条当前记录）。
        db.rollback()
        existing = (
            db.query(SdnScopeException)
            .filter(SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id)
            .first()
        )
        if existing is None:
            raise
        _apply(existing)
        db.commit()

    row = (db.query(SdnScopeException)
           .filter(SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id).first())
    return APIResponse(success=True, data=_serialize_scope_exception(row))


@router.delete("/vpcs/{vpc_id}/devices/{device_id}/scope-exception", response_model=APIResponse)
def clear_vpc_scope_exception(vpc_id: int, device_id: int, db: Session = Depends(get_db)):
    """清除某 VPC/Leaf 的范围例外（直接删除该行；幂等：无当前例外时 deleted=false，不 500）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return error_response(err.SDN_DEVICE_NOT_FOUND, params={"id": device_id})
    row = (
        db.query(SdnScopeException)
        .filter(SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id)
        .first()
    )
    deleted = False
    if row is not None:
        db.delete(row)
        db.commit()
        deleted = True
    return APIResponse(success=True, data={"vpc_id": vpc_id, "device_id": device_id, "deleted": deleted})
