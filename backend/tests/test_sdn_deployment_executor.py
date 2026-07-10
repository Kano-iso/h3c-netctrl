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

from app.models import Device, SdnDeployment, SdnTenant, SdnVpc
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
        vsi_name=SdnAllocator.build_vsi_name(tenant.name, name),
        vsi_interface=SdnAllocator.allocate_vsi_interface(db),
        vlan_id=SdnAllocator.allocate_vlan(db),
        auto_assigned=True,
        status="pending",
    )
    db.add(v)
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


def _create_deployment(db, vpc, device, action="create", planned=None, status="pending"):
    if planned is None:
        planned = json.dumps([{"mode": "merge", "command": "vsi vpc0001"}])
    d = SdnDeployment(
        vpc_id=vpc.id,
        device_id=device.id,
        action=action,
        planned_config=planned,
        status=status,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


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


def test_execute_rejects_delete_action(db):
    """action=delete → SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED (422, 本 change 仅 create)"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    d = _create_deployment(db, vpc, dev, action="delete")

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
    """mock NetconfClient 全成功 → status=success, 14 条全下发"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    cmds = [{"mode": "merge", "command": f"cmd {i}"} for i in range(14)]
    d = _create_deployment(db, vpc, dev, planned=json.dumps(cmds))

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.edit_config.return_value = "<ok/>"

    with patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    assert result.status == "success"
    assert result.error is None
    assert mock_client.edit_config.call_count == 14


def test_execute_netconf_failure_marks_failed(db):
    """mock NetconfClient 第 5 条 raise → status=failed + error 含第 5 条"""
    tenant = _create_tenant(db)
    vpc = _create_vpc(db, tenant)
    dev = _create_device(db)
    cmds = [{"mode": "merge", "command": f"cmd {i}"} for i in range(14)]
    d = _create_deployment(db, vpc, dev, planned=json.dumps(cmds))

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    def raise_on_5th(xml):
        # call_count 在 raise 之后才递增
        if mock_client.edit_config.call_count >= 5:
            raise RuntimeError("NETCONF 设备拒绝")
        return "<ok/>"
    mock_client.edit_config.side_effect = raise_on_5th

    with patch("app.services.sdn_deployment_executor.NetconfClient", return_value=mock_client):
        executor = SdnDeploymentExecutor()
        result = executor.execute(db, deployment_id=d.id)

    # 第 5 条 raise 后立即停, 不应下发 14 条
    assert mock_client.edit_config.call_count == 5
    assert result.status == "failed"
    assert "第 5" in result.error or "配置下发失败" in result.error
