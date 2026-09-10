"""S1 终端接入端点（next-s1-backend）

端点：
- POST /api/sdn/vpcs/{vpc_id}/access-preview       服务端预览（持久化一条计划）
- POST /api/sdn/vpcs/{vpc_id}/access               幂等执行（消费 plan，建 operation/binding/deployment）
- POST /api/sdn/operations/{id}/complete           完成/验证（显式，可 force 采集）
- POST /api/sdn/operations/{id}/withdraw           受控撤回
- POST /api/sdn/operations/{id}/reconcile          显式对账（读设备，读不触发）
- GET  /api/sdn/operations/{id}                    操作详情
- GET  /api/sdn/vpcs/{vpc_id}/access-overview      接入概览（只读，不触发设备 I/O）
"""
import json
import logging
import re
import ipaddress
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n_keys import err, error_response
from app.models import (
    Device,
    SdnAttempt,
    SdnAttemptUnit,
    SdnDeployment,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnResourceClaim,
    SdnTenant,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.schemas import (
    APIResponse,
    SdnAccessCompleteRequest,
    SdnAccessExecuteRequest,
    SdnAccessPreviewRequest,
    SdnWithdrawRequest,
)
from app.services.sdn_deployment_executor import SdnDeploymentError, SdnDeploymentExecutor
from app.services.sdn_operation_service import (
    ACTIVE_PHASE_EXPECTED_KIND,
    SdnOperationError,
    AttemptUnitHooks,
    acquire_claims,
    acquire_or_reuse_claims,
    claim_action_admission,
    claim_deployment,
    claim_stale_takeover,
    compute_access_fingerprint,
    compute_semantic_hash,
    consume_plan,
    create_attempt,
    create_attempt_units,
    create_plan,
    derive_attempt_status_from_units,
    device_port_key,
    finish_action,
    finish_attempt,
    get_plan,
    mark_attempt_stale,
    mark_operation_claims_ambiguous,
    mark_unit_done,
    mark_unit_reconciled,
    mark_unit_started,
    normalize_access_request,
    release_claims,
    resolve_operation,
    snapshot_identity,
    tenant_key,
    vpc_device_key,
    vpc_key,
)
from app.services.sdn_validation_collector import SdnValidationCollector
from app.services.vpc_config_planner import VPCConfigPlanner
from app.services.sdn_device_adapter import H3cV7Adapter
from app.utils.device_access import get_device_with_password

logger = logging.getLogger("app")

router = APIRouter(prefix="/api/sdn", tags=["sdn-access"])

# CR28: withdraw 准入的合法来源状态——除不可逆终态 withdrawn 与进行中 validating/withdrawing 之外皆可。
WITHDRAW_FROM_STATUSES = (
    "planned", "applied", "awaiting_wiring", "awaiting_validation",
    "succeeded", "degraded", "failed", "unknown",
)


# ── 复用 sdn.py 的辅助 ──
from app.routers.sdn import (  # noqa: E402
    _binding_to_response,
    _create_sdn_deployment,
    _deployment_to_response,
    _get_device_metadata,
    _is_sdn_fabric_member,
    _parse_protected_interfaces,
)


def _load_vpc_tenant(db: Session, vpc_id: int):
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return None, None, error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    return vpc, tenant, None


def _get_device_authoritative(db: Session, device_id: int, *, fresh: bool):
    """获取设备元数据（CR7：复用 device_access 显式分派，不靠异常/不污染 session）。

    fresh=True 时 split 模式绕过 5s 缓存重拉权威 sdn_role/protected_interfaces。
    """
    from app.utils.device_access import get_device_metadata
    device, error = get_device_metadata(db, device_id, fresh=fresh)
    if error is not None:
        return None, error
    return device, None


# S1-016: terminal access 前置部署证明（predeploy）的绝对新鲜度上限。
# 与 SdnValidationCollector.DEFAULT_MIN_INTERVAL_SECONDS 对齐：超过即视为陈旧证据，不得放行。
PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS = 600

# S1-017: terminal L2 predeploy 独立于 L3/网关健康。
# 必需的 validation_details 条件只含 L2/EVPN 维度：BGP peer Established、目标 VSI 存在/Up、Type-3 可达。
# 明确不含 vsi_interface_exists / l3_vni_present（L3/网关维度，交由 complete 业务验证的 l3_gateway_ready 表达）。
# raw_has_error 的「无 CLI 错误」语义按 L2 所需命令输出重算（见 _terminal_l2_required_commands），
# 不复用 collector 的全量 all_text raw_has_error——后者会把 Vsi-interface/L3VNI 的 CLI 错误错误地耦合到 L2。
TERMINAL_L2_REQUIRED_CHECKS = ("bgp_peer_established", "vsi_exists", "vsi_up", "type3_present")


def _terminal_l2_required_commands(vpc: SdnVpc) -> tuple[str, ...]:
    """terminal L2 predeploy 所需的原始 display 命令（支撑 BGP/VSI/Type-3）。

    不含 Vsi-interface/L3VNI/ARP/MAC/Type-2 命令——那些是 L3/网关/主机维度，
    其失败/缺失/CLI 错误不得拖垮纯 L2 门禁。
    """
    return (
        "display bgp peer l2vpn evpn",
        f"display l2vpn vsi name {vpc.vsi_name} verbose",
        "display bgp l2vpn evpn",
    )


def _l2_ready_status(db: Session, vpc: SdnVpc, device_id: int) -> tuple[str, str]:
    """前置部署证明（L2 就绪，terminal access predeploy gate）。

    S1-016 收紧：除「存在成功 create + 之后无成功 delete + 采集晚于配置完成」外，
    还必须证明：
    - 该 create deployment 对应当前 vpc.version（版本因果，不伪造）；
    - 快照绝对新鲜（collection_completed_at 距今 <= PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS）；
    - L2 所需命令（BGP peer / VSI / Type-3）全部成功、无 CLI 错误（L2-scoped）；
    - validation_details 中 L2 必需条件（bgp_peer_established/vsi_exists/vsi_up/type3_present）为真。
    S1-017 解除 L3 耦合：不再要求整张快照 validation_result==active，也不遍历整张快照所有命令；
    任何 L2 字段缺失 / 旧格式 / 解析失败 / L2 命令失败 / L2 CLI 错误 一律 unknown（不放行）。
    """
    create = (
        db.query(SdnDeployment)
        .filter(
            SdnDeployment.vpc_id == vpc.id,
            SdnDeployment.device_id == device_id,
            SdnDeployment.action == "create",
            SdnDeployment.status == "success",
        )
        .order_by(SdnDeployment.id.desc())
        .first()
    )
    if not create:
        return "missing", "no successful create deployment on target leaf"
    delete = (
        db.query(SdnDeployment)
        .filter(
            SdnDeployment.vpc_id == vpc.id,
            SdnDeployment.device_id == device_id,
            SdnDeployment.action == "delete",
            SdnDeployment.status == "success",
            SdnDeployment.id > create.id,
        )
        .first()
    )
    if delete:
        return "missing", "VPC deleted after successful create"

    # S1-016: 版本因果——deployment 必须对应当前 vpc.version，缺失/不一致 = 证据不足，不得伪造
    if getattr(create, "version", None) != vpc.version:
        return "unknown", (
            f"create deployment version {getattr(create, 'version', None)} != vpc.version {vpc.version}; "
            "cannot prove current VPC config matches this deployment"
        )

    # CR8: 用持久化的 config 完成/回读时间，而非 created_at（created_at 不证明配置真正落地）
    completion = getattr(create, "config_completed_at", None)
    if completion is None:
        return "unknown", "successful create lacks durable config completion time"

    snap = (
        db.query(SdnValidationSnapshot)
        .filter(
            SdnValidationSnapshot.vpc_id == vpc.id,
            SdnValidationSnapshot.device_id == device_id,
        )
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )
    if not snap or snap.collection_completed_at is None:
        return "unknown", "no fresh observation after successful create"

    # 因果窗口：采集必须晚于配置完成
    if snap.collection_completed_at < completion:
        return "unknown", "observation predates config completion"

    # S1-016: 绝对新鲜度——采集完成距今不得超过 TTL
    age = datetime.utcnow() - snap.collection_completed_at
    if age > timedelta(seconds=PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS):
        return "unknown", f"observation older than {PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS}s"

    # S1-017: 只按 L2 所需命令映射检查原始命令完整性；无关 L3/Vsi-interface/ARP 命令不参与。
    try:
        snap_data = json.loads(snap.snapshot_data or "{}")
    except Exception:
        return "unknown", "snapshot_data invalid json"
    if not isinstance(snap_data, dict):
        return "unknown", "snapshot_data not an object"
    commands = snap_data.get("commands")
    if not isinstance(commands, dict) or not commands:
        return "unknown", "snapshot has no commands"

    l2_outputs: dict[str, str] = {}
    for cmd in _terminal_l2_required_commands(vpc):
        entry = commands.get(cmd)
        if not isinstance(entry, dict):
            return "unknown", f"missing L2 command: {cmd}"
        if entry.get("success") is not True:
            return "unknown", f"L2 command failed: {cmd}"
        if entry.get("error"):
            return "unknown", f"L2 command cli error: {cmd}"
        output = entry.get("output")
        if not isinstance(output, str):
            output = ""
        if SdnValidationCollector._has_display_error(output):
            return "unknown", f"L2 command output has display error: {cmd}"
        l2_outputs[cmd] = output

    # L2-scoped 无 CLI 错误（raw_has_error 语义只覆盖 L2 命令输出）
    if SdnValidationCollector._has_display_error("\n".join(l2_outputs.values())):
        return "unknown", "L2 evidence has CLI error"

    # S1-017: validation_details 中 L2 必需条件为真（不含 L3/网关维度）
    try:
        details = json.loads(snap.validation_details or "{}")
    except Exception:
        return "unknown", "validation_details invalid json"
    if not isinstance(details, dict):
        return "unknown", "validation_details not an object"

    # S1-020: 统一 collector 的 `vsi_up.required = bool(active/expanding 本地绑定)` 语义。
    # 目标 Leaf 尚无 active/expanding 本地绑定时（首次 AC bootstrap），VSI State Down 不得阻断
    # 第一个本地 AC；已有 active/expanding 绑定时，vsi_up 仍是必需条件，Down 保守阻断后续接入。
    # 其余三项（bgp_peer_established / vsi_exists / type3_present）始终必需，不受影响。
    has_local_binding = (
        db.query(SdnPortBinding)
        .filter(
            SdnPortBinding.vpc_id == vpc.id,
            SdnPortBinding.device_id == device_id,
            SdnPortBinding.status.in_(("active", "expanding")),
        )
        .first()
        is not None
    )
    for k in TERMINAL_L2_REQUIRED_CHECKS:
        if k == "vsi_up" and not has_local_binding:
            continue  # 首次 AC bootstrap：vsi_up 不作为门禁
        item = details.get(k)
        if not isinstance(item, dict) or item.get("ok") is not True:
            return "unknown", f"L2 condition not true: {k}"
    return "ready", ""


def _operation_claims(vpc: SdnVpc, device_id: int, if_index: int) -> list[str]:
    return [
        tenant_key(vpc.tenant_id),
        vpc_key(vpc.id),
        vpc_device_key(vpc.id, device_id),
        device_port_key(device_id, if_index),
    ]


_INTERFACE_NAME_RE = re.compile(
    r"^(GigabitEthernet|Ten-GigabitEthernet|XGigabitEthernet|Twenty-FiveGigE|25GE|FortyGigE|40GE|HundredGigE|100GE)\d+/\d+/\d+$"
)
_MANAGEMENT_INTERFACE_PREFIXES = ("OOB", "M-GigabitEthernet", "Vlan-interface", "LoopBack", "M-Eth")


def _validate_expected_host_ip(vpc: SdnVpc, expected_host_ip: Optional[str]) -> Optional[str]:
    """CR6: expected_host_ip 必须是 VPC CIDR 内的主机地址，排除网络/广播/网关地址。"""
    if not expected_host_ip:
        return None
    try:
        ip = ipaddress.ip_address(expected_host_ip)
        net = ipaddress.ip_network(vpc.cidr, strict=False)
    except ValueError:
        return "invalid ip address"
    if ip.version != net.version or ip not in net:
        return "outside vpc cidr"
    if ip == net.network_address or ip == net.broadcast_address:
        return "network/broadcast address"
    if vpc.gateway_ip:
        try:
            if ip == ipaddress.ip_address(vpc.gateway_ip):
                return "gateway address"
        except ValueError:
            pass
    return None


def _validate_interface_identity(interface_name: Optional[str], if_index: Optional[int]) -> Optional[str]:
    """CR6: 接口身份校验——物理以太接口命名 + if_index 合法，排除管理/OOB 接口。"""
    if not if_index or if_index <= 0:
        return "invalid if_index"
    if not interface_name:
        return "missing interface_name"
    if any(interface_name.startswith(p) for p in _MANAGEMENT_INTERFACE_PREFIXES):
        return "management interface not allowed"
    if not _INTERFACE_NAME_RE.match(interface_name):
        return "invalid interface name"
    return None


def _operation_to_dict(db: Session, op: SdnOperation) -> dict:
    attempts = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op.id).order_by(SdnAttempt.id).all()
    attempt_data = []
    for a in attempts:
        units = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == a.id).order_by(SdnAttemptUnit.unit_index).all()
        attempt_data.append({
            "attempt_id": a.id,
            "kind": a.kind,
            "status": a.status,
            "deployment_id": a.deployment_id,
            "started_at": a.started_at,
            "completed_at": a.completed_at,
            "units": [
                {
                    "unit_index": u.unit_index,
                    "unit_name": u.unit_name,
                    "state": u.state,
                    "evidence": json.loads(u.evidence_json) if u.evidence_json else None,
                    "started_at": u.started_at,
                    "completed_at": u.completed_at,
                }
                for u in units
            ],
        })
    scope = json.loads(op.scope_json) if op.scope_json else None
    return {
        "operation_id": op.id,
        "idempotency_key": op.idempotency_key,
        "operation_type": op.operation_type,
        "tenant_id": op.tenant_id,
        "vpc_id": op.vpc_id,
        "device_id": op.device_id,
        "plan_id": op.plan_id,
        "expected_host_ip": op.expected_host_ip,
        "status": op.status,
        "scope": scope,
        "attempts": attempt_data,
        "created_at": op.created_at,
        "updated_at": op.updated_at,
    }


