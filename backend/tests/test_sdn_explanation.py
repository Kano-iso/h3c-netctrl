"""S1-026 operation 解释投影测试（纯函数 + API 级只读投影契约）。

覆盖：正常 execute / validate / withdraw / reconcile、unknown、空/畸形 evidence、
legacy operation；并明确证明 raw evidence 未丢失、旧响应字段未移除、接口不因
解释失败而 500。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import (
    Device,
    SdnAttempt,
    SdnAttemptUnit,
    SdnDeployment,
    SdnOperation,
    SdnPortBinding,
    SdnTenant,
    SdnVpc,
    SdnValidationSnapshot,
)
from app.services.sdn_explanation import (
    explain_attempt,
    explain_operation,
    explain_unit,
)

# ── 纯函数：operation 级 ──


def _op(status="succeeded", op_type="terminal_access", host="10.1.0.2"):
    return {"operation_type": op_type, "status": status, "expected_host_ip": host}


_SCOPE = {
    "tenant_id": 1, "tenant_name": "研发", "vpc_id": 2, "vpc_name": "vpc-a",
    "device_id": 3, "device_name": "Leaf-04", "if_index": 1,
    "interface_name": "GigabitEthernet1/0/1", "service_instance": 3200,
    "access_vlan": 100, "expected_host_ip": "10.1.0.2",
}


def test_operation_succeeded_without_validate_is_recorded_not_verified():
    e = explain_operation(_op(), _SCOPE, [])
    assert e["intent"] == "access_bind"
    assert e["truth_state"] == "succeeded_recorded"  # 执行记录成功 ≠ 设备验证成功
    assert e["safety_boundary"]["target"] == {
        "device_id": 3, "if_index": 1, "interface_name": "GigabitEthernet1/0/1"}
    assert e["safety_boundary"]["target_only"] is True
    assert e["safety_boundary"]["ambiguous_claims"] is False
    assert "vpc=vpc-a" in e["scope_summary"]
    assert "device=Leaf-04" in e["scope_summary"]
    assert "GigabitEthernet1/0/1(1)" in e["scope_summary"]
    assert "host=10.1.0.2" in e["scope_summary"]
    assert e["headline"] == "access_bind GigabitEthernet1/0/1 succeeded_recorded"


def test_operation_verified_only_when_validate_attempt_succeeded():
    attempts = [{"kind": "execute", "status": "succeeded", "evidence": None},
                {"kind": "validate", "status": "succeeded", "evidence": {"dimensions": {}}}]
    assert explain_operation(_op(), _SCOPE, attempts)["truth_state"] == "verified"


def test_operation_failed_validate_does_not_claim_verified():
    attempts = [{"kind": "execute", "status": "succeeded", "evidence": None},
                {"kind": "validate", "status": "failed_known", "evidence": {"dimensions": {}}}]
    assert explain_operation(_op(), _SCOPE, attempts)["truth_state"] == "succeeded_recorded"


def test_operation_unknown_marks_ambiguous_claims():
    e = explain_operation(_op(status="unknown"), _SCOPE, [])
    assert e["truth_state"] == "unknown"
    assert e["safety_boundary"]["ambiguous_claims"] is True


def test_operation_resolved_after_stale_takeover_is_not_still_ambiguous():
    attempts = [{"kind": "execute", "status": "succeeded", "evidence": None},
                {"kind": "reconcile", "status": "unknown",
                 "evidence": {"stale_takeover": True, "from_status": "applying"}}]
    e = explain_operation(_op(), _SCOPE, attempts)
    assert e["safety_boundary"]["ambiguous_claims"] is False


def test_operation_insufficient_evidence_marks_ambiguous():
    attempts = [{"kind": "validate", "status": "unknown",
                 "evidence": {"dimensions": {"evidence": {"status": "insufficient", "reason": "k"}}}}]
    assert explain_operation(_op(status="unknown"), _SCOPE, attempts)["safety_boundary"]["ambiguous_claims"] is True


def test_operation_withdraw_intent_and_target_only():
    e = explain_operation(_op(op_type="terminal_withdraw", status="withdrawn"), _SCOPE, [])
    assert e["intent"] == "access_unbind"
    assert e["truth_state"] == "withdrawn"
    assert e["safety_boundary"]["target_only"] is True


def test_operation_legacy_apply_is_not_single_interface():
    e = explain_operation(_op(op_type="legacy_apply", status="applied"), None, [])
    assert e["intent"] == "legacy_apply"
    assert e["truth_state"] == "applied"
    assert e["safety_boundary"]["target_only"] is False
    assert e["safety_boundary"]["target"] is None
    assert e["scope_summary"] is None


def test_operation_pending_statuses():
    for st in ("planned", "awaiting_wiring", "applying", "awaiting_validation",
               "validating", "withdrawing", "reconciling"):
        assert explain_operation(_op(status=st), _SCOPE, [])["truth_state"] == "pending"


# ── 纯函数：attempt 级 ──


def _att(kind="validate", status="succeeded", evidence=None, completed_at="2026-09-10T01:00:00"):
    return {"kind": kind, "status": status, "started_at": "2026-09-10T00:59:00",
            "completed_at": completed_at, "evidence": evidence}


def test_attempt_validate_four_dimension_basis():
    ev = {"dimensions": {"execution": {"status": "succeeded"}, "evidence": {"status": "fresh"}},
          "gateway_ping": {"status": "ok"}, "observations": []}
    e = explain_attempt(_att("validate", "succeeded", ev))
    assert e["kind"] == "validate"
    assert e["result"] == "succeeded"
    assert e["finished"] is True
    assert e["still_uncertain"] is False
    assert e["evidence_basis"] == "four_dimension_validation"


def test_attempt_insufficient_evidence_basis_and_statement():
    ev = {"dimensions": {"evidence": {"status": "insufficient", "reason": "collect_failed"}}}
    e = explain_attempt(_att("validate", "unknown", ev))
    assert e["evidence_basis"] == "insufficient_evidence"
    assert "could not collect" in e["statement"]
    assert e["still_uncertain"] is True


def test_attempt_stale_takeover_basis():
    ev = {"stale_takeover": True, "from_status": "applying"}
    e = explain_attempt(_att("reconcile", "unknown", ev))
    assert e["evidence_basis"] == "stale_takeover"


def test_attempt_execute_execution_record_basis_no_evidence():
    e = explain_attempt(_att("execute", "succeeded", None))
    assert e["evidence_basis"] == "execution_record"


def test_attempt_failed_known_is_determinate_not_uncertain():
    e = explain_attempt(_att("validate", "failed_known", {"dimensions": {}}))
    assert e["still_uncertain"] is False
    assert e["statement"] == "validate finished with known failure"


def test_attempt_unfinished_uncertain():
    e = explain_attempt(_att("execute", "claimed", None, completed_at=None))
    assert e["finished"] is False
    assert e["still_uncertain"] is True


# ── 纯函数：unit 级 ──


def _unit(state="succeeded", evidence=None, completed_at="2026-09-10T01:00:00"):
    return {"unit_name": "port-bind", "state": state, "evidence": evidence,
            "started_at": "2026-09-10T00:59:00", "completed_at": completed_at}


def test_unit_succeeded_without_evidence_is_desired_record_only():
    e = explain_unit(_unit(), attempt_kind="execute", attempt_scope=_SCOPE)
    assert e["truth_kind"] == "desired"
    assert e["category"] == "execution_record"
    assert e["source"] == "execution_record"
    assert "not device-verified" in e["statement"]
    assert e["observed_at"] is None
    assert e["freshness"] is None
    assert e["scope"] == _SCOPE  # 继承 attempt scope（数据可证）


def test_unit_failed_known_definitive_is_observed_device_rejection():
    e = explain_unit(_unit("failed_known", {"error": "Wrong parameter", "definitive": True}))
    assert e["truth_kind"] == "observed"
    assert e["category"] == "device_rejection"
    assert e["source"] == "device_response"
    assert "Wrong parameter" in e["statement"]


def test_unit_unknown_is_pending():
    e = explain_unit(_unit("unknown", None))
    assert e["truth_kind"] == "pending"
    assert e["category"] == "uncertain_outcome"
    assert e["source"] is None


def test_unit_failed_known_non_definitive_is_uncertain():
    e = explain_unit(_unit("failed_known", {"error": "timeout", "definitive": False}))
    assert e["truth_kind"] == "pending"
    assert e["category"] == "failure_uncertain"


def test_unit_started_and_not_started_pending():
    e = explain_unit(_unit("started", None, completed_at=None))
    assert e["truth_kind"] == "pending"
    assert e["category"] == "in_progress"
    e2 = explain_unit(_unit("not_started", None, completed_at=None))
    assert e2["truth_kind"] == "pending"
    assert e2["category"] == "not_finished"


def test_unit_reconciled_execute_is_observed():
    e = explain_unit(_unit("succeeded", {"reconciled": True, "snapshot_id": 9, "reason": "scoped ok"}),
                     attempt_kind="execute", attempt_scope=None)
    assert e["truth_kind"] == "observed"
    assert e["category"] == "readback_verified"
    assert e["source"] == "snapshot"
    assert e["scope"] is None


def test_unit_reconciled_withdraw_is_inferred_syntax_match():
    e = explain_unit(_unit("succeeded", {"reconciled": True, "snapshot_id": 9, "reason": "missing"}),
                     attempt_kind="withdraw", attempt_scope=None)
    assert e["truth_kind"] == "inferred"
    assert e["category"] == "readback_syntax_match"
    assert "removal" in e["statement"]


# ── 纯函数：畸形/空输入稳定降级（绝不抛异常） ──


def test_projection_functions_never_raise_on_garbage():
    for garbage in (None, "text", 3.14, ["a"], b"bytes", {"unexpected": object()}):
        out = explain_operation(garbage, garbage, garbage)
        assert isinstance(out, dict)
        out = explain_attempt(garbage)
        assert isinstance(out, dict)
        out = explain_unit(garbage, attempt_kind=garbage, attempt_scope=garbage)
        assert isinstance(out, dict)
    # 空 evidence / 空 scope / 空 attempts
    e = explain_operation({"operation_type": "terminal_access", "status": "unknown"}, None, [])
    assert e["scope_summary"] is None
    assert e["safety_boundary"]["target"] is None
    assert e["truth_state"] == "unknown"


def test_unit_scope_null_when_attempt_has_no_scope():
    e = explain_unit(_unit(), attempt_kind="execute", attempt_scope=None)
    assert e["scope"] is None


# ── API 级：GET /operations/{id} 投影存在 + 原始字段保留 ──


def _seed_ready(client, db, *, host="192.168.100.5"):
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


def test_api_operation_detail_has_explanation_and_raw_fields_intact(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-00000001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]

    resp = client.get(f"/api/sdn/operations/{op['operation_id']}")
    assert resp.status_code == 200
    data = resp.json()["data"]

    # S1-026: 投影存在且结构正确
    expl = data["explanation"]
    assert expl["intent"] == "access_bind"
    assert expl["truth_state"] in ("pending", "succeeded_recorded")
    assert expl["scope_summary"] and "host=10.1.0.2" in expl["scope_summary"]
    assert expl["safety_boundary"]["target"]["device_id"] == device.id
    assert expl["safety_boundary"]["target_only"] is True
    assert expl["safety_boundary"]["protected_interfaces"] is None

    # 原始字段未移除、未改写
    assert data["operation_id"] == op["operation_id"]
    assert data["operation_type"] == "terminal_access"
    assert data["status"] == op["status"]
    assert data["scope"] is not None
    assert data["scope"]["expected_host_ip"] == "10.1.0.2"
    assert data["attempts"]
    assert data["attempts"][0]["kind"] == "execute"
    assert data["attempts"][0]["units"]
    # attempt/unit 级投影 + raw evidence 保留
    assert "explanation" in data["attempts"][0]
    unit0 = data["attempts"][0]["units"][0]
    assert "evidence" in unit0  # raw 字段仍在
    assert unit0["explanation"]["truth_kind"] in ("desired", "pending", "observed", "inferred")
    # scope 引用同一对象：projection 不改写原始 evidence
    assert data["attempts"][0]["units"][0].get("evidence") == unit0.get("evidence")


def test_api_operation_detail_survives_malformed_historical_json(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-malformed-json", "plan_id": plan_id, "auto_apply": False}
    op_data = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]
    op = db.query(SdnOperation).filter(SdnOperation.id == op_data["operation_id"]).first()
    op.scope_json = "{broken"
    attempt = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op.id).order_by(SdnAttempt.id).first()
    attempt.evidence_json = "[broken"
    attempt.scope_json = "{broken"
    unit = db.query(SdnAttemptUnit).filter(SdnAttemptUnit.attempt_id == attempt.id).order_by(SdnAttemptUnit.unit_index).first()
    unit.evidence_json = "{broken"
    db.commit()

    resp = client.get(f"/api/sdn/operations/{op.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["scope"] is None
    assert data["attempts"][0]["units"][0]["evidence"] is None
    assert data["explanation"]["scope_summary"] is None


@patch("app.routers.sdn_access.SdnDeploymentExecutor.execute")
def test_api_operation_withdraw_explanation_truth(mock_exec, client, db):
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

    data = client.get(f"/api/sdn/operations/{op['operation_id']}").json()["data"]
    assert data["status"] == "withdrawn"
    # operation 本身是 terminal_access（withdraw 是其上的一次动作），intent 不变、truth_state 变 withdrawn
    assert data["explanation"]["intent"] == "access_bind"
    assert data["explanation"]["truth_state"] == "withdrawn"
    # withdraw attempt 的 unit 成功无观察证据 → desired 执行记录
    withdraw_attempt = next(a for a in data["attempts"] if a["kind"] == "withdraw")
    assert withdraw_attempt["explanation"]["kind"] == "withdraw"
    assert withdraw_attempt["units"][0]["explanation"]["truth_kind"] == "desired"
    assert withdraw_attempt["units"][0]["explanation"]["category"] == "execution_record"
