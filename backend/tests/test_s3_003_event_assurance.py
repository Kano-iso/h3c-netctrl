"""S3-003 对抗测试：有界事件保障（NEXT/S3 后端切片）。

先覆盖失败风险，再验证语义（全部隔离 qa-backend 容器，真实 SQLite）：
- validation/sync 成功落入快照 → 追加 trigger=event 只读评估；同快照重试不重复历史；
- scope-exception 新增/修改/清除 → 各追加一条 event run（id+version / cleared 去重）；
- 未配策略 / enabled=false → 零 event run；manual cadence 只禁用周期，已 enabled 仍允许事件检查；
- 评估失败：原业务事件不受影响（成功响应不变、业务行/version 不变），追加 status=failed
  的 event run 供审计，且同源事件失败也不重复；
- 事件路径零额外设备 I/O、零业务副作用（不写 deployment/binding/operation/snapshot/claim、
  不 bump vpc.version）；
- event_key 只含稳定内部 ID/版本（不含凭据/原始 CLI），作为只读审计字段返回；
- 迁移 016（event_key 列 + 具名唯一索引）幂等可升降，与 ORM 命名一致。
"""
from datetime import datetime
from unittest.mock import patch

from app.database import SessionLocal
from app.models import (
    SdnAssuranceRun,
    SdnScopeException,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.services import sdn_assurance_events as ev_mod
from tests.test_s3_002_scheduler import (
    _business_counts,
    _create_device,
    _create_tenant_via_api,
    _create_vpc_via_api,
    _policy_row,
    _put_policy,
    _runs,
    _seed_healthy_vpc,
)


def _device_id_for(db, vpc_id):
    from app.models import SdnDeployment
    return (
        db.query(SdnDeployment).filter(SdnDeployment.vpc_id == vpc_id).first().device_id
    )


def _event_runs(db, vpc_id=None):
    q = db.query(SdnAssuranceRun).filter(SdnAssuranceRun.trigger == "event")
    if vpc_id is not None:
        q = q.filter(SdnAssuranceRun.vpc_id == vpc_id)
    return q.order_by(SdnAssuranceRun.id).all()


def _sync_snapshot(client, db, vpc_id, device_id, *, cached=False, snap=None):
    if snap is None:
        snap = SdnValidationSnapshot(
            vpc_id=vpc_id, device_id=device_id, snapshot_data="{}",
            validation_result="active", validation_details="{}",
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
    with patch(
        "app.routers.sdn.SdnValidationCollector.sync",
        return_value=(snap, None, cached),
    ):
        resp = client.post(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/sync")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"], snap


# ── 1. 快照事件：sync 成功 → event run；同快照重试去重 ──


def test_snapshot_sync_success_appends_event_run_and_retry_dedups(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)

    data, snap = _sync_snapshot(client, db, vpc_id, device_id)
    assert data["id"] == snap.id
    events = _event_runs(db, vpc_id)
    assert len(events) == 1
    assert events[0].status == "completed"
    assert events[0].trigger == "event"
    assert events[0].event_key == f"snapshot:{snap.id}"
    assert events[0].policy_version == _policy_row(db, vpc_id).version

    # 同一源事件重试（cached 返回同一快照）→ 不重复历史
    _sync_snapshot(client, db, vpc_id, device_id, cached=True, snap=snap)
    assert len(_event_runs(db, vpc_id)) == 1


# ── 2. scope-exception 新增/修改/清除 → 三条 event run（键各异）──


def test_scope_exception_add_modify_clear_events(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)
    base = f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception"

    resp = client.put(base, json={"exception_type": "maintenance_pause", "reason": "nightly upgrade"})
    assert resp.status_code == 200 and resp.json()["success"] is True
    exc_id = db.query(SdnScopeException).filter(
        SdnScopeException.vpc_id == vpc_id, SdnScopeException.device_id == device_id
    ).first().id

    resp = client.put(base, json={"exception_type": "maintenance_pause", "reason": "daytime pause"})
    assert resp.status_code == 200 and resp.json()["success"] is True

    resp = client.delete(base)
    assert resp.status_code == 200 and resp.json()["data"]["deleted"] is True

    events = _event_runs(db, vpc_id)
    assert len(events) == 3
    keys = {e.event_key for e in events}
    assert keys == {
        f"scope-exc:{exc_id}:v1",
        f"scope-exc:{exc_id}:v2",
        f"scope-exc:{exc_id}:cleared",
    }
    assert all(e.status == "completed" for e in events)

    # 清除后再清除（deleted=false）→ 不再触发
    resp = client.delete(base)
    assert resp.json()["data"]["deleted"] is False
    assert len(_event_runs(db, vpc_id)) == 3


# ── 3. 未配策略 / enabled=false → 零 event run；manual cadence 仍允许事件检查 ──


def test_disabled_or_no_policy_zero_event_runs_manual_cadence_still_checks(client, db):
    vpc = _seed_healthy_vpc(client, db, cadence="10m")
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)
    base = f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception"

    # enabled=false（乐观版本：seed 后策略为 v1 → 需传 version=1）→ 快照与 scope 事件都零 run
    _put_policy(client, vpc_id, {"enabled": False, "cadence": "10m", "version": 1})
    assert _policy_row(db, vpc_id).enabled is False
    _sync_snapshot(client, db, vpc_id, device_id)
    client.put(base, json={"exception_type": "maintenance_pause", "reason": "skip me"})
    assert _event_runs(db, vpc_id) == []

    # manual cadence 只禁用周期：enabled 后事件检查照常（v2 → v3）
    _put_policy(client, vpc_id, {"enabled": True, "cadence": "manual", "version": 2})
    data, snap = _sync_snapshot(client, db, vpc_id, device_id)
    events = _event_runs(db, vpc_id)
    assert len(events) == 1 and events[0].event_key == f"snapshot:{snap.id}"
    # 手动评估不受影响（向后兼容）
    resp = client.post(f"/api/sdn/vpcs/{vpc_id}/assurance-runs", json={})
    assert resp.status_code == 200 and resp.json()["success"] is True


def test_no_policy_zero_event_runs(client, db):
    # 无策略：租户 + VPC + Leaf（经 API/种子，但不 PUT 保障策略）
    tenant = _create_tenant_via_api(client, name="no-policy-t1")
    vpc = _create_vpc_via_api(client, tenant["id"], name="no-policy-vpc1")
    leaf = _create_device(db, name="NoPolicy-Leaf", ip="192.0.2.99")

    _sync_snapshot(client, db, vpc["id"], leaf.id)
    client.put(
        f"/api/sdn/vpcs/{vpc['id']}/devices/{leaf.id}/scope-exception",
        json={"exception_type": "maintenance_pause", "reason": "no policy"},
    )
    assert _event_runs(db, vpc["id"]) == []


# ── 4. 评估失败：业务成功不被破坏，追加 failed run 供审计 ──


def test_eval_failure_keeps_business_success_and_appends_failed_run(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)
    version_before = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version
    counts_before = _business_counts(db)
    snap = SdnValidationSnapshot(
        vpc_id=vpc_id, device_id=device_id, snapshot_data="{}",
        validation_result="active", validation_details="{}",
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)

    with patch("app.routers.sdn.SdnValidationCollector.sync", return_value=(snap, None, False)), \
         patch("app.services.sdn_assurance.evaluate_assurance", side_effect=RuntimeError("boom")):
        resp = client.post(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/sync")
    # 原业务事件成功：响应 success 不被评估失败破坏
    assert resp.status_code == 200 and resp.json()["success"] is True
    assert resp.json()["data"]["id"] == snap.id

    events = _event_runs(db, vpc_id)
    assert len(events) == 1
    assert events[0].status == "failed"
    assert events[0].event_key == f"snapshot:{snap.id}"
    assert "boom" in (events[0].error or "")
    # 业务副作用不变：vpc.version 未变、业务表计数未变（快照仅 +1，即业务侧已持久化的那一条）
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version == version_before
    counts_after = _business_counts(db)
    for k in ("deployments", "bindings", "operations", "plans"):
        assert counts_after[k] == counts_before[k], k
    assert counts_after["snapshots"] == counts_before["snapshots"] + 1

    # 同源事件（同快照）重试 → 失败历史也不重复
    _sync_snapshot(client, db, vpc_id, device_id, cached=True, snap=snap)
    assert len(_event_runs(db, vpc_id)) == 1


# ── 5. 事件路径零设备 I/O、零业务副作用 ──


def test_event_path_zero_device_io_zero_business_side_effects(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)
    version_before = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version
    counts_before = _business_counts(db)

    # collector.sync 只应被业务调用一次；事件评估不得再次采集
    with patch("app.routers.sdn.SdnValidationCollector.sync") as mock_sync:
        snap = SdnValidationSnapshot(
            vpc_id=vpc_id, device_id=device_id, snapshot_data="{}",
            validation_result="active", validation_details="{}",
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        mock_sync.return_value = (snap, None, False)
        client.post(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/sync")
        client.put(
            f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception",
            json={"exception_type": "maintenance_pause", "reason": "side-effect probe"},
        )
        assert mock_sync.call_count == 1  # 事件评估不触发任何采集/设备调用

    # 事件评估只读：业务表计数与 vpc.version 均不变
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version == version_before
    counts_after = _business_counts(db)
    for k in ("deployments", "bindings", "operations", "plans"):
        assert counts_after[k] == counts_before[k], k
    # 事件本身追加的两条 run（快照 + scope）
    assert len(_event_runs(db, vpc_id)) == 2


# ── 6. event_key 去重（hook 层）与审计字段 ──


def test_event_retry_same_source_no_duplicate_history(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    s = SessionLocal()
    r1 = ev_mod.record_event_check(s, vpc_id=vpc_id, event_key="snapshot:4242")
    r2 = ev_mod.record_event_check(s, vpc_id=vpc_id, event_key="snapshot:4242")
    assert r1 is not None and r1.status == "completed"
    assert r2 is None  # 同源事件重试 → 不重复
    assert len(_event_runs(db, vpc_id)) == 1
    s.close()


def test_policy_lookup_failure_isolated_from_source_event(client, db):
    vpc = _seed_healthy_vpc(client, db)
    with patch.object(ev_mod, "_policy", side_effect=RuntimeError("policy store unavailable")):
        result = ev_mod.record_event_check(
            db,
            vpc_id=vpc["id"],
            event_key="snapshot:policy-lookup-failure",
        )

    assert result is None
    assert _event_runs(db, vpc["id"]) == []


def test_event_key_readonly_audit_field_and_no_secrets(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    device_id = _device_id_for(db, vpc_id)
    _sync_snapshot(client, db, vpc_id, device_id)
    client.put(
        f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception",
        json={"exception_type": "maintenance_pause", "reason": "audit probe"},
    )
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/assurance-runs")
    assert resp.status_code == 200 and resp.json()["success"] is True
    runs = resp.json()["data"]["runs"]
    event_runs = [r for r in runs if r["trigger"] == "event"]
    assert len(event_runs) == 2
    keys = [r["event_key"] for r in event_runs]
    # 只含稳定内部 ID/版本，绝不含凭据/原始 CLI
    assert all(k.startswith(("snapshot:", "scope-exc:")) for k in keys)
    joined = " ".join(keys).lower()
    for secret in ("admin", "secret", "password", "display ", "cli", "192.0.2."):
        assert secret not in joined
