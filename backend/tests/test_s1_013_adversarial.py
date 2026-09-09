"""S1-013 对抗性测试：CR30 动作代际令牌 + CR31 reconcile 原子准入。

真实线程 + 阻塞 barrier。证明 phase-only CAS 被代际令牌替换后：
- 旧代际迟到收尾 CAS 零行，不覆盖新代际、不动新 claims（ABA）。
- 活跃 apply/validate/withdraw 下 reconcile 在采集前被拒。
- unknown 普通 reconcile 单赢家；active phase 依 lease 判定失联后受保护 takeover。
- reconcile collector 失败/迟到收尾不覆盖 withdrawn/新 phase、不释放 claims。
"""
import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAttempt, SdnAttemptUnit, SdnDeployment, SdnOperation, SdnPortBinding, SdnValidationSnapshot
from app.routers.sdn_access import apply_access, complete_access, reconcile_operation, withdraw_access
from app.schemas import SdnAccessCompleteRequest, SdnWithdrawRequest
from app.services.sdn_operation_service import (
    STALE_ACTION_LEASE_SECONDS,
    create_attempt,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_s1_007_adversarial import _active_claims, _do_access, _seed_ready, _seed_unknown_port_bind  # noqa: E402
from test_s1_010_adversarial import _seed_awaiting_validation  # noqa: E402


def _seed_awaiting_wiring(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    return device, vpc, op["operation_id"]


def _blocking_collector(entered, release, calls, *, return_err=True):
    def _fake_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        calls.append(threading.get_ident())
        entered.set()
        release.wait(timeout=20)
        if return_err:
            return None, {"key": "sdn.device_not_writable", "params": {}}, False
        return None, None, False
    return _fake_sync


def _blocking_executor(entered, release, calls, unit_name):
    def _fake(self, db, dep_id, *, unit_hooks=None):
        calls.append(threading.get_ident())
        entered.set()
        release.wait(timeout=20)
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, unit_name)
            unit_hooks.after_unit_success(0, unit_name)
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d
    return _fake


def _swap_generation_token(db, op_id, kind):
    """模拟 phase 被接管后新一代进入同名 phase：换掉 active_attempt_id 代际令牌。"""
    new_attempt = create_attempt(db, operation_id=op_id, kind=kind, owner="gen-next")
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update(
        {"active_attempt_id": new_attempt.id, "active_started_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return new_attempt


# ── CR30: ABA——旧代际迟到收尾 CAS 零行，不覆盖新代际、不动新 claims ──

def test_cr30_aba_validate_generation_token(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def run():
        s = SessionLocal()
        try:
            results.append(complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, calls)):
            t = threading.Thread(target=run)
            t.start()
            assert entered.wait(timeout=15)

            # 模拟 phase 被安全接管后新一代进入同名 validating（换代际令牌）
            new_token = _swap_generation_token(db, op_id, "validate")

            release.set()
            t.join(timeout=20)
    finally:
        release.set()
        if t is not None:
            t.join(timeout=5)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data["status"] == "validating"  # 未被旧代际覆盖为 unknown
    assert results[0].data.get("note") == "late completion: status changed by concurrent action"
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "validating"
    assert refreshed.active_attempt_id == new_token.id  # 新代际令牌未被清空
    # 旧代际未把新代际的 claims 误标 ambiguous/释放（仍为 held）
    assert all(c.status == "held" for c in _active_claims(db, op_id))


def test_cr30_aba_withdraw_generation_token(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def run():
        s = SessionLocal()
        try:
            results.append(withdraw_access(op_id, SdnWithdrawRequest(), db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, calls, "port-unbind")):
            t = threading.Thread(target=run)
            t.start()
            assert entered.wait(timeout=15)

            new_token = _swap_generation_token(db, op_id, "withdraw")

            release.set()
            t.join(timeout=20)
    finally:
        release.set()
        if t is not None:
            t.join(timeout=5)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data["status"] == "withdrawing"
    assert results[0].data.get("note") == "late completion: status changed by concurrent action"
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "withdrawing"
    assert refreshed.active_attempt_id == new_token.id
    assert all(c.status == "held" for c in _active_claims(db, op_id))


def test_cr30_aba_apply_generation_token(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def run():
        s = SessionLocal()
        try:
            results.append(apply_access(op_id, db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, calls, "port-bind")):
            t = threading.Thread(target=run)
            t.start()
            assert entered.wait(timeout=15)

            new_token = _swap_generation_token(db, op_id, "execute")

            release.set()
            t.join(timeout=20)
    finally:
        release.set()
        if t is not None:
            t.join(timeout=5)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data["status"] == "applying"
    assert results[0].data.get("note") == "late completion: status changed by concurrent action"
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "applying"
    assert refreshed.active_attempt_id == new_token.id
    assert all(c.status == "held" for c in _active_claims(db, op_id))


# ── CR31: 活跃 apply/validate/withdraw 下 reconcile 在采集前被拒 ──

def _assert_reconcile_rejected(client, db, op_id, resp, reconcile_collector_calls):
    assert resp.success is False
    assert resp.error_key == "sdn.operation_in_progress"
    assert len(reconcile_collector_calls) == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "reconcile").count() == 0


def test_cr31_reconcile_rejected_during_live_validate(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    collector_calls = []
    reconcile_resp = []

    def run_reconcile():
        s = SessionLocal()
        try:
            reconcile_resp.append(reconcile_operation(op_id, db=s))
        finally:
            s.close()

    tv = None
    tr = None
    try:
        # validate 先准入并阻塞在 collector（同时占用同名 collector）
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, collector_calls)):
            def run_complete():
                s = SessionLocal()
                try:
                    complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s)
                finally:
                    s.close()
            tv = threading.Thread(target=run_complete)
            tv.start()
            assert entered.wait(timeout=15)

            # 在 validate 活跃期发 reconcile：必须在采集前被拒
            tr = threading.Thread(target=run_reconcile)
            tr.start()
            tr.join(timeout=15)

            assert len(collector_calls) == 1  # 只有 validate 的 collector
            _assert_reconcile_rejected(client, db, op_id, reconcile_resp[0], [])

            release.set()
            tv.join(timeout=20)
    finally:
        release.set()
        if tv is not None:
            tv.join(timeout=5)
        if tr is not None:
            tr.join(timeout=5)


def test_cr31_reconcile_rejected_during_live_apply(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    collector_calls = []
    reconcile_resp = []

    def run_reconcile():
        s = SessionLocal()
        try:
            reconcile_resp.append(reconcile_operation(op_id, db=s))
        finally:
            s.close()

    ta = None
    tr = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-bind")), \
             patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, collector_calls)):
            def run_apply():
                s = SessionLocal()
                try:
                    apply_access(op_id, db=s)
                finally:
                    s.close()
            ta = threading.Thread(target=run_apply)
            ta.start()
            assert entered.wait(timeout=15)

            tr = threading.Thread(target=run_reconcile)
            tr.start()
            tr.join(timeout=15)

            assert len(executor_calls) == 1  # 只有 apply 的 executor
            _assert_reconcile_rejected(client, db, op_id, reconcile_resp[0], collector_calls)

            release.set()
            ta.join(timeout=20)
    finally:
        release.set()
        if ta is not None:
            ta.join(timeout=5)
        if tr is not None:
            tr.join(timeout=5)


def test_cr31_reconcile_rejected_during_live_withdraw(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    collector_calls = []
    reconcile_resp = []

    def run_reconcile():
        s = SessionLocal()
        try:
            reconcile_resp.append(reconcile_operation(op_id, db=s))
        finally:
            s.close()

    tw = None
    tr = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-unbind")), \
             patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, collector_calls)):
            def run_withdraw():
                s = SessionLocal()
                try:
                    withdraw_access(op_id, SdnWithdrawRequest(), db=s)
                finally:
                    s.close()
            tw = threading.Thread(target=run_withdraw)
            tw.start()
            assert entered.wait(timeout=15)

            tr = threading.Thread(target=run_reconcile)
            tr.start()
            tr.join(timeout=15)

            assert len(executor_calls) == 1
            _assert_reconcile_rejected(client, db, op_id, reconcile_resp[0], collector_calls)

            release.set()
            tw.join(timeout=20)
    finally:
        release.set()
        if tw is not None:
            tw.join(timeout=5)
        if tr is not None:
            tr.join(timeout=5)


# ── CR31: unknown 普通 reconcile 只有一个并发赢家 ──

def test_cr31_unknown_reconcile_single_winner(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    op_id = op["operation_id"]

    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []
    results_lock = threading.Lock()

    def run():
        s = SessionLocal()
        try:
            r = reconcile_operation(op_id, db=s)
            with results_lock:
                results.append(r)
        finally:
            s.close()

    t1 = None
    t2 = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, calls)):
            t1 = threading.Thread(target=run)
            t1.start()
            assert entered.wait(timeout=15)

            t2 = threading.Thread(target=run)
            t2.start()
            t2.join(timeout=15)

            assert len(calls) == 1  # 只有一个赢家进入 collector
            assert len(results) == 1
            assert results[0].success is False
            assert results[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "reconcile").count() == 1

            release.set()
            t1.join(timeout=20)
    finally:
        release.set()
        if t1 is not None:
            t1.join(timeout=5)
        if t2 is not None:
            t2.join(timeout=5)

    # 赢家收尾（collector 失败 → 条件收尾到 unknown）
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "unknown"


# ── CR31: active phase 失联租约——未过 lease 拒绝；过 lease 单赢家接管且无设备写重放 ──

def test_cr31_stale_takeover_rejected_within_lease(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)
    # 直接构造 active phase（applying）+ 近期 active_started_at（未过 lease）
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({
        "status": "applying", "active_attempt_id": exec_attempt.id, "active_started_at": datetime.utcnow(),
    })
    db.commit()

    collector_calls = []
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(threading.Event(), threading.Event(), collector_calls)):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is False
    assert resp.error_key == "sdn.operation_in_progress"
    assert len(collector_calls) == 0
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "applying"


def test_cr31_stale_takeover_succeeds_past_lease(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    op_id = op["operation_id"]
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op_id).first()

    # 构造 admission 后崩溃：op 处于 active phase + 旧 attempt/started unit + 过期 active_started_at
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    # 把 execute attempt 的一个 unit 置为 started（模拟崩溃半途），attempt 置于真实活动态 running
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == exec_attempt.id).first()
    if unit is not None:
        unit.state = "started"
    exec_attempt.status = "running"
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({
        "status": "applying",
        "active_attempt_id": exec_attempt.id,
        "active_started_at": datetime.utcnow() - timedelta(seconds=STALE_ACTION_LEASE_SECONDS + 30),
    })
    db.commit()

    # 准备可依据回读收尾的 scoped 证据（port_bind → present：service-instance + xconnect vsi 双标记）
    cmd = f"display current-configuration interface {binding.interface_name}"
    output = f"service-instance {binding.service_instance}\n xconnect vsi {vpc.vsi_name}"
    snap = SdnValidationSnapshot(
        vpc_id=vpc.id, device_id=device.id, validation_result="active",
        snapshot_data=json.dumps({"commands": {cmd: {"success": True, "output": output, "error": None}}}),
    )
    db.add(snap)
    db.commit()

    executor_calls = []
    def _no_executor(self, db, dep_id, *, unit_hooks=None):
        executor_calls.append(threading.get_ident())
        raise AssertionError("device write must not be replayed during reconcile")
    def _snap_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return snap, None, False

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_no_executor), \
         patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_snap_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is True
    assert resp.data["reconciled"] is True
    assert len(executor_calls) == 0  # 无设备写重放
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status in ("awaiting_validation", "succeeded")
    assert refreshed.active_attempt_id is None  # 收尾后清空 token
    assert len(_active_claims(db, op_id)) == 0  # 明确解析后释放 claims


