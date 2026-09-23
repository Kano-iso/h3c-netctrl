"""S2-012 契约测试：VPC EVPN Leaf 范围覆盖投影（只读、additive、保守分类）。

覆盖：
- 四类分类（targeted / withdrawn / not_targeted / ambiguous）与 summary counts；
- 版本不匹配（历史成功 create 版本不符 → ambiguous）；
- snapshot-only（快照单独不能证明 targeted → ambiguous）；
- failed/pending（不覆盖确定生命周期：failed create → ambiguous；create success +
  failed delete → 仍 targeted）；
- gateway_delete 局部动作不改变 base 范围（仍 targeted）；
- planned/active binding（无 deployment 也 targeted，desired_binding_count 正确）；
- 非 EVPN 排除（只走既有 excluded，不混入 scope 分母）；
- 空 inventory（counts 全 0）；脱敏白名单；零 I/O 零写入；
- 既有 leaves/excluded/aggregate 行为不变。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnDeployment, SdnPortBinding, SdnValidationSnapshot, SdnVpc
from app.services.sdn_state_projection import (
    SCOPE_AMBIGUOUS,
    SCOPE_NOT_TARGETED,
    SCOPE_TARGETED,
    SCOPE_WITHDRAWN,
    build_scope_member,
)

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


def _vpc_version(db, vpc):
    return db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version


def _add_deployment(db, vpc, device, *, action="create", unit="vpc-create-all", status="success", version=None):
    if version is None:
        version = _vpc_version(db, vpc)
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=device.id, action=action, unit=unit, status=status,
                         version=version, planned_config="[]", config_completed_at=datetime.utcnow()))
    db.commit()


def _add_binding(db, vpc, tenant, device, *, status="active", service_instance=3200, if_index=10):
    b = SdnPortBinding(device_id=device.id, tenant_id=tenant["id"], vpc_id=vpc["id"], if_index=if_index,
                       interface_name=f"GigabitEthernet1/0/{if_index}", access_vlan=None,
                       service_instance=service_instance, status=status)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _add_snapshot(db, vpc, device, *, data=None, minutes_ago=1):
    snap = SdnValidationSnapshot(vpc_id=vpc["id"], device_id=device.id,
                                 snapshot_data=data, validation_result="active", validation_details="{}",
                                 collection_started_at=NOW - timedelta(minutes=minutes_ago, seconds=30),
                                 collection_completed_at=NOW - timedelta(minutes=minutes_ago))
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def _projection(client, vpc_id):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert "scope" in data  # additive 顶层
    return data


def _member(data, device_id):
    return next(m for m in data["scope"]["members"] if m["device_id"] == device_id)


def test_scope_four_classifications_and_summary(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    target_leaf = _create_device(db, name="Leaf-T", ip="192.0.2.1")
    withdrawn_leaf = _create_device(db, name="Leaf-W", ip="192.0.2.2")
    unset_leaf = _create_device(db, name="Leaf-U", ip="192.0.2.3")
    amb_leaf = _create_device(db, name="Leaf-A", ip="192.0.2.4")
    # targeted：base present
    _add_deployment(db, vpc, target_leaf)
    # withdrawn：create success + delete success → base absent
    _add_deployment(db, vpc, withdrawn_leaf)
    _add_deployment(db, vpc, withdrawn_leaf, action="delete")
    # not_targeted：无任何记录
    # ambiguous：仅快照（snapshot 不能单独证明 targeted）
    _add_snapshot(db, vpc, amb_leaf)

    data = _projection(client, vpc["id"])
    members = {m["device_id"]: m for m in data["scope"]["members"]}
    assert set(members) == {target_leaf.id, withdrawn_leaf.id, unset_leaf.id, amb_leaf.id}
    assert members[target_leaf.id]["classification"] == SCOPE_TARGETED
    assert members[target_leaf.id]["reason_code"] == "base_present"
    assert members[target_leaf.id]["desired_base_state"] == "present"
    assert members[target_leaf.id]["desired_binding_count"] == 0
    assert members[withdrawn_leaf.id]["classification"] == SCOPE_WITHDRAWN
    assert members[withdrawn_leaf.id]["reason_code"] == "base_absent"
    assert members[withdrawn_leaf.id]["desired_base_state"] == "absent"
    assert members[unset_leaf.id]["classification"] == SCOPE_NOT_TARGETED
    assert members[unset_leaf.id]["reason_code"] == "no_records"
    assert members[unset_leaf.id]["record_sources"] == {
        "deployment": {"present": False, "count": 0},
        "binding": {"present": False, "count": 0},
        "snapshot": {"present": False, "count": 0},
    }
    assert members[amb_leaf.id]["classification"] == SCOPE_AMBIGUOUS
    assert members[amb_leaf.id]["reason_code"] == "lifecycle_unproven"
    assert members[amb_leaf.id]["record_sources"]["snapshot"]["count"] == 1
    # summary：只计 EVPN Leaf
    assert data["scope"]["summary"] == {
        "eligible": 4, SCOPE_TARGETED: 1, SCOPE_WITHDRAWN: 1, SCOPE_NOT_TARGETED: 1, SCOPE_AMBIGUOUS: 1,
    }
    # 顺序稳定（按 device id 升序）
    assert [m["device_id"] for m in data["scope"]["members"]] == sorted(m["device_id"] for m in data["scope"]["members"])


def test_scope_version_mismatch_ambiguous(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf, version=_vpc_version(db, vpc) + 1)  # 历史成功但版本不匹配

    data = _projection(client, vpc["id"])
    m = _member(data, leaf.id)
    assert m["classification"] == SCOPE_AMBIGUOUS
    assert m["reason_code"] == "lifecycle_unproven"
    assert m["desired_base_state"] == "unknown"
    assert m["record_sources"]["deployment"]["count"] == 1


def test_scope_snapshot_only_ambiguous_not_targeted(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_snapshot(db, vpc, leaf, data=json.dumps({"commands": {}}))

    data = _projection(client, vpc["id"])
    m = _member(data, leaf.id)
    assert m["classification"] == SCOPE_AMBIGUOUS  # snapshot 单独不能证明 targeted
    assert m["record_sources"]["deployment"]["count"] == 0
    assert m["record_sources"]["snapshot"]["count"] == 1


def test_scope_failed_pending_do_not_cover_lifecycle(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    failed_leaf = _create_device(db, name="Leaf-F", ip="192.0.2.5")
    del_leaf = _create_device(db, name="Leaf-D", ip="192.0.2.6")
    # 仅 failed create → ambiguous（有历史但生命周期未证明）
    _add_deployment(db, vpc, failed_leaf, status="failed")
    # create success + failed delete → 仍 present/targeted（failed 不覆盖确定生命周期）
    _add_deployment(db, vpc, del_leaf)
    _add_deployment(db, vpc, del_leaf, action="delete", status="failed")

    data = _projection(client, vpc["id"])
    assert _member(data, failed_leaf.id)["classification"] == SCOPE_AMBIGUOUS
    assert _member(data, failed_leaf.id)["desired_base_state"] == "unknown"
    assert _member(data, del_leaf.id)["classification"] == SCOPE_TARGETED
    assert _member(data, del_leaf.id)["desired_base_state"] == "present"


def test_scope_gateway_delete_keeps_base_targeted(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_deployment(db, vpc, leaf, action="gateway_delete", unit="vsi-l3")

    data = _projection(client, vpc["id"])
    m = _member(data, leaf.id)
    assert m["classification"] == SCOPE_TARGETED  # 局部网关撤回不改变 base 范围
    assert m["desired_base_state"] == "present"


def test_scope_planned_and_active_binding_targeted_without_deployments(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_binding(db, vpc, tenant, leaf, status="planned", service_instance=3200, if_index=10)
    _add_binding(db, vpc, tenant, leaf, status="active", service_instance=3201, if_index=11)

    data = _projection(client, vpc["id"])
    m = _member(data, leaf.id)
    assert m["classification"] == SCOPE_TARGETED
    assert m["reason_code"] == "current_target_binding"
    assert m["desired_base_state"] == "unknown"  # 无 deployment，生命周期未证明
    assert m["desired_binding_count"] == 2  # planned + active


def test_scope_non_evpn_excluded_not_in_scope(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10")
    access = _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")
    _add_deployment(db, vpc, leaf)
    _add_deployment(db, vpc, access)  # 非 EVPN 有记录 → 只进 excluded

    data = _projection(client, vpc["id"])
    assert {m["device_id"] for m in data["scope"]["members"]} == {leaf.id}
    assert data["scope"]["summary"]["eligible"] == 1
    assert any(e["device_id"] == access.id and e["sdn_role"] == "access" for e in data["excluded"])
    # 非 EVPN 不混入 scope 分母


def test_scope_reuses_canonical_member_role_normalization(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-N", ip="192.0.2.21", sdn_role="EVPN_LEAF")

    data = _projection(client, vpc["id"])
    assert data["scope"]["summary"]["eligible"] == 1
    assert _member(data, leaf.id)["classification"] == SCOPE_NOT_TARGETED


def test_scope_empty_inventory_zero_counts(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    data = _projection(client, vpc["id"])
    assert data["scope"]["members"] == []
    assert data["scope"]["summary"] == {
        "eligible": 0, SCOPE_TARGETED: 0, SCOPE_WITHDRAWN: 0, SCOPE_NOT_TARGETED: 0, SCOPE_AMBIGUOUS: 0,
    }


def test_scope_sanitized_whitelist_only(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-S", ip="192.0.2.7")
    _add_deployment(db, vpc, leaf)
    _add_binding(db, vpc, tenant, leaf)
    _add_snapshot(db, vpc, leaf, data=json.dumps({"commands": {"x": {"output": "RAW-SCOPE-OUT-1"}}}))

    data = _projection(client, vpc["id"])
    m = _member(data, leaf.id)
    assert set(m.keys()) == {"device_id", "name", "host", "classification", "reason_code",
                             "record_sources", "desired_base_state", "desired_binding_count"}
    raw = json.dumps(data["scope"], default=str)
    for forbidden in ("password_encrypted", "protected_interfaces", "planned_config",
                      "RAW-SCOPE-OUT-1", "snapshot_data", "username"):
        assert forbidden not in raw, forbidden


def test_scope_zero_io_and_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    from app.services.sdn_validation_collector import SdnValidationCollector

    counts = (
        db.query(Device).count(), db.query(SdnDeployment).count(),
        db.query(SdnPortBinding).count(), db.query(SdnValidationSnapshot).count(),
    )
    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        data = _projection(client, vpc["id"])
    assert data["scope"]["summary"]["eligible"] == 1
    after = (
        db.query(Device).count(), db.query(SdnDeployment).count(),
        db.query(SdnPortBinding).count(), db.query(SdnValidationSnapshot).count(),
    )
    assert after == counts


def test_scope_existing_leaves_excluded_aggregate_unchanged(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf)

    data = _projection(client, vpc["id"])
    # 既有字段完整且与 scope 并存；leaves 只含「有记录的目标设备」
    assert set(data.keys()) == {"vpc", "snapshot_ttl_seconds", "leaves", "excluded", "aggregate", "scope"}
    assert len(data["leaves"]) == 1
    assert data["leaves"][0]["device_id"] == leaf.id
    assert data["leaves"][0]["aggregate"] == data["aggregate"]
    assert data["excluded"] == []
    # scope 新增不改变 aggregate 语义
    assert data["aggregate"] in ("aligned", "drifted", "unknown", "stale", "not_applicable")


def test_scope_pure_function_matrix_and_garbage():
    for garbage in (None, "text", 3.14, ["a"], {"unexpected": object()}):
        out = build_scope_member(garbage, deployments=garbage, bindings=garbage, snapshot_count=garbage, vpc_version=garbage)
        assert isinstance(out, dict)
        assert out["classification"] == SCOPE_NOT_TARGETED  # 无可用记录 → 稳定降级
    # targeted：base present（create success 当前版本）
    targeted = build_scope_member({"id": 1}, deployments=[{"id": 1, "action": "create", "unit": "vpc-create-all", "status": "success", "version": 2}], bindings=[], snapshot_count=0, vpc_version=2)
    assert targeted["classification"] == SCOPE_TARGETED and targeted["reason_code"] == "base_present"
    # targeted：planned binding（无 deployment）
    b_targeted = build_scope_member({"id": 2}, deployments=[], bindings=[{"status": "planned", "id": 5}], snapshot_count=0, vpc_version=2)
    assert b_targeted["classification"] == SCOPE_TARGETED and b_targeted["reason_code"] == "current_target_binding"
    assert b_targeted["desired_binding_count"] == 1
    # withdrawn：create + delete
    w = build_scope_member({"id": 3}, deployments=[
        {"id": 1, "action": "create", "unit": "vpc-create-all", "status": "success", "version": 2},
        {"id": 2, "action": "delete", "unit": "vpc-create-all", "status": "success", "version": 2},
    ], bindings=[], snapshot_count=0, vpc_version=2)
    assert w["classification"] == SCOPE_WITHDRAWN and w["desired_base_state"] == "absent"
    # ambiguous：版本不匹配 / snapshot-only / failed
    for deps, bindings, snap in (
        ([{"id": 1, "action": "create", "unit": "vpc-create-all", "status": "success", "version": 1}], [], 0),  # 版本不符
        ([], [], 1),  # snapshot-only
        ([{"id": 1, "action": "create", "unit": "vpc-create-all", "status": "failed", "version": 2}], [], 0),  # failed
    ):
        a = build_scope_member({"id": 4}, deployments=deps, bindings=bindings, snapshot_count=snap, vpc_version=2)
        assert a["classification"] == SCOPE_AMBIGUOUS, (deps, bindings, snap)
    # gateway_delete 不改变 base
    g = build_scope_member({"id": 5}, deployments=[
        {"id": 1, "action": "create", "unit": "vpc-create-all", "status": "success", "version": 2},
        {"id": 2, "action": "gateway_delete", "unit": "vsi-l3", "status": "success", "version": 2},
    ], bindings=[], snapshot_count=0, vpc_version=2)
    assert g["classification"] == SCOPE_TARGETED and g["desired_base_state"] == "present"
