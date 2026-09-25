"""S3-002 有界周期保障调度（NEXT/S3 后端切片）。

把 S3-001 已保存的 cadence 从"仅偏好"推进为 config/monolith core 内的安全只读周期评估：
manual 保持手动，10m/30m/1h 才参与周期。无 Redis/etcd/Celery/APScheduler 依赖；无进程锁
（靠 DB 条件更新 CAS 保证并发唯一 winner）；零设备 I/O、零自动修复。

窗口机制（持久化 due/claim，sdn_assurance_slots，每 VPC 至多一条当前窗口）：
- 单行状态机：pending → claimed → completed/failed → （advance 原位推进）→ pending...
- pending：due_at <= now 可被任何 tick 认领；claimed：lease 未过期不可接管、过期可由
  其他 tick 接管（崩溃恢复，同一代际新 token）；completed/failed：窗口终结，tick 原位
  推进到 generation+1 的新窗口（due 锚定终结时刻 + cadence，不补跑无限历史）。
- CAS 语义（全部条件更新 + rowcount 校验，SQLite 串行化写）：
  认领 WHERE (id, generation, status∈可认领)；完成/失败 WHERE (id, generation,
  status='claimed', claim_token)；推进 WHERE (id, generation, status∈可推进)。并发双 tick
  对同一 VPC/同一窗口至多一个
  completed scheduled run；旧代际迟到（token/generation 不匹配）不能覆盖新代际。
- 失败/崩溃不永久饿死后续周期：崩溃 → lease 过期接管重试同一窗口；评估异常 → 窗口落
  failed（诚实，run 记 failed 不伪造 completed/healthy），下一窗口自然重试。

生命周期：仅 SERVICE_NAME=config 或 monolith core 启动线程；data/ctrl 不启动；
shutdown 停止线程；轮询间隔环境可配且安全下限 1.0s；测试可显式关闭
（ASSURANCE_SCHEDULER_ENABLED=false）。
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SdnAssurancePolicy, SdnAssuranceRun, SdnAssuranceSlot

logger = logging.getLogger("app.sdn_assurance_scheduler")

CADENCE_SECONDS = {"manual": None, "10m": 600, "30m": 1800, "1h": 3600}

_SLOT_STATUS_PENDING = "pending"
_SLOT_STATUS_CLAIMED = "claimed"
_SLOT_STATUS_COMPLETED = "completed"
_SLOT_STATUS_FAILED = "failed"

SCHEDULED_TRIGGER = "scheduled"


def cadence_seconds(cadence: str) -> Optional[int]:
    return CADENCE_SECONDS.get(cadence)


def scheduler_enabled_for(service_name: str) -> bool:
    """仅 config / monolith core 启动 scheduler；data/ctrl 不启动。"""
    return service_name in ("config", "core")


def _slot_key_for(vpc_id: int, generation: int) -> str:
    return f"vpc:{vpc_id}:slot:gen:{generation}"


def _claim_slot(
    db: Session, slot: SdnAssuranceSlot, *, now: datetime, lease_seconds: float
) -> Optional[str]:
    """CAS 认领：pending → claimed，或 lease 已过期的 claimed → claimed（同代际新 token）。

    返回新 claim_token（认领成功）或 None（他人持有/代际已变）。
    """
    token = uuid.uuid4().hex
    lease_until = now + timedelta(seconds=lease_seconds)
    claimed = (
        db.query(SdnAssuranceSlot)
        .filter(
            SdnAssuranceSlot.id == slot.id,
            SdnAssuranceSlot.generation == slot.generation,
            or_(
                SdnAssuranceSlot.status == _SLOT_STATUS_PENDING,
                and_(
                    SdnAssuranceSlot.status == _SLOT_STATUS_CLAIMED,
                    SdnAssuranceSlot.lease_expires_at <= now,
                ),
            ),
        )
        .update(
            {
                SdnAssuranceSlot.status: _SLOT_STATUS_CLAIMED,
                SdnAssuranceSlot.claim_token: token,
                SdnAssuranceSlot.claimed_at: now,
                SdnAssuranceSlot.lease_expires_at: lease_until,
                SdnAssuranceSlot.error: None,
                SdnAssuranceSlot.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return token if claimed == 1 else None


def _complete_slot(
    db: Session, slot: SdnAssuranceSlot, *, generation: int, token: str, run_id: int,
    commit: bool = True,
) -> bool:
    """owner-aware 完成 CAS（CR61）：仅当 (id, generation, status='claimed', claim_token)
    全部一致才落 completed，并清空 claim_token/claimed_at/lease。

    同 token 重放、complete→fail、旧 token/旧 generation 均 0 行且不改 run_id/status。
    """
    done = (
        db.query(SdnAssuranceSlot)
        .filter(
            SdnAssuranceSlot.id == slot.id,
            SdnAssuranceSlot.generation == generation,
            SdnAssuranceSlot.status == _SLOT_STATUS_CLAIMED,
            SdnAssuranceSlot.claim_token == token,
        )
        .update(
            {
                SdnAssuranceSlot.status: _SLOT_STATUS_COMPLETED,
                SdnAssuranceSlot.run_id: run_id,
                SdnAssuranceSlot.claim_token: None,
                SdnAssuranceSlot.claimed_at: None,
                SdnAssuranceSlot.lease_expires_at: None,
                SdnAssuranceSlot.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    if commit:
        db.commit()
    return done == 1


def _fail_slot(
    db: Session, slot: SdnAssuranceSlot, *, generation: int, token: str, error: str,
    commit: bool = True,
) -> bool:
    """owner-aware 失败 CAS（CR61）：仅当 (id, generation, status='claimed', claim_token)
    全部一致才落 failed，并清空 claim_token/claimed_at/lease（诚实记录，不伪造）。"""
    done = (
        db.query(SdnAssuranceSlot)
        .filter(
            SdnAssuranceSlot.id == slot.id,
            SdnAssuranceSlot.generation == generation,
            SdnAssuranceSlot.status == _SLOT_STATUS_CLAIMED,
            SdnAssuranceSlot.claim_token == token,
        )
        .update(
            {
                SdnAssuranceSlot.status: _SLOT_STATUS_FAILED,
                SdnAssuranceSlot.error: (error or "")[:500],
                SdnAssuranceSlot.claim_token: None,
                SdnAssuranceSlot.claimed_at: None,
                SdnAssuranceSlot.lease_expires_at: None,
                SdnAssuranceSlot.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    if commit:
        db.commit()
    return done == 1


def _get_slot(db: Session, vpc_id: int) -> Optional[SdnAssuranceSlot]:
    # populate_existing：同一 session 跨 tick 复用/条件更新后强制按库重读，
    # 避免 identity map 里的陈旧 status/claim_token 误导状态机
    return (
        db.query(SdnAssuranceSlot)
        .filter(SdnAssuranceSlot.vpc_id == vpc_id)
        .populate_existing()
        .first()
    )


def _create_first_slot(
    db: Session, policy: SdnAssurancePolicy, *, now: datetime
) -> Optional[SdnAssuranceSlot]:
    """策略首次参与周期：建 pending 窗口（due=now，下一 tick 立即评估）。

    并发双 tick 同时创建时唯一 vpc_id 约束拦后重查既有行（幂等）。
    """
    slot = SdnAssuranceSlot(
        vpc_id=policy.vpc_id,
        slot_key=_slot_key_for(policy.vpc_id, 0),
        cadence=policy.cadence,
        policy_version=policy.version,
        generation=0,
        status=_SLOT_STATUS_PENDING,
        due_at=now,
    )
    db.add(slot)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _get_slot(db, policy.vpc_id)
    db.refresh(slot)
    return slot


def _advance_slot(
    db: Session, policy: SdnAssurancePolicy, slot: SdnAssuranceSlot, *, now: datetime
) -> bool:
    """原位推进到下一窗口：cadence/策略版本改变（新策略续跑，不补跑）或当前窗口终结。

    CAS WHERE (id, generation, status∈{pending,completed,failed})：绝不推进 claimed 窗口
    （未过期 owner 收尾中；先完成/失败，后续 tick 再按新策略推进）。并发推进只有一个成功。
    新窗口 generation+1，due 锚定终结时刻 + 新 cadence，且不晚于 now 时按 now
    （有界：停机后不无限补跑）。返回是否真的推进了。
    """
    period = cadence_seconds(policy.cadence)
    if period is None:
        return False  # manual 不参与周期
    base = slot.updated_at or slot.due_at
    due = base + timedelta(seconds=period)
    if due <= now:
        due = now
    new_generation = slot.generation + 1
    advanced = (
        db.query(SdnAssuranceSlot)
        .filter(
            SdnAssuranceSlot.id == slot.id,
            SdnAssuranceSlot.generation == slot.generation,
            SdnAssuranceSlot.status.in_(
                (_SLOT_STATUS_PENDING, _SLOT_STATUS_COMPLETED, _SLOT_STATUS_FAILED)
            ),
        )
        .update(
            {
                SdnAssuranceSlot.generation: new_generation,
                SdnAssuranceSlot.slot_key: _slot_key_for(policy.vpc_id, new_generation),
                SdnAssuranceSlot.cadence: policy.cadence,
                SdnAssuranceSlot.policy_version: policy.version,
                SdnAssuranceSlot.status: _SLOT_STATUS_PENDING,
                SdnAssuranceSlot.due_at: due,
                SdnAssuranceSlot.claimed_at: None,
                SdnAssuranceSlot.claim_token: None,
                SdnAssuranceSlot.lease_expires_at: None,
                SdnAssuranceSlot.run_id: None,
                SdnAssuranceSlot.error: None,
                SdnAssuranceSlot.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return advanced == 1


def _persist_scheduled_failed_atomic(
    db: Session,
    vpc_id: int,
    slot: SdnAssuranceSlot,
    policy: Optional[SdnAssurancePolicy],
    *,
    now: datetime,
    error: str,
) -> Optional[SdnAssuranceRun]:
    """CR61：评估失败 → failed run 的 INSERT/flush 与失败 CAS 同一事务。

    CAS 0 行（lease 被接管/代际已变/已被推进）或 flush 撞唯一约束（同 slot_key 已有
    run）→ 整个事务 rollback，绝不留 orphan/重复历史，返回 None（赢家负责该窗口）。
    """
    from app.services.sdn_assurance import run_summary_json

    policy_version = policy.version if policy is not None else 0
    policy_enabled = bool(policy.enabled) if policy is not None else False
    run = SdnAssuranceRun(
        vpc_id=vpc_id,
        trigger=SCHEDULED_TRIGGER,
        status="failed",
        started_at=now,
        completed_at=now,
        policy_version=policy_version,
        policy_enabled=policy_enabled,
        slot_key=slot.slot_key,
        error=(error or "")[:500],
        facts_json="{}",
        summary_json=run_summary_json(
            {"overall": None, "total": 0, "blocking": 0, "review": 0, "deferred": 0}
        ),
        items_json="[]",
    )
    try:
        db.add(run)
        db.flush()
    except IntegrityError:
        # 同 slot_key 已有 run（DB 防御命中）→ 输掉竞态，回滚不留行
        db.rollback()
        return None
    done = _fail_slot(
        db, slot, generation=slot.generation, token=slot.claim_token,
        error=error or "scheduled evaluation failed", commit=False,
    )
    if not done:
        db.rollback()
        return None
    db.commit()
    db.refresh(run)
    return run


def _persist_scheduled_completed_atomic(
    db: Session,
    policy: SdnAssurancePolicy,
    slot: SdnAssuranceSlot,
    result: dict,
    *,
    now: datetime,
) -> Optional[SdnAssuranceRun]:
    """CR61：评估成功 → completed run（白名单快照）的 INSERT/flush 与完成 CAS 同一事务。

    CAS 0 行或 flush 撞唯一约束 → 整个事务 rollback，绝不留 orphan/重复历史。
    """
    from app.services.sdn_assurance import facts_json, items_json, run_summary_json

    run = SdnAssuranceRun(
        vpc_id=policy.vpc_id,
        trigger=SCHEDULED_TRIGGER,
        status="completed",
        started_at=now,
        completed_at=now,
        policy_version=policy.version,
        policy_enabled=bool(policy.enabled),
        slot_key=slot.slot_key,
        facts_json=facts_json(result),
        summary_json=run_summary_json(result),
        items_json=items_json(result.get("items") or []),
    )
    try:
        db.add(run)
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    done = _complete_slot(
        db, slot, generation=slot.generation, token=slot.claim_token,
        run_id=run.id, commit=False,
    )
    if not done:
        db.rollback()
        return None
    db.commit()
    db.refresh(run)
    return run


def _run_evaluation(
    db: Session,
    policy: SdnAssurancePolicy,
    slot: SdnAssuranceSlot,
    *,
    token: str,
    now: datetime,
) -> None:
    """认领成功后评估并原子落终态（共用 S3-001 投影/白名单路径；CR61 单事务 + CAS）。

    - 评估成功 → completed run + 完成 CAS 同事务；CAS 0 行 → run 回滚（不留 orphan）。
    - 评估异常 → failed run + 失败 CAS 同事务；同样输掉竞态则回滚，由赢家负责该窗口。
    """
    from app.routers.sdn import build_projection_payload
    from app.services.sdn_assurance import SdnAssuranceVpcNotFound, evaluate_assurance

    fresh = _get_slot(db, policy.vpc_id)
    if (
        fresh is None
        or fresh.status != _SLOT_STATUS_CLAIMED
        or fresh.generation != slot.generation
        or fresh.claim_token != token
    ):
        return  # 窗口已被推进/接管，旧 owner 不得代新 owner 执行
    # 保留本 worker 认领时的 owner 快照。异常分支会 rollback；若对象仍绑定 Session，
    # SQLAlchemy 会将其过期，随后读取 claim_token 可能刷新成另一 worker 的新 token，
    # 让旧 worker 错误地替新 owner 收尾。脱离后字段保持本次认领值，CAS 才能正确失败。
    db.expunge(fresh)
    # 策略版本也是本窗口的审计快照；异常 rollback 后不应刷新成并发修改的新版本。
    db.expunge(policy)

    try:
        projection = build_projection_payload(db, policy.vpc_id)
        if projection is None:
            raise SdnAssuranceVpcNotFound(f"vpc {policy.vpc_id} has no state projection facts")
        result = evaluate_assurance(projection, now=now)
        run = _persist_scheduled_completed_atomic(db, policy, fresh, result, now=now)
        if run is None:
            logger.info(f"scheduled completed-run lost race vpc={policy.vpc_id} (run rolled back)")
    except Exception as exc:
        db.rollback()
        logger.warning(f"scheduled assurance failed vpc={policy.vpc_id}: {exc!r}")
        try:
            failed = _persist_scheduled_failed_atomic(
                db, policy.vpc_id, fresh, policy, now=now, error=str(exc),
            )
            if failed is None:
                logger.info(f"scheduled failed-run lost race vpc={policy.vpc_id} (run rolled back)")
        except Exception as inner:
            logger.error(f"failed-run persistence also failed vpc={policy.vpc_id}: {inner!r}")
            db.rollback()


def _process_vpc(
    db: Session,
    policy: SdnAssurancePolicy,
    *,
    now: datetime,
    lease_seconds: float,
) -> bool:
    """处理一个 VPC 的当前窗口。

    返回 True 当且仅当本 tick 对该 VPC 的 slot 产生了**持久化变更**（建首窗口 / 认领并
    评估 / 任一推进）；纯只读跳过（pending 未到期、claimed 未过期、并发输掉 CAS）返回
    False。CR61：策略变更的推进只允许在非 claimed 状态进行——未过期 owner 收尾中不推进，
    先完成/失败，后续 tick 再按新策略推进。
    """
    slot = _get_slot(db, policy.vpc_id)
    if slot is None:
        # 策略已 enabled 且非 manual 而无窗口 → 建首个窗口（due=now），本轮不评估
        created = _create_first_slot(db, policy, now=now)
        return created is not None
    if slot.status == _SLOT_STATUS_CLAIMED:
        expired = slot.lease_expires_at is not None and slot.lease_expires_at <= now
        if not expired:
            return False  # lease 未过期不可接管；策略变更也等 owner 收尾后由后续 tick 推进
        token = _claim_slot(db, slot, now=now, lease_seconds=lease_seconds)
        if token is None:
            return False  # 并发下他人已接管
        _run_evaluation(db, policy, slot, token=token, now=now)
        return True
    # 非 claimed：pending / completed / failed（claimed 分支已返回）
    policy_changed = (
        slot.cadence != policy.cadence or slot.policy_version != policy.version
    )
    if slot.status == _SLOT_STATUS_PENDING:
        if policy_changed:
            # pending 无 owner：直接按新策略推进（不补跑）
            return _advance_slot(db, policy, slot, now=now)
        if slot.due_at <= now:
            token = _claim_slot(db, slot, now=now, lease_seconds=lease_seconds)
            if token is None:
                return False
            _run_evaluation(db, policy, slot, token=token, now=now)
            return True
        return False
    if slot.status in (_SLOT_STATUS_COMPLETED, _SLOT_STATUS_FAILED):
        return _advance_slot(db, policy, slot, now=now)
    return False


def tick_once(
    db: Session,
    *,
    now: Optional[datetime] = None,
    lease_seconds: Optional[float] = None,
    max_slots: Optional[int] = None,
) -> list:
    """执行一次调度 tick（同步、无锁自旋；可被测试直接调用）。

    扫描 enabled 且 cadence!=manual 的策略，按批量上限处理；**每 tick 的全部持久化窗口
    变更都计入上限**（建首窗口 / 认领评估 / terminal 推进 / policy-change 推进），
    max_slots=N 时最多 N 个 VPC 的 slot 被修改；纯只读跳过不计。返回本轮产生持久化
    变更的 vpc_id 列表。并发调用由 DB CAS 保证唯一 winner。
    """
    from app.config import settings

    now = now or datetime.utcnow()
    lease_seconds = lease_seconds if lease_seconds is not None else settings.ASSURANCE_SLOT_LEASE_SECONDS
    max_slots = max_slots if max_slots is not None else settings.ASSURANCE_TICK_MAX_SLOTS

    changed: list = []
    policies = (
        db.query(SdnAssurancePolicy)
        .filter(SdnAssurancePolicy.enabled.is_(True))
        .order_by(SdnAssurancePolicy.vpc_id)
        .all()
    )
    for policy in policies:
        if len(changed) >= max_slots:
            break
        if cadence_seconds(policy.cadence) is None:
            continue  # manual 不参与周期
        if _process_vpc(db, policy, now=now, lease_seconds=lease_seconds):
            changed.append(policy.vpc_id)
    db.commit()
    return changed


# ---------------------------------------------------------------- 只读状态（GET policy）


def last_scheduled_at(db: Session, vpc_id: int) -> Optional[datetime]:
    return (
        db.query(func.max(SdnAssuranceRun.completed_at))
        .filter(SdnAssuranceRun.vpc_id == vpc_id, SdnAssuranceRun.trigger == SCHEDULED_TRIGGER)
        .scalar()
    )


def schedule_status_for_policy(db: Session, policy: SdnAssurancePolicy) -> dict:
    """GET 策略附带的稳定调度信息（前端未来所需，只读不写库）。"""
    last = last_scheduled_at(db, policy.vpc_id)
    last_iso = last.isoformat() if last else None
    if not policy.enabled:
        return {"schedule_status": "disabled", "next_due": None, "last_scheduled_at": last_iso}
    if cadence_seconds(policy.cadence) is None:
        return {"schedule_status": "manual_only", "next_due": None, "last_scheduled_at": last_iso}
    slot = _get_slot(db, policy.vpc_id)
    now = datetime.utcnow()
    if slot is None:
        return {"schedule_status": "scheduled", "next_due": None, "last_scheduled_at": last_iso}
    if slot.status == _SLOT_STATUS_PENDING:
        status = "due" if slot.due_at <= now else "scheduled"
        return {"schedule_status": status, "next_due": slot.due_at.isoformat(), "last_scheduled_at": last_iso}
    if slot.status == _SLOT_STATUS_CLAIMED:
        lease_ok = slot.lease_expires_at is not None and slot.lease_expires_at > now
        return {
            "schedule_status": "running" if lease_ok else "due",
            "next_due": slot.due_at.isoformat(),
            "last_scheduled_at": last_iso,
        }
    # completed/failed：只读计算下一窗口（与 _advance_slot 锚定规则一致）
    period = cadence_seconds(policy.cadence)
    base = slot.updated_at or slot.due_at
    next_due = (base + timedelta(seconds=period)).isoformat() if period is not None else None
    return {"schedule_status": "scheduled", "next_due": next_due, "last_scheduled_at": last_iso}


# ---------------------------------------------------------------- 线程生命周期


class Scheduler:
    """轮询调度线程：start 后按 interval 循环 tick_once，stop 停止并 join。

    参数缺省取 settings；测试可显式传值并直接 start/stop，或完全不启线程
    （ASSURANCE_SCHEDULER_ENABLED=false）只同步调 tick_once。
    """

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        interval_seconds: Optional[float] = None,
        lease_seconds: Optional[float] = None,
        max_slots: Optional[int] = None,
        session_factory: Optional[Callable[[], Session]] = None,
    ):
        from app.config import settings
        from app.database import SessionLocal

        self.enabled = settings.ASSURANCE_SCHEDULER_ENABLED if enabled is None else enabled
        raw_interval = settings.ASSURANCE_SCHEDULER_INTERVAL_SECONDS if interval_seconds is None else interval_seconds
        self.interval_seconds = max(1.0, float(raw_interval))  # 安全下限 1.0s
        self.lease_seconds = settings.ASSURANCE_SLOT_LEASE_SECONDS if lease_seconds is None else lease_seconds
        self.max_slots = settings.ASSURANCE_TICK_MAX_SLOTS if max_slots is None else max_slots
        self.session_factory = session_factory or SessionLocal
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if not self.enabled or self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="sdn-assurance-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                db = self.session_factory()
                try:
                    tick_once(
                        db,
                        lease_seconds=self.lease_seconds,
                        max_slots=self.max_slots,
                    )
                finally:
                    db.close()
            except Exception:
                logger.exception("assurance scheduler tick failed")
            # 用 stop 事件等待：shutdown 可立即唤醒，不受 interval 阻塞
            elapsed = time.monotonic() - started
            wait = max(0.0, self.interval_seconds - elapsed)
            if self._stop.wait(wait):
                break


_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
