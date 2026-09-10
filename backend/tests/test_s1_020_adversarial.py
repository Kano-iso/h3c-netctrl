"""S1-020 对抗性测试：修复首次接入自阻断（predeploy vsi_up 动态必需）。

这些断言在 S1-019 现状上会失败（`_l2_ready_status` 无条件要求固定四项 vsi_up=True）：
- 无本地绑定 + vsi_up=False + 其余 L2 证据健康 → 应 ready（首个 AC bootstrap 不得阻断）；
- unbound/planned 历史绑定不得误判为「已有绑定」而要求 vsi_up；
- 已有 active/expanding 本地绑定 + vsi_up=False → 仍应 unknown/block（Down 保守阻断）；
- 已有绑定 + vsi_up=True → ready；
- preview/execute 用同一动态语义；execute 证据不足仍 force refresh 且失败零业务副作用。

统一语义：collector 已表达 `vsi_up.required = bool(active/expanding 本地绑定)`；
`_l2_ready_status` 必须按「目标 Leaf 是否有 active/expanding 绑定」动态决定 vsi_up 是否必需。
"""
import json
from unittest.mock import patch

import pytest

from app.models import (
    SdnDeployment,
    SdnOperation,
    SdnPortBinding,
    SdnResourceClaim,
    SdnValidationSnapshot,
)
from app.routers.sdn_access import _l2_ready_status

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


def _set_vsi_up(db, vpc, ok):
    snap = _latest_snap(db, vpc)
    details = json.loads(snap.validation_details)
    details["vsi_up"]["ok"] = ok
    snap.validation_details = json.dumps(details)
    db.commit()
    return snap


def _add_binding(db, vpc, device, status, if_index=11, interface_name="GigabitEthernet1/0/11"):
    b = SdnPortBinding(
        device_id=device.id, tenant_id=vpc.tenant_id, vpc_id=vpc.id,
        if_index=if_index, interface_name=interface_name,
        access_vlan=None, service_instance=3299, status=status,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# ── 1. 无本地绑定 + vsi_up=False → ready（S1-019 会阻断）──

def test_no_local_binding_vsi_up_down_is_ready(db):
    device, _, vpc = _seed_ready(None, db)
    _set_vsi_up(db, vpc, ok=False)
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "ready", detail


# ── 2. 已有 active/expanding 绑定 + vsi_up=False → unknown/block ──

@pytest.mark.parametrize("status", ["active", "expanding"])
def test_active_binding_vsi_up_down_blocks(db, status):
    device, _, vpc = _seed_ready(None, db)
    _add_binding(db, vpc, device, status)
    _set_vsi_up(db, vpc, ok=False)
    st, detail = _l2_ready_status(db, vpc, device.id)
    assert st == "unknown"
    assert "vsi_up" in detail


# ── 3. 已有绑定 + vsi_up=True → ready ──

def test_active_binding_vsi_up_true_ready(db):
    device, _, vpc = _seed_ready(None, db)
    _add_binding(db, vpc, device, "active")
    # _seed_ready 已 vsi_up.ok=True
    st, detail = _l2_ready_status(db, vpc, device.id)
    assert st == "ready", detail


# ── 4. unbound/planned 历史行不得误判为「已有绑定」──

@pytest.mark.parametrize("status", ["unbound", "planned"])
def test_unbound_or_planned_binding_does_not_require_vsi_up(db, status):
    device, _, vpc = _seed_ready(None, db)
    _add_binding(db, vpc, device, status)
    _set_vsi_up(db, vpc, ok=False)
    st, detail = _l2_ready_status(db, vpc, device.id)
    assert st == "ready", detail


# ── 5. preview 用动态 vsi_up 语义 ──

def test_preview_uses_dynamic_vsi_up_semantics(client, db):
    device, _, vpc = _seed_ready(client, db)
    _set_vsi_up(db, vpc, ok=False)
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["predeploy_status"] == "ready"


# ── 6. execute 用动态 vsi_up 语义（无绑定 + vsi_up down → 不再 sdn.predeploy_unknown）──

def test_execute_uses_dynamic_vsi_up_semantics(client, db):
    device, _, vpc = _seed_ready(client, db)
    _set_vsi_up(db, vpc, ok=False)
    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json={
        **_preview_body(device), "idempotency_key": "s1-020-key", "plan_id": plan_id, "auto_apply": False,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    assert "operation_id" in body["data"]


# ── 7. 已有绑定 + vsi_up down → execute force refresh 后仍阻断 + 零业务副作用 ──

def test_execute_active_binding_vsi_up_down_blocks_without_side_effects(client, db):
    device, _, vpc = _seed_ready(client, db)
    _add_binding(db, vpc, device, "active", if_index=21, interface_name="GigabitEthernet1/0/21")
    snap = _set_vsi_up(db, vpc, ok=False)

    plan_id = client.post(f"/api/sdn/vpcs/{vpc.id}/access-preview", json=_preview_body(device)).json()["data"]["plan_id"]
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        resp = client.post(f"/api/sdn/vpcs/{vpc.id}/access", json={
            **_preview_body(device), "idempotency_key": "s1-020-block", "plan_id": plan_id, "auto_apply": False,
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False, body
    assert body["error_key"] == "sdn.predeploy_unknown", body
    # 零业务副作用：未建 operation/binding/deployment、未占 claim
    assert db.query(SdnOperation).filter(SdnOperation.vpc_id == vpc.id).count() == 0
    assert db.query(SdnPortBinding).filter(SdnPortBinding.vpc_id == vpc.id, SdnPortBinding.status != "unbound").count() == 1  # 仅测试预置的 active 绑定
    assert db.query(SdnDeployment).filter(SdnDeployment.action == "port_bind").count() == 0
    assert db.query(SdnResourceClaim).filter(SdnResourceClaim.released_at.is_(None)).count() == 0
