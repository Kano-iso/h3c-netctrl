"""S1-012 对抗性测试：CR29 apply 纳入同一 operation 动作仲裁。

真实线程 + 阻塞 barrier：证明 apply/withdraw/validate 共享持久化动作仲裁，
apply 先赢时 withdraw 不建 attempt/deployment/不进 executor，反之亦然；
两个并发 apply 只有一个赢家；apply 迟到收尾不覆盖现状、不误释放 claims。
"""
import threading
import time
from datetime import datetime
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAttempt, SdnDeployment, SdnOperation
from app.routers.sdn_access import apply_access, withdraw_access
from app.schemas import SdnWithdrawRequest
from app.services.sdn_operation_service import (
    device_port_key,
    release_claims,
    tenant_key,
    vpc_device_key,
    vpc_key,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _seed_ready  # noqa: E402
from test_s1_007_adversarial import _active_claims, _do_access  # noqa: E402


def _seed_awaiting_wiring(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    return device, vpc, op["operation_id"]


def _blocking_executor(entered, release, executor_calls, unit_name):
    def _fake(self, db, dep_id, *, unit_hooks=None):
        executor_calls.append(threading.get_ident())
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


# ── CR29: apply 先赢，withdraw 被准入 CAS 拒绝 ──

def test_cr29_apply_wins_withdraw_blocked(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    apply_resp = []
    withdraw_resp = []

    def run_apply():
        s = SessionLocal()
        try:
            apply_resp.append(apply_access(op_id, db=s))
        finally:
            s.close()

    def run_withdraw():
        s = SessionLocal()
        try:
            withdraw_resp.append(withdraw_access(op_id, SdnWithdrawRequest(), db=s))
        finally:
            s.close()

    ta = None
    tw = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-bind")):
            # apply 先准入，阻塞在原 port_bind executor
            ta = threading.Thread(target=run_apply)
            ta.start()
            assert entered.wait(timeout=15)

            # 此时 apply 已持有 applying 准入，再发 withdraw
            tw = threading.Thread(target=run_withdraw)
            tw.start()
            tw.join(timeout=15)

            assert len(executor_calls) == 1  # 只有 bind I/O
            assert len(withdraw_resp) == 1
            assert withdraw_resp[0].success is False
            assert withdraw_resp[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "applying"
            assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").count() == 0
            assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_unbind").count() == 0

            release.set()
            ta.join(timeout=20)
    finally:
        release.set()
        if ta is not None:
            ta.join(timeout=5)
        if tw is not None:
            tw.join(timeout=5)

    # apply 正常收尾 → awaiting_validation；withdraw 仍未建 attempt/deployment
    assert len(apply_resp) == 1
    assert apply_resp[0].success is True
    assert apply_resp[0].data["status"] == "awaiting_validation"
    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "withdraw").count() == 0
    assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_unbind").count() == 0


# ── CR29: withdraw 先赢，apply 被准入 CAS 拒绝 ──

def test_cr29_withdraw_wins_apply_blocked(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    apply_resp = []
    withdraw_resp = []

    def run_apply():
        s = SessionLocal()
        try:
            apply_resp.append(apply_access(op_id, db=s))
        finally:
            s.close()

    def run_withdraw():
        s = SessionLocal()
        try:
            withdraw_resp.append(withdraw_access(op_id, SdnWithdrawRequest(), db=s))
        finally:
            s.close()

    ta = None
    tw = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-unbind")):
            # withdraw 先准入，阻塞在 port_unbind executor
            tw = threading.Thread(target=run_withdraw)
            tw.start()
            assert entered.wait(timeout=15)

            # 此时 withdraw 已持有 withdrawing 准入，再发 apply
            ta = threading.Thread(target=run_apply)
            ta.start()
            ta.join(timeout=15)

            assert len(executor_calls) == 1  # 只有 unbind I/O，apply 未调 port_bind executor
            assert len(apply_resp) == 1
            assert apply_resp[0].success is False
            assert apply_resp[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawing"
            # 原 execute attempt/deployment 未被 apply 改动
            assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_bind").first().status == "pending"

            release.set()
            tw.join(timeout=20)
    finally:
        release.set()
        if ta is not None:
            ta.join(timeout=5)
        if tw is not None:
            tw.join(timeout=5)

    # withdraw 正常收尾 → withdrawn
    assert len(withdraw_resp) == 1
    assert withdraw_resp[0].success is True
    assert withdraw_resp[0].data["status"] == "withdrawn"
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawn"


# ── CR29: 两个并发 apply 只有一个赢家 ──

def test_cr29_concurrent_apply_single_winner(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    results = []
    results_lock = threading.Lock()

    def run_apply():
        s = SessionLocal()
        try:
            r = apply_access(op_id, db=s)
            with results_lock:
                results.append(r)
        finally:
            s.close()

    t1 = None
    t2 = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-bind")):
            t1 = threading.Thread(target=run_apply)
            t1.start()
            assert entered.wait(timeout=15)

            t2 = threading.Thread(target=run_apply)
            t2.start()
            t2.join(timeout=15)

            # 中间态：只有一次 executor/I/O，输家无副作用
            assert len(executor_calls) == 1
            assert len(results) == 1
            assert results[0].success is False
            assert results[0].error_key == "sdn.operation_in_progress"
            db.expire_all()
            assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "applying"

            release.set()
            t1.join(timeout=20)
    finally:
        release.set()
        if t1 is not None:
            t1.join(timeout=5)
        if t2 is not None:
            t2.join(timeout=5)

    # 赢家收尾一致：awaiting_validation + deployment success + execute attempt succeeded
    assert len(results) == 2
    winners = [r for r in results if r.success is True]
    losers = [r for r in results if r.success is False]
    assert len(winners) == 1 and len(losers) == 1
    assert winners[0].data["status"] == "awaiting_validation"
    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "awaiting_validation"
    assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_bind").first().status == "success"


# ── CR29: apply 迟到收尾不覆盖现状、不误释放 claims ──

def test_cr29_late_apply_does_not_overwrite_withdrawn(client, db):
    device, vpc, op_id = _seed_awaiting_wiring(client, db)

    entered = threading.Event()
    release = threading.Event()
    executor_calls = []
    results = []

    def run_apply():
        s = SessionLocal()
        try:
            results.append(apply_access(op_id, db=s))
        finally:
            s.close()

    t = None
    try:
        with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", new=_blocking_executor(entered, release, executor_calls, "port-bind")):
            t = threading.Thread(target=run_apply)
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
    assert results[0].data["status"] == "withdrawn"  # 未被迟到 apply 覆盖
    assert results[0].data.get("note") == "late completion: status changed by concurrent action"

    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "withdrawn"
    assert _active_claims(db, op_id) == []
