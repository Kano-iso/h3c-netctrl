"""S3-001 VPC 受限保障：策略 + 只读手动评估（NEXT/S3 后端切片）。

沿用 /api/sdn 风格与 APIResponse。策略写库（短事务、零设备 I/O）；手动评估只读复用
同一次 state projection/attention 事实（公共持久化路径 persist_assurance_run，与
scheduled 共用），持久化一条 run（触发仅 manual）。本路由不调用
collector/executor/Netconf/SSH，不创建 deployment/binding/operation/snapshot/claim，
不 bump vpc.version，不做后台调度（调度见 services/sdn_assurance_scheduler）。
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n_keys import err, error_response
from app.models import SdnAssurancePolicy, SdnAssuranceRun, SdnVpc
from app.schemas import APIResponse
from app.services.sdn_assurance import (
    ASSURANCE_CADENCES,
    ASSURANCE_RESPONSE_MODE,
    SdnAssuranceVpcNotFound,
    persist_assurance_run,
)

router = APIRouter(prefix="/api/sdn", tags=["sdn-assurance"])

DEFAULT_POLICY = {
    "enabled": False,
    "cadence": "manual",
    "response_mode": ASSURANCE_RESPONSE_MODE,
    "version": 0,
}

RUN_LIST_DEFAULT_LIMIT = 20
RUN_LIST_MAX_LIMIT = 100


def _serialize_policy(row: SdnAssurancePolicy, db: Session) -> dict:
    from app.services.sdn_assurance_scheduler import schedule_status_for_policy

    info = schedule_status_for_policy(db, row)
    return {
        "id": row.id,
        "vpc_id": row.vpc_id,
        "enabled": bool(row.enabled),
        "cadence": row.cadence,
        "response_mode": row.response_mode,
        "version": row.version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # S3-002：稳定调度信息（只读，供前端未来使用）
        "schedule_status": info["schedule_status"],
        "next_due": info["next_due"],
        "last_scheduled_at": info["last_scheduled_at"],
    }


def _atomic_update_policy(
    db: Session,
    *,
    policy_id: int,
    version: int,
    enabled: bool,
    cadence: str,
    response_mode: str,
) -> int:
    """按 id + version 原子推进策略版本，返回受影响行数。"""
    return (
        db.query(SdnAssurancePolicy)
        .filter(
            SdnAssurancePolicy.id == policy_id,
            SdnAssurancePolicy.version == version,
        )
        .update(
            {
                SdnAssurancePolicy.enabled: enabled,
                SdnAssurancePolicy.cadence: cadence,
                SdnAssurancePolicy.response_mode: response_mode,
                SdnAssurancePolicy.version: version + 1,
                SdnAssurancePolicy.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )


def _safe_json(raw: Optional[str], expected_type):
    """历史 JSON 类型不符或损坏时稳定降级。"""
    if not raw:
        return expected_type()
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return expected_type()
    return value if isinstance(value, expected_type) else expected_type()


def _safe_summary(raw: Optional[str]) -> dict:
    value = _safe_json(raw, dict)
    overall = value.get("overall")
    if overall not in {"healthy", "attention", "blocked", "insufficient_evidence"}:
        overall = "insufficient_evidence"
    return {
        "overall": overall,
        "total": value.get("total") if isinstance(value.get("total"), int) else 0,
        "blocking": value.get("blocking") if isinstance(value.get("blocking"), int) else 0,
        "review": value.get("review") if isinstance(value.get("review"), int) else 0,
        "deferred": value.get("deferred") if isinstance(value.get("deferred"), int) else 0,
    }


def _safe_facts(raw: Optional[str]) -> dict:
    value = _safe_json(raw, dict)
    scope = value.get("scope") if isinstance(value.get("scope"), dict) else {}
    attention = value.get("attention") if isinstance(value.get("attention"), dict) else {}
    leaves = []
    for leaf in value.get("leaves") if isinstance(value.get("leaves"), list) else []:
        if isinstance(leaf, dict):
            leaves.append({
                key: leaf.get(key)
                for key in ("device_id", "name", "aggregate", "snapshot_id", "collected_at")
                if key in leaf
            })
    return {
        "vpc_version": value.get("vpc_version"),
        "scope": {
            key: scope.get(key)
            for key in ("eligible", "targeted", "not_targeted", "withdrawn", "ambiguous")
            if key in scope
        },
        "leaves": leaves,
        "attention": {
            key: attention.get(key)
            for key in ("total", "blocking", "review", "deferred")
            if key in attention
        },
    }


def _safe_items(raw: Optional[str]) -> list:
    from app.services.sdn_assurance import assurance_item

    return [
        normalized
        for item in _safe_json(raw, list)
        if (normalized := assurance_item(item)) is not None
    ]


def _serialize_run(run: SdnAssuranceRun) -> dict:
    summary = _safe_summary(run.summary_json)
    failed = run.status == "failed"
    if failed:
        # S3-002：失败 run 诚实呈现（overall 不得伪装成 insufficient_evidence/healthy）
        summary["overall"] = None
    return {
        "id": run.id,
        "vpc_id": run.vpc_id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "policy_version": run.policy_version,
        "policy_enabled": bool(run.policy_enabled),
        # S3-002：scheduled 运行的窗口 key（manual 为 None）+ 失败原因（仅 failed 非空）
        "slot_key": run.slot_key,
        "error": run.error,
        # S3-003：event 运行的稳定去重审计 key（manual/scheduled 为 None；只读）
        "event_key": run.event_key,
        "overall": None if failed else summary.get("overall"),
        "summary": summary,
        "facts": _safe_facts(run.facts_json),
        "items": _safe_items(run.items_json),
    }


@router.get("/vpcs/{vpc_id}/assurance-policy", response_model=APIResponse)
def get_assurance_policy(vpc_id: int, db: Session = Depends(get_db)):
    """读取 VPC 保障策略；缺失时返回明确默认值（不隐式写库）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    row = db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()
    if row is None:
        return APIResponse(
            success=True,
            data=dict(
                DEFAULT_POLICY,
                vpc_id=vpc_id,
                # S3-002：缺失策略的稳定调度信息（enabled=false → disabled）
                schedule_status="disabled",
                next_due=None,
                last_scheduled_at=None,
            ),
        )
    return APIResponse(success=True, data=_serialize_policy(row, db))


