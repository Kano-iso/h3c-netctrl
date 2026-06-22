import logging
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import APIResponse
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["interface"])

# H3C 命名空间（与 vlan.py 一致）
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"

# LinkType 映射
LINK_TYPE_MAP = {"access": 1, "trunk": 2, "hybrid": 3}
LINK_TYPE_REVERSE = {1: "access", 2: "trunk", 3: "hybrid"}


class InterfaceConfig(BaseModel):
    if_index: int  # NETCONF 接口索引（从查询接口列表获取）
    mode: str  # "access" or "trunk"
    access_vlan: Optional[int] = None
    allowed_vlans: Optional[List[int]] = None
    pvid: Optional[int] = None


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
    """解析 H3C Ifmgr get-config 响应 XML

    H3C Ifmgr 按需返回字段，部分接口可能只有 IfIndex，没有 Name/LinkType。
    只要 IfIndex 存在就保留，缺失字段用合理默认值填充。
    """
    interfaces = []
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "Interface":
                iface = {}
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "IfIndex":
                        iface["if_index"] = int(child.text) if child.text else None
                    elif child_tag == "Name":
                        iface["name"] = child.text or ""
                    elif child_tag == "LinkType":
                        link_type = int(child.text) if child.text else 1
                        iface["mode"] = LINK_TYPE_REVERSE.get(link_type, "access")
                    elif child_tag == "PVID":
                        iface["pvid"] = int(child.text) if child.text else None
                    elif child_tag == "TrunkVLANs":
                        iface["allowed_vlans"] = _parse_vlan_range(child.text or "")
                    elif child_tag == "AdminStatus":
                        iface["status"] = "up" if child.text == "1" else "down"
                # 只检查 if_index，缺失字段用默认值
                if iface.get("if_index"):
                    # Name 缺失时用 IfIndex 生成
                    if not iface.get("name"):
                        iface["name"] = f"If-{iface['if_index']}"
                    # LinkType 缺失时默认 access
                    iface.setdefault("mode", "access")
                    # access_vlan 字段
                    if iface.get("mode") == "access" and iface.get("pvid"):
                        iface["access_vlan"] = iface["pvid"]
                    else:
                        iface["access_vlan"] = None
                    iface.setdefault("status", "unknown")
                    iface.setdefault("allowed_vlans", [])
                    interfaces.append(iface)
    except ET.ParseError as e:
        logger.error(f"接口 XML 解析失败: {e}")
    return interfaces


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
    from ncclient.operations.rpc import RPCError

    error_str = str(error)

    # 设备连接类错误
    conn_msg = classify_connection_error(error)
    if conn_msg != f"连接失败: {error_str}":
        return f"设备连接失败: {conn_msg}"

    # NETCONF RPC 错误
    if isinstance(error, RPCError):
        msg = str(error.message) if hasattr(error, "message") else str(error)
        if "not support" in msg.lower():
            return f"设备不支持此操作: {msg}"
        if "denied" in msg.lower():
            return "操作被拒绝"
        return f"设备返回错误: {msg}"

    if "timeout" in error_str.lower():
        return "设备响应超时，请检查网络连接或设备状态"

    return f"操作失败: {error_str}"


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
            filter_xml = _build_interface_filter_xml()
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

    try:
        config_xml = _build_interface_config_xml(
            if_index=body.if_index,
            mode=body.mode,
            access_vlan=body.access_vlan,
            allowed_vlans=body.allowed_vlans,
            pvid=body.pvid,
        )

        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
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
