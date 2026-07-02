import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Log, Asset
from app.schemas import APIResponse

logger = logging.getLogger("app")

router = APIRouter(tags=["dashboard"])


def _get_asset_stats(db: Session):
    """获取资产统计（在线/离线数）

    monolith 模式：直接查本地 Asset 表。
    3 容器模式（ctrl 容器无 Asset 表）：走内部 API 调 data 容器。
    """
    try:
        online = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar()
        offline = db.query(func.count(Asset.id)).filter(Asset.status == "offline").scalar()
        return online or 0, offline or 0
    except Exception as e:
        # 3 容器模式：ctrl 容器无 assets 表，走内部 API
        logger.warning(f"本地 Asset 表不可用，走内部 API: {e}")
        try:
            from app.internal_api import get_assets
            resp = get_assets()
            if resp.get("success"):
                assets = resp["data"]
                online = sum(1 for a in assets if a.get("status") == "online")
                offline = sum(1 for a in assets if a.get("status") == "offline")
                return online, offline
        except Exception as api_err:
            logger.error(f"内部 API 查 assets 也失败: {api_err}")
        return 0, 0


@router.get("/dashboard", response_model=APIResponse)
def get_dashboard(db: Session = Depends(get_db)):
    """获取仪表盘数据"""
    # 设备统计
    total_devices = db.query(func.count(Device.id)).scalar()
    online_devices, offline_devices = _get_asset_stats(db)

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
