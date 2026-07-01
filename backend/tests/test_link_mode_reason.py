"""v24-bugfix-ui-feedback-and-loopback link-mode reason_code 单测

覆盖 link-mode 护栏拒时返回的 reason_code + suggested_action 字段。
"""
import json


def test_link_mode_l3_interface_reason_code(client, created_device, mock_netconf):
    """v24-bugfix: 改 Loopback L3 类型 → success=False, reason_code=L3_INTERFACE

    场景：用户点 LoopBack0 改 link-mode（应被护栏拒并给明确 reason_code）
    """
    # mock NetconfClient.get_interface_name_by_index 返回 "LoopBack0"
    mock_netconf.get_interface_name_by_index.return_value = "LoopBack0"
    # mock get_config（VPN 路由不调用，但 mock 已有默认 side_effect）

    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/5128/link-mode",
        json={"mode": "bridge", "force": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "LoopBack0" in body["error"] or "L3" in body["error"]

    # 关键断言：reason_code + suggested_action 在 data 里
    assert body["data"] is not None
    assert body["data"]["reason_code"] == "L3_INTERFACE"
    assert "虚接口" in body["data"]["suggested_action"] or "L3" in body["data"]["suggested_action"]


def test_link_mode_non_physical_port_reason_code(client, created_device, mock_netconf):
    """v24-bugfix: 改非物理口（自定义 name）→ reason_code=PHYSICAL_ONLY

    场景：H3C V7 自定义 Description（如 "Custom_Port_99"）既不匹配 L3_NAME_PATTERN
    也不匹配 _looks_like_physical_port，应被护栏拒并给 PHYSICAL_ONLY reason_code
    """
    # 自定义 name：不匹配 L3_NAME_PATTERN（不是 LoopBack/Vsi/Vlan）也不匹配物理口正则
    mock_netconf.get_interface_name_by_index.return_value = "Custom_Port_99"

    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/5130/link-mode",
        json={"mode": "bridge", "force": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False

    # 关键断言：reason_code=PHYSICAL_ONLY
    assert body["data"] is not None
    assert body["data"]["reason_code"] == "PHYSICAL_ONLY"
    assert "物理口" in body["data"]["suggested_action"]


def test_link_mode_physical_port_success_no_reason_code(client, created_device, mock_netconf):
    """v24-bugfix: 物理口 force=false 二次确认 → success=True, no reason_code

    场景：用户点物理口（如 GigabitEthernet1/0/1）改 link-mode，二次确认流程走通
    此时 success=True，data 是确认提示，**无** reason_code 字段（或为 None）
    注：created_device 的 protected_interfaces=[2]，所以必须用非保护口（如 100）触发物理口分支
    """
    mock_netconf.get_interface_name_by_index.return_value = "GigabitEthernet1/0/1"

    resp = client.patch(
        f"/api/devices/{created_device['id']}/interfaces/100/link-mode",
        json={"mode": "bridge", "force": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["confirmed"] is False  # 二次确认提示
    assert "force=true" in body["data"]["message"]
    # 二次确认时不应有 reason_code
    assert body["data"].get("reason_code") is None


def test_link_mode_protected_interface_reason_code(client, db):
    """v24-bugfix: 受保护接口 → reason_code=PROTECTED_INTERFACE

    场景：设备 protected_interfaces 含 2，点 if_index=2 改 link-mode（force=false）
    应被护栏拒并给 PROTECTED reason_code
    """
    from app.models import Device
    from app.utils.crypto import encrypt_password
    # 创建带 protected 的设备
    device = Device(
        name="Protected-Device",
        host="192.168.100.100",
        port=830,
        username="admin",
        password_encrypted=encrypt_password("TestPass123!"),
        protected_interfaces=json.dumps([2]),  # 保护 if_index=2
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    resp = client.patch(
        f"/api/devices/{device.id}/interfaces/2/link-mode",
        json={"mode": "bridge", "force": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "受保护" in body["error"]

    # 关键断言：reason_code=PROTECTED_INTERFACE
    assert body["data"] is not None
    assert body["data"]["reason_code"] == "PROTECTED_INTERFACE"
    assert "保护" in body["data"]["suggested_action"] or "force=true" in body["data"]["suggested_action"]
