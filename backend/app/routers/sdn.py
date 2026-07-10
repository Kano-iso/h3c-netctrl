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
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, SdnDeployment, SdnTenant, SdnVpc
from app.schemas import (
    APIResponse,
    SdnDeploymentCreate,
    SdnDeploymentResponse,
    SdnDeploymentUpdate,
    SdnTenantCreate,
    SdnTenantResponse,
    SdnTenantUpdate,
    SdnVpcCreate,
    SdnVpcResponse,
)
from app.i18n_keys import err, error_response
from app.services.sdn_deployment_executor import SdnDeploymentError, SdnDeploymentExecutor
from app.services.sdn_device_adapter import H3cV7Adapter
from app.services.vpc_config_planner import VPCConfigPlanner
from app.utils.sdn_allocator import SdnAllocator

logger = logging.getLogger("app")

router = APIRouter(prefix="/api/sdn", tags=["sdn"])


# ─────────── 内部辅助 ───────────

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
    """删除租户（CASCADE 清理其下所有 VPC / binding / deployment / snapshot）。"""
    tenant = db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first()
    if not tenant:
        return error_response(err.SDN_TENANT_NOT_FOUND, params={"id": tenant_id})
    db.delete(tenant)
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
        vsi_name=SdnAllocator.build_vsi_name(tenant.name, payload.name),
        vsi_interface=vsi_interface,
        vlan_id=vlan_id,
        auto_assigned=True,
        status="pending",
        description=payload.description,
    )
    db.add(vpc)
    try:
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

    items = [_vpc_to_response(v, tenants.get(v.tenant_id)).model_dump(mode="json") for v in vpcs]
    return APIResponse(success=True, data={"total": total, "vpcs": items})


@router.get("/vpcs/{vpc_id}", response_model=APIResponse)
def get_vpc(vpc_id: int, db: Session = Depends(get_db)):
    """VPC 详情。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    return APIResponse(success=True, data=_vpc_to_response(vpc, tenant).model_dump(mode="json"))


# ── v3.0 SDN/VPC Deployment 端点（sdn-vpc-deployment-api）──

def _deployment_to_response(d: SdnDeployment) -> SdnDeploymentResponse:
    """SdnDeployment ORM → SdnDeploymentResponse。"""
    return SdnDeploymentResponse(
        id=d.id,
        vpc_id=d.vpc_id,
        device_id=d.device_id,
        action=d.action,
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
    device_err = _check_device_exists(body.device_id)
    if device_err is not None:
        return device_err

    # 调 planner 生成命令
    planner = VPCConfigPlanner(H3cV7Adapter())
    if body.action == "create":
        commands = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    else:  # delete
        commands = planner.plan_vpc_delete(vpc, dry_run=True)

    # 序列化为 JSON 字符串
    planned_json = VPCConfigPlanner.serialize(commands)

    deployment = SdnDeployment(
        vpc_id=body.vpc_id,
        device_id=body.device_id,
        action=body.action,
        planned_config=planned_json,
        status="pending",
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return APIResponse(success=True, data=_deployment_to_response(deployment).model_dump(mode="json"))


@router.get("/deployments", response_model=APIResponse)
def list_deployments(
    vpc_id: Optional[int] = Query(default=None, ge=1),
    device_id: Optional[int] = Query(default=None, ge=1),
    action: Optional[str] = Query(default=None, pattern="^(create|delete)$"),
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
    if body.status is not None:
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
    try:
        deployment = executor.execute(db, deployment_id)
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