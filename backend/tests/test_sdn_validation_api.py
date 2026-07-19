"""SDN/VPC display 状态采集 API 测试（v3.3）。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import Device, SdnPortBinding


def _create_tenant(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc(client, tenant_id, name="vpc-1", cidr="192.168.2.0/24"):
    return client.post(
        "/api/sdn/vpcs",
        json={
            "name": name,
            "tenant_id": tenant_id,
            "cidr": cidr,
            "gateway_ip": "192.168.2.254",
        },
    ).json()["data"]


def _create_device(db):
    dev = Device(
        name="Leaf-04",
        host="192.168.100.5",
        port=830,
        username="admin",
        password_encrypted="encrypted",
        protected_interfaces="[]",
        platform="LSTN",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _create_active_binding(db, device_id, tenant_id, vpc_id):
    binding = SdnPortBinding(
        device_id=device_id,
        tenant_id=tenant_id,
        vpc_id=vpc_id,
        if_index=2,
        interface_name="GigabitEthernet1/0/2",
        service_instance=3200,
        status="active",
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def _fake_results(commands):
    outputs = {
        "display bgp peer l2vpn evpn": "1.1.1.1 65000 10 10 0 0 00:01:00 Established",
        "display current-configuration interface Vsi-interface1000": (
            "interface Vsi-interface1000\n"
            " ip binding vpn-instance sdn_l3vpn\n"
            " ip address 192.168.2.254 255.255.255.0\n"
            " l3-vni 10000"
        ),
        "display l2vpn vsi name vpc0001 verbose": (
            "VSI Name: vpc0001\n"
            "  VSI State               : Up\n"
            "  Gateway Interface       : VSI-interface 1000\n"
            "  VXLAN ID                : 20000\n"
            "  ACs:\n"
            "    GE1/0/2 srv3200                    0          Up          Manual"
        ),
        "display l2vpn mac-address": (
            "MAC Address    State     VSI Name                        Link ID/Name   Aging\n"
            "96ba-e5f7-0a06 Dynamic   vpc0001                         GE1/0/2        Aging"
        ),
        "display evpn route arp": (
            "IP address      MAC address     Router MAC      VSI index   Flags\n"
            "192.168.2.2     96ba-e5f7-0a06  001a-2b00-4e20  0           DL"
        ),
        "display bgp l2vpn evpn": (
            "Route distinguisher: 1:20000\n"
            "* >  Network : [2][0][48][96ba-e5f7-0a06][0][0.0.0.0]/104\n"
            "* >  Network : [2][0][48][96ba-e5f7-0a06][32][192.168.2.2]/136\n"
            "* >  Network : [3][0][32][1.1.1.4]/80"
        ),
        "display arp vpn-instance sdn_l3vpn": (
            "IP address      MAC address    VLAN/VSI name Interface                Aging Type\n"
            "192.168.2.2     96ba-e5f7-0a06 vpc0001       GE1/0/2                  1192  D"
        ),
        "display current-configuration interface GigabitEthernet1/0/2": (
            "interface GigabitEthernet1/0/2\n"
            " service-instance 3200\n"
            "  encapsulation default\n"
            "  xconnect vsi vpc0001"
        ),
    }
    return [
        {"cmd": cmd, "output": outputs.get(cmd, ""), "success": True, "error": None}
        for cmd in commands
    ]


def test_validation_sync_collects_snapshot_and_marks_active(client, db):
    """POST validation/sync 采集 display，写入快照并返回 active。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    device = _create_device(db)
    _create_active_binding(db, device.id, tenant["id"], vpc["id"])

    fake_device = SimpleNamespace(host=device.host, username=device.username)
    fake_ssh = MagicMock()
    fake_ssh.execute_commands.side_effect = lambda commands, delay_ms=300: _fake_results(commands)

    with patch(
        "app.services.sdn_validation_collector.get_device_with_password",
        return_value=(fake_device, "password", None),
    ), patch("app.utils.ssh_executor.SSHExecutor", return_value=fake_ssh):
        resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync")

    data = resp.json()
    assert data["success"] is True
    snapshot = data["data"]
    assert snapshot["cached"] is False
    assert snapshot["validation_result"] == "active"
    assert snapshot["validation_details"]["bgp_peer_established"]["ok"] is True
    assert snapshot["validation_details"]["vsi_up"]["ok"] is True
    assert snapshot["validation_details"]["type2_present"]["ok"] is True
    assert "display bgp l2vpn evpn" in snapshot["snapshot_data"]["commands"]


def test_validation_sync_reuses_recent_snapshot_without_ssh(client, db):
    """默认 600 秒内复用快照，不重复打设备 SSH。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    device = _create_device(db)
    _create_active_binding(db, device.id, tenant["id"], vpc["id"])

    fake_device = SimpleNamespace(host=device.host, username=device.username)
    fake_ssh = MagicMock()
    fake_ssh.execute_commands.side_effect = lambda commands, delay_ms=300: _fake_results(commands)

    with patch(
        "app.services.sdn_validation_collector.get_device_with_password",
        return_value=(fake_device, "password", None),
    ), patch("app.utils.ssh_executor.SSHExecutor", return_value=fake_ssh):
        first = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync")
        second = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync")

    assert first.json()["data"]["cached"] is False
    assert second.json()["data"]["cached"] is True
    assert fake_ssh.execute_commands.call_count == 1


def test_validation_sync_force_refreshes_snapshot(client, db):
    """force=true 跳过 600 秒缓存，重新采集。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    device = _create_device(db)
    _create_active_binding(db, device.id, tenant["id"], vpc["id"])

    fake_device = SimpleNamespace(host=device.host, username=device.username)
    fake_ssh = MagicMock()
    fake_ssh.execute_commands.side_effect = lambda commands, delay_ms=300: _fake_results(commands)

    with patch(
        "app.services.sdn_validation_collector.get_device_with_password",
        return_value=(fake_device, "password", None),
    ), patch("app.utils.ssh_executor.SSHExecutor", return_value=fake_ssh):
        client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync")
        resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync?force=true")

    assert resp.json()["data"]["cached"] is False
    assert fake_ssh.execute_commands.call_count == 2


def test_validation_latest_does_not_touch_device(client, db):
    """GET latest 只读最近快照，不触发设备访问。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    device = _create_device(db)
    fake_device = SimpleNamespace(host=device.host, username=device.username)
    fake_ssh = MagicMock()
    fake_ssh.execute_commands.side_effect = lambda commands, delay_ms=300: _fake_results(commands)

    with patch(
        "app.services.sdn_validation_collector.get_device_with_password",
        return_value=(fake_device, "password", None),
    ), patch("app.utils.ssh_executor.SSHExecutor", return_value=fake_ssh):
        client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/sync")

    fake_ssh.execute_commands.reset_mock()
    resp = client.get(f"/api/sdn/vpcs/{vpc['id']}/devices/{device.id}/validation/latest")

    assert resp.json()["data"]["validation_result"] == "active"
    fake_ssh.execute_commands.assert_not_called()
