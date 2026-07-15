"""H3C V7 VPC 创建 / 删除 双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

## 背景

基于 .2 / .3 参考设备（2026-07-09 勘察）的实际配置抽象的命令序列模板。
模板不实际下发，只生成**双套 payload**（CLI 文本 + schema 化 NETCONF XML）。

## 业务下发通道（按 device.platform 路由）

| Platform | 通道 | 适用设备 |
|---|---|---|
| LSTN（老芯片）| CLI 文本走 `<Configuration>` 包裹 | S6850 / S6850-56HF / S6805 / S6825 / S5560X / S6520X |
| RSTN（新芯片）| schema 化 NETCONF XML 直接下发 | V9850 / S9820 / S12500R / S6890 |

**真根因**（3 维证据链 design.md T1.13d + T1.13e）：
- H3C Comware V7 L2VPN/EVPN/VXLAN 业务 NETCONF 实现走**芯片驱动**
- LSTN 老芯片驱动**不实现** schema 化 L2VPN 子树
- RSTN 新芯片驱动**完整实现** schema 化 L2VPN

## 变量

context 必须包含:
  - vpc: SdnVpc (id, vni, cidr, gateway_ip, gateway_mac, vsi_interface)
  - tenant: SdnTenant (rd, l3_vni)

返回 List[TemplateUnit] = List[
    TemplateUnit(name, description, cli_commands, xml_payloads, undo_cli, undo_xml)
]

## 5 unit 拆分（spec.md ADR-110）

| # | Unit | 范围 | undo 范围 |
|---|---|---|---|
| 1 | vsi-l2 | VSI 实例 + VXLAN + gateway vsi-interface | undo vsi + undo interface |
| 2 | evpn | evpn encapsulation + route-distinguisher | undo evpn + undo RD |
| 3 | l3vpn | ip vpn-instance l3vpn + RD + address-family evpn | （共享，不删）|
| 4 | vsi-l3 | Vsi-interface + IP + MAC + l3-vni + vpn binding | undo interface |
| 5 | global | vxlan tunnel mac-learning disable | （设备级，不删）|

## ADR

- ADR-102: 第 1 轮省略 import-rt / export-rt（BGP 自动默认）
- ADR-103: VSI 名称格式 vpc{vpc_id:04d}（4 位 0-pad）
- ADR-105: 模板本身不写 DB，dry-run 由 VPCConfigPlanner 决定
- ADR-109: 按 device.platform 路由通道（LSTN 走 CLI / RSTN 走 schema XML）
- ADR-110: 5 unit × 4 字段（cli + xml + undo_cli + undo_xml）
"""

from ipaddress import IPv4Network
from typing import List

from app.services.sdn_device_adapter import (
    H3C_V7_CONFIG_NS,
    H3C_V7_OP_CREATE,
    H3C_V7_OP_DELETE,
    H3C_V7_XC_NS,
    SDN_L3VPN_NAME,
    TemplateUnit,
    UNIT_EVPN,
    UNIT_GLOBAL,
    UNIT_L3VPN,
    UNIT_VSI_L2,
    UNIT_VSI_L3,
    VPCConfigTemplate,
)


def _vsi_name(vpc_id: int) -> str:
    """VSI 名称: vpc0001 ~ vpc9999 (ADR-103)"""
    return f"vpc{vpc_id:04d}"


def _vpc_rd(vni: int) -> str:
    """VPC RD: 1:{vni // 10} (spec.md 备注, .2/.3 现状回推)"""
    return f"1:{vni // 10}"


def _l3vpn_rd(l3_vni: int) -> str:
    """L3VPN RD: 1:{l3_vni} (共享 l3vpn 实例)"""
    return f"1:{l3_vni}"


def _subnet_mask(cidr: str) -> str:
    """CIDR → dotted decimal mask (e.g. '10.0.1.0/24' → '255.255.255.0')"""
    return str(IPv4Network(cidr, strict=False).netmask)


# ─────────── XML 构造 helpers ───────────

