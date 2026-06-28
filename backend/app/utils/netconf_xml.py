"""NETCONF XML 构造器（v2.2 H3C V7 实际模型）

H3C V7 设备（192.168.100.4 Leaf-03 实测）模型拆分：
- `Ifmgr/Interfaces/Interface`：物理/子接口（L2 + 部分 L3），**不返回带 VPN 的 L3 接口**
- `IPV4ADDRESS/Ipv4Addresses/Ipv4Address`：L3 接口的 IP 地址（独立模块）
- `L3vpn/L3vpnVRF/VRF/VRF`：VPN instance 定义
- `L3vpn/L3vpnIf/Bind/VRF/IfIndex`：VPN instance 绑定的接口

**合并规则**：完整接口列表 = Ifmgr 接口 + IPV4ADDRESS 中出现的 if_index（去重）

如果设备不支持 L3vpn，调用方降级走 SSH CLI（v2.3 跟进）。

**重要**：本文件所有 XML 都基于 192.168.100.4 探测得到。其他 H3C V7 设备
模型一致（用同一 H3C NETCONF schema），但具体字段可能略有差异。
"""
import xml.etree.ElementTree as ET
from typing import Optional

# H3C NETCONF 配置命名空间（与 vlan.py / interface.py 一致）
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"
# NETCONF base 1.0 命名空间
NETCONF_BASE_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"


# ============ 接口查询 filter ============


def build_interfaces_filter_xml() -> str:
    """物理/子接口（不含 L3）"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><Ifmgr><Interfaces/></Ifmgr></top>'


def build_ipv4_addresses_filter_xml() -> str:
    """L3 接口的 IP 地址（独立模块）"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><IPV4ADDRESS></IPV4ADDRESS></top>'


def build_interface_extended_filter_xml() -> str:
    """兼容旧名：返回 Ifmgr + IPV4ADDRESS（同时获取）

    注意：H3C filter 必须严格匹配 schema，**不能**同时声明多个根元素（多根是 XML 错），
    所以本函数保留为单根 Ifmgr，与原实现一致。IPV4ADDRESS 需单独查询。
    """
    return build_interfaces_filter_xml()


# ============ VPN instance ============


def build_vpn_instance_filter_xml() -> str:
    """查询所有 VPN instance + 绑定（一次拿全）"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><L3vpn></L3vpn></top>'


def build_vpn_instance_create_xml(name: str, rd: str = "auto") -> str:
    """创建 VPN instance

    H3C 模型：
    <L3vpn>
      <L3vpnVRF>
        <VRF>
          <VRF>name</VRF>
        </VRF>
      </L3vpnVRF>
    </L3vpn>

    注：H3C 探测下来 RD 不作为必填字段，VRF 下只需要 VRF 子元素。
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <L3vpn>
                <L3vpnVRF>
                    <VRF>
                        <VRF>{name}</VRF>
                    </VRF>
                </L3vpnVRF>
            </L3vpn>
        </top>
    </config>
    """


def build_vpn_instance_delete_xml(name: str) -> str:
    """删除 VPN instance

    H3C V7 限制：xc:operation 必须挂在外层 VRF（带 name 的那个）上，**不能**挂在内层 `<VRF>name</VRF>`。
    但两个元素都叫 VRF（外层结构 = VRF 容器，内层 = VRF name），所以需要在外层 VRF 加 xc:operation="delete"，
    然后内层 VRF 仍带 name 标识。

    实测：H3C 报错 `Unexpected attribute 'operation' of element '.../VRF/VRF'`
          → 必须改在外层 `VRF`（容器）上挂 `operation="delete"`。
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <L3vpn>
                <L3vpnVRF>
                    <VRF xmlns:xc="{NETCONF_BASE_NS}" xc:operation="delete">
                        <VRF>{name}</VRF>
                    </VRF>
                </L3vpnVRF>
            </L3vpn>
        </top>
    </config>
    """


# ============ 接口绑 VPN instance ============


def build_interface_bind_vpn_xml(if_index: int, vpn_name: str) -> str:
    """接口绑 VPN instance

    H3C 模型：
    <L3vpn>
      <L3vpnIf>
        <Bind>
          <VRF>mgt</VRF>
          <IfIndex>5121</IfIndex>
        </Bind>
      </L3vpnIf>
    </L3vpn>
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <L3vpn>
                <L3vpnIf>
                    <Bind>
                        <VRF>{vpn_name}</VRF>
                        <IfIndex>{if_index}</IfIndex>
                    </Bind>
                </L3vpnIf>
            </L3vpn>
        </top>
    </config>
    """


def build_interface_unbind_vpn_xml(if_index: int, vpn_name: str) -> str:
    """接口解绑 VPN instance（必须指定 VRF 名 + IfIndex 唯一定位 Bind）"""
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <L3vpn>
                <L3vpnIf xmlns:xc="{NETCONF_BASE_NS}">
                    <Bind xc:operation="delete">
                        <VRF>{vpn_name}</VRF>
                        <IfIndex>{if_index}</IfIndex>
                    </Bind>
                </L3vpnIf>
            </L3vpn>
        </top>
    </config>
    """


