"""S3-002 对抗测试：有界周期保障调度（NEXT/S3 后端切片）。

先覆盖失败风险，再验证语义（全部隔离 qa-backend 容器，真实 SQLite）：
- 并发双 session/线程认领同一 due 窗口 → 唯一 winner、至多一条 completed scheduled run；
- 重复 tick 幂等；enabled=false / cadence=manual 不排程；cadence 改变按新策略续跑不补跑；
- 重启恢复：pending 已到期 / claimed lease 已过期可恢复执行，lease 未过期不可接管；
- 评估异常 → run 落 failed + slot 落 failed（诚实，不伪造 completed/healthy），下一窗口可重试；
- 旧代际迟到（token/generation 不匹配）不能覆盖新代际；
- SERVICE_NAME=config/core 才启动 scheduler，data/ctrl 不启动；线程可 start/stop；
- scheduler 路径不能触达 collector/executor/Netconf/SSH；业务表与 vpc.version 不变；
- 每 tick 批量上限；GET 策略附带稳定 schedule_status/next_due/last_scheduled_at；
- 手动评估（S3-001 API）保持向后兼容。
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import count
from unittest.mock import patch

import pytest

from app.database import SessionLocal
from app.models import (
    Device,
    SdnAssurancePolicy,
    SdnAssuranceRun,
    SdnAssuranceSlot,
    SdnDeployment,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnTenant,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.services import sdn_assurance_scheduler as sched_mod
from app.services.sdn_assurance_scheduler import (
    Scheduler,
    scheduler_enabled_for,
    tick_once,
)

NOW = datetime.utcnow()

_DEVICE_IP_SEQ = count(10)  # 同测试内多次建种子时保证设备 IP 唯一


# ── seed helpers（镜像 S3-001 模式） ──


def _create_tenant_via_api(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc_via_api(client, tenant_id, name="vpc-1"):
    return client.post(
        "/api/sdn/vpcs",
        json={"name": name, "tenant_id": tenant_id, "cidr": "192.168.2.0/24", "gateway_ip": "192.168.2.254"},
    ).json()["data"]


def _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf"):
    dev = Device(
        name=name, host=ip, port=830, username="admin", password_encrypted="SECRET-ENC",
        protected_interfaces="[]", platform="LSTN", sdn_role=sdn_role,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _add_create_deployment(db, vpc, device):
    version = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version
    db.add(SdnDeployment(
        vpc_id=vpc["id"], device_id=device.id, action="create", unit="vpc-create-all",
        status="success", version=version, planned_config='[{"secret": "RAW-PLAN-1"}]',
        config_completed_at=NOW,
    ))
    db.commit()


def _tenant_l3_vni(db, tenant_id):
    return db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first().l3_vni


def _aligned_snapshot(db, vpc, device, tenant_id):
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    l3_vni = _tenant_l3_vni(db, tenant_id)
    commands = {
        "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: State: Established", "error": None},
        vsi_cmd: {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up", "error": None},
        vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {l3_vni}", "error": None},
        "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
    }
    db.add(SdnValidationSnapshot(
        vpc_id=vpc["id"], device_id=device.id, validation_result="active",
        validation_details=json.dumps({
            "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
            "bgp_peer_established": {"ok": True}, "vsi_interface_exists": {"ok": True},
            "l3_vni_present": {"ok": True},
        }),
        snapshot_data=json.dumps({"commands": commands}),
        collection_started_at=NOW - timedelta(seconds=10),
        collection_completed_at=NOW - timedelta(seconds=5),
    ))
    db.commit()


def _seed_healthy_vpc(client, db, cadence="10m", name_suffix=""):
    """租户 + VPC + Leaf 已部署 + 对齐快照 + enabled 策略（健康评估基础）。

    name_suffix 用于同一测试内多次建种子时避免租户/VPC 重名。
    """
    tenant = _create_tenant_via_api(client, name=f"t{name_suffix}")
    vpc = _create_vpc_via_api(client, tenant["id"], name=f"vpc-{name_suffix}")
    leaf_ip = f"192.0.2.{next(_DEVICE_IP_SEQ)}"
    leaf = _create_device(db, name=f"Leaf-{name_suffix}", ip=leaf_ip)
    _add_create_deployment(db, vpc, leaf)
    _aligned_snapshot(db, vpc, leaf, tenant["id"])
    resp = client.put(
        f"/api/sdn/vpcs/{vpc['id']}/assurance-policy",
        json={"enabled": True, "cadence": cadence, "version": 0},
    )
    assert resp.status_code == 200, resp.text
    return vpc


def _put_policy(client, vpc_id, body):
    resp = client.put(f"/api/sdn/vpcs/{vpc_id}/assurance-policy", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _policy_row(db, vpc_id):
    return db.query(SdnAssurancePolicy).filter(SdnAssurancePolicy.vpc_id == vpc_id).first()


def _slot_row(db, vpc_id):
    return db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.vpc_id == vpc_id).first()


def _runs(db, vpc_id=None):
    q = db.query(SdnAssuranceRun)
    if vpc_id is not None:
        q = q.filter(SdnAssuranceRun.vpc_id == vpc_id)
    return q.order_by(SdnAssuranceRun.id).all()


def _business_counts(db):
    return {
        "deployments": db.query(SdnDeployment).count(),
        "bindings": db.query(SdnPortBinding).count(),
        "operations": db.query(SdnOperation).count(),
        "snapshots": db.query(SdnValidationSnapshot).count(),
        "plans": db.query(SdnPlan).count(),
    }


# ── 1. 并发唯一 winner ──


def test_concurrent_ticks_same_due_slot_single_winner(client, db):
    """双 session/线程并发 tick：同一 VPC 同一 due 窗口只有一个 completed scheduled run。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]

    # 建好首个窗口并令其到期
    s1 = SessionLocal()
    tick_once(s1)
    s1.close()
    slot = _slot_row(db, vpc_id)
    assert slot is not None and slot.status == "pending"
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=10)
        s = SessionLocal()
        try:
            tick_once(s)
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(worker), ex.submit(worker)]
        for f in futs:
            f.result(timeout=30)

    runs = _runs(db, vpc_id)
    scheduled = [r for r in runs if r.trigger == "scheduled"]
    assert len(scheduled) == 1, f"expected exactly one completed scheduled run, got {len(scheduled)}"
    assert scheduled[0].status == "completed"
    assert scheduled[0].slot_key is not None
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    # 唯一 winner 完成窗口；输家 tick 可能随后把已完成的窗口推进到下一代际（合法），
    # 因此允许 completed 或（已推进的）pending，但绝不出现第二条 scheduled run
    assert slot.status in ("completed", "pending")
    if slot.status == "completed":
        assert slot.run_id == scheduled[0].id


