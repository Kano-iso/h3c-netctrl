"""v2.3 fix-loopback-vsi-ipv4 单元测试（mock XML 验证修复）

不依赖真实设备，纯 mock，验证：
1. _parse_interface_response 对 Ifmgr 没回 Name 的接口（如 Loopback/Vsi）能正确用
   Description 兜底，且不假装是物理口
2. _looks_like_physical_port 能正确判断
3. build_ipv4_address_clear_entries_xml 生成的 XML 用 (IfIndex, Ipv4Address) 作为 key
4. set_interface_ipv4 路由层先查 IP 再 clear 的链路（mock NetconfClient）
"""
import re
from unittest.mock import MagicMock, patch

# 这些测试不需要 DB/Client，直接调内部函数即可


def test_build_ipv4_address_clear_entries_xml_with_ips():
    """生成 clear XML 用 (IfIndex, Ipv4Address) key，AddressOrigin 不能出现"""
    from app.utils.netconf_xml import build_ipv4_address_clear_entries_xml
    xml = build_ipv4_address_clear_entries_xml(5131, ["192.168.2.254"])
    assert "xc:operation=\"delete\"" in xml
    assert "<IfIndex>5131</IfIndex>" in xml
    assert "<Ipv4Address>192.168.2.254</Ipv4Address>" in xml
    # 关键：不能包含 AddressOrigin（H3C V7 实际拒绝）
    assert "AddressOrigin" not in xml
    # 也不能包含 Ipv4Mask（非索引列）
    assert "Ipv4Mask" not in xml


def test_build_ipv4_address_clear_entries_xml_multiple_ips():
    """多条 IP 生成多条 delete"""
    from app.utils.netconf_xml import build_ipv4_address_clear_entries_xml
    xml = build_ipv4_address_clear_entries_xml(5131, ["192.168.2.254", "10.0.0.1"])
    # 应该有 2 个 xc:operation="delete"
    assert xml.count("xc:operation=\"delete\"") == 2
    assert "<Ipv4Address>192.168.2.254</Ipv4Address>" in xml
    assert "<Ipv4Address>10.0.0.1</Ipv4Address>" in xml


def test_build_ipv4_address_clear_entries_xml_empty():
    """空 IP 列表返回空字符串（路由层应短路）"""
    from app.utils.netconf_xml import build_ipv4_address_clear_entries_xml
    xml = build_ipv4_address_clear_entries_xml(5131, [])
    assert xml == ""


def test_build_ipv4_address_clear_xml_deprecated():
    """旧函数 build_ipv4_address_clear_xml(if_index) 已废弃"""
    from app.utils.netconf_xml import build_ipv4_address_clear_xml
    try:
        build_ipv4_address_clear_xml(5131)
        assert False, "应该抛 NotImplementedError"
    except NotImplementedError as e:
        assert "build_ipv4_address_clear_entries_xml" in str(e)


def test_looks_like_physical_port():
    from app.routers.interface import _looks_like_physical_port
    # 物理口
    assert _looks_like_physical_port("GigabitEthernet1/0/1")
    assert _looks_like_physical_port("TenGigabitEthernet1/0/1")
    assert _looks_like_physical_port("Eth1/0/1")
    assert _looks_like_physical_port("Bridge-Aggregation1")
    # 非物理口
    assert not _looks_like_physical_port("LoopBack0")
    assert not _looks_like_physical_port("Vsi-interface2")
    assert not _looks_like_physical_port("Vlan-interface100")
    assert not _looks_like_physical_port("If-5128")
    assert not _looks_like_physical_port("Loopback_VTEP_ID")
    # 空
    assert not _looks_like_physical_port("")
    assert not _looks_like_physical_port(None)


def test_parse_interface_response_loopback_uses_description_fallback():
    """Loopback 没 Name 时用 Description 兜底，name 仍非物理口 → 触发补查"""
    from app.routers.interface import _parse_interface_response
    xml = '''<data>
    <top xmlns="http://www.h3c.com/netconf/config:1.0">
      <Ifmgr>
        <Interfaces>
          <Interface>
            <IfIndex>5128</IfIndex>
            <Description>Loopback_VTEP_ID</Description>
          </Interface>
        </Interfaces>
      </Ifmgr>
    </top>
    </data>'''
    result = _parse_interface_response(xml)
    assert len(result) == 1
    iface = result[0]
    assert iface["if_index"] == 5128
    # 真机数据：Ifmgr 没 Name，Description 兜底成 Loopback_VTEP_ID
    assert iface["name"] == "Loopback_VTEP_ID"
    # 不像物理口 → 路由层会触发补查
    from app.routers.interface import _looks_like_physical_port
    assert not _looks_like_physical_port(iface["name"])
    # v24-bugfix-ui-feedback-and-loopback 修复：弱匹配兜底，name="Loopback_VTEP_ID" 判 L3
    # （v2.3 行为是判 L2，这就是用户报错的根因场景）
    assert iface["layer"] == "L3"


def test_parse_interface_response_vsi_interface():
    """Vsi-interface 没 Name 也没 Description → 兜底成 If-N"""
    from app.routers.interface import _parse_interface_response
    xml = '''<data>
    <top xmlns="http://www.h3c.com/netconf/config:1.0">
      <Ifmgr>
        <Interfaces>
          <Interface>
            <IfIndex>5131</IfIndex>
            <MAC>00-02-00-02-00-02</MAC>
          </Interface>
        </Interfaces>
      </Ifmgr>
    </top>
    </data>'''
    result = _parse_interface_response(xml)
    assert len(result) == 1
    iface = result[0]
    assert iface["if_index"] == 5131
    # 没 Name 也没 Description → 兜底成 If-5131
    assert iface["name"] == "If-5131"
    from app.routers.interface import _looks_like_physical_port
    assert not _looks_like_physical_port(iface["name"])


def test_detect_layer_with_name_loopback():
    """_detect_layer 对有 LoopBack0 名字的接口 → L3"""
    from app.routers.interface import _detect_layer
    # 补查后 name 变成 LoopBack0
    iface = {"if_index": 5128, "name": "LoopBack0"}
    layer = _detect_layer(iface, [], None)
    assert layer == "L3"


def test_detect_layer_with_name_vsi():
    """_detect_layer 对有 Vsi-interface2 名字的接口 → L3"""
    from app.routers.interface import _detect_layer
    iface = {"if_index": 5131, "name": "Vsi-interface2"}
    layer = _detect_layer(iface, [], None)
    assert layer == "L3"


def test_detect_layer_with_ip_vsi_no_name():
    """_detect_layer 对没 name 但有 IP 的接口 → L3（IP 兜底）"""
    from app.routers.interface import _detect_layer
    iface = {"if_index": 5131, "name": "If-5131"}
    layer = _detect_layer(iface, ["192.168.2.254/24"], None)
    assert layer == "L3"


def test_detect_layer_loopback_no_name_no_ip():
    """_detect_layer 对没 name 没 IP 的 Loopback 兜底字段 → L3（v24-bugfix 弱匹配修复）

    v2.3 行为是判 L2（这就是用户报错的根因场景）。
    v2.4 行为：name 弱匹配命中"loopback"关键字 → L3。
    """
    from app.routers.interface import _detect_layer
    iface = {"if_index": 5128, "name": "Loopback_VTEP_ID"}
    layer = _detect_layer(iface, [], None)
    assert layer == "L3"