@router.put("/vpcs/{vpc_id}/assurance-policy", response_model=APIResponse)
def put_assurance_policy(vpc_id: int, body: dict, db: Session = Depends(get_db)):
    """保存 VPC 保障策略（每 VPC 至多一条；乐观并发 version 冲突即拒绝）。写库零设备 I/O。

    body: {enabled: bool, cadence: manual|10m|30m|1h, response_mode?: observe_only,
           version: int}；缺失策略时 version 必须为 0（创建 v1），否则必须等于当前版本。
    """
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    if not isinstance(body, dict):
        body = {}

    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return error_response(err.SDN_ASSURANCE_INVALID_POLICY)
    cadence = body.get("cadence")
    if cadence not in ASSURANCE_CADENCES:
        return error_response(err.SDN_ASSURANCE_INVALID_CADENCE, params={"cadence": cadence})
    response_mode = body.get("response_mode", ASSURANCE_RESPONSE_MODE)
    if response_mode != ASSURANCE_RESPONSE_MODE:
        return error_response(
            err.SDN_ASSURANCE_INVALID_RESPONSE_MODE, params={"response_mode": response_mode}
        )
    version = body.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        return error_response(err.SDN_ASSURANCE_INVALID_POLICY)

    existing = (
        db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()
    )
    current = existing.version if existing is not None else 0
    if version != current:
        return error_response(
            err.SDN_ASSURANCE_POLICY_VERSION_CONFLICT,
            params={"expected": current, "given": version},
        )
    try:
        if existing is not None:
            # 单条条件 UPDATE 是真正的 CAS：并发请求即使都读到同一版本，也只有一个
            # 能把 version 从 N 推到 N+1；输家零行更新，绝不 last-write-wins。
            updated = _atomic_update_policy(
                db,
                policy_id=existing.id,
                version=version,
                enabled=enabled,
                cadence=cadence,
                response_mode=response_mode,
            )
            if updated != 1:
                db.rollback()
                current_row = db.query(SdnAssurancePolicy).filter(
                    SdnAssurancePolicy.vpc_id == vpc_id
                ).first()
                return error_response(
                    err.SDN_ASSURANCE_POLICY_VERSION_CONFLICT,
                    params={"expected": current_row.version if current_row else 0, "given": version},
                )
        else:
            db.add(SdnAssurancePolicy(
                vpc_id=vpc_id, enabled=enabled, cadence=cadence,
                response_mode=response_mode, version=1,
            ))
        db.commit()
    except IntegrityError:
        # 并发创建：唯一 vpc_id 约束拦截后回滚，重读既有行并再做版本校验（短事务）。
        db.rollback()
        existing = (
            db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()
        )
        if existing is None:
            raise
        return error_response(
            err.SDN_ASSURANCE_POLICY_VERSION_CONFLICT,
            params={"expected": existing.version, "given": version},
        )

    # bulk CAS 不同步 ORM identity map；提交后主动失效，响应必须反映数据库新版本。
    db.expire_all()
    row = (
        db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()
    )
    return APIResponse(success=True, data=_serialize_policy(row, db))