# ── 预览 ──

@router.post("/vpcs/{vpc_id}/access-preview", response_model=APIResponse)
def preview_access(vpc_id: int, payload: SdnAccessPreviewRequest, db: Session = Depends(get_db)):
    """服务端预览：持久化一条计划，不写设备/不建 binding/deployment/operation。"""
    vpc, tenant, vpc_err = _load_vpc_tenant(db, vpc_id)
    if vpc_err:
        return vpc_err

    device, device_err = _get_device_authoritative(db, payload.device_id, fresh=False)
    if device_err:
        return device_err
    if not _is_sdn_fabric_member(device):
        return error_response(err.OPERATION_FAILED, params={"error": "only EVPN fabric devices can be selected"})

    blocking = []
    if payload.if_index in _parse_protected_interfaces(device):
        blocking.append({"code": "sdn.interface_protected", "detail": "target interface is protected"})

    # CR6: ipaddress/接口身份校验（blocking 级）
    ip_err = _validate_expected_host_ip(vpc, payload.expected_host_ip)
    if ip_err:
        blocking.append({"code": "sdn.invalid_host_ip", "detail": ip_err})
    iface_err = _validate_interface_identity(payload.interface_name, payload.if_index)
    if iface_err:
        blocking.append({"code": "sdn.invalid_interface", "detail": iface_err})

    conflict = (
        db.query(SdnPortBinding)
        .filter(
            SdnPortBinding.device_id == payload.device_id,
            SdnPortBinding.if_index == payload.if_index,
            SdnPortBinding.status != "unbound",
        )
        .first()
    )
    port_free = conflict is None
    if not port_free:
        blocking.append({"code": "sdn.port_binding_conflict", "detail": "port already bound"})

    l2_status, l2_detail = _l2_ready_status(db, vpc, payload.device_id)
    predeploy_ready = l2_status == "ready"
    if not predeploy_ready:
        blocking.append({"code": f"sdn.predeploy_{l2_status}", "detail": l2_detail})

    plan_id = str(uuid.uuid4())
    request_semantics = normalize_access_request(
        tenant_id=vpc.tenant_id,
        vpc_id=vpc.id,
        device_id=payload.device_id,
        if_index=payload.if_index,
        interface_name=payload.interface_name,
        access_vlan=payload.access_vlan,
        service_instance=payload.service_instance,
        expected_host_ip=payload.expected_host_ip,
        mode=payload.mode,
    )
    semantic_hash = compute_semantic_hash(
        vpc_version=vpc.version,
        sdn_role=getattr(device, "sdn_role", None),
        protected=_parse_protected_interfaces(device),
        port_free=port_free,
        predeploy_ready=predeploy_ready,
        request=request_semantics,
    )
    version_snapshot = {
        "vpc_version": vpc.version,
        "sdn_role": getattr(device, "sdn_role", None),
        "protected_interfaces": sorted(_parse_protected_interfaces(device)),
        "port_free": port_free,
        "predeploy_status": l2_status,
    }
    scope = {
        "tenant_id": vpc.tenant_id,
        "tenant_name": tenant.name if tenant else "",
        "vpc_id": vpc.id,
        "vpc_name": vpc.name,
        "device_id": payload.device_id,
        "device_name": getattr(device, "name", ""),
        "if_index": payload.if_index,
        "interface_name": payload.interface_name,
        "service_instance": payload.service_instance,
        "access_vlan": payload.access_vlan,
        "expected_host_ip": payload.expected_host_ip,
        "mode": payload.mode,
    }
    plan = create_plan(
        db,
        plan_id=plan_id,
        semantic_hash=semantic_hash,
        version_snapshot_json=json.dumps(version_snapshot, ensure_ascii=False),
        scope_json=json.dumps(scope, ensure_ascii=False),
    )
    db.commit()
    return APIResponse(success=True, data={
        "plan_id": plan.plan_id,
        "status": plan.status,
        "expires_at": plan.expires_at,
        "scope": scope,
        "blocking": blocking,
        "predeploy_status": l2_status,
    })


# ── 执行 ──

