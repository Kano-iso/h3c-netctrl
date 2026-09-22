"""S2-008-R1 契约测试：operation detail 多对象变更影响投影（只读、additive、复用同一 truth 系统）。

S2-008-R1 复审返工后的契约：
- impact 嵌套在既有 additive `explanation.impact` 之下（顶层无影子字段）；explanation
  或 impact builder 异常时 detail 仍 200，explanation.impact 明确 unavailable；
- 接口节点为稳定复合身份（device identity + if_index），跨 Leaf 不碰撞；scope 缺 device
  时不编造全局接口身份；可读字段 device_id/if_index/interface_name 保留，关系端点引用
  同一身份；
- source 如实区分 operation_scope / operation_record（malformed/no scope 回退记录来源）；
- safety 复用 explain_operation 同一判定（含 attempt 中 stale_takeover / insufficient
  evidence 的歧义），不另写简化判定；
- 关系 operation-type aware：access 用 expects，withdraw 用 withdraws，legacy 不编造；
- 变更项复用 explain_attempt/explain_unit 的 truth_kind/source/statement；只读零 I/O
  零写入；脱敏；旧字段不删不改。
"""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnAttempt, SdnAttemptUnit, SdnDeployment, SdnOperation, SdnTenant, SdnVpc
from app.services.sdn_explanation import build_operation_impact, explain_operation

NOW = datetime.utcnow()

SCOPE = {
    "tenant_id": 1,
    "tenant_name": "研发",
    "vpc_id": 10,
    "vpc_name": "vpc-a",
    "device_id": 20,
    "device_name": "Leaf-04",
    "if_index": 1,
    "interface_name": "GigabitEthernet1/0/1",
    "service_instance": 3200,
    "access_vlan": None,
    "expected_host_ip": "10.1.0.2",
}

IFACE_ID = "device:20:if_index:1"


