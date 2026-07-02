"""ctrl 容器内部端点（v241-container-split）

供 config / data 容器调用的内部 API：
- GET /internal/devices — 拉所有设备列表（config/data 启动时缓存用）
- GET /internal/devices/{device_id} — 查单个设备（NETCONF 连接前查 IP/凭据）
- POST /internal/logs — 写操作日志（config 改配置后调）
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Log
from app.utils.crypto import decrypt_password
from app.schemas import APIResponse

logger = logging.getLogger("app")

router = APIRouter(prefix="/internal", tags=["internal"])


class WriteLogRequest(BaseModel):
    device_id: int
    action: str
    status: str
    detail: str
    device_name: str = ""
    error_message: str = ""


@router.get("/devices", response_model=APIResponse)
def internal_list_devices(db: Session = Depends(get_db)):
    """返回所有设备列表（含解密后的密码，仅供内部容器调用）"""
    devices = db.query(Device).all()
    data = []
    for d in devices:
        data.append({
            "id": d.id,
            "name": d.name,
            "host": d.host,
            "port": d.port,
            "username": d.username,
            "password": decrypt_password(d.password_encrypted),
            "protected_interfaces": d.protected_interfaces,
        })
    return {"success": True, "data": data}


@router.get("/devices/{device_id}", response_model=APIResponse)
def internal_get_device(device_id: int, db: Session = Depends(get_db)):
    """查单个设备（含解密后的密码）"""
    d = db.query(Device).filter(Device.id == device_id).first()
    if not d:
        return {"success": False, "error": f"设备 {device_id} 不存在"}
    return {
        "success": True,
        "data": {
            "id": d.id,
            "name": d.name,
            "host": d.host,
            "port": d.port,
            "username": d.username,
            "password": decrypt_password(d.password_encrypted),
            "protected_interfaces": d.protected_interfaces,
        },
    }


@router.post("/logs", response_model=APIResponse)
def internal_write_log(req: WriteLogRequest, db: Session = Depends(get_db)):
    """写操作日志（供 config 容器调）"""
    device_name = req.device_name
    if not device_name:
        d = db.query(Device).filter(Device.id == req.device_id).first()
        device_name = d.name if d else f"device-{req.device_id}"

    log = Log(
        device_id=req.device_id,
        device_name=device_name,
        action=req.action,
        status=req.status,
        detail=req.detail,
        error_message=req.error_message or None,
    )
    db.add(log)
    db.commit()
    return {"success": True, "data": {"id": log.id}}