@router.post("/vpcs/{vpc_id}/access", response_model=APIResponse)
def execute_access(vpc_id: int, payload: SdnAccessExecuteRequest, db: Session = Depends(get_db)):
    """幂等执行终端接入：消费 plan → 建 operation/binding/deployment，可选 auto_apply。"""
    vpc, tenant, vpc_err = _load_vpc_tenant(db, vpc_id)
    if vpc_err:
        return vpc_err

    # 权威元数据（fresh：绕过 5s 缓存）
    device, device_err = _get_device_authoritative(db, payload.device_id, fresh=True)
    if device_err:
        return device_err
    if not _is_sdn_fabric_member(device):
        return error_response(err.OPERATION_FAILED, params={"error": "only EVPN fabric devices can be selected"})
    if payload.if_index in _parse_protected_interfaces(device):
        return error_response(err.INTERFACE_PROTECTED_BLOCKED)

    # CR6: ipaddress/接口身份硬校验（执行不可绕过）
    ip_err = _validate_expected_host_ip(vpc, payload.expected_host_ip)
    if ip_err:
        return error_response(err.SDN_INVALID_HOST_IP, params={"detail": ip_err})
    iface_err = _validate_interface_identity(payload.interface_name, payload.if_index)
    if iface_err:
        return error_response(err.SDN_INVALID_INTERFACE, params={"detail": iface_err})

    # 前置部署证明（L2 就绪）
    l2_status, l2_detail = _l2_ready_status(db, vpc, payload.device_id)
    if l2_status == "missing":
        return error_response(err.SDN_PREDEPLOY_MISSING, params={"detail": l2_detail})
    if l2_status == "unknown":
        # S1-016: 证据不足 → execute 必须重新取得足够新的权威设备证据，不能复用陈旧缓存。
        # 读取/采集为只读 display，不写设备；采集失败或仍不满足门禁 → 阻断且零业务副作用
        # （尚未消费 plan / 建 operation/binding/deployment / 占用 claim）。
        collector = SdnValidationCollector()
        _, coll_err, _ = collector.sync(
            db, vpc.id, payload.device_id, force=True, min_interval_seconds=0
        )
        if coll_err is not None:
            return error_response(err.SDN_PREDEPLOY_UNKNOWN, params={"detail": f"evidence refresh failed: {coll_err.get('key')}"})
        l2_status, l2_detail = _l2_ready_status(db, vpc, payload.device_id)
        if l2_status == "missing":
            return error_response(err.SDN_PREDEPLOY_MISSING, params={"detail": l2_detail})
        if l2_status != "ready":
            return error_response(err.SDN_PREDEPLOY_UNKNOWN, params={"detail": l2_detail})

    fingerprint = compute_access_fingerprint(
        tenant_id=vpc.tenant_id,
        vpc_id=vpc.id,
        device_id=payload.device_id,
        if_index=payload.if_index,
        interface_name=payload.interface_name,
        access_vlan=payload.access_vlan,
        service_instance=payload.service_instance,
        expected_host_ip=payload.expected_host_ip,
        auto_apply=payload.auto_apply,
        mode=payload.mode,
    )

    scope = {
        "tenant_id": vpc.tenant_id,
        "vpc_id": vpc.id,
        "device_id": payload.device_id,
        "if_index": payload.if_index,
        "interface_name": payload.interface_name,
        "service_instance": payload.service_instance,
        "access_vlan": payload.access_vlan,
        "expected_host_ip": payload.expected_host_ip,
    }

    # 计划/幂等事务顺序：先解析 plan 状态（not_found/expired/consumed），
    # 仅对 valid 计划做新鲜度（归一化 scope + 语义哈希）校验，再消费 plan + 幂等创建 operation。
    try:
        _plan = get_plan(db, payload.plan_id)
    except SdnOperationError as e:
        return error_response(_err_attr(e), params=e.params)

    if _plan.status == "consumed":
        existing = db.query(SdnOperation).filter(SdnOperation.idempotency_key == payload.idempotency_key).first()
        if existing and existing.fingerprint == fingerprint and existing.tenant_id == vpc.tenant_id \
                and existing.vpc_id == vpc.id and existing.device_id == payload.device_id:
            return APIResponse(success=True, data={**_operation_to_dict(db, existing), "duplicate": True})
        return error_response(err.SDN_PLAN_CONSUMED, params={"plan_id": payload.plan_id})
    if _plan.status != "valid":
        return error_response(err.SDN_PLAN_EXPIRED, params={"plan_id": payload.plan_id})

    # CR6: 归一化请求语义 + 服务端状态做 stale 校验（scope 与语义哈希都必须一致）
    _port_free = (
        db.query(SdnPortBinding)
        .filter(
            SdnPortBinding.device_id == payload.device_id,
            SdnPortBinding.if_index == payload.if_index,
            SdnPortBinding.status != "unbound",
        )
        .first()
        is None
    )
    _request_semantics = normalize_access_request(
        tenant_id=vpc.tenant_id,
        vpc_id=vpc.id,
        device_id=payload.device_id,
        if_index=payload.if_index,
        interface_name=payload.interface_name,
        access_vlan=payload.access_vlan,
        service_instance=payload.service_instance,
        expected_host_ip=payload.expected_host_ip,
        mode=payload.mode,
    )
    _plan_scope = json.loads(_plan.scope_json) if _plan.scope_json else {}
    _plan_req = {k: _plan_scope.get(k) for k in _request_semantics}
    if _plan_req != _request_semantics:
        return error_response(err.SDN_PLAN_STALE)
    _current_hash = compute_semantic_hash(
        vpc_version=vpc.version,
        sdn_role=getattr(device, "sdn_role", None),
        protected=_parse_protected_interfaces(device),
        port_free=_port_free,
        predeploy_ready=(l2_status == "ready"),
        request=_request_semantics,
    )
    if _plan.semantic_hash != _current_hash:
        return error_response(err.SDN_PLAN_STALE)

    try:
        consume_plan(db, payload.plan_id)
    except SdnOperationError as e:
        return error_response(_err_attr(e), params=e.params)

    # 幂等创建 operation（同 key 同 scope 同 fingerprint → duplicate；异 fingerprint → 409；跨 scope → 404）
    try:
        op, created = resolve_operation(
            db,
            idempotency_key=payload.idempotency_key,
            fingerprint=fingerprint,
            operation_type="terminal_access",
            tenant_id=vpc.tenant_id,
            vpc_id=vpc.id,
            device_id=payload.device_id,
            plan_id=payload.plan_id,
            expected_host_ip=payload.expected_host_ip,
            request_payload_json=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
            scope_json=json.dumps(scope, ensure_ascii=False),
        )
    except SdnOperationError as e:
        return error_response(_err_attr(e), params=e.params, fallback=_fallback(e))

    if not created:
        db.commit()
        return APIResponse(success=True, data={**_operation_to_dict(db, op), "duplicate": True})

    # CR3: 端口占用探测（SELECT-then-INSERT 由下方部分唯一索引 uq_sdn_port_bindings_live 兜底）
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
        db.rollback()
        return error_response(err.SDN_PORT_BINDING_CONFLICT, params={"device_id": payload.device_id, "interface_name": payload.interface_name})

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
        created_by_operation_id=op.id,
        last_changed_by_operation_id=op.id,
        operation_id=op.id,
    )
    db.add(binding)
    db.flush()
    # CR4: 持久化绑定版本所有权，供 withdraw 做版本 CAS
    scope["binding_version"] = binding.version
    op.scope_json = json.dumps(scope, ensure_ascii=False)

    planner = VPCConfigPlanner(H3cV7Adapter())
    units = planner.plan_port_bind(binding, vpc, mode=payload.mode or "auto", dry_run=True)
    deployment = SdnDeployment(
        vpc_id=vpc.id,
        device_id=payload.device_id,
        action="port_bind",
        unit="port-bind",
        port_binding_id=binding.id,
        planned_config=VPCConfigPlanner.serialize(units),
        status="pending",
        operation_id=op.id,
    )
    db.add(deployment)
    db.flush()

    unit_names = [u.name for u in units] or ["port-bind"]
    attempt = create_attempt(
        db,
        operation_id=op.id,
        kind="execute",
        deployment_id=deployment.id,
        owner=str(op.id),
        scope_json=json.dumps(scope, ensure_ascii=False),
    )
    create_attempt_units(db, attempt.id, unit_names)

    # CR3: 在同一个短事务内认领（owner=operation+attempt），与 operation/binding/deployment 一起 commit。
    try:
        acquired = acquire_claims(
            db, _operation_claims(vpc, payload.device_id, payload.if_index),
            operation_id=op.id, attempt_id=attempt.id,
        )
    except SdnOperationError as e:
        db.rollback()
        return error_response(_err_attr(e), params=e.params)

    op.status = "claimed" if payload.auto_apply else "awaiting_wiring"
    db.commit()  # CR3: 原子暴露（无半状态）

    if payload.auto_apply:
        hooks = AttemptUnitHooks(db, attempt.id, operation_id=op.id)
        executor = SdnDeploymentExecutor()
        try:
            deployment = executor.execute(db, deployment.id, unit_hooks=hooks)
        except SdnDeploymentError:
            deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()
        db.expire_all()
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()

        final_state = derive_attempt_status_from_units(db, attempt.id)
        finish_attempt(db, attempt.id, final_state)
        if deployment.status == "success":
            binding.status = "active"
            op.status = "awaiting_validation"
        elif deployment.status == "failed":
            op.status = "failed"
        else:
            op.status = "unknown"
        # CR12: 确定性成功/失败才释放 claims；unknown 保留并标 ambiguous（等 reconcile）
        if deployment.status in ("success", "failed"):
            release_claims(db, acquired, owner_operation_id=op.id)
        else:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
        db.commit()
    # else: 非 auto-apply 保留 claim（资源预订），由 apply/withdraw 续作

    return APIResponse(success=True, data=_operation_to_dict(db, op))