# ============ XML 解析辅助 ============


def parse_vpn_instances(xml_str: str) -> list[dict]:
    """解析 L3vpn get-config 响应

    预期响应：
    <L3vpn>
      <L3vpnVRF><VRF><VRF>name</VRF></VRF></L3vpnVRF>
      <L3vpnIf>
        <Bind><VRF>name</VRF><IfIndex>idx</IfIndex></Bind>
        ...
      </L3vpnIf>
    </L3vpn>

    Returns:
        {"instances": [{"name": "mgt", "bound_interfaces": [5121]}], "bindings": [{"vrf": "mgt", "if_index": 5121}]}
    """
    instances = []
    bindings = []
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "L3vpnVRF":
                for vrf in elem.iter():
                    t = vrf.tag.split("}")[-1] if "}" in vrf.tag else vrf.tag
                    if t == "VRF":
                        # VRF 元素下嵌套 VRF name
                        for sub in vrf:
                            st = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                            if st == "VRF" and sub.text:
                                instances.append({"name": sub.text.strip(), "rd": "auto"})
            elif tag == "Bind":
                bind = {"vrf": None, "if_index": None}
                for child in elem:
                    ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ct == "VRF" and child.text:
                        bind["vrf"] = child.text.strip()
                    elif ct == "IfIndex" and child.text:
                        try:
                            bind["if_index"] = int(child.text)
                        except ValueError:
                            pass
                if bind["vrf"] is not None and bind["if_index"] is not None:
                    bindings.append(bind)
    except ET.ParseError as e:
        raise ValueError(f"VPN instance XML 解析失败: {e}") from e

    # 合并
    for inst in instances:
        bound = [b["if_index"] for b in bindings if b["vrf"] == inst["name"]]
        inst["bound_interfaces"] = bound
    return {"instances": instances, "bindings": bindings}


def parse_ipv4_addresses(xml_str: str) -> dict[int, list[str]]:
    """解析 IPV4ADDRESS get-config 响应

    Returns:
        {if_index: ["192.168.100.4/24"], ...}
    """
    result = {}
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "Ipv4Address":
                if_index = None
                ip = None
                mask = None
                for child in elem:
                    ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ct == "IfIndex" and child.text:
                        try:
                            if_index = int(child.text)
                        except ValueError:
                            pass
                    elif ct == "Ipv4Address" and child.text:
                        ip = child.text.strip()
                    elif ct == "Ipv4Mask" and child.text:
                        mask = child.text.strip()
                if if_index is not None and ip:
                    if mask:
                        # 转换 255.255.255.0 → /24
                        prefix = _mask_to_prefix(mask)
                        result[if_index] = result.get(if_index, []) + [f"{ip}/{prefix}"]
                    else:
                        result[if_index] = result.get(if_index, []) + [ip]
    except ET.ParseError as e:
        raise ValueError(f"IPv4Address XML 解析失败: {e}") from e
    return result


def _mask_to_prefix(mask: str) -> int:
    """255.255.255.0 → 24"""
    try:
        parts = [int(p) for p in mask.split(".")]
        if len(parts) != 4:
            return 32
        n = 0
        for p in parts:
            n = (n << 8) | p
        # 计算 1 的个数
        prefix = 0
        for i in range(31, -1, -1):
            if (n >> i) & 1:
                prefix += 1
            else:
                break
        return prefix
    except (ValueError, AttributeError):
        return 32


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
