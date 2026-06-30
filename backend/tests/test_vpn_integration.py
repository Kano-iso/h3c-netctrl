"""VPN 集成测试（v2.3 真实设备）

测试设备：192.168.100.5 (Leaf-04)，NETCONF 端口 830。
所有测试带 @pytest.mark.integration，默认 skip，需 --integration 显式开启。

覆盖：
- 创建 VPN instance
- 列表 VPN instance，验证新实例出现
- 接口绑定 VPN instance
- 接口解绑 VPN instance
- 删除 VPN instance
- 接口 link type 切换（access ↔ trunk）
- L3 接口设置 IPv4 地址
- L3 接口清空 IPv4 地址
"""
import os
import socket
import time

import pytest


# ==================== 设备凭据 ====================

VPN_HOST = os.getenv("INTEGRATION_VPN_HOST", "192.168.100.177")
VPN_PORT = int(os.getenv("INTEGRATION_VPN_PORT", "830"))
VPN_USERNAME = os.getenv("INTEGRATION_VPN_USERNAME", "python")
VPN_PASSWORD = os.getenv("INTEGRATION_VPN_PASSWORD", "Admin123!@#")


# ==================== 辅助函数 ====================


def _check_netconf_reachable(host: str, port: int, timeout: int = 5, retries: int = 3, retry_interval: int = 5) -> bool:
    """快速检测 NETCONF 端口 TCP 是否可达（重试 N 次，扛过设备抖动）

    177 测试机偶发丢包（实测 33% 丢包），单次 connect 不可靠。
    最多 retries 次，每次间隔 retry_interval 秒。
    """
    for i in range(retries):
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            if i > 0:
                print(f"[vpn-int] NETCONF {host}:{port} 第 {i+1} 次重试成功")
            return True
        except OSError as e:
            if i < retries - 1:
                print(f"[vpn-int] NETCONF {host}:{port} 第 {i+1} 次失败: {e}，{retry_interval}s 后重试")
                time.sleep(retry_interval)
            else:
                print(f"[vpn-int] NETCONF {host}:{port} 重试 {retries} 次仍失败: {e}")
    return False


def wait_for_ssh(host: str, port: int, username: str, password: str,
                 timeout: int = 120, interval: int = 5) -> bool:
    """等待 SSH/NETCONF 端口可达，每 interval 秒重试，最多 timeout 秒

    用于设备重启后等待服务就绪。对 NETCONF 设备检测 TCP 端口连通性。
    """
    start = time.time()
    while time.time() - start < timeout:
        if _check_netconf_reachable(host, port, timeout=5):
            return True
        time.sleep(interval)
    return False