# ── 续作：非 auto-apply 的显式执行（CR3）──

@router.post("/operations/{operation_id}/apply", response_model=APIResponse)
def apply_access(operation_id: int, db: Session = Depends(get_db)):
    """对 auto_apply=False 创建的操作执行设备 I/O（消费已持有的 claim）。

    CR29：进入任何设备 I/O 前原子 CAS `awaiting_wiring → applying`，与 validating/withdrawing 互斥；
    收尾条件 CAS `applying → awaiting_validation|failed|unknown`，迟到收尾不覆盖现状、不误释放 claims；
    deployment CAS 失败（已被他人认领）停止上层收尾，不推导 unknown、不误标 claims。
    """
    op = db.query(SdnOperation).filter(SdnOperation.id == operation_id).first()
    if not op:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op.id, SdnAttempt.kind == "execute").order_by(SdnAttempt.id.desc()).first()
    deployment = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op.id, SdnDeployment.status == "pending").order_by(SdnDeployment.id.desc()).first()
    if not attempt or not deployment:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    # CR11: 复用本 operation 已持有的 claim，仅补齐缺失；绝不对自己的 claim 重新认领
    vpc = db.query(SdnVpc).filter(SdnVpc.id == op.vpc_id).first()
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op.id).first()
    keys = _operation_claims(vpc, op.device_id, binding.if_index if binding else 0)

    # CR29/CR30: 原子准入——只有 rowcount==1 的请求能把 awaiting_wiring 置为 applying（绑定原 execute attempt 代际令牌）并调用 executor
    if not claim_action_admission(db, op.id, from_statuses=["awaiting_wiring"], to_status="applying", active_attempt_id=attempt.id):
        db.rollback()
        db.expire_all()
        refreshed = db.query(SdnOperation).filter(SdnOperation.id == op.id).first()
        if refreshed is not None and refreshed.status in ("applying", "validating", "withdrawing", "reconciling"):
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        data = _operation_to_dict(db, refreshed) if refreshed is not None else {"operation_id": op.id}
        data["note"] = f"apply not applicable in status {refreshed.status if refreshed is not None else 'gone'}"
        return APIResponse(success=True, data=data)

    try:
        held, acquired = acquire_or_reuse_claims(db, keys, operation_id=op.id, attempt_id=attempt.id)
    except SdnOperationError as e:
        db.rollback()
        return error_response(_err_attr(e), params=e.params)
    db.commit()

    hooks = AttemptUnitHooks(db, attempt.id, operation_id=op.id)
    executor = SdnDeploymentExecutor()
    try:
        deployment = executor.execute(db, deployment.id, unit_hooks=hooks)
    except SdnDeploymentError as e:
        db.expire_all()
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()
        # CR29: deployment CAS 失败（已被另一执行者认领 running）→ 停止上层收尾，不推导 unknown、不误标 claims
        if e.error_key == "SDN_DEPLOYMENT_NOT_PENDING" or (deployment is not None and deployment.status == "running"):
            db.rollback()
            return error_response(err.SDN_DEPLOYMENT_NOT_PENDING, params={"id": deployment.id, "status": deployment.status if deployment else "missing"})
    db.expire_all()
    deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()

    final_state = derive_attempt_status_from_units(db, attempt.id)
    finish_attempt(db, attempt.id, final_state)
    if deployment.status == "success":
        final_op_status = "awaiting_validation"
    elif deployment.status == "failed":
        final_op_status = "failed"
    else:
        final_op_status = "unknown"

    # CR29/CR30: 条件收尾 CAS——只有 op 仍在 applying phase 且持原 execute attempt 代际令牌才写入终态；迟到收尾不覆盖现状、不误释放 claims
    won = finish_action(db, op.id, from_status="applying", final_status=final_op_status, active_attempt_id=attempt.id)
    if won:
        if deployment.status == "success":
            binding.status = "active"
            # CR12: 确定性成功才释放本 operation 完整 scoped claims；否则保留并标 ambiguous
            release_claims(db, held, owner_operation_id=op.id)
        else:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
    db.commit()

    resp_status = final_op_status
    if not won:
        db.refresh(op)
        resp_status = op.status
    data = _operation_to_dict(db, op)
    data["status"] = resp_status
    if not won:
        data["note"] = "late completion: status changed by concurrent action"
    return APIResponse(success=True, data=data)


# ── 完成 / 验证 ──

def _ip_exact_match(text: str, ip: str) -> bool:
    """CR16: 精确 IP 匹配（前后无数字边界），避免 .2 误匹配 .20 / .200。"""
    if not ip or not text:
        return False
    pattern = r"(?<!\d)" + re.escape(ip) + r"(?!\d)"
    return re.search(pattern, text) is not None


_MAC_RE = re.compile(r"(?i)\b[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}\b")


def _build_host_observations(snapshot_data_str: Optional[str], expected_host_ip: Optional[str], interface_name: Optional[str]):
    """CR16/CR23: 结构化主机观测（source/scope）。

    host_observed 仅在以下情况为 True：
    - 本地命令 entry.success==True 且无 error；
    - expected_host_ip 与目标物理接口出现在**同一条本地记录**（ARP 同一行）；
      或通过同一 MAC 关联（ARP 行给出 IP→MAC，MAC 表行给出 MAC→目标端口）。
    远端 EVPN Type-2 / BGP EVPN 只标 remote/inferred，绝不令 host_observed=true。
    """
    observations: list[dict] = []
    host_observed = False
    if not snapshot_data_str:
        return observations, False
    try:
        data = json.loads(snapshot_data_str)
    except Exception:
        return observations, False
    commands = data.get("commands", {})
    local_cmds = {
        "arp": f"display arp vpn-instance {SdnValidationCollector._sdn_l3vpn_name()}",
        "mac": "display l2vpn mac-address",
    }
    remote_cmds = {"display evpn route arp", "display bgp l2vpn evpn", "display bgp peer l2vpn evpn"}

    if expected_host_ip:
        # CR23: ARP 逐记录（行）关联，IP 与接口必须在同一行
        arp_cmd = local_cmds["arp"]
        arp_entry = commands.get(arp_cmd)
        arp_success = bool(arp_entry) and arp_entry.get("success") is True and not arp_entry.get("error")
        arp_output = (arp_entry or {}).get("output", "") or "" if arp_success else ""
        host_mac = None
        arp_same_line = False
        for line in arp_output.splitlines():
            line = line.strip()
            if not line:
                continue
            ip_match = _ip_exact_match(line, expected_host_ip)
            port_match = bool(interface_name) and interface_name in line
            if ip_match and not host_mac:
                m = _MAC_RE.search(line)
                if m:
                    host_mac = m.group(0)
            if ip_match and port_match:
                arp_same_line = True
        if arp_cmd in commands:
            observations.append({
                "source": "local",
                "scope": "local",
                "kind": "arp",
                "command": arp_cmd,
                "success": arp_success,
                "ip_match": _ip_exact_match(arp_output, expected_host_ip),
                "port_match": bool(interface_name) and interface_name in arp_output,
                "same_record": arp_same_line,
                "host_observed": arp_same_line,
            })
        if arp_same_line:
            host_observed = True

        # CR23: MAC 表关联——同一 MAC 出现在目标端口行
        mac_cmd = local_cmds["mac"]
        mac_entry = commands.get(mac_cmd)
        mac_success = bool(mac_entry) and mac_entry.get("success") is True and not mac_entry.get("error")
        mac_output = (mac_entry or {}).get("output", "") or "" if mac_success else ""
        mac_same_record = False
        if mac_success and host_mac and interface_name:
            for line in mac_output.splitlines():
                if host_mac.lower() in line.lower() and interface_name in line:
                    mac_same_record = True
                    break
        if mac_cmd in commands:
            observations.append({
                "source": "local",
                "scope": "local",
                "kind": "mac",
                "command": mac_cmd,
                "success": mac_success,
                "mac_correlated": bool(host_mac),
                "same_record": mac_same_record,
                "host_observed": mac_same_record,
            })
        if mac_same_record:
            host_observed = True

    # 远端证据只记录，不计 host_observed
    for cmd, entry in commands.items():
        if cmd in remote_cmds:
            output = (entry or {}).get("output", "") or ""
            observations.append({
                "source": "remote",
                "scope": "remote",
                "command": cmd,
                "ip_match": _ip_exact_match(output, expected_host_ip) if expected_host_ip else False,
                "host_observed": False,
            })
    return observations, host_observed