# ── 2. 重复 tick 幂等 / 禁用 / manual ──


def test_repeated_tick_idempotent(client, db):
    vpc = _seed_healthy_vpc(client, db)
    s = SessionLocal()
    tick_once(s)  # 建首个窗口
    tick_once(s)  # 到期窗口 → 一条 scheduled run
    s.close()
    assert len(_runs(db, vpc["id"])) == 1
    s = SessionLocal()
    tick_once(s)  # 已完成窗口 → 只推进下一代际，不重复生成 run
    s.close()
    assert len(_runs(db, vpc["id"])) == 1
    slot = _slot_row(db, vpc["id"])
    assert slot.status == "pending"
    assert slot.generation == 1


def test_disabled_and_manual_policies_not_scheduled(client, db):
    # enabled=false
    vpc_d = _seed_healthy_vpc(client, db, name_suffix="d")
    _put_policy(client, vpc_d["id"], {"enabled": False, "cadence": "10m", "version": 1})
    # cadence=manual
    vpc_m = _seed_healthy_vpc(client, db, cadence="manual", name_suffix="m")

    s = SessionLocal()
    processed = tick_once(s)
    s.close()

    assert _slot_row(db, vpc_d["id"]) is None
    assert _slot_row(db, vpc_m["id"]) is None
    assert _runs(db, vpc_d["id"]) == []
    assert _runs(db, vpc_m["id"]) == []
    assert vpc_d["id"] not in processed and vpc_m["id"] not in processed


