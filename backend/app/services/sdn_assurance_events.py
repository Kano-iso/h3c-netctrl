"""S3-003 有界事件保障：业务事件成功后追加 trigger=event 的只读评估（NEXT/S3 后端切片）。

两类已成功持久化的业务事件后触发（调用方在业务事务 commit 之后调用本模块）：
1. validation/sync 成功落入快照 → event_key = snapshot:{snapshot_id}（每快照至多一次）；
2. scope-exception 新增/修改/清除 → event_key = scope-exc:{id}:v{version} / :cleared。

不变量（S3-003）：
- 未配策略或 enabled=false → 零 event run；manual cadence 只禁用周期，已 enabled 时仍允许
  事件检查；
- 评估复用 S3-001 投影/白名单路径（build_projection_payload + evaluate_assurance），不再次
  采集、不下发、不改 vpc.version 与 deployment/binding/operation/snapshot/claim；
- event_key 稳定去重：同源事件重试不重复历史（DB 具名唯一索引 uq_sdn_assurance_runs_event_key
  兜底，flush 撞唯一约束即跳过）；event_key 只含稳定内部 ID/版本，不含凭据/原始 CLI；
- 原业务事件已成功不受影响：评估失败不回滚、不伪装业务失败，追加 status=failed 的 event run
  供审计；本模块绝不向调用方抛异常。
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.models import SdnAssurancePolicy, SdnAssuranceRun
from app.services.sdn_assurance import (
    SdnAssuranceVpcNotFound,
    facts_json,
    items_json,
    run_summary_json,
)

logger = logging.getLogger(__name__)

EVENT_TRIGGER = "event"


def snapshot_event_key(snapshot_id: int) -> str:
    """快照事件的稳定去重 key（仅内部快照 id，无凭据/CLI）。"""
    return f"snapshot:{snapshot_id}"


def scope_exception_event_key(exception_id: int, version: Optional[int] = None, *, cleared: bool = False) -> str:
    """scope-exception 事件的稳定去重 key：新增/修改按 (id, version)，清除按 (id)。"""
    if cleared:
        return f"scope-exc:{exception_id}:cleared"
    return f"scope-exc:{exception_id}:v{version}"


def _policy(db, vpc_id: int) -> Optional[SdnAssurancePolicy]:
    return db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()


def _failed_summary_json() -> str:
    """失败 run 的诚实 summary（overall=None，不伪装 insufficient_evidence/healthy）。"""
    return run_summary_json(
        {"overall": None, "total": 0, "blocking": 0, "review": 0, "deferred": 0}
    )


def record_event_check(
    db,
    *,
    vpc_id: int,
    event_key: str,
    now: Optional[datetime] = None,
) -> Optional[SdnAssuranceRun]:
    """业务事件已成功持久化后追加一条 trigger=event 只读评估（S3-003）。

    返回该 event run（completed/failed）；跳过时（未配策略 / enabled=false / 同源事件已
    记录）返回 None。绝不抛异常：评估失败只追加 failed run，不影响已成功的原业务事件。
    """
    try:
        policy = _policy(db, vpc_id)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"event assurance policy lookup failed vpc={vpc_id} key={event_key}: {exc!r}")
        return None
    if policy is None or not policy.enabled:
        return None  # 未配策略或 enabled=false → 零 event run
    # Keep the policy generation detached from the Session.  A failed evaluation rolls
    # back and expires ORM instances; reading policy afterwards could refresh a newer
    # generation (or fail if the policy was removed) and corrupt the audit record.
    policy_version = policy.version
    policy_enabled = bool(policy.enabled)
    now = now or datetime.utcnow()

    run = SdnAssuranceRun(
        vpc_id=vpc_id,
        trigger=EVENT_TRIGGER,
        status="started",  # 占位：先占 event_key（唯一防御立即生效），成功/失败后改终态
        started_at=now,
        policy_version=policy_version,
        policy_enabled=policy_enabled,
        event_key=event_key,
        facts_json="{}",
        summary_json="{}",
        items_json="[]",
    )
    try:
        db.add(run)
        db.flush()  # 同源事件已记录 → 撞唯一约束
    except IntegrityError:
        db.rollback()
        return None  # 同一源事件重试 → 不重复历史

    try:
        # 函数级 import：与 S3-002 scheduler 一致，允许测试 patch 源模块函数
        from app.routers.sdn import build_projection_payload
        from app.services.sdn_assurance import evaluate_assurance

        projection = build_projection_payload(db, vpc_id)
        if projection is None:
            raise SdnAssuranceVpcNotFound(f"vpc {vpc_id} has no state projection facts")
        result = evaluate_assurance(projection, now=now)
        run.status = "completed"
        run.completed_at = now
        run.facts_json = facts_json(result)
        run.summary_json = run_summary_json(result)
        run.items_json = items_json(result.get("items") or [])
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        # 评估失败：不回滚已成功的原业务事件、不伪装业务失败——追加 failed run 供审计
        db.rollback()
        logger.warning(f"event assurance failed vpc={vpc_id} key={event_key}: {exc!r}")
        failed = SdnAssuranceRun(
            vpc_id=vpc_id,
            trigger=EVENT_TRIGGER,
            status="failed",
            started_at=now,
            completed_at=now,
            policy_version=policy_version,
            policy_enabled=policy_enabled,
            event_key=event_key,
            error=str(exc)[:500],
            facts_json="{}",
            summary_json=_failed_summary_json(),
            items_json="[]",
        )
        try:
            db.add(failed)
            db.commit()
            db.refresh(failed)
            return failed
        except IntegrityError:
            db.rollback()
            return None  # 同源事件失败也已记录 → 不重复
        except Exception as inner:
            db.rollback()
            logger.error(
                f"failed event-run persistence failed vpc={vpc_id} key={event_key}: {inner!r}"
            )
            return None