def _run_gateway_ping(db: Session, vpc: Optional[SdnVpc], op: SdnOperation, deployment, force: bool) -> dict:
    """CR17: scoped 网关 ping，结构化返回 reachable/unreachable/error/unsupported/not_run。"""
    if not force:
        return {"status": "not_run", "detail": "force_validation=false"}
    if deployment is None or deployment.status != "success":
        return {"status": "not_run", "detail": "deployment not success"}
    if not op.expected_host_ip:
        return {"status": "unsupported", "detail": "no expected host ip"}
    if vpc is None or not getattr(vpc, "gateway_ip", None):
        return {"status": "unsupported", "detail": "no vpc gateway ip"}
    try:
        from app.routers.sdn import _ping_from_vpc_gateway
        result, perr = _ping_from_vpc_gateway(db, vpc, op.device_id, op.expected_host_ip)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": f"{type(e).__name__}: {e}"}
    if perr is not None:
        detail = getattr(perr, "body", None)
        return {"status": "error", "detail": str(detail) if detail else "ping error"}
    if result.get("success"):
        return {"status": "reachable", "detail": (result.get("output", "") or "")[:200]}
    return {"status": "unreachable", "detail": (result.get("error") or result.get("output", ""))[:200]}


@router.post("/operations/{operation_id}/complete", response_model=APIResponse)
def complete_access(operation_id: int, payload: SdnAccessCompleteRequest, db: Session = Depends(get_db)):
    """完成/验证（CR8/CR16/CR17/CR22/CR25/CR27）：四维状态 + 结构化主机观测 + 网关 ping，绝不互相冒充。

    CR22 守卫：
    - 已存在确定完成的 validate attempt（succeeded/failed_known）→ 幂等返回原结果，不新建 attempt。
    - op.status 非 awaiting_validation 且非可恢复 unknown（withdrawn/failed 等不可验证终态）→ 不改任何状态。
    - 只允许 port_bind deployment 作为执行证据，绝不选较新的 port_unbind deployment。
    - mutation 前 owner-aware 获取/复用 tenant/vpc/vpc-device claims。

    CR25 恢复路径：
    - 只有确定完成的 validate attempt 才幂等返回；unknown validation 保留旧 attempt 历史，
      并在执行已确定成功（port_bind success + config_completed_at）时允许显式重试新建 validate attempt。
    - 不自动重放设备写操作（执行未知/失败不得走 complete 恢复，需显式 reconcile）。

    CR27 并发准入：
    - 原子 CAS 把 awaiting_validation/unknown → validating；同一 operation 至多一个 validate attempt 进入 I/O。
    - 输家返回 sdn.operation_in_progress，不建第二 attempt、不执行 collector/ping。
    """
    op = db.query(SdnOperation).filter(SdnOperation.id == operation_id).first()
    if not op:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    binding = db.query(SdnPortBinding).filter(SdnPortBinding.created_by_operation_id == op.id).first()
    vpc = db.query(SdnVpc).filter(SdnVpc.id == op.vpc_id).first()
    if not binding or not vpc:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    # CR22: 只允许原 port_bind deployment 作为执行证据（不用较新的 port_unbind）
    deployment = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.operation_id == op.id, SdnDeployment.action == "port_bind")
        .order_by(SdnDeployment.id.desc())
        .first()
    )

    # CR25: 幂等仅限“确定完成”的 validate attempt；unknown validation 保留历史并允许显式重试
    latest_validate = (
        db.query(SdnAttempt)
        .filter(SdnAttempt.operation_id == op.id, SdnAttempt.kind == "validate")
        .order_by(SdnAttempt.id.desc())
        .first()
    )
    if latest_validate is not None and latest_validate.status in ("succeeded", "failed_known"):
        data = _operation_to_dict(db, op)
        data["note"] = "already validated (idempotent)"
        return APIResponse(success=True, data=data)

    execution_succeeded = (
        deployment is not None
        and deployment.status == "success"
        and getattr(deployment, "config_completed_at", None) is not None
    )

    if deployment is None:
        data = _operation_to_dict(db, op)
        data["note"] = "no port_bind deployment"
        return APIResponse(success=True, data=data)

    # CR22/CR25: 状态守卫——awaiting_validation 正常；unknown（执行已确定成功 + 存在未完成 validate attempt）可显式重试
    recoverable = (
        op.status == "unknown"
        and execution_succeeded
        and latest_validate is not None
    )
    # CR27/CR28/CR29/CR31: 已有 validate/withdraw/apply/reconcile 进行中（另一请求已准入）→ 明确 in-progress，不重复准入
    if op.status in ("validating", "withdrawing", "applying", "reconciling"):
        return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
    if op.status == "awaiting_validation":
        from_status = "awaiting_validation"
    elif recoverable:
        from_status = "unknown"
    else:
        data = _operation_to_dict(db, op)
        data["note"] = f"not verifiable in status {op.status}"
        return APIResponse(success=True, data=data)

    # CR27/CR28/CR30: 先建 validate attempt 拿代际令牌，再原子准入（from_status → validating + 绑定 token）
    guard_keys = [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, op.device_id)]
    attempt = create_attempt(db, operation_id=op.id, kind="validate", owner=str(op.id))
    if not claim_action_admission(db, op.id, from_statuses=[from_status], to_status="validating", active_attempt_id=attempt.id):
        db.rollback()  # 输家：回滚刚建的临时 attempt，不留垃圾
        db.expire_all()
        refreshed = db.query(SdnOperation).filter(SdnOperation.id == op.id).first()
        if refreshed is not None and refreshed.status in ("validating", "withdrawing", "applying", "reconciling"):
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        data = _operation_to_dict(db, refreshed) if refreshed is not None else {"operation_id": op.id}
        data["note"] = f"already settled in status {refreshed.status if refreshed is not None else 'gone'}"
        return APIResponse(success=True, data=data)

    # 赢者：获取/复用 claims（与 admission 同事务，原子提交）
    try:
        held_keys, _ = acquire_or_reuse_claims(db, guard_keys, operation_id=op.id, attempt_id=attempt.id)
    except SdnOperationError as e:
        db.rollback()
        return error_response(_err_attr(e), params=e.params)
    db.commit()

    collector = SdnValidationCollector()
    snapshot, coll_err, cached = collector.sync(
        db, op.vpc_id, op.device_id, force=payload.force_validation, min_interval_seconds=0 if payload.force_validation else 600
    )
    if coll_err is not None:
        # CR17: 采集失败 = 证据不足，既不等于成功也不等于主机失败；claims 保留并标 ambiguous
        attempt.evidence_json = json.dumps({"dimensions": {"evidence": {"status": "insufficient", "reason": coll_err.get("key")}}}, ensure_ascii=False)
        finish_attempt(db, attempt.id, "unknown")
        # CR28/CR30: 条件收尾 CAS——迟到收尾/代际已被接管时不得覆盖现状
        won = finish_action(db, op.id, from_status="validating", final_status="unknown", active_attempt_id=attempt.id)
        if won:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
        db.commit()
        if won:
            final_op_status = "unknown"
        else:
            db.refresh(op)
            final_op_status = op.status
        return APIResponse(success=True, data={
            "operation_id": op.id, "status": final_op_status,
            "dimensions": {"evidence": {"status": "insufficient", "reason": coll_err.get("key")}},
            "reconciled_like": False,
            "note": "" if won else "late completion: status changed by concurrent action",
        })

    # CR8: cached 快照不可变——只在新快照上绑定 operation/attempt
    if not cached:
        snapshot.operation_id = op.id
        snapshot.attempt_id = attempt.id
        db.commit()

    # 维度 1: execution（配置执行）
    config_completed = getattr(deployment, "config_completed_at", None) if deployment else None
    exec_ok = deployment is not None and deployment.status == "success" and config_completed is not None

    # 维度 4: evidence（因果窗口 + 非 cached）
    causal_ok = True
    if cached:
        causal_ok = False
    if exec_ok:
        if snapshot.collection_started_at is None or snapshot.collection_started_at < config_completed:
            causal_ok = False
    else:
        causal_ok = False

    result = snapshot.validation_result if snapshot.validation_result else "unknown"

    # CR16/CR23: 结构化主机观测（本地 ARP/MAC 同记录关联）
    observations, host_observed = _build_host_observations(
        snapshot.snapshot_data, op.expected_host_ip, binding.interface_name if binding else None
    )

    # CR17: L2 vs L3/gateway 各自判定（业务验证）
    l2_ready = False
    l3_gateway_ready = False
    if snapshot.validation_details:
        try:
            details = json.loads(snapshot.validation_details)
            l2_ready = all(details.get(k, {}).get("ok") is True for k in ("vsi_exists", "vsi_up", "type3_present"))
            l3_gateway_ready = all(details.get(k, {}).get("ok") is True for k in ("vsi_interface_exists", "l3_vni_present"))
        except Exception:
            pass

    # CR17: scoped 网关 ping（结构化，异常不静默吞掉）
    ping = _run_gateway_ping(db, vpc, op, deployment, payload.force_validation)

    business_ok = l2_ready and l3_gateway_ready
    business_reasons = []
    if not l2_ready:
        business_reasons.append("l2 not ready")
    if not l3_gateway_ready:
        business_reasons.append("l3/gateway not ready")
    if op.expected_host_ip and not host_observed:
        business_ok = False
        business_reasons.append("host not observed locally")
    if ping["status"] == "unreachable":
        business_ok = False
        business_reasons.append("gateway ping unreachable")

    # 四维 → 操作终态（CR17：不互相冒充；CR28：条件 CAS 收尾，迟到收尾不覆盖现状）
    if not exec_ok:
        final_op_status = "failed" if (deployment and deployment.status == "failed") else "unknown"
        validation_status = "failed_known" if final_op_status == "failed" else "unknown"
    elif not causal_ok:
        final_op_status = "unknown"
        validation_status = "unknown"
    elif ping["status"] == "error" or result == "unknown":
        final_op_status = "unknown"
        validation_status = "unknown"
    elif result == "active" and business_ok:
        final_op_status = "succeeded"
        validation_status = "succeeded"
    else:
        final_op_status = "degraded"
        validation_status = "failed_known"

    dimensions = {
        "execution": {"status": "succeeded" if exec_ok else ("failed" if (deployment and deployment.status == "failed") else "unknown"),
                      "reason": "" if exec_ok else "deployment not success or lacks config_completed_at"},
        "config_readback": {"status": result, "reason": "" if result == "active" else f"validation_result={result}"},
        "business_validation": {"status": "succeeded" if business_ok else "degraded",
                                "reason": "; ".join(business_reasons) if business_reasons else "",
                                "l2_ready": l2_ready, "l3_gateway_ready": l3_gateway_ready,
                                "host_observed": host_observed},
        "evidence": {"status": "fresh" if causal_ok else "stale",
                     "reason": "cached snapshot" if cached else ("" if causal_ok else "observation predates config completion"),
                     "causal_ok": causal_ok, "cached": cached},
    }

    # CR17: 四维 + ping 持久化到本次 validate attempt evidence
    attempt.evidence_json = json.dumps({
        "dimensions": dimensions,
        "gateway_ping": ping,
        "observations": observations,
    }, ensure_ascii=False)
    finish_attempt(db, attempt.id, validation_status)

    # CR28/CR30: 条件收尾 CAS——只有 op 仍在 validating phase 且持本代际令牌才写入终态；迟到收尾不覆盖现状、不误释放 claims
    won = finish_action(db, op.id, from_status="validating", final_status=final_op_status, active_attempt_id=attempt.id)
    if won:
        # CR22: 确定性终态释放 guard claims；unknown 保留并标 ambiguous
        if final_op_status in ("succeeded", "degraded", "failed"):
            release_claims(db, held_keys, owner_operation_id=op.id)
        else:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
    db.commit()

    resp_status = final_op_status
    if not won:
        db.refresh(op)
        resp_status = op.status
    note = "本地网关 ping 仅证明 scoped 本地可达，不证明跨 leaf 成功"
    if not won:
        note = "late completion: status changed by concurrent action"

    return APIResponse(success=True, data={
        "operation_id": op.id,
        "status": resp_status,
        "validation_result": result,
        "dimensions": dimensions,
        "gateway_ping": ping,
        "expected_host_ip": op.expected_host_ip,
        "host_observed": host_observed,
        "observations": observations,
        "causal_ok": causal_ok,
        "cached": cached,
        "collection_started_at": snapshot.collection_started_at,
        "collection_completed_at": snapshot.collection_completed_at,
        "config_completed_at": config_completed,
        "note": note,
    })


