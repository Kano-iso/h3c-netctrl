"""POST /api/sdn/deployments/{id}/apply 端点测试（v3.0 sdn-vpc-deployment-executor）

覆盖：
- 200 success：mock NETCONF 全成功
- 200 failed：mock NETCONF 抛异常 → status=failed（业务视为已尝试）
- 404：deployment_id 不存在
- 409：deployment.status ≠ pending
- 422：device 不在白名单（.2/.3/.177）
- 支持 delete / port_bind / port_unbind / gateway_delete 等撤回动作

依赖：mock NetconfClient（避免连真设备）
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.models import Device, SdnDeployment, SdnTenant, SdnVpc
from app.utils.crypto import encrypt_password


# ======================== helpers ========================

def _create_tenant_vpc_device(db, device_name="Leaf-04", device_ip="192.168.100.5",
                                action="create", vpc_status_value="pending", plan=None):
    from app.utils.sdn_allocator import SdnAllocator
    t = SdnTenant(
        name=f"t-{device_name}",
        rd="pending", import_rt="pending", export_rt="pending", l3_vni=0,
        auto_assigned=True,
    )
    db.add(t)
    db.flush()
    t.rd = SdnAllocator.allocate_rd(t.id)
    irt, ert = SdnAllocator.allocate_rt(t.id)
    t.import_rt = irt
    t.export_rt = ert
    t.l3_vni = SdnAllocator.allocate_l3vni(db)
    db.commit()

    v = SdnVpc(
        name="vpc-1",
        tenant_id=t.id,
        cidr="192.168.10.0/24",
        gateway_ip="192.168.10.1",
        gateway_mac="00:00:00:00:00:01",
        vni=SdnAllocator.allocate_l2vni(db),
        vsi_name="pending",  # 占位，flush 后用 v.id 重算（ADR-103 vpc{id:04d}）
        vsi_interface=SdnAllocator.allocate_vsi_interface(db),
        vlan_id=SdnAllocator.allocate_vlan(db),
        auto_assigned=True,
        status=vpc_status_value,
    )
    db.add(v)
    db.flush()  # 拿 v.id
    v.vsi_name = SdnAllocator.build_vsi_name(v.id)
    db.commit()
    db.refresh(v)

    dev = Device(
        name=device_name,
        host=device_ip,
        port=830,
        username="test",
        password_encrypted=encrypt_password("test_password_xyz"),
        protected_interfaces="[]",
        # v3.0 sdn-vpc-netconf-schema-xml T6 A 方案: 默认走 RSTN 平台（schema 化 NETCONF mock）
        # LSTN 平台走 SSH 22, 在 test_apply_lstn_ssh_success / test_apply_lstn_ssh_failure 单独覆盖
        platform="RSTN",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)

    if plan is None:
        # v3.0 sdn-vpc-netconf-schema-xml T3: planned_config 是 List[TemplateUnit]（双套 payload）
        # 默认构造 3 个 unit，每个 unit 含 cli_commands + xml_payloads（v1 走 CLI，v2 走 schema XML）
        plan = json.dumps([
            {"name": "vsi-l2", "description": "VSI L2 test", "cli_commands": [f"cmd {i}"], "xml_payloads": [f"<config><cmd>{i}</cmd></config>"]}
            for i in range(3)
        ])
    d = SdnDeployment(
        vpc_id=v.id, device_id=dev.id,
        action=action, planned_config=plan, status="pending",
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d, v, dev, t


def _patch_netconf_success():
    """构造 mock NetconfClient，edit_config 全部成功"""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.edit_config.return_value = "<ok/>"
    return patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client)


def _patch_netconf_failure_at(call_index):
    """构造 mock NetconfClient，第 call_index 次抛异常"""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    def raise_after(xml):
        if mock_client.edit_config.call_count >= call_index:
            raise RuntimeError(f"mock NETCONF failure at call {call_index}")
        return "<ok/>"
    mock_client.edit_config.side_effect = raise_after
    return patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client)


# ======================== 200 success ========================

def test_apply_200_success(client, db):
    """正常 apply → 200 + status=success"""
    d, _, _, _ = _create_tenant_vpc_device(db)

    with _patch_netconf_success():
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "success"


def test_apply_200_netconf_failure_returns_failed_status(client, db):
    """NETCONF 失败 → 200 + status=failed（业务视为已尝试下发，不返回 5xx）"""
    d, _, _, _ = _create_tenant_vpc_device(db)

    with _patch_netconf_failure_at(call_index=2):
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "failed"
    assert data["data"]["error"] is not None
    assert "配置下发失败" in data["data"]["error"]


# ======================== 错误路径 ========================

def test_apply_404_deployment_not_found(client):
    """deployment_id 不存在 → 404"""
    resp = client.post("/api/sdn/deployments/9999/apply")
    assert resp.status_code == 200  # APIResponse 包装, success=False
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.deployment_not_found"


def test_apply_409_not_pending(client, db):
    """deployment.status = success → 409"""
    d, _, _, _ = _create_tenant_vpc_device(db)
    # 改 status 为 success
    d.status = "success"
    db.commit()

    with _patch_netconf_success():
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.deployment_not_pending"


def test_apply_422_device_readonly_leaf01(client, db):
    """device = Leaf-01 (.2) → 422 SDN_DEVICE_NOT_WRITABLE"""
    d, _, _, _ = _create_tenant_vpc_device(db, device_name="Leaf-01", device_ip="192.168.100.2")

    resp = client.post(f"/api/sdn/deployments/{d.id}/apply")
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.device_not_writable"


def test_apply_422_device_readonly_test(client, db):
    """device = Test-Switch-177 (.177) → 422 SDN_DEVICE_NOT_WRITABLE"""
    d, _, _, _ = _create_tenant_vpc_device(db, device_name="Test-Switch-177", device_ip="192.168.100.177")

    resp = client.post(f"/api/sdn/deployments/{d.id}/apply")
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.device_not_writable"


def test_apply_delete_action_success(client, db):
    """action=delete 可执行，成功后返回 deployment success。"""
    d, v, _, _ = _create_tenant_vpc_device(db, action="delete", vpc_status_value="active")

    with _patch_netconf_success():
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "success"
    db.refresh(v)
    assert v.status == "withdrawn"


def test_apply_500_planned_config_invalid(client, db):
    """planned_config 是非法 JSON → 500 SDN_PLANNED_CONFIG_INVALID"""
    d, _, _, _ = _create_tenant_vpc_device(db, plan="not-valid-json{[")
    d.status = "pending"  # 二次确认
    db.commit()

    resp = client.post(f"/api/sdn/deployments/{d.id}/apply")
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.planned_config_invalid"


# ======================== 链路验证 ========================

def test_apply_does_not_use_ops_toolkit(client, db, monkeypatch):
    """验证: apply 端点不调 ops-toolkit 容器 (即不调任何 ops-toolkit 脚本)

    业务下发走 backend → NetconfClient → 设备, ops-toolkit 不参与。
    """
    d, _, _, _ = _create_tenant_vpc_device(db)

    # monkeypatch 模拟 ops-toolkit 容器调用, 验证 executor 不会调它
    called = {"ops_toolkit": False}
    def fake_ops(*args, **kwargs):
        called["ops_toolkit"] = True
        return None
    monkeypatch.setattr("subprocess.run", fake_ops)

    with _patch_netconf_success():
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    assert resp.status_code == 200
    assert called["ops_toolkit"] is False  # ops-toolkit 完全没被调用


# ======================== LSTN 平台 → SSH 22 通道（A 方案 T6） ========================

def _patch_ssh_success():
    """构造 mock SSHExecutor，execute_commands 全部成功"""
    mock_ssh = MagicMock()
    mock_ssh.execute_commands.return_value = [
        {"success": True, "cmd": c, "output": "", "error": None} for c in [
            "system-view", "vsi vpc0001", "return"
        ]
    ]
    return patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh)


def _patch_ssh_failure_at(cmd_index):
    """构造 mock SSHExecutor, 第 cmd_index 条命令返回 success=False"""
    mock_ssh = MagicMock()
    def fake_execute(commands, delay_ms=300):
        results = []
        for i, cmd in enumerate(commands):
            if i >= cmd_index:
                results.append({"success": False, "cmd": cmd, "output": "模拟失败", "error": "模拟失败"})
            else:
                results.append({"success": True, "cmd": cmd, "output": "", "error": None})
        return results
    mock_ssh.execute_commands.side_effect = fake_execute
    return patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh)


def test_apply_lstn_ssh_success(client, db):
    """LSTN 平台 → SSH 22 通道: 200 + status=success（A 方案 T6）"""
    d, _, _, _ = _create_tenant_vpc_device(db, device_name="Leaf-04-LSTN", device_ip="192.168.100.5")
    # 改 device.platform = LSTN
    from app.models import Device
    dev = db.query(Device).filter(Device.id == d.device_id).first()
    dev.platform = "LSTN"
    db.commit()

    with _patch_ssh_success():
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "success"


def test_apply_lstn_ssh_failure_returns_failed_status(client, db):
    """LSTN 平台 → SSH 22 通道: 命令失败 → 200 + status=failed（A 方案 T6）"""
    d, _, _, _ = _create_tenant_vpc_device(db, device_name="Leaf-04-LSTN2", device_ip="192.168.100.6")
    from app.models import Device
    dev = db.query(Device).filter(Device.id == d.device_id).first()
    dev.platform = "LSTN"
    db.commit()

    # 第 2 条命令失败 (system-view + cli_command)
    with _patch_ssh_failure_at(cmd_index=2):
        resp = client.post(f"/api/sdn/deployments/{d.id}/apply")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "failed"
    assert "配置下发失败" in data["data"]["error"]
