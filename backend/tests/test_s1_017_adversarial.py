"""S1-017 对抗性测试：解除 terminal L2 接入门禁对 L3 网关健康的隐式耦合。

这些断言在 S1-016 现状上会失败（错误耦合 L3）：
- `_l2_ready_status` 要求整张快照 `validation_result == "active"` 且遍历全部命令成功，
  使 Vsi-interface/L3VNI 不健康、gateway delete 后 L3 命令失败也错误阻断纯 L2 接入。
- 修复后：L2 predeploy 只按 L2 所需条件（bgp_peer_established/vsi_exists/vsi_up/type3_present）+ L2 所需命令独立判定；
  网关/L3 健康继续由 complete 业务验证的 l3_gateway_ready 表达，不互相冒充。

覆盖：
- validation_result=degraded + L2 健康 + L3 失败 → L2 predeploy ready；
- Vsi-interface/L3VNI 命令失败但 L2 命令成功 → L2 predeploy ready；
- bgp_peer_established/vsi_exists/type3_present 分别 false → 阻断（vsi_up 自 S1-020 起为动态必需，见 test_s1_020_adversarial.py）；
- L2 必需命令缺失 / success=false / CLI error 分别阻断；
- complete/业务验证仍把 L3 不健康表达为 degraded（不冒充完整业务成功）。
"""
import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.models import (
    SdnDeployment,
    SdnOperation,
    SdnValidationSnapshot,
)
from app.routers.sdn_access import _l2_ready_status

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402
from test_s1_007_adversarial import _do_access  # noqa: E402


def _latest_snap(db, vpc):
    return (
        db.query(SdnValidationSnapshot)
        .filter(SdnValidationSnapshot.vpc_id == vpc.id)
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )


def _l3_unhealthy(db, vpc, *, validation_result="degraded"):
    """把 L3/网关维度置为不健康，L2 维度保持健康。"""
    snap = _latest_snap(db, vpc)
    details = json.loads(snap.validation_details)
    details["vsi_interface_exists"]["ok"] = False
    details["l3_vni_present"]["ok"] = False
    snap.validation_details = json.dumps(details)
    snap.validation_result = validation_result
    db.commit()
    return snap


# ── validation_result / L3 命令失败不拖垮纯 L2 门禁（S1-016 会错误阻断）──

def test_l2_ready_with_degraded_overall_and_healthy_l2(db):
    device, _, vpc = _seed_ready(None, db)
    _l3_unhealthy(db, vpc, validation_result="degraded")
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "ready"


def test_l2_ready_with_l3_command_failure(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    # Vsi-interface/L3VNI 相关命令失败 + CLI error，但 L2 命令健康
    data["commands"]["display current-configuration interface Vsi-interface1"] = {
        "success": False, "output": "Unrecognized command", "error": "Unrecognized command",
    }
    snap.snapshot_data = json.dumps(data)
    # 同时让 L3 维度不健康，整张快照 degraded
    details = json.loads(snap.validation_details)
    details["vsi_interface_exists"]["ok"] = False
    details["l3_vni_present"]["ok"] = False
    snap.validation_details = json.dumps(details)
    snap.validation_result = "degraded"
    db.commit()
    status, _ = _l2_ready_status(db, vpc, device.id)
    assert status == "ready"


# ── L2 必需条件分别 false → 阻断 ──
# 注：vsi_up 自 S1-020 起为动态必需（仅目标 Leaf 已有 active/expanding 本地绑定时必需），
# 其「无绑定放行 / 有绑定阻断」语义见 test_s1_020_adversarial.py，此处只覆盖始终必需的三项。

@pytest.mark.parametrize("check", ["bgp_peer_established", "vsi_exists", "type3_present"])
def test_l2_condition_false_blocks(db, check):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    details = json.loads(snap.validation_details)
    details[check]["ok"] = False
    snap.validation_details = json.dumps(details)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert check in detail


# ── L2 必需命令缺失 / success=false / CLI error 分别阻断 ──

def test_l2_command_missing_blocks(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    del data["commands"]["display bgp l2vpn evpn"]
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "missing L2 command" in detail


def test_l2_command_failed_blocks(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    data["commands"]["display bgp peer l2vpn evpn"]["success"] = False
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "L2 command failed" in detail


def test_l2_command_cli_error_blocks(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    data = json.loads(snap.snapshot_data)
    data["commands"]["display bgp peer l2vpn evpn"]["error"] = "Unrecognized command"
    snap.snapshot_data = json.dumps(data)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "L2 command cli error" in detail


# ── complete/业务验证仍把 L3 不健康表达为 degraded（不冒充完整业务成功）──

def test_complete_still_expresses_l3_unhealth_as_degraded(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    dep = (
        db.query(SdnDeployment)
        .filter(SdnDeployment.operation_id == op["operation_id"], SdnDeployment.action == "port_bind")
        .first()
    )
    snap = _latest_snap(db, vpc)
    dep.status = "success"
    dep.config_completed_at = snap.collection_started_at - timedelta(seconds=1)
    db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).update({"status": "awaiting_validation"})
    db.commit()

    # L2 健康（vsi_exists/vsi_up/type3/bgp ok），L3/网关不健康
    details = json.loads(snap.validation_details)
    details["vsi_interface_exists"]["ok"] = False
    details["l3_vni_present"]["ok"] = False
    snap.validation_details = json.dumps(details)
    snap.validation_result = "active"
    db.commit()

    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        with patch("app.routers.sdn_access._run_gateway_ping", return_value={"status": "unsupported", "detail": "no gateway"}):
            resp = client.post(f"/api/sdn/operations/{op['operation_id']}/complete", json={"force_validation": True})

    data = resp.json()["data"]
    assert data["status"] == "degraded"
    assert data["dimensions"]["business_validation"]["l2_ready"] is True
    assert data["dimensions"]["business_validation"]["l3_gateway_ready"] is False
