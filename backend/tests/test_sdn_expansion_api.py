"""SDN/VPC 既有 VPC 扩容 API 测试（v3.3）。"""

import json
from unittest.mock import patch

from app.models import Device, SdnDeployment, SdnPortBinding, SdnValidationSnapshot


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


def _create_device(db, name="Leaf-04", ip="192.168.100.5", platform="LSTN"):
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


def _mark_deployment_success(db, deployment_id):
    deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
    deployment.status = "success"
    deployment.error = None
    db.commit()
    db.refresh(deployment)
    return deployment


def test_start_vpc_expansion_requires_leaf_device(client, db):
    """扩容只能选择 Leaf 设备。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    edge = _create_device(db, name="Edge-01", ip="192.168.100.100", platform=None)

    resp = client.post(
        f"/api/sdn/vpcs/{vpc['id']}/expansions",
        json={
            "device_id": edge.id,
            "if_index": 2,
            "interface_name": "GigabitEthernet1/0/2",
            "service_instance": 3200,
        },
    )

    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "common.operation_failed"


def test_start_vpc_expansion_applies_binding_and_enters_expanding(client, db):
    """开始扩容会创建绑定、下发 port_bind，并进入 expanding。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    leaf = _create_device(db)

    with patch(
        "app.services.sdn_deployment_executor.SdnDeploymentExecutor.execute",
        side_effect=lambda db_arg, deployment_id: _mark_deployment_success(db_arg, deployment_id),
    ):
        resp = client.post(
            f"/api/sdn/vpcs/{vpc['id']}/expansions",
            json={
                "device_id": leaf.id,
                "if_index": 2,
                "interface_name": "GigabitEthernet1/0/2",
                "service_instance": 3200,
                "expected_host_ip": "192.168.2.2",
            },
        )

    data = resp.json()
    assert data["success"] is True
    body = data["data"]
    assert body["binding"]["status"] == "expanding"
    assert body["vpc"]["status"] == "expanding"
    assert body["deployment"]["action"] == "port_bind"
    assert json.loads(body["deployment"]["planned_config"])[0]["name"] == "port-bind"
    assert body["expected_host_ip"] == "192.168.2.2"


def test_complete_vpc_expansion_ping_and_validation_success(client, db):
    """扩容完成时 ping + display 校验都成功后转 active。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    leaf = _create_device(db)
    binding = SdnPortBinding(
        device_id=leaf.id,
        tenant_id=tenant["id"],
        vpc_id=vpc["id"],
        if_index=2,
        interface_name="GigabitEthernet1/0/2",
        service_instance=3200,
        status="expanding",
    )
    snapshot = SdnValidationSnapshot(
        vpc_id=vpc["id"],
        device_id=leaf.id,
        snapshot_data=json.dumps({"commands": {}}),
        validation_result="active",
        validation_details=json.dumps({"type2_present": {"ok": True, "required": True}}),
    )
    db.add(binding)
    db.add(snapshot)
    db.commit()
    db.refresh(binding)
    db.refresh(snapshot)

    with patch(
        "app.routers.sdn._ping_from_vpc_gateway",
        return_value=({"success": True, "command": "ping ...", "output": "0.0% packet loss"}, None),
    ), patch(
        "app.services.sdn_validation_collector.SdnValidationCollector.sync",
        return_value=(snapshot, None, False),
    ):
        resp = client.post(
            f"/api/sdn/vpcs/{vpc['id']}/expansions/{binding.id}/complete",
            json={"expected_host_ip": "192.168.2.2"},
        )

    data = resp.json()
    assert data["success"] is True
    body = data["data"]
    assert body["success"] is True
    assert body["binding"]["status"] == "active"
    assert body["vpc"]["status"] == "active"
    assert body["ping"]["success"] is True
    assert body["validation"]["validation_result"] == "active"


def test_complete_vpc_expansion_ping_failure_marks_degraded(client, db):
    """ping 失败时扩容完成返回失败并标记 degraded。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    leaf = _create_device(db)
    binding = SdnPortBinding(
        device_id=leaf.id,
        tenant_id=tenant["id"],
        vpc_id=vpc["id"],
        if_index=2,
        interface_name="GigabitEthernet1/0/2",
        service_instance=3200,
        status="expanding",
    )
    snapshot = SdnValidationSnapshot(
        vpc_id=vpc["id"],
        device_id=leaf.id,
        snapshot_data=json.dumps({"commands": {}}),
        validation_result="active",
        validation_details=json.dumps({}),
    )
    db.add(binding)
    db.add(snapshot)
    db.commit()
    db.refresh(binding)
    db.refresh(snapshot)

    with patch(
        "app.routers.sdn._ping_from_vpc_gateway",
        return_value=({"success": False, "command": "ping ...", "output": "100.0% packet loss"}, None),
    ), patch(
        "app.services.sdn_validation_collector.SdnValidationCollector.sync",
        return_value=(snapshot, None, False),
    ):
        resp = client.post(
            f"/api/sdn/vpcs/{vpc['id']}/expansions/{binding.id}/complete",
            json={"expected_host_ip": "192.168.2.2"},
        )

    body = resp.json()["data"]
    assert body["success"] is False
    assert body["binding"]["status"] == "failed"
    assert body["vpc"]["status"] == "degraded"
