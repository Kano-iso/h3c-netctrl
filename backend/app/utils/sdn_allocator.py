"""SDN 资源编号分配器（v3.0）

负责租户、VPC 等资源的自动编号分配，所有值避开前 1000 号段。
- RD/RT 格式：{base}:{tenant_id}（如 100:1）
- L3VNI / L2VNI / Vsi-interface / VLAN：从环境变量起始值递增

无状态设计：每次分配查询 DB 当前最大值 + 1。
适用场景：租户/VPC 创建是低频操作，SQLite 单写场景无竞争。
"""
import os
import ipaddress
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import SdnTenant, SdnVpc


# 前 1000 号段保留给人工/历史配置，所有起始值默认 ≥ 1000
RESERVED_THRESHOLD = 1000


class SdnAllocator:
    """SDN 编号分配器（无状态）。"""

    RD_BASE = int(os.getenv("SDN_RD_BASE", "100"))
    RT_BASE = int(os.getenv("SDN_RT_BASE", "100"))
    L3VNI_START = int(os.getenv("SDN_L3VNI_START", "10000"))
    L2VNI_START = int(os.getenv("SDN_L2VNI_START", "20000"))
    VSI_IF_START = int(os.getenv("SDN_VSI_IF_START", "1000"))
    VLAN_START = int(os.getenv("SDN_VLAN_START", "2000"))

    @staticmethod
    def allocate_rd(tenant_id: int) -> str:
        """分配 RD：{base}:{tenant_id}"""
        return f"{SdnAllocator.RD_BASE}:{tenant_id}"

    @staticmethod
    def allocate_rt(tenant_id: int) -> tuple[str, str]:
        """分配 RT（import, export）：{base}:{tenant_id}"""
        base = SdnAllocator.RT_BASE
        return (f"{base}:{tenant_id}", f"{base}:{tenant_id}")

    @staticmethod
    def allocate_l3vni(db: Session) -> int:
        """分配 L3VNI：max + 1，起始值 L3VNI_START（默认 10000）。"""
        max_vni = db.query(func.max(SdnTenant.l3_vni)).scalar() or 0
        return max(max_vni + 1, SdnAllocator.L3VNI_START)

    @staticmethod
    def allocate_l2vni(db: Session) -> int:
        """分配 L2VNI：max + 1，起始值 L2VNI_START（默认 20000）。"""
        max_vni = db.query(func.max(SdnVpc.vni)).scalar() or 0
        return max(max_vni + 1, SdnAllocator.L2VNI_START)

    @staticmethod
    def allocate_vsi_interface(db: Session) -> int:
        """分配 Vsi-interface 编号：max + 1，起始值 VSI_IF_START（默认 1000）。"""
        max_if = db.query(func.max(SdnVpc.vsi_interface)).scalar() or 0
        return max(max_if + 1, SdnAllocator.VSI_IF_START)

    @staticmethod
    def allocate_vlan(db: Session) -> int:
        """分配 VLAN：max + 1，起始值 VLAN_START（默认 2000）。"""
        max_vlan = db.query(func.max(SdnVpc.vlan_id)).scalar() or 0
        return max(max_vlan + 1, SdnAllocator.VLAN_START)

    @staticmethod
    def derive_gateway_ip(cidr: str) -> str:
        """从 CIDR 推导默认 gateway_ip：取最后一个可用地址。

        例：192.168.10.0/24 → 192.168.10.254
        """
        net = ipaddress.IPv4Network(cidr, strict=False)
        # 广播地址 - 1 = 最后可用地址
        broadcast = net.broadcast_address
        gateway_int = int(broadcast) - 1
        return str(ipaddress.IPv4Address(gateway_int))

    @staticmethod
    def derive_gateway_mac(vni: int) -> str:
        """从 VNI 推导默认分布式网关 MAC：001a-2b00-xxxx（H3C V7 mac-address 命令格式）。

        H3C V7 Vsi-interface 视图下 `mac-address` 命令格式为 H-H-H（3 组 4 hex，共 12 hex）：
        - 不是 IEEE 802 标准 MAC 6 组 2 hex 格式（XX-XX-XX-XX-XX-XX）— 设备会报 "% Wrong parameter"
        - H3C OUI 001a2b（H3C 厂商注册）作为前缀避开 IANA reserved 范围
        - xx = VNI 低 16 位 hex（4 hex 位）
        - 例：vni=20000 → 0x4E20 → 001a-2b00-4e20

        Note:
            - T6 真机验证（2026-07-15）：H3C V7 S6850 Vsi-interface 视图下：
              1. `mac-address` 要求 H-H-H 格式（3 组 4 hex），不是 6 组 2 hex
              2. 00:00:5e 范围（VRRP reserved）报 "% Wrong parameter"
              3. 00:1a:2b 在 6 组格式下也拒绝（设备内部可能做了格式归一化检查）
            - 正确格式：H3C OUI + 16-bit VNI，输出 001a-2b00-xxxx
        """
        # VNI 高 8 位 -> 第 3 组前 2 位
        # VNI 低 8 位 -> 第 3 组后 2 位
        # 组合成 16-bit VNI hex = 4 hex chars（作为 H-H-H 第 3 组）
        vni_hex = f"{vni & 0xFFFF:04x}"
        return f"001a-2b00-{vni_hex}"

    @staticmethod
    def build_vsi_name(vpc_id: int) -> str:
        """生成 VSI 名称：vpc{vpc_id:04d}（4 位 0-pad，ADR-103）

        与模板 _vsi_name(vpc.id) 保持一致——避免双源数据漂移。
        历史版本曾用 vpc-{tenant_name}-{vpc_name}，但导致 vpc.vsi_name 字段与模板生成的 VSI 名字不一致。
        """
        return f"vpc{vpc_id:04d}"


def validate_cidr(cidr: str) -> Optional[str]:
    """校验 CIDR 格式与网段合法性。

    返回 None 表示合法；返回错误描述字符串表示不合法。
    """
    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
    except (ValueError, TypeError) as e:
        return f"无效的 CIDR 格式：{cidr}（{e}）"
    if net.prefixlen < 8 or net.prefixlen > 30:
        return f"CIDR 前缀长度需在 /8~/30 之间，当前 /{net.prefixlen}"
    return None