# ── 撤回 ──

@router.post("/operations/{operation_id}/withdraw", response_model=APIResponse)
def withdraw_access(operation_id: int, payload: SdnWithdrawRequest, db: Session = Depends(get_db)):
    """受控撤回（CR4/CR28）：owner=operation 的稳定令牌；版本 CAS + 无新引用；幂等。

    CR28：进入任何设备 I/O 前用原子 CAS 取得 withdrawing 独占动作准入（与 validating 互斥）；
    迟到收尾的条件 CAS 不得覆盖被并发动作改变的现状、不得误释放另一动作仍需的 claims。
    """
    op = db.query(SdnOperation).filter(SdnOperation.id == operation_id).first()
    if not op:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    binding = db.query(SdnPortBinding).filter(SdnPortBinding.created_by_operation_id == op.id).first()
    if not binding:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    # 幂等：已撤回直接返回原结果
    if op.status == "withdrawn":
        return APIResponse(success=True, data={
            "operation_id": op.id, "operation_type": "terminal_withdraw", "status": "withdrawn",
            "withdrawn_binding": {"id": binding.id, "status": binding.status},
            "note": "already withdrawn (idempotent)",
        })

    # 版本所有权 CAS：创建操作时持久化的 binding_version 必须未变
    scope = json.loads(op.scope_json) if op.scope_json else {}
    expected_version = scope.get("binding_version", 0)
    other_deployments = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.port_binding_id == binding.id, SdnDeployment.operation_id != op.id)
        .count()
    )
    if binding.version != expected_version or other_deployments > 0 or binding.last_changed_by_operation_id not in (None, op.id):
        return error_response(err.SDN_UNSAFE_WITHDRAWAL, params={"binding_id": binding.id})

    vpc = db.query(SdnVpc).filter(SdnVpc.id == op.vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": op.vpc_id})

    # CR28/CR30: 先建 withdraw attempt/units 拿代际令牌，再原子准入（withdrawing + 绑定 token，与 validating/applying/reconciling 互斥）
    attempt = create_attempt(db, operation_id=op.id, kind="withdraw", owner=str(op.id))
    create_attempt_units(db, attempt.id, ["port-unbind"])
    if not claim_action_admission(db, op.id, from_statuses=list(WITHDRAW_FROM_STATUSES), to_status="withdrawing", active_attempt_id=attempt.id):
        db.rollback()  # 输家：回滚刚建的临时 attempt/units
        db.expire_all()
        refreshed = db.query(SdnOperation).filter(SdnOperation.id == op.id).first()
        if refreshed is not None and refreshed.status in ("validating", "withdrawing", "applying", "reconciling"):
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        return APIResponse(success=True, data={
            "operation_id": op.id, "operation_type": "terminal_withdraw",
            "status": refreshed.status if refreshed is not None else "unknown",
            "withdrawn_binding": {"id": binding.id, "status": binding.status},
            "note": "withdraw admission lost (status changed by concurrent action)",
        })

    # CR11/CR12: 复用本 operation 已持有的 claim（auto_apply=False 创建时已持有），仅补齐缺失；
    # 成功后按完整 scoped keys 释放本操作全部 claims，绝不只释放本轮新增。
    keys = _operation_claims(vpc, op.device_id, binding.if_index)
    try:
        held_keys, acquired = acquire_or_reuse_claims(db, keys, operation_id=op.id, attempt_id=attempt.id)
    except SdnOperationError as e:
        db.rollback()
        return error_response(_err_attr(e), params=e.params)
    db.commit()

    planner = VPCConfigPlanner(H3cV7Adapter())
    units = planner.plan_port_unbind(binding, vpc, dry_run=True)
    deployment = SdnDeployment(
        vpc_id=op.vpc_id, device_id=op.device_id, action="port_unbind", unit="port-unbind",
        port_binding_id=binding.id, planned_config=VPCConfigPlanner.serialize(units),
        status="pending", operation_id=op.id,
    )
    db.add(deployment)
    db.flush()
    # CR13: 把 withdraw attempt 关联到 port_unbind deployment，供 reconcile 按 action 判定
    attempt.deployment_id = deployment.id
    db.commit()

    hooks = AttemptUnitHooks(db, attempt.id, operation_id=op.id)
    executor = SdnDeploymentExecutor()
    try:
        deployment = executor.execute(db, deployment.id, unit_hooks=hooks)
    except SdnDeploymentError:
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()
    db.expire_all()
    deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment.id).first()

    final_state = derive_attempt_status_from_units(db, attempt.id)
    finish_attempt(db, attempt.id, final_state)
    if deployment.status == "success":
        final_op_status = "withdrawn"
    elif deployment.status == "failed":
        final_op_status = "failed"
    else:
        final_op_status = "unknown"

    # CR28/CR30: 条件收尾 CAS——只有 op 仍在 withdrawing phase 且持本代际令牌才写入终态；迟到收尾不覆盖现状、不误释放 claims
    won = finish_action(db, op.id, from_status="withdrawing", final_status=final_op_status, active_attempt_id=attempt.id)
    if won:
        if deployment.status == "success":
            binding.status = "unbound"
            binding.version += 1
            binding.last_changed_by_operation_id = op.id
            # CR12: 确定性成功才释放本 operation 完整 scoped claims；unknown 保留并标 ambiguous
            release_claims(db, held_keys, owner_operation_id=op.id)
        else:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
    db.commit()

    resp_status = final_op_status
    if not won:
        db.refresh(op)
        resp_status = op.status
    note = "只撤回本次新建且无新引用的绑定，保留 VPC/网关/租户与其他端口"
    if not won:
        note = "late completion: status changed by concurrent action"

    return APIResponse(success=True, data={
        "operation_id": op.id, "operation_type": "terminal_withdraw", "status": resp_status,
        "withdrawn_binding": {"id": binding.id, "status": binding.status},
        "deployments": [_deployment_to_response(deployment).model_dump(mode="json")],
        "kept": [f"vpc={vpc.id}({vpc.name})", f"tenant={vpc.tenant_id}", "gateway/other ports"],
        "note": note,
    })


# ── 显式对账 ──

def _token_present(text: str, *, head: str, token: str) -> bool:
    """结构化/语法级匹配：head 后跟空白 + 精确 token，避免裸数字误命中接口名/其他配置。"""
    if not head or token in (None, ""):
        return False
    return re.search(r"\b" + re.escape(head) + r"\s+" + re.escape(str(token)) + r"\b", text) is not None