def test_tick_batch_cap_prevents_storm(client, db):
    """CR61：批量上限计入全部持久化窗口变更（建窗口/评估/推进），不只评估。"""
    for i in range(3):
        _seed_healthy_vpc(client, db, cadence="10m", name_suffix=i)
    s = SessionLocal()
    # tick1：最多 2 个首窗口
    changed = tick_once(s, max_slots=2)
    assert len(changed) == 2
    assert db.query(SdnAssuranceSlot).count() == 2
    # tick2：两个到期窗口评估（claim+eval 也是持久化变更，仍受上限约束）
    changed = tick_once(s, max_slots=2)
    assert len(changed) == 2
    assert len(_runs(db)) == 2
    # tick3：两个 completed 窗口被推进（terminal advance 计入上限；第三个策略本轮不被处理）
    changed = tick_once(s, max_slots=2)
    assert len(changed) == 2
    assert db.query(SdnAssuranceSlot).count() == 2  # 第 3 个策略仍未建窗口
    assert len(_runs(db)) == 2  # 推进不产生 run
    # tick4：前两个窗口 gen1 未到期（只读跳过）→ 第 3 个策略建首窗口
    changed = tick_once(s, max_slots=2)
    assert len(changed) == 1
    assert db.query(SdnAssuranceSlot).count() == 3
    # tick5：第 3 个策略评估
    tick_once(s, max_slots=2)
    assert len(_runs(db)) == 3
    s.close()


# ── 3. cadence 改变 / 重启恢复 / lease ──


def test_cadence_change_continues_without_backfill(client, db):
    vpc = _seed_healthy_vpc(client, db, cadence="10m")
    s = SessionLocal()
    tick_once(s)  # 建窗口
    tick_once(s)  # 评估 → 1 条 scheduled run
    s.close()
    assert len(_runs(db, vpc["id"])) == 1

    # 改 cadence：按新策略续跑，不补跑历史
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "30m", "version": 1})
    s = SessionLocal()
    tick_once(s)
    s.close()
    slot = _slot_row(db, vpc["id"])
    assert slot.cadence == "30m"
    assert slot.policy_version == 2
    assert slot.status == "pending"
    assert len(_runs(db, vpc["id"])) == 1  # 不补跑

    # 新窗口到期后正常执行一次
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    db.commit()
    s = SessionLocal()
    tick_once(s)
    s.close()
    runs = _runs(db, vpc["id"])
    assert len(runs) == 2
    assert runs[-1].trigger == "scheduled"
    assert runs[-1].policy_version == 2


