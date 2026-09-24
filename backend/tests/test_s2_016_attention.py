"""S2-016 契约测试：VPC 可行动关注队列（attention，只读 additive 顶层投影）。

覆盖：
- 保守矩阵全 8 条（scope_uncertain / confirmed_drift / evidence_missing_or_stale /
  coverage_gap / coverage_deferred / exception_expired / exception_invalid / aligned 无 item）；
- active exception 不消灭漂移事实（仍 blocking + 携带 exception）；
- expired exception 与 blocking drift 可共存、key 不冲突；
- 排序固定（blocking→review→deferred，再 device_id/category）与稳定 key；
- 空态 / 非 EVPN 不进入；
- 脱敏（无凭据/原始配置/CLI output/error/snapshot_data）；
- 纯函数畸形输入稳定降级（绝不 500）；
- 零 DB 写、零设备 I/O、零隐式采集；
- 既有 scope/leaves/excluded/aggregate 完全不变（additive）。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Device, SdnDeployment, SdnScopeException, SdnValidationSnapshot, SdnVpc
from app.services.sdn_attention import (
    CATEGORY_CONFIRMED_DRIFT,
    CATEGORY_COVERAGE_DEFERRED,
    CATEGORY_COVERAGE_GAP,
    CATEGORY_EVIDENCE_MISSING_OR_STALE,
    CATEGORY_EXCEPTION_EXPIRED,
    CATEGORY_EXCEPTION_INVALID,
    CATEGORY_SCOPE_UNCERTAIN,
    SEVERITY_BLOCKING,
    SEVERITY_DEFERRED,
    SEVERITY_REVIEW,
    attention_projection,
    build_attention_items,
)
from app.services.sdn_state_projection import (
    SCOPE_AMBIGUOUS,
    SCOPE_NOT_TARGETED,
    SCOPE_TARGETED,
    SCOPE_WITHDRAWN,
)

NOW = datetime.utcnow()


def _create_tenant_via_api(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc_via_api(client, tenant_id, name="vpc-1"):
    return client.post("/api/sdn/vpcs", json={"name": name, "tenant_id": tenant_id, "cidr": "192.168.2.0/24", "gateway_ip": "192.168.2.254"}).json()["data"]


def _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf"):
    dev = Device(name=name, host=ip, port=830, username="t", password_encrypted="SECRET-ENC", protected_interfaces="[]", platform="LSTN", sdn_role=sdn_role)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _vpc_version(db, vpc):
    return db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version


def _add_deployment(db, vpc, device, *, action="create", status="success", version=None):
    if version is None:
        version = _vpc_version(db, vpc)
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=device.id, action=action, unit="vpc-create-all",
                         status=status, version=version, planned_config="[]",
                         config_completed_at=datetime.utcnow()))
    db.commit()


def _add_snapshot(db, vpc, device, *, data, minutes_ago=1):
    db.add(SdnValidationSnapshot(vpc_id=vpc["id"], device_id=device.id, snapshot_data=json.dumps(data),
                                 validation_result="active", validation_details="{}",
                                 collection_started_at=NOW - timedelta(minutes=minutes_ago, seconds=30),
                                 collection_completed_at=NOW - timedelta(minutes=minutes_ago)))
    db.commit()


def _vsi_cmd(vpc):
    return f"display l2vpn vsi name {vpc['vsi_name']} verbose"


def _vsi_if_cmd(vpc):
    return f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"


def _aligned_data(vpc, tenant):
    return {"commands": {
        _vsi_cmd(vpc): {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up", "error": None},
        _vsi_if_cmd(vpc): {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {tenant['l3_vni']}", "error": None},
    }}


def _drifted_data(vpc):
    return {"commands": {
        _vsi_cmd(vpc): {"success": True, "output": "The VSI does not exist.", "error": None},
    }}


def _put_exception(client, vpc_id, device_id, body):
    return client.put(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception", json=body)


def _projection(client, vpc_id):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/state-projection")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert "attention" in data  # additive 顶层
    return data


def _attention(data):
    return data["attention"]


def _items_by_key(data):
    return {i["key"]: i for i in _attention(data)["items"]}


def _member(data, device_id):
    return next(m for m in data["scope"]["members"] if m["device_id"] == device_id)


# ── 矩阵：endpoint 全场景 ──


def test_attention_full_matrix(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    amb_leaf = _create_device(db, name="Leaf-A", ip="192.0.2.4")
    drift_leaf = _create_device(db, name="Leaf-D", ip="192.0.2.1")
    stale_leaf = _create_device(db, name="Leaf-S", ip="192.0.2.2")
    aligned_leaf = _create_device(db, name="Leaf-L", ip="192.0.2.6")
    unset_leaf = _create_device(db, name="Leaf-U", ip="192.0.2.3")
    withdrawn_leaf = _create_device(db, name="Leaf-W", ip="192.0.2.5")
    deferred_leaf = _create_device(db, name="Leaf-F", ip="192.0.2.7")
    access_dev = _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")

    # ambiguous：仅快照（snapshot 不能单独证明 targeted）
    _add_snapshot(db, vpc, amb_leaf, data={"commands": {}})
    # targeted + drifted
    _add_deployment(db, vpc, drift_leaf)
    _add_snapshot(db, vpc, drift_leaf, data=_drifted_data(vpc))
    # targeted + stale（12min > TTL 600s）
    _add_deployment(db, vpc, stale_leaf)
    _add_snapshot(db, vpc, stale_leaf, data=_aligned_data(vpc, tenant), minutes_ago=12)
    # targeted + aligned → 无 item
    _add_deployment(db, vpc, aligned_leaf)
    _add_snapshot(db, vpc, aligned_leaf, data=_aligned_data(vpc, tenant))
    # not_targeted 无例外 → coverage_gap
    # withdrawn 无例外 → coverage_gap
    _add_deployment(db, vpc, withdrawn_leaf)
    _add_deployment(db, vpc, withdrawn_leaf, action="delete")
    # not_targeted + active exception → coverage_deferred
    _put_exception(client, vpc["id"], deferred_leaf.id, {"exception_type": "maintenance_pause", "reason": "维护中"})

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    att = _attention(data)

    # 非 EVPN 不进 scope 也不进 attention
    assert access_dev.id not in [m["device_id"] for m in data["scope"]["members"]]
    assert not any(i["device_id"] == access_dev.id for i in att["items"])

    def _item(device_id, category):
        key = f"{vpc['id']}:{device_id}:{category}"
        assert key in items, f"missing {key}; have {sorted(items)}"
        return items[key]

    # 规则 1
    i = _item(amb_leaf.id, CATEGORY_SCOPE_UNCERTAIN)
    assert i["severity"] == SEVERITY_BLOCKING and i["recommended_action"] == "review_records"
    assert i["source_refs"][0]["classification"] == SCOPE_AMBIGUOUS
    assert i["exception"] is None
    # 规则 2
    i = _item(drift_leaf.id, CATEGORY_CONFIRMED_DRIFT)
    assert i["severity"] == SEVERITY_BLOCKING and i["recommended_action"] == "inspect_differences"
    assert i["source_refs"][0]["aggregate"] == "drifted"
    # 规则 3（stale）
    i = _item(stale_leaf.id, CATEGORY_EVIDENCE_MISSING_OR_STALE)
    assert i["severity"] == SEVERITY_REVIEW and i["recommended_action"] == "refresh_evidence"
    assert i["source_refs"][0]["snapshot"]["stale"] is True
    # 规则 8：targeted + aligned → 无 item
    assert f"{vpc['id']}:{aligned_leaf.id}:{CATEGORY_CONFIRMED_DRIFT}" not in items
    assert not any(i["device_id"] == aligned_leaf.id for i in att["items"])
    # 规则 4
    for leaf in (unset_leaf, withdrawn_leaf):
        i = _item(leaf.id, CATEGORY_COVERAGE_GAP)
        assert i["severity"] == SEVERITY_REVIEW and i["recommended_action"] == "review_coverage"
        assert i["source_refs"][0]["classification"] in (SCOPE_NOT_TARGETED, SCOPE_WITHDRAWN)
    # 规则 5
    i = _item(deferred_leaf.id, CATEGORY_COVERAGE_DEFERRED)
    assert i["severity"] == SEVERITY_DEFERRED and i["recommended_action"] == "review_exception"
    assert i["exception"]["state"] == "active"
    assert _member(data, deferred_leaf.id)["classification"] == SCOPE_NOT_TARGETED  # 保留原分类

    # summary 与排序
    assert att["summary"] == {
        "total": 6, "blocking": 2, "review": 3, "deferred": 1,
    }
    sev_order = [SEVERITY_BLOCKING, SEVERITY_REVIEW, SEVERITY_DEFERRED]
    order = {s: k for k, s in enumerate(sev_order)}
    keys = att["items"]
    assert [order[i["severity"]] for i in keys] == sorted(order[i["severity"]] for i in keys)
    # 同级再按 device_id 升序
    for a, b in zip(keys, keys[1:]):
        assert (order[a["severity"]], a["device_id"], a["category"]) <= (order[b["severity"]], b["device_id"], b["category"])


def test_attention_targeted_unknown_no_snapshot_review(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)  # targeted 但无快照 → aggregate unknown

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    i = items[f"{vpc['id']}:{leaf.id}:{CATEGORY_EVIDENCE_MISSING_OR_STALE}"]
    assert i["severity"] == SEVERITY_REVIEW
    assert i["recommended_action"] == "refresh_evidence"


def test_attention_drift_with_active_exception_still_blocking(client, db):
    """active exception 不消灭漂移事实：仍 blocking confirmed_drift 并携带 exception。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "有意排除"})

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    i = items[f"{vpc['id']}:{leaf.id}:{CATEGORY_CONFIRMED_DRIFT}"]
    assert i["severity"] == SEVERITY_BLOCKING  # 不得降成无问题
    assert i["exception"]["state"] == "active"
    # 同时没有 coverage 类降级 item（active exception 不产生 coverage_deferred——targeted 不走规则 4/5）
    assert len([x for x in data["attention"]["items"] if x["device_id"] == leaf.id]) == 1


