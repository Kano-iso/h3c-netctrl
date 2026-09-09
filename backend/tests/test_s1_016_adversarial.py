"""S1-016 对抗性测试：真实设备证据门禁与前置部署语义闭环。

这些断言在 S1-015 现状上会失败（错误放行）：
- 旧 `_l2_ready_status` 只证明「存在成功 create + 之后无成功 delete + 快照晚于 config 完成」，
  不检查绝对新鲜度 / 命令成功 / CLI 错误 / validation_details 目标 scoped 条件 / VPC 版本因果。
- execute 复用陈旧缓存，取证失败不阻断、零副作用不成立。
- create preflight 的「VNI 应不存在」语义可能被误接到 terminal access（后者要求 VSI 已存在）。

覆盖：
- fresh + scoped healthy 快照放行；
- 超过 TTL 阻断；时间晚于 deployment 但 validation failed/degraded 阻断；
- command success=false / CLI error / validation_details 缺项 / 非法 JSON 各自阻断；
- snapshot 早于 config completion 阻断；
- VPC version 变化后旧 deployment 阻断；
- execute 取证失败 → plan 未消费、零 operation/binding/deployment/claim；
- create preflight vs terminal predeploy 的「VNI 不存在/存在」语义反例。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import (
    SdnDeployment,
    SdnOperation,
    SdnPlan,
    SdnPortBinding,
    SdnResourceClaim,
    SdnValidationSnapshot,
)
from app.routers.sdn_access import (
    PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS,
    _l2_ready_status,
)
from app.services.sdn_preflight import SdnPreflight

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402


def _latest_snap(db, vpc):
    return (
        db.query(SdnValidationSnapshot)
        .filter(SdnValidationSnapshot.vpc_id == vpc.id)
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )


def _make_stale(db, vpc):
    """把 create config 完成时间 + 快照一起回拨到 TTL 之外（仍保持因果：快照晚于 config 完成）。"""
    create_dep = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.vpc_id == vpc.id, SdnDeployment.action == "create")
        .first()
    )
    base = datetime.utcnow() - timedelta(seconds=PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS + 60)
    create_dep.config_completed_at = base
    snap = _latest_snap(db, vpc)
    snap.collection_started_at = base + timedelta(seconds=1)
    snap.collection_completed_at = base + timedelta(seconds=2)
    db.commit()
    return snap


def _snapshot_commands(db, vpc):
    return json.loads(_latest_snap(db, vpc).snapshot_data)


# ── 放行（基线）──

def test_predeploy_fresh_scoped_healthy_snapshot_ready(db):
    device, _, vpc = _seed_ready(None, db)
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "ready"
    assert detail == ""


# ── 绝对新鲜度 / 因果窗口 ──

def test_predeploy_stale_snapshot_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    _make_stale(db, vpc)
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "older than" in detail


def test_predeploy_snapshot_predates_config_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    create_dep = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.vpc_id == vpc.id, SdnDeployment.action == "create")
        .first()
    )
    snap = _latest_snap(db, vpc)
    snap.collection_completed_at = create_dep.config_completed_at - timedelta(seconds=1)
    db.commit()
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"


# ── validation_result 不再是 L2 门禁（S1-017 解除 L3 耦合）──

@pytest.mark.parametrize("vr", ["failed", "degraded"])
def test_predeploy_validation_result_not_a_l2_gate(db, vr):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    snap.validation_result = vr
    db.commit()
    # L2 条件 + L2 命令均健康时，整张快照 validation_result 不影响纯 L2 门禁
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "ready"


# ── 命令成功 / CLI 错误 ──

def test_predeploy_command_failed_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    cmd = next(iter(data["commands"]))
    data["commands"][cmd]["success"] = False
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "failed" in detail


def test_predeploy_command_cli_error_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    cmd = next(iter(data["commands"]))
    data["commands"][cmd]["error"] = "Unrecognized command"
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "cli error" in detail


def test_predeploy_display_error_in_output_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    cmd = next(iter(data["commands"]))
    data["commands"][cmd]["output"] = "Incomplete command"
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"


# ── validation_details 缺项 / 非法 JSON ──

def test_predeploy_validation_details_missing_key_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    details = json.loads(snap.validation_details)
    del details["type3_present"]
    snap.validation_details = json.dumps(details)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "type3_present" in detail


def test_predeploy_validation_details_invalid_json_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    snap.validation_details = "{not json"
    db.commit()
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"


# ── VPC 版本因果 ──

def test_predeploy_vpc_version_change_blocked(db):
    device, _, vpc = _seed_ready(None, db)
    vpc.version += 1
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "vpc.version" in detail


# ── execute 取证失败零副作用 ──

def test_execute_collection_failure_blocks_without_side_effects(client, db):
    device, _, vpc = _seed_ready(client, db)
    plan_id = client.post(
        f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)
    ).json()["data"]["plan_id"]
    # 使既有证据陈旧 → execute 触发重新取证（force 采集）
    _make_stale(db, vpc)

    body = {**_preview_body(device), "idempotency_key": "key-s1-016-exec", "plan_id": plan_id, "auto_apply": False}
    with patch(
        "app.routers.sdn_access.SdnValidationCollector.sync",
        return_value=(None, {"key": "sdn.device_not_writable", "params": {}}, False),
    ):
        resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json=body)

    assert resp.status_code == 200
    assert resp.json()["error_key"] == "sdn.predeploy_unknown"
    # 零业务副作用：plan 未消费、零 operation/binding/claim/port_bind deployment
    assert db.query(SdnOperation).count() == 0
    assert db.query(SdnPortBinding).count() == 0
    assert db.query(SdnResourceClaim).count() == 0
    assert db.query(SdnDeployment).filter(SdnDeployment.action == "port_bind").count() == 0
    plan = db.query(SdnPlan).filter(SdnPlan.plan_id == plan_id).first()
    assert plan is not None and plan.status == "valid"


# ── create preflight vs terminal predeploy 语义反例 ──

def test_terminal_predeploy_requires_vsi_exists_not_create_semantics(db):
    device, _, vpc = _seed_ready(None, db)
    # terminal access 要求目标 VSI 已存在；vsi_exists=False（不存在）→ 阻断
    snap = _latest_snap(db, vpc)
    details = json.loads(snap.validation_details)
    details["vsi_exists"]["ok"] = False
    snap.validation_details = json.dumps(details)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "vsi_exists" in detail

    # create preflight 的 check_vpc_not_exists 是「VNI 应不存在」的 create 语义（deferred 占位），
    # 其 success=True 不代表 terminal access 已就绪——二者不得混用。
    pf = SdnPreflight(adapter=None, db=None)
    r = pf.check_vpc_not_exists(None, vpc)
    assert r.success is True
    assert "deferred" in r.reason