def test_restart_recovers_overdue_pending_and_expired_lease(client, db):
    """重启恢复：pending 已到期、claimed lease 已过期都可恢复执行；未过期不可。"""
    vpc_overdue = _seed_healthy_vpc(client, db, name_suffix="o")
    vpc_expired = _seed_healthy_vpc(client, db, name_suffix="e")
    vpc_holding = _seed_healthy_vpc(client, db, name_suffix="h")

    s = SessionLocal()
    tick_once(s)
    s.close()
    # 三个窗口都 pending（due=now）；人为制造三种状态
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.vpc_id == vpc_overdue["id"]).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.vpc_id == vpc_expired["id"]).update(
        {"status": "claimed", "claim_token": "stale-token",
         "claimed_at": datetime.utcnow() - timedelta(seconds=3600),
         "lease_expires_at": datetime.utcnow() - timedelta(seconds=1),
         "due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.vpc_id == vpc_holding["id"]).update(
        {"status": "claimed", "claim_token": "live-token",
         "claimed_at": datetime.utcnow() - timedelta(seconds=10),
         "lease_expires_at": datetime.utcnow() + timedelta(seconds=3600),
         "due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    s = SessionLocal()
    tick_once(s)
    s.close()

    # overdue + expired 各恢复执行一条 scheduled run；holding 保持 claimed 不动
    assert len(_runs(db, vpc_overdue["id"])) == 1
    assert len(_runs(db, vpc_expired["id"])) == 1
    assert len(_runs(db, vpc_holding["id"])) == 0
    db.expire_all()
    holding = _slot_row(db, vpc_holding["id"])
    assert holding.status == "claimed"
    assert holding.claim_token == "live-token"


def test_lease_expiry_takeover_boundary(client, db):
    vpc = _seed_healthy_vpc(client, db)
    s = SessionLocal()
    tick_once(s)
    s.close()
    slot = _slot_row(db, vpc["id"])
    now = datetime.utcnow()
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"status": "claimed", "claim_token": "old-token",
         "claimed_at": now, "lease_expires_at": now + timedelta(seconds=3600)}
    )
    db.commit()
    db.expire_all()
    slot = _slot_row(db, vpc["id"])

    # 未过期：不可接管
    token = sched_mod._claim_slot(db, slot, now=now + timedelta(seconds=1), lease_seconds=60)
    assert token is None

    # 已过期：可接管（同代际新 token）
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    token = sched_mod._claim_slot(
        db, slot, now=now + timedelta(seconds=3601), lease_seconds=60
    )
    assert token is not None
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    assert slot.claim_token == token
    assert slot.status == "claimed"
    assert slot.generation == 0  # 接管不换代际


# ── 4. 失败诚实 + 后续可重试 ──


def test_evaluation_failure_records_failed_and_retries_next_window(client, db):
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    s = SessionLocal()
    tick_once(s)
    s.close()
    slot = _slot_row(db, vpc_id)
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    # 评估抛异常 → run 落 failed（诚实）、slot 落 failed
    with patch("app.services.sdn_assurance.evaluate_assurance", side_effect=RuntimeError("boom")):
        s = SessionLocal()
        tick_once(s)
        s.close()

    runs = _runs(db, vpc_id)
    assert len(runs) == 1  # 首 tick 只建窗口，此轮只有一条 failed run
    failed = runs[-1]
    assert failed.status == "failed"
    assert failed.error and "boom" in failed.error
    assert failed.slot_key is not None
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "failed"
    assert slot.error and "boom" in slot.error

    # 下一窗口可重试成功（不再 patch）
    s = SessionLocal()
    tick_once(s)
    s.close()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "pending"  # failed → 推进到下一窗口
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=1)}
    )
    db.commit()
    s = SessionLocal()
    tick_once(s)
    s.close()
    latest = _runs(db, vpc_id)[-1]
    assert latest.status == "completed"
    assert latest.trigger == "scheduled"


# ── 5. 旧代际迟到不能覆盖新代际 ──


def test_old_generation_late_arrival_does_not_overwrite(client, db):
    vpc = _seed_healthy_vpc(client, db)
    s = SessionLocal()
    tick_once(s)
    s.close()
    slot = _slot_row(db, vpc["id"])
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()
    db.expire_all()

    # tick 1 认领 gen 0（token A）
    s = SessionLocal()
    slot = _slot_row(db, vpc["id"])
    token_a = sched_mod._claim_slot(s, slot, now=datetime.utcnow(), lease_seconds=60)
    assert token_a is not None

    # 模拟：认领后窗口被别人接管并完成、随后推进到 gen 1
    s.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"status": "completed", "run_id": 999, "claim_token": "other-token",
         "lease_expires_at": None}, synchronize_session=False)
    s.commit()
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    policy = _policy_row(db, vpc["id"])
    advanced = sched_mod._advance_slot(s, policy, slot, now=datetime.utcnow())
    assert advanced is True
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    assert slot.generation == 1 and slot.status == "pending"

    # 迟到的 gen 0 / token A 完成：不覆盖新代际
    late = sched_mod._complete_slot(s, slot, generation=0, token=token_a, run_id=777)
    assert late is False
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    assert slot.generation == 1
    assert slot.status == "pending"
    assert slot.run_id is None
    assert slot.claim_token is None
    s.close()


# ── 6. 生命周期：service 门控 + 线程 ──


def test_scheduler_service_gate():
    assert scheduler_enabled_for("config") is True
    assert scheduler_enabled_for("core") is True
    assert scheduler_enabled_for("data") is False
    assert scheduler_enabled_for("ctrl") is False


