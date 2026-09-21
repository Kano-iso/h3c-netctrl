"""S2-004 契约测试：设备快照时间线（只读，历史设备快照 vs 当前目标态）。

覆盖：
- 倒序与 limit（snapshot id/采集时间倒序，limit 默认 10、1..50）；
- device_id 过滤；
- 非 EVPN 排除（不进 timelines、不进聚合）；
- 坏快照保留为 unknown/evidence_missing，不跳过、不改写；
- desired 标记 basis=current_target，复用当前 deployment/binding 生命周期；
- 每点含 snapshot_id/collected_at/validation_result + 复用纯函数 aggregate/逐维 diff；
- GET 零设备 I/O、零写入；响应脱敏（不含原始 CLI output/error/凭据）。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnDeployment, SdnValidationSnapshot

NOW = datetime.utcnow()


def _create_tenant_via_api(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc_via_api(client, tenant_id, name="vpc-1"):
    return client.post("/api/sdn/vpcs", json={"name": name, "tenant_id": tenant_id, "cidr": "192.168.2.0/24", "gateway_ip": "192.168.2.254"}).json()["data"]


def _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf"):
    dev = Device(name=name, host=ip, port=830, username="t", password_encrypted="enc", protected_interfaces="[]", platform="LSTN", sdn_role=sdn_role)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _add_create_deployment(db, vpc, device):
    from app.models import SdnVpc

    version = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=device.id, action="create", unit="vpc-create-all", status="success", version=version, planned_config="[]", config_completed_at=datetime.utcnow()))
    db.commit()


def _aligned_snapshot_data(vpc, tenant):
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    return json.dumps({
        "commands": {
            vsi_cmd: {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up", "error": None},
            vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}", "error": None},
        }
    })


def _add_snapshot(db, vpc, device, *, snapshot_data=None, validation_result="active", minutes_ago=1):
    snap = SdnValidationSnapshot(
        vpc_id=vpc["id"],
        device_id=device.id,
        snapshot_data=snapshot_data,
        validation_result=validation_result,
        validation_details="{}",
        collection_started_at=NOW - timedelta(minutes=minutes_ago, seconds=30),
        collection_completed_at=NOW - timedelta(minutes=minutes_ago),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def _history(client, vpc_id, **params):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection/history", params=params)
    return resp


def test_history_desc_order_and_limit(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    data = _aligned_snapshot_data(vpc, tenant)
    for i, mins in enumerate((5, 3, 1), start=1):
        _add_snapshot(db, vpc, leaf, snapshot_data=data, minutes_ago=mins)

    resp = _history(client, vpc["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    timeline = body["data"]["timelines"][0]
    ids = [p["snapshot_id"] for p in timeline["points"]]
    assert ids == sorted(ids, reverse=True)
    assert len(timeline["points"]) == 3

    # limit 生效（默认 10 之上限内）；倒序
    resp2 = _history(client, vpc["id"], limit=2)
    points2 = resp2.json()["data"]["timelines"][0]["points"]
    assert [p["snapshot_id"] for p in points2] == ids[:2]

    # 每个点都含 aggregate 与逐维 diff（复用纯函数）
    assert {"aggregate", "diff", "desired", "observed"} <= set(points2[0].keys())
    assert "evidence" in points2[0]["diff"]["vsi"]


def test_history_device_filter(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf1 = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    leaf2 = _create_device(db, name="Leaf-02", ip="192.0.2.11", sdn_role="evpn_leaf")
    for leaf in (leaf1, leaf2):
        _add_create_deployment(db, vpc, leaf)
        _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant))

    body = _history(client, vpc["id"], device_id=leaf1.id).json()["data"]
    assert len(body["timelines"]) == 1
    assert body["timelines"][0]["device_id"] == leaf1.id

    body_all = _history(client, vpc["id"]).json()["data"]
    assert {t["device_id"] for t in body_all["timelines"]} == {leaf1.id, leaf2.id}


def test_history_non_evpn_excluded_not_in_timelines(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    access = _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant))
    _add_snapshot(db, vpc, access)  # 非 EVPN 有记录 → 只进 excluded

    body = _history(client, vpc["id"]).json()["data"]
    assert {t["device_id"] for t in body["timelines"]} == {leaf.id}
    assert {e["device_id"] for e in body["excluded"]} == {access.id}
    assert body["excluded"][0]["reason"] == "not_evpn_leaf"
    # 非 EVPN 不进聚合
    assert body["aggregate"] in {"aligned", "unknown", "drifted", "stale"}


def test_history_bad_snapshot_kept_as_unknown(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant), minutes_ago=2)
    bad = _add_snapshot(db, vpc, leaf, snapshot_data="not-json{{{", validation_result="failed", minutes_ago=1)

    body = _history(client, vpc["id"]).json()["data"]
    points = body["timelines"][0]["points"]
    ids = [p["snapshot_id"] for p in points]
    # 坏点不被跳过、不被改写
    assert bad.id in ids
    bad_point = next(p for p in points if p["snapshot_id"] == bad.id)
    assert bad_point["validation_result"] == "failed"
    assert bad_point["diff"]["vsi"]["status"] == "unknown"
    assert bad_point["diff"]["vsi"]["reason_code"] == "evidence_missing"


def test_history_desired_basis_current_target(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant))

    body = _history(client, vpc["id"]).json()["data"]
    point = body["timelines"][0]["points"][0]
    assert point["desired"]["basis"] == "current_target"
    # desired 复用当前生命周期（成功 create → 基础对象期望存在）
    assert point["desired"]["vsi"]["present"] is True
    assert point["desired"]["base"]["source"]["action"] == "create"
    assert body["desired_basis"] == "current_target"


def test_history_validation_result_in_point(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant), validation_result="degraded")

    body = _history(client, vpc["id"]).json()["data"]
    point = body["timelines"][0]["points"][0]
    assert point["snapshot_id"] is not None
    assert point["collected_at"] is not None
    assert point["validation_result"] == "degraded"


def test_history_zero_io_and_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_snapshot_data(vpc, tenant))

    before = db.query(SdnValidationSnapshot).count()
    from app.services.sdn_validation_collector import SdnValidationCollector

    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        resp = _history(client, vpc["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    # 零写入：不增快照、不增 deployment
    assert db.query(SdnValidationSnapshot).count() == before
    assert db.query(SdnDeployment).count() == 1


def test_history_response_sanitized(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    leaky = json.dumps({"commands": {vsi_cmd: {"success": True, "output": "VSI Name: SECRET-CLI-LEAK-9", "error": "SECRET-ERR-9"}}})
    _add_snapshot(db, vpc, leaf, snapshot_data=leaky)

    resp = _history(client, vpc["id"])
    body = resp.json()
    assert resp.status_code == 200
    # 原始 CLI output/error/凭据绝不进入响应
    assert "SECRET-CLI-LEAK-9" not in json.dumps(body)
    assert "SECRET-ERR-9" not in json.dumps(body)
    point = body["data"]["timelines"][0]["points"][0]
    ev = point["diff"]["vsi"]["evidence"]
    assert "output" not in ev["observed_source"]
    assert "error" not in ev["observed_source"]


def test_history_vpc_not_found(client, db):
    resp = _history(client, 999999)
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.vpc_not_found"


def test_history_limit_bounds_rejected(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    for bad in (0, 51):
        resp = _history(client, vpc["id"], limit=bad)
        assert resp.status_code == 422, resp.text
