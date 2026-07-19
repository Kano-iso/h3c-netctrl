"""SdnDeploymentExecutor 单元测试（v3.0 sdn-vpc-deployment-executor）

覆盖：
- 校验类（status / action / device host / JSON 解析）
- 串行 NETCONF 下发
- 失败路径（NETCONF 抛异常 → status=failed + error_message）
- 设备白名单（.2/.3 拒绝）
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.models import Device, SdnDeployment, SdnPortBinding, SdnTenant, SdnVpc
from app.services.sdn_deployment_executor import (
    SdnDeploymentError,
    SdnDeploymentExecutor,
)


# ======================== helpers ========================

def _create_tenant(db, name="t1"):
    from app.utils.sdn_allocator import SdnAllocator
    t = SdnTenant(
        name=name,
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
    db.refresh(t)
    return t


def _create_vpc(db, tenant, name="vpc-1", cidr="192.168.10.0/24"):
    from app.utils.sdn_allocator import SdnAllocator
    v = SdnVpc(
        name=name,
        tenant_id=tenant.id,
        cidr=cidr,
        gateway_ip="192.168.10.1",
        gateway_mac="00:00:00:00:00:01",
        vni=SdnAllocator.allocate_l2vni(db),
        vsi_name="pending",  # 占位，flush 后用 v.id 重算（ADR-103 vpc{id:04d}）
        vsi_interface=SdnAllocator.allocate_vsi_interface(db),
        vlan_id=SdnAllocator.allocate_vlan(db),
        auto_assigned=True,
        status="pending",
    )
    db.add(v)
    db.flush()  # 拿 v.id
    v.vsi_name = SdnAllocator.build_vsi_name(v.id)
    db.commit()
    db.refresh(v)
    return v


def _create_device(db, name="Leaf-04", ip="192.168.100.5"):
    from app.utils.crypto import encrypt_password
    dev = Device(
        name=name,
        host=ip,
        port=830,
        username="test",
        password_encrypted=encrypt_password("test_password_xyz"),
        protected_interfaces="[]",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _create_deployment(db, vpc, device, action="create", planned=None, status="pending", binding=None):
    if planned is None:
        planned = json.dumps([{"mode": "merge", "command": "vsi vpc0001"}])
    d = SdnDeployment(
        vpc_id=vpc.id,
        device_id=device.id,
        action=action,
        port_binding_id=binding.id if binding is not None else None,
        planned_config=planned,
        status=status,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _create_binding(db, vpc, device):
    b = SdnPortBinding(
        device_id=device.id,
        tenant_id=vpc.tenant_id,
        vpc_id=vpc.id,
        if_index=14,
        interface_name="GigabitEthernet1/0/14",
        access_vlan=vpc.vlan_id,
        service_instance=None,
        status="pending",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# ======================== 校验类 ========================

def test_execute_deployment_not_found(db):
    """deployment_id 不存在 → SdnDeploymentError SDN_DEPLOYMENT_NOT_FOUND"""
    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=9999)
    assert exc.value.error_key == "SDN_DEPLOYMENT_NOT_FOUND"
    assert exc.value.status_code == 404


def test_execute_rejects_not_pending(db):
    """status=success 重放 → SDN_DEPLOYMENT_NOT_PENDING (409)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    d = _create_deployment(db, vpc, dev, status="success")

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_DEPLOYMENT_NOT_PENDING"
    assert exc.value.status_code == 409


def test_execute_rejects_unknown_action(db):
    """未知 action → SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED (422)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    d = _create_deployment(db, vpc, dev, action="invalid-action")

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED"
    assert exc.value.status_code == 422


def test_execute_rejects_readonly_device(db):
    """device.host = .2 → SDN_DEVICE_NOT_WRITABLE (422)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db, name="Leaf-01", ip="192.168.100.2")  # SDN 参考机
    d = _create_deployment(db, vpc, dev)

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_DEVICE_NOT_WRITABLE"
    assert exc.value.status_code == 422


