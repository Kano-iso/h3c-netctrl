import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import APIResponse, DeviceCreate, DeviceResponse, DeviceUpdate
from app.utils.crypto import decrypt_password, encrypt_password

logger = logging.getLogger("app")

router = APIRouter(tags=["device"])


@router.get("/device", response_model=APIResponse)
def get_device(db: Session = Depends(get_db)):
    """获取当前设备信息（V1.0 仅支持单设备）"""
    device = db.query(Device).first()
    if not device:
        return APIResponse(success=True, data=None)

    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.post("/device", response_model=APIResponse)
def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    """创建设备（V1.0 仅支持单设备，已存在时返回错误）"""
    # 检查是否已有设备
    existing = db.query(Device).first()
    if existing:
        return APIResponse(success=False, error="已存在设备配置，V1.0仅支持单设备，请使用PUT更新")

    # 校验必填字段
    if not body.host:
        return APIResponse(success=False, error="缺少必填字段: host")
    if not body.username:
        return APIResponse(success=False, error="缺少必填字段: username")
    if not body.password:
        return APIResponse(success=False, error="缺少必填字段: password")

    # 加密密码后存储
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

    logger.info(f"设备创建成功: name={device.name}, host={device.host}")

    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.put("/device", response_model=APIResponse)
def update_device(body: DeviceUpdate, db: Session = Depends(get_db)):
    """更新设备信息"""
    device = db.query(Device).first()
    if not device:
        return APIResponse(success=False, error="未配置设备，请先添加设备信息")

    # 更新非空字段
    if body.name is not None:
        device.name = body.name
    if body.host is not None:
        device.host = body.host
    if body.port is not None:
        device.port = body.port
    if body.username is not None:
        device.username = body.username
    if body.password is not None:
        # 密码变更时重新加密
        try:
            device.password_encrypted = encrypt_password(body.password)
        except ValueError as e:
            return APIResponse(success=False, error=str(e))

    db.commit()
    db.refresh(device)

    logger.info(f"设备更新成功: name={device.name}, host={device.host}")

    resp = DeviceResponse.model_validate(device)
    return APIResponse(success=True, data=resp.model_dump())


@router.post("/device/test", response_model=APIResponse)
def test_device_connection(db: Session = Depends(get_db)):
    """测试 NETCONF 连接，返回精确的错误分类"""
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
            pass  # 连接成功即关闭（context manager 自动管理）
        logger.info(f"设备连接测试成功: {device.host}:{device.port}")
        return APIResponse(success=True, data={"message": "连接成功"})
    except Exception as e:
        error_msg = classify_connection_error(e)
        logger.info(f"设备连接测试失败: {device.host}:{device.port}, 原因: {error_msg}")
        return APIResponse(success=False, error=error_msg)
