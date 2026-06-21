import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Log, Asset
from app.schemas import APIResponse

logger = logging.getLogger("app")

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=APIResponse)
def get_dashboard(db: Session = Depends(get_db)):
    """获取仪表盘数据"""
    # 设备统计
    total_devices = db.query(func.count(Device.id)).scalar()
    online_devices = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar()
    offline_devices = db.query(func.count(Asset.id)).filter(Asset.status == "offline").scalar()

    # 最近5条操作日志
    recent_logs = db.query(Log).order_by(Log.created_at.desc()).limit(5).all()
    recent_logs_data = [
        {
            "id": log.id,
            "device_name": log.device_name,
            "action": log.action,
            "detail": log.detail,
            "status": log.status,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in recent_logs
    ]

    # 最近5条失败操作
    recent_failures = db.query(Log).filter(Log.status == "failed").order_by(Log.created_at.desc()).limit(5).all()
    recent_failures_data = [
        {
            "id": log.id,
            "device_name": log.device_name,
            "action": log.action,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in recent_failures
    ]

    return APIResponse(success=True, data={
        "device_stats": {
            "total": total_devices,
            "online": online_devices,
            "offline": offline_devices,
        },
        "recent_logs": recent_logs_data,
        "recent_failures": recent_failures_data,
    })