def _create_device(client, name: str, host: str, port: int, username: str, password: str) -> dict:
    """通过 API 创建设备，返回 device dict"""
    resp = client.post("/api/devices", json={
        "name": name,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200, f"创建设备失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True, f"创建设备返回失败: {data}"
    return data["data"]


def _query_interfaces(client, device_id: int) -> list[dict]:
    """查询设备接口列表，返回接口数据列表"""
    resp = client.get(f"/api/devices/{device_id}/interfaces")
    assert resp.status_code == 200, f"查询接口失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True, f"查询接口返回失败: {data}"
    return data["data"]


def _query_vpn_instances(client, device_id: int) -> list[dict]:
    """查询设备 VPN instance 列表"""
    resp = client.get(f"/api/devices/{device_id}/vpn-instances")
    assert resp.status_code == 200, f"查询 VPN 列表失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True, f"查询 VPN 列表返回失败: {data}"
    return data["data"]["vpn_instances"]


# v2.3.1：集成测试必须避开所有"已有用途"接口，避免误改用户线上配置。
#
# 黑名单范围（v2.3 总结的真实事故案例）：
# - if_index=1  → mgmt 口（绝对不能动）
# - if_index 2-31 → GE1/0/1~30（用户接入端口，可能跑业务）
# - if_index >= 4096 → LoopBack (5123) / Vsi (5131) / Vlan-interface 等逻辑口
#   5131 (Vsi-interface2) 是 VTEP，绑着 VPN 跑 VXLAN，绝对不能解绑/改 IP
#   5123-5125 是 LoopBack，跑 VTEP ID / 路由 ID
#   其它 Vlan-interface 也常跑 SVI 业务
#
# 白名单：if_index ∈ [32, 4095] 且 name 看起来像物理口（GE/XGE/...）
SAFE_IFINDEX_MIN = 32
SAFE_IFINDEX_MAX = 4095  # 物理口 if_index 一般 < 4096
PHYS_PORT_NAME_HINTS = (
    "GigabitEthernet",
    "Ten-GigabitEthernet",
    "TwentyFiveGigE",
    "FortyGigE",
    "HundredGigE",
    "GE",  # 简写
    "XGE",  # 简写
)


def _filter_safe_ifaces(interfaces: list[dict]) -> list[dict]:
    """过滤出"安全可动"的接口：物理口 + if_index 32-4095 + 看着像物理口名"""
    result = []
    for i in interfaces:
        idx = i.get("if_index", 0)
        if idx < SAFE_IFINDEX_MIN or idx >= SAFE_IFINDEX_MAX:
            continue
        name = i.get("name", "") or ""
        if not any(h in name for h in PHYS_PORT_NAME_HINTS):
            continue
        result.append(i)
    return result


# ==================== 测试用例 ====================


@pytest.mark.integration
def test_create_vpn_instance(client):
    """创建 VPN instance，验证 API 返回 success=True，列表中出现新实例"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-VPN", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)
    vpn_name = f"test_vpn_integ_{device['id']}_{int(time.time()*1000)%100000}"  # 加 id+ts 后缀

    try:
        # 创建 VPN instance
        resp = client.post(
            f"/api/devices/{device['id']}/vpn-instances",
            json={"name": vpn_name, "rd": "100:1"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True, f"VPN 创建失败: {data}"
        assert data["data"]["name"] == vpn_name, f"VPN 名称不匹配: {data['data']}"

        # 列表验证
        vpn_list = _query_vpn_instances(client, device["id"])
        vpn_names = [v["name"] for v in vpn_list]
        assert vpn_name in vpn_names, f"新 VPN {vpn_name} 不在列表中: {vpn_names}"

        # 清理：删除 VPN instance
        del_resp = client.delete(
            f"/api/devices/{device['id']}/vpn-instances/{vpn_name}",
        )
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True, f"VPN 清理删除失败: {del_data}"
    except Exception:
        # 尽力清理
        try:
            client.delete(f"/api/devices/{device['id']}/vpn-instances/{vpn_name}")
        except Exception:
            pass
        raise


@pytest.mark.integration
def test_delete_vpn_instance(client):
    """删除 VPN instance，验证列表中不再出现"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-DelVPN", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)
    vpn_name = f"test_vpn_del_{device['id']}_{int(time.time()*1000)%100000}"  # 加 id+ts 后缀

    try:
        # 创建 VPN
        create_resp = client.post(
            f"/api/devices/{device['id']}/vpn-instances",
            json={"name": vpn_name, "rd": "100:1"},
        )
        assert create_resp.status_code == 200
        assert create_resp.json()["success"] is True

        # 删除 VPN
        del_resp = client.delete(
            f"/api/devices/{device['id']}/vpn-instances/{vpn_name}",
        )
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True, f"VPN 删除失败: {del_data}"

        # 列表验证不再出现
        vpn_list = _query_vpn_instances(client, device["id"])
        vpn_names = [v["name"] for v in vpn_list]
        assert vpn_name not in vpn_names, f"已删除的 VPN {vpn_name} 仍在列表中: {vpn_names}"
    except Exception:
        try:
            client.delete(f"/api/devices/{device['id']}/vpn-instances/{vpn_name}")
        except Exception:
            pass
        raise


@pytest.mark.integration
def test_bind_unbind_vpn(client):
    """接口绑定 VPN instance → 解绑，验证操作成功"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-BindVPN", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)
    vpn_name = f"test_vpn_bind_{device['id']}_{int(time.time()*1000)%100000}"  # 加 id+ts 后缀
    if_index = None  # 提前声明，确保 except 块可用

    try:
        # 创建 VPN instance
        create_resp = client.post(
            f"/api/devices/{device['id']}/vpn-instances",
            json={"name": vpn_name, "rd": "100:1"},
        )
        assert create_resp.status_code == 200
        assert create_resp.json()["success"] is True, f"VPN 创建失败: {create_resp.json()}"

        # 查询接口列表，找一个 L3 接口用于绑定
        interfaces = _query_interfaces(client, device["id"])
        l3_ifaces = _filter_safe_ifaces([i for i in interfaces if i.get("layer") == "L3"])
        if not l3_ifaces:
            pytest.skip("设备上没有 GE1/0/30+ 的 L3 接口，无法测试 VPN 绑定")

        # 找一个未绑定 VPN 的 L3 接口
        target_iface = None
        for iface in l3_ifaces:
            if not iface.get("vpn_instance"):
                target_iface = iface
                break
        if target_iface is None:
            # 所有 L3 接口都已绑定，取第一个
            target_iface = l3_ifaces[0]
        if_index = target_iface["if_index"]

        # 绑定 VPN 到接口
        bind_resp = client.post(
            f"/api/devices/{device['id']}/interfaces/{if_index}/vpn-instance",
            json={"name": vpn_name},
        )
        assert bind_resp.status_code == 200, bind_resp.text
        bind_data = bind_resp.json()
        assert bind_data["success"] is True, f"VPN 绑定失败: {bind_data}"

        # 解绑
        unbind_resp = client.delete(
            f"/api/devices/{device['id']}/interfaces/{if_index}/vpn-instance",
        )
        assert unbind_resp.status_code == 200, unbind_resp.text
        unbind_data = unbind_resp.json()
        assert unbind_data["success"] is True, f"VPN 解绑失败: {unbind_data}"

        # 清理：删除 VPN instance
        del_resp = client.delete(
            f"/api/devices/{device['id']}/vpn-instances/{vpn_name}",
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True, f"VPN 清理删除失败: {del_resp.json()}"
    except Exception:
        # 尽力清理
        if if_index is not None:
            try:
                client.delete(
                    f"/api/devices/{device['id']}/interfaces/{if_index}/vpn-instance",
                )
            except Exception:
                pass
        try:
            client.delete(f"/api/devices/{device['id']}/vpn-instances/{vpn_name}")
        except Exception:
            pass
        raise


@pytest.mark.integration
def test_change_link_type(client):
    """切换接口 link type（access ↔ trunk），验证 API 返回 success=True"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-LinkType", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)

    try:
        # 查询接口列表，找一个 L2 接口
        interfaces = _query_interfaces(client, device["id"])
        l2_ifaces = _filter_safe_ifaces([i for i in interfaces if i.get("layer") == "L2"])
        if not l2_ifaces:
            pytest.skip("设备上没有 GE1/0/30+ 的 L2 接口，无法测试 link type 切换")

        # 找一个 access 模式接口，切到 trunk
        target_iface = None
        new_mode = None
        for iface in l2_ifaces:
            current_mode = iface.get("mode", "access")
            if current_mode == "access":
                target_iface = iface
                new_mode = "trunk"
                break
            elif current_mode == "trunk":
                target_iface = iface
                new_mode = "access"
                break

        if target_iface is None:
            pytest.skip("没有找到可切换 link type 的 L2 接口")

        if_index = target_iface["if_index"]
        current_mode_actual = target_iface.get("mode", "access")

        # 切换 link type
        resp = client.patch(
            f"/api/devices/{device['id']}/interfaces/{if_index}/link-type",
            json={"mode": new_mode, "force": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True, f"link type 切换失败: {data}"

        # 切换回原模式
        revert_resp = client.patch(
            f"/api/devices/{device['id']}/interfaces/{if_index}/link-type",
            json={"mode": current_mode_actual, "force": True},
        )
        assert revert_resp.status_code == 200, revert_resp.text
        revert_data = revert_resp.json()
        assert revert_data["success"] is True, f"link type 还原失败: {revert_data}"
    except Exception:
        raise


@pytest.mark.integration
def test_set_ipv4_address(client):
    """给 L3 接口设置 IPv4 地址，验证 API 返回 success=True"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-IPv4", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)

    try:
        # 查询接口列表，找一个 L3 接口
        interfaces = _query_interfaces(client, device["id"])
        l3_ifaces = _filter_safe_ifaces([i for i in interfaces if i.get("layer") == "L3"])
        if not l3_ifaces:
            pytest.skip("设备上没有 GE1/0/30+ 的 L3 接口，无法测试 IPv4 地址设置")

        target_iface = l3_ifaces[0]
        if_index = target_iface["if_index"]

        # 设置 IPv4 地址（使用测试用私有地址）
        test_ip = "10.99.99.1"
        test_mask = "255.255.255.0"

        set_resp = client.post(
            f"/api/devices/{device['id']}/interfaces/{if_index}/ipv4-address",
            json={"ip": test_ip, "mask": test_mask},
        )
        assert set_resp.status_code == 200, set_resp.text
        set_data = set_resp.json()
        assert set_data["success"] is True, f"IPv4 地址设置失败: {set_data}"

        # === n → n+1 → n 还原：清掉测试 IP，恢复原状态 ===
        clear_resp = client.delete(
            f"/api/devices/{device['id']}/interfaces/{if_index}/ipv4-address",
        )
        assert clear_resp.status_code == 200, clear_resp.text
        clear_data = clear_resp.json()
        assert clear_data["success"] is True, f"IPv4 地址清理失败（还原）: {clear_data}"
    except Exception:
        raise


@pytest.mark.integration
def test_clear_ipv4_address(client):
    """清空 L3 接口的 IPv4 地址，验证 API 返回 success=True"""
    if not _check_netconf_reachable(VPN_HOST, VPN_PORT):
        pytest.skip(f"设备 {VPN_HOST}:{VPN_PORT} NETCONF 不可达")

    device = _create_device(client, "Leaf-04-ClearIP", VPN_HOST, VPN_PORT,
                            VPN_USERNAME, VPN_PASSWORD)
    if_index = None  # 提前声明，确保 except 块可用

    try:
        # 查询接口列表，找一个 L3 接口（避开 mgmt + GE1/0/1~30）
        interfaces = _query_interfaces(client, device["id"])
        l3_ifaces = _filter_safe_ifaces([i for i in interfaces if i.get("layer") == "L3"])
        if not l3_ifaces:
            pytest.skip("设备上没有 GE1/0/30+ 的 L3 接口，无法测试 IPv4 地址清空")

        target_iface = l3_ifaces[0]
        if_index = target_iface["if_index"]

        # 先设置一个 IPv4 地址
        test_ip = "10.99.99.2"
        test_mask = "255.255.255.0"

        set_resp = client.post(
            f"/api/devices/{device['id']}/interfaces/{if_index}/ipv4-address",
            json={"ip": test_ip, "mask": test_mask},
        )
        assert set_resp.status_code == 200
        set_data = set_resp.json()
        assert set_data["success"] is True, f"IPv4 地址设置失败（前置）: {set_data}"

        # 清空 IPv4 地址
        clear_resp = client.delete(
            f"/api/devices/{device['id']}/interfaces/{if_index}/ipv4-address",
        )
        assert clear_resp.status_code == 200, clear_resp.text
        clear_data = clear_resp.json()
        assert clear_data["success"] is True, f"IPv4 地址清空失败: {clear_data}"
    except Exception:
        # 尽力清理：清空 IP
        if if_index is not None:
            try:
                client.delete(
                    f"/api/devices/{device['id']}/interfaces/{if_index}/ipv4-address",
                )
            except Exception:
                pass
        raise