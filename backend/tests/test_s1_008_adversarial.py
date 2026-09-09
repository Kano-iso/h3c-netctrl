"""S1-008 对抗性测试：CR19-CR23 关键安全断言。

这些断言在 S1-007 现状上会失败：
- reconcile 真正解析 unknown unit + CAS 零行不得成功（CR19）
- port_bind reconcile 需要目标端口 scoped 正向证据（CR20）
- port_unbind reconcile 不得把采集失败当配置缺失（CR21）
- complete/validate 遵守 claim 与终态守卫（CR22）
- 主机 IP 与端口必须来自同一条本地记录（CR23）
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import (
    SdnAttempt,
    SdnAttemptUnit,
    SdnDeployment,
    SdnOperation,
    SdnPortBinding,
    SdnResourceClaim,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.services.sdn_operation_service import (
    acquire_claims,
    release_claims,
    vpc_device_key,
)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402
from test_s1_007_adversarial import (  # noqa: E402
    _active_claims,
    _do_access,
    _seed_unknown_port_bind,
    _seed_unknown_port_unbind,
)


def _operation_claims(vpc, device_id, if_index):
    from app.services.sdn_operation_service import tenant_key, vpc_key, device_port_key
    return [tenant_key(vpc.tenant_id), vpc_key(vpc.id), vpc_device_key(vpc.id, device_id), device_port_key(device_id, if_index)]


def _set_port_snapshot(db, vpc, binding, *, output, success=True, error=None, present=True, validation_result="active"):
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    cmd = f"display current-configuration interface {binding.interface_name}"
    commands = {}
    if present:
        commands[cmd] = {"success": success, "output": output, "error": error}
    snap.validation_result = validation_result
    snap.snapshot_data = json.dumps({"commands": commands})
    db.commit()
    return snap


def _reconcile(client, op_id, snap):
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        return client.post(f"/api/sdn/operations/{op_id}/reconcile")


def _binding(db, op_id):
    return db.query(SdnPortBinding).filter(SdnPortBinding.operation_id == op_id).first()


def _original_attempt(db, op_id):
    return db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind.in_(("execute", "withdraw"))).order_by(SdnAttempt.id.desc()).first()


# ── CR19: reconcile 真正解析 unknown unit ──

def test_cr19_unknown_unit_reconciles_consistently(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="service-instance 3200\n xconnect vsi vsi-a")

    resp = _reconcile(client, op["operation_id"], snap)
    data = resp.json()["data"]
    assert data["reconciled"] is True

    attempt = _original_attempt(db, op["operation_id"])
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == attempt.id).first()
    assert unit.state == "succeeded"  # unknown 真正被解析

    db.expire_all()
    attempt = _original_attempt(db, op["operation_id"])
    assert attempt.status == "succeeded"  # 由 unit 重推，非硬写
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"], SdnDeployment.action == "port_bind").first()
    assert dep.status == "success"
    op2 = db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first()
    assert op2.status == "awaiting_validation"
    assert _binding(db, op["operation_id"]).status == "active"
    assert len(_active_claims(db, op["operation_id"])) == 0


def test_cr19_cas_zero_row_keeps_unknown_ambiguous_no_release(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="service-instance 3200\n xconnect vsi vsi-a")

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        with patch("app.routers.sdn_access.mark_unit_reconciled", return_value=False):
            resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    data = resp.json()["data"]
    assert data["reconciled"] is False
    op2 = db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first()
    assert op2.status == "unknown"
    claims = _active_claims(db, op["operation_id"])
    assert len(claims) == 4
    assert all(c.status == "ambiguous" for c in claims)


# ── CR20: port_bind reconcile 需要目标端口 scoped 正向证据 ──

def test_cr20_port_bind_vpc_active_without_port_config_not_success(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = _binding(db, op["operation_id"])
    # VPC active，但目标端口回读无 service-instance/xconnect 标记
    snap = _set_port_snapshot(db, vpc, binding, output="interface GigabitEthernet1/0/1")
    resp = _reconcile(client, op["operation_id"], snap)
    data = resp.json()["data"]
    assert data["reconciled"] is False
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "unknown"


def test_cr20_port_bind_scoped_config_complete_success(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="service-instance 3200\n xconnect vsi vsi-a")
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is True
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "awaiting_validation"


# ── CR21: port_unbind 不得把采集失败当配置缺失 ──

def test_cr21_port_unbind_missing_command_not_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="", present=False)
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is False
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "unknown"


def test_cr21_port_unbind_command_failed_not_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="", success=False)
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is False


def test_cr21_port_unbind_cli_error_not_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    snap = _set_port_snapshot(db, vpc, binding, output="", error="Unrecognized command")
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is False


def test_cr21_port_unbind_number_false_hit_not_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    # "3200" 只作为 "13200" 子串出现，不能当作 service-instance 3200 命中
    snap = _set_port_snapshot(db, vpc, binding, output="service-instance 13200\n xconnect vsi vsi-a")
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is False
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "unknown"


def test_cr21_port_unbind_scoped_absent_success(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    # 命令有效且 service-instance 3200 + xconnect vsi vsi-a 均确认缺失
    snap = _set_port_snapshot(db, vpc, binding, output="interface GigabitEthernet1/0/1")
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is True
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "withdrawn"


# ── CR22: complete/validate claim 与终态守卫 ──

def test_cr22_complete_claim_conflict(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"]).first()
    dep.status = "success"
    dep.config_completed_at = datetime.utcnow()
    # 模拟 apply 成功：释放本 op 全部 claims + 进入 awaiting_validation
    release_claims(db, _operation_claims(vpc, device.id, 1), owner_operation_id=op["operation_id"])
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()
    # 另一 operation 抢占 vpc-device claim → complete 必须 resource_busy
    other = SdnOperation(idempotency_key="other-op-008", fingerprint="f", operation_type="terminal_access",
                         tenant_id=vpc.tenant_id, vpc_id=vpc.id, device_id=device.id, status="claimed")
    db.add(other); db.flush()
    acquire_claims(db, [vpc_device_key(vpc.id, device.id)], operation_id=other.id, attempt_id=None)
    db.commit()

    resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.resource_busy"


def test_cr22_withdrawn_complete_no_mutation(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)

    def _fake_withdraw(s, dep_id, *, unit_hooks=None):
        d = db.query(SdnDeployment).filter(SdnDeployment.id == dep_id).first()
        if unit_hooks is not None:
            unit_hooks.before_unit(0, "port-unbind")
            unit_hooks.after_unit_success(0, "port-unbind")
        d.status = "success"
        d.config_completed_at = datetime.utcnow()
        db.commit()
        return d

    with patch("app.routers.sdn_access.SdnDeploymentExecutor.execute", side_effect=_fake_withdraw):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/withdraw", json={})
    assert resp.json()["data"]["status"] == "withdrawn"

    resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "withdrawn"
    # 不得新建 validate attempt
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op["operation_id"], SdnAttempt.kind == "validate").count() == 0


def test_cr22_complete_uses_original_port_bind_deployment(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op["operation_id"], SdnDeployment.action == "port_bind").first()
    snap = db.query(SdnValidationSnapshot).filter(SdnValidationSnapshot.vpc_id == vpc.id).order_by(SdnValidationSnapshot.id.desc()).first()
    dep.status = "success"
    # 确定性因果窗口：port_bind 完成时间取快照采集开始前，避免 datetime.utcnow() 与 seed 快照 +1s 的竞态
    dep.config_completed_at = snap.collection_started_at - timedelta(seconds=1)
    # 较新的 port_unbind deployment（不得冒充原 port_bind 执行证据）
    db.add(SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="port_unbind", unit="port-unbind",
                         port_binding_id=_binding(db, op["operation_id"]).id, planned_config="[]",
                         status="success", operation_id=op["operation_id"]))
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()

    snap.validation_details = json.dumps({
        "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
        "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
    })
    snap.snapshot_data = json.dumps({"commands": {
        "display arp vpn-instance sdn_l3vpn": {
            "success": True,
            "output": "10.1.0.2  aaaa-bbbb-cccc  100  GigabitEthernet1/0/1",
            "error": None,
        },
    }})
    db.commit()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        with patch("app.routers.sdn_access._run_gateway_ping", return_value={"status": "unsupported", "detail": "no gateway"}):
            resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})
    data = resp.json()["data"]
    # 用了原 port_bind（exec_ok=true）→ succeeded；若误用 port_unbind（无 config_completed_at）会 unknown/failed
    assert data["status"] == "succeeded"


# ── CR23: 主机 IP 与端口必须同一条本地记录 ──

def test_cr23_arp_different_lines_not_host_observed():
    from app.routers.sdn_access import _build_host_observations
    data = json.dumps({"commands": {
        "display arp vpn-instance sdn_l3vpn": {
            "success": True,
            "output": "10.1.0.2  aaaa-bbbb-cccc  100  GigabitEthernet1/0/2\n10.1.0.3  dddd-eeee-ffff  100  GigabitEthernet1/0/1",
            "error": None,
        },
    }})
    observations, host_observed = _build_host_observations(data, "10.1.0.2", "GigabitEthernet1/0/1")
    assert host_observed is False


def test_cr23_arp_same_line_host_observed():
    from app.routers.sdn_access import _build_host_observations
    data = json.dumps({"commands": {
        "display arp vpn-instance sdn_l3vpn": {
            "success": True,
            "output": "10.1.0.2  aaaa-bbbb-cccc  100  GigabitEthernet1/0/1",
            "error": None,
        },
    }})
    observations, host_observed = _build_host_observations(data, "10.1.0.2", "GigabitEthernet1/0/1")
    assert host_observed is True


def test_cr23_command_failed_not_observed():
    from app.routers.sdn_access import _build_host_observations
    data = json.dumps({"commands": {
        "display arp vpn-instance sdn_l3vpn": {
            "success": False,
            "output": "10.1.0.2  aaaa-bbbb-cccc  100  GigabitEthernet1/0/1",
            "error": "command failed",
        },
    }})
    observations, host_observed = _build_host_observations(data, "10.1.0.2", "GigabitEthernet1/0/1")
    assert host_observed is False
