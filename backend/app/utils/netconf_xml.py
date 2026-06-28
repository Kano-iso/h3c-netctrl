"""NETCONF XML 构造器（v2.2）

封装 H3C V7 设备 NETCONF 模型相关 XML 的构造，避免散落在各路由中。

- VPN instance (`Ipv4Vrf` / `VRF`) 创建 / 删除
- 接口绑 / 解绑 VPN instance (`IpBindVrfInstance`)
- 接口扩展字段 filter（`Ipv4Address` 等）

**注意**：H3C V7 实际命名空间 / 字段名以设备探测为准，注释中标注
"待探测"的字段在实施时需要在 192.168.100.4 上验证。
如 NETCONF 模型不被设备接受，应 fallback 到 SSH CLI 实现（见 design.md）。
"""
import xml.etree.ElementTree as ET
from typing import Optional

# H3C NETCONF 配置命名空间（与 vlan.py / interface.py 一致）
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"
# NETCONF base 1.0 命名空间（xc:operation="delete" 等用）
NETCONF_BASE_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"


# ============ VPN instance ============


def build_vpn_instance_filter_xml() -> str:
    """构造查询 VPN instance 的 get-config filter

    H3C 模型：`<Ipv4Vrf><VRF>...所有实例...</VRF></Ipv4Vrf>`
    """
    return f'<top xmlns="{H3C_CONFIG_NS}"><Ipv4Vrf></Ipv4Vrf></top>'


def build_vpn_instance_create_xml(name: str, rd: str = "auto") -> str:
    """构造创建 VPN instance 的 edit-config XML

    Args:
        name: VPN instance 名（如 "MGMT"）
        rd: route-distinguisher，默认 "auto"（设备自动分配）

    H3C 模型（待探测）:
        <top>
          <Ipv4Vrf>
            <VRF>
              <Name>{name}</Name>
              <DefaultRD>{rd}</DefaultRD>
            </VRF>
          </Ipv4Vrf>
        </top>
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <Ipv4Vrf>
                <VRF>
                    <Name>{name}</Name>
                    <DefaultRD>{rd}</DefaultRD>
                </VRF>
            </Ipv4Vrf>
        </top>
    </config>
    """


def build_vpn_instance_delete_xml(name: str) -> str:
    """构造删除 VPN instance 的 edit-config XML（用 xc:operation="delete"）"""
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <Ipv4Vrf>
                <VRF xmlns:xc="{NETCONF_BASE_NS}">
                    <Name xc:operation="delete">{name}</Name>
                </VRF>
            </Ipv4Vrf>
        </top>
    </config>
    """


# ============ 接口绑 VPN instance ============


def build_interface_bind_vpn_xml(if_index: int, vpn_name: str) -> str:
    """构造接口绑 VPN instance 的 edit-config XML

    Args:
        if_index: 接口 if_index（NETCONF 索引）
        vpn_name: VPN instance 名

    H3C 模型（待探测）:
        <Ifmgr>
          <Interfaces>
            <Interface>
              <IfIndex>{if_index}</IfIndex>
              <IpBindVrfInstance>{vpn_name}</IpBindVrfInstance>
            </Interface>
          </Interfaces>
        </Ifmgr>
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <Ifmgr>
                <Interfaces>
                    <Interface>
                        <IfIndex>{if_index}</IfIndex>
                        <IpBindVrfInstance>{vpn_name}</IpBindVrfInstance>
                    </Interface>
                </Interfaces>
            </Ifmgr>
        </top>
    </config>
    """


def build_interface_unbind_vpn_xml(if_index: int) -> str:
    """构造接口解绑 VPN instance 的 edit-config XML"""
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <Ifmgr>
                <Interfaces>
                    <Interface xmlns:xc="{NETCONF_BASE_NS}">
                        <IfIndex>{if_index}</IfIndex>
                        <IpBindVrfInstance xc:operation="delete"></IpBindVrfInstance>
                    </Interface>
                </Interfaces>
            </Ifmgr>
        </top>
    </config>
    """


# ============ 接口扩展 filter（IP 地址 + VPN instance 绑定）============


def build_interface_extended_filter_xml() -> str:
    """构造查询接口扩展字段的 get-config filter

    在原 Ifmgr/Interfaces filter 基础上不需特殊处理（get-config 子树
    会返回所有匹配字段，包括 Ipv4Address / IpBindVrfInstance）。
    保留独立函数以便未来按需裁剪。
    """
    return f'<top xmlns="{H3C_CONFIG_NS}"><Ifmgr><Interfaces/></Ifmgr></top>'


# ============ XML 解析辅助 ============


def parse_vpn_instances(xml_str: str) -> list[dict]:
    """解析 VPN instance get-config 响应

    预期响应（待 192.168.100.4 探测）:
        <Ipv4Vrf>
          <VRF>
            <Name>MGMT</Name>
            <DefaultRD>auto</DefaultRD>
          </VRF>
        </Ipv4Vrf>

    Returns:
        [{"name": "MGMT", "rd": "auto"}, ...]
    """
    results = []
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "VRF":
                vrf = {"name": None, "rd": None}
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "Name" and child.text:
                        vrf["name"] = child.text.strip()
                    elif child_tag == "DefaultRD" and child.text:
                        vrf["rd"] = child.text.strip()
                if vrf["name"]:
                    results.append(vrf)
    except ET.ParseError as e:
        # 让上层记录日志
        raise ValueError(f"VPN instance XML 解析失败: {e}") from e
    return results


def extract_if_index(elem) -> Optional[int]:
    """从 Interface XML 元素中提取 if_index，缺失返回 None"""
    for child in elem:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "IfIndex" and child.text:
            try:
                return int(child.text)
            except ValueError:
                return None
    return None
