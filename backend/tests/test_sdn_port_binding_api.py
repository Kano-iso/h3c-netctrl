"""SDN/VPC 端口绑定 API 测试（v3.3 VPC/EVPN 配置闭环）。"""

import json

from app.models import Device


def _create_tenant(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc(client, tenant_id, name="vpc-1", cidr="192.168.10.0/24"):
    return client.post(
        "/api/sdn/vpcs",
        json={"name": name, "tenant_id": tenant_id, "cidr": cidr},
    ).json()["data"]


def _create_device(db, name="Leaf-04", ip="192.168.100.5", protected="[]", platform="LSTN", sdn_role="evpn_leaf"):
    dev = Device(
        name=name,
        host=ip,
        port=830,
        username="test",
        password_encrypted="encrypted",
        protected_interfaces=protected,
        platform=platform,
        sdn_role=sdn_role,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def test_create_port_binding_defaults_to_vpc_vlan(client, db):
    """创建绑定时不传 SI/VLAN，默认使用 VPC 自动分配 VLAN。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post("/api/sdn/port-bindings", json={
        "device_id": dev.id,
        "vpc_id": vpc["id"],
        "if_index": 14,
        "interface_name": "GigabitEthernet1/0/14",
    })
    data = resp.json()
    assert data["success"] is True
    binding = data["data"]
    assert binding["vpc_id"] == vpc["id"]
    assert binding["tenant_id"] == tenant["id"]
    assert binding["access_vlan"] == vpc["vlan_id"]
    assert binding["status"] == "planned"


def test_create_port_binding_rejects_protected_interface(client, db):
    """受保护口不能被 VPC 绑定绕过。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db, protected="[14]")

    resp = client.post("/api/sdn/port-bindings", json={
        "device_id": dev.id,
        "vpc_id": vpc["id"],
        "if_index": 14,
        "interface_name": "GigabitEthernet1/0/14",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "interface.protected_blocked"


def test_create_port_binding_rejects_non_evpn_fabric_device(client, db):
    """名字像 Leaf 但未标记为 EVPN Fabric 成员时不能做 VPC 绑定。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db, name="Leaf-Access-01", ip="192.168.100.4", platform="LSTN", sdn_role=None)

    resp = client.post("/api/sdn/port-bindings", json={
        "device_id": dev.id,
        "vpc_id": vpc["id"],
        "if_index": 14,
        "interface_name": "GigabitEthernet1/0/14",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "common.operation_failed"
    assert "EVPN fabric" in data["error"]


def test_create_port_binding_rejects_duplicate_active_or_planned(client, db):
    """同一设备同一接口只能有一个未解绑绑定。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    payload = {
        "device_id": dev.id,
        "vpc_id": vpc["id"],
        "if_index": 14,
        "interface_name": "GigabitEthernet1/0/14",
    }
    first = client.post("/api/sdn/port-bindings", json=payload)
    assert first.json()["success"] is True

    second = client.post("/api/sdn/port-bindings", json=payload)
    data = second.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.port_binding_conflict"


def test_port_binding_deploy_and_undeploy_create_deployments(client, db):
    """绑定/解绑动作生成带 port_binding_id 的 deployment。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    binding = client.post("/api/sdn/port-bindings", json={
        "device_id": dev.id,
        "vpc_id": vpc["id"],
        "if_index": 14,
        "interface_name": "GigabitEthernet1/0/14",
        "service_instance": 1014,
    }).json()["data"]

    deploy = client.post(f"/api/sdn/port-bindings/{binding['id']}/deploy").json()["data"]
    assert deploy["action"] == "port_bind"
    assert deploy["unit"] == "port-bind"
    assert deploy["port_binding_id"] == binding["id"]
    assert json.loads(deploy["planned_config"])[0]["name"] == "port-bind"

    undeploy = client.post(f"/api/sdn/port-bindings/{binding['id']}/undeploy").json()["data"]
    assert undeploy["action"] == "port_unbind"
    assert undeploy["unit"] == "port-unbind"
    assert undeploy["port_binding_id"] == binding["id"]
    assert json.loads(undeploy["planned_config"])[0]["name"] == "port-unbind"


def test_gateway_undeploy_only_contains_vsi_l3_unit(client, db):
    """三层网关撤回只包含 Vsi-interface unit，不带 L2 VSI/EVPN。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{dev.id}/gateway/undeploy")
    data = resp.json()
    assert data["success"] is True
    deployment = data["data"]
    assert deployment["action"] == "gateway_delete"
    assert deployment["unit"] == "vsi-l3"
    units = json.loads(deployment["planned_config"])
    assert [u["name"] for u in units] == ["vsi-l3"]


def test_gateway_deploy_only_contains_vsi_l3_unit(client, db):
    """三层网关加回只包含 Vsi-interface unit，不带 L2 VSI/EVPN。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{dev.id}/gateway/deploy?auto_apply=false")
    data = resp.json()
    assert data["success"] is True
    deployment = data["data"]["deployment"]
    assert deployment["action"] == "create"
    assert deployment["unit"] == "vsi-l3"
    assert deployment["status"] == "pending"
    units = json.loads(deployment["planned_config"])
    assert [u["name"] for u in units] == ["vsi-l3"]
    text = "\n".join(units[0]["cli_commands"])
    assert "interface Vsi-interface" in text
    assert "gateway vsi-interface" in text
    assert "evpn encapsulation vxlan" not in text


def test_vpc_redeploy_creates_full_vpc_deployment(client, db):
    """单 Leaf 补回 VPC 生成完整 VPC create deployment。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/devices/{dev.id}/redeploy?auto_apply=false")
    data = resp.json()
    assert data["success"] is True
    deployment = data["data"]["deployment"]
    assert deployment["action"] == "create"
    assert deployment["unit"] == "vpc-create-all"
    assert deployment["status"] == "pending"
    units = json.loads(deployment["planned_config"])
    assert [u["name"] for u in units] == ["vsi-l2", "evpn", "l3vpn", "vsi-l3", "global"]
