"""S2-001/S2-003 契约测试：VPC 目标态 / 观测态 / 差异投影 + 差异证据指针（只读）。

覆盖（单元 + 端点）：
- 无快照 → 全维 unknown（reason=no_snapshot），聚合 unknown；
- 过期快照（> 600s）→ 全维 stale，聚合 stale；
- 全部一致 → aligned；
- 明确偏差（l3-vni 缺失）→ 仅该维 drifted，其余 aligned；
- 部分命令失败（success=False）→ 该维 unknown，绝不冒充 drifted；
- 无 operable 绑定 → vsi_up not_applicable；planned 绑定 → not_applicable；
- 非 EVPN Leaf 不进 leaves、仅 excluded；
- GET 零设备 I/O、零写入（不触发 sync/SSH，不增快照）；
- CR47 生命周期证明目标态；CR48 多值成员关系；CR49 token 精确匹配；gateway 生命周期；
- S2-003 逐维 evidence 指针（desired_source/observed_source），脱敏、不回传原始 CLI 输出。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import (
    Device,
    SdnDeployment,
    SdnPortBinding,
    SdnValidationSnapshot,
)
from app.services.sdn_state_projection import build_leaf_projection

NOW = datetime(2026, 1, 1, 0, 0, 0)


def _mk(commands):
    """cmd→str 包装为成功条目；cmd→dict 视为已构造条目原样使用（可表达失败条目）。"""
    return {
        "commands": {
            cmd: (val if isinstance(val, dict) else {"success": True, "output": val, "error": None})
            for cmd, val in commands.items()
        }
    }


def _vpc_dict(vsi_name="vpna", vsi_interface=1):
    return {"id": 1, "name": "v", "version": 3, "vni": 2000, "vsi_name": vsi_name, "vsi_interface": vsi_interface}


def _tenant_dict(l3_vni=3000):
    return {"id": 1, "l3_vni": l3_vni}


def _leaf_device():
    return {"id": 5, "name": "Leaf-01", "host": "192.0.2.10", "sdn_role": "evpn_leaf"}


def _active_binding(service_instance=3200):
    return {
        "id": 11,
        "if_index": 10,
        "interface_name": "GigabitEthernet1/0/10",
        "access_vlan": None,
        "service_instance": service_instance,
        "status": "active",
        "version": 0,
    }


def _deployment(deployment_id=1, action="create", status="success", version=None):
    """构造 deployment 事实（id/action/status/version；unit 仅作占位不影响折叠）。"""
    return {"id": deployment_id, "action": action, "unit": "vpc-create-all", "status": status, "version": version}


def _vsi_cmd(vpc):
    return f"display l2vpn vsi name {vpc['vsi_name']} verbose"


def _vsi_if_cmd(vpc):
    return f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"


def _binding_cmd(binding):
    return f"display current-configuration interface {binding['interface_name']}"


def _aligned_commands(vpc, tenant, binding):
    return {
        _vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up",
        _vsi_if_cmd(vpc): f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}",
        _binding_cmd(binding): f"interface {binding['interface_name']}\n service-instance {binding['service_instance']}",
    }


def _leaf(commands=None, bindings=None, deployments=None, snapshot_meta=None, now=NOW, **kw):
    vpc = kw.get("vpc") or _vpc_dict()
    tenant = kw.get("tenant") or _tenant_dict()
    bindings = bindings if bindings is not None else [_active_binding()]
    if deployments is None:
        deployments = [_deployment(version=vpc.get("version"))]
    snapshot = _mk(commands) if commands is not None else None
    meta = snapshot_meta if snapshot_meta is not None else {}
    return build_leaf_projection(
        device=kw.get("device") or _leaf_device(),
        vpc=vpc,
        tenant=tenant,
        bindings=bindings,
        deployments=deployments,
        snapshot=snapshot,
        snapshot_meta=meta,
        now=now,
    )


def _dim(diff, status, reason_code):
    """diff 维度断言：status/reason_code 精确匹配；evidence 存在且只含白名单键。"""
    assert diff["status"] == status
    assert diff["reason_code"] == reason_code
    ev = diff["evidence"]
    assert set(ev.keys()) == {"desired_source", "observed_source"}
    return diff


# ── 单元：投影语义 ──


def test_no_snapshot_all_unknown():
    leaf = _leaf(commands=None, snapshot_meta={})
    assert leaf["observed"] is None
    _dim(leaf["diff"]["vsi"], "unknown", "no_snapshot")
    _dim(leaf["diff"]["l3_vni"], "unknown", "no_snapshot")
    # 无快照 → observed_source 为 null；目标仍可由 lifecycle 证明
    assert leaf["diff"]["vsi"]["evidence"]["observed_source"] is None
    assert leaf["diff"]["vsi"]["evidence"]["desired_source"]["kind"] == "deployment"
    assert leaf["aggregate"] == "unknown"


def test_stale_snapshot_all_stale():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    cmds = _aligned_commands(vpc, tenant, binding)
    stale_now = NOW + timedelta(seconds=700)
    collected = stale_now - timedelta(seconds=700)  # 恰好 700s > 600 TTL
    # 快照采集时间在 now 之前 700s
    leaf = _leaf(
        vpc=vpc,
        tenant=tenant,
        bindings=[binding],
        commands=cmds,
        snapshot_meta={"snapshot_id": 9, "collected_at": NOW - timedelta(seconds=700)},
        now=stale_now,
    )
    assert leaf["observed"]["stale"] is True
    _dim(leaf["diff"]["vsi"], "stale", "snapshot_stale")
    _dim(leaf["diff"]["l3_vni"], "stale", "snapshot_stale")
    assert leaf["diff"]["port_bindings"][0]["service_instance"]["status"] == "stale"
    assert leaf["diff"]["vsi"]["evidence"]["observed_source"]["snapshot_id"] == 9
    assert leaf["aggregate"] == "stale"


def test_all_aligned():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=_aligned_commands(vpc, tenant, binding), snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")
    _dim(leaf["diff"]["vsi_up"], "aligned", "vsi_up")
    _dim(leaf["diff"]["vsi_interface"], "aligned", "vsi_interface_present")
    _dim(leaf["diff"]["l3_vni"], "aligned", "l3_vni_present")
    si = leaf["diff"]["port_bindings"][0]["service_instance"]
    assert si["status"] == "aligned"
    assert si["reason_code"] == "service_instance_present"
    assert si["observed"] == [3200]
    assert leaf["aggregate"] == "aligned"


def test_l3vni_drifted_only_that_dimension():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    cmds = _aligned_commands(vpc, tenant, binding)
    # l3-vni 缺失（明确偏差），其余一致
    cmds[_vsi_if_cmd(vpc)] = f"interface Vsi-interface{vpc['vsi_interface']}"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")
    _dim(leaf["diff"]["vsi_interface"], "aligned", "vsi_interface_present")  # 接口仍在，只是缺 l3-vni
    _dim(leaf["diff"]["l3_vni"], "drifted", "l3_vni_missing")
    # 聚合不得覆盖逐维事实
    assert leaf["diff"]["l3_vni"]["status"] == "drifted"
    assert leaf["aggregate"] == "drifted"


def test_partial_command_failure_is_unknown_not_drifted():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    # vsi-if 命令失败（success=False）且无输出
    commands = {
        _vsi_cmd(vpc): {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up", "error": None},
        _vsi_if_cmd(vpc): {"success": False, "output": "", "error": "command failed"},
        _binding_cmd(binding): {"success": True, "output": f"service-instance {binding['service_instance']}", "error": None},
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")
    _dim(leaf["diff"]["vsi_interface"], "unknown", "evidence_missing")  # 采不到，绝不 drift
    _dim(leaf["diff"]["l3_vni"], "unknown", "evidence_missing")
    assert leaf["diff"]["port_bindings"][0]["service_instance"]["status"] == "aligned"
    assert leaf["aggregate"] == "unknown"


def test_vsi_up_not_applicable_without_operable_binding():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[], commands={_vsi_cmd(vpc): "VSI Name: vpna"}, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi_up"], "not_applicable", "not_required")
    assert leaf["desired"]["vsi_up"]["expected"] is False


def test_planned_binding_not_asserted():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    planned = {**_active_binding(), "status": "planned"}
    cmds = {
        _vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}",
        _vsi_if_cmd(vpc): f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}",
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[planned], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    bd = leaf["diff"]["port_bindings"][0]
    assert bd["service_instance"]["status"] == "not_applicable"
    assert bd["service_instance"]["reason_code"] == "planned_not_deployed"
    # planned 绑定不驱动 vsi_up 期望
    _dim(leaf["diff"]["vsi_up"], "not_applicable", "not_required")


# ── 端点：只读语义 + 排除 ──


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


def _add_binding_and_snapshot(db, vpc, tenant, device, *, service_instance=3200, output=None):
    binding = SdnPortBinding(
        device_id=device.id,
        tenant_id=tenant["id"],
        vpc_id=vpc["id"],
        if_index=10,
        interface_name="GigabitEthernet1/0/10",
        access_vlan=None,
        service_instance=service_instance,
        status="active",
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)

    # CR47：成功且当前版本有效的 create deployment 才能证明目标态 present。
    from app.models import SdnVpc

    vpc_version = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version
    db.add(
        SdnDeployment(
            vpc_id=vpc["id"],
            device_id=device.id,
            action="create",
            unit="vpc-create-all",
            status="success",
            version=vpc_version,
            planned_config="[]",
            config_completed_at=datetime.utcnow(),
        )
    )
    db.commit()

    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    b_cmd = f"display current-configuration interface {binding.interface_name}"
    if output is None:
        snap_cmds = {
            vsi_cmd: f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up",
            vsi_if_cmd: f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}",
            b_cmd: f"service-instance {service_instance}",
        }
    else:
        snap_cmds = output
    snap = SdnValidationSnapshot(
        vpc_id=vpc["id"],
        device_id=device.id,
        snapshot_data=json.dumps({"commands": {k: {"success": True, "output": v, "error": None} for k, v in snap_cmds.items()}}),
        validation_result="active",
        validation_details="{}",
        collection_started_at=datetime.utcnow(),
        collection_completed_at=datetime.utcnow(),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return binding, snap


def test_endpoint_zero_device_io_and_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_binding_and_snapshot(db, vpc, tenant, leaf)

    snapshots_before = db.query(SdnValidationSnapshot).count()
    bindings_before = db.query(SdnPortBinding).count()
    deployments_before = db.query(SdnDeployment).count()

    from app.services.sdn_validation_collector import SdnValidationCollector

    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/state-projection")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["vpc"]["id"] == vpc["id"]
    from app.models import SdnVpc

    db_vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first()
    assert body["data"]["vpc"]["version"] == db_vpc.version
    assert len(body["data"]["leaves"]) == 1
    assert body["data"]["leaves"][0]["aggregate"] == "aligned"
    assert body["data"]["excluded"] == []

    # 零副作用：不增快照、不增绑定、不增 deployment
    assert db.query(SdnValidationSnapshot).count() == snapshots_before
    assert db.query(SdnPortBinding).count() == bindings_before
    assert db.query(SdnDeployment).count() == deployments_before


def test_non_evpn_leaf_excluded_not_in_leaves(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    access = _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")
    # leaf 有绑定+快照（成为可操作目标）；access 只有历史 deployment（残留）。
    _add_binding_and_snapshot(db, vpc, tenant, leaf)
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=access.id, action="create", unit="vpc-create-all", status="success", planned_config="[]"))
    db.commit()

    resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/state-projection")
    body = resp.json()["data"]
    leaf_ids = {l["device_id"] for l in body["leaves"]}
    excluded = {e["device_id"] for e in body["excluded"]}
    assert leaf.id in leaf_ids
    assert access.id not in leaf_ids
    assert access.id in excluded
    assert body["excluded"][0]["reason"] == "not_evpn_leaf"


def test_vpc_not_found(client, db):
    resp = client.get("/api/sdn/vpcs/999999/state-projection")
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.vpc_not_found"


# ── CR47：目标态由生命周期记录证明 ──


def test_create_then_delete_base_absent_not_drift():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [
        _deployment(1, "create", "success", vpc["version"]),
        _deployment(2, "delete", "success", vpc["version"]),
    ]
    # 删除后的快照显示 VSI 已不存在 → 应是 aligned(vsi_absent)，绝不 vsi_missing 假 drift
    commands = {
        _vsi_cmd(vpc): "The VSI does not exist.",
        _vsi_if_cmd(vpc): "",
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[], deployments=deployments, commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    assert leaf["desired"]["base"]["state"] == "absent"
    assert leaf["desired"]["vsi"]["present"] is False
    assert leaf["desired"]["base"]["source"]["action"] == "delete"
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_absent")
    _dim(leaf["diff"]["vsi_interface"], "aligned", "vsi_interface_absent")
    # desired_source 指向 delete deployment
    assert leaf["diff"]["vsi"]["evidence"]["desired_source"]["action"] == "delete"

    # 若设备仍残留 VSI（陈旧遗留），应漂移方向为 unexpected，而非 vsi_missing
    leaf_stale = _leaf(
        vpc=vpc, tenant=tenant, bindings=[],
        deployments=deployments,
        commands={_vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}"},
        snapshot_meta={"snapshot_id": 2, "collected_at": NOW},
    )
    _dim(leaf_stale["diff"]["vsi"], "drifted", "vsi_unexpected")


def test_delete_then_new_create_present():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [
        _deployment(1, "delete", "success", vpc["version"]),
        _deployment(2, "create", "success", vpc["version"]),
    ]
    leaf = _leaf(
        vpc=vpc, tenant=tenant, bindings=[],
        deployments=deployments,
        commands={_vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}"},
        snapshot_meta={"snapshot_id": 1, "collected_at": NOW},
    )
    assert leaf["desired"]["base"]["state"] == "present"
    assert leaf["desired"]["vsi"]["present"] is True
    assert leaf["desired"]["base"]["source"]["action"] == "create"
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")


def test_snapshot_only_desired_unknown_not_drift():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    # 无任何 deployment：observation-only，desired 不得武断 present，diff 不得制造 drift
    leaf = _leaf(
        vpc=vpc, tenant=tenant, bindings=[],
        deployments=[],
        commands={_vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}"},
        snapshot_meta={"snapshot_id": 1, "collected_at": NOW},
    )
    assert leaf["desired"]["base"]["state"] == "unknown"
    assert leaf["desired"]["vsi"]["present"] is None
    _dim(leaf["diff"]["vsi"], "unknown", "desired_unknown")
    # desired_source 无证明 → null；observed_source 仍指向快照
    assert leaf["diff"]["vsi"]["evidence"]["desired_source"] is None
    assert leaf["diff"]["vsi"]["evidence"]["observed_source"]["snapshot_id"] == 1


def test_failed_delete_does_not_override_last_determinate():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [
        _deployment(1, "create", "success", vpc["version"]),
        _deployment(2, "delete", "failed", vpc["version"]),
    ]
    leaf = _leaf(
        vpc=vpc, tenant=tenant, bindings=[],
        deployments=deployments,
        commands={_vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}"},
        snapshot_meta={"snapshot_id": 1, "collected_at": NOW},
    )
    # failed delete 不覆盖 create → 仍 present
    assert leaf["desired"]["base"]["state"] == "present"
    assert leaf["desired"]["vsi"]["present"] is True
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")


def test_absent_base_with_operable_binding_is_conflict():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    deployments = [
        _deployment(1, "create", "success", vpc["version"]),
        _deployment(2, "delete", "success", vpc["version"]),
    ]
    leaf = _leaf(
        vpc=vpc, tenant=tenant, bindings=[binding],
        deployments=deployments,
        commands={_binding_cmd(binding): f"service-instance {binding['service_instance']}"},
        snapshot_meta={"snapshot_id": 1, "collected_at": NOW},
    )
    assert leaf["desired"]["base"]["state"] == "absent"
    assert leaf["desired"]["base"]["conflict"] is True
    si = leaf["diff"]["port_bindings"][0]["service_instance"]
    assert si["status"] == "unknown"
    assert si["reason_code"] == "lifecycle_conflict"
    _dim(leaf["diff"]["vsi_up"], "unknown", "lifecycle_conflict")


# ── CR48：多值接口配置按成员关系比较 ──


def test_binding_target_not_first_but_present():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding(service_instance=3200)
    cmds = _aligned_commands(vpc, tenant, binding)
    # 接口含多个 service-instance，目标 3200 不是第一个
    cmds[_binding_cmd(binding)] = f"service-instance 200\n service-instance 3200\n service-instance 900"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    si = leaf["diff"]["port_bindings"][0]["service_instance"]
    assert si["status"] == "aligned"
    assert si["reason_code"] == "service_instance_present"
    assert si["observed"] == [200, 3200, 900]


def test_binding_target_truly_missing():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding(service_instance=3200)
    cmds = _aligned_commands(vpc, tenant, binding)
    cmds[_binding_cmd(binding)] = "service-instance 200\n service-instance 3100"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    si = leaf["diff"]["port_bindings"][0]["service_instance"]
    assert si["status"] == "drifted"
    assert si["reason_code"] == "service_instance_missing"
    assert 3200 not in si["observed"]


# ── CR49：配置 token 精确匹配 ──


def test_l3vni_prefix_not_matched():
    vpc, tenant = _vpc_dict(), _tenant_dict(l3_vni=3000)
    binding = _active_binding()
    cmds = _aligned_commands(vpc, tenant, binding)
    # l3-vni 30000 —— 不得匹配目标 3000
    cmds[_vsi_if_cmd(vpc)] = f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni 30000"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["l3_vni"], "drifted", "l3_vni_missing")


def test_vsi_interface_prefix_not_matched():
    vpc, tenant = _vpc_dict(vsi_interface=1), _tenant_dict()
    binding = _active_binding()
    cmds = _aligned_commands(vpc, tenant, binding)
    # Vsi-interface10 —— 不得匹配目标 Vsi-interface1
    cmds[_vsi_if_cmd(vpc)] = f"interface Vsi-interface10\n l3-vni {tenant['l3_vni']}"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi_interface"], "drifted", "vsi_interface_missing")


def test_vsi_name_prefix_not_matched():
    vpc, tenant = _vpc_dict(vsi_name="vpna"), _tenant_dict()
    binding = _active_binding()
    cmds = _aligned_commands(vpc, tenant, binding)
    # VSI Name: vpnax —— 不得匹配目标 vpna
    cmds[_vsi_cmd(vpc)] = "VSI Name: vpnax\nVSI State               : Up"
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=cmds, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    _dim(leaf["diff"]["vsi"], "drifted", "vsi_missing")


# ── Gateway 生命周期 ──


def test_gateway_delete_only_removes_l3_dimension():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [
        _deployment(1, "create", "success", vpc["version"]),
        {**_deployment(2, "gateway_delete", "success", vpc["version"]), "unit": "vsi-l3"},
    ]
    commands = {
        _vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}",
        _vsi_if_cmd(vpc): "",
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[], deployments=deployments,
                 commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    assert leaf["desired"]["base"]["state"] == "present"
    assert leaf["desired"]["gateway"]["state"] == "absent"
    _dim(leaf["diff"]["vsi"], "aligned", "vsi_present")
    _dim(leaf["diff"]["vsi_interface"], "aligned", "vsi_interface_absent")
    _dim(leaf["diff"]["l3_vni"], "aligned", "l3_vni_absent")
    # 维度级证据来源不同：vsi 指向 create，gateway 维指向 gateway_delete
    assert leaf["diff"]["vsi"]["evidence"]["desired_source"]["action"] == "create"
    assert leaf["diff"]["vsi_interface"]["evidence"]["desired_source"]["action"] == "gateway_delete"


def test_gateway_redeploy_does_not_prove_l2_vsi_exists():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [
        {**_deployment(1, "create", "success", vpc["version"]), "unit": "vsi-l3"},
    ]
    commands = {
        _vsi_cmd(vpc): f"VSI Name: {vpc['vsi_name']}",
        _vsi_if_cmd(vpc): f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}",
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[], deployments=deployments,
                 commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    assert leaf["desired"]["base"]["state"] == "unknown"
    assert leaf["desired"]["gateway"]["state"] == "present"
    _dim(leaf["diff"]["vsi"], "unknown", "desired_unknown")
    _dim(leaf["diff"]["vsi_interface"], "aligned", "vsi_interface_present")
    _dim(leaf["diff"]["l3_vni"], "aligned", "l3_vni_present")


def test_cli_error_text_is_unknown_not_drifted():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    deployments = [_deployment(1, "create", "success", vpc["version"])]
    leaf = _leaf(
        vpc=vpc,
        tenant=tenant,
        bindings=[],
        deployments=deployments,
        commands={_vsi_cmd(vpc): "% Wrong parameter found at '^' position."},
        snapshot_meta={"snapshot_id": 1, "collected_at": NOW},
    )
    _dim(leaf["diff"]["vsi"], "unknown", "evidence_missing")


def test_malformed_snapshot_record_is_evidence_missing_not_no_snapshot():
    vpc, tenant = _vpc_dict(), _tenant_dict()
    leaf = build_leaf_projection(
        device=_leaf_device(),
        vpc=vpc,
        tenant=tenant,
        bindings=[],
        deployments=[_deployment(1, "create", "success", vpc["version"])],
        snapshot=None,
        snapshot_meta={"snapshot_id": 9, "collected_at": NOW},
        now=NOW,
    )
    assert leaf["observed"]["snapshot_id"] == 9
    _dim(leaf["diff"]["vsi"], "unknown", "evidence_missing")
    # 有快照记录（即使畸形）→ observed_source 保留指针
    assert leaf["diff"]["vsi"]["evidence"]["observed_source"]["snapshot_id"] == 9


# ── S2-003：差异证据指针 ──


def test_evidence_aligned_pointers():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=_aligned_commands(vpc, tenant, binding), snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    # VSI 维：desired 来自 lifecycle deployment，observed 来自快照 + vsi 命令
    ev = leaf["diff"]["vsi"]["evidence"]
    assert ev["desired_source"]["kind"] == "deployment"
    assert ev["desired_source"]["action"] == "create"
    assert ev["observed_source"] == {"kind": "snapshot", "snapshot_id": 1, "collected_at": NOW, "command": _vsi_cmd(vpc)}
    # vsi_up：desired 来自 operable 绑定计数
    assert leaf["diff"]["vsi_up"]["evidence"]["desired_source"] == {"kind": "operable_binding_count", "count": 1}
    # gateway 维：observed 来自 vsi-interface 命令
    assert leaf["diff"]["l3_vni"]["evidence"]["observed_source"]["command"] == _vsi_if_cmd(vpc)
    # 绑定字段：desired 指向 binding id/version，observed 指向精确接口命令
    bev = leaf["diff"]["port_bindings"][0]["service_instance"]["evidence"]
    assert bev["desired_source"] == {"kind": "binding", "binding_id": 11, "version": 0}
    assert bev["observed_source"]["command"] == _binding_cmd(binding)
    assert bev["observed_source"]["snapshot_id"] == 1


def test_evidence_command_failure_keeps_pointer_but_sanitizes():
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    commands = {
        _vsi_cmd(vpc): {"success": True, "output": f"VSI Name: {vpc['vsi_name']}", "error": None},
        _vsi_if_cmd(vpc): {"success": False, "output": "secret-output-xyz", "error": "secret-error-abc"},
        _binding_cmd(binding): {"success": True, "output": f"service-instance {binding['service_instance']}", "error": None},
    }
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    assert leaf["diff"]["vsi_interface"]["status"] == "unknown"
    ev = leaf["diff"]["vsi_interface"]["evidence"]
    # 指针仍在（诚实说明观测来源），但绝不携带原始 output/error
    assert ev["observed_source"] == {"kind": "snapshot", "snapshot_id": 1, "collected_at": NOW, "command": _vsi_if_cmd(vpc)}
    raw = json.dumps(ev, default=str)
    assert "secret-output-xyz" not in raw
    assert "secret-error-abc" not in raw


def test_evidence_never_leaks_output_or_credentials():
    """脱敏边界：整棵 leaf 投影的 evidence 永不携带原始 CLI 输出 / error / 凭据。"""
    vpc, tenant, binding = _vpc_dict(), _tenant_dict(), _active_binding()
    commands = _aligned_commands(vpc, tenant, binding)
    # 注入敏感输出，断言绝不流入 evidence 或响应
    commands[_vsi_cmd(vpc)] = {"success": True, "output": "VSI Name: vpna\npassword hunter2-secret", "error": None}
    leaf = _leaf(vpc=vpc, tenant=tenant, bindings=[binding], commands=commands, snapshot_meta={"snapshot_id": 1, "collected_at": NOW})
    raw = json.dumps(leaf, default=str)
    assert "hunter2-secret" not in raw
    for dim in ("vsi", "vsi_up", "vsi_interface", "l3_vni"):
        ev = leaf["diff"][dim]["evidence"]
        assert set(ev.keys()) == {"desired_source", "observed_source"}
        if ev["observed_source"] is not None:
            assert set(ev["observed_source"].keys()) == {"kind", "snapshot_id", "collected_at", "command"}
            assert "output" not in ev["observed_source"]
            assert "error" not in ev["observed_source"]
    for bd in leaf["diff"]["port_bindings"]:
        for col in ("service_instance", "access_vlan"):
            ev = bd[col]["evidence"]
            assert set(ev["observed_source"].keys()) == {"kind", "snapshot_id", "collected_at", "command"}


def test_evidence_endpoint_sanitized(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    binding, snap = _add_binding_and_snapshot(
        db, vpc, tenant, leaf,
        output={
            vsi_cmd: "VSI Name: SECRET-TOKEN-LEAK\nVSI State               : Up",
            vsi_if_cmd: f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}",
            f"display current-configuration interface GigabitEthernet1/0/10": "service-instance 3200",
        },
    )
    resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/state-projection")
    body = resp.json()
    assert body["success"] is True
    leaf0 = body["data"]["leaves"][0]
    ev = leaf0["diff"]["vsi"]["evidence"]
    assert ev["observed_source"]["kind"] == "snapshot"
    assert ev["observed_source"]["snapshot_id"] == snap.id
    assert ev["observed_source"]["command"] == vsi_cmd
    # 脱敏：原始输出 / 错误 / 凭据绝不进入响应
    assert "SECRET-TOKEN-LEAK" not in json.dumps(body)
    assert "output" not in json.dumps(ev)
    assert "error" not in json.dumps(ev)