def test_execute_rejects_test_device(db):
    """device.host = .177 → SDN_DEVICE_NOT_WRITABLE (.177 是 test 设备, 不允许下发)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db, name="Test-Switch-177", ip="192.168.100.177")
    d = _create_deployment(db, vpc, dev)

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_DEVICE_NOT_WRITABLE"


def test_parse_planned_config_invalid_json(db):
    """planned_config 是非法 JSON → status=failed (deployment 已 commit)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    d = _create_deployment(db, vpc, dev, planned="not-valid-json{[")

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_PLANNED_CONFIG_INVALID"

    # 验证 deployment 状态已写回
    db.refresh(d)
    assert d.status == "failed"
    assert "格式错误" in d.error


def test_parse_planned_config_empty(db):
    """planned_config 为空 → SDN_PLANNED_CONFIG_INVALID"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    d = _create_deployment(db, vpc, dev, planned="")

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_PLANNED_CONFIG_INVALID"


def test_parse_planned_config_missing_command_field(db):
    """planned_config 缺 command 字段 → SDN_PLANNED_CONFIG_INVALID"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    bad = json.dumps([{"mode": "merge"}])  # 缺 command
    d = _create_deployment(db, vpc, dev, planned=bad)

    executor = SdnDeploymentExecutor()
    with pytest.raises(SdnDeploymentError) as exc:
        executor.execute(db, deployment_id=d.id)
    assert exc.value.error_key == "SDN_PLANNED_CONFIG_INVALID"


# ======================== 下发路径 ========================

def test_execute_success(db):
    """mock NetconfClient 全成功 → status=success, RSTN 平台走 xml_payloads 通道（A 方案 T6）"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    # v3.0 T6 A 方案: device.platform = RSTN → 走 NETCONF schema XML 通道
    # 1 unit × 3 xml_payloads = 3 次 NETCONF edit_config
    cmds = [f"cmd {i}" for i in range(3)]
    planned = json.dumps([{
        "name": "test-unit",
        "description": "test",
        "cli_commands": cmds,
        "xml_payloads": [f"<config><cmd>{c}</cmd></config>" for c in cmds],
        "undo_cli": [],
        "undo_xml": [],
    }])
    d = _create_deployment(db, vpc, dev, planned=planned)
    # 设置 device.platform = RSTN（RSTN 走 xml_payloads 通道）
    dev.platform = "RSTN"
    db.commit()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.edit_config.return_value = "<ok/>"

    with patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    assert result.status == "success"
    assert result.error is None
    db.refresh(vpc)
    assert vpc.status == "active"
    # RSTN 走 xml_payloads，每个 unit 3 条 xml = 3 次 edit_config
    assert mock_client.edit_config.call_count == 3


def test_execute_lstn_ssh_success(db):
    """LSTN 平台 → SSH 22 通道: mock SSHExecutor 全成功 → status=success（A 方案 T6）"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    # v3.0 T6 A 方案: LSTN 走 SSH 22 + cli_commands
    cmds = [f"cmd {i}" for i in range(3)]
    planned = json.dumps([{
        "name": "test-unit-lstn",
        "description": "test LSTN",
        "cli_commands": cmds,
        "xml_payloads": [],
        "undo_cli": [],
        "undo_xml": [],
    }])
    d = _create_deployment(db, vpc, dev, planned=planned)
    dev.platform = "LSTN"
    db.commit()

    mock_ssh = MagicMock()
    mock_ssh.execute_commands.return_value = [
        {"success": True, "cmd": c, "output": "", "error": None} for c in
        ["system-view"] + cmds + ["return"]
    ]

    with patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    assert result.status == "success"
    assert result.error is None
    # 1 unit，3 cli_commands + system-view + return = 5 条命令一次 SSH 连接
    assert mock_ssh.execute_commands.call_count == 1