def test_scheduler_thread_lifecycle_processes_due_slot(client, db):
    vpc = _seed_healthy_vpc(client, db)
    s = SessionLocal()
    tick_once(s)
    s.close()
    slot = _slot_row(db, vpc["id"])
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    scheduler = Scheduler(enabled=True, interval_seconds=1.0, lease_seconds=60, max_slots=10)
    scheduler.start()
    assert scheduler.running is True
    try:
        deadline = datetime.utcnow() + timedelta(seconds=15)
        while datetime.utcnow() < deadline:
            if any(r.trigger == "scheduled" for r in _runs(db, vpc["id"])):
                break
            import time as _time
            _time.sleep(0.1)
        assert any(r.trigger == "scheduled" for r in _runs(db, vpc["id"])), "thread did not process due slot"
    finally:
        scheduler.stop()
    assert scheduler.running is False
    assert scheduler._thread is None


def test_scheduler_disabled_does_not_start_thread():
    scheduler = Scheduler(enabled=False, interval_seconds=1.0)
    scheduler.start()
    assert scheduler.running is False
    assert scheduler._thread is None


# ── 7. 零设备 I/O / 零业务写副作用 / 审计 ──


def test_scheduler_zero_device_io_and_no_business_side_effects(client, db):
    """scheduler 模块无 collector/executor/Netconf/SSH 绑定；scheduled run 零业务写副作用。"""
    mod = sched_mod
    assert not hasattr(mod, "NetconfClient")
    assert not hasattr(mod, "SdnValidationCollector")
    assert not hasattr(mod, "SdnDeploymentExecutor")
    assert not hasattr(mod, "ssh")
    import inspect as _inspect
    src = _inspect.getsource(mod)
    for banned in ("NetconfClient", "SdnValidationCollector", "SdnDeploymentExecutor", "paramiko"):
        assert banned not in src, f"scheduler module must not reference {banned}"

    vpc = _seed_healthy_vpc(client, db)
    vpc_row = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first()
    before_version = vpc_row.version
    before_counts = _business_counts(db)

    s = SessionLocal()
    tick_once(s)  # 建首个窗口
    tick_once(s)  # 到期窗口 → scheduled run
    s.close()

    db.expire_all()
    assert _business_counts(db) == before_counts
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version == before_version

    # 审计：slot_key + policy_version + 完成状态齐全
    run = _runs(db, vpc["id"])[0]
    assert run.trigger == "scheduled"
    assert run.status == "completed"
    assert run.slot_key == f"vpc:{vpc['id']}:slot:gen:0"
    assert run.policy_version == 1
    assert run.policy_enabled is True
    db.expire_all()
    slot = _slot_row(db, vpc["id"])
    assert slot.run_id == run.id


# ── 8. GET 策略稳定调度信息 + 手动向后兼容 ──


def test_policy_get_exposes_stable_schedule_info(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])

    # 缺失策略 → disabled
    resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/assurance-policy")
    data = resp.json()["data"]
    assert data["schedule_status"] == "disabled"
    assert data["next_due"] is None
    assert data["last_scheduled_at"] is None

    # enabled + cadence=10m → scheduled（首窗口尚未建时 next_due=None）
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "10m", "version": 0})
    data = client.get(f"/api/sdn/vpcs/{vpc['id']}/assurance-policy").json()["data"]
    assert data["schedule_status"] == "scheduled"
    assert data["next_due"] is None
    assert data["last_scheduled_at"] is None

    # 首个窗口建立后 next_due 稳定可见
    s = SessionLocal()
    tick_once(s)
    s.close()
    data = client.get(f"/api/sdn/vpcs/{vpc['id']}/assurance-policy").json()["data"]
    assert data["schedule_status"] in ("scheduled", "due")
    assert data["next_due"] is not None

    # cadence=manual → manual_only
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "manual", "version": 1})
    data = client.get(f"/api/sdn/vpcs/{vpc['id']}/assurance-policy").json()["data"]
    assert data["schedule_status"] == "manual_only"
    assert data["next_due"] is None


