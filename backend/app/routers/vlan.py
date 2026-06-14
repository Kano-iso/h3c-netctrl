import logging
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import APIResponse, VLANCreate, VLANResponse, VLANUpdate
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["vlan"])

# H3C VLAN 命名空间（通过实际设备探测确认）
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"


def _get_device_and_password(db: Session, device_id: int):
    """根据设备 ID 获取设备信息和解密密码"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return None, None, APIResponse(success=False, error=f"设备不存在: id={device_id}")
    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return None, None, APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")
    return device, password, None


def _build_vlan_filter_xml() -> str:
    """构造 H3C VLAN get-config filter XML（简单 VLAN 标签即可）"""
    return f'<top xmlns="{H3C_CONFIG_NS}"><VLAN></VLAN></top>'


def _parse_vlan_response(xml_str: str) -> list[dict]:
    """解析 H3C VLAN get-config 响应 XML

    实际响应结构:
    <VLANs>
      <VLANID><ID>1</ID></VLANID>
      <VLANID><ID>100</ID><AccessPortList>2-21</AccessPortList>...</VLANID>
    </VLANs>
    """
    vlans = []
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "VLANID":
                vlan_id = None
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "ID":
                        vlan_id = int(child.text) if child.text else None
                if vlan_id is not None:
                    vlans.append({"vlan_id": vlan_id, "name": f"VLAN {vlan_id}"})
    except ET.ParseError as e:
        logger.error(f"VLAN XML 解析失败: {e}")
    return vlans


def _build_vlan_create_xml(vlan_id: int, name: str) -> str:
    """构造 H3C VLAN 创建 edit-config XML

    H3C VLAN 创建使用 VLANs/VLANID/ID 结构
    """
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <VLAN>
                <VLANs>
                    <VLANID>
                        <ID>{vlan_id}</ID>
                    </VLANID>
                </VLANs>
            </VLAN>
        </top>
    </config>
    """