def test_execute_delete_success_marks_vpc_withdrawn(db):
    """action=delete 成功后 VPC 状态回写 withdrawn。"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    vpc.status = "active"
    dev = _create_device(db)
    planned = json.dumps([{
        "name": "vsi-l3",
        "description": "delete vsi interface",
        "cli_commands": ["undo interface Vsi-interface1000"],
        "xml_payloads": [],
        "undo_cli": [],
        "undo_xml": [],
    }])
    d = _create_deployment(db, vpc, dev, action="delete", planned=planned)
    dev.platform = "LSTN"
    db.commit()

    mock_ssh = MagicMock()
    mock_ssh.execute_commands.return_value = [
        {"success": True, "cmd": "system-view", "output": "", "error": None},
        {"success": True, "cmd": "undo interface Vsi-interface1000", "output": "", "error": None},
        {"success": True, "cmd": "return", "output": "", "error": None},
    ]

    with patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh):
        result = SdnDeploymentExecutor().execute(db, deployment_id=d.id)

    assert result.status == "success"
    db.refresh(vpc)
    assert vpc.status == "withdrawn"


def test_execute_port_bind_and_unbind_update_binding_status(db):
    """port_bind / port_unbind 成功后回写端口绑定状态。"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    binding = _create_binding(db, vpc, dev)
    dev.platform = "LSTN"
    planned = json.dumps([{
        "name": "port-bind",
        "description": "bind port",
        "cli_commands": ["interface GigabitEthernet1/0/14", "port access vlan 2000"],
        "xml_payloads": [],
        "undo_cli": [],
        "undo_xml": [],
    }])
    bind_deployment = _create_deployment(
        db, vpc, dev, action="port_bind", planned=planned, binding=binding
    )
    db.commit()

    mock_ssh = MagicMock()
    mock_ssh.execute_commands.return_value = [
        {"success": True, "cmd": "system-view", "output": "", "error": None},
        {"success": True, "cmd": "interface GigabitEthernet1/0/14", "output": "", "error": None},
        {"success": True, "cmd": "port access vlan 2000", "output": "", "error": None},
        {"success": True, "cmd": "return", "output": "", "error": None},
    ]
    with patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh):
        SdnDeploymentExecutor().execute(db, deployment_id=bind_deployment.id)
    db.refresh(binding)
    assert binding.status == "active"

    unbind_deployment = _create_deployment(
        db, vpc, dev, action="port_unbind", planned=planned, binding=binding
    )
    with patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh):
        SdnDeploymentExecutor().execute(db, deployment_id=unbind_deployment.id)
    db.refresh(binding)
    assert binding.status == "unbound"


def test_execute_lstn_ssh_failure_marks_failed(db):
    """LSTN 平台 → SSH 22 通道: 命令失败 → status=failed（A 方案 T6）"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    cmds = [f"cmd {i}" for i in range(3)]
    planned = json.dumps([{
        "name": "test-unit-lstn-fail",
        "description": "test LSTN fail",
        "cli_commands": cmds,
        "xml_payloads": [],
        "undo_cli": [],
        "undo_xml": [],
    }])
    d = _create_deployment(db, vpc, dev, planned=planned)
    dev.platform = "LSTN"
    db.commit()

    mock_ssh = MagicMock()
    def fake_execute(commands, delay_ms=300):
        # 第 2 条命令（system-view 之后第 1 条 cli）失败
        return [
            {"success": i != 2, "cmd": c, "output": "", "error": None if i != 2 else "mock fail"}
            for i, c in enumerate(commands)
        ]
    mock_ssh.execute_commands.side_effect = fake_execute

    with patch("app.utils.ssh_executor.SSHExecutor", return_value=mock_ssh):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    assert result.status == "failed"
    assert "配置下发失败" in result.error


def test_execute_netconf_failure_marks_failed(db):
    """mock NetconfClient 第 2 条 raise → status=failed + error 含配置下发失败（A 方案 T6 RSTN 路径）"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    # v3.0 T6 A 方案: RSTN 平台走 NETCONF schema XML
    cmds = [f"cmd {i}" for i in range(3)]
    planned = json.dumps([{
        "name": "test-unit",
        "description": "test",
        "cli_commands": cmds,
        "xml_payloads": [f"<config><cmd>{c}</cmd></config>" for c in cmds],
        "undo_cli": [],
        "undo_xml": [],
    }])
    d = _create_deployment(db, vpc, dev, planned=planned)
    # 设置 device.platform = RSTN
    dev.platform = "RSTN"
    db.commit()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    call_counter = [0]
    def raise_on_2nd(xml):
        # 用显式计数器, 第 2 次调用时 raise
        call_counter[0] += 1
        if call_counter[0] >= 2:
            raise RuntimeError("NETCONF 设备拒绝")
        return "<ok/>"
    mock_client.edit_config.side_effect = raise_on_2nd

    with patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    # 第 2 条 raise 后立即停（RSTN 走 xml_payloads，1 unit 3 条 xml）
    assert mock_client.edit_config.call_count == 2
    assert result.status == "failed"
    assert "配置下发失败" in result.error
