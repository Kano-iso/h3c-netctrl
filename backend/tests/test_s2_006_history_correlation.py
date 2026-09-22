"""S2-006 契约测试：历史快照 × 操作/尝试关联（只读，脱敏，纯证据归属不宣称因果）。

覆盖：
- linked：op/attempt 存在、与快照引用及当前时间线（vpc_id/device_id）一致 → 白名单摘要；
- unlinked：快照零引用；
- missing：operation/attempt 引用 dangling；
- mismatch：attempt 属于另一 operation、operation 属于另一 VPC / 设备；
- 响应脱敏：绝不携带 request_payload_json/scope_json/idempotency_key/fingerprint/owner/evidence_json/凭据；
- 端点零设备 I/O、零写入、零隐式采集。
"""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnAttempt, SdnDeployment, SdnOperation, SdnValidationSnapshot

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


def _add_snapshot(db, vpc, device, *, operation_id=None, attempt_id=None):
    snap = SdnValidationSnapshot(
        vpc_id=vpc["id"],
        device_id=device.id,
        snapshot_data=_aligned_snapshot_data(vpc, {"l3_vni": 3000}),
        validation_result="active",
        validation_details="{}",
        operation_id=operation_id,
        attempt_id=attempt_id,
        collection_started_at=NOW - timedelta(seconds=90),
        collection_completed_at=NOW - timedelta(seconds=60),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def _add_operation(db, vpc, device, *, status="succeeded", operation_type="terminal_access"):
    op = SdnOperation(
        idempotency_key=f"ik-{uuid.uuid4().hex}",
        fingerprint=f"fp-{uuid.uuid4().hex}",
        operation_type=operation_type,
        tenant_id=vpc["tenant_id"],
        vpc_id=vpc["id"],
        device_id=device.id,
        expected_host_ip=device.host,
        request_payload_json=json.dumps({"secret": "OP-SECRET-1"}),
        scope_json=json.dumps({"target": "vpc"}),
        status=status,
        created_at=NOW - timedelta(minutes=10),
        updated_at=NOW - timedelta(minutes=5),
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def _add_attempt(db, op, *, kind="validate", status="succeeded", owner="svc"):
    at = SdnAttempt(
        operation_id=op.id,
        deployment_id=None,
        kind=kind,
        status=status,
        owner=owner,
        claimed_at=NOW - timedelta(minutes=9),
        started_at=NOW - timedelta(minutes=8),
        completed_at=NOW - timedelta(minutes=6),
        scope_json=json.dumps({"target": "vpc"}),
        evidence_json=json.dumps({"secret": "AT-SECRET-2"}),
        created_at=NOW - timedelta(minutes=9),
        updated_at=NOW - timedelta(minutes=6),
    )
    db.add(at)
    db.commit()
    db.refresh(at)
    return at


def _history(client, vpc_id, **params):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection/history", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_correlation_linked_full_summaries(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op = _add_operation(db, vpc, leaf)
    at = _add_attempt(db, op)
    _add_snapshot(db, vpc, leaf, operation_id=op.id, attempt_id=at.id)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "linked"
    assert corr["operation_id"] == op.id
    assert corr["attempt_id"] == at.id
    assert corr["operation"] == {
        "id": op.id,
        "operation_type": "terminal_access",
        "status": "succeeded",
        "expected_host_ip": "192.0.2.10",
        "created_at": op.created_at.isoformat(),
        "updated_at": op.updated_at.isoformat(),
    }
    assert corr["attempt"] == {
        "id": at.id,
        "kind": "validate",
        "status": "succeeded",
        "started_at": at.started_at.isoformat(),
        "completed_at": at.completed_at.isoformat(),
    }


def test_correlation_unlinked_when_no_references(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr == {"operation_id": None, "attempt_id": None, "status": "unlinked", "operation": None, "attempt": None}


def test_correlation_dangling_operation_missing(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, operation_id=999999)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "missing"
    assert corr["operation_id"] == 999999
    assert corr["operation"] is None and corr["attempt"] is None


def test_correlation_dangling_attempt_missing(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op = _add_operation(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, operation_id=op.id, attempt_id=999999)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "missing"
    assert corr["attempt_id"] == 999999
    assert corr["operation"] is None and corr["attempt"] is None


def test_correlation_dangling_operation_with_existing_attempt_missing(client, db):
    """dangling operation 引用优先于存在的 attempt：整体 missing，不覆盖成 mismatch。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op = _add_operation(db, vpc, leaf)
    at = _add_attempt(db, op)
    # operation_id 为 dangling（999999），attempt_id 指向存在的 attempt
    _add_snapshot(db, vpc, leaf, operation_id=999999, attempt_id=at.id)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "missing"
    assert corr["operation_id"] == 999999
    assert corr["attempt_id"] == at.id
    # dangling → 不返回任何摘要
    assert corr["operation"] is None and corr["attempt"] is None


def test_correlation_attempt_of_other_operation_mismatch(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op1 = _add_operation(db, vpc, leaf)
    op2 = _add_operation(db, vpc, leaf, status="failed")
    at2 = _add_attempt(db, op2)
    # 快照引用 op1 + op2 的 attempt → attempt 属于另一 operation
    _add_snapshot(db, vpc, leaf, operation_id=op1.id, attempt_id=at2.id)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "mismatch"
    assert corr["operation"] is None and corr["attempt"] is None


def test_correlation_operation_of_other_vpc_mismatch(client, db):
    tenant = _create_tenant_via_api(client)
    vpc1 = _create_vpc_via_api(client, tenant["id"], name="vpc-1")
    vpc2 = _create_vpc_via_api(client, tenant["id"], name="vpc-2")
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc1, leaf)
    # operation 属于 vpc2（同一设备）→ 与当前时间线 vpc1 不一致
    op = _add_operation(db, vpc2, leaf)
    _add_snapshot(db, vpc1, leaf, operation_id=op.id)

    body = _history(client, vpc1["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "mismatch"
    assert corr["operation"] is None


def test_correlation_operation_of_other_device_mismatch(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf1 = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    leaf2 = _create_device(db, name="Leaf-02", ip="192.0.2.11", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf1)
    # operation 属于 leaf2（同一 VPC）→ 与当前时间线 leaf1 不一致
    op = _add_operation(db, vpc, leaf2)
    _add_snapshot(db, vpc, leaf1, operation_id=op.id)

    body = _history(client, vpc["id"])
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert corr["status"] == "mismatch"
    assert corr["operation"] is None


def test_correlation_response_sanitized(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op = _add_operation(db, vpc, leaf)
    at = _add_attempt(db, op)
    _add_snapshot(db, vpc, leaf, operation_id=op.id, attempt_id=at.id)

    body = _history(client, vpc["id"])
    raw = json.dumps(body, default=str)
    # 禁止字段与敏感内容绝不进入响应
    for forbidden in ("request_payload_json", "scope_json", "idempotency_key", "fingerprint", "owner", "evidence_json", "OP-SECRET-1", "AT-SECRET-2"):
        assert forbidden not in raw, forbidden
    corr = body["timelines"][0]["points"][0]["correlation"]
    assert set(corr["operation"].keys()) == {"id", "operation_type", "status", "expected_host_ip", "created_at", "updated_at"}
    assert set(corr["attempt"].keys()) == {"id", "kind", "status", "started_at", "completed_at"}


def test_correlation_zero_io_and_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf")
    _add_create_deployment(db, vpc, leaf)
    op = _add_operation(db, vpc, leaf)
    at = _add_attempt(db, op)
    _add_snapshot(db, vpc, leaf, operation_id=op.id, attempt_id=at.id)

    before_snap = db.query(SdnValidationSnapshot).count()
    before_op = db.query(SdnOperation).count()
    before_at = db.query(SdnAttempt).count()
    from app.services.sdn_validation_collector import SdnValidationCollector

    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/state-projection/history")
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    # 零写入、零隐式采集
    assert db.query(SdnValidationSnapshot).count() == before_snap
    assert db.query(SdnOperation).count() == before_op
    assert db.query(SdnAttempt).count() == before_at
