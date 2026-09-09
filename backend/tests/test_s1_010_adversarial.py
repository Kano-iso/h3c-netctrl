"""S1-010 对抗性测试：CR27 complete/validate 并发准入。

真实线程 + barrier：证明同一 operation 至多一个 validate attempt 进入 collector/ping，
unknown 恢复同样只有一个赢家；准入后崩溃留下 validating 痕迹不回退、不重放。
"""
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAttempt, SdnDeployment, SdnOperation, SdnValidationSnapshot
from app.routers.sdn_access import complete_access
from app.schemas import SdnAccessCompleteRequest
from app.services.sdn_operation_service import (
    device_port_key,
    release_claims,
    tenant_key,
    vpc_device_key,
    vpc_key,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402
from test_s1_007_adversarial import _active_claims, _do_access  # noqa: E402


def _seed_awaiting_validation(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_bind").first()
    dep.status = "success"
    dep.config_completed_at = datetime.utcnow() - timedelta(seconds=10)
    # 模拟 apply 成功：释放全部 4 条 scoped claims + 进入 awaiting_validation
    release_claims(db, [
        tenant_key(vpc.tenant_id), vpc_key(vpc.id),
        vpc_device_key(vpc.id, device.id), device_port_key(device.id, 1),
    ], owner_operation_id=op_id)
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({"status": "awaiting_validation"})
    db.commit()
    return device, vpc, op_id


def _blocking_sync(entered, release, collector_calls, call_lock):
    def _fake_sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        with call_lock:
            collector_calls.append(threading.get_ident())
        entered.set()
        release.wait(timeout=20)
        # 采集失败 → 赢者收尾为 unknown（简化，不依赖 active 快照组装）
        return None, {"key": "sdn.device_not_writable", "params": {}}, False
    return _fake_sync


def _worker(op_id, results, results_lock):
    s = SessionLocal()
    try:
        resp = complete_access(op_id, SdnAccessCompleteRequest(force_validation=True), db=s)
        with results_lock:
            results.append(resp)
    finally:
        s.close()


# ── CR27: awaiting_validation 并发只有一个赢家 ──

def test_cr27_concurrent_complete_single_winner(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    entered = threading.Event()
    release = threading.Event()
    collector_calls = []
    call_lock = threading.Lock()
    results = []
    results_lock = threading.Lock()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_sync(entered, release, collector_calls, call_lock)):
        t1 = threading.Thread(target=_worker, args=(op_id, results, results_lock))
        t2 = threading.Thread(target=_worker, args=(op_id, results, results_lock))
        t1.start(); t2.start()

        # 等赢者进入 collector
        assert entered.wait(timeout=15)
        # 等输家返回（此时只有一个 in-progress 结果）
        deadline = time.time() + 15
        while len(results) < 1 and time.time() < deadline:
            time.sleep(0.02)

        # 中间态：只有一个 collector 调用、一个活跃 validate attempt、op validating
        with call_lock:
            assert len(collector_calls) == 1
        db.expire_all()
        assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "validating"
        attempts = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").all()
        assert len(attempts) == 1 and attempts[0].status == "claimed"
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error_key == "sdn.operation_in_progress"

        release.set()
        t1.join(timeout=20)
        t2.join(timeout=20)

    assert len(results) == 2
    successes = [r for r in results if r.success is True]
    failures = [r for r in results if r.success is False]
    assert len(successes) == 1 and len(failures) == 1
    assert failures[0].error_key == "sdn.operation_in_progress"
    assert successes[0].data["status"] == "unknown"

    db.expire_all()
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").count() == 1
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "unknown"


# ── CR27: unknown 恢复并发同样只有一个赢家 ──

def test_cr27_concurrent_unknown_recovery_single_winner(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)

    # 第一次 complete 采集失败 → unknown validation（旧 unknown attempt 保留）
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(None, {"key": "sdn.device_not_writable", "params": {}}, False)):
        r1 = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True})
    assert r1.json()["data"]["status"] == "unknown"
    db.expire_all()
    old_attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").first()
    assert old_attempt.status == "unknown"

    entered = threading.Event()
    release = threading.Event()
    collector_calls = []
    call_lock = threading.Lock()
    results = []
    results_lock = threading.Lock()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", new=_blocking_sync(entered, release, collector_calls, call_lock)):
        t1 = threading.Thread(target=_worker, args=(op_id, results, results_lock))
        t2 = threading.Thread(target=_worker, args=(op_id, results, results_lock))
        t1.start(); t2.start()

        assert entered.wait(timeout=15)
        deadline = time.time() + 15
        while len(results) < 1 and time.time() < deadline:
            time.sleep(0.02)

        with call_lock:
            assert len(collector_calls) == 1
        db.expire_all()
        attempts = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").order_by(SdnAttempt.id.asc()).all()
        assert len(attempts) == 2
        assert attempts[0].status == "unknown"  # 旧历史保留
        assert attempts[1].status == "claimed"  # 新赢家 attempt
        assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "validating"
        assert len(results) == 1
        assert results[0].error_key == "sdn.operation_in_progress"

        release.set()
        t1.join(timeout=20)
        t2.join(timeout=20)

    db.expire_all()
    attempts = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").order_by(SdnAttempt.id.asc()).all()
    assert len(attempts) == 2
    assert attempts[0].status == "unknown"
    assert attempts[1].status == "unknown"  # 新 attempt 采集失败收尾，旧历史不丢


# ── CR27: 准入后崩溃留下的 validating 痕迹不回退、不重放 ──

def test_cr27_validating_stuck_not_replayed(client, db):
    device, vpc, op_id = _seed_awaiting_validation(client, db)
    # 模拟准入后崩溃：op validating + 一个 claimed attempt（无终态）
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({"status": "validating"})
    db.add(SdnAttempt(operation_id=op_id, kind="validate", status="claimed", owner=str(op_id)))
    db.commit()
    db.expire_all()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        r = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True})
    assert r.status_code == 200
    assert r.json()["error_key"] == "sdn.operation_in_progress"
    mock_sync.assert_not_called()  # 不重复进入 collector/ping

    db.expire_all()
    assert db.query(SdnOperation).filter(SdnOperation.id == op_id).first().status == "validating"
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").count() == 1
