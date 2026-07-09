"""H3C V7 VPC 创建 / 删除 CLI 模板

## 背景

基于 .2 / .3 参考设备（2026-07-09 勘察）的实际配置抽象的命令序列模板。
模板不实际下发，只生成有序命令列表。

## 变量

context 必须包含:
  - vpc: SdnVpc (id, vni, cidr, gateway_ip, gateway_mac, vsi_interface)
  - tenant: SdnTenant (rd, l3_vni)

返回 List[ConfigCommand] = List[{mode: "configure", command: "<cli>"}]

## ADR

- ADR-102: 第 1 轮省略 import-rt / export-rt（BGP 自动默认）
- ADR-103: VSI 名称格式 vpc{vpc_id:04d}（4 位 0-pad）
- ADR-105: 模板本身不写 DB，dry-run 由 VPCConfigPlanner 决定
"""

from ipaddress import IPv4Network
from typing import List

from app.services.sdn_device_adapter import VPCConfigTemplate


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


class H3cV7VpcCreateTemplate(VPCConfigTemplate):
    """H3C V7 VPC 创建命令模板

    输出 14 条命令（spec.md Requirement: VPCConfigPlanner 配置计划生成）
    """

    def render(self, context: dict) -> List[dict]:
        vpc = context["vpc"]
        tenant = context["tenant"]

        vsi_name = _vsi_name(vpc.id)
        vpc_rd = _vpc_rd(vpc.vni)
        l3vpn_rd = _l3vpn_rd(tenant.l3_vni)

        return [
            # 1. 创建 VSI
            {"mode": "configure", "command": f"vsi {vsi_name}"},
            {"mode": "configure", "command": f"  gateway vsi-interface {vpc.vsi_interface}"},
            {"mode": "configure", "command": f"  vxlan {vpc.vni}"},
            {"mode": "configure", "command": "  evpn encapsulation vxlan"},
            {"mode": "configure", "command": f"    route-distinguisher {vpc_rd}"},

            # 2. 共享 l3vpn vpn-instance (第 1 轮, 共享, 不重复创建)
            {"mode": "configure", "command": "ip vpn-instance l3vpn"},
            {"mode": "configure", "command": f"  route-distinguisher {l3vpn_rd}"},
            {"mode": "configure", "command": "  address-family evpn"},
            # import-rt / export-rt 第 1 轮省略 (ADR-102)

            # 3. 创建 Vsi-interface
            {"mode": "configure", "command": f"interface Vsi-interface{vpc.vsi_interface}"},
            {"mode": "configure", "command": "  ip binding vpn-instance l3vpn"},
            {"mode": "configure", "command": f"  ip address {vpc.gateway_ip} {_subnet_mask(vpc.cidr)}"},
            {"mode": "configure", "command": f"  mac-address {vpc.gateway_mac}"},
            {"mode": "configure", "command": f"  l3-vni {tenant.l3_vni}"},

            # 4. 全局配置 (一次性, 设备级)
            {"mode": "configure", "command": "vxlan tunnel mac-learning disable"},
        ]


class H3cV7VpcDeleteTemplate(VPCConfigTemplate):
    """H3C V7 VPC 删除命令模板（反向 create, 共享 l3vpn 保留）

    设计: 删 vsi + vsi-interface, 不删 l3vpn / 不删 vxlan tunnel mac-learning disable
    (设备级, 跟其他 vpc 共享)
    """

    def render(self, context: dict) -> List[dict]:
        vpc = context["vpc"]

        vsi_name = _vsi_name(vpc.id)
        vsi_interface = vpc.vsi_interface

        return [
            {"mode": "configure", "command": f"undo vsi {vsi_name}"},
            {"mode": "configure", "command": f"undo interface Vsi-interface{vsi_interface}"},
            # l3vpn vpn-instance 共享, 不删
            # vxlan tunnel mac-learning disable 设备级, 不删
        ]
