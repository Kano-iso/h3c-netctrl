import logging
import re
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import APIResponse, VLANCreate, VLANResponse, VLANUpdate
from app.utils.crypto import decrypt_password

logger = logging.getLogger("app")

router = APIRouter(tags=["vlan"])

# H3C VLAN YANG namespace
H3C_VLAN_NS = "http://www.h3c.com/netconf/conf:vg"
H3C_VLAN_NS_PREFIX = "h3c"


def _get_device_and_password(db: Session):
    """获取设备信息和解密密码，失败时返回错误响应元组"""
    device = db.query(Device).first()
    if not device:
        return None, None, APIResponse(success=False, error="未配置设备，请先添加设备信息")
    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return None, None, APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")
    return device, password, None


def _build_vlan_filter_xml() -> str:
    """构造 H3C VLAN get-config filter XML"""
    return f"""
    <top xmlns="{H3C_VLAN_NS}">
        <Vlan>
            <VlanInterfaces>
                <VlanInterface>
                    <VlanID></VlanID>
                    <Name></Name>
                </VlanInterface>
            </VlanInterfaces>
        </Vlan>
    </top>
    """


def _parse_vlan_response(xml_str: str) -> list[dict]:
    """解析 H3C VLAN get-config 响应 XML，提取 vlan_id 和 name"""
    vlans = []
    try:
        root = ET.fromstring(xml_str)
        # 在 XML 中查找所有 VlanInterface 元素
        # H3C namespace 可能出现在各种位置
        for elem in root.iter():
            if elem.tag.endswith("VlanInterface") or elem.tag == "VlanInterface":
                vlan_id = None
                name = None
                for child in elem:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "VlanID":
                        vlan_id = int(child.text) if child.text else None
                    elif tag == "Name":
                        name = child.text or ""
                if vlan_id is not None:
                    vlans.append({"vlan_id": vlan_id, "name": name})
    except ET.ParseError as e:
        logger.error(f"VLAN XML 解析失败: {e}")
    return vlans


def _build_vlan_create_xml(vlan_id: int, name: str) -> str:
    """构造 H3C VLAN 创建 edit-config XML"""
    return f"""
    <config>
        <top xmlns="{H3C_VLAN_NS}">
            <Vlan>
                <VlanInterfaces>
                    <VlanInterface>
                        <VlanID>{vlan_id}</VlanID>
                        <Name>{name}</Name>
                    </VlanInterface>
                </VlanInterfaces>
            </Vlan>
        </top>
    </config>
    """


def _build_vlan_delete_xml(vlan_id: int) -> str:
    """构造 H3C VLAN 删除 edit-config XML"""
    return f"""
    <config>
        <top xmlns="{H3C_VLAN_NS}">
            <Vlan>
                <VlanInterfaces>
                    <VlanInterface xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0" xc:operation="delete">
                        <VlanID>{vlan_id}</VlanID>
                    </VlanInterface>
                </VlanInterfaces>
            </Vlan>
        </top>
    </config>
    """


@router.get("/vlans", response_model=APIResponse)
def get_vlans(db: Session = Depends(get_db)):
    """查询设备上所有 VLAN"""
    device, password, error = _get_device_and_password(db)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)

        vlans = _parse_vlan_response(response_xml)
        logger.info(f"VLAN查询成功: 获取到 {len(vlans)} 个VLAN")
        return APIResponse(success=True, data=vlans)
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.info(f"VLAN查询失败: {error_msg}")
        return APIResponse(success=False, error=error_msg)


@router.post("/vlans", response_model=APIResponse)
def create_vlan(body: VLANCreate, db: Session = Depends(get_db)):
    """创建 VLAN"""
    # 输入校验
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")

    device, password, error = _get_device_and_password(db)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 先查询是否已存在
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            for v in existing_vlans:
                if v["vlan_id"] == body.vlan_id:
                    return APIResponse(success=False, error=f"VLAN {body.vlan_id}已存在")

            # 创建 VLAN
            config_xml = _build_vlan_create_xml(body.vlan_id, body.name)
            client.edit_config(config_xml)

        logger.info(f"VLAN创建成功: vlan_id={body.vlan_id}, name={body.name}")
        return APIResponse(success=True, data={"vlan_id": body.vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.info(f"VLAN创建失败: vlan_id={body.vlan_id}, 原因={error_msg}")
        return APIResponse(success=False, error=error_msg)


@router.put("/vlans/{vlan_id}", response_model=APIResponse)
def update_vlan(vlan_id: int, body: VLANUpdate, db: Session = Depends(get_db)):
    """修改 VLAN 名称"""
    # 输入校验
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device, password, error = _get_device_and_password(db)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 先查询 VLAN 是否存在
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            # 修改 VLAN 名称（merge 操作）
            config_xml = _build_vlan_create_xml(vlan_id, body.name)
            client.edit_config(config_xml)

        logger.info(f"VLAN修改成功: vlan_id={vlan_id}, name={body.name}")
        return APIResponse(success=True, data={"vlan_id": vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.info(f"VLAN修改失败: vlan_id={vlan_id}, 原因={error_msg}")
        return APIResponse(success=False, error=error_msg)


@router.delete("/vlans/{vlan_id}", response_model=APIResponse)
def delete_vlan(vlan_id: int, db: Session = Depends(get_db)):
    """删除 VLAN"""
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device, password, error = _get_device_and_password(db)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            # 先查询 VLAN 是否存在
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            # 删除 VLAN
            config_xml = _build_vlan_delete_xml(vlan_id)
            client.edit_config(config_xml)

        logger.info(f"VLAN删除成功: vlan_id={vlan_id}")
        return APIResponse(success=True, data={"message": f"VLAN {vlan_id}已删除"})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.info(f"VLAN删除失败: vlan_id={vlan_id}, 原因={error_msg}")
        return APIResponse(success=False, error=error_msg)


def _classify_vlan_error(error: Exception) -> str:
    """将 VLAN 操作异常分类为可读的中文错误信息"""
    from ncclient.operations.rpc import RPCError

    error_str = str(error)

    # 设备连接类错误
    conn_msg = classify_connection_error(error)
    if conn_msg != f"连接失败: {error_str}":
        return f"设备连接失败: {conn_msg}"

    # NETCONF RPC 错误
    if isinstance(error, RPCError):
        return f"设备返回错误: {_translate_rpc_error(error)}"

    # 超时
    if "timeout" in error_str.lower():
        return "设备响应超时，请检查网络连接或设备状态"

    return f"操作失败: {error_str}"


def _translate_rpc_error(error) -> str:
    """翻译 NETCONF RPC 错误信息"""
    msg = str(error.message) if hasattr(error, "message") else str(error)
    # 常见 H3C 错误翻译
    if "already exist" in msg.lower() or "already exists" in msg.lower():
        return "VLAN已存在"
    if "not found" in msg.lower() or "does not exist" in msg.lower():
        return "VLAN不存在"
    if "denied" in msg.lower() or "not allowed" in msg.lower():
        return "操作被拒绝"
    return msg