def test_attention_expired_exception_coexists_with_blocking_drift(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": (NOW + timedelta(days=1)).isoformat()})
    row = db.query(SdnScopeException).filter(SdnScopeException.vpc_id == vpc["id"], SdnScopeException.device_id == leaf.id).first()
    row.expires_at = NOW - timedelta(hours=1)
    db.commit()

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    drift = items[f"{vpc['id']}:{leaf.id}:{CATEGORY_CONFIRMED_DRIFT}"]
    expired = items[f"{vpc['id']}:{leaf.id}:{CATEGORY_EXCEPTION_EXPIRED}"]
    assert drift["severity"] == SEVERITY_BLOCKING
    assert expired["severity"] == SEVERITY_REVIEW
    assert expired["recommended_action"] == "refresh_evidence"
    assert expired["exception"]["state"] == "expired"
    assert drift["key"] != expired["key"]  # key 不冲突


def test_attention_expired_exception_on_aligned_leaf(client, db):
    """targeted+aligned 有 expired exception → 仅 exception_expired（规则 8 例外）。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_aligned_data(vpc, tenant))
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": (NOW + timedelta(days=1)).isoformat()})
    row = db.query(SdnScopeException).filter(SdnScopeException.vpc_id == vpc["id"], SdnScopeException.device_id == leaf.id).first()
    row.expires_at = NOW - timedelta(hours=1)
    db.commit()

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    assert set(items) == {f"{vpc['id']}:{leaf.id}:{CATEGORY_EXCEPTION_EXPIRED}"}


def test_attention_not_targeted_with_expired_exception(client, db):
    """not_targeted + expired exception：coverage_gap 与 exception_expired 均保留（key 不冲突）。"""
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "m", "expires_at": (NOW + timedelta(days=1)).isoformat()})
    row = db.query(SdnScopeException).filter(SdnScopeException.vpc_id == vpc["id"], SdnScopeException.device_id == leaf.id).first()
    row.expires_at = NOW - timedelta(hours=1)
    db.commit()

    data = _projection(client, vpc["id"])
    items = _items_by_key(data)
    assert items[f"{vpc['id']}:{leaf.id}:{CATEGORY_COVERAGE_GAP}"]["severity"] == SEVERITY_REVIEW
    assert items[f"{vpc['id']}:{leaf.id}:{CATEGORY_EXCEPTION_EXPIRED}"]["severity"] == SEVERITY_REVIEW


# ── 空态 / 非 EVPN / 稳定 key / 排序 ──


def test_attention_empty_no_devices(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    data = _projection(client, vpc["id"])
    assert _attention(data) == {"summary": {"total": 0, "blocking": 0, "review": 0, "deferred": 0}, "items": []}


def test_attention_non_evpn_only(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _create_device(db, name="Access-01", ip="192.0.2.20", sdn_role="access")
    data = _projection(client, vpc["id"])
    assert _attention(data)["summary"]["total"] == 0  # 非 EVPN 不进入


def test_attention_stable_keys_and_sorting(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    a = _create_device(db, name="Leaf-A", ip="192.0.2.1")
    b = _create_device(db, name="Leaf-B", ip="192.0.2.2")
    _add_deployment(db, vpc, a)
    _add_snapshot(db, vpc, a, data=_drifted_data(vpc))
    _add_deployment(db, vpc, b)
    _add_snapshot(db, vpc, b, data=_aligned_data(vpc, tenant), minutes_ago=12)  # stale → review

    first = _projection(client, vpc["id"])
    second = _projection(client, vpc["id"])
    assert [i["key"] for i in first["attention"]["items"]] == [i["key"] for i in second["attention"]["items"]]
    items = first["attention"]["items"]
    assert [i["device_id"] for i in items] == [a.id, b.id]  # blocking(drift) 在前，review(stale) 在后
    assert items[0]["category"] == CATEGORY_CONFIRMED_DRIFT
    assert items[1]["category"] == CATEGORY_EVIDENCE_MISSING_OR_STALE


# ── 脱敏 / 既有投影不变 / 零写入零 I/O ──


def test_attention_sanitized(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "排除原因"})

    data = _projection(client, vpc["id"])
    raw = json.dumps(data["attention"], default=str)
    for forbidden in ("SECRET-ENC", "password_encrypted", "protected_interfaces", "planned_config",
                      "RAW-", "snapshot_data", "The VSI does not exist", "error", "username"):
        assert forbidden not in raw, forbidden
    # 白名单键
    for i in data["attention"]["items"]:
        assert set(i.keys()) == {"key", "vpc_id", "device_id", "name", "host", "severity",
                                 "category", "reason_code", "recommended_action", "source_refs", "exception"}


def test_attention_existing_projection_unchanged(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    _put_exception(client, vpc["id"], leaf.id, {"exception_type": "intentional_exclusion", "reason": "r"})

    data = _projection(client, vpc["id"])
    assert set(data.keys()) == {"vpc", "snapshot_ttl_seconds", "leaves", "excluded", "aggregate", "scope", "attention"}
    # 既有语义完全不变（与 S2-012/014 断言一致）
    assert data["leaves"][0]["aggregate"] == "drifted"
    assert data["aggregate"] == "drifted"
    assert _member(data, leaf.id)["classification"] == SCOPE_TARGETED
    assert _member(data, leaf.id)["exception"]["state"] == "active"
    assert data["scope"]["summary"]["active_exception"] == 1
    assert data["excluded"] == []
    assert "attention" in data  # additive


def test_attention_zero_io_zero_writes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_deployment(db, vpc, leaf)
    from app.services.sdn_validation_collector import SdnValidationCollector
    from app.models import SdnScopeException

    before = {
        "vpcs": db.query(SdnVpc).count(),
        "deployments": db.query(SdnDeployment).count(),
        "snapshots": db.query(SdnValidationSnapshot).count(),
        "exceptions": db.query(SdnScopeException).count(),
    }
    with patch.object(SdnValidationCollector, "sync", side_effect=AssertionError("must not trigger sync")):
        data = _projection(client, vpc["id"])
        assert _attention(data)["summary"]["total"] >= 1
    after = {
        "vpcs": db.query(SdnVpc).count(),
        "deployments": db.query(SdnDeployment).count(),
        "snapshots": db.query(SdnValidationSnapshot).count(),
        "exceptions": db.query(SdnScopeException).count(),
    }
    assert before == after  # 零 DB 写


# ── 纯函数畸形输入稳定降级 ──


def _fake_member(device_id=1, classification=SCOPE_NOT_TARGETED, exception=None, **kw):
    m = {"device_id": device_id, "name": "Leaf-X", "host": "192.0.2.9",
         "classification": classification, "reason_code": "no_records"}
    m.update(kw)
    if exception is not None:
        m["exception"] = exception
    return m


def test_attention_pure_function_malformed_degrade():
    # 垃圾成员/分类/聚合/例外 state → 稳定输出，不 500
    items = build_attention_items(vpc_id=7, members=[
        "not-a-dict",
        {"name": "no-id"},                          # 缺 device_id → 跳过
        _fake_member(device_id=2, classification="weird"),  # 未知分类 → 无分类 item
        _fake_member(device_id=3, classification=SCOPE_TARGETED, exception={"state": "weird"}),  # 坏 exception → invalid
    ], leaves_by_device={3: {"device_id": 3, "aggregate": "garbage"}})
    by_key = {i["key"]: i for i in items}
    assert f"7:3:{CATEGORY_EXCEPTION_INVALID}" in by_key
    assert by_key[f"7:3:{CATEGORY_EXCEPTION_INVALID}"]["severity"] == SEVERITY_BLOCKING
    # targeted + 坏 aggregate → 保守 review evidence_missing_or_stale
    items2 = build_attention_items(vpc_id=7, members=[
        _fake_member(device_id=4, classification=SCOPE_TARGETED),
    ], leaves_by_device={4: {"device_id": 4, "aggregate": "garbage"}})
    assert items2[0]["category"] == CATEGORY_EVIDENCE_MISSING_OR_STALE
    assert items2[0]["severity"] == SEVERITY_REVIEW
    # leaves_by_device 非 dict / members 非 list → 空
    assert build_attention_items(vpc_id=7, members=None) == []
    assert build_attention_items(vpc_id=7, members=[], leaves_by_device="nope") == []
    # exception=None 的成员不产生例外 item
    assert not any(i["device_id"] == 2 and i["category"].startswith("exception_") for i in items)


def test_attention_pure_function_aligned_no_item():
    items = build_attention_items(vpc_id=7, members=[
        _fake_member(device_id=1, classification=SCOPE_TARGETED, reason_code="base_present"),
    ], leaves_by_device={1: {"device_id": 1, "aggregate": "aligned"}})
    assert items == []
    # active exception + aligned → 仍无 item（active 例外本身不产生 attention）
    items = build_attention_items(vpc_id=7, members=[
        _fake_member(device_id=1, classification=SCOPE_TARGETED, reason_code="base_present",
                     exception={"vpc_id": 7, "device_id": 1, "state": "active", "exception_type": "intentional_exclusion"}),
    ], leaves_by_device={1: {"device_id": 1, "aggregate": "aligned"}})
    assert items == []