# ── CR31: reconcile collector 失败/迟到收尾不覆盖 withdrawn、不释放 claims ──

def test_cr31_reconcile_collector_fail_keeps_claims(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    op_id = op["operation_id"]

    def _err_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return None, {"key": "sdn.device_not_writable", "params": {}}, False

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_err_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is False
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "unknown"
    # collector 失败不释放 claims（仍 active/ambiguous）
    assert len(_active_claims(db, op_id)) > 0


def test_cr31_reconcile_late_finish_does_not_overwrite_withdrawn(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    op_id = op["operation_id"]

    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def run():
        s = SessionLocal()
        try:
            results.append(reconcile_operation(op_id, db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector(entered, release, calls)):
            t = threading.Thread(target=run)
            t.start()
            assert entered.wait(timeout=15)

            # 模拟 reconcile 采集期间，并发动作把 op 终态收尾为 withdrawn
            db.query(SdnOperation).filter(SdnOperation.id == op_id).update({
                "status": "withdrawn", "active_attempt_id": None, "active_started_at": None,
            })
            db.commit()

            release.set()
            t.join(timeout=20)
    finally:
        release.set()
        if t is not None:
            t.join(timeout=5)

    assert len(results) == 1
    assert results[0].success is False  # collector 失败路径
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "withdrawn"  # 未被 reconcile 覆盖
    # reconcile 收尾 CAS 零行不得释放/改动 claims（并发动作未释放时仍保持原样）
    assert len(_active_claims(db, op_id)) == 4
