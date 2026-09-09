"""S1-014 对抗性测试：CR32 stale takeover 正确归属 active attempt vs effect attempt。

真实线程/直接构造 + 阻塞/回读。证明：
- validating 失联时 active(validate)≠effect(execute)，execute 已确定终态不被降级；
- applying/withdrawing 失联时 active==effect，started unit 标 unknown 后按回读解析；
- token 指向不存在/他 operation 的 attempt 时保守拒绝，不采集、不改 attempt/claim。
"""
import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAttempt, SdnAttemptUnit, SdnDeployment, SdnOperation, SdnPortBinding, SdnValidationSnapshot
from app.routers.sdn_access import reconcile_operation
from app.services.sdn_operation_service import (
    STALE_ACTION_LEASE_SECONDS,
    create_attempt,
    finish_attempt,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_s1_007_adversarial import _active_claims, _do_access, _seed_ready, _seed_unknown_port_unbind  # noqa: E402
from test_s1_010_adversarial import _seed_awaiting_validation  # noqa: E402


def _set_active_phase(db, op_id, status, token_id, *, past=True):
    started = datetime.utcnow() - timedelta(seconds=STALE_ACTION_LEASE_SECONDS + 30) if past else datetime.utcnow()
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update(
        {"status": status, "active_attempt_id": token_id, "active_started_at": started},
        synchronize_session=False,
    )
    db.commit()


def _make_snap(db, vpc, device, binding, output):
    cmd = f"display current-configuration interface {binding.interface_name}"
    snap = SdnValidationSnapshot(
        vpc_id=vpc.id, device_id=device.id, validation_result="active",
        snapshot_data=json.dumps({"commands": {cmd: {"success": True, "output": output, "error": None}}}),
    )
    db.add(snap)
    db.commit()
    return snap


def _no_executor(self, db, dep_id, *, unit_hooks=None):
    raise AssertionError("device write must not be replayed during reconcile")


# ── CR32: stale validating takeover——active(validate)≠effect(execute)，execute 不降级 ──

def test_cr32_stale_validating_takeover_preserves_succeeded_execute(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    # 原 execute attempt 已确定成功；active 是失联的 validate attempt（claimed）
    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    finish_attempt(db, exec_attempt.id, "succeeded")
    exec_unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == exec_attempt.id).first()
    if exec_unit is not None:
        exec_unit.state = "succeeded"
    validate_attempt = create_attempt(db, operation_id=op_id, kind="validate", owner="stale-validate")
    _set_active_phase(db, op_id, "validating", validate_attempt.id, past=True)

    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op_id).first()
    # 依据原 port_bind 回读恢复到 awaiting_validation（不冒充完整业务验证成功）
    snap = _make_snap(db, vpc, device, binding, f"service-instance {binding.service_instance}\n xconnect vsi {vpc.vsi_name}")

    executor_calls = []
    def _snap_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return snap, None, False

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_no_executor), \
         patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_snap_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is True
    assert resp.data["reconciled"] is True
    db.expire_all()
    # 关键：execute 已确定成功不被降级；validate 失联动作被标 unknown
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == "succeeded"
    assert db.query(SdnAttempt).filter(SdnAttempt.id == validate_attempt.id).first().status == "unknown"
    # 新 reconcile attempt 独立留痕
    rec_attempts = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "reconcile").all()
    assert len(rec_attempts) == 1
    assert rec_attempts[0].status == "succeeded"
    # op 恢复到 awaiting_validation（port_bind 存在 ≠ 完整业务验证成功），token 清空
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "awaiting_validation"
    assert refreshed.active_attempt_id is None


# ── CR32: stale applying takeover——active==effect(execute)，started unit 标 unknown ──

def test_cr32_stale_applying_takeover_marks_started_unit_unknown(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]

    exec_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "execute").first()
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == exec_attempt.id).first()
    unit.state = "started"  # 模拟崩溃半途
    _set_active_phase(db, op_id, "applying", exec_attempt.id, past=True)

    def _err_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return None, {"key": "sdn.device_not_writable", "params": {}}, False

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_no_executor), \
         patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_err_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is False
    db.expire_all()
    # active==effect：execute attempt 标 unknown，started unit 标 unknown
    assert db.query(SdnAttempt).filter(SdnAttempt.id == exec_attempt.id).first().status == "unknown"
    assert db.query(SdnAttemptUnit).filter(SdnAttemptUnit.id == unit.id).first().state == "unknown"


# ── CR32: stale withdrawing takeover——active==effect(withdraw)，按回读解析为 withdrawn ──

def test_cr32_stale_withdrawing_takeover_resolves_via_readback(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    op_id = op["operation_id"]

    withdraw_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").first()
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == withdraw_attempt.id).first()
    unit.state = "started"
    withdraw_attempt.status = "running"  # 真实活动态（崩溃半途）
    _set_active_phase(db, op_id, "withdrawing", withdraw_attempt.id, past=True)

    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op_id).first()
    # 配置缺失（scoped）→ 撤回成功
    snap = _make_snap(db, vpc, device, binding, "interface GigabitEthernet1/0/1")

    def _snap_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        return snap, None, False

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_no_executor), \
         patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_snap_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is True
    assert resp.data["reconciled"] is True
    db.expire_all()
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "withdrawn"
    assert refreshed.active_attempt_id is None
    # 无设备写重放
    assert db.query(SdnAttempt).filter(SdnAttempt.id == withdraw_attempt.id).first().status in ("succeeded", "failed_known")


# ── CR32: token 指向不存在/他 operation 的 attempt → 保守拒绝，不采集、不改 attempt/claim ──

def test_cr32_stale_takeover_rejects_invalid_token(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]

    # 指向不存在的 attempt
    _set_active_phase(db, op_id, "applying", 999999, past=True)

    collector_calls = []
    def _count_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        collector_calls.append(threading.get_ident())
        return None, {"key": "sdn.device_not_writable", "params": {}}, False

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_count_sync):
        resp = reconcile_operation(op_id, db=SessionLocal())

    assert resp.success is False
    assert resp.error_key == "sdn.operation_in_progress"
    assert len(collector_calls) == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "reconcile").count() == 0
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op_id).first()
    assert refreshed.status == "applying"  # 未被改动
    assert refreshed.active_attempt_id == 999999


def test_cr32_stale_takeover_rejects_other_operation_token(client, db):
    device, _, vpc = _seed_ready(client, db)
    op_a = _do_access(client, db, device, vpc, auto_apply=False, idempotency_key="op-a-token-test")
    op_a_id = op_a["operation_id"]

    # 手工构造另一个 operation + 其 execute attempt（避免与 op_a 的 claims 冲突）
    op_b = SdnOperation(
        idempotency_key="op-b-token-test", fingerprint="f", operation_type="terminal_access",
        tenant_id=vpc.tenant_id, vpc_id=vpc.id, device_id=device.id, status="planned",
    )
    db.add(op_b)
    db.flush()
    op_b_exec = create_attempt(db, operation_id=op_b.id, kind="execute", owner="other-op")
    db.commit()

    # op_a 的 active token 指向 op_b 的 execute attempt（跨 operation）
    _set_active_phase(db, op_a_id, "applying", op_b_exec.id, past=True)

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        resp = reconcile_operation(op_a_id, db=SessionLocal())

    assert resp.success is False
    assert resp.error_key == "sdn.operation_in_progress"
    assert mock_sync.call_count == 0
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_a_id, SdnAttempt.kind == "reconcile").count() == 0
    assert db.query(SdnOperation).filter(SdnOperation.id == op_a_id).first().status == "applying"
