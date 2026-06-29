import json
import logging
import re
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from typing_extensions import Literal
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_netconf_error
from app.schemas import APIResponse
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log
from app.utils.netconf_xml import (
    build_interface_bind_vpn_xml,
    build_interface_extended_filter_xml,
    build_interface_unbind_vpn_xml,
    build_ipv4_address_clear_xml,
    build_ipv4_address_set_xml,
    build_link_type_change_xml,
    build_vpn_instance_create_xml,
    build_vpn_instance_delete_xml,
    build_vpn_instance_filter_xml,
    parse_vpn_instances,
)

logger = logging.getLogger("app")

router = APIRouter(tags=["interface"])

# H3C 命名空间（与 vlan.py 一致）
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"

# LinkType 映射
LINK_TYPE_MAP = {"access": 1, "trunk": 2, "hybrid": 3}
LINK_TYPE_REVERSE = {1: "access", 2: "trunk", 3: "hybrid"}

# L3 接口命名约定（H3C 官方）
L3_NAME_PATTERN = re.compile(r"^Vlan-interface\d+", re.IGNORECASE)
# 子接口命名约定（如 GigabitEthernet0/0/0.100）
SUB_IF_PATTERN = re.compile(r"^.+\.\d+$")


class InterfaceConfig(BaseModel):
    if_index: int  # NETCONF 接口索引（从查询接口列表获取）
    mode: str  # "access" or "trunk"
    access_vlan: Optional[int] = None
    allowed_vlans: Optional[List[int]] = None
    pvid: Optional[int] = None
    force: bool = Field(default=False, description="强制配置被保护的接口（高风险，需明确知道后果）")


def _get_device_and_password(db: Session, device_id: int):
    """根据设备 ID 获取设备信息和解密密码"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return None, None, APIResponse(success=False, error=f"设备不存在: id={device_id}")
    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return None, None, APIResponse(success=False, error="密码解密失败")
    return device, password, None


def _build_interface_filter_xml() -> str:
    """构造 H3C 接口 get-config filter XML"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><Ifmgr><Interfaces/></Ifmgr></top>'


def _parse_interface_response(xml_str: str) -> list[dict]:
    """解析 H3C 合并响应 XML（v2.2 多模块真实模型）

    H3C V7 实际响应（单次 get-config 多模块 filter）：
    <Ifmgr><Interfaces>
      <Interface><IfIndex>2</IfIndex><Description>Trunk</Description><LinkType>2</LinkType></Interface>
      ...
    </Interfaces></Ifmgr>
    <IPV4ADDRESS><Ipv4Addresses>
      <Ipv4Address><IfIndex>5121</IfIndex><Ipv4Address>192.168.100.4</Ipv4Address><Ipv4Mask>255.255.255.0</Ipv4Mask></Ipv4Address>
    </Ipv4Addresses></IPV4ADDRESS>
    <L3vpn>
      <L3vpnVRF><VRF><VRF>mgt</VRF></VRF></L3vpnVRF>
      <L3vpnIf><Bind><VRF>mgt</VRF><IfIndex>5121</IfIndex></Bind></L3vpnIf>
    </L3vpn>

    关键发现：H3C V7 ifmgr **不返回**带 VPN 的 L3 接口（如 5121），所以要合并 IPV4ADDRESS 找 L3 接口。

    字段：
    - L2 接口（ifmgr 返回）：name, mode, pvid, allowed_vlans, status
    - L3 接口（IPV4ADDRESS 返回）：ip_addresses
    - VPN 绑定（L3vpnIf 返回）：vpn_instance
    """
    interfaces = []
    if_index_to_iface: dict[int, dict] = {}
    ip_by_idx: dict[int, list[str]] = {}
    vpn_by_idx: dict[int, str] = {}

    try:
        root = ET.fromstring(xml_str)

        # Pass 1: Ifmgr
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag != "Interface":
                continue
            iface: dict = {"if_index": None}
            for child in elem:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "IfIndex" and child.text:
                    iface["if_index"] = int(child.text)
                elif ct == "Description" and child.text:
                    iface["name"] = child.text.strip()
                elif ct == "LinkType" and child.text:
                    iface["mode"] = LINK_TYPE_REVERSE.get(int(child.text), "access")
                elif ct == "PVID" and child.text:
                    iface["pvid"] = int(child.text)
                elif ct == "TrunkVLANs" and child.text:
                    iface["allowed_vlans"] = _parse_vlan_range(child.text)
                elif ct == "AdminStatus" and child.text:
                    iface["status"] = "up" if child.text == "1" else "down"
            if iface.get("if_index") is not None:
                if_index_to_iface[iface["if_index"]] = iface

        # Pass 2: IPV4ADDRESS
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag != "Ipv4Address":
                continue
            if_idx = None
            ip = None
            mask = None
            for child in elem:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "IfIndex" and child.text:
                    try:
                        if_idx = int(child.text)
                    except ValueError:
                        pass
                elif ct == "Ipv4Address" and child.text:
                    ip = child.text.strip()
                elif ct == "Ipv4Mask" and child.text:
                    mask = child.text.strip()
            if if_idx is not None and ip:
                if mask:
                    prefix = _mask_to_prefix(mask)
                    ip_by_idx[if_idx] = ip_by_idx.get(if_idx, []) + [f"{ip}/{prefix}"]
                else:
                    ip_by_idx[if_idx] = ip_by_idx.get(if_idx, []) + [ip]

        # Pass 3: L3vpnIf.Bind
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag != "Bind":
                continue
            vrf = None
            if_idx = None
            for child in elem:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "VRF" and child.text:
                    vrf = child.text.strip()
                elif ct == "IfIndex" and child.text:
                    try:
                        if_idx = int(child.text)
                    except ValueError:
                        pass
            if vrf and if_idx is not None:
                vpn_by_idx[if_idx] = vrf

        # 合并：ifmgr 接口 + 纯 L3 接口（IPV4ADDRESS 有但 ifmgr 没有）
        for if_idx, iface in if_index_to_iface.items():
            iface["ip_addresses"] = ip_by_idx.get(if_idx, [])
            iface["vpn_instance"] = vpn_by_idx.get(if_idx)
            iface["layer"] = _detect_layer(iface, ip_by_idx.get(if_idx, []), vpn_by_idx.get(if_idx))
            interfaces.append(iface)

        # 加纯 L3 接口（ifmgr 不返回的）
        for if_idx, ips in ip_by_idx.items():
            if if_idx in if_index_to_iface:
                continue
            iface = {
                "if_index": if_idx,
                "name": f"If-{if_idx}",  # ifmgr 没返回，兜底
                "ip_addresses": ips,
                "vpn_instance": vpn_by_idx.get(if_idx),
                "layer": "L3",
                "mode": "access",  # 占位
                "pvid": None,
                "allowed_vlans": [],
                "status": "unknown",
            }
            interfaces.append(iface)

    except ET.ParseError as e:
        logger.error(f"接口 XML 解析失败: {e}")

    # 兜底：fill 默认值 + 算 access_vlan
    for iface in interfaces:
        iface.setdefault("name", f"If-{iface.get('if_index', '?')}")
        iface.setdefault("mode", "access")
        iface.setdefault("status", "unknown")
        iface.setdefault("allowed_vlans", [])
        iface.setdefault("ip_addresses", [])
        iface.setdefault("vpn_instance", None)
        iface.setdefault("layer", "L2")
        iface["access_vlan"] = iface["pvid"] if iface.get("mode") == "access" and iface.get("pvid") else None

    # 按 if_index 排序
    interfaces.sort(key=lambda x: x.get("if_index", 0))
    return interfaces


