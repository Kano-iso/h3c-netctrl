"""v24-bugfix-ui-feedback-and-loopback 单测

覆盖 _detect_layer description 弱匹配兜底（修复 Loopback name 兜底成
Description 时被错判 L2 的 bug）。
"""
from app.routers.interface import _detect_layer


def test_detect_layer_with_description_loopback_fallback():
    """v24-bugfix 修复：name="Loopback_VTEP_ID"（H3C Ifmgr Description 兜底）→ L3

    场景：H3C V7 Ifmgr 对 Loopback 接口不返回 Name 字段，name 兜底成 Description
    (e.g. "Loopback_VTEP_ID")。L3_NAME_PATTERN 严格匹配 LoopBack\\d+ 不命中，
    弱匹配必须兜底成 L3。
    """
    iface = {"if_index": 5123, "name": "Loopback_VTEP_ID"}
    assert _detect_layer(iface, [], None) == "L3"


def test_detect_layer_with_description_vsi_fallback():
    """v24-bugfix 修复：name="VSI_TUNNEL_2"（H3C Ifmgr Description 兜底）→ L3"""
    iface = {"if_index": 5124, "name": "VSI_TUNNEL_2"}
    assert _detect_layer(iface, [], None) == "L3"


def test_detect_layer_with_description_vlan_fallback():
    """v24-bugfix 修复：name="Vlan_interface10"（H3C Ifmgr Description 兜底）→ L3

    注意：用户下划线命名（Vlan_interface10）也能识别，弱匹配宽松。
    """
    iface = {"if_index": 5125, "name": "Vlan_interface10"}
    assert _detect_layer(iface, [], None) == "L3"


def test_detect_layer_physical_port_description_safe():
    """v24-bugfix 安全：name="Uplink_to_Spine"（物理口 Description）→ L2

    关键回归：弱匹配不能误判物理口。H3C 物理口常见 Description 含 "to"/"uplink"，
    不应误判 L3。
    """
    iface = {"if_index": 2, "name": "Uplink_to_Spine"}
    assert _detect_layer(iface, [], None) == "L2"


def test_detect_layer_existing_strict_pattern_still_works():
    """回归：v2.3 B11 严格匹配（LoopBack0 / Vsi-interface2 / Vlan-interface10）继续工作"""
    assert _detect_layer({"if_index": 5123, "name": "LoopBack0"}, [], None) == "L3"
    assert _detect_layer({"if_index": 5124, "name": "Vsi-interface2"}, [], None) == "L3"
    assert _detect_layer({"if_index": 5125, "name": "Vlan-interface10"}, [], None) == "L3"


def test_detect_layer_port_layer_takes_priority_over_weak_match():
    """回归：PortLayer 字段优先级最高，不被弱匹配覆盖

    万一 H3C 设备错误地把物理口的 PortLayer 标成 1，但 name 含 "loopback" 字样，
    弱匹配不能盖过 PortLayer=1（L2）的权威。
    """
    iface = {"if_index": 99, "name": "Something_Loopback_Test", "port_layer": 1}
    assert _detect_layer(iface, [], None) == "L2"


def test_detect_layer_ip_address_overrides_weak_match():
    """回归：IP 地址优先级最高

    即使 name 不含弱匹配关键字，有 IP 地址就是 L3。
    """
    iface = {"if_index": 99, "name": "GigabitEthernet1/0/1"}
    assert _detect_layer(iface, ["192.168.1.1/24"], None) == "L3"


def test_detect_layer_vpn_instance_overrides_weak_match():
    """回归：VPN 绑定优先级最高

    即使 name 是物理口命名但绑了 VPN → L3。
    """
    iface = {"if_index": 99, "name": "GigabitEthernet1/0/1"}
    assert _detect_layer(iface, [], "mgt") == "L3"


def test_detect_layer_empty_name_defaults_l2():
    """边界：name 为空 → L2（弱匹配也不命中）"""
    assert _detect_layer({"if_index": 99, "name": ""}, [], None) == "L2"
    assert _detect_layer({"if_index": 99, "name": None}, [], None) == "L2"