def _scoped_port_evidence(snapshot: SdnValidationSnapshot, binding: SdnPortBinding, vpc: Optional[SdnVpc]):
    """CR20/CR21: 目标端口的 scoped 正向/负向证据。

    Returns:
        ("present"|"absent"|"insufficient", reason)
    - 命令缺失 / success!=True / error 非空 → insufficient（绝不当配置缺失）。
    - present：本次 binding 的全部标记都在接口回读中精确匹配。
    - absent：命令有效且本次 binding 的全部标记都确认缺失。
    """
    if snapshot is None or binding is None:
        return "insufficient", "no snapshot/binding"
    if not snapshot.snapshot_data:
        return "insufficient", "no snapshot_data"
    try:
        data = json.loads(snapshot.snapshot_data)
    except Exception:
        return "insufficient", "bad snapshot_data"
    cmd = f"display current-configuration interface {binding.interface_name}"
    entry = data.get("commands", {}).get(cmd)
    if not entry:
        return "insufficient", f"missing port command {cmd}"
    if entry.get("success") is not True:
        return "insufficient", "port command not successful"
    if entry.get("error"):
        return "insufficient", f"port command cli error: {entry.get('error')}"
    output = entry.get("output", "") or ""

    # CR26: CLI 错误可能只在 output 里（success=true/error=null），复用 collector 的 display-error 判断。
    if SdnValidationCollector._has_display_error(output):
        return "insufficient", "port command output has display/cli error"

    markers = []
    if binding.service_instance is not None:
        markers.append(("service-instance", str(binding.service_instance)))
        if vpc is not None and getattr(vpc, "vsi_name", None):
            markers.append(("xconnect vsi", str(vpc.vsi_name)))
    if binding.access_vlan is not None:
        markers.append(("port access vlan", str(binding.access_vlan)))

    if not markers:
        return "insufficient", "no binding markers to check"

    present = {f"{h} {t}": _token_present(output, head=h, token=t) for (h, t) in markers}
    any_present = any(present.values())
    all_present = all(present.values())
    if all_present:
        return "present", "all scoped markers present"
    if not any_present:
        return "absent", "all scoped markers absent"
    return "insufficient", "partial scoped markers"


def _reconcile_outcome(db: Session, op: SdnOperation, deployment: Optional[SdnDeployment], binding: Optional[SdnPortBinding], snapshot: SdnValidationSnapshot):
    """CR13/CR20/CR21: 按 deployment action + 目标端口 scoped 证据判定对账结论。

    Returns:
        ("succeeded"|"failed_known"|None, reason)。None = 证据不足，继续 unknown/ambiguous。
    """
    if snapshot is None:
        return None, "no snapshot"
    action = deployment.action if deployment is not None else None
    vpc = db.query(SdnVpc).filter(SdnVpc.id == op.vpc_id).first()

    if action == "port_bind":
        # CR20: 必须目标端口回读成功 + scoped 配置完整；VPC active 单独不证明本次端口已绑定。
        evidence, reason = _scoped_port_evidence(snapshot, binding, vpc)
        if evidence == "present":
            return "succeeded", "port scoped config present"
        if evidence == "absent":
            return None, "port scoped config absent (not yet bound)"
        return None, f"port scoped evidence insufficient: {reason}"

    if action in ("port_unbind", "delete", "gateway_delete"):
        # CR21: 先证命令存在/成功/无 CLI 错误，再证标记缺失；采集失败绝不当作配置缺失。
        evidence, reason = _scoped_port_evidence(snapshot, binding, vpc)
        if evidence == "absent":
            return "succeeded", "port scoped config absent"
        if evidence == "present":
            return "failed_known", "binding still present"
        return None, f"port scoped evidence insufficient: {reason}"

    return None, f"unsupported action {action}"