def _detect_layer(iface: dict, ip_addresses: list[str], vpn_instance: str | None) -> str:
    """判定 L2 / L3（v2.2 H3C V7 实际模型版）

    判定规则（H3C V7 真实情况，name 不可用）：
    1. 有 IPv4 地址 → L3
    2. 绑了 VPN instance → L3
    3. 名称以 Vlan-interface 开头 → L3
    4. 名称匹配子接口正则（X.Y） → L3
    5. 其余 → L2
    """
    if ip_addresses:
        return "L3"
    if vpn_instance:
        return "L3"
    name = iface.get("name", "") or ""
    if L3_NAME_PATTERN.match(name):
        return "L3"
    if SUB_IF_PATTERN.match(name):
        return "L3"
    return "L2"


def _mask_to_prefix(mask: str) -> int:
    """255.255.255.0 → 24"""
    try:
        parts = [int(p) for p in mask.split(".")]
        if len(parts) != 4:
            return 32
        n = 0
        for p in parts:
            n = (n << 8) | p
        prefix = 0
        for i in range(31, -1, -1):
            if (n >> i) & 1:
                prefix += 1
            else:
                break
        return prefix
    except (ValueError, AttributeError):
        return 32


def _parse_vlan_range(vlan_str: str) -> list[int]:
    """解析 H3C VLAN 范围字符串，如 '1-5,10,20-30' → [1,2,3,4,5,10,20,21,...,30]"""
    vlans = []
    if not vlan_str or vlan_str.strip() == "":
        return vlans
    for part in vlan_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                for v in range(int(start), int(end) + 1):
                    vlans.append(v)
            except ValueError:
                continue
        else:
            try:
                vlans.append(int(part))
            except ValueError:
                continue
    return vlans


def _build_interface_config_xml(if_index: int, mode: str, access_vlan: Optional[int] = None,
                                 allowed_vlans: Optional[List[int]] = None, pvid: Optional[int] = None) -> str:
    """构造 H3C 接口配置 edit-config XML"""
    link_type = LINK_TYPE_MAP.get(mode, 1)

    # 构建 TrunkVLANs
    trunk_vlans_elem = ""
    if mode == "trunk" and allowed_vlans:
        vlan_str = ",".join(str(v) for v in allowed_vlans)
        trunk_vlans_elem = f"<TrunkVLANs>{vlan_str}</TrunkVLANs>"

    # PVID
    pvid_elem = ""
    pvid_val = pvid if mode == "trunk" and pvid else access_vlan if mode == "access" and access_vlan else None
    if pvid_val:
        pvid_elem = f"<PVID>{pvid_val}</PVID>"

    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}" xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
            <Ifmgr>
                <Interfaces>
                    <Interface>
                        <IfIndex>{if_index}</IfIndex>
                        <LinkType>{link_type}</LinkType>
                        {pvid_elem}
                        {trunk_vlans_elem}
                    </Interface>
                </Interfaces>
            </Ifmgr>
        </top>
    </config>
    """


def _classify_interface_error(error: Exception) -> str:
    """将接口操作异常分类为可读的中文错误信息"""
    return classify_netconf_error(error)


def _build_vlan_filter() -> str:
    """构造 H3C VLAN get-config filter XML（与 vlan.py 一致）"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><VLAN></VLAN></top>'


def _parse_vlans_from_xml(xml_str: str) -> set:
    """从 VLAN get-config 响应中提取所有 VLAN ID 集合"""
    import xml.etree.ElementTree as ET
    vlan_ids = set()
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "VLANID":
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "ID" and child.text:
                        try:
                            vlan_ids.add(int(child.text))
                        except ValueError:
                            pass
    except ET.ParseError:
        pass
    return vlan_ids


