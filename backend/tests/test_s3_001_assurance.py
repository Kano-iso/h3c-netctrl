"""S3-001 契约测试：VPC 受限保障（策略 + 只读手动评估，NEXT/S3 后端切片）。

先覆盖失败风险，再验证语义：
- GET 策略缺失 → 明确默认值且零写库（不产生策略行）；VPC 不存在 → 404 语义；
- PUT 校验：cadence 白名单 / response_mode 固定 observe_only / enabled 与 version 类型 /
  乐观并发版本冲突（缺失=0 创建 v1，之后必须匹配当前版本，冲突即拒绝且不写库）；
- POST manual run：持久化 run + policy_version/policy_enabled 快照 + 白名单 items/facts；
  policy disabled 时手动评估仍允许（policy_enabled=false 明确记录）；trigger 仅 manual；
- 零设备 I/O、零业务写副作用（不创建 deployment/binding/operation/snapshot/claim、
  不 bump vpc.version）；
- 四种 overall：healthy / attention(coverage_gap) / blocked(confirmed_drift) /
  insufficient_evidence(无 eligible Leaf)；
- 例外边界：active maintenance exception 把 coverage gap 保持 deferred（不升级
  blocking），但 confirmed_drift blocking 不被吞掉（携带 exception）；
- 坏历史稳定降级：畸形快照不 500，run 仍完成且 overall 为白名单值；
- 并发两次 manual run 各自完整、互不覆盖（两条独立 run）；
- 分页/详情：limit 与 before 游标稳定降序、run 不属于该 VPC → 404 语义。
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.models import (
    Device,
    SdnAssurancePolicy,
    SdnAssuranceRun,
    SdnDeployment,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnTenant,
    SdnValidationSnapshot,
    SdnVpc,
)
from app.routers import sdn_assurance as assurance_mod
from app.services.sdn_assurance import evaluate_assurance

NOW = datetime.utcnow()


# ── seed helpers（镜像 S2-014 模式） ──


def _create_tenant_via_api(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc_via_api(client, tenant_id, name="vpc-1"):
    return client.post("/api/sdn/vpcs", json={"name": name, "tenant_id": tenant_id, "cidr": "192.168.2.0/24", "gateway_ip": "192.168.2.254"}).json()["data"]


def _create_device(db, name="Leaf-01", ip="192.0.2.10", sdn_role="evpn_leaf"):
    dev = Device(name=name, host=ip, port=830, username="admin", password_encrypted="SECRET-ENC", protected_interfaces="[]", platform="LSTN", sdn_role=sdn_role)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _add_create_deployment(db, vpc, device):
    version = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version
    db.add(SdnDeployment(vpc_id=vpc["id"], device_id=device.id, action="create", unit="vpc-create-all",
                         status="success", version=version, planned_config='[{"secret": "RAW-PLAN-1"}]',
                         config_completed_at=NOW))
    db.commit()


def _tenant_l3_vni(db, tenant_id):
    return db.query(SdnTenant).filter(SdnTenant.id == tenant_id).first().l3_vni


def _aligned_snapshot(db, vpc, device, tenant_id):
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    vsi_if_cmd = f"display current-configuration interface Vsi-interface{vpc['vsi_interface']}"
    l3_vni = _tenant_l3_vni(db, tenant_id)
    commands = {
        "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: State: Established", "error": None},
        vsi_cmd: {"success": True, "output": f"VSI Name: {vpc['vsi_name']}\nVSI State               : Up", "error": None},
        vsi_if_cmd: {"success": True, "output": f"interface Vsi-interface{vpc['vsi_interface']}\n l3-vni {l3_vni}", "error": None},
        "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
    }
    _add_snapshot(db, vpc, device, commands, details={
        "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
        "bgp_peer_established": {"ok": True}, "vsi_interface_exists": {"ok": True},
        "l3_vni_present": {"ok": True},
    })


def _drifted_snapshot(db, vpc, device):
    vsi_cmd = f"display l2vpn vsi name {vpc['vsi_name']} verbose"
    _add_snapshot(db, vpc, device, {
        "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: State: Established", "error": None},
        vsi_cmd: {"success": True, "output": "The VSI does not exist.", "error": None},
        "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
    }, details={"vsi_exists": {"ok": False}})


def _add_snapshot(db, vpc, device, commands, details):
    db.add(SdnValidationSnapshot(
        vpc_id=vpc["id"], device_id=device.id, validation_result="active",
        validation_details=json.dumps(details),
        snapshot_data=json.dumps({"commands": commands}),
        collection_started_at=NOW - timedelta(seconds=10),
        collection_completed_at=NOW - timedelta(seconds=5),
    ))
    db.commit()


def _put_exception(client, vpc_id, device_id, body):
    return client.put(f"/api/sdn/vpcs/{vpc_id}/devices/{device_id}/scope-exception", json=body)


# ── assurance API helpers ──


def _get_policy(client, vpc_id):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/assurance-policy")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _put_policy(client, vpc_id, body):
    return client.put(f"/api/sdn/vpcs/{vpc_id}/assurance-policy", json=body)


def _post_run(client, vpc_id, body=None):
    return client.post(f"/api/sdn/vpcs/{vpc_id}/assurance-runs", json=body or {})


def _list_runs(client, vpc_id, **params):
    resp = client.get(f"/api/sdn/vpcs/{vpc_id}/assurance-runs", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _get_run(client, vpc_id, run_id):
    return client.get(f"/api/sdn/vpcs/{vpc_id}/assurance-runs/{run_id}")


def _run_counts(db):
    return {
        "policies": db.query(SdnAssurancePolicy).count(),
        "runs": db.query(SdnAssuranceRun).count(),
        "deployments": db.query(SdnDeployment).count(),
        "bindings": db.query(SdnPortBinding).count(),
        "operations": db.query(SdnOperation).count(),
        "snapshots": db.query(SdnValidationSnapshot).count(),
        "plans": db.query(SdnPlan).count(),
    }


# ── 策略：GET 默认值 / PUT 校验与版本 ──


def test_get_policy_missing_returns_defaults_without_writing(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    data = _get_policy(client, vpc["id"])
    assert data["vpc_id"] == vpc["id"]
    assert data["enabled"] is False
    assert data["cadence"] == "manual"
    assert data["response_mode"] == "observe_only"
    assert data["version"] == 0
    # GET 缺失不隐式写库
    assert db.query(SdnAssurancePolicy).count() == 0


def test_get_policy_vpc_not_found(client):
    resp = client.get("/api/sdn/vpcs/99999/assurance-policy")
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.vpc_not_found"


def test_put_policy_create_and_bump_version_single_row(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    resp = _put_policy(client, vpc["id"], {"enabled": True, "cadence": "30m", "version": 0})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["version"] == 1
    assert data["enabled"] is True
    assert data["cadence"] == "30m"
    assert data["response_mode"] == "observe_only"

    resp = _put_policy(client, vpc["id"], {"enabled": False, "cadence": "1h", "version": 1})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["version"] == 2
    assert data["enabled"] is False
    assert data["cadence"] == "1h"
    assert db.query(SdnAssurancePolicy).count() == 1


def test_put_policy_validation(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    # cadence 白名单
    resp = _put_policy(client, vpc["id"], {"enabled": True, "cadence": "5m", "version": 0})
    assert resp.json()["error_key"] == "sdn.assurance_invalid_cadence"
    # response_mode 固定 observe_only
    resp = _put_policy(client, vpc["id"], {"enabled": True, "cadence": "manual", "response_mode": "auto_fix", "version": 0})
    assert resp.json()["error_key"] == "sdn.assurance_invalid_response_mode"
    # enabled 类型
    resp = _put_policy(client, vpc["id"], {"enabled": "yes", "cadence": "manual", "version": 0})
    assert resp.json()["error_key"] == "sdn.assurance_invalid_policy"
    # version 类型
    resp = _put_policy(client, vpc["id"], {"enabled": True, "cadence": "manual", "version": "x"})
    assert resp.json()["error_key"] == "sdn.assurance_invalid_policy"
    # 全程零写
    assert db.query(SdnAssurancePolicy).count() == 0


def test_put_policy_version_conflict_rejected_without_write(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "manual", "version": 0})
    resp = _put_policy(client, vpc["id"], {"enabled": True, "cadence": "10m", "version": 5})
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.assurance_policy_version_conflict"
    assert body["error_params"] == {"expected": 1, "given": 5}
    # 冲突不写库、版本不变
    row = db.query(SdnAssurancePolicy).first()
    assert row.version == 1
    assert row.cadence == "manual"


def test_concurrent_same_version_policy_update_has_one_winner(client, db, monkeypatch):
    """两个请求都读到 v1 时，CAS 只允许一个推进到 v2。"""
    from app.database import SessionLocal
    from app.routers.sdn_assurance import put_assurance_policy

    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "manual", "version": 0})

    barrier = threading.Barrier(2)
    original = assurance_mod._atomic_update_policy

    def synchronized_update(*args, **kwargs):
        barrier.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(assurance_mod, "_atomic_update_policy", synchronized_update)
    results = []
    errors = []

    def update(cadence):
        session = SessionLocal()
        try:
            results.append(put_assurance_policy(
                vpc["id"],
                {"enabled": True, "cadence": cadence, "version": 1},
                session,
            ))
        except Exception as exc:  # pragma: no cover - 失败时保留诊断
            errors.append(exc)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, cadence) for cadence in ("10m", "30m")]
        for future in futures:
            future.result()

    assert not errors, errors
    assert sorted(result.success for result in results) == [False, True]
    loser = next(result for result in results if not result.success)
    assert loser.error_key == "sdn.assurance_policy_version_conflict"
    db.expire_all()
    row = db.query(SdnAssurancePolicy).filter_by(vpc_id=vpc["id"]).one()
    assert row.version == 2
    assert row.cadence in {"10m", "30m"}


# ── 手动评估：四种 overall ──


def test_manual_run_healthy_overall_persisted(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _aligned_snapshot(db, vpc, leaf, tenant["id"])
    _put_policy(client, vpc["id"], {"enabled": True, "cadence": "10m", "version": 0})

    resp = _post_run(client, vpc["id"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["overall"] == "healthy"
    assert data["summary"] == {"overall": "healthy", "total": 0, "blocking": 0, "review": 0, "deferred": 0}
    assert data["items"] == []
    assert data["trigger"] == "manual"
    assert data["status"] == "completed"
    assert data["policy_version"] == 1
    assert data["policy_enabled"] is True
    assert data["facts"]["vpc_version"] == 0
    assert data["facts"]["leaves"][0]["aggregate"] == "aligned"
    assert db.query(SdnAssuranceRun).count() == 1

    # 历史：list 与 detail
    listed = _list_runs(client, vpc["id"])
    assert listed["total"] == 1
    assert listed["runs"][0]["id"] == data["id"]
    detail = _get_run(client, vpc["id"], data["id"])
    assert detail.status_code == 200
    assert detail.json()["data"]["overall"] == "healthy"


def test_manual_run_attention_coverage_gap(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _create_device(db, name="Leaf-U", ip="192.0.2.3")  # 无记录 → not_targeted
    resp = _post_run(client, vpc["id"])
    data = resp.json()["data"]
    assert data["overall"] == "attention"
    assert data["summary"]["review"] == 1
    item = data["items"][0]
    assert item["category"] == "coverage_gap"
    assert item["severity"] == "review"
    assert item["recommendation"] == "review_scope"
    assert item["device_id"] == 1
    # 白名单字段：无原始配置/CLI/凭据
    assert set(item.keys()) == {"key", "vpc_id", "device_id", "name", "host", "severity", "category", "source_refs", "exception", "recommendation"}
    assert "RAW-PLAN-1" not in json.dumps(data)


def test_manual_run_blocked_confirmed_drift(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _drifted_snapshot(db, vpc, leaf)
    resp = _post_run(client, vpc["id"])
    data = resp.json()["data"]
    assert data["overall"] == "blocked"
    assert data["summary"]["blocking"] == 1
    item = data["items"][0]
    assert item["category"] == "confirmed_drift"
    assert item["severity"] == "blocking"
    assert item["recommendation"] == "inspect_drift"


def test_manual_run_insufficient_evidence(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    # 无任何 EVPN Leaf → 无可评估对象
    resp = _post_run(client, vpc["id"])
    data = resp.json()["data"]
    assert data["overall"] == "insufficient_evidence"
    assert data["items"] == []


def test_only_missing_or_stale_evidence_is_insufficient_not_attention():
    projection = {
        "vpc": {"version": 4},
        "scope": {"summary": {"eligible": 1}},
        "attention": {
            "items": [{
                "key": "1:7:evidence_missing_or_stale",
                "vpc_id": 1,
                "device_id": 7,
                "name": "Leaf-07",
                "host": "192.0.2.7",
                "severity": "review",
                "category": "evidence_missing_or_stale",
                "source_refs": [],
                "exception": None,
            }]
        },
        "leaves": [],
    }
    result = evaluate_assurance(projection)
    assert result["overall"] == "insufficient_evidence"
    assert result["items"][0]["recommendation"] == "refresh_evidence"


def test_manual_run_policy_disabled_still_allowed(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _create_device(db, name="Leaf-U", ip="192.0.2.3")
    # 无策略（等价 disabled）→ 手动评估仍允许，结果明确 policy_enabled=false
    resp = _post_run(client, vpc["id"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["policy_enabled"] is False
    assert data["policy_version"] == 0
    assert data["overall"] == "attention"  # 评估语义不受 disabled 影响


def test_manual_run_trigger_only_manual(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    resp = _post_run(client, vpc["id"], {"trigger": "scheduled"})
    assert resp.json()["error_key"] == "sdn.assurance_invalid_trigger"
    assert db.query(SdnAssuranceRun).count() == 0


# ── 零副作用 / 零设备 I/O ──


def test_manual_run_zero_side_effects_and_no_device_io(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    _aligned_snapshot(db, vpc, leaf, tenant["id"])

    before = _run_counts(db)
    assert before["deployments"] == 1 and before["snapshots"] == 1
    assert before["bindings"] == 0 and before["operations"] == 0 and before["plans"] == 0
    vpc_version_before = db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version

    resp = _post_run(client, vpc["id"])
    assert resp.status_code == 200, resp.text

    after = _run_counts(db)
    assert after == {**before, "runs": before["runs"] + 1}
    assert db.query(SdnVpc).filter(SdnVpc.id == vpc["id"]).first().version == vpc_version_before
    # 路由模块不存在任何设备 I/O 客户端绑定（零 collector/executor/Netconf/SSH 调用路径）
    for forbidden in ("NetconfClient", "SdnValidationCollector", "SdnDeploymentExecutor", "ssh"):
        assert not hasattr(assurance_mod, forbidden)


# ── 例外边界 ──


def test_exception_defers_gap_but_never_hides_drift(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    gap_leaf = _create_device(db, name="Leaf-Gap", ip="192.0.2.4")
    drift_leaf = _create_device(db, name="Leaf-Drift", ip="192.0.2.5")
    _add_create_deployment(db, vpc, drift_leaf)
    _drifted_snapshot(db, vpc, drift_leaf)
    # 两台 Leaf 都挂 active maintenance exception
    for leaf in (gap_leaf, drift_leaf):
        _put_exception(client, vpc["id"], leaf.id, {"exception_type": "maintenance_pause", "reason": "维护中"})

    resp = _post_run(client, vpc["id"])
    data = resp.json()["data"]
    by_device = {i["device_id"]: i for i in data["items"]}
    # 未覆盖 Leaf：exception 把 coverage gap 保持 deferred，不升级 blocking
    gap_item = by_device[gap_leaf.id]
    assert gap_item["category"] == "coverage_deferred"
    assert gap_item["severity"] == "deferred"
    assert gap_item["recommendation"] == "review_exception"
    assert gap_item["exception"]["state"] == "active"
    # 漂移 Leaf：confirmed_drift blocking 不被吞掉，且携带 exception
    drift_item = by_device[drift_leaf.id]
    assert drift_item["category"] == "confirmed_drift"
    assert drift_item["severity"] == "blocking"
    assert drift_item["recommendation"] == "inspect_drift"
    assert drift_item["exception"]["state"] == "active"
    # 全局 blocked（blocking 事实优先）
    assert data["overall"] == "blocked"
    assert data["summary"]["blocking"] == 1
    assert data["summary"]["deferred"] == 1


# ── 坏历史稳定降级 ──


def test_bad_history_stable_degrade_run_completes(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    leaf = _create_device(db)
    _add_create_deployment(db, vpc, leaf)
    db.add(SdnValidationSnapshot(
        vpc_id=vpc["id"], device_id=leaf.id, validation_result="active",
        validation_details="not-json", snapshot_data="not-json",
        collection_started_at=NOW - timedelta(minutes=1), collection_completed_at=NOW,
    ))
    db.commit()
    resp = _post_run(client, vpc["id"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["overall"] in ("healthy", "attention", "blocked", "insufficient_evidence")
    # items 白名单字段（畸形快照最多产生 evidence 类项，绝不 500）
    for item in data["items"]:
        assert set(item.keys()) == {"key", "vpc_id", "device_id", "name", "host", "severity", "category", "source_refs", "exception", "recommendation"}


def test_malformed_persisted_run_is_type_safe_and_recursively_whitelisted(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    run = SdnAssuranceRun(
        vpc_id=vpc["id"], trigger="manual", status="completed",
        started_at=NOW, completed_at=NOW, policy_version=0, policy_enabled=False,
        summary_json='["wrong-type", {"password": "LEAK"}]',
        facts_json=json.dumps({
            "vpc_version": 1,
            "secret": "LEAK",
            "scope": {"eligible": 1, "password": "LEAK"},
            "leaves": [{"device_id": 1, "aggregate": "aligned", "raw_cli": "LEAK"}],
            "attention": {"total": 1, "token": "LEAK"},
        }),
        items_json=json.dumps([{
            "key": "1:1:coverage_gap", "vpc_id": vpc["id"], "device_id": 1,
            "name": "Leaf", "host": "192.0.2.1", "severity": "review",
            "category": "coverage_gap", "password": "LEAK",
            "source_refs": [{"kind": "leaf", "device_id": 1, "raw_cli": "LEAK"}],
            "exception": {"state": "active", "password": "LEAK"},
        }]),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    response = _get_run(client, vpc["id"], run.id)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["overall"] == "insufficient_evidence"
    assert data["summary"] == {
        "overall": "insufficient_evidence", "total": 0,
        "blocking": 0, "review": 0, "deferred": 0,
    }
    assert "LEAK" not in json.dumps(data)
    assert data["items"][0]["recommendation"] == "review_scope"


# ── 并发 / 分页 / 详情 ──


def test_concurrent_manual_runs_both_complete_and_distinct(client, db):
    """并发两次 manual run 各自完整、互不覆盖（处理器层 + 独立会话并发写）。

    TestClient 的 startup 会跑 alembic upgrade head，双客户端并发启动会竞争
    alembic_version 表；这里改为直接并发调用路由处理器（各线程独立 Session），
    验证的是本切片承诺的并发语义：追加两条 run、各自完整、不互相覆盖。
    """
    from app.database import SessionLocal
    from app.routers.sdn_assurance import create_manual_assurance_run

    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _create_device(db, name="Leaf-U", ip="192.0.2.3")

    results = []
    errors = []

    def _post():
        try:
            session = SessionLocal()
            try:
                resp = create_manual_assurance_run(vpc["id"], {}, session)
                results.append(resp)
            finally:
                session.close()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_post) for _ in range(2)]
        for f in futures:
            f.result()
    assert not errors, errors
    assert all(r.success for r in results)
    ids = [r.data["id"] for r in results]
    assert len(ids) == 2 and len(set(ids)) == 2
    listed = _list_runs(client, vpc["id"])
    assert listed["total"] == 2
    assert sorted(r["id"] for r in listed["runs"]) == sorted(ids)
    # 两条 run 各自完整（互不覆盖）
    for run_id in ids:
        detail = _get_run(client, vpc["id"], run_id).json()["data"]
        assert detail["overall"] in ("healthy", "attention", "blocked", "insufficient_evidence")
        assert detail["trigger"] == "manual"
        assert detail["status"] == "completed"


def test_run_list_pagination_and_detail_404(client, db):
    tenant = _create_tenant_via_api(client)
    vpc = _create_vpc_via_api(client, tenant["id"])
    _create_device(db, name="Leaf-U", ip="192.0.2.3")
    ids = []
    for _ in range(3):
        ids.append(_post_run(client, vpc["id"]).json()["data"]["id"])
    # limit 稳定降序
    page1 = _list_runs(client, vpc["id"], limit=2)
    assert [r["id"] for r in page1["runs"]] == sorted(ids, reverse=True)[:2]
    assert page1["total"] == 3
    # before 游标翻页
    page2 = _list_runs(client, vpc["id"], limit=2, before=page1["runs"][-1]["id"])
    assert [r["id"] for r in page2["runs"]] == [min(ids)]
    # run 不属于该 VPC → 404 语义（success=False + error_key）
    other_tenant = _create_tenant_via_api(client, name="t2")
    other_vpc = _create_vpc_via_api(client, other_tenant["id"], name="vpc-2")
    resp = _get_run(client, other_vpc["id"], ids[0])
    body = resp.json()
    assert body["success"] is False
    assert body["error_key"] == "sdn.assurance_run_not_found"
