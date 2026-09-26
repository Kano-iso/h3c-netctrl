"""S3-004 受控修复提案（只生成提案，绝不执行设备配置，NEXT/S3 后端切片）。

把 S3 从"发现 confirmed_drift + inspect_drift 建议"推进到"可审计的修复提案"：
- 复用 S3-001 评估与 state-projection（build_projection_payload + evaluate_assurance）与
  VPCConfigPlanner dry-run，不另造第二套 VPC 引擎；
- 提案绑定当时的保障 run、VPC version、目标 Leaf 与最新证据，为下一轮人工确认执行建立
  防陈旧边界；action 固定 redeploy_vpc_on_device；
- 全路径零设备 I/O：不调用 executor/collector/Netconf/SSH，不创建
  deployment/operation/binding/claim，不改 vpc.version；不实现 confirm/apply；
- summary_json 只存语义单元名/影响范围（planner dry-run 提取 name/description），
  绝不含原始 CLI、凭据、planned_config。
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Device,
    SdnAssuranceRun,
    SdnDeployment,
    SdnRemediationProposal,
    SdnScopeException,
    SdnTenant,
    SdnVpc,
)
from app.services.vpc_config_planner import VPCConfigPlanner
from app.services.sdn_device_adapter import H3cV7Adapter

logger = logging.getLogger(__name__)

ACTION = "redeploy_vpc_on_device"
CATEGORY = "confirmed_drift"

STATUS_PROPOSED = "proposed"
STATUS_STALE = "stale"
STATUS_CANCELLED = "cancelled"

# 影响范围：planner dry-run 对单台 Leaf 重新应用 VPC 语义单元；保留项绝不删除。
_PRESERVED = ["tenant", "vpc", "other_leaves", "port_bindings"]

CREATE_CREATED = "created"
CREATE_DUPLICATE = "duplicate"


class ProposalRejected(Exception):
    """准入失败：携带 error_key 与 params（路由映射为 APIResponse 错误，HTTP 200 + success false）。"""

    def __init__(self, error_key, params=None):
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params or {}


def _load_run(db, vpc_id: int, run_id: int) -> Optional[SdnAssuranceRun]:
    run = db.query(SdnAssuranceRun).filter(SdnAssuranceRun.id == run_id).first()
    if run is None or run.vpc_id != vpc_id or run.status != "completed":
        return None
    return run


def _find_item(run: SdnAssuranceRun, item_key: str, vpc_id: int) -> Optional[dict]:
    """从 run 白名单 items 取真实 item；非 blocking confirmed_drift 一律不可提案。"""
    try:
        items = json.loads(run.items_json or "[]")
    except (TypeError, ValueError):
        return None
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("key") == item_key and item.get("vpc_id") == vpc_id:
            if item.get("severity") == "blocking" and item.get("category") == CATEGORY:
                return item
    return None


def _evidence_snapshot_id(item: dict) -> Optional[int]:
    """从 run item 的 source_refs 提取证据 snapshot id（脱敏引用，绝不含 CLI/凭据）。"""
    for ref in item.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        snapshot = ref.get("snapshot")
        if isinstance(snapshot, dict):
            return snapshot.get("snapshot_id")
    return None


def _run_facts_vpc_version(run: SdnAssuranceRun) -> Optional[int]:
    try:
        facts = json.loads(run.facts_json or "{}")
    except (TypeError, ValueError):
        return None
    return facts.get("vpc_version") if isinstance(facts, dict) else None


def _has_active_maintenance_exception(db, vpc_id: int, device_id: int, now: datetime) -> bool:
    """有 active maintenance_pause 例外 → 拒绝提案（维护中的 Leaf 不生成可用提案）。"""
    from app.routers.sdn import _serialize_scope_exception

    exc = (
        db.query(SdnScopeException)
        .filter(
            SdnScopeException.vpc_id == vpc_id,
            SdnScopeException.device_id == device_id,
        )
        .first()
    )
    if exc is None or exc.exception_type != "maintenance_pause":
        return False
    try:
        return _serialize_scope_exception(exc, now=now).get("state") == "active"
    except Exception:  # 畸形例外保守视为活跃（拒绝，绝不生成可用提案）
        return True


def _fingerprint(*, vpc_id, run_id, item_key, device_id, action, category,
                 vpc_version_at_create, policy_version, evidence_snapshot_id) -> str:
    payload = {
        "vpc_id": vpc_id, "run_id": run_id, "item_key": item_key, "device_id": device_id,
        "action": action, "category": category, "vpc_version_at_create": vpc_version_at_create,
        "policy_version": policy_version, "evidence_snapshot_id": evidence_snapshot_id,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _impact_summary(vpc, tenant, device: Device) -> dict:
    """planner dry-run 计算语义单元与影响范围；只取 name/description，绝不保存 CLI/XML。"""
    planner = VPCConfigPlanner(H3cV7Adapter())
    units = planner.plan_vpc_create(vpc, tenant, dry_run=True)
    return {
        "action": ACTION,
        "device_id": device.id,
        "device_name": device.name,
        "units": [{"name": u.name, "description": u.description} for u in units],
        "preserved": list(_PRESERVED),
        "executed": False,
    }


def create_proposal(
    db: Session, *, vpc_id: int, run_id: int, item_key: str, now: Optional[datetime] = None
):
    """创建提案（准入全过才生成 proposed；失败抛 ProposalRejected 或返回重复结果）。

    返回 {"result": CREATE_CREATED|CREATE_DUPLICATE, "proposal": SdnRemediationProposal}。
    幂等：同 (run_id, item_key) 已存在 → 返回既有行（CREATE_DUPLICATE），并发由唯一约束兜底。
    """
    from app.config import settings
    from app.routers.sdn import (
        _is_sdn_fabric_member,
        _latest_snapshot,
        build_projection_payload,
    )
    from app.services.sdn_assurance import evaluate_assurance
    from app.i18n_keys import err

    now = now or datetime.utcnow()

    run = _load_run(db, vpc_id, run_id)
    if run is None:
        raise ProposalRejected(err.SDN_REMEDIATION_RUN_NOT_FOUND, {"run_id": run_id})
    item = _find_item(run, item_key, vpc_id)
    if item is None:
        raise ProposalRejected(err.SDN_REMEDIATION_ITEM_NOT_FOUND, {"item_key": item_key})
    device_id = item.get("device_id")
    if not isinstance(device_id, int):
        raise ProposalRejected(err.SDN_REMEDIATION_INVALID_ITEM, {"item_key": item_key})

    # Idempotency precedes freshness admission. A retry must resolve to the original
    # proposal even when its evidence has since become stale; get_proposal applies the
    # conservative proposed -> stale CAS before returning it.
    existing = (
        db.query(SdnRemediationProposal)
        .filter(
            SdnRemediationProposal.run_id == run_id,
            SdnRemediationProposal.item_key == item_key,
        )
        .first()
    )
    if existing is not None:
        existing = get_proposal(db, vpc_id=vpc_id, proposal_id=existing.id, now=now)
        return {"result": CREATE_DUPLICATE, "proposal": existing}

    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if vpc is None:
        raise ProposalRejected(err.SDN_VPC_NOT_FOUND, {"id": vpc_id})
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None or not _is_sdn_fabric_member(device):
        raise ProposalRejected(err.SDN_REMEDIATION_DEVICE_NOT_LEAF, {"device_id": device_id})

    # VPC/run/item 归属一致：device 必须是该 VPC 的目标 Leaf（deployment 存在）
    deployment = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.vpc_id == vpc_id, SdnDeployment.device_id == device_id)
        .first()
    )
    if deployment is None:
        raise ProposalRejected(err.SDN_REMEDIATION_OWNERSHIP_MISMATCH, {"device_id": device_id})

    run_vpc_version = _run_facts_vpc_version(run)
    if run_vpc_version is None or vpc.version != run_vpc_version:
        raise ProposalRejected(err.SDN_REMEDIATION_STALE, {"reason": "vpc_version"})

    # 重新读取当前 projection：目标仍 confirmed_drift blocking 且证据仍指向同一快照
    projection = build_projection_payload(db, vpc_id)
    if projection is None:
        raise ProposalRejected(err.SDN_REMEDIATION_STALE, {"reason": "projection"})
    result = evaluate_assurance(projection, now=now)
    current_item = next(
        (
            i for i in result.get("items") or []
            if i.get("key") == item_key and i.get("device_id") == device_id
        ),
        None,
    )
    if current_item is None or current_item.get("category") != CATEGORY or current_item.get("severity") != "blocking":
        raise ProposalRejected(err.SDN_REMEDIATION_STALE, {"reason": "classification"})

    evidence_snapshot_id = _evidence_snapshot_id(item)
    latest = _latest_snapshot(db, vpc_id, device_id)
    if evidence_snapshot_id is None or latest is None or latest.id != evidence_snapshot_id:
        raise ProposalRejected(err.SDN_REMEDIATION_STALE, {"reason": "evidence"})

    if _has_active_maintenance_exception(db, vpc_id, device_id, now):
        raise ProposalRejected(err.SDN_REMEDIATION_ACTIVE_MAINTENANCE_EXCEPTION, {"device_id": device_id})

    tenant = db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).first()
    summary = _impact_summary(vpc, tenant, device)
    expires_at = now + timedelta(seconds=float(settings.REMEDIATION_PROPOSAL_TTL_SECONDS))
    fingerprint = _fingerprint(
        vpc_id=vpc_id, run_id=run_id, item_key=item_key, device_id=device_id,
        action=ACTION, category=CATEGORY, vpc_version_at_create=vpc.version,
        policy_version=run.policy_version, evidence_snapshot_id=evidence_snapshot_id,
    )

    # 幂等：先查（同 run+item），并发由唯一约束兜底
    existing = (
        db.query(SdnRemediationProposal)
        .filter(
            SdnRemediationProposal.run_id == run_id,
            SdnRemediationProposal.item_key == item_key,
        )
        .first()
    )
    if existing is not None:
        return {"result": CREATE_DUPLICATE, "proposal": existing}

    row = SdnRemediationProposal(
        vpc_id=vpc_id,
        run_id=run_id,
        item_key=item_key,
        device_id=device_id,
        action=ACTION,
        category=CATEGORY,
        vpc_version_at_create=vpc.version,
        policy_version=run.policy_version,
        evidence_snapshot_id=evidence_snapshot_id,
        status=STATUS_PROPOSED,
        expires_at=expires_at,
        fingerprint=fingerprint,
        summary_json=json.dumps(summary, ensure_ascii=False),
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"result": CREATE_CREATED, "proposal": row}
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(SdnRemediationProposal)
            .filter(
                SdnRemediationProposal.run_id == run_id,
                SdnRemediationProposal.item_key == item_key,
            )
            .first()
        )
        if existing is None:
            raise
        existing = get_proposal(db, vpc_id=vpc_id, proposal_id=existing.id, now=now)
        return {"result": CREATE_DUPLICATE, "proposal": existing}


def _current_proposal_is_stale(db, proposal: SdnRemediationProposal, now: datetime) -> bool:
    """读取端保守陈旧判定（短事务、只读 DB + 一次 projection 评估，零设备 I/O）。"""
    from app.routers.sdn import _is_sdn_fabric_member, _latest_snapshot, build_projection_payload
    from app.services.sdn_assurance import evaluate_assurance

    if proposal.status != STATUS_PROPOSED:
        return False
    if proposal.expires_at is not None and proposal.expires_at <= now:
        return True
    vpc = db.query(SdnVpc).filter(SdnVpc.id == proposal.vpc_id).first()
    if vpc is None:
        return True
    if vpc.version != proposal.vpc_version_at_create:
        return True
    device = db.query(Device).filter(Device.id == proposal.device_id).first()
    if device is None or not _is_sdn_fabric_member(device):
        return True
    latest = _latest_snapshot(db, proposal.vpc_id, proposal.device_id)
    if latest is None or latest.id != proposal.evidence_snapshot_id:
        return True
    if _has_active_maintenance_exception(db, proposal.vpc_id, proposal.device_id, now):
        return True
    projection = build_projection_payload(db, proposal.vpc_id)
    if projection is None:
        return True
    result = evaluate_assurance(projection, now=now)
    current_item = next(
        (
            i for i in result.get("items") or []
            if i.get("key") == proposal.item_key and i.get("device_id") == proposal.device_id
        ),
        None,
    )
    if current_item is None or current_item.get("category") != CATEGORY or current_item.get("severity") != "blocking":
        return True
    return False


def _mark_stale_cas(db, proposal: SdnRemediationProposal, now: datetime):
    """proposed → stale 的 CAS 短事务：仅当仍 proposed 才改写，绝不覆盖 cancelled。"""
    updated = (
        db.query(SdnRemediationProposal)
        .filter(
            SdnRemediationProposal.id == proposal.id,
            SdnRemediationProposal.status == STATUS_PROPOSED,
        )
        .update(
            {
                SdnRemediationProposal.status: STATUS_STALE,
                SdnRemediationProposal.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return updated == 1


def get_proposal(
    db: Session, *, vpc_id: int, proposal_id: int, now: Optional[datetime] = None
) -> Optional[SdnRemediationProposal]:
    """读取并保守刷新陈旧状态：VPC version / 最新 snapshot / 分类 / 例外变化 → 标 stale。"""
    now = now or datetime.utcnow()
    proposal = (
        db.query(SdnRemediationProposal)
        .filter(SdnRemediationProposal.id == proposal_id)
        .first()
    )
    if proposal is None or proposal.vpc_id != vpc_id:
        return None
    if _current_proposal_is_stale(db, proposal, now):
        _mark_stale_cas(db, proposal, now)
        db.expire_all()
        proposal = (
            db.query(SdnRemediationProposal)
            .filter(SdnRemediationProposal.id == proposal_id)
            .first()
        )
    return proposal


def list_proposals(
    db: Session, *, vpc_id: int, now: Optional[datetime] = None
) -> list:
    """列出该 VPC 的提案（读取时对每条 proposed 保守刷新陈旧状态）。"""
    now = now or datetime.utcnow()
    rows = (
        db.query(SdnRemediationProposal)
        .filter(SdnRemediationProposal.vpc_id == vpc_id)
        .order_by(SdnRemediationProposal.id.desc())
        .all()
    )
    refreshed = []
    for row in rows:
        if _current_proposal_is_stale(db, row, now):
            _mark_stale_cas(db, row, now)
            db.expire_all()
            row = (
                db.query(SdnRemediationProposal)
                .filter(SdnRemediationProposal.id == row.id)
                .first()
            )
        refreshed.append(row)
    return refreshed


def cancel_proposal(
    db: Session, *, vpc_id: int, proposal_id: int, now: Optional[datetime] = None
) -> Optional[SdnRemediationProposal]:
    """取消提案：仅 proposed → cancelled（CAS）；重复取消/已 stale 幂等返回当前行。"""
    now = now or datetime.utcnow()
    proposal = (
        db.query(SdnRemediationProposal)
        .filter(SdnRemediationProposal.id == proposal_id)
        .first()
    )
    if proposal is None or proposal.vpc_id != vpc_id:
        return None
    if proposal.status == STATUS_PROPOSED:
        _mark_status_cas(db, proposal, STATUS_CANCELLED, now)
        db.expire_all()
        proposal = (
            db.query(SdnRemediationProposal)
            .filter(SdnRemediationProposal.id == proposal_id)
            .first()
        )
    return proposal


def _mark_status_cas(db, proposal: SdnRemediationProposal, status: str, now: datetime) -> bool:
    updated = (
        db.query(SdnRemediationProposal)
        .filter(
            SdnRemediationProposal.id == proposal.id,
            SdnRemediationProposal.status == STATUS_PROPOSED,
        )
        .update(
            {
                SdnRemediationProposal.status: status,
                SdnRemediationProposal.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return updated == 1


def serialize_proposal(proposal: SdnRemediationProposal) -> dict:
    """提案序列化（白名单；summary 只含语义单元/保留项/边界，绝不含 CLI/凭据）。"""
    try:
        summary = json.loads(proposal.summary_json or "{}")
    except (TypeError, ValueError):
        summary = {}
    summary = summary if isinstance(summary, dict) else {}
    return {
        "id": proposal.id,
        "vpc_id": proposal.vpc_id,
        "run_id": proposal.run_id,
        "item_key": proposal.item_key,
        "device_id": proposal.device_id,
        "device_name": summary.get("device_name"),
        "action": proposal.action,
        "category": proposal.category,
        "vpc_version_at_create": proposal.vpc_version_at_create,
        "policy_version": proposal.policy_version,
        "evidence_snapshot_id": proposal.evidence_snapshot_id,
        "status": proposal.status,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
        "fingerprint": proposal.fingerprint,
        "units": summary.get("units") or [],
        "preserved": summary.get("preserved") or list(_PRESERVED),
        "executed": bool(summary.get("executed")),
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
    }