def _check_vlans_exist(client: NetconfClient, vlan_ids: list) -> tuple[bool, str]:
    """检查 VLAN 是否都存在

    Returns: (all_exist, error_msg)
    - all_exist=True: 所有 VLAN 都存在
    - all_exist=False: 缺失的 VLAN 列表（error_msg 含详情）
    """
    if not vlan_ids:
        return True, ""
    try:
        xml_str = client.get_config(_build_vlan_filter())
        existing = _parse_vlans_from_xml(xml_str)
        missing = [v for v in vlan_ids if v not in existing]
        if missing:
            return False, f"VLAN {','.join(str(v) for v in missing)} 不存在，请先创建"
        return True, ""
    except Exception as e:
        # VLAN 查询失败不阻塞主流程，让设备返回更具体的错误
        logger.warning(f"VLAN 预校验失败，跳过校验: {e}")
        return True, ""


@router.get("/devices/{device_id}/interfaces", response_model=APIResponse)
def get_interfaces(device_id: int, db: Session = Depends(get_db)):
    """获取设备接口列表（NETCONF）"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 一次查三模块（Ifmgr + IPV4ADDRESS + L3vpn）
            combined_filter = (
                f'<top xmlns="{H3C_CONFIG_NS}">'
                '<Ifmgr><Interfaces/></Ifmgr>'
                '<IPV4ADDRESS></IPV4ADDRESS>'
                '<L3vpn></L3vpn>'
                '</top>'
            )
            filter_xml = combined_filter
            response_xml = client.get_config(filter_xml)

        interfaces = _parse_interface_response(response_xml)
        logger.info(f"接口查询成功: device_id={device_id}, 获取到 {len(interfaces)} 个接口")
        return APIResponse(success=True, data=interfaces)
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"接口查询失败: device_id={device_id}, 原因={error_msg}", exc_info=True)
        return APIResponse(success=False, error=error_msg)


@router.post("/devices/{device_id}/interfaces/config", response_model=APIResponse)
def configure_interface(device_id: int, body: InterfaceConfig, db: Session = Depends(get_db)):
    """下发接口配置（NETCONF edit-config）"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    if body.mode not in ("access", "trunk"):
        return APIResponse(success=False, error="模式必须是 access 或 trunk")

    # 安全护栏：检查 if_index 是否在保护列表中
    try:
        protected = json.loads(device.protected_interfaces or "[]")
    except (json.JSONDecodeError, TypeError):
        protected = []
    if not isinstance(protected, list):
        protected = []
    protected = [int(x) for x in protected if isinstance(x, (int, str)) and str(x).isdigit()]

    if body.if_index in protected and not body.force:
        msg = (f"接口 if_index={body.if_index} 在保护列表中，禁止配置。"
               f"如需配置请加 force=true 或先在设备管理中解除保护")
        logger.warning(f"接口配置被保护拦截: device_id={device_id}, if_index={body.if_index}, 保护列表={protected}")
        record_log(db, device.id, device.name, "interface_config",
                   f"配置接口 if_index={body.if_index} 被保护拦截", "failed", error_message=msg)
        return APIResponse(success=False, error=msg)

    if body.if_index in protected and body.force:
        logger.warning(f"接口配置 force=true 强制通过保护: device_id={device_id}, if_index={body.if_index}")

    # 设备能力边界：H3C V7 NETCONF edit-config 不支持配置 trunk 允许 VLAN 列表
    # 详见 openspec/changes/fix-interface-trunk-deploy（H3C 官方命令参考 + 设备实地探测）
    if body.mode == "trunk" and body.allowed_vlans:
        vlan_list_str = ",".join(str(v) for v in body.allowed_vlans)
        msg = (f"当前设备不支持通过 NETCONF 配置 trunk 允许 VLAN 列表（{vlan_list_str}）。"
               f"请到设备 CLI 手工执行：port trunk permit vlan {vlan_list_str}")
        logger.warning(f"接口配置被设备能力拦截: device_id={device_id}, if_index={body.if_index}, "
                       f"mode=trunk, allowed_vlans={vlan_list_str}")
        record_log(db, device.id, device.name, "interface_config",
                   f"配置接口 if_index={body.if_index} 被设备能力拦截（trunk+allowed_vlans）",
                   "failed", error_message=msg)
        return APIResponse(success=False, error=msg)

    # 收集需要校验的 VLAN（access 用 access_vlan，trunk 用 pvid + allowed_vlans）
    vlans_to_check = []
    if body.mode == "access" and body.access_vlan:
        vlans_to_check.append(body.access_vlan)
    elif body.mode == "trunk":
        if body.pvid:
            vlans_to_check.append(body.pvid)
        if body.allowed_vlans:
            vlans_to_check.extend(body.allowed_vlans)

    try:
        # 一次性连接，同时做 VLAN 预校验和接口配置
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # VLAN 预校验
            ok, vlan_err = _check_vlans_exist(client, vlans_to_check)
            if not ok:
                logger.warning(f"接口配置前置校验失败: device_id={device_id}, {vlan_err}")
                return APIResponse(success=False, error=vlan_err)

            # 校验通过，下发配置
            config_xml = _build_interface_config_xml(
                if_index=body.if_index,
                mode=body.mode,
                access_vlan=body.access_vlan,
                allowed_vlans=body.allowed_vlans,
                pvid=body.pvid,
            )
            client.edit_config(config_xml)

        logger.info(f"接口配置成功: device_id={device_id}, if_index={body.if_index}, mode={body.mode}")
        record_log(db, device.id, device.name, "interface_config",
                   f"配置接口 if_index={body.if_index}: mode={body.mode}", "success")
        return APIResponse(success=True, data={"message": f"接口配置已下发 (if_index={body.if_index})"})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"接口配置失败: device_id={device_id}, if_index={body.if_index}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "interface_config",
                   f"配置接口 if_index={body.if_index} 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ============================================================
