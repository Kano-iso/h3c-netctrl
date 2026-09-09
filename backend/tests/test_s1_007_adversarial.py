"""S1-007 对抗性测试：CR11-CR17 关键安全断言。

这些断言在 S1-006 上会失败：
- apply 复用 own claims（CR11）
- unknown 保留并标 ambiguous（CR12）
- withdraw 释放全部 scoped claims（CR12）
- reconcile 按 action/期望状态判定（CR13）
- started unit 重放阻断 I/O + legacy 多单元（CR14）
- 主机观测不混入远端 Type-2（CR16）
- 四维验证不互相冒充 + ping 诚实（CR17）
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.database import SessionLocal
from app.models import (
    Device,
    SdnAttempt,
    SdnAttemptUnit,
    SdnDeployment,
    SdnOperation,
    SdnPortBinding,
    SdnResourceClaim,
    SdnTenant,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.services.sdn_deployment_executor import SdnDeploymentError, SdnDeploymentExecutor
from app.services.sdn_operation_service import (
    SdnOperationError,
    acquire_claims,
    acquire_or_reuse_claims,
    create_attempt,
    mark_operation_claims_ambiguous,
    release_claims,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402


def _do_access(client, db, device, vpc, idempotency_key="key-cr11", auto_apply=False):
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": idempotency_key, "plan_id": plan_id, "auto_apply": auto_apply}
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _active_claims(db, operation_id):
    return db.query(SdnResourceClaim).filter(
        SdnResourceClaim.owner_operation_id == operation_id,
        SdnResourceClaim.released_at.is_(None),
    ).all()


# ── CR11: apply 复用 own claims ──

def test_cr11_apply_reuses_own_claims_and_releases_on_success(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    assert len(_active_claims(db, op["operation_id"])) == 4

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            assert unit_hooks.before_unit(0, "port-bind") is True
            assert unit_hooks.after_unit_success(0, "port-bind") is True
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/apply")
    assert resp.status_code == 200, resp.text
    # CR12: 成功后释放全部（复用 + 新补），不残留
    assert len(_active_claims(db, op["operation_id"])) == 0


# ── CR12: unknown 保留 + ambiguous + 新旧入口被阻塞 ──

def test_cr12_unknown_keeps_claims_ambiguous_and_blocks(client, db):
    device, _, vpc = _seed_ready(client, db)

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-bind")
            unit_hooks.after_unit_failure(0, "port-bind", False, "timeout")
        d.status = "unknown"
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        op = _do_access(client, db, device, vpc, auto_apply=True)
    claims = _active_claims(db, op["operation_id"])
    assert len(claims) == 4
    assert all(c.status == "ambiguous" for c in claims)
    # 旧入口被 ambiguous claim 阻塞
    resp = client.post("/api/sdn/port-bindings", json={
        "device_id": device.id, "vpc_id": vpc.id, "if_index": 1,
        "interface_name": "GigabitEthernet1/0/1",
    })
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"


# ── CR12: withdraw 释放全部原 claims / unknown 保留全部 ──

def test_cr12_withdraw_success_releases_all_original_claims(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    assert len(_active_claims(db, op["operation_id"])) == 4

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_success(0, "port-unbind")
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "withdrawn"
    assert len(_active_claims(db, op["operation_id"])) == 0


def test_cr12_withdraw_unknown_keeps_all_claims(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_failure(0, "port-unbind", False, "timeout")
        d.status = "unknown"
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert resp.status_code == 200
    claims = _active_claims(db, op["operation_id"])
    assert len(claims) == 4
    assert all(c.status == "ambiguous" for c in claims)


# ── CR13: reconcile 按 action/期望状态 ──

def _seed_unknown_port_bind(client, db):
    device, _, vpc = _seed_ready(client, db)

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-bind")
            unit_hooks.after_unit_failure(0, "port-bind", False, "timeout")
        d.status = "unknown"
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        op = _do_access(client, db, device, vpc, auto_apply=True)
    return device, vpc, op


def test_cr13_reconcile_port_bind_active_resolves_success(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op["operation_id"]).first()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    snap.validation_result = "active"
    # CR20: port_bind 对账需目标端口 scoped 正向证据
    cmd = f"display current-configuration interface {binding.interface_name}"
    snap.snapshot_data = json.dumps({"commands": {cmd: {"success": True, "output": "service-instance 3200\n xconnect vsi vsi-a", "error": None}}})
    db.commit()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["reconciled"] is True
    # 一致收尾：operation 不再 unknown，claims 释放
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first()
    assert refreshed.status in ("awaiting_validation", "succeeded")
    assert len(_active_claims(db, op["operation_id"])) == 0


def _seed_unknown_port_unbind(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_failure(0, "port-unbind", False, "timeout")
        d.status = "unknown"
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    return device, vpc, op


def test_cr13_reconcile_port_unbind_active_not_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op["operation_id"]).first()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    # validation active（VPC 仍存在）+ 端口 config 仍含 service_instance → 撤回未生效
    port_cmd = f"display current-configuration interface {binding.interface_name}"
    snap.validation_result = "active"
    snap.snapshot_data = json.dumps({"commands": {port_cmd: {"success": True, "output": f"service-instance {binding.service_instance}", "error": None}}})
    db.commit()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    data = resp.json()["data"]
    # active 不能解析为撤回成功
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first()
    assert refreshed.status != "withdrawn"


def test_cr13_reconcile_port_unbind_absent_resolves_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op["operation_id"]).first()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    port_cmd = f"display current-configuration interface {binding.interface_name}"
    snap.validation_result = "active"
    # 配置缺失（scoped）→ 撤回成功
    snap.snapshot_data = json.dumps({"commands": {port_cmd: {"success": True, "output": "interface GigabitEthernet1/0/1", "error": None}}})
    db.commit()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["reconciled"] is True
    refreshed = db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first()
    assert refreshed.status == "withdrawn"
    assert len(_active_claims(db, op["operation_id"])) == 0


# ── CR14: started unit 重放阻断 I/O + legacy 多单元 ──

def test_cr14_started_unit_replay_blocks_io(db):
    from app.utils.crypto import encrypt_password
    device = Device(name="Leaf-04", host="192.168.100.5", port=830, username="admin",
                    password_encrypted=encrypt_password("test_password_xyz"),
                    protected_interfaces="[]", platform="LSTN", sdn_role="evpn_leaf")
    db.add(device); db.flush()
    tenant = SdnTenant(name="t", rd="1:1", import_rt="1:1", export_rt="1:1", l3_vni=10001)
    db.add(tenant); db.flush()
    vpc = SdnVpc(tenant_id=tenant.id, name="v", cidr="10.1.0.0/24", gateway_ip="10.1.0.1",
                 gateway_mac="00:00:5e:00:01:01", vni=10001, vsi_name="vsi-a", vsi_interface=1,
                 vlan_id=100, status="deployed", version=0)
    db.add(vpc); db.flush()
    dep = SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="port_bind", unit="port-bind",
                        planned_config=json.dumps([{"name": "port-bind", "cli_commands": ["vsi a"], "xml_payloads": []}]),
                        status="pending")
    db.add(dep); db.flush()
    op = SdnOperation(idempotency_key="cr14-replay", fingerprint="f", operation_type="terminal_access",
                      tenant_id=tenant.id, vpc_id=vpc.id, device_id=device.id, status="claimed")
    db.add(op); db.commit()
    attempt = create_attempt(db, operation_id=op.id, kind="execute", deployment_id=dep.id)
    db.add(SdnAttemptUnit(attempt_id=attempt.id, unit_index=0, unit_name="port-bind", state="started"))
    db.commit()

    hooks = __import__("app.services.sdn_operation_service", fromlist=["AttemptUnitHooks"]).AttemptUnitHooks(db, attempt.id)
    with patch("app.utils.ssh_executor.SSHExecutor") as mock_ssh:
        result = SdnDeploymentExecutor().execute(db, dep.id, unit_hooks=hooks)
    # CR14: before_unit CAS 失败（unit 已 started）→ 阻断 I/O，deployment 落 unknown
    assert result.status == "unknown"
    mock_ssh.assert_not_called()


def test_cr14_legacy_two_units_created_and_updated(db):
    from app.utils.crypto import encrypt_password
    from app.services.sdn_operation_service import ensure_legacy_apply_operation
    device = Device(name="Leaf-04", host="192.168.100.5", port=830, username="admin",
                    password_encrypted=encrypt_password("test_password_xyz"),
                    protected_interfaces="[]", platform="LSTN", sdn_role="evpn_leaf")
    db.add(device); db.flush()
    tenant = SdnTenant(name="t", rd="1:1", import_rt="1:1", export_rt="1:1", l3_vni=10001)
    db.add(tenant); db.flush()
    vpc = SdnVpc(tenant_id=tenant.id, name="v", cidr="10.1.0.0/24", gateway_ip="10.1.0.1",
                 gateway_mac="00:00:5e:00:01:01", vni=10001, vsi_name="vsi-a", vsi_interface=1,
                 vlan_id=100, status="deployed", version=0)
    db.add(vpc); db.flush()
    planned = json.dumps([
        {"name": "unit-a", "cli_commands": ["vsi a"], "xml_payloads": []},
        {"name": "unit-b", "cli_commands": ["vsi b"], "xml_payloads": []},
    ])
    dep = SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="create", unit="vpc-create-all",
                        planned_config=planned, status="pending")
    db.add(dep); db.commit()

    attempt_id = ensure_legacy_apply_operation(db, dep)
    units = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == attempt_id).order_by(SdnAttemptUnit.unit_index).all()
    assert [u.unit_name for u in units] == ["unit-a", "unit-b"]

    # 模拟 executor 两单元都 started→succeeded，两个 unit 行都被更新
    from app.services.sdn_operation_service import mark_unit_started, mark_unit_done
    for u in units:
        assert mark_unit_started(db, attempt_id, u.unit_index) is True
        assert mark_unit_done(db, attempt_id, u.unit_index, state="succeeded") is True
    db.commit()
    db.expire_all()  # expire_on_commit=False，需显式刷新 identity map
    states = [u.state for u in db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == attempt_id).order_by(SdnAttemptUnit.unit_index).all()]
    assert states == ["succeeded", "succeeded"]


# ── CR16: 主机观测不混入远端 Type-2 + IP 精确匹配 ──

def test_cr16_remote_type2_does_not_mark_host_observed():
    from app.routers.sdn_access import _build_host_observations
    data = json.dumps({"commands": {
        "display evpn route arp": {"success": True, "output": "10.1.0.2 -> remote MAC", "error": None},
        "display bgp l2vpn evpn": {"success": True, "output": "[2][10.1.0.2]", "error": None},
    }})
    observations, host_observed = _build_host_observations(data, "10.1.0.2", "GigabitEthernet1/0/1")
    assert host_observed is False
    assert all(o["source"] == "remote" for o in observations)


def test_cr16_local_port_association_marks_host_observed():
    from app.routers.sdn_access import _build_host_observations
    data = json.dumps({"commands": {
        "display arp vpn-instance sdn_l3vpn": {
            "success": True,
            "output": "10.1.0.2  xxxx-xxxx-xxxx  100  GigabitEthernet1/0/1",
            "error": None,
        },
    }})
    observations, host_observed = _build_host_observations(data, "10.1.0.2", "GigabitEthernet1/0/1")
    assert host_observed is True
    local = [o for o in observations if o["source"] == "local"]
    assert local and local[0]["ip_match"] and local[0]["port_match"]


def test_cr16_ip_substring_not_matched():
    from app.routers.sdn_access import _ip_exact_match
    assert _ip_exact_match("10.1.0.2", "10.1.0.2") is True
    assert _ip_exact_match("10.1.0.20", "10.1.0.2") is False
    assert _ip_exact_match("10.1.0.200", "10.1.0.2") is False


# ── CR17: 四维验证不互相冒充 + ping 诚实 ──

def _complete_with(client, db, ping_status, *, force=True, coll=None):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"]).first()
    dep.status = "success"
    dep.config_completed_at = datetime.utcnow()
    # CR22: complete 只允许 awaiting_validation（模拟 apply 成功后的状态）
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()
    snap = SdnValidationSnapshot(
        vpc_id=vpc.id, device_id=device.id, validation_result="active",
        collection_started_at=dep.config_completed_at + timedelta(seconds=1),
        collection_completed_at=dep.config_completed_at + timedelta(seconds=2),
        validation_details=json.dumps({
            "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
            "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
        }),
        snapshot_data=json.dumps({"commands": {
            "display arp vpn-instance sdn_l3vpn": {
                "success": True,
                "output": "10.1.0.2  xxxx-xxxx-xxxx  100  GigabitEthernet1/0/1",
                "error": None,
            },
        }}),
    )
    db.add(snap)
    db.commit()
    if coll is not None:
        sync_ret = coll
    else:
        sync_ret = (snap, None, False)
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=sync_ret):
        with patch("app.routers.sdn_access._run_gateway_ping", return_value=ping_status):
            resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": force})
    return resp


def test_cr17_ping_unreachable_degrades_not_succeeds(client, db):
    resp = _complete_with(client, db, {"status": "unreachable", "detail": "timeout"})
    data = resp.json()["data"]
    assert data["gateway_ping"]["status"] == "unreachable"
    assert data["status"] != "succeeded"


def test_cr17_ping_error_unknown_not_succeeds(client, db):
    resp = _complete_with(client, db, {"status": "error", "detail": "boom"})
    data = resp.json()["data"]
    assert data["gateway_ping"]["status"] == "error"
    assert data["status"] == "unknown"


def test_cr17_ping_unsupported_does_not_block_success(client, db):
    resp = _complete_with(client, db, {"status": "unsupported", "detail": "no gateway"})
    data = resp.json()["data"]
    assert data["gateway_ping"]["status"] == "unsupported"
    assert data["status"] == "succeeded"


def test_cr17_evidence_insufficient_not_success(client, db):
    resp = _complete_with(client, db, {"status": "not_run", "detail": ""}, coll=(None, {"key": "sdn.device_not_writable", "params": {}}, False))
    data = resp.json()["data"]
    assert data["status"] == "unknown"
    assert data["dimensions"]["evidence"]["status"] == "insufficient"


# ── CR18: SHALL 覆盖缺口（4.2 依赖重放 / 6.4 撤回矩阵 / 7.2 终端视图明细）──

def test_cr18_dependency_prior_not_succeeded_blocks(db):
    from app.services.sdn_operation_service import AttemptUnitHooks, create_attempt
    device, _, vpc = _seed_ready(client=None, db=db)
    op = SdnOperation(idempotency_key="dep-replay", fingerprint="f", operation_type="terminal_access",
                      tenant_id=vpc.tenant_id, vpc_id=vpc.id, device_id=device.id, status="claimed")
    db.add(op); db.commit()
    attempt = create_attempt(db, operation_id=op.id, kind="execute")
    db.add(SdnAttemptUnit(attempt_id=attempt.id, unit_index=0, unit_name="unit-a", state="started"))
    db.add(SdnAttemptUnit(attempt_id=attempt.id, unit_index=1, unit_name="unit-b", state="not_started"))
    db.commit()
    hooks = AttemptUnitHooks(db, attempt.id)
    # 依赖 unit 0 未 succeeded → unit 1 不得执行
    assert hooks.before_unit(1, "unit-b") is False


def test_cr18_withdraw_idempotent(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)

    def _fake_exec(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_success(0, "port-unbind")
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_exec):
        first = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
        second = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert first.json()["data"]["status"] == "withdrawn"
    assert second.json()["data"]["status"] == "withdrawn"
    # 幂等：只产生一个 port_unbind deployment
    assert db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"], SdnDeployment.action == "port_unbind").count() == 1


def test_cr18_withdraw_blocked_by_new_reference(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op["operation_id"]).first()
    # 新引用：另一 operation 对同一 binding 生成 deployment
    db.add(SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="port_bind", unit="port-bind",
                         port_binding_id=binding.id, planned_config="[]", status="pending", operation_id=999))
    db.commit()
    resp = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.unsafe_withdrawal"


def test_cr18_read_does_not_bump_version(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op["operation_id"]).first()
    v0 = binding.version
    client.get(f"/api/sdn/operations/{op['operation_id']}")
    db.expire_all()
    binding = db.query(SdnPortBinding).filter(SdnPortBinding.id == binding.id).first()
    assert binding.version == v0


def test_cr18_overview_observations_filter_remote(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    # 仅远端 EVPN Type-2 含 IP → overview 观测 host_observed=false，且标 remote
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    snap.snapshot_data = json.dumps({"commands": {
        "display evpn route arp": {"success": True, "output": "10.1.0.2 -> remote", "error": None},
    }})
    db.commit()
    resp = client.get(f"/api/sdn/vpcs/{vpc.id}/access-overview")
    assert resp.status_code == 200
    data = resp.json()["data"]
    obs = [o for o in data["observations"] if o["operation_id"] == op["operation_id"]]
    assert obs and obs[0]["host_observed"] is False
    assert all(item["scope"] == "remote" for item in obs[0]["items"])

