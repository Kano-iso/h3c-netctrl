import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Asset
from app.schemas import APIResponse
from app.i18n_keys import err, error_response
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["asset"])


def _get_device_or_error(db: Session, device_id: int):
    """获取设备（不需要密码）

    monolith 模式：查本地 Device 表
    split 模式（data 容器无 devices 表）：走 internal_api 调 ctrl 容器
    """
    from app.utils.device_access import get_device_or_error
    return get_device_or_error(db, device_id)


def _get_asset_or_create(db: Session, device_id: int):
    """获取资产记录，不存在则创建"""
    asset = db.query(Asset).filter(Asset.device_id == device_id).first()
    if not asset:
        asset = Asset(device_id=device_id, status="unknown")
        db.add(asset)
        db.commit()
        db.refresh(asset)
    return asset


@router.get("/assets/device/{device_id}", response_model=APIResponse)
def get_asset(device_id: int, db: Session = Depends(get_db)):
    """获取设备资产信息"""
    device, error = _get_device_or_error(db, device_id)
    if error:
        return error
    asset = _get_asset_or_create(db, device_id)
    return APIResponse(success=True, data={
        "device_id": asset.device_id,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "firmware_version": asset.firmware_version,
        "software_package": asset.software_package,
        "location": asset.location,
        "tags": asset.tags,
        "status": asset.status,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    })


@router.put("/assets/device/{device_id}", response_model=APIResponse)
def update_asset(device_id: int, body: dict, db: Session = Depends(get_db)):
    """更新设备资产信息（手动编辑位置/标签/状态）"""
    device, error = _get_device_or_error(db, device_id)
    if error:
        return error
    asset = _get_asset_or_create(db, device_id)

    if "location" in body:
        asset.location = body["location"]
    if "tags" in body:
        asset.tags = body["tags"]
    if "status" in body:
        valid_statuses = ["online", "offline", "maintenance", "decommissioned", "unknown"]
        if body["status"] not in valid_statuses:
            return error_response(
                err.INVALID_PARAM,
                params={"param": f"status (可选: {', '.join(valid_statuses)})"},
            )
        asset.status = body["status"]

    db.commit()
    db.refresh(asset)
    logger.info(f"资产信息更新: device_id={device_id}")
    return APIResponse(success=True, data={"message": "资产信息已更新"})


@router.post("/assets/device/{device_id}/refresh", response_model=APIResponse)
def refresh_asset(device_id: int, db: Session = Depends(get_db)):
    """刷新设备硬件信息（SSH 采集）"""
    device, error = _get_device_or_error(db, device_id)
    if error:
        return error
    asset = _get_asset_or_create(db, device_id)

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return error_response(err.DEVICE_CRYPTO_DECRYPT_FAILED)

    try:
        from app.utils.ssh_executor import SSHExecutor
        executor = SSHExecutor(
            host=device.host,
            port=22,
            username=device.username,
            password=password,
        )
        # 采集硬件信息
        info = executor.collect_hardware_info()
        # 防御性兜底：info 全空时（即便 collect_hardware_info 行为变化）也视为采集失败
        if not any(info.values()):
            raise Exception(f"采集结果为空（model/serial/firmware/software 均无），SSH 可能未正确连接: {device.host}")
        asset.model = info.get("model", asset.model)
        asset.serial_number = info.get("serial_number", asset.serial_number)
        asset.firmware_version = info.get("firmware_version", asset.firmware_version)
        asset.software_package = info.get("software_package", asset.software_package)
        asset.status = "online"
        db.commit()

        record_log(db, device.id, device.name, "asset_refresh", f"刷新硬件信息: {device.host}", "success")
        return APIResponse(success=True, data={"message": "硬件信息已刷新"})
    except Exception as e:
        asset.status = "offline"
        db.commit()
        error_msg = f"采集硬件信息失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        record_log(db, device.id, device.name, "asset_refresh", f"刷新硬件信息失败: {device.host}", "failed", error_message=error_msg)
        # v2.6.1 fix-asset-collect-failure: 用 asset.route.refresh_failed 走 i18n
        return error_response(err.ASSET_ROUTE_REFRESH_FAILED, params={"error": error_msg}, fallback=error_msg)
