"""S1-009 对抗性测试：CR24-CR26 真实链路缺口。

- CR24: 显式 reconcile 必须采到待对账目标接口（走真实 _commands/_snapshot_data，只 mock SSH）。
- CR25: unknown validation 必须存在可恢复路径（仅确定完成才幂等返回）。
- CR26: CLI 错误从 output 与结构化字段共同识别。
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import (
    SdnAttempt,
    SdnDeployment,
    SdnOperation,
    SdnPortBinding,
    SdnValidationSnapshot,
)
from app.services.sdn_operation_service import (
    device_port_key,
    release_claims,
    tenant_key,
    vpc_device_key,
    vpc_key,
)
from app.services.sdn_validation_collector import SdnValidationCollector

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _preview_body, _seed_ready  # noqa: E402
from test_s1_007_adversarial import (  # noqa: E402
    _active_claims,
    _do_access,
    _seed_unknown_port_bind,
    _seed_unknown_port_unbind,
)
from test_s1_008_adversarial import _binding, _reconcile, _set_port_snapshot  # noqa: E402


def _mock_credentials(device):
    """只 mock 设备凭据解析（非 SSH I/O）；真实 collector 仍走 _commands/_snapshot_data。"""
    return patch(
        "app.services.sdn_validation_collector.get_device_with_password",
        return_value=(device, "dummy-password", None),
    )


# ── CR24: 真实 reconcile 必须采到待对账目标接口 ──

def test_cr24_reconcile_port_bind_collects_target_interface(client, db):
    device, vpc, op = _seed_unknown_port_bind(client, db)
    binding = _binding(db, op["operation_id"])
    assert binding.status == "planned"  # unknown port_bind 的 binding 仍为 planned
    target_cmd = f"display current-configuration interface {binding.interface_name}"
    issued = []

    def _fake_collect(device, password, commands):
        issued.extend(commands)
        return [
            {"success": True, "output": ("service-instance 3200\n xconnect vsi vsi-a" if c == target_cmd else ""), "error": None}
            for c in commands
        ]

    with patch("app.services.sdn_validation_collector.SdnValidationCollector._collect", side_effect=_fake_collect), \
            _mock_credentials(device):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    assert resp.status_code == 200, resp.text
    assert target_cmd in issued  # 确实发出了目标接口回读命令
    assert resp.json()["data"]["reconciled"] is True
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "awaiting_validation"
    assert len(_active_claims(db, op["operation_id"])) == 0


def test_cr24_reconcile_port_unbind_collects_target_interface(client, db):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    assert binding.status == "planned"
    target_cmd = f"display current-configuration interface {binding.interface_name}"
    issued = []

    def _fake_collect(device, password, commands):
        issued.extend(commands)
        return [
            {"success": True, "output": ("interface GigabitEthernet1/0/1" if c == target_cmd else ""), "error": None}
            for c in commands
        ]

    with patch("app.services.sdn_validation_collector.SdnValidationCollector._collect", side_effect=_fake_collect), \
            _mock_credentials(device):
        resp = client.post(f"/api/sdn/operations/{op['operation_id']}/reconcile")
    assert resp.status_code == 200, resp.text
    assert target_cmd in issued
    assert resp.json()["data"]["reconciled"] is True
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "withdrawn"
    assert len(_active_claims(db, op["operation_id"])) == 0


def test_cr24_periodic_collection_excludes_planned_binding(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)  # binding planned，未执行
    binding = _binding(db, op["operation_id"])
    assert binding.status == "planned"
    target_cmd = f"display current-configuration interface {binding.interface_name}"
    issued = []

    def _fake_collect(device, password, commands):
        issued.extend(commands)
        return [{"success": True, "output": "", "error": None} for _ in commands]

    with patch("app.services.sdn_validation_collector.SdnValidationCollector._collect", side_effect=_fake_collect), \
            _mock_credentials(device):
        snap, err, cached = SdnValidationCollector().sync(db, vpc.id, device.id, force=True, min_interval_seconds=0)
    assert err is None
    assert snap is not None
    assert target_cmd not in issued  # 普通周期采集不把 planned binding 混入


# ── CR25: unknown validation 恢复路径 ──

def _active_snapshot(db, vpc, device, config_completed_at):
    snap = SdnValidationSnapshot(
        vpc_id=vpc.id, device_id=device.id, validation_result="active",
        collection_started_at=config_completed_at + timedelta(seconds=1),
        collection_completed_at=config_completed_at + timedelta(seconds=2),
        validation_details=json.dumps({
            "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
            "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
        }),
        snapshot_data=json.dumps({"commands": {
            "display arp vpn-instance sdn_l3vpn": {
                "success": True,
                "output": "10.1.0.2  aaaa-bbbb-cccc  100  GigabitEthernet1/0/1",
                "error": None,
            },
        }}),
    )
    db.add(snap); db.commit(); db.refresh(snap)
    return snap


def test_cr25_unknown_validation_recovers_on_retry(client, db):
    device, _, vpc = _seed_ready(client, db)
    op = _do_access(client, db, device, vpc, auto_apply=False)
    op_id = op["operation_id"]
    dep = db.query(SdnDeployment).filter(SdnDeployment.operation_id == op_id, SdnDeployment.action == "port_bind").first()
    dep.status = "success"
    dep.config_completed_at = datetime.utcnow() - timedelta(seconds=10)
    # 模拟 apply 成功：释放全部 4 条 scoped claims + 进入 awaiting_validation
    release_claims(db, [
        tenant_key(vpc.tenant_id), vpc_key(vpc.id),
        vpc_device_key(vpc.id, device.id), device_port_key(device.id, 1),
    ], owner_operation_id=op_id)
    db.query(SdnOperation).filter(SdnOperation.id == op_id).update({"status": "awaiting_validation"})
    db.commit()

    # 第一次 complete：采集失败 → unknown validation（attempt unknown + claims ambiguous）
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(None, {"key": "sdn.device_not_writable", "params": {}}, False)):
        r1 = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True})
    assert r1.json()["data"]["status"] == "unknown"
    held = _active_claims(db, op_id)
    assert held and all(c.status == "ambiguous" for c in held)
    first = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").order_by(SdnAttempt.id.desc()).first()
    assert first.status == "unknown"

    # 第二次 complete：采集成功 → 恢复，新建 validate attempt
    snap = _active_snapshot(db, vpc, device, dep.config_completed_at)
    with patch("app.routers.sdn_access.SdnValidationCollector.sync", return_value=(snap, None, False)):
        with patch("app.routers.sdn_access._run_gateway_ping", return_value={"status": "unsupported", "detail": "no gateway"}):
            r2 = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True})
    assert r2.json()["data"]["status"] == "succeeded"
    validates = db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").order_by(SdnAttempt.id.asc()).all()
    assert len(validates) == 2
    assert validates[0].status == "unknown"  # 旧 attempt 历史保留
    assert validates[1].status == "succeeded"  # 新 attempt 可追溯
    assert len(_active_claims(db, op_id)) == 0

    # 第三次 complete：latest validate succeeded → 幂等返回，不再新建 attempt
    r3 = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True})
    assert r3.json()["data"]["status"] == "succeeded"
    assert db.query(SdnAttempt).filter(SdnAttempt.operation_id == op_id, SdnAttempt.kind == "validate").count() == 2


# ── CR26: CLI 错误从 output 与结构化字段共同识别 ──

@pytest.mark.parametrize("bad_output", [
    "% Wrong parameter found at '^' position.",
    "Unrecognized command found at '^' position.",
    "Incomplete command found at '^' position.",
])
def test_cr26_port_unbind_cli_error_in_output_not_success(client, db, bad_output):
    device, vpc, op = _seed_unknown_port_unbind(client, db)
    binding = _binding(db, op["operation_id"])
    # success=true / error=null，但 output 含 CLI 错误 → 绝不当作配置缺失
    snap = _set_port_snapshot(db, vpc, binding, output=bad_output, success=True, error=None)
    resp = _reconcile(client, op["operation_id"], snap)
    assert resp.json()["data"]["reconciled"] is False
    assert db.query(SdnOperation).filter(SdnOperation.id == op["operation_id"]).first().status == "unknown"