@router.post("/vpcs/{vpc_id}/assurance-runs", response_model=APIResponse)
def create_manual_assurance_run(vpc_id: int, body: Optional[dict] = None, db: Session = Depends(get_db)):
    """发起一次只读手动评估：同一次 state projection/attention 事实 → 持久化一条 run。

    零设备 I/O（不调用 collector/executor/Netconf/SSH）、零业务写副作用（不创建
    deployment/binding/operation/snapshot/claim、不 bump vpc.version）。触发仅允许
    manual（scheduled/event 为未来 scheduler 保留）。policy disabled 时评估仍允许，
    但 run 明确记录 policy_enabled=false。
    """
    body = body or {}
    trigger = body.get("trigger", "manual")
    if trigger != "manual":
        return error_response(err.SDN_ASSURANCE_INVALID_TRIGGER, params={"trigger": trigger})

    try:
        run = persist_assurance_run(db, vpc_id, trigger="manual")
    except SdnAssuranceVpcNotFound:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    return APIResponse(success=True, data=_serialize_run(run))


@router.get("/vpcs/{vpc_id}/assurance-runs", response_model=APIResponse)
def list_assurance_runs(
    vpc_id: int,
    limit: int = RUN_LIST_DEFAULT_LIMIT,
    before: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """评估历史（稳定游标分页：before=上一页最后 run_id，limit 上限 100，按 id 降序）。"""
    vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    if not vpc:
        return error_response(err.SDN_VPC_NOT_FOUND, params={"id": vpc_id})
    if limit <= 0 or limit > RUN_LIST_MAX_LIMIT:
        limit = RUN_LIST_DEFAULT_LIMIT
    query = db.query(SdnAssuranceRun).filter(SdnAssuranceRun.vpc_id == vpc_id)
    if before is not None:
        query = query.filter(SdnAssuranceRun.id < before)
    runs = query.order_by(SdnAssuranceRun.id.desc()).limit(limit).all()
    total = (
        db.query(SdnAssuranceRun).filter(SdnAssuranceRun.vpc_id == vpc_id).count()
    )
    return APIResponse(
        success=True,
        data={
            "vpc_id": vpc_id,
            "limit": limit,
            "before": before,
            "total": total,
            "runs": [_serialize_run(r) for r in runs],
        },
    )


@router.get("/vpcs/{vpc_id}/assurance-runs/{run_id}", response_model=APIResponse)
def get_assurance_run(vpc_id: int, run_id: int, db: Session = Depends(get_db)):
    """评估运行详情（白名单输出；run 不存在或不属于该 VPC → 404 语义）。"""
    run = (
        db.query(SdnAssuranceRun)
        .filter(SdnAssuranceRun.id == run_id, SdnAssuranceRun.vpc_id == vpc_id)
        .first()
    )
    if run is None:
        return error_response(
            err.SDN_ASSURANCE_RUN_NOT_FOUND, params={"vpc_id": vpc_id, "run_id": run_id}
        )
    return APIResponse(success=True, data=_serialize_run(run))