def test_manual_run_backward_compatible(client, db):
    """S3-001 手动评估 API 不变：trigger=manual、slot_key=None、S3-002 字段附加不影响。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _aligned_snapshot(db, vpc, leaf, tenant["id"])

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/assurance-runs", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["trigger"] == "manual"
    assert data["status"] == "completed"
    assert data["slot_key"] is None
    assert data["error"] is None
    assert data["overall"] in ("healthy", "attention", "blocked", "insufficient_evidence")

    # scheduled 触发仍被写接口拒绝
    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/assurance-runs", json={"trigger": "scheduled"})
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.assurance_invalid_trigger"
    # 手动 run 不建 slot
    assert _slot_row(db, vpc["id"]) is None


# ── 9. CR61：run 与 slot 终态原子性 / terminal CAS 防御 / 批量上限口径 ──


def _evaluate_healthy(db, vpc_id):
    """走真实投影 + 评估，返回 result dict（供原子函数测试）。"""
    from app.routers.sdn import build_projection_payload
    from app.services.sdn_assurance import evaluate_assurance
    projection = build_projection_payload(db, vpc_id)
    assert projection is not None
    return evaluate_assurance(projection)


def test_takeover_then_late_arrival_single_run_per_slot_key(client, db):
    """A 过租约、B 接管并完成后，A 迟到收尾：CAS 0 行 → A 的 run 回滚，
    同 slot_key 最终仅一条 run（原子路径 + DB 唯一约束双保险）。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    s = SessionLocal()
    tick_once(s)  # 建首窗口
    s.close()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    t0 = datetime.utcnow()
    sA = SessionLocal()
    sB = SessionLocal()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    token_a = sched_mod._claim_slot(sA, slot, now=t0, lease_seconds=60)
    assert token_a is not None

    # A 的 lease 过期，B 接管（同代际新 token）
    db.expire_all()
    slot_b = _slot_row(db, vpc_id)
    token_b = sched_mod._claim_slot(sB, slot_b, now=t0 + timedelta(seconds=120), lease_seconds=60)
    assert token_b is not None and token_b != token_a
    # 认领是 bulk UPDATE（不同步 identity map）→ 重取拿新 token 视图
    slot_b = sched_mod._get_slot(sB, vpc_id)

    # A 在 B 已接管、但 B 尚未写 run 的窗口迟到。此时唯一索引还帮不上忙：
    # 必须由 run INSERT + owner CAS 的单事务保证 CAS 输家不留下 orphan run。
    policy = _policy_row(db, vpc_id)
    db.expire_all()
    stale_a = _slot_row(db, vpc_id)  # 当前行（token 已被 B 顶替）
    stale_a.claim_token = token_a  # 模拟 A 的陈旧 owner 视图
    stale_a.generation = 0
    result_a = _evaluate_healthy(sA, vpc_id)
    run_a = sched_mod._persist_scheduled_completed_atomic(
        sA, policy, stale_a, result_a, now=t0 + timedelta(seconds=130)
    )
    assert run_a is None
    assert [r for r in _runs(db, vpc_id) if r.trigger == "scheduled"] == []

    # B 随后完成，证明 A 的 CAS 失败已把 run 一并回滚，没有阻塞合法 owner。
    result_b = _evaluate_healthy(sB, vpc_id)
    run_b = sched_mod._persist_scheduled_completed_atomic(
        sB, policy, slot_b, result_b, now=t0 + timedelta(seconds=140)
    )
    assert run_b is not None and run_b.slot_key == f"vpc:{vpc_id}:slot:gen:0"
    sA.close()
    sB.close()

    # 同 slot_key 最终仅一条 run（B 的）
    runs = _runs(db, vpc_id)
    scheduled = [r for r in runs if r.trigger == "scheduled"]
    assert len(scheduled) == 1
    assert scheduled[0].id == run_b.id
    assert scheduled[0].slot_key == f"vpc:{vpc_id}:slot:gen:0"
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "completed"
    assert slot.run_id == run_b.id