# v2.2 VPN instance + 接口绑 VPN
# ============================================================


class VpnInstanceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, description="VPN instance 名")
    rd: str = Field(default="auto", description="route-distinguisher，默认 auto")


class InterfaceVpnBind(BaseModel):
    name: str = Field(..., min_length=1, max_length=32, description="VPN instance 名")


def _get_protected_interfaces(device: Device) -> list[int]:
    """解析 device.protected_interfaces JSON 列表"""
    try:
        protected = json.loads(device.protected_interfaces or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(protected, list):
        return []
    return [int(x) for x in protected if isinstance(x, (int, str)) and str(x).isdigit()]


def _resolve_interfaces_for_vpn(client: NetconfClient, vpn_name: str) -> list[dict]:
    """查询 VPN instance 当前绑定的所有接口

    通过 L3vpn get-config 找到该 VPN 的所有 Bind IfIndex。
    """
    response_xml = client.get_config(build_vpn_instance_filter_xml())
    parsed = parse_vpn_instances(response_xml)
    bindings = parsed.get("bindings", [])
    bound = []
    for b in bindings:
        if b.get("vrf") == vpn_name and b.get("if_index") is not None:
            bound.append({
                "if_index": b["if_index"],
                "name": f"If-{b['if_index']}",  # 简化：没拿 name
            })
    return bound


def _parse_vpn_bindings_by_ifindex(vpn_xml: str) -> dict[int, str]:
    """解析 L3vpn get-config 响应，返回 {if_index: vpn_name} 映射

    用于 unbind_interface_vpn 等需要把 VPN 绑定信息合并到接口列表的场景。
    委托给 netconf_xml.parse_vpn_instances，避免重复实现。
    """
    parsed = parse_vpn_instances(vpn_xml)
    return {b["if_index"]: b["vrf"] for b in parsed.get("bindings", [])
            if b.get("if_index") is not None and b.get("vrf") is not None}


# H3C filter 多根限制：必须分两次 get_config，再合并
# 见 netconf_xml.py: build_interface_extended_filter_xml 的注释
_IFACE_FILTERS_FOR_UNBIND = (
    f'<top xmlns="{H3C_CONFIG_NS}">'
    '<Ifmgr><Interfaces/></Ifmgr>'
    '<IPV4ADDRESS></IPV4ADDRESS>'
    '</top>'
)


# ============ VPN instance 端点 ============


@router.get("/devices/{device_id}/vpn-instances", response_model=APIResponse)
def list_vpn_instances(device_id: int, db: Session = Depends(get_db)):
    """列出设备上所有 VPN instance"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            response_xml = client.get_config(build_vpn_instance_filter_xml())
            parsed = parse_vpn_instances(response_xml)
            vpn_list = parsed["instances"]  # 已含 bound_interfaces

            result = []
            for vpn in vpn_list:
                # vpn 含 bound_interfaces（已解析）；前端用 if_index 即可
                bound = [{"if_index": idx, "name": f"If-{idx}"} for idx in vpn.get("bound_interfaces", [])]
                result.append({
                    "name": vpn["name"],
                    "rd": vpn.get("rd", "auto"),
                    "interfaces": bound,
                })

        logger.info(f"VPN instance 列表: device_id={device_id}, count={len(result)}")
        return APIResponse(
            success=True,
            data={"device_id": device_id, "total": len(result), "vpn_instances": result},
        )
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"VPN instance 列表失败: device_id={device_id}, 原因={error_msg}", exc_info=True)
        return APIResponse(success=False, error=error_msg)


@router.post("/devices/{device_id}/vpn-instances", response_model=APIResponse)
def create_vpn_instance(device_id: int, body: VpnInstanceCreate, db: Session = Depends(get_db)):
    """创建 VPN instance（NETCONF 优先，失败由设备返回错误）"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # 名称校验
    name = body.name.strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", name):
        return APIResponse(success=False, error="VPN instance 名只能包含字母、数字、下划线、连字符")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 预校验：是否已存在
            existing = parse_vpn_instances(client.get_config(build_vpn_instance_filter_xml()))["instances"]
            if any(v["name"] == name for v in existing):
                return APIResponse(success=False, error=f"VPN instance {name} 已存在")

            config_xml = build_vpn_instance_create_xml(name, body.rd)
            client.edit_config(config_xml)

        logger.info(f"VPN instance 创建成功: device_id={device_id}, name={name}, rd={body.rd}")
        record_log(db, device.id, device.name, "vpn_instance_create",
                   f"创建 VPN instance {name} (rd={body.rd})", "success")
        return APIResponse(success=True, data={"name": name, "rd": body.rd})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"VPN instance 创建失败: device_id={device_id}, name={name}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vpn_instance_create",
                   f"创建 VPN instance {name} 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


@router.delete("/devices/{device_id}/vpn-instances/{vpn_name}", response_model=APIResponse)
def delete_vpn_instance(device_id: int, vpn_name: str, db: Session = Depends(get_db)):
    """删除 VPN instance（前置预校验：必须有 0 个绑定）"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 预校验：是否还存在
            existing = parse_vpn_instances(client.get_config(build_vpn_instance_filter_xml()))["instances"]
            if not any(v["name"] == vpn_name for v in existing):
                return APIResponse(success=False, error=f"VPN instance {vpn_name} 不存在")

            # 预校验：绑定数
            bound = _resolve_interfaces_for_vpn(client, vpn_name)
            if bound:
                bound_names = ", ".join(b["name"] for b in bound)
                return APIResponse(
                    success=False,
                    error=f"VPN instance {vpn_name} 还有 {len(bound)} 个接口绑定（{bound_names}），请先解绑",
                )

            config_xml = build_vpn_instance_delete_xml(vpn_name)
            client.edit_config(config_xml)

        logger.info(f"VPN instance 删除成功: device_id={device_id}, name={vpn_name}")
        record_log(db, device.id, device.name, "vpn_instance_delete",
                   f"删除 VPN instance {vpn_name}", "success")
        return APIResponse(success=True, data={"name": vpn_name})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"VPN instance 删除失败: device_id={device_id}, name={vpn_name}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vpn_instance_delete",
                   f"删除 VPN instance {vpn_name} 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ============ 接口 ↔ VPN instance 绑定端点 ============


@router.post("/devices/{device_id}/interfaces/{if_index}/vpn-instance", response_model=APIResponse)
def bind_interface_vpn(device_id: int, if_index: int, body: InterfaceVpnBind,
                       db: Session = Depends(get_db)):
    """接口绑 VPN instance（受保护接口拦截 + NETCONF 优先）"""
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # 受保护接口护栏
    protected = _get_protected_interfaces(device)
    if if_index in protected:
        msg = f"接口 if_index={if_index} 在保护列表中，禁止绑定 VPN instance"
        logger.warning(f"接口绑 VPN 被保护拦截: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "vpn_instance_bind",
                   f"接口 if_index={if_index} 绑 VPN {body.name} 被保护拦截", "failed", error_message=msg)
        return APIResponse(success=False, error=msg)

    vpn_name = body.name.strip()
    if not vpn_name:
        return APIResponse(success=False, error="缺少必填字段: name")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 预校验：VPN instance 是否存在
            existing = parse_vpn_instances(client.get_config(build_vpn_instance_filter_xml()))["instances"]
            if not any(v["name"] == vpn_name for v in existing):
                return APIResponse(success=False, error=f"VPN instance {vpn_name} 不存在，请先创建")

            config_xml = build_interface_bind_vpn_xml(if_index, vpn_name)
            client.edit_config(config_xml)

        logger.info(f"接口绑 VPN 成功: device_id={device_id}, if_index={if_index}, vpn={vpn_name}")
        record_log(db, device.id, device.name, "vpn_instance_bind",
                   f"接口 if_index={if_index} 绑 VPN {vpn_name}", "success")
        return APIResponse(success=True, data={"if_index": if_index, "vpn_instance": vpn_name})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"接口绑 VPN 失败: device_id={device_id}, if_index={if_index}, vpn={vpn_name}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vpn_instance_bind",
                   f"接口 if_index={if_index} 绑 VPN {vpn_name} 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


@router.delete("/devices/{device_id}/interfaces/{if_index}/vpn-instance", response_model=APIResponse)
def unbind_interface_vpn(device_id: int, if_index: int, db: Session = Depends(get_db)):
    """接口解绑 VPN instance

    v2.2.1 修复（fix-vpn-and-l2l3-ux-bugs）：
    预校验必须能正确读到接口的 vpn_instance。原实现调
    build_interface_extended_filter_xml()（**只**查 Ifmgr），导致
    _parse_interface_response 的 Pass 3 (Bind 解析) 永远拿不到数据，
    vpn_instance 永远 None → 误判"未绑定"。

    改用两次 get_config（Ifmgr+IPV4ADDRESS + L3vpn），合并 vpn_by_idx。
    """
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # Pass A: 查 Ifmgr + IPV4ADDRESS（拿到接口列表 + IP）
            iface_xml = client.get_config(_IFACE_FILTERS_FOR_UNBIND)
            current_ifaces = _parse_interface_response(iface_xml)
            target = next((i for i in current_ifaces if i["if_index"] == if_index), None)
            if not target:
                return APIResponse(success=False, error=f"接口 if_index={if_index} 不存在")

            # Pass B: 查 L3vpn 拿 Bind 列表（v2.2.1 修复关键点）
            vpn_bindings = _parse_vpn_bindings_by_ifindex(
                client.get_config(build_vpn_instance_filter_xml())
            )
            # 合并：把 vpn_bindings 注入 target
            target_vpn = vpn_bindings.get(if_index)
            if not target_vpn:
                return APIResponse(success=False, error=f"接口 if_index={if_index} 未绑定 VPN instance")

            # 同时记日志用
            target["vpn_instance"] = target_vpn

            # Pass C: 真正的 edit-config（带 vpn_name 唯一定位 Bind 条目）
            config_xml = build_interface_unbind_vpn_xml(if_index, target_vpn)
            client.edit_config(config_xml)

        logger.info(f"接口解绑 VPN 成功: device_id={device_id}, if_index={if_index}, vpn={target_vpn}")
        record_log(db, device.id, device.name, "vpn_instance_unbind",
                   f"接口 if_index={if_index} 解绑 VPN {target_vpn}", "success")
        return APIResponse(success=True, data={"if_index": if_index, "vpn_instance": target_vpn})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"接口解绑 VPN 失败: device_id={device_id}, if_index={if_index}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vpn_instance_unbind",
                   f"接口 if_index={if_index} 解绑 VPN 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ============================================================
# v2.2.2 patch: 调整 link type + 配 IP
# ============================================================


class LinkTypeChange(BaseModel):
    """调整接口 link type (mode)"""
    mode: Literal["access", "trunk"] = Field(..., description="新 mode：access 或 trunk")
    force: bool = Field(default=False, description="强制配置被保护接口（高风险）")


class LinkModeSwitch(BaseModel):
    """切换接口 L2/L3 层级（bridge/route）

    v2.3 新增：走 SSH CLI（`port link-mode` 命令），NETCONF 不支持。
    """
    mode: Literal["bridge", "route"] = Field(..., description="bridge=二层 / route=三层")
    force: bool = Field(default=False, description="强制切换（跳过二次确认）")


class Ipv4AddressSet(BaseModel):
    """给 L3 接口设置/替换 IPv4 地址"""
    ip: str = Field(..., description="点分十进制 IPv4，如 192.168.1.1")
    mask: str = Field(..., description="点分十进制 mask，如 255.255.255.0")


def _is_valid_ipv4(ip: str) -> bool:
    """校验 IPv4 格式：4 段 0-255"""
    if not ip:
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        n = int(p)
        if n < 0 or n > 255:
            return False
    return True


def _is_valid_mask(mask: str) -> bool:
    """校验 mask 格式：连续 1 后跟连续 0（如 255.255.255.0 合法，255.0.255.0 非法）"""
    if not _is_valid_ipv4(mask):
        return False
    parts = [int(p) for p in mask.split(".")]
    n = 0
    for p in parts:
        n = (n << 8) | p
    # 计算 1 的个数 + 0 的个数
    bit_str = format(n, "032b")
    if "01" in bit_str:
        return False  # 出现 0 后又有 1，非法
    return True


def _query_current_mode(client: NetconfClient, if_index: int) -> str | None:
    """查接口当前 link type（access/trunk/hybrid），不存在返回 None

    重要（H3C V7 实际行为）：
    - L2 接口（Ifmgr 返回 + IPV4ADDRESS 无）：如果有 LinkType 字段就用，没有就**默认 access**（多数 L2 access 不显式设）
    - L3 接口（Ifmgr 可能不返回 / 或返回但绑了 VPN）：L3 接口无 mode 概念，**返回 None**
    - 接口完全不存在：返回 None

    用 Ifmgr + IPV4ADDRESS 合并查询判断接口是 L2 还是 L3。
    """
    combined_filter = (
        f'<top xmlns="{H3C_CONFIG_NS}">'
        '<Ifmgr><Interfaces/></Ifmgr>'
        '<IPV4ADDRESS></IPV4ADDRESS>'
        '</top>'
    )
    response_xml = client.get_config(combined_filter)
    root = ET.fromstring(response_xml)

    # 1) 扫 Ifmgr 找 LinkType（如果存在）
    found_in_ifmgr = False
    current_mode: str | None = None
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag != "Interface":
            continue
        cur_idx = None
        link_type_raw = None
        for child in elem:
            ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ct == "IfIndex" and child.text:
                try:
                    cur_idx = int(child.text)
                except ValueError:
                    cur_idx = None
            elif ct == "LinkType" and child.text:
                link_type_raw = child.text
        if cur_idx == if_index:
            found_in_ifmgr = True
            if link_type_raw is not None:
                try:
                    current_mode = LINK_TYPE_REVERSE.get(int(link_type_raw))
                except ValueError:
                    current_mode = None
            break

    # 2) 扫 IPV4ADDRESS 判断是否 L3-only（L3 接口 ifmgr 可能不返回）
    found_in_ipv4 = False
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag != "Ipv4Address":
            continue
        for child in elem:
            ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ct == "IfIndex" and child.text:
                try:
                    if int(child.text) == if_index:
                        found_in_ipv4 = True
                except ValueError:
                    pass

    if not found_in_ifmgr and not found_in_ipv4:
        return None  # 接口不存在

    # Ifmgr 有 + IPV4ADDRESS 无 → L2 接口
    if found_in_ifmgr and not found_in_ipv4:
        return current_mode if current_mode is not None else "access"  # 缺省为 access

    # Ifmgr 无 + IPV4ADDRESS 有 → L3-only 接口（无 mode 概念，不能切 link type）
    if not found_in_ifmgr and found_in_ipv4:
        return None

    # Ifmgr 有 + IPV4ADDRESS 也有 → 这是 L3 接口在 Ifmgr 里也返回了（如某些三层物理口）
    # 比如 192.168.100.5 上的 5129 物理口（绑 Vlan12），但 LinkType 字段可能存在
    # 这种接口切 link type 也是有意义的，按 L2 处理（如果 LinkType 字段存在）
    if found_in_ifmgr and found_in_ipv4:
        return current_mode  # None 表示"无 mode" / L3-only 语义上不能切


def _check_l3_interface(client: NetconfClient, if_index: int) -> tuple[bool, str]:
    """校验接口是否为 L3（H3C V7 三模块合并：IPV4ADDRESS / L3vpn / Vlan-interface 名称）

    Returns: (is_l3, error_msg)
    - is_l3=True: 是 L3 接口
    - is_l3=False: 不是 L3 接口（error_msg 含原因）
    """
    # 一次查三模块
    combined_filter = (
        f'<top xmlns="{H3C_CONFIG_NS}">'
        '<Ifmgr><Interfaces/></Ifmgr>'
        '<IPV4ADDRESS></IPV4ADDRESS>'
        '<L3vpn></L3vpn>'
        '</top>'
    )
    response_xml = client.get_config(combined_filter)
    ifaces = _parse_interface_response(response_xml)
    target = next((i for i in ifaces if i["if_index"] == if_index), None)
    if not target:
        return False, f"接口 if_index={if_index} 不存在"
    if target.get("layer") != "L3":
        return False, f"接口 if_index={if_index} 不是 L3 接口，无法配置 IP"
    return True, ""


# ============ 调整 link type (mode) ============


@router.patch("/devices/{device_id}/interfaces/{if_index}/link-type", response_model=APIResponse)
def change_link_type(device_id: int, if_index: int, body: LinkTypeChange,
                     db: Session = Depends(get_db)):
    """调整接口 link type (access/trunk)

    v2.2.2 patch (fix-vpn-edit-capabilities)：
    - 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝，force=true 时允许
    - 预校验：当前 mode == new_mode 直接 400（无需切换）
    - H3C V7 行为：mode 切换会清空该接口已有配置（access_vlan / pvid / allowed_vlans），
      后端**不**做"会清空什么"的预测，由前端 modal 提示用户
    """
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # 受保护接口护栏
    protected = _get_protected_interfaces(device)
    if if_index in protected and not body.force:
        msg = f"接口 if_index={if_index} 是受保护口，需要 force=true 才能继续"
        logger.warning(f"改 link type 被保护拦截: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "link_type_change",
                   f"改 link type if_index={if_index} -> {body.mode} 被保护拦截",
                   "failed", error_message=msg)
        return APIResponse(success=False, error=msg)
    if if_index in protected and body.force:
        logger.warning(f"改 link type force=true 强制通过保护: device_id={device_id}, if_index={if_index}")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 预校验：当前 mode
            current_mode = _query_current_mode(client, if_index)
            if current_mode is None:
                # 区分 L3 接口（不能切 link type） vs 接口不存在
                # 复用 _check_l3_interface 判定
                is_l3, l3_err = _check_l3_interface(client, if_index)
                if is_l3:
                    return APIResponse(
                        success=False,
                        error=f"接口 if_index={if_index} 是 L3 接口，无 link type 概念，无法切换 mode",
                    )
                return APIResponse(success=False, error=f"接口 if_index={if_index} 不存在")
            if current_mode == body.mode:
                return APIResponse(
                    success=False,
                    error=f"接口 if_index={if_index} 当前 mode 已经是 {body.mode}，无需切换",
                )

            # 下发配置
            config_xml = build_link_type_change_xml(if_index, body.mode, force=body.force)
            client.edit_config(config_xml)

        logger.info(f"改 link type 成功: device_id={device_id}, if_index={if_index}, "
                    f"{current_mode} -> {body.mode}")
        record_log(db, device.id, device.name, "link_type_change",
                   f"改 link type if_index={if_index}: {current_mode} -> {body.mode}", "success")
        return APIResponse(
            success=True,
            data={"if_index": if_index, "old_mode": current_mode, "new_mode": body.mode},
        )
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"改 link type 失败: device_id={device_id}, if_index={if_index}, 原因={error_msg}",
                     exc_info=True)
        record_log(db, device.id, device.name, "link_type_change",
                   f"改 link type if_index={if_index} -> {body.mode} 失败",
                   "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ============ 切换 L2/L3 层级（v2.3） ============


@router.patch("/devices/{device_id}/interfaces/{if_index}/link-mode", response_model=APIResponse)
def switch_link_mode(device_id: int, if_index: int, body: LinkModeSwitch,
                     db: Session = Depends(get_db)):
    """切换接口 L2/L3 层级（bridge ↔ route）

    v2.3 新增：走 SSH CLI（`port link-mode` 命令），NETCONF 不支持此操作。
    - bridge：接口工作在二层模式
    - route：接口工作在三层模式（会清 L2 配置，如 VLAN / trunk）
    - 受保护接口护栏：force=true 才能跳过
    - 二次确认：force=false 时返回确认提示，前端弹 Modal 确认后 force=true 再调用
    """
    from app.utils.ssh_executor import SSHExecutor

    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # 受保护接口护栏
    protected = _get_protected_interfaces(device)
    if if_index in protected and not body.force:
        msg = f"接口 if_index={if_index} 是受保护口，需要 force=true 才能继续"
        logger.warning(f"切 link mode 被保护拦截: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "link_mode_switch",
                   f"切 link mode if_index={if_index} -> {body.mode} 被保护拦截",
                   "failed", error_message=msg)
        return APIResponse(success=False, error=msg)
    if if_index in protected and body.force:
        logger.warning(f"切 link mode force=true 强制通过保护: device_id={device_id}, if_index={if_index}")

    # 二次确认（force=false 时返回确认提示，不执行）
    if not body.force:
        return APIResponse(
            success=True,
            data={
                "if_index": if_index,
                "mode": body.mode,
                "confirmed": False,
                "message": f"即将切换接口 if_index={if_index} 到 {body.mode} 模式。"
                           f"此操作会{'清空 L2 配置（VLAN/trunk）' if body.mode == 'route' else '清空 L3 配置（IP）'}，"
                           f"请确认后 force=true 重新调用",
            },
        )

    # v2.3 修复：先用 NETCONF 查接口真实 name（if_index ≠ name 数字），再用 SSH 22 CLI 改
    # H3C V7：port 22 = SSH CLI（link-mode 走这条）；port 830 = NETCONF（无 link-mode）
    try:
        from app.netconf_client import NetconfClient
        nc = NetconfClient(
            host=device.host,
            port=device.port,
            username=device.username,
            password=password,
        )
        nc.connect()
        try:
            name = nc.get_interface_name_by_index(if_index)
        finally:
            nc.disconnect()
    except Exception as e:
        error_msg = f"NETCONF 查接口名失败 if_index={if_index}: {e}"
        logger.error(error_msg)
        record_log(db, device.id, device.name, "link_mode_switch",
                   f"切 link mode if_index={if_index} -> {body.mode} 失败（NETCONF 查 name）",
                   "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)

    if not name:
        error_msg = f"接口不存在 if_index={if_index}"
        logger.error(f"切 link mode 失败: {error_msg}")
        record_log(db, device.id, device.name, "link_mode_switch",
                   f"切 link mode if_index={if_index} -> {body.mode} 失败（接口不存在）",
                   "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)

    # 执行 SSH CLI（强制走 22，NETCONF 不支持 link-mode）
    ssh = SSHExecutor(
        host=device.host,
        port=22,
        username=device.username,
        password=password,
        timeout=30,
    )

    # 切到 system-view → 进入接口 → 改 link-mode
    commands = [
        "system-view",
        f"interface {name}",
        f"port link-mode {body.mode}",
    ]
    results = ssh.execute_commands(commands, delay_ms=500)

    # 检查结果
    for r in results:
        if not r["success"]:
            error_msg = f"SSH CLI 失败: {r.get('cmd', '?')} -> {(r.get('error') or r.get('output', ''))[:200]}"
            logger.error(f"切 link mode 失败: device_id={device_id}, if_index={if_index}, {error_msg}")
            record_log(db, device.id, device.name, "link_mode_switch",
                       f"切 link mode if_index={if_index} -> {body.mode} 失败",
                       "failed", error_message=error_msg)
            return APIResponse(success=False, error=error_msg)

    logger.info(f"切 link mode 成功: device_id={device_id}, if_index={if_index}, -> {body.mode}")
    record_log(db, device.id, device.name, "link_mode_switch",
               f"切 link mode if_index={if_index} -> {body.mode}", "success")
    return APIResponse(
        success=True,
        data={"if_index": if_index, "mode": body.mode, "confirmed": True},
    )


def _parse_if_name_for_cli(if_index: int) -> str:
    """把 if_index 转成 H3C 接口名（如 100 -> GigabitEthernet1/0/1）

    简化映射：if_index 的最后两位是端口号，前面是槽位号。
    """
    port = if_index % 100
    slot = if_index // 100
    return f"GigabitEthernet{slot}/0/{port}"


# ============ 设置/替换 IPv4 地址 ============


@router.post("/devices/{device_id}/interfaces/{if_index}/ipv4-address", response_model=APIResponse)
def set_interface_ipv4(device_id: int, if_index: int, body: Ipv4AddressSet,
                       db: Session = Depends(get_db)):
    """给 L3 接口设置/替换 IPv4 地址（clear + set 两步 edit-config）

    v2.2.2 patch (fix-vpn-edit-capabilities)：
    - layer=L3 校验：不是 L3 → 400
    - 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝
    - IP/mask 格式校验
    - clear + set 模式：H3C V7 IPV4ADDRESS 模型下，set 不会自动清空原条目
    """
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # IP/mask 格式校验
    if not _is_valid_ipv4(body.ip):
        return APIResponse(success=False, error=f"IP 格式非法: {body.ip!r}（必须 4 段 0-255）")
    if not _is_valid_mask(body.mask):
        return APIResponse(
            success=False,
            error=f"mask 格式非法: {body.mask!r}（必须是连续 1 后跟连续 0，如 255.255.255.0）",
        )

    # 受保护接口护栏
    protected = _get_protected_interfaces(device)
    if if_index in protected:
        msg = f"接口 if_index={if_index} 是受保护口，禁止配置 IP"
        logger.warning(f"配 IP 被保护拦截: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "ipv4_address_set",
                   f"接口 if_index={if_index} 配 IP 被保护拦截", "failed", error_message=msg)
        return APIResponse(success=False, error=msg)

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # L3 校验
            is_l3, l3_err = _check_l3_interface(client, if_index)
            if not is_l3:
                return APIResponse(success=False, error=l3_err)

            # clear + set 两步 edit-config
            clear_xml = build_ipv4_address_clear_xml(if_index)
            client.edit_config(clear_xml)

            set_xml = build_ipv4_address_set_xml(if_index, body.ip, body.mask)
            client.edit_config(set_xml)

        logger.info(f"配 IP 成功: device_id={device_id}, if_index={if_index}, ip={body.ip}/{body.mask}")
        record_log(db, device.id, device.name, "ipv4_address_set",
                   f"接口 if_index={if_index} 配 IP {body.ip}/{body.mask}", "success")
        return APIResponse(
            success=True,
            data={"if_index": if_index, "ip": body.ip, "mask": body.mask},
        )
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"配 IP 失败: device_id={device_id}, if_index={if_index}, 原因={error_msg}",
                     exc_info=True)
        record_log(db, device.id, device.name, "ipv4_address_set",
                   f"接口 if_index={if_index} 配 IP 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ============ 清空 IPv4 地址 ============


@router.delete("/devices/{device_id}/interfaces/{if_index}/ipv4-address", response_model=APIResponse)
def clear_interface_ipv4(device_id: int, if_index: int, db: Session = Depends(get_db)):
    """清空 L3 接口的所有 IPv4 地址

    v2.2.2 patch (fix-vpn-edit-capabilities)：
    - layer=L3 校验：不是 L3 → 400
    - 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝
    """
    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    # 受保护接口护栏
    protected = _get_protected_interfaces(device)
    if if_index in protected:
        msg = f"接口 if_index={if_index} 是受保护口，禁止清空 IP"
        logger.warning(f"清空 IP 被保护拦截: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "ipv4_address_clear",
                   f"接口 if_index={if_index} 清空 IP 被保护拦截", "failed", error_message=msg)
        return APIResponse(success=False, error=msg)

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # L3 校验
            is_l3, l3_err = _check_l3_interface(client, if_index)
            if not is_l3:
                return APIResponse(success=False, error=l3_err)

            # 清空
            clear_xml = build_ipv4_address_clear_xml(if_index)
            client.edit_config(clear_xml)

        logger.info(f"清空 IP 成功: device_id={device_id}, if_index={if_index}")
        record_log(db, device.id, device.name, "ipv4_address_clear",
                   f"接口 if_index={if_index} 清空 IP", "success")
        return APIResponse(success=True, data={"if_index": if_index})
    except Exception as e:
        error_msg = _classify_interface_error(e)
        logger.error(f"清空 IP 失败: device_id={device_id}, if_index={if_index}, 原因={error_msg}",
                     exc_info=True)
        record_log(db, device.id, device.name, "ipv4_address_clear",
                   f"接口 if_index={if_index} 清空 IP 失败", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)
