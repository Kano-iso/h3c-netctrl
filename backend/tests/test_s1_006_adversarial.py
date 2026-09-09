"""S1-006 对抗性测试：CR1/CR3/CR4/CR6 关键安全断言。

这些断言在 S1-005 上会失败（claim 未提交即 I/O、绑定无 DB 约束、计划哈希不含端口/配置、
withdraw claim 泄漏），在 S1-006 修正后通过。
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import SdnDeployment, SdnOperation, SdnPortBinding, SdnResourceClaim
from app.services.sdn_operation_service import (
    SdnOperationError,
    acquire_claims,
    claim_deployment,
    release_claims,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402


# ── CR1: 两 Session 可见性（claim 提交后才 I/O，第二 Session 不可再认领）──

def test_cr1_claim_durably_visible_and_exclusive(db):
    _, _, vpc = _seed_ready(None, db)
    dep = SdnDeployment(vpc_id=vpc.id, device_id=1, action="create", unit="vpc-create-all",
                        planned_config="[]", status="pending")
    db.add(dep)
    db.commit()

    claim_deployment(db, dep.id, attempt_id=1)
    db.commit()

    # 第二 Session 立即可见 running 且 CAS 拒绝
    s2 = SessionLocal()
    try:
        seen = s2.query(SdnDeployment).filter(SdnDeployment.id == dep.id).first()
        assert seen.status == "running"
        with pytest.raises(SdnOperationError) as ei:
            claim_deployment(s2, dep.id, attempt_id=2)
        assert ei.value.error_key == "sdn.deployment_not_pending"
    finally:
        s2.close()


# ── CR3: 绑定 live 唯一约束（DB 层兜底，SELECT-then-INSERT 无法绕过）──

def test_cr3_live_binding_unique_constraint(db):
    _, _, vpc = _seed_ready(None, db)
    b1 = SdnPortBinding(device_id=1, tenant_id=vpc.tenant_id, vpc_id=vpc.id,
                        if_index=1, interface_name="GigabitEthernet1/0/1", status="planned")
    db.add(b1)
    db.commit()
    b2 = SdnPortBinding(device_id=1, tenant_id=vpc.tenant_id, vpc_id=vpc.id,
                        if_index=1, interface_name="GigabitEthernet1/0/1", status="planned")
    db.add(b2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 历史 unbound 行不受唯一约束限制
    b1.status = "unbound"
    db.commit()
    b3 = SdnPortBinding(device_id=1, tenant_id=vpc.tenant_id, vpc_id=vpc.id,
                        if_index=1, interface_name="GigabitEthernet1/0/1", status="planned")
    db.add(b3)
    db.commit()  # unbound + planned 共存合法


# ── CR4: 释放必须有 owner，且只释放自己的 claim ──

def test_cr4_release_requires_owner_and_scoped(db):
    acquire_claims(db, ["vpc:1"], operation_id=10, attempt_id=1)
    acquire_claims(db, ["vpc:2"], operation_id=20, attempt_id=2)
    db.commit()
    # 无 owner 释放必须被拒（绝不释放他人 claim）
    with pytest.raises(ValueError):
        release_claims(db, ["vpc:1"])
    # 只释放 owner=10 的 claim
    released = release_claims(db, ["vpc:1", "vpc:2"], owner_operation_id=10)
    assert released == 1
    db.commit()
    assert db.query(SdnResourceClaim).filter(SdnResourceClaim.resource_key == "vpc:2", SdnResourceClaim.released_at.is_(None)).count() == 1


# ── CR6: 计划哈希/scope 绑定完整端口/配置语义 ──

def test_cr6_port_substitution_rejected(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device, if_index=1)).json()["data"]["plan_id"]
    # 用另一端口执行 → plan_stale
    body = {**_preview_body(device, if_index=2), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.plan_stale"


def test_cr6_vlan_substitution_rejected(client, db):
    device, _, vpc = _seed_ready(client, db)
    base = _preview_body(device)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=base).json()["data"]["plan_id"]
    body = {**base, "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False, "access_vlan": 200}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.plan_stale"


def test_cr6_expected_ip_substitution_rejected(client, db):
    device, _, vpc = _seed_ready(client, db)
    base = _preview_body(device)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=base).json()["data"]["plan_id"]
    # 用 CIDR 内但不同的主机 IP 执行 → plan_stale（语义哈希绑定完整配置）
    body = {**base, "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False, "expected_host_ip": "10.1.0.3"}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.plan_stale"


def test_cr6_host_ip_outside_cidr_rejected(client, db):
    device, _, vpc = _seed_ready(client, db)
    # CIDR 外主机 IP → 硬校验拒绝（网络/广播/网关同理）
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": "unused", "auto_apply": False, "expected_host_ip": "10.1.1.2"}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.invalid_host_ip"


# ── CR7: split 元数据显式分派（不靠异常、fresh 绕缓存、失败不回退本地陈旧）──

def test_cr7_split_metadata_explicit_dispatch(db, monkeypatch):
    from app.utils import device_access
    import app.internal_api as internal_api

    monkeypatch.setattr(device_access, "_local_devices_table_exists", lambda db: False)

    calls = []
    def _fake_get(device_id):
        calls.append(("get", device_id))
        return {"success": True, "data": {"id": device_id, "name": "Leaf-X", "host": "10.0.0.9",
                                          "port": 830, "username": "a", "password": "p",
                                          "platform": "LSTN", "sdn_role": "evpn_leaf",
                                          "protected_interfaces": "[]"}}
    def _fake_fresh(device_id):
        calls.append(("fresh", device_id))
        return {"success": True, "data": {"id": device_id, "name": "Leaf-X", "host": "10.0.0.9",
                                          "port": 830, "username": "a", "password": "p",
                                          "platform": "LSTN", "sdn_role": "evpn_leaf",
                                          "protected_interfaces": "[]"}}
    monkeypatch.setattr(internal_api, "get_device", _fake_get)
    monkeypatch.setattr(internal_api, "get_device_fresh", _fake_fresh)

    dev, err = device_access.get_device_metadata(db, 7)
    assert err is None and dev.sdn_role == "evpn_leaf"
    assert calls == [("get", 7)]

    calls.clear()
    dev, err = device_access.get_device_metadata(db, 7, fresh=True)
    assert err is None and dev.sdn_role == "evpn_leaf"
    assert calls == [("fresh", 7)]

    # 内部 API 不可用 → 返回错误，绝不回退本地陈旧/静默 None
    monkeypatch.setattr(internal_api, "get_device", lambda device_id: (_ for _ in ()).throw(RuntimeError("down")))
    dev, err = device_access.get_device_metadata(db, 7)
    assert dev is None and err is not None and err.success is False


# ── CR8: 前置部署/证据因果（config_completed_at 而非 created_at；cached 快照不可变）──

def test_cr8_late_observation_not_causal(client, db):
    from app.models import SdnValidationSnapshot
    device, _, vpc = _seed_ready(client, db)
    from unittest.mock import patch
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]
    # 端口绑定 deployment 声称在“未来”完成 → 观测（过去）不早于完成 → 不因果
    from app.models import SdnDeployment
    pbd = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"]).first()
    pbd.status = "success"
    pbd.config_completed_at = datetime.utcnow() + timedelta(hours=1)
    # CR22: complete 只允许 awaiting_validation（模拟 apply 成功）
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).first()
    snap.validation_result = "active"
    db.commit()
    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        mock_sync.return_value = (snap, None, False)
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    data = resp.json()["data"]
    assert data["causal_ok"] is False
    assert data["status"] == "unknown"


def test_cr8_cached_snapshot_immutable(client, db):
    from app.models import SdnValidationSnapshot
    device, _, vpc = _seed_ready(client, db)
    from unittest.mock import patch
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]
    # CR22: complete 只允许 awaiting_validation（模拟 apply 成功）
    db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"]).update({"status": "success"})
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).first()
    snap_id = snap.id
    with patch("app.routers.sdn_access.SdnValidationCollector.sync") as mock_sync:
        mock_sync.return_value = (snap, None, True)  # cached
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    data = resp.json()["data"]
    assert data["cached"] is True
    assert data["causal_ok"] is False
    db.expire_all()
    cached = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.id == snap_id).first()
    assert cached.operation_id is None  # cached 快照未被改写


# ── CR9: 父删除先认领 + PATCH 终态不可改写 ──

def test_cr9_tenant_delete_blocked_by_claim(client, db):
    from app.models import SdnTenant
    from app.services.sdn_operation_service import tenant_key
    _, tenant, _vpc = _seed_ready(client, db)
    acquire_claims(db, [tenant_key(tenant.id)], attempt_id=1)
    db.commit()
    resp = client.delete(f"/api/sdn/tenants/{tenant.id}")
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"
    assert db.query(SdnTenant).filter(SdnTenant.id == tenant.id).count() == 1


def test_cr9_patch_terminal_deployment_immutable(client, db):
    from app.models import SdnDeployment
    _, _, vpc = _seed_ready(client, db)
    dep = db.query(SdnDeployment).filter(SdnDeployment.vpc_id == vpc.id, SdnDeployment.action == "create").first()
    dep.status = "success"
    db.commit()
    resp = client.patch(f"/api/sdn/deployments/{dep.id}", json={"status": "pending"})
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.deployment_not_pending"
    db.expire_all()
    assert db.query(SdnDeployment).filter(SdnDeployment.id == dep.id).first().status == "success"


def test_cr9_legacy_deploy_blocked_by_claim(client, db):
    from app.models import SdnDeployment
    from app.services.sdn_operation_service import tenant_key
    device, tenant, vpc = _seed_ready(client, db)
    acquire_claims(db, [tenant_key(tenant.id)], attempt_id=1)
    db.commit()
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/deploy",
                       json={"device_ids": [device.id], "auto_apply": False, "include_port_bindings": False})
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"
    # 仅 _seed_ready 的 create 保留，deploy 未生成新 create deployment
    assert db.query(SdnDeployment).filter(SdnDeployment.vpc_id == vpc.id, SdnDeployment.action == "create").count() == 1


def test_cr9_old_claim_blocks_new_access(client, db):
    from app.services.sdn_operation_service import tenant_key
    device, tenant, vpc = _seed_ready(client, db)
    # 旧入口（合成 owner attempt_id=-1）持锁 → 新 access 被挡
    acquire_claims(db, [tenant_key(tenant.id)], attempt_id=-1)
    db.commit()
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"
