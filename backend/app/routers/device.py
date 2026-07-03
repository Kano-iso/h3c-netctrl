import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import APIResponse, DeviceCreate, DeviceResponse, DeviceUpdate
from app.utils.crypto import decrypt_password, encrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["device"])


def _get_device_or_404(db: Session, device_id: int):
    """根据 ID 获取设备，不存在时返回错误响应元组"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return None, APIResponse(success=False, error=f"设备不存在: id={device_id}")
    return device, None


# ========== 多设备 CRUD（v1.1 主路由） ==========


@router.get("/devices", response_model=APIResponse)
def list_devices(db: Session = Depends(get_db)):
    """获取设备列表"""
    devices = db.query(Device).all()
    data = [DeviceResponse.model_validate(d).model_dump() for d in devices]
    return APIResponse(success=True, data=data)


@router.get("/devices/{device_id}", response_model=APIResponse)
def get_device(device_id: int, db: Session = Depends(get_db)):
    """获取单个设备详情"""
    device, error = _get_device_or_404(db, device_id)
    if error:
        return error
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.post("/devices", response_model=APIResponse)
def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    """添加设备"""
    if not body.host:
        return APIResponse(success=False, error="缺少必填字段: host")
    if not body.username:
        return APIResponse(success=False, error="缺少必填字段: username")
    if not body.password:
        return APIResponse(success=False, error="缺少必填字段: password")

    try:
        encrypted_pwd = encrypt_password(body.password)
    except ValueError as e:
        return APIResponse(success=False, error=str(e))

    device = Device(
        name=body.name,
        host=body.host,
        port=body.port,
        username=body.username,
        password_encrypted=encrypted_pwd,
        protected_interfaces=json.dumps(body.protected_interfaces or []),
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    # 自动创建空资产记录
    from app.models import Asset
    asset = Asset(device_id=device.id, status="unknown")
    db.add(asset)
    db.commit()

    logger.info(f"设备创建成功: id={device.id}, name={device.name}, host={device.host}")
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.put("/devices/{device_id}", response_model=APIResponse)
def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    """更新设备信息"""
    device, error = _get_device_or_404(db, device_id)
    if error:
        return error

    if body.name is not None:
        device.name = body.name
    if body.host is not None:
        device.host = body.host
    if body.port is not None:
        device.port = body.port
    if body.username is not None:
        device.username = body.username
    if body.password is not None:
        try:
            device.password_encrypted = encrypt_password(body.password)
        except ValueError as e:
            return APIResponse(success=False, error=str(e))
    if body.protected_interfaces is not None:
        device.protected_interfaces = json.dumps(body.protected_interfaces)

    db.commit()
    db.refresh(device)

    logger.info(f"设备更新成功: id={device.id}, name={device.name}, host={device.host}, protected={body.protected_interfaces}")
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.delete("/devices/{device_id}", response_model=APIResponse)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    """删除设备

    split 模式（ctrl 容器）：device 行删成功后调 data 容器 cleanup 端点清理关联 asset/backup
    monolith 模式：SQLAlchemy cascade 自动级联清理，不调内部 API
    """
    device, error = _get_device_or_404(db, device_id)
    if error:
        return error

    db.delete(device)
    db.commit()

    logger.info(f"设备删除成功: id={device_id}")

    # split 模式：通知 data 容器清理关联 asset/backup + 备份文件
    # monolith 模式：SQLAlchemy cascade 已自动级联，跳过
    import os
    if os.getenv("SERVICE_NAME") == "ctrl":
        try:
            from app.internal_api import cleanup_device
            cleanup_resp = cleanup_device(device_id)
            logger.info(
                f"split 模式 cleanup 调用成功: device_id={device_id} "
                f"deleted_assets={cleanup_resp.get('data', {}).get('deleted_assets', 0)}"
                f" deleted_backups={cleanup_resp.get('data', {}).get('deleted_backups', 0)}"
            )
            return APIResponse(
                success=True,
                data={
                    "message": f"设备 {device_id} 已删除",
                    "cleanup": cleanup_resp.get("data", {}),
                },
            )
        except Exception as e:
            # 设备已删事实优先，cleanup 失败仅 log warning
            logger.warning(f"split 模式 cleanup 调用失败（已忽略）: device_id={device_id} err={e}")
            return APIResponse(
                success=True,
                data={
                    "message": f"设备 {device_id} 已删除",
                    "warning": f"关联数据清理失败: {e}",
                },
            )

    return APIResponse(success=True, data={"message": f"设备 {device_id} 已删除"})


@router.post("/devices/{device_id}/test", response_model=APIResponse)
def test_device_connection(device_id: int, db: Session = Depends(get_db)):
    """测试设备 NETCONF 连接"""
    device, error = _get_device_or_404(db, device_id)
    if error:
        return error

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败，请检查ENCRYPTION_KEY配置")

    try:
        with NetconfClient(
            host=device.host,
            port=device.port,
            username=device.username,
            password=password,
        ):
            pass
        logger.info(f"设备连接测试成功: {device.host}:{device.port}")
        record_log(db, device.id, device.name, "connect", f"测试连接 {device.host}:{device.port}", "success")
        return APIResponse(success=True, data={"message": "连接成功"})
    except Exception as e:
        error_msg = classify_connection_error(e)
        logger.error(f"设备连接测试失败: {device.host}:{device.port}, 原因: {error_msg}", exc_info=True)
        record_log(db, device.id, device.name, "connect", f"测试连接 {device.host}:{device.port}", "failed", error_message=error_msg)
        return APIResponse(success=False, error=error_msg)


# ========== v1.0 兼容路由（deprecated） ==========


@router.get("/device", response_model=APIResponse, deprecated=True)
def compat_get_device(db: Session = Depends(get_db)):
    """[已弃用] 获取当前设备信息，请使用 GET /api/devices"""
    device = db.query(Device).first()
    if not device:
        return APIResponse(success=True, data=None)
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.post("/device", response_model=APIResponse, deprecated=True)
def compat_create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    """[已弃用] 创建设备，请使用 POST /api/devices"""
    existing = db.query(Device).first()
    if existing:
        return APIResponse(success=False, error="已存在设备配置，V1.0仅支持单设备，请使用PUT更新")

    if not body.host:
        return APIResponse(success=False, error="缺少必填字段: host")
    if not body.username:
        return APIResponse(success=False, error="缺少必填字段: username")
    if not body.password:
        return APIResponse(success=False, error="缺少必填字段: password")

    try:
        encrypted_pwd = encrypt_password(body.password)
    except ValueError as e:
        return APIResponse(success=False, error=str(e))

    device = Device(
        name=body.name,
        host=body.host,
        port=body.port,
        username=body.username,
        password_encrypted=encrypted_pwd,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    # 自动创建空资产记录
    from app.models import Asset
    asset = Asset(device_id=device.id, status="unknown")
    db.add(asset)
    db.commit()

    logger.info(f"设备创建成功(v1兼容): name={device.name}, host={device.host}")
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.put("/device", response_model=APIResponse, deprecated=True)
def compat_update_device(body: DeviceUpdate, db: Session = Depends(get_db)):
    """[已弃用] 更新设备信息，请使用 PUT /api/devices/{id}"""
    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    if body.name is not None:
        device.name = body.name
    if body.host is not None:
        device.host = body.host
    if body.port is not None:
        device.port = body.port
    if body.username is not None:
        device.username = body.username
    if body.password is not None:
        try:
            device.password_encrypted = encrypt_password(body.password)
        except ValueError as e:
            return APIResponse(success=False, error=str(e))

    db.commit()
    db.refresh(device)

    logger.info(f"设备更新成功(v1兼容): name={device.name}, host={device.host}")
    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.post("/device/test", response_model=APIResponse, deprecated=True)
def compat_test_device(db: Session = Depends(get_db)):
    """[已弃用] 测试设备连接，请使用 POST /api/devices/{id}/test"""
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
            host=device.host,
            port=device.port,
            username=device.username,
            password=password,
        ):
            pass
        logger.info(f"设备连接测试成功(v1兼容): {device.host}:{device.port}")
        return APIResponse(success=True, data={"message": "连接成功"})
    except Exception as e:
        error_msg = classify_connection_error(e)
        logger.error(f"设备连接测试失败(v1兼容): {device.host}:{device.port}, 原因: {error_msg}", exc_info=True)
        return APIResponse(success=False, error=error_msg)
