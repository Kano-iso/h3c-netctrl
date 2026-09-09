"""S1-011 对抗性测试：CR28 validate 与 withdraw 跨动作并发仲裁。

真实线程 + 阻塞 barrier：证明同一 operation 的 validate 与 withdraw 互斥，
无论谁先取得动作准入，另一方不得创建有效 attempt/deployment、不得进入 I/O；
迟到收尾的条件 CAS 不覆盖 withdrawn、不误释放 claims。
"""
import threading
import time
from datetime import datetime
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAttempt, SdnDeployment, SdnOperation
from app.routers.sdn_access import complete_access, withdraw_access
from app.schemas import SdnAccessCompleteRequest, SdnWithdrawRequest
from app.services.sdn_operation_service import (
    device_port_key,
    release_claims,
    tenant_key,
    vpc_device_key,
    vpc_key,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_s1_010_adversarial import _seed_awaiting_validation  # noqa: E402
from test_s1_007_adversarial import _active_claims  # noqa: E402


def _blocking_collector_sync(entered, release, collector_calls):
    def _fake_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        collector_calls.append(threading.get_ident())
        entered.set()
        release.wait(timeout=20)
        return None, {"key": "sdn.device_not_writable", "params": {}}, False
    return _fake_sync


# ── CR28: validate 先赢，withdraw 被准入 CAS 拒绝 ──

def test_cr28_validate_wins_withdraw_blocked(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    collector_calls = []
    executor_calls = []
    complete_resp = []
    withdraw_resp = []

    def _record_executor(self, db, dep_id, *, unit_hooks=None):
        executor_calls.append(threading.get_ident())
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        d.status = "unknown"
        db.commit()
        return d

    def run_complete():
        s = SessionLocal()
        try:
            complete_resp.append(complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s))
        finally:
            s.close()

    def run_withdraw():
        s = SessionLocal()
        try:
            withdraw_resp.append(withdraw_access(op_id, SdnWithdrawRequest(), db=s))
        finally:
            s.close()

    tc = None
    tw = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_collector_sync(entered, release, collector_calls)), \
             patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_record_executor):
            # validate 先准入，阻塞在 collector
            tc = threading.Thread(target=run_complete)
            tc.start()
            assert entered.wait(timeout=15)

            # 此时 validate 已持有 validating 准入，再发 withdraw
            tw = threading.Thread(target=run_withdraw)
            tw.start()
            tw.join(timeout=15)

            # 中间态：validate 已准入，withdraw 被拒绝，未进入任何设备 I/O
            assert len(collector_calls) == 1
            assert len(executor_calls) == 0
            assert len(withdraw_resp) == 1
            assert withdraw_resp[0].success is False
            assert withdraw_resp[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "validating"
            assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").count() == 0
            assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_unbind").count() == 0

            release.set()
            tc.join(timeout=20)
    finally:
        release.set()
        if tc is not None:
            tc.join(timeout=5)
        if tw is not None:
            tw.join(timeout=5)

    # validate 正常收尾（采集失败 → unknown）；withdraw 仍未建 attempt/deployment
    assert len(complete_resp) == 1
    assert complete_resp[0].success is True
    assert complete_resp[0].data["status"] == "unknown"
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").count() == 0
    assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_unbind").count() == 0


# ── CR28: withdraw 先赢，complete 被准入 CAS 拒绝 ──

def test_cr28_withdraw_wins_complete_blocked(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    collector_calls = []
    complete_resp = []
    withdraw_resp = []

    def _blocking_executor(self, db, dep_id, *, unit_hooks=None):
        entered.set()
        release.wait(timeout=20)
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_success(0, "port-unbind")
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    def _no_collector(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        collector_calls.append(threading.get_ident())
        return None, {"key": "sdn.device_not_writable", "params": {}}, False

    def run_complete():
        s = SessionLocal()
        try:
            complete_resp.append(complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s))
        finally:
            s.close()

    def run_withdraw():
        s = SessionLocal()
        try:
            withdraw_resp.append(withdraw_access(op_id, SdnWithdrawRequest(), db=s))
        finally:
            s.close()

    tc = None
    tw = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_no_collector), \
             patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor):
            # withdraw 先准入，阻塞在 executor
            tw = threading.Thread(target=run_withdraw)
            tw.start()
            assert entered.wait(timeout=15)

            # 此时 withdraw 已持有 withdrawing 准入，再发 complete
            tc = threading.Thread(target=run_complete)
            tc.start()
            tc.join(timeout=15)

            # 中间态：withdraw 已准入，complete 被拒绝，未进入 collector/ping
            assert len(collector_calls) == 0
            assert len(complete_resp) == 1
            assert complete_resp[0].success is False
            assert complete_resp[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawing"
            assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").count() == 0

            release.set()
            tw.join(timeout=20)
    finally:
        release.set()
        if tc is not None:
            tc.join(timeout=5)
        if tw is not None:
            tw.join(timeout=5)

    # withdraw 成功 → withdrawn；complete 仍未建 validate attempt
    assert len(withdraw_resp) == 1
    assert withdraw_resp[0].success is True
    assert withdraw_resp[0].data["status"] == "withdrawn"
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawn"
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").count() == 0


# ── CR28: 迟到收尾的条件 CAS 不覆盖 withdrawn、不误释放 claims ──

def test_cr28_late_complete_does_not_overwrite_withdrawn(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    results = []

    def _blocking_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        entered.set()
        release.wait(timeout=20)
        return None, {"key": "sdn.device_not_writable", "params": {}}, False

    def worker():
        s = SessionLocal()
        try:
            results.append(complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_sync):
            t = threading.Thread(target=worker)
            t.start()
            assert entered.wait(timeout=15)

            # 模拟并发 withdraw 已终态收尾：op=withdrawn + 释放全部 claims
            db.query(SdnOperation).filter(SdnOperation.id == op_id).update({"status": "withdrawn"})
            release_claims(db, [
                tenant_key(vpc.tenant_id), vpc_key(vpc.id),
                vpc_device_key(vpc.id, device.id), device_port_key(device.id, 1),
            ], owner_operation_id=op_id)
            db.commit()

            release.set()
            t.join(timeout=20)
    finally:
        release.set()
        if t is not None:
            t.join(timeout=5)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data["status"] == "withdrawn"  # 未被迟到 validate 覆盖
    assert results[0].data.get("note") == "late completion: status changed by concurrent action"

    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawn"
    # validate 迟到收尾不得把已释放的 claims 重新标 ambiguous
    assert _active_claims(db, op_id) == []
