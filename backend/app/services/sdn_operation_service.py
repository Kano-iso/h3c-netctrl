"""S1 共享变更安全服务（资源声明 / 幂等 / 指纹 / 计划 / 身份快照 / deployment CAS）

被 legacy SDN 变更入口与新的 NEXT 接入端点复用，避免在多处 router 重复校验。

关键约束：
- 短事务：claim 获取 + CAS + 幂等在提交后立即结束；设备 I/O 不置于 DB 事务内。
- 锁序是声明式 rank（tenant < vpc < vpc-device < device-port）+ 同 rank 数值升序，
  不是字典序字符串比较。
- claim 互斥覆盖 held 与 ambiguous（部分唯一索引 released_at IS NULL）。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    SdnAttempt,
    SdnAttemptUnit,
    SdnDeployment,
    SdnIdentitySnapshot,
    SdnOperation,
    SdnPlan,
    SdnResourceClaim,
    SdnVpc,
)

logger = logging.getLogger("app")

# 声明式 rank：越小越先获取
_RANK = {"tenant": 0, "vpc": 1, "vpc-device": 2, "device-port": 3}

PLAN_TTL_SECONDS = 600  # 预览默认 10 分钟过期（可被配置覆盖）

# CR31: 失联接管的最小租约（秒）。保守且大于单次网络 I/O 上限；active_started_at 超过此时长
# 才允许 reconcile 抢占同名 phase。不宣称能精确识别进程存活——仅凭持久化时间做保守判断。
STALE_ACTION_LEASE_SECONDS = 300

# CR32/CR35: active phase 唯一映射到可被该 phase 作为代际令牌持有的 attempt kind。
# 用于 stale takeover 的 kind 一致性校验——错误 kind（如 validating 持有 execute token）必须拒绝。
ACTIVE_PHASE_EXPECTED_KIND = {
    "applying": "execute",
    "validating": "validate",
    "withdrawing": "withdraw",
}

# CR35: 仅这些 attempt 状态代表真实活动（可被 stale takeover）；终态/unknown 绝不可被再次降级覆盖。
STALE_TAKEOVERABLE_ATTEMPT_STATUSES = ("claimed", "running")


class SdnOperationError(Exception):
    """S1 业务可处理异常（router 转 APIResponse）"""

    def __init__(self, error_key: str, params: Optional[dict] = None, status_code: int = 422):
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params or {}
        self.status_code = status_code


# ── resource_key 构造 ──


def tenant_key(tenant_id: int) -> str:
    return f"tenant:{tenant_id}"


def vpc_key(vpc_id: int) -> str:
    return f"vpc:{vpc_id}"


def vpc_device_key(vpc_id: int, device_id: int) -> str:
    return f"vpc-device:{vpc_id}:{device_id}"


def device_port_key(device_id: int, if_index: int) -> str:
    return f"device-port:{device_id}:{if_index}"


def _claim_sort_key(resource_key: str):
    """声明式 rank + 数值标识符；rank 先，同 rank 数值升序。"""
    try:
        if resource_key.startswith("tenant:"):
            return (_RANK["tenant"], int(resource_key.split(":", 1)[1]), 0, 0)
        if resource_key.startswith("vpc-device:"):
            _, vid, did = resource_key.split(":")
            return (_RANK["vpc-device"], int(vid), int(did), 0)
        if resource_key.startswith("vpc:"):
            return (_RANK["vpc"], int(resource_key.split(":", 1)[1]), 0, 0)
        if resource_key.startswith("device-port:"):
            _, did, ifidx = resource_key.split(":")
            return (_RANK["device-port"], int(did), 0, int(ifidx))
    except (ValueError, IndexError):
        pass
    return (99, 0, 0, 0)


def ordered_claim_keys(keys: Iterable[str]) -> list[str]:
    """按声明式 rank 排序（非字典序）。"""
    return sorted(set(keys), key=_claim_sort_key)


# ── 资源声明 ──


def acquire_claims(
    db: Session,
    keys: Iterable[str],
    *,
    operation_id: Optional[int] = None,
    attempt_id: Optional[int] = None,
) -> list[str]:
    """按 rank 序获取 claim；任一冲突抛 SdnOperationError（不自动释放已获取项由调用方回滚）。

    用部分唯一索引 (resource_key) WHERE released_at IS NULL 互斥，覆盖 held 与 ambiguous。
    """
    ordered = ordered_claim_keys(keys)
    now = datetime.utcnow()
    for key in ordered:
        claim = SdnResourceClaim(
            resource_key=key,
            owner_operation_id=operation_id,
            owner_attempt_id=attempt_id,
            status="held",
            claimed_at=now,
        )
        db.add(claim)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise SdnOperationError(
                "sdn.resource_busy",
                params={"resource_key": key},
                status_code=409,
            )
    return ordered


def release_claims(db: Session, keys: Iterable[str], *, owner_attempt_id: Optional[int] = None, owner_operation_id: Optional[int] = None) -> int:
    """显式 resolution 后释放 claim（released_at 置非空）。

    CR4: 必须给定 owner 令牌，只释放属于该 owner 的 claim，绝不释放他人 claim。
    返回实际释放条数。
    """
    now = datetime.utcnow()
    if owner_attempt_id is None and owner_operation_id is None:
        raise ValueError("release_claims requires an owner token (owner_attempt_id or owner_operation_id)")
    released = 0
    for key in keys:
        q = db.query(SdnResourceClaim).filter(
            SdnResourceClaim.resource_key == key,
            SdnResourceClaim.released_at.is_(None),
        )
        if owner_attempt_id is not None:
            q = q.filter(SdnResourceClaim.owner_attempt_id == owner_attempt_id)
        if owner_operation_id is not None:
            q = q.filter(SdnResourceClaim.owner_operation_id == owner_operation_id)
        for claim in q.all():
            claim.status = "released"
            claim.released_at = now
            released += 1
    db.flush()
    return released


def mark_claims_ambiguous(db: Session, *, attempt_id: int) -> None:
    """TTL 过期后把仍持有的 claim 标 ambiguous（released_at 仍 NULL，仍独占）。"""
    for claim in (
        db.query(SdnResourceClaim)
        .filter(SdnResourceClaim.owner_attempt_id == attempt_id, SdnResourceClaim.released_at.is_(None))
        .all()
    ):
        claim.status = "ambiguous"
    db.flush()


def mark_operation_claims_ambiguous(db: Session, *, operation_id: int) -> None:
    """CR12: 把本 operation 仍持有的全部 claim 标 ambiguous（按 operation 归属，不按具体 attempt）。"""
    for claim in (
        db.query(SdnResourceClaim)
        .filter(SdnResourceClaim.owner_operation_id == operation_id, SdnResourceClaim.released_at.is_(None))
        .all()
    ):
        claim.status = "ambiguous"
    db.flush()


def acquire_or_reuse_claims(
    db: Session,
    keys: Iterable[str],
    *,
    operation_id: int,
    attempt_id: Optional[int] = None,
) -> tuple[list[str], list[str]]:
    """CR11: owner-aware claim 复用——本 operation 已持有的 claim 直接复用，仅补齐缺失。

    绝不对本 operation 自己的 claim 重新认领（那会因部分唯一索引自冲突）。
    Returns:
        (held_keys, acquired_keys)：held = 本 operation 现持有的全部 key；
        acquired = 本次新认领的 key（供调用方决定后续释放范围）。
    """
    ordered = ordered_claim_keys(keys)
    held_existing = {
        c.resource_key
        for c in db.query(SdnResourceClaim)
        .filter(
            SdnResourceClaim.resource_key.in_(ordered),
            SdnResourceClaim.released_at.is_(None),
            SdnResourceClaim.owner_operation_id == operation_id,
        )
        .all()
    }
    missing = [k for k in ordered if k not in held_existing]
    acquired = acquire_claims(db, missing, operation_id=operation_id, attempt_id=attempt_id) if missing else []
    held = ordered  # 复用 + 新认领 = 完整 scoped keys
    return held, acquired


def claim_action_admission(
    db: Session, operation_id: int, *, from_statuses: list, to_status: str, active_attempt_id: int
) -> bool:
    """CR27/CR28/CR30: 原子动作准入 CAS——单行 UPDATE 把 op.status 从 from_statuses 之一置为 to_status，
    同时绑定当前动作代际令牌 active_attempt_id + active_started_at。

    只有 rowcount==1 的请求赢，赢者才可进入 collector/ping 或设备写 I/O。
    输家回查 op.status 即可区分 in-progress（active phase）与已到终态。
    """
    n = (
        db.query(SdnOperation)
        .filter(SdnOperation.id == operation_id, SdnOperation.status.in_(from_statuses))
        .update(
            {
                "status": to_status,
                "active_attempt_id": active_attempt_id,
                "active_started_at": datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return n == 1


def finish_action(
    db: Session, operation_id: int, *, from_status: str, final_status: str, active_attempt_id: int
) -> bool:
    """CR28/CR30: 条件收尾 CAS——同时匹配 operation_id + phase + active_attempt_id 才写入 final_status，
    成功后原子清空 active_attempt_id/active_started_at。

    返回 False 表示状态已被并发动作改变（迟到收尾或代际已被接管）；调用方 SHALL NOT 覆盖现状，
    SHALL NOT 释放/误标另一动作仍需的 claims，并留下可诊断证据或明确错误。
    """
    n = (
        db.query(SdnOperation)
        .filter(
            SdnOperation.id == operation_id,
            SdnOperation.status == from_status,
            SdnOperation.active_attempt_id == active_attempt_id,
        )
        .update(
            {"status": final_status, "active_attempt_id": None, "active_started_at": None},
            synchronize_session=False,
        )
    )
    db.flush()
    return n == 1


def claim_stale_takeover(
    db: Session,
    operation_id: int,
    *,
    from_status: str,
    old_active_attempt_id: int,
    new_active_attempt_id: int,
    expected_kind: str,
) -> bool:
    """CR31/CR35: 显式且受保护的失联接管 CAS（单条原子 UPDATE）。

    仅当同时满足以下全部条件才抢占为 reconciling 并绑定新 token：
    - op 仍处于 from_status（active phase）
    - op.active_attempt_id == old token
    - op.active_started_at 早于最小租约（NULL 无法证明失联 → 拒绝）
    - 该 old token 指向的 attempt 仍属于本 operation、kind == expected_kind 且
      状态仍可接管（claimed|running，见 STALE_TAKEOVERABLE_ATTEMPT_STATUSES）

    EXISTS 子查询与 op 行更新在同一个 UPDATE 语句内原子求值，消除「先读后改」的 TOCTOU：
    即使 Python 层先前读到的 attempt 仍是活动态，只要在 CAS 执行前被并发改为终态，EXISTS
    即不成立 → rowcount==0 → 保守拒绝，绝不覆盖终态 attempt。
    """
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_ACTION_LEASE_SECONDS)
    active_attempt_ok = exists(
        select(1).where(
            SdnAttempt.id == old_active_attempt_id,
            SdnAttempt.operation_id == operation_id,
            SdnAttempt.kind == expected_kind,
            SdnAttempt.status.in_(STALE_TAKEOVERABLE_ATTEMPT_STATUSES),
        )
    )
    n = (
        db.query(SdnOperation)
        .filter(
            SdnOperation.id == operation_id,
            SdnOperation.status == from_status,
            SdnOperation.active_attempt_id == old_active_attempt_id,
            SdnOperation.active_started_at < cutoff,
            active_attempt_ok,
        )
        .update(
            {
                "status": "reconciling",
                "active_attempt_id": new_active_attempt_id,
                "active_started_at": datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return n == 1


def mark_attempt_stale(
    db: Session,
    attempt_id: int,
    *,
    from_statuses=STALE_TAKEOVERABLE_ATTEMPT_STATUSES,
) -> bool:
    """CR35: 条件式失联标记——仅当 attempt 仍处于可接管活动态（claimed|running）才标 unknown。

    返回 rowcount==1。零行表示 attempt 已被并发改为终态；调用方必须回滚接管或保守收尾，
    绝不能无条件覆盖已确定终态、不能宣称接管成功。
    """
    now = datetime.utcnow()
    n = (
        db.query(SdnAttempt)
        .filter(SdnAttempt.id == attempt_id, SdnAttempt.status.in_(from_statuses))
        .update({"status": "unknown", "completed_at": now}, synchronize_session=False)
    )
    db.flush()
    return n == 1


# ── 幂等 / 指纹 ──


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_access_fingerprint(
    *,
    tenant_id: int,
    vpc_id: int,
    device_id: int,
    if_index: int,
    interface_name: str,
    access_vlan: Optional[int],
    service_instance: Optional[int],
    expected_host_ip: Optional[str],
    auto_apply: bool,
    mode: Optional[str],
) -> str:
    """请求指纹（幂等用）：规范化字段名排序、去时间戳。"""
    payload = {
        "tenant_id": tenant_id,
        "vpc_id": vpc_id,
        "device_id": device_id,
        "if_index": if_index,
        "interface_name": interface_name,
        "access_vlan": access_vlan,
        "service_instance": service_instance,
        "expected_host_ip": expected_host_ip,
        "auto_apply": auto_apply,
        "mode": mode,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_access_request(
    *,
    tenant_id: int,
    vpc_id: int,
    device_id: int,
    if_index: int,
    interface_name: str,
    access_vlan: Optional[int],
    service_instance: Optional[int],
    expected_host_ip: Optional[str],
    mode: Optional[str],
) -> dict:
    """归一化接入请求语义（计划 scope/哈希共用的唯一事实）。

    注意：不含 auto_apply（auto_apply 是执行方式而非"接入什么"，不进计划语义/scope）。
    """
    return {
        "tenant_id": tenant_id,
        "vpc_id": vpc_id,
        "device_id": device_id,
        "if_index": if_index,
        "interface_name": interface_name,
        "access_vlan": access_vlan,
        "service_instance": service_instance,
        "expected_host_ip": expected_host_ip,
        "mode": mode,
    }


def compute_semantic_hash(*, vpc_version: int, sdn_role: Optional[str], protected: list, port_free: bool, predeploy_ready: bool, request: dict) -> str:
    """计划语义哈希（stale 检测用）= 完整归一化请求语义 + 服务端状态/依赖版本（CR6）。"""
    payload = {
        "request": request,
        "state": {
            "vpc_version": vpc_version,
            "sdn_role": sdn_role,
            "protected_interfaces": sorted(protected),
            "port_free": port_free,
            "predeploy_ready": predeploy_ready,
        },
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ── 计划 ──


def get_plan(db: Session, plan_id: str) -> SdnPlan:
    plan = db.query(SdnPlan).filter(SdnPlan.plan_id == plan_id).first()
    if not plan:
        raise SdnOperationError("sdn.plan_not_found", params={"plan_id": plan_id}, status_code=404)
    return plan


def consume_plan(db: Session, plan_id: str) -> SdnPlan:
    """原子消费 plan：valid → consumed；并发只有一个成功。

    Returns:
        SdnPlan（已消费）。若已被并发消费，抛 sdn.plan_consumed；过期抛 sdn.plan_expired。
    """
    plan = get_plan(db, plan_id)
    if plan.status == "expired" or plan.expires_at <= datetime.utcnow():
        plan.status = "expired"
        db.flush()
        raise SdnOperationError("sdn.plan_expired", params={"plan_id": plan_id}, status_code=409)
    if plan.status != "valid":
        raise SdnOperationError("sdn.plan_consumed", params={"plan_id": plan_id}, status_code=409)
    n = (
        db.query(SdnPlan)
        .filter(SdnPlan.plan_id == plan_id, SdnPlan.status == "valid")
        .update({"status": "consumed"}, synchronize_session=False)
    )
    if n == 0:
        raise SdnOperationError("sdn.plan_consumed", params={"plan_id": plan_id}, status_code=409)
    db.flush()
    db.refresh(plan)
    return plan


def create_plan(
    db: Session,
    *,
    plan_id: str,
    semantic_hash: str,
    version_snapshot_json: str,
    scope_json: str,
    ttl_seconds: int = PLAN_TTL_SECONDS,
) -> SdnPlan:
    plan = SdnPlan(
        plan_id=plan_id,
        semantic_hash=semantic_hash,
        version_snapshot_json=version_snapshot_json,
        scope_json=scope_json,
        status="valid",
        expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
    )
    db.add(plan)
    db.flush()
    db.refresh(plan)
    return plan


# ── 操作 / 幂等 ──


def resolve_operation(
    db: Session,
    *,
    idempotency_key: str,
    fingerprint: str,
    operation_type: str,
    tenant_id: int,
    vpc_id: int,
    device_id: int,
    plan_id: Optional[str],
    expected_host_ip: Optional[str],
    request_payload_json: Optional[str],
    scope_json: str,
) -> tuple[SdnOperation, bool]:
    """幂等创建 operation。

    Returns:
        (operation, created)：created=True 表示新插入；False 表示命中已存在（duplicate）。
    """
    existing = db.query(SdnOperation).filter(SdnOperation.idempotency_key == idempotency_key).first()
    if existing is not None:
        # 鉴权/scope 校验在调用方已完成；这里做 scope + 指纹比对
        if (
            existing.tenant_id != tenant_id
            or existing.vpc_id != vpc_id
            or existing.device_id != device_id
            or existing.operation_type != operation_type
        ):
            # 不可访问 scope → 按不存在处理（调用方转 404），不泄漏
            raise SdnOperationError("sdn.idempotency_not_found", params={}, status_code=404)
        if existing.fingerprint != fingerprint:
            raise SdnOperationError("sdn.idempotency_conflict", params={"idempotency_key": idempotency_key}, status_code=409)
        return existing, False

    op = SdnOperation(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        operation_type=operation_type,
        tenant_id=tenant_id,
        vpc_id=vpc_id,
        device_id=device_id,
        plan_id=plan_id,
        expected_host_ip=expected_host_ip,
        request_payload_json=request_payload_json,
        scope_json=scope_json,
        status="planned",
    )
    db.add(op)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # 并发 INSERT：另一个事务已插入同 key → 回查
        existing = db.query(SdnOperation).filter(SdnOperation.idempotency_key == idempotency_key).first()
        if existing is None:
            raise SdnOperationError("sdn.idempotency_conflict", params={"idempotency_key": idempotency_key}, status_code=409)
        if (
            existing.tenant_id != tenant_id
            or existing.vpc_id != vpc_id
            or existing.device_id != device_id
            or existing.operation_type != operation_type
        ):
            raise SdnOperationError("sdn.idempotency_not_found", params={}, status_code=404)
        if existing.fingerprint != fingerprint:
            raise SdnOperationError("sdn.idempotency_conflict", params={"idempotency_key": idempotency_key}, status_code=409)
        return existing, False
    db.refresh(op)
    return op, True


# ── deployment CAS ──


def claim_deployment(db: Session, deployment_id: int, *, attempt_id: int, operation_id: Optional[int] = None) -> SdnDeployment:
    """唯一原子认领 deployment：pending → running（CR1 单一 CAS 来源）。

    设置 claimed_at/config_started_at/归属；调用方负责随后 commit（短事务）。
    """
    now = datetime.utcnow()
    n = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.id == deployment_id, SdnDeployment.status == "pending")
        .update(
            {
                "status": "running",
                "claimed_at": now,
                "config_started_at": now,
                "claimed_by_attempt_id": attempt_id,
                "operation_id": operation_id,
            },
            synchronize_session=False,
        )
    )
    if n == 0:
        dep = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
        status = dep.status if dep else "missing"
        raise SdnOperationError(
            "sdn.deployment_not_pending",
            params={"id": deployment_id, "status": status},
            status_code=409,
        )
    db.flush()
    dep = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
    if dep is not None:
        db.refresh(dep)
    return dep


# ── 尝试 / 单元 ──


def create_attempt(
    db: Session,
    *,
    operation_id: int,
    kind: str,
    owner: Optional[str] = None,
    deployment_id: Optional[int] = None,
    scope_json: Optional[str] = None,
) -> SdnAttempt:
    now = datetime.utcnow()
    attempt = SdnAttempt(
        operation_id=operation_id,
        deployment_id=deployment_id,
        kind=kind,
        status="claimed",
        owner=owner,
        claimed_at=now,
        scope_json=scope_json,
    )
    db.add(attempt)
    db.flush()
    db.refresh(attempt)
    return attempt


def create_attempt_units(db: Session, attempt_id: int, unit_names: list[str]) -> None:
    for idx, name in enumerate(unit_names):
        db.add(SdnAttemptUnit(attempt_id=attempt_id, unit_index=idx, unit_name=name, state="not_started"))
    db.flush()


def ensure_legacy_apply_operation(db: Session, deployment: SdnDeployment) -> int:
    """CR2: legacy `/deployments/{id}/apply` 复用同一 attempt/unit 追踪。

    无 operation_id 时创建系统 operation；有则直接建 execute attempt + units。
    CR14: 从 planned_config 解析真实 unit 列表（而非单一 legacy-apply），
    保证 executor 逐单元写入与 attempt_units 一一对应。
    返回 attempt.id（供 AttemptUnitHooks 使用）。
    """
    operation_id = deployment.operation_id
    if operation_id is None:
        vpc = db.query(SdnVpc).filter(SdnVpc.id == deployment.vpc_id).first()
        op = SdnOperation(
            idempotency_key=f"legacy-apply-{deployment.id}",
            fingerprint="legacy-apply",
            operation_type="legacy_apply",
            tenant_id=vpc.tenant_id if vpc else 0,
            vpc_id=deployment.vpc_id,
            device_id=deployment.device_id,
            status="applied",
        )
        db.add(op)
        db.flush()
        operation_id = op.id
        deployment.operation_id = op.id
        db.flush()
    attempt = create_attempt(
        db, operation_id=operation_id, kind="execute", owner=f"legacy-{deployment.id}", deployment_id=deployment.id
    )
    # CR14: 真实 unit 列表（与 executor._parse_planned_config 同一解析器），缺省回退 legacy-apply
    unit_names = ["legacy-apply"]
    if deployment.planned_config:
        try:
            from app.services.sdn_device_adapter import deserialize_template_units
            parsed = deserialize_template_units(deployment.planned_config)
            if parsed:
                unit_names = [u.name for u in parsed]
        except Exception:
            unit_names = ["legacy-apply"]
    create_attempt_units(db, attempt.id, unit_names)
    db.commit()
    return attempt.id


def mark_unit_started(db: Session, attempt_id: int, unit_index: int) -> bool:
    """设备 I/O 前把单元置 started；若已非 not_started，返回 False（阻塞）。"""
    n = (
        db.query(SdnAttemptUnit)
        .filter(SdnAttemptUnit.attempt_id == attempt_id, SdnAttemptUnit.unit_index == unit_index, SdnAttemptUnit.state == "not_started")
        .update({"state": "started", "started_at": datetime.utcnow()}, synchronize_session=False)
    )
    db.flush()
    return n == 1


def mark_unit_done(db: Session, attempt_id: int, unit_index: int, *, state: str, evidence: Optional[dict] = None) -> bool:
    """设备 I/O 后落终态。仅允许 started → 终态 的 CAS，绝不覆盖已终态证据（CR2）。"""
    if state not in ("succeeded", "failed_known", "unknown"):
        raise ValueError(f"illegal unit terminal state: {state}")
    n = (
        db.query(SdnAttemptUnit)
        .filter(
            SdnAttemptUnit.attempt_id == attempt_id,
            SdnAttemptUnit.unit_index == unit_index,
            SdnAttemptUnit.state == "started",
        )
        .update(
            {"state": state, "evidence_json": json.dumps(evidence) if evidence is not None else None, "completed_at": datetime.utcnow()},
            synchronize_session=False,
        )
    )
    db.flush()
    return n == 1


def mark_unit_reconciled(db: Session, attempt_id: int, unit_index: int, *, state: str, evidence: Optional[dict] = None) -> bool:
    """CR19: reconcile 专用受限解析——允许 started|unknown → succeeded|failed_known，写对账证据。

    与 mark_unit_done 不同：不覆盖已 succeeded/failed_known 的确定性终态（CR2 证据不可变），
    只把不确定单元（started/unknown）解析为确定终态。返回 rowcount==1 表示真正解析成功。
    """
    if state not in ("succeeded", "failed_known"):
        raise ValueError(f"illegal reconcile terminal state: {state}")
    n = (
        db.query(SdnAttemptUnit)
        .filter(
            SdnAttemptUnit.attempt_id == attempt_id,
            SdnAttemptUnit.unit_index == unit_index,
            SdnAttemptUnit.state.in_(("started", "unknown")),
        )
        .update(
            {"state": state, "evidence_json": json.dumps(evidence) if evidence is not None else None, "completed_at": datetime.utcnow()},
            synchronize_session=False,
        )
    )
    db.flush()
    return n == 1


def finish_attempt(db: Session, attempt_id: int, status: str) -> None:
    now = datetime.utcnow()
    db.query(SdnAttempt).filter(SdnAttempt.id == attempt_id).update(
        {"status": status, "completed_at": now}, synchronize_session=False
    )
    db.flush()


def derive_attempt_status_from_units(db: Session, attempt_id: int) -> str:
    """由持久化单元推导 attempt 终态（CR2）：任一 unknown→unknown；有 failed_known 且无 unknown→failed；
    全 succeeded→succeeded；存在未终态（started/not_started）→unknown。"""
    units = (
        db.query(SdnAttemptUnit)
        .filter(SdnAttemptUnit.attempt_id == attempt_id)
        .order_by(SdnAttemptUnit.unit_index)
        .all()
    )
    if not units:
        return "unknown"
    terminal = {"succeeded", "failed_known", "unknown"}
    states = [u.state for u in units]
    if any(s not in terminal for s in states):
        return "unknown"
    if any(s == "unknown" for s in states):
        return "unknown"
    if any(s == "failed_known" for s in states):
        return "failed"
    return "succeeded"


class AttemptUnitHooks:
    """逐单元执行证据回调（CR2），供 executor 经 unit_hooks 调用。

    before_unit/after_unit_* 各自短事务 commit，使 started 持久可见后再 I/O、
    I/O 后终态持久可见。CR14: before_unit 返回是否 CAS 成功（False 表示单元
    已非 not_started，executor 必须阻止 I/O）；after_unit_* 返回是否落库成功，
    零行更新不得静默忽略。
    """

    def __init__(self, db: Session, attempt_id: int, operation_id: Optional[int] = None):
        self.db = db
        self.attempt_id = attempt_id
        self.operation_id = operation_id

    def before_unit(self, index: int, name: str) -> bool:
        # CR18/4.2: 依赖重放——index 之前的单元必须全部 succeeded，否则阻断（不得越级执行）
        prior = (
            self.db.query(SdnAttemptUnit)
            .filter(SdnAttemptUnit.attempt_id == self.attempt_id, SdnAttemptUnit.unit_index < index)
            .all()
        )
        if any(u.state != "succeeded" for u in prior):
            return False
        ok = mark_unit_started(self.db, self.attempt_id, index)
        self.db.commit()
        return ok

    def after_unit_success(self, index: int, name: str) -> bool:
        ok = mark_unit_done(self.db, self.attempt_id, index, state="succeeded")
        self.db.commit()
        return ok

    def after_unit_failure(self, index: int, name: str, definitive: bool, error: str) -> bool:
        ok = mark_unit_done(
            self.db, self.attempt_id, index,
            state="failed_known" if definitive else "unknown",
            evidence={"error": error, "definitive": definitive},
        )
        self.db.commit()
        return ok


# ── 身份快照 ──


def snapshot_identity(db: Session, *, entity_kind: str, entity_id: int, identity: dict, deleted: bool = False) -> None:
    db.add(
        SdnIdentitySnapshot(
            entity_kind=entity_kind,
            entity_id=entity_id,
            identity_json=json.dumps(identity, ensure_ascii=False, default=str),
            deleted_at=datetime.utcnow() if deleted else None,
        )
    )
    db.flush()
