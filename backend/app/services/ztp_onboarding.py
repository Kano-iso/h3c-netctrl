"""ZTP onboarding service（v3.1.2）.

ztp-server 确认设备 static 管理地址上线后，回调后端 API。
本 service 负责纳管入库与资产同步，不依赖 DHCP lease 监听。
"""
import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, Device
from app.netconf_client import NetconfClient, classify_connection_error
from app.schemas import ZtpOnboardRequest
from app.utils.crypto import encrypt_password
from app.utils.log_recorder import record_log
from app.utils.ssh_executor import SSHExecutor

logger = logging.getLogger("app")


def derive_ztp_name(host: str) -> str:
    """按管理地址派生默认设备名。"""
    last = host.rsplit(".", 1)[-1]
    return f"ztp-switch-{last}" if last.isdigit() else f"ztp-{host}"


def _probe_device(body: ZtpOnboardRequest) -> None:
    """验证 SSH 22 与 NETCONF 端口可用。失败直接抛异常。"""
    ssh = SSHExecutor(host=body.host, port=22, username=body.username, password=body.password)
    result = ssh.execute("display version")
    if not result.get("success"):
        raise ConnectionError(
            f"SSH 22 探测失败: {result.get('error') or result.get('output') or 'unknown'}"
        )

    try:
        with NetconfClient(
            host=body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            timeout=10,
            max_retries=0,
        ):
            pass
    except Exception as e:
        raise ConnectionError(f"NETCONF {body.port} 探测失败: {classify_connection_error(e)}") from e


def _upsert_local_asset(db: Session, device_id: int, info: dict, status: str) -> dict:
    asset = db.query(Asset).filter(Asset.device_id == device_id).first()
    if not asset:
        asset = Asset(device_id=device_id)
        db.add(asset)
    asset.model = info.get("model", asset.model)
    asset.serial_number = info.get("serial_number", asset.serial_number)
    asset.firmware_version = info.get("firmware_version", asset.firmware_version)
    asset.software_package = info.get("software_package", asset.software_package)
    asset.status = status
    db.commit()
    db.refresh(asset)
    return {
        "device_id": asset.device_id,
        "status": asset.status,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "firmware_version": asset.firmware_version,
        "software_package": asset.software_package,
    }


def _upsert_asset(db: Session, device_id: int, info: dict, status: str) -> dict:
    """monolith 本地写 asset；split ctrl 通过 data internal API 写 asset。"""
    if os.getenv("SERVICE_NAME") == "ctrl":
        from app.internal_api import upsert_asset

        resp = upsert_asset(device_id=device_id, status=status, info=info)
        if not resp.get("success"):
            raise RuntimeError(resp.get("error") or "data 容器 asset upsert 失败")
        return resp.get("data", {})
    return _upsert_local_asset(db, device_id, info, status)


def _collect_asset(body: ZtpOnboardRequest) -> dict:
    ssh = SSHExecutor(host=body.host, port=22, username=body.username, password=body.password)
    info = ssh.collect_hardware_info()
    if not any(info.values()):
        raise RuntimeError("资产采集结果为空")
    return info


def onboard_ztp_device(db: Session, body: ZtpOnboardRequest) -> dict:
    """完成 ZTP 设备纳管。

    探测失败不入库；资产采集失败保留设备记录并返回 partial。
    """
    _probe_device(body)

    name = body.name or derive_ztp_name(body.host)
    encrypted_pwd = encrypt_password(body.password)
    protected = json.dumps([])

    device = db.query(Device).filter(Device.host == body.host).first()
    created = device is None
    if device is None:
        device = Device(
            name=name,
            host=body.host,
            port=body.port,
            username=body.username,
            password_encrypted=encrypted_pwd,
            protected_interfaces=protected,
            platform=body.platform,
        )
        db.add(device)
    else:
        device.name = name
        device.port = body.port
        device.username = body.username
        device.password_encrypted = encrypted_pwd
        if body.platform is not None:
            device.platform = body.platform
    db.commit()
    db.refresh(device)

    asset_data: Optional[dict] = None
    asset_error: Optional[str] = None
    status = "success"

    if body.collect_asset:
        try:
            info = _collect_asset(body)
            asset_data = _upsert_asset(db, device.id, info, "online")
            record_log(
                db,
                device.id,
                device.name,
                "ztp_onboard",
                f"ZTP 纳管并采集资产: {device.host}",
                "success",
            )
        except Exception as e:
            status = "partial"
            asset_error = str(e)
            try:
                asset_data = _upsert_asset(db, device.id, {}, "offline")
            except Exception as sync_error:
                asset_error = f"{asset_error}; asset sync failed: {sync_error}"
            record_log(
                db,
                device.id,
                device.name,
                "ztp_onboard",
                f"ZTP 纳管成功但资产采集失败: {device.host}",
                "failed",
                error_message=asset_error,
            )
    else:
        asset_data = _upsert_asset(db, device.id, {}, "unknown")
        record_log(
            db,
            device.id,
            device.name,
            "ztp_onboard",
            f"ZTP 纳管设备: {device.host}",
            "success",
        )

    return {
        "status": status,
        "created": created,
        "device": {
            "id": device.id,
            "name": device.name,
            "host": device.host,
            "port": device.port,
            "username": device.username,
            "platform": device.platform,
        },
        "asset": asset_data,
        "asset_error": asset_error,
        "source": body.source,
    }
