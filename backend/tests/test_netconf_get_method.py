"""v2.4-bugfix-interface-display-100 单测

覆盖 NetconfClient.get() 与 get_interfaces 路由使用 get（不是 get_config）。
"""
from unittest.mock import MagicMock, patch

from app.netconf_client import NetconfClient


# ===== NetconfClient.get() 方法 =====

def test_netconf_client_get_method_uses_get_not_get_config():
    """NetconfClient.get() 内部必须调 manager.get(filter=...) 不能调 get_config

    v2.4-bugfix-interface-display-100：H3C V7 Ifmgr / IPV4ADDRESS / L3vpn 是 operational data，
    用 get_config 拿不到全部接口。
    """
    fake_response_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<data><top xmlns="http://www.h3c.com/netconf/data:1.0">'
        '<Ifmgr><Interfaces>'
        '<Interface><IfIndex>2</IfIndex><Name>GigabitEthernet1/0/1</Name></Interface>'
        '</Interfaces></Ifmgr></top></data>'
    )
    fake_manager = MagicMock()
    fake_manager.get.return_value = MagicMock(xml=fake_response_xml)

    client = NetconfClient.__new__(NetconfClient)  # 不走 connect
    client._manager = fake_manager

    result = client.get('<top xmlns="http://www.h3c.com/netconf/data:1.0"><Ifmgr><Interfaces/></Ifmgr></top>')

    # 验证调了 get(filter=("subtree", ...)) 而不是 get_config
    assert fake_manager.get.called, "NetconfClient.get() 必须调 manager.get()"
    assert not fake_manager.get_config.called, "NetconfClient.get() 不能调 manager.get_config()"
    # 验证 filter 参数是 subtree + xml
    call_args = fake_manager.get.call_args
    assert call_args.kwargs.get("filter") is not None
    filt = call_args.kwargs["filter"]
    assert filt[0] == "subtree"
    assert "Ifmgr" in filt[1]
    # 验证返回 XML
    assert result == fake_response_xml


def test_netconf_client_get_method_raises_if_not_connected():
    """NetconfClient.get() 在未连接时必须抛 RuntimeError（防止静默失败）"""
    client = NetconfClient.__new__(NetconfClient)
    client._manager = None
    try:
        client.get("<top/>")
        assert False, "应当抛 RuntimeError"
    except RuntimeError as e:
        assert "未连接" in str(e)


# ===== get_interfaces 路由用 get 不用 get_config =====

def test_get_interfaces_uses_get_not_get_config(mock_netconf):
    """v24-bugfix-interface-display-100: get_interfaces 路由必须调 client.get() 不调 get_config

    验证：调 GET /api/devices/{id}/interfaces 后，NetconfClient.get() 被调过，
    NetconfClient.get_config() 没在 Ifmgr 路径上被调过。
    """
    # 设置 mock 返回值
    mock_netconf.get.return_value = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<data><top xmlns="http://www.h3c.com/netconf/data:1.0">'
        '<Ifmgr><Interfaces>'
        '<Interface><IfIndex>2</IfIndex><Name>GigabitEthernet1/0/1</Name>'
        '<AdminStatus>1</AdminStatus><PortLayer>1</PortLayer></Interface>'
        '<Interface><IfIndex>3</IfIndex><Name>GigabitEthernet1/0/2</Name>'
        '<AdminStatus>1</AdminStatus><PortLayer>1</PortLayer></Interface>'
        '</Interfaces></Ifmgr>'
        '<IPV4ADDRESS></IPV4ADDRESS>'
        '<L3vpn></L3vpn>'
        '</top></data>'
    )

    from fastapi.testclient import TestClient
    from app.main import app
    tc = TestClient(app)
    resp = tc.post("/api/devices", json={
        "name": "test-get-iface",
        "host": "192.168.100.100",
        "port": 830,
        "username": "admin",
        "password": "TestPass123!",
    })
    assert resp.status_code == 200, resp.text
    device_id = resp.json()["data"]["id"]

    resp = tc.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, f"接口查询失败: {body.get('error')}"
    assert len(body["data"]) >= 2, "应至少返回 2 个接口"

    # 验证：NetconfClient.get() 被调过（拿 Ifmgr / IPV4ADDRESS / L3vpn）
    assert mock_netconf.get.called, "get_interfaces 必须调 NetconfClient.get()（NETCONF get 操作）"
    # 验证 get 的 filter 含 data namespace + Ifmgr + L3vpn
    get_calls = mock_netconf.get.call_args_list
    ifmgr_get = None
    for call in get_calls:
        # mock fixture 直接给 mock_instance.get 设 side_effect，
        # 所以 call 拿到的就是 router 传的 raw filter XML（不走真 method 的 filter=("subtree", xml) 包装）
        filt = call.kwargs.get("filter")
        if filt is None and call.args:
            filt = call.args[0]
        if isinstance(filt, str) and "Ifmgr" in filt:
            ifmgr_get = filt
            break
    assert ifmgr_get is not None, f"必须有 get(Ifmgr filter) 调用，实际: {get_calls}"
    assert "data:1.0" in ifmgr_get, f"必须用 data namespace，got: {ifmgr_get[:200]}"


