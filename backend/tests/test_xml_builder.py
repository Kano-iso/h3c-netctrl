"""VLAN XML 构建和解析测试"""
from app.routers.vlan import _build_vlan_filter_xml, _build_vlan_create_xml, _build_vlan_delete_xml, H3C_CONFIG_NS


def test_build_vlan_filter_xml():
    """测试 VLAN 查询 filter XML 构建"""
    xml_str = _build_vlan_filter_xml()
    assert "VLAN" in xml_str or "vlan" in xml_str.lower()


def test_build_vlan_create_xml():
    """测试 VLAN 创建 XML 构建"""
    xml_str = _build_vlan_create_xml(100, "TestVLAN")
    assert "100" in xml_str
    assert "VLAN" in xml_str


def test_build_vlan_delete_xml():
    """测试 VLAN 删除 XML 构建"""
    xml_str = _build_vlan_delete_xml(100)
    assert "100" in xml_str


def test_h3c_namespace():
    """测试 H3C 命名空间常量"""
    assert H3C_CONFIG_NS == "http://www.h3c.com/netconf/config:1.0"
