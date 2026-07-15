"""SDN/VPC Deployment API 测试（v3.0 sdn-vpc-deployment-api）

覆盖：POST /api/sdn/deployments + GET /api/sdn/deployments + PATCH。
需要先创建 tenant + vpc + device 才能创建 deployment。
"""
import json
import pytest

from app.models import Device


# ======================== helpers ========================

def _create_tenant(client, name="t1"):
    return client.post("/api/sdn/tenants", json={"name": name}).json()["data"]


def _create_vpc(client, tenant_id, name="vpc-1", cidr="192.168.10.0/24"):
    return client.post(
        "/api/sdn/vpcs",
        json={"name": name, "tenant_id": tenant_id, "cidr": cidr},
    ).json()["data"]


def _create_device(db, name="Leaf-04", ip="192.168.100.5"):
    """直接走 ORM 创建测试设备（绕开 NETCONF 校验）。"""
    dev = Device(
        name=name,
        host=ip,
        port=830,
        username="test",
        password_encrypted="encrypted",
        protected_interfaces="[]",
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


# ======================== POST /api/sdn/deployments ========================

def test_create_deployment_success(client, db):
    """POST 创建 deployment，自动调 planner 生成 planned_config（5 unit × 双套 payload）。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    d = data["data"]
    assert d["vpc_id"] == vpc["id"]
    assert d["device_id"] == dev.id
    assert d["action"] == "create"
    assert d["status"] == "pending"
    assert d["planned_config"] is not None

    # v3.0 sdn-vpc-netconf-schema-xml T3: planned_config 是 List[TemplateUnit]（双套 payload）
    # 5 unit × 4 字段（cli_commands / xml_payloads / undo_cli / undo_xml）
    units = json.loads(d["planned_config"])
    assert isinstance(units, list)
    assert len(units) == 5
    assert all("name" in u and "cli_commands" in u and "xml_payloads" in u for u in units)


def test_create_deployment_delete_action(client, db):
    """POST action=delete 走 plan_vpc_delete。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    resp = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "delete"},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["action"] == "delete"

    cmds = json.loads(data["data"]["planned_config"])
    assert len(cmds) > 0  # delete 命令数与 create 不同


def test_create_deployment_vpc_not_found(client, db):
    """POST 时 vpc_id 不存在 → sdn.vpc_not_found。"""
    dev = _create_device(db)
    resp = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": 999, "device_id": dev.id, "action": "create"},
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.vpc_not_found"


def test_create_deployment_device_not_found(client, db):
    """POST 时 device_id 不存在 → sdn.device_not_found。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    resp = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": 999, "action": "create"},
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.device_not_found"


def test_create_deployment_invalid_action(client, db):
    """POST 时 action 非法（pydantic pattern 校验）。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    resp = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "invalid"},
    )
    assert resp.status_code == 422  # pydantic validation


# ======================== GET /api/sdn/deployments ========================

def test_get_deployment_by_id(client, db):
    """GET /api/sdn/deployments/{id} 返回完整 deployment。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    create = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"},
    ).json()["data"]

    resp = client.get(f"/api/sdn/deployments/{create['id']}")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["id"] == create["id"]
    assert data["data"]["planned_config"] is not None


def test_get_deployment_not_found(client):
    """GET /api/sdn/deployments/999 → sdn.deployment_not_found。"""
    resp = client.get("/api/sdn/deployments/999")
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.deployment_not_found"


def test_list_deployments_filter_by_vpc(client, db):
    """GET /api/sdn/deployments?vpc_id=1 按 vpc 过滤。"""
    tenant = _create_tenant(client)
    vpc1 = _create_vpc(client, tenant["id"], name="vpc-1")
    vpc2 = _create_vpc(client, tenant["id"], name="vpc-2")
    dev = _create_device(db)

    client.post("/api/sdn/deployments", json={"vpc_id": vpc1["id"], "device_id": dev.id, "action": "create"})
    client.post("/api/sdn/deployments", json={"vpc_id": vpc2["id"], "device_id": dev.id, "action": "create"})

    resp = client.get(f"/api/sdn/deployments?vpc_id={vpc1['id']}")
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["deployments"][0]["vpc_id"] == vpc1["id"]


def test_list_deployments_filter_by_device_and_action(client, db):
    """GET /api/sdn/deployments?device_id=1&action=delete 按 device + action 过滤。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)

    client.post("/api/sdn/deployments", json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"})
    client.post("/api/sdn/deployments", json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "delete"})

    resp = client.get(f"/api/sdn/deployments?device_id={dev.id}&action=delete")
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["deployments"][0]["action"] == "delete"


# ======================== PATCH /api/sdn/deployments/{id} ========================

def test_update_deployment_status_success(client, db):
    """PATCH /api/sdn/deployments/{id} 更新 status=success。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    create = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"},
    ).json()["data"]

    resp = client.patch(
        f"/api/sdn/deployments/{create['id']}",
        json={"status": "success"},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "success"
    assert data["data"]["error"] is None


def test_update_deployment_status_failed_with_error(client, db):
    """PATCH 更新 status=failed + error 信息。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    create = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"},
    ).json()["data"]

    resp = client.patch(
        f"/api/sdn/deployments/{create['id']}",
        json={"status": "failed", "error": "device unreachable"},
    )
    data = resp.json()
    assert data["data"]["status"] == "failed"
    assert data["data"]["error"] == "device unreachable"


def test_update_deployment_invalid_status(client, db):
    """PATCH 非法 status 值被 pydantic 拒绝。"""
    tenant = _create_tenant(client)
    vpc = _create_vpc(client, tenant["id"])
    dev = _create_device(db)
    create = client.post(
        "/api/sdn/deployments",
        json={"vpc_id": vpc["id"], "device_id": dev.id, "action": "create"},
    ).json()["data"]

    resp = client.patch(
        f"/api/sdn/deployments/{create['id']}",
        json={"status": "wrong"},
    )
    assert resp.status_code == 422


def test_update_deployment_not_found(client):
    """PATCH /api/sdn/deployments/999 → sdn.deployment_not_found。"""
    resp = client.patch("/api/sdn/deployments/999", json={"status": "success"})
    data = resp.json()
    assert data["success"] is False
    assert data["error_key"] == "sdn.deployment_not_found"