def test_get_interfaces_includes_l3vpn_filter(mock_netconf):
    """v2.4-bugfix-interface-display-100: 接口查询 filter 必须含 L3vpn（VPN 绑定信息）"""
    from fastapi.testclient import TestClient
    from app.main import app

    mock_netconf.get.return_value = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<data><top xmlns="http://www.h3c.com/netconf/data:1.0">'
        '<Ifmgr><Interfaces></Interfaces></Ifmgr>'
        '<IPV4ADDRESS></IPV4ADDRESS>'
        '<L3vpn></L3vpn></top></data>'
    )

    tc = TestClient(app)
    resp = tc.post("/api/devices", json={
        "name": "test-l3vpn",
        "host": "192.168.100.100",
        "port": 830,
        "username": "admin",
        "password": "TestPass123!",
    })
    device_id = resp.json()["data"]["id"]

    resp = tc.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True, f"接口查询失败: {resp.json().get('error')}"

    # 验证：filter 含 L3vpn
    for call in mock_netconf.get.call_args_list:
        filt = call.kwargs.get("filter")
        if filt is None and call.args:
            filt = call.args[0]
        if isinstance(filt, str) and "Ifmgr" in filt:
            assert "L3vpn" in filt, f"filter 必须含 L3vpn，got: {filt[:200]}"
            return
    assert False, f"没找到 Ifmgr get 调用，actual calls: {mock_netconf.get.call_args_list}"


def test_get_interfaces_status_uses_oper_status(mock_netconf):
    """v2.4-bugfix-interface-display-100 + v24-bugfix-status-mapping: status 字段必须用 OperStatus（链路层）覆盖 AdminStatus

    H3C V7 AdminStatus=1（没 shutdown）+ OperStatus=2（link down，IF-MIB RFC 2863）= 实际 down。
    早期实现只看 AdminStatus，把 link down 的接口错标成 "up"。
    v2.4-bugfix-interface-display-100 引入 OperStatus 概念但编码写反。
    v24-bugfix-status-mapping 修正编码为 1=UP 2=DOWN。
    """
    from fastapi.testclient import TestClient
    from app.main import app

    # 模拟 link-down 接口：AdminStatus=1（没 shutdown）但 OperStatus=2（link down，RFC 2863）
    mock_netconf.get.return_value = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<data><top xmlns="http://www.h3c.com/netconf/data:1.0">'
        '<Ifmgr><Interfaces>'
        '<Interface><IfIndex>2</IfIndex><Name>GigabitEthernet1/0/1</Name>'
        '<AdminStatus>1</AdminStatus><OperStatus>2</OperStatus><PortLayer>1</PortLayer></Interface>'
        '<Interface><IfIndex>3</IfIndex><Name>NULL0</Name>'
        '<AdminStatus>1</AdminStatus><OperStatus>1</OperStatus><PortLayer>2</PortLayer></Interface>'
        '</Interfaces></Ifmgr>'
        '<IPV4ADDRESS></IPV4ADDRESS>'
        '<L3vpn></L3vpn>'
        '</top></data>'
    )

    tc = TestClient(app)
    resp = tc.post("/api/devices", json={
        "name": "test-status",
        "host": "192.168.100.100",
        "port": 830,
        "username": "admin",
        "password": "TestPass123!",
    })
    device_id = resp.json()["data"]["id"]

    resp = tc.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, f"接口查询失败: {body.get('error')}"
    ifs = body["data"]
    assert len(ifs) == 2, f"应返回 2 个接口，实际 {len(ifs)}"

    by_idx = {i["if_index"]: i for i in ifs}
    # GigabitEthernet1/0/1: AdminStatus=1, OperStatus=2 (DOWN, RFC 2863) → status="down"
    assert by_idx[2]["status"] == "down", f"if_index=2 应 down，实际: {by_idx[2]}"
    assert by_idx[2]["admin_status"] == "up"
    assert by_idx[2]["oper_status"] == "down"
    # NULL0: AdminStatus=1, OperStatus=1 (UP, RFC 2863) → status="up"
    assert by_idx[3]["status"] == "up", f"if_index=3 NULL0 link up 应为 up，实际: {by_idx[3]}"
    assert by_idx[3]["admin_status"] == "up"
    assert by_idx[3]["oper_status"] == "up"
