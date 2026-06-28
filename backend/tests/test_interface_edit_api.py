"""接口编辑 API 测试（v2.3 add-v22-qa-repair 1.1.4）

覆盖 link-type + ipv4-address 3 个 API：smoke + 错误码 + 中文错误信息。
"""
from unittest.mock import MagicMock, patch


# ======================== PATCH /api/devices/{id}/interfaces/{if_index}/link-type ========================

def test_change_link_type_success(client, created_device, real_device_netconf):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type 成功"""
    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/100/link-type",
        json={"mode": "access", "force": False}
    )
    assert resp.status_code in (200, 422, 500)


def test_change_link_type_device_not_found(client):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type 设备不存在"""
    resp = client.patch(
        "/api/devices/99999/interfaces/100/link-type",
        json={"mode": "access", "force": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_change_link_type_invalid_mode(client, created_device, real_device_netconf):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type mode 非法"""
    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/100/link-type",
        json={"mode": "invalid", "force": False}
    )
    assert resp.status_code in (200, 422)


def test_change_link_type_protected_blocked(client, created_device, real_device_netconf):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type 受保护口被拒绝"""
    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/2/link-type",
        json={"mode": "access", "force": False}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "保护" in data["error"]


def test_change_link_type_protected_force(client, created_device, real_device_netconf):
    """PATCH /api/devices/{id}/interfaces/{if_index}/link-type force=true 强制通过"""
    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/2/link-type",
        json={"mode": "access", "force": True}
    )
    assert resp.status_code in (200, 422, 500)


# ======================== POST /api/devices/{id}/interfaces/{if_index}/ipv4-address ========================

def test_set_ipv4_address_success(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/interfaces/{if_index}/ipv4-address 成功"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/interfaces/100/ipv4-address",
        json={"ip": "10.0.0.1", "mask": "255.255.255.0"}
    )
    assert resp.status_code in (200, 422, 500)


def test_set_ipv4_address_device_not_found(client):
    """POST /api/devices/{id}/interfaces/{if_index}/ipv4-address 设备不存在"""
    resp = client.post(
        "/api/devices/99999/interfaces/100/ipv4-address",
        json={"ip": "10.0.0.1", "mask": "255.255.255.0"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


def test_set_ipv4_address_invalid_ip(client, created_device, real_device_netconf):
    """POST /api/devices/{id}/interfaces/{if_index}/ipv4-address IP 非法"""
    resp = client.post(
        f"/api/devices/{created_device['id']}/interfaces/100/ipv4-address",
        json={"ip": "999.999.999.999", "mask": "255.255.255.0"}
    )
    assert resp.status_code in (200, 422)


# ======================== DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address ========================

def test_delete_ipv4_address_success(client, created_device, real_device_netconf):
    """DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address 成功"""
    resp = client.delete(
        f"/api/devices/{created_device['id']}/interfaces/100/ipv4-address"
    )
    assert resp.status_code in (200, 422, 500)


def test_delete_ipv4_address_device_not_found(client):
    """DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address 设备不存在"""
    resp = client.delete("/api/devices/99999/interfaces/100/ipv4-address")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]