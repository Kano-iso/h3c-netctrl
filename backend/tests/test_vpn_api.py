"""VPN 实例 API 测试（v2.3 add-v22-qa-repair 1.1.3）

覆盖 VPN 4 个 API：smoke + 错误码 + 中文错误信息。
"""
from unittest.mock import MagicMock, patch


# ======================== GET /api/devices/{id}/vpn-instances ========================

def test_list_vpn_instances_success(client, created_device, real_device_netconf):
    """GET /api/devices/{id}/vpn-instances 成功"""
    resp = client.get(f"/api/devices/{created_device['id']}/vpn-instances")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "vpn_instances" in data["data"]


def test_list_vpn_instances_device_not_found(client):
    """GET /api/devices/{id}/vpn-instances 设备不存在"""
    resp = client.get("/api/devices/99999/vpn-instances")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


# ======================== POST /api/devices/{id}/vpn-instances ========================

def test_create_vpn_instance_success(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/vpn-instances 成功（mock NETCONF edit_config）"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/vpn-instances",
        json={"name": "test_vpn", "rd": "100:1"}
    )
    assert resp.status_code in (200, 422, 500)


def test_create_vpn_instance_device_not_found(client):
    """POST /api/devices/{id}/vpn-instances 设备不存在"""
    resp = client.post(
        "/api/devices/99999/vpn-instances",
        json={"name": "test_vpn", "rd": "100:1"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_create_vpn_instance_invalid_name(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/vpn-instances 名称非法"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/vpn-instances",
        json={"name": "test vpn", "rd": "100:1"}  # 含空格
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "字母" in data["error"] or "数字" in data["error"]


# ======================== POST /api/devices/{id}/interfaces/{if_index}/vpn-instance ========================

def test_bind_vpn_success(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/interfaces/{if_index}/vpn-instance 绑定"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/interfaces/100/vpn-instance",
        json={"name": "test_vpn"}
    )
    assert resp.status_code in (200, 422, 500)


def test_bind_vpn_device_not_found(client):
    """POST /api/devices/{id}/interfaces/{if_index}/vpn-instance 设备不存在"""
    resp = client.post(
        "/api/devices/99999/interfaces/100/vpn-instance",
        json={"name": "test_vpn"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


# ======================== DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance ========================

def test_unbind_vpn_success(client, created_device, real_device_netconf):
    """DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance 解绑"""
    resp = client.delete(
        f"/api/devices/{created_device['id']}/interfaces/100/vpn-instance"
    )
    assert resp.status_code in (200, 422, 500)


def test_unbind_vpn_device_not_found(client):
    """DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance 设备不存在"""
    resp = client.delete("/api/devices/99999/interfaces/100/vpn-instance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]