@router.post("/operations/{operation_id}/reconcile", response_model=APIResponse)
def reconcile_operation(operation_id: int, db: Session = Depends(get_db)):
    """显式对账（CR5/CR13/CR31/CR32/CR35）：按动作与期望设备状态定位原始不确定单元，证明才一致收尾。

    CR31/CR32/CR35：reconcile 参与动作仲裁，并严格区分两种 attempt 身份：
    - `active_attempt`：按 takeover 前 `active_attempt_id` 查询，是需要被标 unknown 的失联动作；
      只修改它及其 started units，并写明 stale takeover 证据。token 不存在、不属于本 operation、
      kind 与 phase 不匹配、或状态非活动态（claimed|running）时保守拒绝，绝不覆盖已确定终态。
    - `effect_attempt`：与设备写副作用关联的 execute/withdraw attempt，用于确定 deployment/action/目标状态；
      其已确定终态不得因 validate/reconcile 崩溃而被改写。
    - applying/withdrawing 失联时 active 与 effect 可为同一对象；validating 失联时二者不同。
    """
    op = db.query(SdnOperation).filter(SdnOperation.id == operation_id).first()
    if not op:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})

    # CR31: withdrawn 是不可逆终态，reconcile 不得改写
    if op.status == "withdrawn":
        return APIResponse(success=True, data={
            "operation_id": op.id, "status": "withdrawn",
            "reconciled": False, "reason": "withdrawn is immutable",
            "uncertain_units": [],
        })

    # effect_attempt：设备写副作用关联的 execute/withdraw attempt（确定 deployment/action/目标状态）
    effect_attempt = (
        db.query(SdnAttempt)
        .filter(SdnAttempt.operation_id == op.id, SdnAttempt.kind.in_(("execute", "withdraw")))
        .order_by(SdnAttempt.id.desc())
        .first()
    )
    uncertain_units = []
    if effect_attempt is not None:
        uncertain_units = (
            db.query(SdnAttemptUnit)
            .filter(SdnAttemptUnit.attempt_id == effect_attempt.id, SdnAttemptUnit.state.in_(("started", "unknown")))
            .all()
        )
    deployment = (
        db.query(SdnDeployment).filter(SdnDeployment.id == effect_attempt.deployment_id).first()
        if effect_attempt and effect_attempt.deployment_id else None
    )
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.created_by_operation_id == op.id).first()
    vpc = db.query(SdnVpc).filter(SdnVpc.id == op.vpc_id).first()

    took_over = False
    active_attempt = None

    # ── CR31/CR32/CR35 动作准入 ──
    if op.status in ("applying", "validating", "withdrawing"):
        # 显式受保护 stale takeover：必须依据持久化租约判定失联。
        expected_kind = ACTIVE_PHASE_EXPECTED_KIND[op.status]
        old_token = op.active_attempt_id
        if old_token is None:
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        # CR35: 不在 Python 层「先读 attempt 再判 kind/status」——kind/status 一致性由
        # claim_stale_takeover 的 EXISTS 子查询与 op 行更新在同一条原子 UPDATE 内证明。
        reconcile_attempt = create_attempt(db, operation_id=op.id, kind="reconcile", owner=str(op.id))
        if not claim_stale_takeover(
            db, op.id, from_status=op.status, old_active_attempt_id=old_token,
            new_active_attempt_id=reconcile_attempt.id, expected_kind=expected_kind,
        ):
            db.rollback()  # 未过期/已被接管/token 无效或错 kind/attempt 已终态：回滚临时 reconcile attempt
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        # CAS 已赢：现在才读 active_attempt（仅供标记 units/证据，kind/status 已由 CAS 证明）
        active_attempt = db.query(SdnAttempt).filter(
            SdnAttempt.id == old_token, SdnAttempt.operation_id == op.id
        ).first()
        if active_attempt is None:
            db.rollback()  # 理论不可达（CAS 已 EXISTS 证明存在），保守兜底
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        # CR35: 条件式失联标记——仅 claimed|running 可被标 unknown；零行说明 attempt 已在 CAS 后
        # 被并发改为终态，回滚本次接管，绝不覆盖终态。
        if not mark_attempt_stale(db, active_attempt.id):
            db.rollback()
            return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
        took_over = True
        # 只把 active token 指向的失联 attempt 及其 started units 标 unknown，并留 stale takeover 证据；
        # effect_attempt（尤其已 succeeded 的 execute）绝不被误改。
        db.refresh(active_attempt)  # 取得 status=unknown 的最新行后再写证据
        active_attempt.evidence_json = json.dumps({"stale_takeover": True, "from_status": op.status}, ensure_ascii=False)
        active_started_units = (
            db.query(SdnAttemptUnit)
            .filter(SdnAttemptUnit.attempt_id == active_attempt.id, SdnAttemptUnit.state == "started")
            .all()
        )
        for u in active_started_units:
            u.state = "unknown"
        db.commit()
    elif op.status == "reconciling":
        # 已有另一个 reconcile 在采集/I/O 前持有 reconciling → 明确 in-progress
        return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
    elif op.status == "unknown":
        # 普通 reconcile：只能从明确 unknown 原子准入
        reconcile_attempt = create_attempt(db, operation_id=op.id, kind="reconcile", owner=str(op.id))
        if not claim_action_admission(db, op.id, from_statuses=["unknown"], to_status="reconciling", active_attempt_id=reconcile_attempt.id):
            db.rollback()
            db.expire_all()
            refreshed = db.query(SdnOperation).filter(SdnOperation.id == op.id).first()
            if refreshed is not None and refreshed.status in ("applying", "validating", "withdrawing", "reconciling"):
                return error_response(err.SDN_OPERATION_IN_PROGRESS, params={"id": op.id})
            return APIResponse(success=True, data={
                "operation_id": op.id,
                "status": refreshed.status if refreshed is not None else "unknown",
                "reconciled": False, "reason": f"not reconcilable in status {refreshed.status if refreshed is not None else 'gone'}",
                "uncertain_units": [],
            })
        db.commit()
    else:
        # 其他稳定/终态：无可对账的不确定单元，不做采集、不改状态
        return APIResponse(success=True, data={
            "operation_id": op.id, "status": op.status,
            "reconciled": False, "reason": f"not reconcilable in status {op.status}",
            "uncertain_units": [],
        })

    collector = SdnValidationCollector()
    # CR24: 显式 reconcile 必须采到待对账目标接口（binding 可能仍是 planned/unbound，不在 active|expanding 内）
    snapshot, coll_err, _ = collector.sync(
        db, op.vpc_id, op.device_id, force=True, min_interval_seconds=0,
        scope_bindings=[binding] if binding is not None else None,
    )
    if coll_err is not None:
        finish_attempt(db, reconcile_attempt.id, "unknown")
        # CR31: 条件收尾到 unknown；迟到/已被接管则不覆盖现状、不误标 claims
        won = finish_action(db, op.id, from_status="reconciling", final_status="unknown", active_attempt_id=reconcile_attempt.id)
        if won:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
        db.commit()
        return error_response(err.SDN_EVIDENCE_INSUFFICIENT, params={"detail": coll_err.get("key")})

    outcome, reason = _reconcile_outcome(db, op, deployment, binding, snapshot)

    if outcome is None:
        # 证据不足：保留 unknown + 标 ambiguous，绝不在证据不足时返回 reconciled=true
        finish_attempt(db, reconcile_attempt.id, "unknown")
        won = finish_action(db, op.id, from_status="reconciling", final_status="unknown", active_attempt_id=reconcile_attempt.id)
        if won:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
        db.commit()
        db.refresh(op)
        return APIResponse(success=True, data={
            "operation_id": op.id, "status": op.status,
            "reconciled": False,
            "reason": reason,
            "uncertain_units": [u.unit_index for u in uncertain_units],
            "evidence": {"snapshot_id": snapshot.id, "validation_result": snapshot.validation_result},
        })

    # 确定性结论：CR19/CR32——只解析 effect_attempt 中真正 uncertain 的 started|unknown units，逐项检查 rowcount；
    # 任何单元未真正解析成功，都不得返回 reconciled=true、不得释放 claims、上层保持 unknown/ambiguous。
    # effect_attempt 已 succeeded/failed_known 时不重放、不降级。
    unit_terminal = "succeeded" if outcome == "succeeded" else "failed_known"
    evidence = {"reconciled": True, "snapshot_id": snapshot.id, "reason": reason}
    all_resolved = True
    if effect_attempt is not None:
        for u in uncertain_units:
            ok = mark_unit_reconciled(db, effect_attempt.id, u.unit_index, state=unit_terminal, evidence=evidence)
            if not ok:
                all_resolved = False
                break

    if effect_attempt is None or not all_resolved:
        finish_attempt(db, reconcile_attempt.id, "unknown")
        won = finish_action(db, op.id, from_status="reconciling", final_status="unknown", active_attempt_id=reconcile_attempt.id)
        if won:
            mark_operation_claims_ambiguous(db, operation_id=op.id)
        db.commit()
        db.refresh(op)
        return APIResponse(success=True, data={
            "operation_id": op.id, "status": op.status,
            "reconciled": False,
            "reason": "unit not resolved" if not all_resolved else reason,
            "uncertain_units": [u.unit_index for u in uncertain_units],
            "evidence": {"snapshot_id": snapshot.id, "validation_result": snapshot.validation_result},
        })

    if outcome == "succeeded":
        if deployment is not None and deployment.action in ("port_unbind", "delete", "gateway_delete"):
            final_op_status = "withdrawn"
        elif deployment is not None and deployment.action == "port_bind":
            final_op_status = "awaiting_validation"
        else:
            final_op_status = "succeeded"
    else:  # failed_known
        final_op_status = "failed"

    # CR31/CR32: 收尾 CAS 同时匹配 phase + 本代际令牌；成功才写 deployment/binding/claims
    won = finish_action(db, op.id, from_status="reconciling", final_status=final_op_status, active_attempt_id=reconcile_attempt.id)
    if won:
        # CR19/CR32: effect_attempt 终态由解析后的 unit 重新推导，不得硬写成功、不得降级已确定终态
        if effect_attempt is not None:
            db.expire_all()
            derived = derive_attempt_status_from_units(db, effect_attempt.id)
            finish_attempt(db, effect_attempt.id, derived)
        if outcome == "succeeded":
            if deployment is not None:
                deployment.status = "success"
                deployment.config_completed_at = datetime.utcnow()
            if deployment is not None and deployment.action in ("port_unbind", "delete", "gateway_delete"):
                if binding is not None:
                    binding.status = "unbound"
            elif deployment is not None and deployment.action == "port_bind":
                if binding is not None:
                    binding.status = "active"
        else:  # failed_known
            if deployment is not None:
                deployment.status = "failed"
        # 仅当所有不确定副作用被明确解析后才释放完整 scoped claims
        keys = _operation_claims(vpc, op.device_id, binding.if_index if binding else 0)
        release_claims(db, keys, owner_operation_id=op.id)
        finish_attempt(db, reconcile_attempt.id, "succeeded")
    else:
        # 迟到收尾：不改业务实体、不释放 claims，只留审计
        finish_attempt(db, reconcile_attempt.id, "unknown")
    db.commit()
    db.refresh(op)
    return APIResponse(success=True, data={
        "operation_id": op.id, "status": op.status,
        "reconciled": won,
        "reason": reason,
        "uncertain_units": [u.unit_index for u in uncertain_units],
        "evidence": {"snapshot_id": snapshot.id, "validation_result": snapshot.validation_result},
        "note": "" if won else "late completion: status changed by concurrent action",
    })


# ── 详情 / 概览（只读）──

@router.get("/operations/{operation_id}", response_model=APIResponse)
def get_operation(operation_id: int, db: Session = Depends(get_db)):
    op = db.query(SdnOperation).filter(SdnOperation.id == operation_id).first()
    if not op:
        return error_response(err.SDN_OPERATION_NOT_FOUND, params={"id": operation_id})
    return APIResponse(success=True, data=_operation_to_dict(db, op))


@router.get("/vpcs/{vpc_id}/access-overview", response_model=APIResponse)
def access_overview(vpc_id: int, db: Session = Depends(get_db)):
    """VPC 接入聚合视图（只读，不触发设备 I/O）。CR18/7.2：带 source/scope/timestamp 的观测明细。"""
    vpc, tenant, vpc_err = _load_vpc_tenant(db, vpc_id)
    if vpc_err:
        return vpc_err
    bindings = db.query(SdnPortBinding).filter(SdnPortBinding.vpc_id == vpc_id).order_by(SdnPortBinding.id.desc()).all()
    ops = db.query(SdnOperation).filter(SdnOperation.vpc_id == vpc_id).order_by(SdnOperation.id.desc()).all()
    snapshots = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc_id).order_by(SdnValidationSnapshot.id.desc()).all()

    # CR18/7.2: 结构化观测明细（本地 ARP/MAC 才计 host_observed，远端 EVPN Type-2 标 remote 不挂本地端口）
    observations = []
    for op in ops:
        if not op.expected_host_ip:
            continue
        binding = next((b for b in bindings if b.operation_id == op.id), None)
        snap = next((s for s in snapshots if s.device_id == op.device_id), None)
        if snap is None:
            continue
        obs, host_observed = _build_host_observations(
            snap.snapshot_data, op.expected_host_ip, binding.interface_name if binding else None
        )
        observations.append({
            "operation_id": op.id,
            "device_id": op.device_id,
            "expected_host_ip": op.expected_host_ip,
            "host_observed": host_observed,
            "collected_at": snap.collection_completed_at or snap.created_at,
            "snapshot_id": snap.id,
            "items": obs,
        })

    return APIResponse(success=True, data={
        "vpc_id": vpc.id,
        "vpc_name": vpc.name,
        "bindings": [_binding_to_response(b, vpc, tenant).model_dump(mode="json") for b in bindings],
        "operations": [{"operation_id": o.id, "status": o.status, "operation_type": o.operation_type, "expected_host_ip": o.expected_host_ip, "updated_at": o.updated_at} for o in ops],
        "latest_validation": [
            {"id": s.id, "device_id": s.device_id, "validation_result": s.validation_result, "collected_at": s.collection_completed_at or s.created_at}
            for s in snapshots[:20]
        ],
        "observations": observations,
    })


# ── 错误映射辅助 ──

def _err_attr(e: SdnOperationError):
    key = e.error_key
    if key.startswith("sdn."):
        name = key.split(".", 1)[1].upper()
        return getattr(err, f"SDN_{name}", err.OPERATION_FAILED)
    return key


def _fallback(e: SdnOperationError) -> Optional[str]:
    return None
