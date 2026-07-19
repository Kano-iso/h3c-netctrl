"""SDN/VPC Fabric 级编排 API 测试（v3.3）。"""

import json

from app.models import Device


def _create_tenant(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc(client, tenant_id, name="vpc-1", cidr="192.168.10.0/24"):
    return client.post(
        "/api/sdn/vpcs",
        json={"name": name, "tenant_id": tenant_id, "cidr": cidr},
    ).json()["data"]


def _create_device(db, name, ip, platform=None):
    dev = Device(
        name=name,
        host=ip,
        port=830,
        username="test",
        password_encrypted="encrypted",
        protected_interfaces="[]",
        platform=platform,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _create_binding(client, device_id, vpc_id, if_index=14, service_instance=1014):
    return client.post("/api/sdn/port-bindings", json={
        "device_id": device_id,
        "vpc_id": vpc_id,
        "if_index": if_index,
        "interface_name": f"GigabitEthernet1/0/{if_index}",
        "service_instance": service_instance,
    }).json()["data"]


def test_vpc_deploy_defaults_to_leaf_targets_and_port_bindings(client, db):
    """VPC deploy 默认选择 Leaf，并把已有端口绑定展开为 port_bind deployment。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    leaf_a = _create_device(db, "Leaf-04", "192.168.100.5")
    leaf_b = _create_device(db, "Leaf-05", "192.168.100.6", platform="LSTN")
    _create_device(db, "Edge-01", "192.168.100.100")
    binding = _create_binding(client, leaf_a.id, vpc["id"])

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/deploy", json={})
    data = resp.json()
    assert data["success"] is True

    result = data["data"]
    assert result["operation"] == "deploy"
    assert result["target_device_ids"] == [leaf_a.id, leaf_b.id]
    assert result["total"] == 3
    actions = [d["action"] for d in result["deployments"]]
    assert actions == ["create", "port_bind", "create"]
    port_bind = result["deployments"][1]
    assert port_bind["port_binding_id"] == binding["id"]
    assert port_bind["parent_deployment_id"] == result["deployments"][0]["id"]
    assert json.loads(port_bind["planned_config"])[0]["name"] == "port-bind"


def test_vpc_withdraw_orders_unbind_before_delete(client, db):
    """VPC withdraw 对每台设备先 port_unbind，再 delete VPC。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    leaf_a = _create_device(db, "Leaf-04", "192.168.100.5")
    leaf_b = _create_device(db, "Leaf-05", "192.168.100.6")
    binding = _create_binding(client, leaf_a.id, vpc["id"])

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/withdraw", json={})
    data = resp.json()
    assert data["success"] is True

    result = data["data"]
    assert result["operation"] == "withdraw"
    assert result["target_device_ids"] == [leaf_a.id, leaf_b.id]
    assert result["total"] == 3
    deployments = result["deployments"]
    assert [d["action"] for d in deployments] == ["port_unbind", "delete", "delete"]
    assert deployments[0]["port_binding_id"] == binding["id"]
    assert deployments[1]["parent_deployment_id"] == deployments[0]["id"]
    assert json.loads(deployments[0]["planned_config"])[0]["name"] == "port-unbind"


def test_vpc_deploy_allows_explicit_device_ids(client, db):
    """显式 device_ids 覆盖默认 Leaf 选择。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    edge = _create_device(db, "Edge-01", "192.168.100.100")

    resp = client.post(
        f"/api/sdn/vpcs/{vpc['id']}/deploy",
        json={"device_ids": [edge.id], "include_port_bindings": False},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["target_device_ids"] == [edge.id]
    assert [d["action"] for d in data["data"]["deployments"]] == ["create"]


def test_vpc_deploy_without_leaf_targets_fails(client, db):
    """默认选择没有 Leaf 候选时返回明确失败。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    _create_device(db, "Edge-01", "192.168.100.100")

    resp = client.post(f"/api/sdn/vpcs/{vpc['id']}/deploy", json={})
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "common.operation_failed"

