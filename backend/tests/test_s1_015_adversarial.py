"""S1-015 对抗性测试：CR35 收紧 stale takeover 的 active attempt 身份与终态保护。

证明（先在 S1-014 现状失败，再修到通过）：
- phase→kind 唯一映射（applying→execute / validating→validate / withdrawing→withdraw）；
- 同 operation 错 kind token 被拒；
- 终态（succeeded/failed/failed_known/unknown）attempt 不可被 takeover 再次降级；
- 正确 kind + 活动态（claimed/running）仍可 takeover；
- 真实线程/barrier：attempt 在读取后、CAS 前被转终态 → CAS 失败且不覆盖终态。
"""
import json
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.database import SessionLocal
from app.models import SdnAttempt, SdnAttemptUnit, SdnOperation, SdnPortBinding, SdnVpc
from app.routers.sdn_access import reconcile_operation
from app.services.sdn_operation_service import (
    STALE_ACTION_LEASE_SECONDS,
    claim_stale_takeover,
    create_attempt,
    finish_attempt,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_s1_007_adversarial import _do_access, _seed_ready, _seed_unknown_port_unbind  # noqa: E402
from test_s1_010_adversarial import _seed_awaiting_validation  # noqa: E402
from test_s1_014_adversarial import _make_snap, _no_executor, _set_active_phase  # noqa: E402


def _assert_rejected_clean(resp, db, op_id, *, expect_status, expect_token):
    """统一保守拒绝断言：in-progress + 不采集/不写 executor + 无 reconcile attempt + op 不变。"""
    assert resp.success is False
    assert resp.error_key == "sdn.operation_in_progress"
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "reconcile").count() == 0
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == expect_status
    assert refreshed.active_attempt_id == expect_token


# ── CR35: applying 持有同 operation 的 validate token → 拒绝 ──

def test_cr35_applying_with_validate_token_rejected(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    validate_attempt = create_attempt(db, operation_id=op_id, kind="validate", owner="wrong-kind")
    _set_active_phase(db, op_id, "applying", validate_attempt.id, past=True)  # 错 kind：applying 应持 execute

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync, \
         patch("app.routers.sdn_access.SdnDeploymentExecutor.execute") as mock_exec:
        resp = reconcile_operation(op_id, db=SessionLocal())

    _assert_rejected_clean(resp, db, op_id, expect_status="applying", expect_token=validate_attempt.id)
    assert mock_sync.call_count == 0
    assert mock_exec.call_count == 0
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == "claimed"  # 原 execute 不变


# ── CR35: validating 持有 succeeded execute token → 拒绝且 execute 历史不变 ──

def test_cr35_validating_with_succeeded_execute_token_rejected(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    finish_attempt(db, exec_attempt.id, "succeeded")
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == exec_attempt.id).first()
    if unit is not None:
        unit.state = "succeeded"
    _set_active_phase(db, op_id, "validating", exec_attempt.id, past=True)  # 错 kind：validating 应持 validate

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        resp = reconcile_operation(op_id, db=SessionLocal())

    _assert_rejected_clean(resp, db, op_id, expect_status="validating", expect_token=exec_attempt.id)
    assert mock_sync.call_count == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == "succeeded"  # 历史完全不变


# ── CR35: withdrawing 持有终态 withdraw token → 拒绝且历史不变 ──

def test_cr35_withdrawing_with_terminal_withdraw_token_rejected(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    op_id = op["operation_id"]
    withdraw_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").first()
    finish_attempt(db, withdraw_attempt.id, "succeeded")
    _set_active_phase(db, op_id, "withdrawing", withdraw_attempt.id, past=True)  # 正确 kind 但终态

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        resp = reconcile_operation(op_id, db=SessionLocal())

    _assert_rejected_clean(resp, db, op_id, expect_status="withdrawing", expect_token=withdraw_attempt.id)
    assert mock_sync.call_count == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.id == withdraw_attempt.id).first().status == "succeeded"  # 历史不变


# ── CR35: 正确 kind 但终态/unknown → 逐类拒绝 ──

@pytest.mark.parametrize("terminal_status", ["unknown", "failed", "failed_known", "succeeded"])
def test_cr35_applying_with_terminal_execute_token_rejected(client, db, terminal_status):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    exec_attempt.status = terminal_status
    _set_active_phase(db, op_id, "applying", exec_attempt.id, past=True)  # 正确 kind 但不可接管

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        resp = reconcile_operation(op_id, db=SessionLocal())

    _assert_rejected_clean(resp, db, op_id, expect_status="applying", expect_token=exec_attempt.id)
    assert mock_sync.call_count == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == terminal_status  # 不降级


# ── CR35: 正确 kind + 活动态（claimed/running）仍可单赢家 takeover ──

@pytest.mark.parametrize("active_status", ["claimed", "running"])
def test_cr35_stale_takeover_allows_active_attempt(client, db, active_status):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]

    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == exec_attempt.id).first()
    if unit is not None:
        unit.state = "started"
    exec_attempt.status = active_status
    _set_active_phase(db, op_id, "applying", exec_attempt.id, past=True)

    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op_id).first()
    vpc_obj = db.query(SdnVpc).filter(SdnVpc.id == vpc.id).first()
    snap = _make_snap(db, vpc, device, binding, f"service-instance {binding.service_instance}\n xconnect vsi {vpc_obj.vsi_name}")

    def _snap_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return snap, None, False

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_no_executor), \
         patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_snap_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is True
    assert resp.data["reconciled"] is True
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status in ("awaiting_validation", "succeeded")
    assert refreshed.active_attempt_id is None


# ── CR35: 真实线程/barrier——attempt 在读取后、CAS 前被转终态 → CAS 失败且不覆盖终态 ──

def test_cr35_cas_rejects_when_attempt_terminalized_between_read_and_cas(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    exec_attempt.status = "claimed"
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({
        "status": "applying",
        "active_attempt_id": exec_attempt.id,
        "active_started_at": datetime.utcnow() - timedelta(seconds=STALE_ACTION_LEASE_SECONDS + 30),
    }, synchronize_session=False)
    db.commit()

    entered = threading.Event()
    release = threading.Event()
    results = []

    def worker():
        # 1) Python「读取」阶段（模拟旧实现的先读后改）：读 op + attempt，随后立即关闭会话释放锁
        s0 = SessionLocal()
        try:
            op_read = s0.query(SdnOperation).filter(SdnOperation.id == op_id).first()
            att_read = s0.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first()
            assert op_read.active_attempt_id == exec_attempt.id
            assert att_read.status in ("claimed", "running")
        finally:
            s0.close()
        entered.set()
        release.wait(timeout=10)
        # 2) 原子 CAS 阶段：fresh session，EXISTS 必须在同一 UPDATE 内重新校验 attempt 状态
        s2 = SessionLocal()
        try:
            results.append(claim_stale_takeover(
                s2, op_id, from_status="applying", old_active_attempt_id=exec_attempt.id,
                new_active_attempt_id=999999, expected_kind="execute",
            ))
            s2.commit()
        finally:
            s2.close()

    t = threading.Thread(target=worker)
    t.start()
    try:
        assert entered.wait(timeout=10)
        # 并发动作：在读取之后、CAS 之前把 attempt 转为终态
        db.expire_all()
        exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first()
        exec_attempt.status = "succeeded"
        db.commit()

        release.set()
        t.join(timeout=15)
    finally:
        release.set()
        t.join(timeout=5)

    assert results == [False]  # CAS 因 EXISTS 失败而拒绝
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == "succeeded"  # 未覆盖终态
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "applying"  # op 未被抢占