def _seed_op(db, *, op_type="terminal_access", status="succeeded", scope=None, expected_host_ip="10.1.0.2", vpc_id=10, device_id=20):
    op = SdnOperation(
        idempotency_key=f"ik-{uuid.uuid4().hex}",
        fingerprint=f"fp-{uuid.uuid4().hex}",
        operation_type=op_type,
        tenant_id=1,
        vpc_id=vpc_id,
        device_id=device_id,
        plan_id=None,
        expected_host_ip=expected_host_ip,
        request_payload_json=json.dumps({"secret": "REQ-SECRET-1"}),
        scope_json=json.dumps(scope) if scope else None,
        status=status,
        created_at=NOW - timedelta(minutes=10),
        updated_at=NOW - timedelta(minutes=5),
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def _seed_attempt(db, op, *, kind="execute", status="succeeded", evidence=None, units=None, scope=None):
    a = SdnAttempt(
        operation_id=op.id,
        deployment_id=None,
        kind=kind,
        status=status,
        owner="svc",
        claimed_at=NOW - timedelta(minutes=9),
        started_at=NOW - timedelta(minutes=8),
        completed_at=NOW - timedelta(minutes=6) if status not in ("claimed", "running") else None,
        scope_json=json.dumps(scope) if scope else None,
        evidence_json=json.dumps(evidence) if evidence else None,
        created_at=NOW - timedelta(minutes=9),
        updated_at=NOW - timedelta(minutes=6),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    for i, (name, state, ev) in enumerate(units or []):
        u = SdnAttemptUnit(
            attempt_id=a.id,
            unit_index=i,
            unit_name=name,
            state=state,
            evidence_json=json.dumps(ev) if ev else None,
            started_at=NOW - timedelta(minutes=7),
            completed_at=NOW - timedelta(minutes=6) if state not in ("started", "not_started", "unknown") else None,
        )
        db.add(u)
    db.commit()
    return a


def _detail(client, op_id):
    resp = client.get(f"/api/sdn/operations/{op_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "impact" in data["explanation"]
    return data


def _impact(data):
    return data["explanation"]["impact"]


# ── 纯函数：垃圾输入稳定降级 ──


def test_impact_pure_function_never_raises_on_garbage():
    for garbage in (None, "text", 3.14, ["a"], b"bytes", {"unexpected": object()}):
        out = build_operation_impact(garbage, garbage, garbage, garbage, garbage)
        assert isinstance(out, dict)
        assert set(out.keys()) == {"nodes", "relations", "changes", "safety"}
    out = build_operation_impact({"operation_type": "terminal_access", "status": "unknown"}, None, None, None, None)
    assert out["nodes"] == []
    assert out["relations"] == []
    assert out["changes"] == []
    assert out["safety"]["ambiguous_claims"] is True  # 同源判定（status unknown）
    assert out["safety"]["protected_interfaces"] is None


# ── 完整 terminal_access ──


def test_impact_full_terminal_access(client, db):
    op = _seed_op(db, scope=SCOPE)
    a_exec = _seed_attempt(db, op, kind="execute", status="succeeded", units=[("vpc-vsi", "succeeded", {})])
    a_val = _seed_attempt(
        db, op, kind="validate", status="succeeded",
        evidence={"dimensions": {"evidence": {"status": "sufficient"}}},
        units=[("validate-l2", "succeeded", {"reconciled": True})],
    )

    data = _detail(client, op.id)
    impact = _impact(data)
    # 节点：vpc/device/interface(复合身份)/host；source 如实区分
    kinds = [(n["kind"], n["id"]) for n in impact["nodes"]]
    assert kinds == [("vpc", 10), ("device", 20), ("interface", IFACE_ID), ("host", "10.1.0.2")]
    vpc_node = impact["nodes"][0]
    assert vpc_node["label"] == "vpc-a"
    assert vpc_node["truth_kind"] == "desired"
    assert vpc_node["source"] == "operation_scope"
    host_node = impact["nodes"][3]
    assert host_node["source"] == "operation_record"
    # 接口节点：复合身份 + 可读字段保留
    iface_node = impact["nodes"][2]
    assert iface_node["id"] == IFACE_ID
    assert iface_node["device_id"] == 20
    assert iface_node["if_index"] == 1
    assert iface_node["interface_name"] == "GigabitEthernet1/0/1"
    # 关系（业务范围，非物理邻接）；接口端点引用同一复合身份
    rels = [(r["from_kind"], r["relation"], r["to_kind"], r.get("to_id") if r["to_kind"] == "interface" else None) for r in impact["relations"]]
    assert rels == [
        ("vpc", "targets", "device", None),
        ("device", "exposes", "interface", IFACE_ID),
        ("interface", "expects", "host", None),
    ]
    assert impact["relations"][1]["to_id"] == IFACE_ID
    assert impact["relations"][2]["from_id"] == IFACE_ID
    # 变更项：attempt/unit 持久化顺序
    assert [c["attempt_id"] for c in impact["changes"]] == [a_exec.id, a_val.id]
    assert [c["attempt_kind"] for c in impact["changes"]] == ["execute", "validate"]
    first_unit = impact["changes"][0]["units"][0]
    assert first_unit["unit_name"] == "vpc-vsi"
    assert first_unit["state"] == "succeeded"
    # truth 完全同源（复用 attempt/unit 解释）
    api_unit0 = data["attempts"][0]["units"][0]["explanation"]
    assert first_unit["truth_kind"] == api_unit0["truth_kind"]
    assert first_unit["source"] == api_unit0["source"]
    assert first_unit["statement"] == api_unit0["statement"]
    assert first_unit["truth_kind"] == "desired"  # execute 无回读 → 仅执行记录
    api_unit1 = data["attempts"][1]["units"][0]["explanation"]
    assert impact["changes"][1]["units"][0]["truth_kind"] == api_unit1["truth_kind"] == "observed"  # validate 回读
    # safety
    assert impact["safety"]["target_only"] is True
    assert impact["safety"]["ambiguous_claims"] is False
    assert impact["safety"]["shared_vpc_gateway_not_target"] is True
    assert impact["safety"]["protected_interfaces"] is None


def test_impact_withdraw_uses_withdraws_relation(client, db):
    op = _seed_op(db, op_type="terminal_withdraw", status="withdrawn", scope=SCOPE)
    _seed_attempt(db, op, kind="withdraw", status="succeeded", units=[("withdraw-binding", "succeeded", {"reconciled": True})])
    data = _detail(client, op.id)
    impact = _impact(data)
    rels = [(r["from_kind"], r["relation"], r["to_kind"]) for r in impact["relations"]]
    # withdraw 不再表达「接口继续期望主机」，改用撤回/移除目标关系
    assert ("interface", "expects", "host") not in rels
    assert ("interface", "withdraws", "host") in rels
    assert impact["safety"]["target_only"] is True
    assert impact["safety"]["shared_vpc_gateway_not_target"] is True
    # withdraw 对账 → inferred（复用 explain_unit 语义）
    assert impact["changes"][0]["units"][0]["truth_kind"] == "inferred"


def test_impact_legacy_apply_no_fabricated_relations(client, db):
    op = _seed_op(db, op_type="legacy_apply", status="succeeded", scope=None, vpc_id=10, device_id=20)
    data = _detail(client, op.id)
    impact = _impact(data)
    # legacy/无 scope：节点回退到 operation 记录上的 vpc/device/host（source=operation_record）
    assert [(n["kind"], n["source"]) for n in impact["nodes"]] == [
        ("vpc", "operation_record"), ("device", "operation_record"), ("host", "operation_record"),
    ]
    # 无接口 → 不编造 exposes/expects/withdraws 关系
    assert [(r["from_kind"], r["relation"], r["to_kind"]) for r in impact["relations"]] == [("vpc", "targets", "device")]
    assert impact["safety"]["target_only"] is False
    assert impact["safety"]["shared_vpc_gateway_not_target"] is None


def test_impact_malformed_scope_source_operation_record(client, db):
    op = _seed_op(db, scope=SCOPE)
    _seed_attempt(db, op, kind="execute", status="succeeded", units=[("x", "succeeded", {})])
    op.scope_json = "{broken"
    db.commit()
    at = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op.id).first()
    at.evidence_json = "[broken"
    at.scope_json = "{broken"
    db.commit()

    data = _detail(client, op.id)
    impact = _impact(data)
    # scope 损坏 → vpc/device 值回退 operation 记录，source 必须如实标 operation_record；
    # label 无 scope 数据 → null
    assert [(n["kind"], n["id"], n["source"], n["label"]) for n in impact["nodes"]] == [
        ("vpc", 10, "operation_record", None),
        ("device", 20, "operation_record", None),
        ("host", "10.1.0.2", "operation_record", "10.1.0.2"),
    ]
    assert impact["changes"][0]["units"][0]["truth_kind"] == "desired"
    assert "unavailable" not in data["explanation"]  # 解释投影未降级


def test_impact_scope_interface_without_device_no_fabricated_identity(client, db):
    """scope 有接口但缺 device_id：接口节点保留（id=null），不编造全局接口身份/关系。"""
    scope_no_device = {k: v for k, v in SCOPE.items() if k != "device_id"}
    op = _seed_op(db, scope=scope_no_device)
    _seed_attempt(db, op, kind="execute", status="succeeded", units=[("x", "succeeded", {})])
    data = _detail(client, op.id)
    impact = _impact(data)
    iface_node = next(n for n in impact["nodes"] if n["kind"] == "interface")
    assert iface_node["id"] is None  # 不编造全局接口身份
    assert iface_node["if_index"] == 1
    assert iface_node["interface_name"] == "GigabitEthernet1/0/1"
    # 关系不引用无身份的接口
    for r in impact["relations"]:
        assert r["to_kind"] != "interface" and r["from_kind"] != "interface"


def test_impact_multiple_attempts_units_order_and_dedup(client, db):
    op = _seed_op(db, scope=SCOPE)
    for kind, unit_names in (("execute", ["a", "b"]), ("validate", ["c", "d"])):
        _seed_attempt(db, op, kind=kind, status="succeeded", units=[(n, "succeeded", {}) for n in unit_names])
    data = _detail(client, op.id)
    impact = _impact(data)
    assert [c["attempt_id"] for c in impact["changes"]] == sorted(c["attempt_id"] for c in impact["changes"])
    for c in impact["changes"]:
        idx = [u["unit_index"] for u in c["units"]]
        assert idx == sorted(idx)
    node_keys = [(n["kind"], n["id"]) for n in impact["nodes"]]
    assert len(node_keys) == len(set(node_keys))


def test_impact_sanitized(client, db):
    op = _seed_op(db, scope=SCOPE)
    _seed_attempt(db, op, kind="execute", status="succeeded", units=[("x", "succeeded", {"note": "RAW-EVIDENCE-9"})])
    data = _detail(client, op.id)
    raw = json.dumps(_impact(data), default=str)
    for forbidden in ("REQ-SECRET-1", "RAW-EVIDENCE-9", "request_payload_json", "idempotency_key", "fingerprint", "owner", "evidence_json", "scope_json"):
        assert forbidden not in raw, forbidden
    # 旧字段保留且未被改写
    assert data["operation_id"] == op.id
    assert data["operation_type"] == "terminal_access"
    assert data["scope"] == SCOPE
    assert data["attempts"][0]["units"][0]["evidence"] == {"note": "RAW-EVIDENCE-9"}
    # 顶层无 impact 影子字段
    assert "impact" not in set(data.keys())


def test_impact_ambiguous_consistent_with_explanation(client, db):
    """非 unknown + stale_takeover attempt：impact 与 operation explanation 的 ambiguous_claims 完全一致。"""
    op = _seed_op(db, status="validating", scope=SCOPE)
    _seed_attempt(
        db, op, kind="validate", status="unknown",
        evidence={"stale_takeover": True, "dimensions": {"evidence": {"status": "insufficient"}}},
        units=[("validate-l2", "unknown", {})],
    )
    data = _detail(client, op.id)
    explanation_ambiguous = data["explanation"]["safety_boundary"]["ambiguous_claims"]
    assert explanation_ambiguous is True  # stale_takeover/insufficient 证据 → 歧义
    assert _impact(data)["safety"]["ambiguous_claims"] == explanation_ambiguous


def test_impact_fallback_safety_reuses_explain_operation():
    """纯函数未传 explanation 时：用真实 attempt facts 调用既有 explain_operation，不另写简化判定。"""
    op = {"operation_type": "terminal_access", "status": "validating", "expected_host_ip": "10.1.0.2", "vpc_id": 10, "device_id": 20}
    facts = [{"kind": "validate", "status": "unknown", "evidence": {"stale_takeover": True}}]
    impact = build_operation_impact(op, SCOPE, attempts=[], explanation=None, attempt_facts=facts)
    expected = explain_operation(op, SCOPE, facts)
    assert impact["safety"]["ambiguous_claims"] == expected["safety_boundary"]["ambiguous_claims"] is True
    assert impact["safety"]["target_only"] == expected["safety_boundary"]["target_only"] is True


def test_impact_builder_exception_detail_200_and_unavailable(client, db):
    """builder 抛异常：detail 仍 200、旧 explanation 字段保留、explanation.impact 明确 unavailable。"""
    op = _seed_op(db, scope=SCOPE)
    _seed_attempt(db, op, kind="execute", status="succeeded", units=[("x", "succeeded", {})])
    import app.routers.sdn_access as sdn_access

    with patch.object(sdn_access, "build_operation_impact", side_effect=RuntimeError("boom")):
        resp = client.get(f"/api/sdn/operations/{op.id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "impact" in data["explanation"]
    assert data["explanation"]["impact"] == {"unavailable": True, "reason": "impact_unavailable"}
    # 旧 explanation 字段保留（未因 impact 失败而降级/丢失）
    assert "intent" in data["explanation"]
    assert "safety_boundary" in data["explanation"]
    assert data["operation_id"] == op.id


def test_impact_unknown_status_ambiguous(client, db):
    op = _seed_op(db, status="unknown", scope=SCOPE)
    _seed_attempt(db, op, kind="execute", status="unknown", units=[("x", "unknown", {})])
    data = _detail(client, op.id)
    impact = _impact(data)
    assert impact["safety"]["ambiguous_claims"] is True
    assert impact["changes"][0]["units"][0]["truth_kind"] == "pending"


def test_impact_zero_io_and_zero_writes(client, db):
    op = _seed_op(db, scope=SCOPE)
    _seed_attempt(db, op, kind="execute", status="succeeded", units=[("x", "succeeded", {})])
    before_op = db.query(SdnOperation).count()
    before_at = db.query(SdnAttempt).count()
    from app.services.sdn_validation_collector import SdnValidationCollector

    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        data = _detail(client, op.id)
    assert data["operation_id"] == op.id
    assert db.query(SdnOperation).count() == before_op
    assert db.query(SdnAttempt).count() == before_at


# ── API 端到端：真实 terminal_access 创建路径 ──


def _seed_ready(client, db):
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
    db.flush()
    dep = SdnDeployment(vpc_id=vpc.id, device_id=device.id, action="create", unit="vpc-create-all",
                        planned_config="[]", status="success")
    db.add(dep)
    db.commit()
    dep.config_completed_at = dep.created_at
    db.commit()
    from app.models import SdnValidationSnapshot

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


def test_api_operation_detail_impact_end_to_end(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    body = {**_preview_body(device), "idempotency_key": "key-s2-008-r1-0001", "plan_id": plan_id, "auto_apply": False}
    op = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body).json()["data"]

    data = _detail(client, op["operation_id"])
    impact = _impact(data)
    node_keys = [(n["kind"], n["id"]) for n in impact["nodes"]]
    assert ("vpc", vpc.id) in node_keys
    assert ("device", device.id) in node_keys
    assert ("interface", f"device:{device.id}:if_index:1") in node_keys
    assert ("host", "10.1.0.2") in node_keys
    rels = [(r["from_kind"], r["relation"], r["to_kind"]) for r in impact["relations"]]
    assert ("vpc", "targets", "device") in rels
    assert ("device", "exposes", "interface") in rels
    assert ("interface", "expects", "host") in rels
    assert impact["safety"]["target_only"] is True
    assert impact["safety"]["shared_vpc_gateway_not_target"] is True
    assert impact["changes"]
    unit0 = impact["changes"][0]["units"][0]
    api_unit0 = data["attempts"][0]["units"][0]["explanation"]
    assert unit0["truth_kind"] == api_unit0["truth_kind"]
    assert unit0["source"] == api_unit0["source"]
