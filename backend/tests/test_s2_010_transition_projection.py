"""S2-010 契约测试：STRATA 快照状态转变投影（只读、additive、保守语义）。

覆盖：
- 倒序相邻配对：每个较新的点 transition_from_prior 与紧邻较旧点比较；窗口最旧点
  明确 baseline_unavailable（不拿窗口外/当前实时状态补造基线）；
- 维度转变矩阵：aligned→drifted=drift_detected、drifted→aligned=drift_cleared、
  drifted→unknown/stale=evidence_lost、unknown→aligned=evidence_gained、
  unchanged、not_applicable 变化=state_changed；
- binding 复合维度按稳定 binding_id 匹配（service_instance / access_vlan）；
- limit 截断边界、坏快照稳定降级、脱敏、零 I/O 零写入；
- 纯函数垃圾输入不抛异常。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnDeployment, SdnPortBinding, SdnValidationSnapshot
from app.services.sdn_state_projection import baseline_unavailable_transition, build_transition

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


def _add_binding(db, vpc, tenant, device, *, if_index=10, interface_name="GigabitEthernet1/0/10", service_instance=3200, access_vlan=None):
    b = SdnPortBinding(
        device_id=device.id,
        tenant_id=tenant["id"],
        vpc_id=vpc["id"],
        if_index=if_index,
        interface_name=interface_name,
        access_vlan=access_vlan,
        service_instance=service_instance,
        status="active",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


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


def _aligned_payload(vpc, tenant, binding=None):
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    commands = {
        vsi_cmd: {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up\nRAW-CLI-OUTPUT-77", "error": None},
        vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}", "error": None},
    }
    if binding is not None:
        bcmd = f"display current-configuration interface {binding.interface_name}"
        lines = [f"interface {binding.interface_name}", f" service-instance {binding.service_instance}"]
        if binding.access_vlan is not None:
            lines.append(f" access vlan {binding.access_vlan}")
        commands[bcmd] = {"success": True, "output": "\n".join(lines), "error": None}
    return json.dumps({"commands": commands})


def _drifted_payload(vpc, tenant, binding=None):
    """vsi 缺失 → vsi/vsi_up drifted（RC_VSI_MISSING/RC_VSI_DOWN）。"""
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    commands = {
        vsi_cmd: {"success": True, "output": "The VSI does not exist.", "error": None},
        vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}", "error": None},
    }
    if binding is not None:
        bcmd = f"display current-configuration interface {binding.interface_name}"
        commands[bcmd] = {"success": True, "output": f"interface {binding.interface_name}\n undo service-instance", "error": None}
    return json.dumps({"commands": commands})


def _unknown_payload(vpc, tenant):
    """vsi 命令失败 → vsi/vsi_up unknown（RC_EVIDENCE_MISSING）。"""
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    return json.dumps({"commands": {
        vsi_cmd: {"success": False, "output": "", "error": "timeout"},
        vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}", "error": None},
    }})


def _history(client, vpc_id, **params):
    return client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection/history", params=params)


def _first_timeline(client, vpc_id, **params):
    resp = _history(client, vpc_id, **params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]["timelines"][0]


def _vsi_dim(transition):
    return next(d for d in transition["dimensions"] if d["dimension"] == "vsi")


def test_transition_desc_adjacent_pairing_and_oldest_baseline_unavailable(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    # 添加顺序=时间顺序：oldest aligned(5) → drifted(3) → newest aligned(1)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=5)
    _add_snapshot(db, vpc, leaf, snapshot_data=_drifted_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=1)

    timeline = _first_timeline(client, vpc["id"])
    points = timeline["points"]
    assert len(points) == 3
    assert [p["snapshot_id"] for p in points] == sorted([p["snapshot_id"] for p in points], reverse=True)
    # 每个点都有 transition_from_prior
    assert all("transition_from_prior" in p for p in points)
    # 最新点 vs 紧邻较旧点（drifted→aligned）：vsi drift_cleared
    t0 = points[0]["transition_from_prior"]
    assert t0["kind"] == "transition"
    assert t0["desired_basis"] == "current_target"
    assert t0["from_snapshot_id"] == points[1]["snapshot_id"]
    assert t0["to_snapshot_id"] == points[0]["snapshot_id"]
    assert t0["from_collected_at"] == points[1]["collected_at"]
    assert t0["to_collected_at"] == points[0]["collected_at"]
    assert _vsi_dim(t0)["transition"] == "drift_cleared"
    assert _vsi_dim(t0)["from_status"] == "drifted"
    assert _vsi_dim(t0)["to_status"] == "aligned"
    # 中间点 vs 紧邻较旧点（aligned→drifted）：vsi drift_detected
    t1 = points[1]["transition_from_prior"]
    assert _vsi_dim(t1)["transition"] == "drift_detected"
    assert _vsi_dim(t1)["from_status"] == "aligned"
    assert _vsi_dim(t1)["to_status"] == "drifted"
    # 最旧点：明确 baseline_unavailable，无编造基线
    t2 = points[2]["transition_from_prior"]
    assert t2["kind"] == "baseline_unavailable"
    assert t2["baseline_unavailable"] is True
    assert t2["from_snapshot_id"] is None
    assert t2["to_snapshot_id"] == points[2]["snapshot_id"]
    assert t2["summary"]["counts"] == {"baseline_unavailable": 1}
    assert t2["dimensions"] == []
    # 摘要：changed_dimensions 与按 kind 计数
    assert "vsi" in t0["summary"]["changed_dimensions"]
    assert t0["summary"]["counts"].get("drift_cleared", 0) >= 1


def test_transition_drifted_to_unknown_is_evidence_lost_not_cleared(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_drifted_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_unknown_payload(vpc, tenant), minutes_ago=1)

    points = _first_timeline(client, vpc["id"])["points"]
    t = points[0]["transition_from_prior"]
    vsi = _vsi_dim(t)
    assert vsi["from_status"] == "drifted"
    assert vsi["to_status"] == "unknown"
    assert vsi["transition"] == "evidence_lost"  # drifted→unknown 只能 evidence_lost
    assert vsi["transition"] != "drift_cleared"


def test_transition_unknown_to_aligned_is_evidence_gained(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_unknown_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=1)

    points = _first_timeline(client, vpc["id"])["points"]
    vsi = _vsi_dim(points[0]["transition_from_prior"])
    assert vsi["from_status"] == "unknown"
    assert vsi["to_status"] == "aligned"
    assert vsi["transition"] == "evidence_gained"


def test_transition_unchanged_same_status(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    data = _aligned_payload(vpc, tenant)
    _add_snapshot(db, vpc, leaf, snapshot_data=data, minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=data, minutes_ago=1)

    points = _first_timeline(client, vpc["id"])["points"]
    t = points[0]["transition_from_prior"]
    assert t["summary"]["counts"] == {"unchanged": 4}  # vsi/vsi_up/vsi_interface/l3_vni 均 unchanged
    assert t["summary"]["changed_dimensions"] == []
    for d in t["dimensions"]:
        assert d["transition"] == "unchanged"
        assert d["from_status"] == d["to_status"]
        assert d["from_reason_code"] == d["to_reason_code"]


def test_transition_binding_compound_dimension_matched_by_binding_id(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    binding = _add_binding(db, vpc, tenant, leaf)
    # 快照 A：binding service_instance 3200 存在（aligned）；快照 B：缺失（drifted）
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant, binding), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_drifted_payload(vpc, tenant, binding), minutes_ago=1)

    points = _first_timeline(client, vpc["id"])["points"]
    t = points[0]["transition_from_prior"]
    dims = {d["dimension"]: d for d in t["dimensions"]}
    key = f"binding:{binding.id}:service_instance"
    assert key in dims
    sd = dims[key]
    assert sd["binding_id"] == binding.id
    assert sd["column"] == "service_instance"
    assert sd["from_status"] == "aligned"
    assert sd["from_reason_code"] == "service_instance_present"
    assert sd["to_status"] == "drifted"
    assert sd["to_reason_code"] == "service_instance_missing"
    assert sd["transition"] == "drift_detected"
    # 按稳定 binding_id 匹配，不以显示名/接口名为唯一身份
    assert "GigabitEthernet" not in {d["dimension"] for d in t["dimensions"]}


def test_transition_limit_truncation_oldest_baseline(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    for mins in (7, 5, 3, 1):
        _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=mins)

    # limit=1 → 单点即窗口最旧 → baseline_unavailable
    t1 = _first_timeline(client, vpc["id"], limit=1)["points"]
    assert len(t1) == 1
    assert t1[0]["transition_from_prior"]["kind"] == "baseline_unavailable"
    # limit=2 → 最旧点（points[1]）baseline_unavailable；新点与窗口内紧邻点比较
    t2 = _first_timeline(client, vpc["id"], limit=2)["points"]
    assert len(t2) == 2
    assert t2[0]["transition_from_prior"]["kind"] == "transition"
    assert t2[0]["transition_from_prior"]["summary"]["counts"] == {"unchanged": 4}
    assert t2[1]["transition_from_prior"]["kind"] == "baseline_unavailable"
    # 窗口外更旧的点不参与比较（不得补造基线）


def test_transition_bad_snapshot_stable_not_500(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data="{broken", minutes_ago=1)  # 坏快照

    points = _first_timeline(client, vpc["id"])["points"]
    t = points[0]["transition_from_prior"]
    vsi = _vsi_dim(t)
    assert vsi["from_status"] == "aligned"
    assert vsi["to_status"] == "unknown"  # 坏快照 → unknown/evidence_missing
    assert vsi["transition"] == "evidence_lost"
    assert t["kind"] == "transition"


def test_transition_sanitized_no_raw_output_or_secrets(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_drifted_payload(vpc, tenant), minutes_ago=1)

    points = _first_timeline(client, vpc["id"])["points"]
    transitions_json = json.dumps([p["transition_from_prior"] for p in points], default=str)
    assert "RAW-CLI-OUTPUT-77" not in transitions_json
    for forbidden in ("output", "error", "commands", "evidence", "observed", "password"):
        assert forbidden not in transitions_json
    # 每维度只含白名单字段
    for d in points[0]["transition_from_prior"]["dimensions"]:
        assert set(d.keys()) <= {"dimension", "binding_id", "column", "from_status", "from_reason_code", "to_status", "to_reason_code", "transition"}


def test_transition_zero_io_and_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, snapshot_data=_aligned_payload(vpc, tenant), minutes_ago=3)
    _add_snapshot(db, vpc, leaf, snapshot_data=_drifted_payload(vpc, tenant), minutes_ago=1)
    from app.services.sdn_validation_collector import SdnValidationCollector

    before = db.query(SdnValidationSnapshot).count()
    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        timeline = _first_timeline(client, vpc["id"])
    assert timeline["points"][0]["transition_from_prior"]["kind"] == "transition"
    assert db.query(SdnValidationSnapshot).count() == before


def test_transition_pure_functions_never_raise_on_garbage():
    for garbage in (None, "text", 3.14, ["a"], {"unexpected": object()}):
        out = build_transition(garbage, garbage)
        assert isinstance(out, dict)
        assert set(out.keys()) == {
            "kind", "desired_basis", "from_snapshot_id", "to_snapshot_id",
            "from_collected_at", "to_collected_at", "dimensions", "summary",
        }
        assert out["kind"] == "transition"
    empty = build_transition({}, {})
    # 固定维度始终出现（from/to 缺失 → null，None↔None → unchanged），不编造状态
    assert [d["dimension"] for d in empty["dimensions"]] == ["vsi", "vsi_up", "vsi_interface", "l3_vni"]
    assert all(d["from_status"] is None and d["to_status"] is None and d["transition"] == "unchanged" for d in empty["dimensions"])
    assert empty["summary"]["changed_dimensions"] == []
    assert empty["summary"]["counts"] == {"unchanged": 4}
    base = baseline_unavailable_transition()
    assert base["kind"] == "baseline_unavailable"
    assert base["baseline_unavailable"] is True
    assert base["summary"]["counts"] == {"baseline_unavailable": 1}
    mixed_bindings = {
        "diff": {
            "port_bindings": [
                {"binding_id": 1, "service_instance": {"status": "aligned"}},
                {"binding_id": "bad-id", "service_instance": {"status": "drifted"}},
                {"binding_id": True, "service_instance": {"status": "drifted"}},
            ]
        }
    }
    mixed = build_transition(mixed_bindings, mixed_bindings)
    assert [d["binding_id"] for d in mixed["dimensions"] if "binding_id" in d] == [1, 1]
    # 纯函数矩阵抽查（保守语义）
    t = lambda f, to: next(d for d in build_transition({"diff": {"vsi": {"status": f, "reason_code": "x"}}}, {"diff": {"vsi": {"status": to, "reason_code": "y"}}})["dimensions"] if d["dimension"] == "vsi")["transition"]
    assert t("aligned", "drifted") == "drift_detected"
    assert t("drifted", "aligned") == "drift_cleared"
    assert t("drifted", "unknown") == "evidence_lost"
    assert t("drifted", "stale") == "evidence_lost"
    assert t("unknown", "drifted") == "drift_detected"
    assert t("unknown", "aligned") == "evidence_gained"
    assert t("aligned", "unknown") == "evidence_lost"
    assert t("not_applicable", "aligned") == "state_changed"
    assert t("aligned", "not_applicable") == "state_changed"
    assert t("unknown", "stale") == "state_changed"
    assert t("aligned", "aligned") == "unchanged"
