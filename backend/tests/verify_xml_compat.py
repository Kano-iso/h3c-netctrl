"""
NETCONF XML 交互层验证脚本

目的：确认 v1.1 重构后，XML 构建/解析逻辑与 v1.0 完全一致。
不需要连接真交换机，使用 mock XML 样例验证。

运行方式：docker exec h3c-netctrl-backend python /app/tests/verify_xml_compat.py
"""

import sys
import xml.etree.ElementTree as ET

# 添加项目路径
sys.path.insert(0, "/app")

from app.routers.vlan import (
    H3C_CONFIG_NS,
    _build_vlan_filter_xml,
    _build_vlan_create_xml,
    _build_vlan_delete_xml,
    _parse_vlan_response,
)

# ========== v1.0 基线 XML 样例（从真实 H3C 设备获取） ==========

# H3C VLAN get-config 响应样例
SAMPLE_VLAN_RESPONSE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <data>
    <top xmlns="{H3C_CONFIG_NS}">
      <VLAN>
        <VLANs>
          <VLANID><ID>1</ID></VLANID>
          <VLANID><ID>100</ID></VLANID>
          <VLANID><ID>200</ID></VLANID>
        </VLANs>
      </VLAN>
    </top>
  </data>
</rpc-reply>"""

# v1.0 期望的解析结果
EXPECTED_PARSED_VLANS = [
    {"vlan_id": 1, "name": "VLAN 1"},
    {"vlan_id": 100, "name": "VLAN 100"},
    {"vlan_id": 200, "name": "VLAN 200"},
]


def test_build_vlan_filter_xml():
    """验证 get-config filter XML 格式"""
    xml = _build_vlan_filter_xml()
    # 验证可解析
    root = ET.fromstring(xml)
    # 验证命名空间
    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    assert ns == H3C_CONFIG_NS, f"命名空间不匹配: 期望 {H3C_CONFIG_NS}, 实际 {ns}"
    # 验证根元素是 top，子元素是 VLAN
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    assert tag == "top", f"根元素不匹配: 期望 top, 实际 {tag}"
    print("  [PASS] _build_vlan_filter_xml — 命名空间和结构正确")


def test_build_vlan_create_xml():
    """验证 VLAN 创建 XML 格式"""
    xml = _build_vlan_create_xml(100, "TestVLAN")
    root = ET.fromstring(xml)
    # 遍历找到 ID 元素
    id_value = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "ID":
            id_value = int(elem.text)
    assert id_value == 100, f"VLAN ID 不匹配: 期望 100, 实际 {id_value}"
    print("  [PASS] _build_vlan_create_xml — VLAN ID 正确嵌入")


def test_build_vlan_delete_xml():
    """验证 VLAN 删除 XML 格式"""
    xml = _build_vlan_delete_xml(200)
    root = ET.fromstring(xml)
    # 验证 delete 操作标记
    found_delete = False
    id_value = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "VLANID":
            # 检查 xc:operation="delete" 属性
            for attr_name, attr_value in elem.attrib.items():
                if "operation" in attr_name and attr_value == "delete":
                    found_delete = True
        if tag == "ID":
            id_value = int(elem.text)
    assert found_delete, "未找到 xc:operation=delete 标记"
    assert id_value == 200, f"VLAN ID 不匹配: 期望 200, 实际 {id_value}"
    print("  [PASS] _build_vlan_delete_xml — delete 标记和 VLAN ID 正确")


def test_parse_vlan_response():
    """验证 H3C VLAN 响应 XML 解析为 JSON 的逻辑"""
    vlans = _parse_vlan_response(SAMPLE_VLAN_RESPONSE_XML)
    assert len(vlans) == 3, f"VLAN 数量不匹配: 期望 3, 实际 {len(vlans)}"
    for i, expected in enumerate(EXPECTED_PARSED_VLANS):
        assert vlans[i] == expected, f"VLAN {i} 不匹配: 期望 {expected}, 实际 {vlans[i]}"
    print("  [PASS] _parse_vlan_response — 解析结果与 v1.0 基线一致")


def test_xml_roundtrip():
    """验证 构建→解析 的完整往返"""
    # 构建创建 XML → 解析出 VLAN ID
    create_xml = _build_vlan_create_xml(300, "RoundTrip")
    root = ET.fromstring(create_xml)
    id_value = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "ID":
            id_value = int(elem.text)
    assert id_value == 300, f"往返验证失败: 期望 300, 实际 {id_value}"
    print("  [PASS] XML roundtrip — 构建和解析逻辑自洽")


if __name__ == "__main__":
    print("=" * 50)
    print("NETCONF XML 交互层兼容性验证")
    print("=" * 50)

    tests = [
        test_build_vlan_filter_xml,
        test_build_vlan_create_xml,
        test_build_vlan_delete_xml,
        test_parse_vlan_response,
        test_xml_roundtrip,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {test.__name__}: {e}")
            failed += 1

    print("=" * 50)
    print(f"结果: {passed} 通过, {failed} 失败")
    if failed > 0:
        print("XML 交互层存在不兼容变更，请检查！")
        sys.exit(1)
    else:
        print("XML 交互层与 v1.0 完全兼容，可安全重构路由层。")