def _wrap_rstn_xml(body_xml: str, operation: str = H3C_V7_OP_CREATE) -> str:
    """构造 RSTN 平台 schema 化 NETCONF XML 完整 payload

    Args:
        body_xml: H3C 业务子树 XML（不含 <config> 包裹）
        operation: "create" | "delete" | "merge" | "replace"
    """
    return (
        f'<config xmlns:xc="{H3C_V7_XC_NS}">'
        f'<top xmlns="{H3C_V7_CONFIG_NS}" xc:operation="{operation}">'
        f"{body_xml}"
        f"</top></config>"
    )


def _wrap_lstn_xml(cli_text: str, operation: str = H3C_V7_OP_CREATE) -> str:
    """构造 LSTN 平台 CLI-over-NETCONF XML 完整 payload（T1.13f 验证通道可写）

    H3C V7 LSTN 设备 <Configuration>{cli}</Configuration> 真实可写
    """
    return (
        f'<config xmlns:xc="{H3C_V7_XC_NS}">'
        f'<top xmlns="{H3C_V7_CONFIG_NS}" xc:operation="{operation}">'
        f"<Configuration>{cli_text}</Configuration>"
        f"</top></config>"
    )


# ─────────── H3cV7VpcCreateTemplate ───────────

class H3cV7VpcCreateTemplate(VPCConfigTemplate):
    """H3C V7 VPC 创建双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

    输出 5 个 TemplateUnit，每 unit 含:
    - cli_commands: LSTN 设备走 CLI 文本（每条 system-view 下的命令）
    - xml_payloads: RSTN 设备走 schema 化 NETCONF XML（每条完整 <config> XML）
    - undo_cli: 反向 CLI 命令
    - undo_xml: 反向 schema 化 XML
    """

    def render(self, context: dict) -> List[TemplateUnit]:
        vpc = context["vpc"]
        tenant = context["tenant"]

        vsi_name = _vsi_name(vpc.id)
        vpc_rd = _vpc_rd(vpc.vni)
        l3vpn_rd = _l3vpn_rd(tenant.l3_vni)
        vxlan_id = vpc.vni
        vsi_iface_id = vpc.vsi_interface
        vsi_iface_name = f"Vsi-interface{vsi_iface_id}"
        subnet_mask = _subnet_mask(vpc.cidr)

        return [
            self._vsi_l2_unit(vsi_name, vxlan_id, vsi_iface_id, vsi_iface_name),
            self._evpn_unit(vsi_name, vpc_rd),
            self._l3vpn_unit(l3vpn_rd),
            self._vsi_l3_unit(vsi_iface_name, vpc, tenant.l3_vni, subnet_mask),
            self._global_unit(),
        ]

    # ---- unit 1: vsi-l2 ----

    def _vsi_l2_unit(
        self, vsi_name: str, vxlan_id: int, vsi_iface_id: int, vsi_iface_name: str
    ) -> TemplateUnit:
        """Unit 1: VSI 实例 + VXLAN 绑定 + gateway vsi-interface

        CLI (LSTN):
            vsi vpc0001
              gateway vsi-interface 1
              vxlan 20000

        XML (RSTN):
            <L2VPN>
              <VSIs>
                <VSI>
                  <VsiName>vpc0001</VsiName>
                  <VxlanID>20000</VxlanID>
                </VSI>
              </VSIs>
            </L2VPN>
            <VsiInterfaces>
              <VsiInterface>
                <ID>1</ID>
              </VsiInterface>
            </VsiInterfaces>
        """
        # CLI (LSTN) — system-view 下的层级缩进
        cli = [
            f"vsi {vsi_name}",
            f"  gateway vsi-interface {vsi_iface_id}",
            f"  vxlan {vxlan_id}",
        ]

        # XML (RSTN) — 2 条 payload: VSI + VsiInterface（不同子树，分开下发更稳）
        xml_vsi = _wrap_rstn_xml(
            f"<L2VPN><VSIs><VSI>"
            f"<VsiName>{vsi_name}</VsiName>"
            f"<VxlanID>{vxlan_id}</VxlanID>"
            f"</VSI></VSIs></L2VPN>"
        )
        xml_vsi_iface = _wrap_rstn_xml(
            f"<VsiInterfaces><VsiInterface>"
            f"<ID>{vsi_iface_id}</ID>"
            f"</VsiInterface></VsiInterfaces>"
        )

        # undo CLI (LSTN) — 反向
        undo_cli = [
            f"undo vsi {vsi_name}",
        ]

        # undo XML (RSTN) — 1 条 payload 即可（VsiInterface 跟 VSI 一同删除）
        undo_xml = [
            _wrap_rstn_xml(
                f"<L2VPN><VSIs><VSI>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<VxlanID>{vxlan_id}</VxlanID>"
                f"</VSI></VSIs></L2VPN>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        return TemplateUnit(
            name=UNIT_VSI_L2,
            description="VSI 实例 + VXLAN 绑定 + Vsi-interface 创建（L2 层）",
            cli_commands=cli,
            xml_payloads=[xml_vsi, xml_vsi_iface],
            undo_cli=undo_cli,
            undo_xml=undo_xml,
        )

    # ---- unit 2: evpn ----

    def _evpn_unit(self, vsi_name: str, vpc_rd: str) -> TemplateUnit:
        """Unit 2: EVPN 封装 + VPC RD

        CLI (LSTN):
            vsi vpc0001
              evpn encapsulation vxlan
                route-distinguisher 1:2000

        XML (RSTN):
            <L2VPN><VSIs><VSI>
              <VsiName>vpc0001</VsiName>
              <EVPN><Encapsulation>vxlan</Encapsulation>
                <RouteDistinguisher>1:2000</RouteDistinguisher>
              </EVPN>
            </VSI></VSIs></L2VPN>
        """
        cli = [
            f"vsi {vsi_name}",
            f"  evpn encapsulation vxlan",
            f"    route-distinguisher {vpc_rd}",
        ]

        xml = [
            _wrap_rstn_xml(
                f"<L2VPN><VSIs><VSI>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<EVPN>"
                f"<Encapsulation>vxlan</Encapsulation>"
                f"<RouteDistinguisher>{vpc_rd}</RouteDistinguisher>"
                f"</EVPN>"
                f"</VSI></VSIs></L2VPN>"
            ),
        ]

        undo_cli = [
            f"vsi {vsi_name}",
            f"  evpn encapsulation vxlan",
            f"    undo route-distinguisher",
        ]

        undo_xml = [
            _wrap_rstn_xml(
                f"<L2VPN><VSIs><VSI>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<EVPN>"
                f"<Encapsulation>vxlan</Encapsulation>"
                f"</EVPN>"
                f"</VSI></VSIs></L2VPN>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        return TemplateUnit(
            name=UNIT_EVPN,
            description="EVPN 封装 + VPC 路由区分符（RD）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=undo_cli,
            undo_xml=undo_xml,
        )

    # ---- unit 3: l3vpn ----

    def _l3vpn_unit(self, l3vpn_rd: str) -> TemplateUnit:
        """Unit 3: 共享 L3VPN 实例 + RD + address-family evpn

        CLI (LSTN):
            ip vpn-instance sdn_l3vpn
              route-distinguisher 1:10000
              address-family evpn

        XML (RSTN):
            <L3VPN><Instances><Instance>
              <Name>sdn_l3vpn</Name>
              <RouteDistinguisher>1:10000</RouteDistinguisher>
              <AddressFamilies>
                <AddressFamily>evpn</AddressFamily>
              </AddressFamilies>
            </Instance></Instances></L3VPN>

        Note:
            - v3.0 T6 真机验证：使用 sdn_l3vpn 而非 l3vpn（避开 .2/.3 underlay 冲突）
            - 此 unit undo 为空（sdn_l3vpn 是设备级共享实例，删 vpc 时不删）
            - 但 unit.cli_commands 和 xml_payloads 仍非空（创建时需要保证存在）
        """
        cli = [
            f"ip vpn-instance {SDN_L3VPN_NAME}",
            f"  route-distinguisher {l3vpn_rd}",
            "  address-family evpn",
        ]

        xml = [
            _wrap_rstn_xml(
                f"<L3VPN><Instances><Instance>"
                f"<Name>{SDN_L3VPN_NAME}</Name>"
                f"<RouteDistinguisher>{l3vpn_rd}</RouteDistinguisher>"
                f"<AddressFamilies><AddressFamily>evpn</AddressFamily></AddressFamilies>"
                f"</Instance></Instances></L3VPN>"
            ),
        ]

        return TemplateUnit(
            name=UNIT_L3VPN,
            description=f"共享 L3VPN 实例（{SDN_L3VPN_NAME}）+ RD + EVPN 地址族（设备级，共享）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=[],  # 共享，不删
            undo_xml=[],  # 共享，不删
        )

    # ---- unit 4: vsi-l3 ----

    def _vsi_l3_unit(
        self,
        vsi_iface_name: str,
        vpc,
        l3_vni: int,
        subnet_mask: str,
    ) -> TemplateUnit:
        """Unit 4: Vsi-interface L3 配置（IP + MAC + l3-vni + vpn binding）

        CLI (LSTN):
            interface Vsi-interface1
              ip binding vpn-instance sdn_l3vpn
              ip address 10.0.1.1 255.255.255.0
              mac-address 00-00-00-00-4e20-01
              l3-vni 10000

        XML (RSTN):
            <Interfaces>
              <Interface>
                <Name>Vsi-interface1</Name>
                <L3VPNInstanceName>sdn_l3vpn</L3VPNInstanceName>
                <IPv4>
                  <IPAddress>10.0.1.1</IPAddress>
                  <MaskLength>24</MaskLength>
                </IPv4>
                <MACAddress>00-00-00-00-4e20-01</MACAddress>
                <L3VNI>10000</L3VNI>
              </Interface>
            </Interfaces>
        """
        cli = [
            f"interface {vsi_iface_name}",
            f"  ip binding vpn-instance {SDN_L3VPN_NAME}",
            f"  ip address {vpc.gateway_ip} {subnet_mask}",
            f"  mac-address {vpc.gateway_mac}",
            f"  l3-vni {l3_vni}",
        ]

        # RSTN XML — 用 MaskLength 比 dotted mask 更稳
        # MaskLength 来自 CIDR
        from ipaddress import IPv4Network
        mask_length = IPv4Network(vpc.cidr, strict=False).prefixlen

        xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{vsi_iface_name}</Name>"
                f"<L3VPNInstanceName>{SDN_L3VPN_NAME}</L3VPNInstanceName>"
                f"<IPv4>"
                f"<IPAddress>{vpc.gateway_ip}</IPAddress>"
                f"<MaskLength>{mask_length}</MaskLength>"
                f"</IPv4>"
                f"<MACAddress>{vpc.gateway_mac}</MACAddress>"
                f"<L3VNI>{l3_vni}</L3VNI>"
                f"</Interface></Interfaces>"
            ),
        ]

        undo_cli = [
            f"undo interface {vsi_iface_name}",
        ]

        undo_xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{vsi_iface_name}</Name>"
                f"</Interface></Interfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        return TemplateUnit(
            name=UNIT_VSI_L3,
            description="Vsi-interface L3 配置（IP / MAC / L3VNI / VPN binding）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=undo_cli,
            undo_xml=undo_xml,
        )

    # ---- unit 5: global ----

    def _global_unit(self) -> TemplateUnit:
        """Unit 5: 设备级全局配置（vxlan tunnel mac-learning disable）

        CLI (LSTN):
            vxlan tunnel mac-learning disable

        XML (RSTN):
            注：RSTN 平台上无对应 schema 化 XML，executor 会 fallback 到 CLI 兜底
            此 unit 的 xml_payloads 和 undo_xml 留空（spec.md 验收 #1: global unit xml 为空）
        """
        cli = [
            "vxlan tunnel mac-learning disable",
        ]

        return TemplateUnit(
            name=UNIT_GLOBAL,
            description="设备级全局配置（VXLAN 隧道 MAC 学习关闭，RSTN 平台无 schema XML 兜底走 CLI）",
            cli_commands=cli,
            xml_payloads=[],  # RSTN 平台无对应 schema 化 XML
            undo_cli=[],  # 设备级，不删
            undo_xml=[],
        )