def _build_vlan_delete_xml(vlan_id: int) -> str:
    """构造 H3C VLAN 删除 edit-config XML"""
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <VLAN>
                <VLANs xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <VLANID xc:operation="delete">
                        <ID>{vlan_id}</ID>
                    </VLANID>
                </VLANs>
            </VLAN>
        </top>
    </config>
    """


# ========== v1.1 多设备 VLAN 路由 ==========


@router.get("/devices/{device_id}/vlans", response_model=APIResponse)
def get_vlans(device_id: int, db: Session = Depends(get_db)):
    """查询指定设备的 VLAN 列表"""
    device, password, error = _get_device_and_password(db, device_id)
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
        logger.info(f"VLAN查询成功: device_id={device_id}, 获取到 {len(vlans)} 个VLAN")
        return APIResponse(success=True, data=vlans)
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.error(f"VLAN查询失败: device_id={device_id}, 原因={error_msg}", exc_info=True)
        return APIResponse(success=False, error=error_msg)


@router.post("/devices/{device_id}/vlans", response_model=APIResponse)
def create_vlan(device_id: int, body: VLANCreate, db: Session = Depends(get_db)):
    """在指定设备上创建 VLAN"""
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")

    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            for v in existing_vlans:
                if v["vlan_id"] == body.vlan_id:
                    return APIResponse(success=False, error=f"VLAN {body.vlan_id}已存在")

            config_xml = _build_vlan_create_xml(body.vlan_id, body.name)
            client.edit_config(config_xml)

        logger.info(f"VLAN创建成功: device_id={device_id}, vlan_id={body.vlan_id}, name={body.name}")
        record_log(db, device.id, device.name, "vlan_create", f"创建 VLAN {body.vlan_id} (name={body.name})", "success")
        return APIResponse(success=True, data={"vlan_id": body.vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.error(f"VLAN创建失败: device_id={device_id}, vlan_id={body.vlan_id}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vlan_create", f"创建 VLAN {body.vlan_id} (name={body.name})", "failed")
        return APIResponse(success=False, error=error_msg)


@router.put("/devices/{device_id}/vlans/{vlan_id}", response_model=APIResponse)
def update_vlan(device_id: int, vlan_id: int, body: VLANUpdate, db: Session = Depends(get_db)):
    """修改指定设备上的 VLAN 名称"""
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            config_xml = _build_vlan_create_xml(vlan_id, body.name)
            client.edit_config(config_xml)

        logger.info(f"VLAN修改成功: device_id={device_id}, vlan_id={vlan_id}, name={body.name}")
        record_log(db, device.id, device.name, "vlan_update", f"修改 VLAN {vlan_id} (name={body.name})", "success")
        return APIResponse(success=True, data={"vlan_id": vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.error(f"VLAN修改失败: device_id={device_id}, vlan_id={vlan_id}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vlan_update", f"修改 VLAN {vlan_id} (name={body.name})", "failed")
        return APIResponse(success=False, error=error_msg)


@router.delete("/devices/{device_id}/vlans/{vlan_id}", response_model=APIResponse)
def delete_vlan(device_id: int, vlan_id: int, db: Session = Depends(get_db)):
    """删除指定设备上的 VLAN"""
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device, password, error = _get_device_and_password(db, device_id)
    if error:
        return error

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            config_xml = _build_vlan_delete_xml(vlan_id)
            client.edit_config(config_xml)

        logger.info(f"VLAN删除成功: device_id={device_id}, vlan_id={vlan_id}")
        record_log(db, device.id, device.name, "vlan_delete", f"删除 VLAN {vlan_id}", "success")
        return APIResponse(success=True, data={"message": f"VLAN {vlan_id}已删除"})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        logger.error(f"VLAN删除失败: device_id={device_id}, vlan_id={vlan_id}, 原因={error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "vlan_delete", f"删除 VLAN {vlan_id}", "failed")
        return APIResponse(success=False, error=error_msg)


# ========== v1.0 兼容路由（deprecated） ==========


@router.get("/vlans", response_model=APIResponse, deprecated=True)
def compat_get_vlans(db: Session = Depends(get_db)):
    """[已弃用] 查询VLAN，请使用 GET /api/devices/{id}/vlans"""
    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)

        vlans = _parse_vlan_response(response_xml)
        return APIResponse(success=True, data=vlans)
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        return APIResponse(success=False, error=error_msg)


@router.post("/vlans", response_model=APIResponse, deprecated=True)
def compat_create_vlan(body: VLANCreate, db: Session = Depends(get_db)):
    """[已弃用] 创建VLAN，请使用 POST /api/devices/{id}/vlans"""
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")

    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            for v in existing_vlans:
                if v["vlan_id"] == body.vlan_id:
                    return APIResponse(success=False, error=f"VLAN {body.vlan_id}已存在")

            config_xml = _build_vlan_create_xml(body.vlan_id, body.name)
            client.edit_config(config_xml)

        return APIResponse(success=True, data={"vlan_id": body.vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        return APIResponse(success=False, error=error_msg)


@router.put("/vlans/{vlan_id}", response_model=APIResponse, deprecated=True)
def compat_update_vlan(vlan_id: int, body: VLANUpdate, db: Session = Depends(get_db)):
    """[已弃用] 修改VLAN，请使用 PUT /api/devices/{id}/vlans/{vlan_id}"""
    if not body.name:
        return APIResponse(success=False, error="缺少必填字段: name")
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            config_xml = _build_vlan_create_xml(vlan_id, body.name)
            client.edit_config(config_xml)

        return APIResponse(success=True, data={"vlan_id": vlan_id, "name": body.name})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
        return APIResponse(success=False, error=error_msg)


@router.delete("/vlans/{vlan_id}", response_model=APIResponse, deprecated=True)
def compat_delete_vlan(vlan_id: int, db: Session = Depends(get_db)):
    """[已弃用] 删除VLAN，请使用 DELETE /api/devices/{id}/vlans/{vlan_id}"""
    if vlan_id < 1 or vlan_id > 4094:
        return APIResponse(success=False, error="VLAN ID必须在1-4094范围内")

    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")

    try:
        with NetconfClient(
            host=device.host, port=device.port,
            username=device.username, password=password,
        ) as client:
            filter_xml = _build_vlan_filter_xml()
            response_xml = client.get_config(filter_xml)
            existing_vlans = _parse_vlan_response(response_xml)

            vlan_exists = any(v["vlan_id"] == vlan_id for v in existing_vlans)
            if not vlan_exists:
                return APIResponse(success=False, error=f"VLAN {vlan_id}不存在")

            config_xml = _build_vlan_delete_xml(vlan_id)
            client.edit_config(config_xml)

        return APIResponse(success=True, data={"message": f"VLAN {vlan_id}已删除"})
    except Exception as e:
        error_msg = _classify_vlan_error(e)
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
    if "already exist" in msg.lower() or "already exists" in msg.lower():
        return "VLAN已存在"
    if "not found" in msg.lower() or "does not exist" in msg.lower():
        return "VLAN不存在"
    if "denied" in msg.lower() or "not allowed" in msg.lower():
        return "操作被拒绝"
    return msg