def test_terminal_cas_replay_and_complete_fail_immutable(client, db):
    """terminal CAS 幂等防御：成功后清 token；同 token 重放 complete / complete→fail /
    旧 token / 旧 generation 均 0 行且不改 run_id/status。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    s = SessionLocal()
    tick_once(s)
    s.close()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    s = SessionLocal()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    token = sched_mod._claim_slot(s, slot, now=datetime.utcnow(), lease_seconds=60)
    assert token is not None
    slot = sched_mod._get_slot(s, vpc_id)  # 认领为 bulk UPDATE → 重取拿 token 视图
    policy = _policy_row(db, vpc_id)
    result = _evaluate_healthy(s, vpc_id)
    run = sched_mod._persist_scheduled_completed_atomic(s, policy, slot, result, now=datetime.utcnow())
    assert run is not None

    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "completed"
    assert slot.run_id == run.id
    assert slot.claim_token is None      # token 已清
    assert slot.claimed_at is None
    assert slot.lease_expires_at is None

    # 同 token 重放 complete → 0 行，不改 run_id/status
    assert sched_mod._complete_slot(s, slot, generation=0, token=token, run_id=999) is False
    # complete→fail → 0 行，不改 run_id/status
    assert sched_mod._fail_slot(s, slot, generation=0, token=token, error="late") is False
    # 旧 generation → 0 行
    assert sched_mod._complete_slot(s, slot, generation=1, token=token, run_id=999) is False
    # 旧 token（status 已非 claimed）→ 0 行
    assert sched_mod._fail_slot(s, slot, generation=0, token="stale-token", error="x") is False
    s.close()

    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "completed"
    assert slot.run_id == run.id
    assert slot.claim_token is None


def test_failed_old_owner_cannot_finalize_new_owner_after_rollback(client, db, monkeypatch):
    """评估异常 rollback 会过期 Session 对象；旧 owner 必须继续用自己的 token，
    不得刷新到接管者 token 后替新 owner 把 slot 标成 failed。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    bootstrap = SessionLocal()
    tick_once(bootstrap)
    bootstrap.close()

    t0 = datetime.utcnow()
    s_a = SessionLocal()
    s_b = SessionLocal()
    slot_a = sched_mod._get_slot(s_a, vpc_id)
    token_a = sched_mod._claim_slot(s_a, slot_a, now=t0, lease_seconds=60)
    assert token_a is not None
    slot_a = sched_mod._get_slot(s_a, vpc_id)
    policy_a = _policy_row(s_a, vpc_id)
    owner_b = {}

    def takeover_then_fail(_db, _vpc_id):
        slot_b = sched_mod._get_slot(s_b, vpc_id)
        owner_b["token"] = sched_mod._claim_slot(
            s_b, slot_b, now=t0 + timedelta(seconds=120), lease_seconds=60
        )
        assert owner_b["token"] and owner_b["token"] != token_a
        raise RuntimeError("synthetic evaluation failure after takeover")

    import app.routers.sdn as sdn_router
    monkeypatch.setattr(sdn_router, "build_projection_payload", takeover_then_fail)
    sched_mod._run_evaluation(s_a, policy_a, slot_a, token=token_a, now=t0)

    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "claimed"
    assert slot.claim_token == owner_b["token"]
    assert [r for r in _runs(db, vpc_id) if r.trigger == "scheduled"] == []
    s_a.close()
    s_b.close()