# ─────────── H3cV7VpcDeleteTemplate ───────────

class H3cV7VpcDeleteTemplate(VPCConfigTemplate):
    """H3C V7 VPC 删除双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

    输出 3 个 TemplateUnit（删除 VSI / EVPN / Vsi-interface，**共享 l3vpn 保留**）
    - 1: vsi-l2  undo → 删 vsi + vsi-interface
    - 2: evpn   undo → 清 evpn encapsulation RD
    - 3: vsi-l3 undo → 删 Vsi-interface
    - 不含 l3vpn / global（共享，保留）

    Note:
        delete template 的 unit **本身就是 undo**（再 delete 等于 idempotent）
        因此 unit.cli_commands / xml_payloads = undo 内容
        unit.undo_cli / undo_xml 留空（不需要再 undo）
    """

    def render(self, context: dict) -> List[TemplateUnit]:
        vpc = context["vpc"]

        vsi_name = _vsi_name(vpc.id)
        vpc_rd = _vpc_rd(vpc.vni)
        vsi_iface_id = vpc.vsi_interface
        vsi_iface_name = f"Vsi-interface{vsi_iface_id}"

        return [
            self._vsi_l2_undo_unit(vsi_name, vpc.vni, vsi_iface_id),
            self._evpn_undo_unit(vsi_name, vpc_rd),
            self._vsi_l3_undo_unit(vsi_iface_name),
        ]

    def _vsi_l2_undo_unit(
        self, vsi_name: str, vxlan_id: int, vsi_iface_id: int
    ) -> TemplateUnit:
        """vsi-l2 单元的 undo（删除 VSI + VsiInterface 子树）"""
        vsi_iface_name = f"Vsi-interface{vsi_iface_id}"
        cli = [
            f"undo vsi {vsi_name}",
            f"undo interface {vsi_iface_name}",
        ]
        xml = [
            _wrap_rstn_xml(
                f"<L2VPN><VSIs><VSI>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<VxlanID>{vxlan_id}</VxlanID>"
                f"</VSI></VSIs></L2VPN>",
                operation=H3C_V7_OP_DELETE,
            ),
            _wrap_rstn_xml(
                f"<VsiInterfaces><VsiInterface>"
                f"<ID>{vsi_iface_id}</ID>"
                f"</VsiInterface></VsiInterfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]
        return TemplateUnit(
            name=UNIT_VSI_L2,
            description="VPC 删除：撤销 VSI + VsiInterface（L2 层）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=[],  # delete 操作的 unit 不需要再 undo
            undo_xml=[],
        )

    def _evpn_undo_unit(self, vsi_name: str, vpc_rd: str) -> TemplateUnit:
        """evpn 单元的 undo（清 EVPN 封装 + RD）"""
        cli = [
            f"vsi {vsi_name}",
            f"  evpn encapsulation vxlan",
            f"    undo route-distinguisher",
        ]
        xml = [
            _wrap_rstn_xml(
                f"<L2VPN><VSIs><VSI>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<EVPN>"
                f"<Encapsulation>vxlan</Encapsulation>"
                f"<RouteDistinguisher>{vpc_rd}</RouteDistinguisher>"
                f"</EVPN>"
                f"</VSI></VSIs></L2VPN>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]
        return TemplateUnit(
            name=UNIT_EVPN,
            description="VPC 删除：撤销 EVPN 封装 + RD",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=[],
            undo_xml=[],
        )

    def _vsi_l3_undo_unit(self, vsi_iface_name: str) -> TemplateUnit:
        """vsi-l3 单元的 undo（删 Vsi-interface）"""
        cli = [
            f"undo interface {vsi_iface_name}",
        ]
        xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{vsi_iface_name}</Name>"
                f"</Interface></Interfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]
        return TemplateUnit(
            name=UNIT_VSI_L3,
            description="VPC 删除：撤销 Vsi-interface（L3 层）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=[],
            undo_xml=[],
        )
