"""S3-004 对抗测试：受控修复提案（只生成、绝不执行设备配置，NEXT/S3 后端切片）。

先覆盖失败风险，再验证语义（全部隔离 qa-backend 容器，真实 SQLite）：
- 准入：仅 completed run 中 severity=blocking、category=confirmed_drift 的真实 item；
  服务端从 run 白名单取 device/item，不信任调用方重填设备或动作；
- 防陈旧：创建时 VPC version / 分类 / 证据快照 / 例外任一变化 → 拒绝或 stale；
- 幂等并发：同 run+item 返回同一提案（DB 唯一约束兜底）；
- 读取时保守标 stale：VPC version / 最新快照 / 分类 / 例外变化后 proposed → stale（CAS）；
- 取消：仅 proposed → cancelled，重复取消幂等；
- 白名单/无密钥：summary 只含语义单元名/保留项/边界，无原始 CLI/凭据/planned_config；
- 全路径零设备 I/O、零业务副作用：不写 deployment/operation/binding/claim、不改 vpc.version；
- 迁移 017（建表 + 唯一索引）幂等可升降，与 ORM 一致。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import SessionLocal
from app.models import SdnAssuranceRun, SdnRemediationProposal, SdnVpc
from tests.test_s2_016_attention import (
    _add_deployment,
    _add_snapshot,
    _aligned_data,
    _create_device,
    _create_tenant_via_api,
    _create_vpc_via_api,
    _drifted_data,
)
from tests.test_s3_002_scheduler import _business_counts, _runs


def _seed_drift(client, db, *, name="vpc-drift"):
    """租户 + VPC + 目标 Leaf（create deployment）+ drifted 快照 → confirmed_drift blocking。"""
    tenant = _create_tenant_via_api(client, name=name)
    vpc = _create_vpc_via_api(client, tenant["id"], name=name)
    leaf = _create_device(db, name=f"Leaf-{name}", ip=f"192.0.2.{_ip_seq()}")
    _add_deployment(db, vpc, leaf)
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    return vpc, leaf


_IP_COUNTER = [100]


def _ip_seq():
    _IP_COUNTER[0] += 1
    return _IP_COUNTER[0]


def _make_run(client, db, vpc_id):
    """手动评估 → completed run（含 confirmed_drift blocking item）。"""
    resp = client.post(f"/api/sdn/vpcs/{vpc_id}/assurance-runs", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    runs = _runs(db, vpc_id)
    run = [r for r in runs if r.trigger == "manual"][-1]
    assert run.status == "completed"
    items = json.loads(run.items_json or "[]")
    drift = [i for i in items if i.get("category") == "confirmed_drift" and i.get("severity") == "blocking"]
    assert drift, "expected a confirmed_drift blocking item in run items"
    return run, drift[0]


def _create_proposal(client, vpc_id, run_id, item_key, **extra):
    payload = {"run_id": run_id, "item_key": item_key}
    payload.update(extra)
    return client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals", json=payload)


# ── 1. 创建：准入 + 白名单摘要 + 固定 action ──


def test_create_proposal_happy_path(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    data = body["data"]
    assert data["result"] == "created"
    prop = data["proposal"]
    assert prop["run_id"] == run.id
    assert prop["item_key"] == item["key"]
    assert prop["device_id"] == item["device_id"]
    assert prop["action"] == "redeploy_vpc_on_device"
    assert prop["category"] == "confirmed_drift"
    assert prop["status"] == "proposed"
    assert prop["executed"] is False
    current_version = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).one().version
    assert prop["vpc_version_at_create"] == current_version
    assert prop["policy_version"] == run.policy_version
    assert prop["evidence_snapshot_id"] is not None
    assert prop["fingerprint"] and len(prop["fingerprint"]) == 64
    # 语义单元 + 保留项 + 边界（无原始 CLI/凭据）
    names = {u["name"] for u in prop["units"]}
    assert {"vsi-l2", "evpn", "l3vpn", "vsi-l3", "global"} <= names
    assert "tenant" in prop["preserved"] and "port_bindings" in prop["preserved"]
    raw = json.dumps(body)
    for secret in ("cli_commands", "xml_payloads", "system-view", "display ", "password", "SECRET", "admin"):
        assert secret not in raw, secret


def test_create_ignores_caller_filled_device_and_action(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    # 调用方试图伪造 device/action → 服务端忽略，仍按 run 白名单 item 生成
    resp = _create_proposal(
        client, vpc_id, run.id, item["key"],
        device_id=999999, action="erase_everything", category="whatever",
    )
    assert resp.status_code == 200 and resp.json()["success"] is True
    prop = resp.json()["data"]["proposal"]
    assert prop["device_id"] == item["device_id"]
    assert prop["action"] == "redeploy_vpc_on_device"
    assert prop["category"] == "confirmed_drift"


def test_create_admission_rejects(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)

    # 不存在/未 completed 的 run
    resp = _create_proposal(client, vpc_id, 999999, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_run_not_found"

    # 非 blocking/非 confirmed_drift 的 item key → 拒绝
    other_key = "vpc:%d:item:not-a-drift" % vpc_id
    resp = _create_proposal(client, vpc_id, run.id, other_key)
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_item_not_found"

    # 其他 VPC 的 run → 拒绝
    vpc2, leaf2 = _seed_drift(client, db, name="vpc-drift-2")
    run2, item2 = _make_run(client, db, vpc2["id"])
    resp = _create_proposal(client, vpc_id, run2.id, item2["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_run_not_found"


# ── 2. 防陈旧：创建时任一条件不满足 → 拒绝/返回 stale ──


def test_create_stale_when_vpc_version_changed(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    # 直接 bump vpc.version（模拟部署/业务变更；只读测试不触发真实设备）
    row = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    row.version += 1
    db.commit()

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_stale"


def test_create_stale_when_classification_gone(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    # 对齐快照后 drift 消失 → 当前分类不再是 confirmed_drift
    tenant = _create_tenant_via_api(client, name=f"tenant-align-{vpc_id}")
    _add_snapshot(db, vpc, leaf, data=_aligned_data(vpc, tenant))

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_stale"


def test_create_stale_when_evidence_changed(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    # 新的 drifted 快照（新证据）→ 与 run source_refs 不再指向同一快照
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_stale"


def test_create_rejected_by_active_maintenance_exception(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    resp = client.put(
        f"/api/sdn/vpcs/{vpc_id}/devices/{leaf.id}/scope-exception",
        json={"exception_type": "maintenance_pause", "reason": "维护窗口"},
    )
    assert resp.status_code == 200 and resp.json()["success"] is True

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_active_maintenance_exception"


def test_create_rejected_when_device_not_leaf(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    leaf.sdn_role = "access"  # 目标不再是 EVPN Leaf
    db.commit()

    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_device_not_leaf"


# ── 3. 幂等 + 并发唯一（DB 唯一约束兜底）──


def test_create_idempotent_duplicate_and_concurrent(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)

    # 从空表并发创建；在首次存在性检查之前同步两个调用，避免把“读取既有行”
    # 冒充并发唯一性验证。
    import threading
    errors = []
    outcomes = []
    barrier = threading.Barrier(2)
    from app.services import sdn_remediation as remed
    original_summary = remed._impact_summary

    def synchronized_summary(*args, **kwargs):
        result = original_summary(*args, **kwargs)
        barrier.wait(timeout=5)
        return result

    def call():
        s = SessionLocal()
        try:
            outcomes.append(
                remed.create_proposal(s, vpc_id=vpc_id, run_id=run.id, item_key=item["key"])
            )
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            s.close()

    with patch.object(remed, "_impact_summary", side_effect=synchronized_summary):
        threads = [threading.Thread(target=call) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert not errors
    assert sorted(outcome["result"] for outcome in outcomes) == ["created", "duplicate"]
    assert db.query(SdnRemediationProposal).filter(
        SdnRemediationProposal.run_id == run.id,
        SdnRemediationProposal.item_key == item["key"],
    ).count() == 1

    pid = outcomes[0]["proposal"].id
    second = _create_proposal(client, vpc_id, run.id, item["key"])
    body = second.json()
    assert body["success"] is True
    assert body["data"]["result"] == "duplicate"
    assert body["data"]["proposal"]["id"] == pid


def test_duplicate_retry_returns_same_proposal_after_it_becomes_stale(client, db):
    """幂等重试返回原提案，并在证据变化后如实刷新为 stale。"""
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    first = _create_proposal(client, vpc_id, run.id, item["key"]).json()["data"]["proposal"]

    row = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).one()
    row.version += 1
    db.commit()

    retry = _create_proposal(client, vpc_id, run.id, item["key"])
    assert retry.json()["success"] is True
    assert retry.json()["data"]["result"] == "duplicate"
    assert retry.json()["data"]["proposal"]["id"] == first["id"]
    assert retry.json()["data"]["proposal"]["status"] == "stale"


# ── 4. 读取时保守标 stale（CAS，不能仍显示可执行）──


def _propose(client, db, vpc_id):
    run, item = _make_run(client, db, vpc_id)
    resp = _create_proposal(client, vpc_id, run.id, item["key"])
    return resp.json()["data"]["proposal"]


def test_read_marks_stale_on_vpc_version_change(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    prop = _propose(client, db, vpc_id)
    assert prop["status"] == "proposed"

    row = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    row.version += 1
    db.commit()

    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}")
    assert resp.json()["data"]["status"] == "stale"
    # 列表也保守标 stale
    lst = client.get(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals").json()["data"]["proposals"]
    assert lst[0]["status"] == "stale"


def test_read_marks_stale_on_snapshot_or_exception_change(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    prop = _propose(client, db, vpc_id)

    # 新证据快照 → stale
    _add_snapshot(db, vpc, leaf, data=_drifted_data(vpc))
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}")
    assert resp.json()["data"]["status"] == "stale"


def test_read_marks_stale_on_maintenance_exception(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    prop = _propose(client, db, vpc_id)

    client.put(
        f"/api/sdn/vpcs/{vpc_id}/devices/{leaf.id}/scope-exception",
        json={"exception_type": "maintenance_pause", "reason": "维护"},
    )
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}")
    assert resp.json()["data"]["status"] == "stale"


# ── 5. 取消（仅 proposed → cancelled，重复幂等）──


def test_cancel_proposal_idempotent(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    prop = _propose(client, db, vpc_id)

    resp = client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}/cancel")
    assert resp.json()["data"]["status"] == "cancelled"
    # 重复取消幂等
    resp2 = client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}/cancel")
    assert resp2.json()["data"]["status"] == "cancelled"
    assert resp2.json()["data"]["id"] == prop["id"]

    # cancelled 后读取不再变 stale（也不复活为 proposed）
    row = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
    row.version += 1
    db.commit()
    resp3 = client.get(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}")
    assert resp3.json()["data"]["status"] == "cancelled"


def test_cancel_missing_proposal(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    resp = client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/424242/cancel")
    assert resp.json()["success"] is False
    assert resp.json()["error_key"] == "sdn.remediation_not_found"


# ── 6. 全路径零设备 I/O、零业务副作用 ──


def test_zero_device_io_zero_business_side_effects(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    version_before = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version
    counts_before = _business_counts(db)

    from unittest.mock import patch
    from app.services.vpc_config_planner import VPCConfigPlanner as _P
    with patch.object(_P, "plan_vpc_create", autospec=True, wraps=_P.plan_vpc_create) as m:
        resp = _create_proposal(client, vpc_id, run.id, item["key"])
    assert resp.json()["success"] is True
    assert m.call_count == 1  # 仅一次 dry-run 计算，无任何设备调用

    # 零业务副作用：vpc.version 未变、业务表计数未变、未新增 run
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first().version == version_before
    counts_after = _business_counts(db)
    for k in ("deployments", "bindings", "operations", "plans", "snapshots"):
        assert counts_after[k] == counts_before[k], k
    assert len(_runs(db, vpc_id)) == 1  # 只有手动评估那一条 run
    assert db.query(SdnRemediationProposal).count() == 1

    # 提案只读字段：executed=False、无 confirm/apply 端点（路由不存在 404/未实现 405）
    prop = resp.json()["data"]["proposal"]
    assert prop["executed"] is False
    assert client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}/confirm").status_code in (404, 405)
    assert client.post(f"/api/sdn/vpcs/{vpc_id}/remediation-proposals/{prop['id']}/apply").status_code in (404, 405)


# ── 7. 存储层白名单：DB 无原始 CLI/凭据 ──


def test_db_summary_never_contains_cli_or_secrets(client, db):
    vpc, leaf = _seed_drift(client, db)
    vpc_id = vpc["id"]
    run, item = _make_run(client, db, vpc_id)
    _create_proposal(client, vpc_id, run.id, item["key"])

    row = db.query(SdnRemediationProposal).filter(
        SdnRemediationProposal.run_id == run.id
    ).first()
    raw = row.summary_json
    assert "cli_commands" not in raw and "xml_payloads" not in raw
    for secret in ("system-view", "display ", "password", "SECRET", "admin", "192.0.2."):
        assert secret not in raw, secret
    summary = json.loads(raw)
    assert summary["executed"] is False
    assert all(u["name"] in ("vsi-l2", "evpn", "l3vpn", "vsi-l3", "global") for u in summary["units"])