def test_old_owner_cannot_start_after_lease_takeover(client, db, monkeypatch):
    """认领后、执行前若已被接管，旧 worker 必须在投影/评估前退出，
    不得复用数据库里的新 token 代新 owner 执行。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    bootstrap = SessionLocal()
    tick_once(bootstrap)
    bootstrap.close()

    t0 = datetime.utcnow()
    s_a = SessionLocal()
    s_b = SessionLocal()
    slot_a = sched_mod._get_slot(s_a, vpc_id)
    token_a = sched_mod._claim_slot(s_a, slot_a, now=t0, lease_seconds=60)
    assert token_a is not None
    policy_a = _policy_row(s_a, vpc_id)

    slot_b = sched_mod._get_slot(s_b, vpc_id)
    token_b = sched_mod._claim_slot(
        s_b, slot_b, now=t0 + timedelta(seconds=120), lease_seconds=60
    )
    assert token_b and token_b != token_a

    calls = {"projection": 0}

    def must_not_project(*_args, **_kwargs):
        calls["projection"] += 1
        raise AssertionError("stale owner reached projection")

    import app.routers.sdn as sdn_router
    monkeypatch.setattr(sdn_router, "build_projection_payload", must_not_project)
    sched_mod._run_evaluation(s_a, policy_a, slot_a, token=token_a, now=t0)

    assert calls["projection"] == 0
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "claimed"
    assert slot.claim_token == token_b
    assert [r for r in _runs(db, vpc_id) if r.trigger == "scheduled"] == []
    s_a.close()
    s_b.close()


def test_claimed_valid_lease_policy_change_does_not_steal_generation(client, db):
    """claimed 未过期时 cadence/策略版本变化：不推进不抢代际；owner 收尾后由后续 tick
    按新策略推进。"""
    vpc = _seed_healthy_vpc(client, db)
    vpc_id = vpc["id"]
    s = SessionLocal()
    tick_once(s)
    s.close()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    db.query(SdnAssuranceSlot).filter(SdnAssuranceSlot.id == slot.id).update(
        {"due_at": datetime.utcnow() - timedelta(seconds=60)}
    )
    db.commit()

    s = SessionLocal()
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    token = sched_mod._claim_slot(s, slot, now=datetime.utcnow(), lease_seconds=3600)
    assert token is not None
    slot = sched_mod._get_slot(s, vpc_id)  # 认领为 bulk UPDATE → 重取拿 token 视图

    # 策略 cadence 变更（version 1 → 2）
    _put_policy(client, vpc_id, {"enabled": True, "cadence": "30m", "version": 1})

    # tick：claimed 未过期 → 不推进、不抢代际、不建 run
    changed = tick_once(s, max_slots=10)
    assert vpc_id not in changed
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "claimed"
    assert slot.generation == 0
    assert slot.claim_token == token
    assert slot.cadence == "10m"
    assert len(_runs(db, vpc_id)) == 0

    # owner 收尾完成（原子路径）
    policy = _policy_row(db, vpc_id)
    result = _evaluate_healthy(s, vpc_id)
    run = sched_mod._persist_scheduled_completed_atomic(s, policy, slot, result, now=datetime.utcnow())
    assert run is not None

    # 后续 tick：completed + 策略不匹配 → 按新策略推进（cadence=30m, gen1）
    changed = tick_once(s, max_slots=10)
    assert vpc_id in changed
    db.expire_all()
    slot = _slot_row(db, vpc_id)
    assert slot.status == "pending"
    assert slot.generation == 1
    assert slot.cadence == "30m"
    assert slot.policy_version == 2
    s.close()


def test_batch_cap_counts_all_slot_changes(client, db):
    """CR61：20+ 个 terminal/policy-change slot 下 max_slots=2 → 恰好 2 个 slot 被修改。"""
    for i in range(20):
        _seed_healthy_vpc(client, db, cadence="10m", name_suffix=i)
    s = SessionLocal()
    tick_once(s, max_slots=100)  # 建 20 个首窗口
    tick_once(s, max_slots=100)  # 20 个到期窗口评估 → completed
    assert len(_runs(db)) == 20
    # 全部策略 cadence 变更（10m → 30m）→ 20 个窗口都 policy-change 待推进
    from app.models import SdnAssurancePolicy as _P
    s.query(_P).update({_P.cadence: "30m"})
    s.commit()
    runs_before = len(_runs(db))

    changed = tick_once(s, max_slots=2)
    assert len(changed) == 2
    db.expire_all()
    slots = db.query(SdnAssuranceSlot).order_by(SdnAssuranceSlot.vpc_id).all()
    advanced = [sl for sl in slots if sl.generation == 1]
    untouched = [sl for sl in slots if sl.generation == 0]
    assert len(advanced) == 2          # 恰好 2 个被推进
    assert len(untouched) == 18        # 其余未被修改
    assert all(sl.status == "completed" and sl.cadence == "10m" for sl in untouched)
    assert all(sl.status == "pending" and sl.cadence == "30m" for sl in advanced)
    assert len(_runs(db)) == runs_before  # 推进不产生 run
    s.close()
