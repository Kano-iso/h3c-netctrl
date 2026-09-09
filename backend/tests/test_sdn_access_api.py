"""S1 终端接入端点测试（预览/执行/幂等/撤回/完成/概览/历史）。"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import SessionLocal
from app.models import (
    Device,
    SdnDeployment,
    SdnIdentitySnapshot,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnTenant,
    SdnVpc,
    SdnValidationSnapshot,
)


def _seed_ready(client, db, *, host="192.168.100.5"):
    """创建 evpn_leaf 设备 + 租户 + VPC + 成功 create + 新鲜快照（前置部署 ready）。"""
    device = Device(name="Leaf-04", host=host, username="admin", password_encrypted="enc",
                    protected_interfaces="[]", platform="LSTN", sdn_role="evpn_leaf")
    db.add(device)
    db.flush()
    tenant = SdnTenant(name="研发", rd="1:1", import_rt="1:1", export_rt="1:1", l3_vni=10001)
    db.add(tenant)
    db.flush()
    vpc = SdnVpc(tenant_id=tenant.id, name="vpc-a", cidr="10.1.0.0/24", gateway_ip="10.1.0.1",
                 gateway_mac="00:00:5e:00:01:01", vni=10001, vsi_name="vsi-a", vsi_interface=1,
                 vlan_id=100, status="deployed", version=0)
    db.add(vpc)
    db.flush()
    dep = SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="create", unit="vpc-create-all",
                        planned_config="[]", status="success")
    db.add(dep)
    db.commit()
    db.refresh(dep)
    # CR8: 持久化 config 完成时间（真实 executor 在 I/O 成功后写入）
    dep.config_completed_at = dep.created_at
    db.commit()
    snap = SdnValidationSnapshot(
        vpc_id=vpc.id, device_id=device.id, validation_result="active",
        collection_started_at=dep.config_completed_at + timedelta(seconds=1),
        collection_completed_at=dep.config_completed_at + timedelta(seconds=2),
        snapshot_data=json.dumps({"commands": {
            "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: 192.168.100.5 State: Established", "error": None},
            f"display l2vpn vsi name {vpc.vsi_name} verbose": {"success": True, "output": f"VSI Name: {vpc.vsi_name}\n VSI State               : Up", "error": None},
            "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
        }}),
        validation_details=json.dumps({
            "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
            "raw_has_error": {"ok": True}, "bgp_peer_established": {"ok": True},
            "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
        }),
    )
    db.add(snap)
    db.commit()
    return device, tenant, vpc


def _preview_body(device, if_index=1, interface_name="GigabitEthernet1/0/1"):
    return {
        "device_id": device.id,
        "if_index": if_index,
        "interface_name": interface_name,
        "access_vlan": None,
        "service_instance": 3200,
        "expected_host_ip": "10.1.0.2",
    }


def test_preview_persists_plan_only(client, db):
    device, _, vpc = _seed_ready(client, db)
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["plan_id"]
    assert data["predeploy_status"] == "ready"
    assert data["blocking"] == []
    # 只写计划，不建 binding/deployment/operation
    assert db.query(SdnPlan).count() == 1
    assert db.query(SdnPortBinding).count() == 0
    assert db.query(SdnOperation).count() == 0


def test_access_creates_operation_binding_deployment(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]

    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["operation_id"]
    assert data["status"] == "awaiting_wiring"
    assert db.query(SdnOperation).count() == 1
    assert db.query(SdnPortBinding).count() == 1
    assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == data["operation_id"]).count() == 1


def test_access_duplicate_returns_same_operation(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    first = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]
    second = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert second.status_code == 200
    assert second.json()["data"]["operation_id"] == first["operation_id"]
    assert second.json()["data"]["duplicate"] is True
    assert db.query(SdnPortBinding).count() == 1


def test_access_consumed_plan_different_key_conflict(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    body2 = {**_preview_body(device), "idempotency_key": "key-00000002", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body2)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.plan_consumed"


def test_access_missing_predeploy_blocks(client, db):
    device = Device(name="Leaf-04", host="192.168.100.5", username="admin", password_encrypted="enc",
                    protected_interfaces="[]", platform="LSTN", sdn_role="evpn_leaf")
    db.add(device)
    db.flush()
    tenant = SdnTenant(name="研发", rd="1:1", import_rt="1:1", export_rt="1:1", l3_vni=10001)
    db.add(tenant)
    db.flush()
    vpc = SdnVpc(tenant_id=tenant.id, name="vpc-a", cidr="10.1.0.0/24", gateway_ip="10.1.0.1",
                 gateway_mac="00:00:5e:00:01:01", vni=10001, vsi_name="vsi-a", vsi_interface=1,
                 vlan_id=100, status="deployed", version=0)
    db.add(vpc)
    db.commit()

    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    # 预览 blocking 含 predeploy_missing
    body = {**_preview_body(device), "idempotency_key": "key-00000009", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] in ("sdn.predeploy_missing", "sdn.predeploy_unknown")


def test_operation_detail_has_attempts_units(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]
    resp = client.get(f"/api/sdn/operations/{op['operation_id']}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["attempts"]
    assert data["attempts"][0]["units"]


def test_access_overview_read_only(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    resp = client.get(f"/api/sdn/vpcs/{vpc.id}/access-overview")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["bindings"]) == 1
    assert len(data["operations"]) == 1


@patch("app.routers.sdn_access.SdnDeploymentExecutor.execute")
def test_withdraw_preserves_shared_resources(mock_exec, client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_success(0, "port-unbind")
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    mock_exec.side_effect = _fake_exec
    resp = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "withdrawn"
    assert data["withdrawn_binding"]["status"] == "unbound"
    # 保留 VPC / 租户
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc.id).count() == 1
    assert db.query(SdnTenant).filter(SdnTenant.id == vpc.tenant_id).count() == 1


@patch("app.routers.sdn_access.SdnValidationCollector.sync")
def test_complete_records_causal_window(mock_sync, client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]

    # CR22: complete 只允许 awaiting_validation（模拟 apply 成功）
    db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"]).update({"status": "success"})
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()

    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).first()
    snap.validation_result = "active"
    db.commit()
    mock_sync.return_value = (snap, None, False)

    resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["validation_result"] == "active"
    assert data["cached"] is False


def test_delete_tenant_keeps_identity_snapshot(client, db):
    device, tenant, vpc = _seed_ready(client, db)
    resp = client.delete(f"/api/sdn/tenants/{tenant.id}")
    assert resp.status_code == 200
    # 租户/VPC 被删，但身份快照保留
    assert db.query(SdnIdentitySnapshot).filter(SdnIdentitySnapshot.entity_kind == "tenant", SdnIdentitySnapshot.entity_id == tenant.id).count() >= 1
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc.id).count() == 0


def test_legacy_create_port_binding_blocked_by_claim(client, db):
    """跨新旧入口争抢：旧入口 create_port_binding 也要过层级 claim，被 S1 claim 挡住。"""
    device, _, vpc = _seed_ready(client, db)
    from app.services.sdn_operation_service import acquire_claims, device_port_key
    acquire_claims(db, [device_port_key(device.id, 1)], operation_id=999, attempt_id=999)
    db.commit()
    resp = client.post("/api/sdn/port-bindings", json={
        "device_id": device.id, "vpc_id": vpc.id, "if_index": 1,
        "interface_name": "GigabitEthernet1/0/1",
    })
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"


def test_access_stale_plan_rejected(client, db):
    """预览后 vpc.version 变化 → S1-016 版本因果阻断（create deployment 不再对应当前版本）。"""
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    vpc.version += 1
    db.commit()
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.predeploy_unknown"
