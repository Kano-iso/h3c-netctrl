"""data 容器内部端点（v241-container-split）

供 ctrl / config 容器调用的内部 API：
- GET /internal/assets — 拉所有资产数据（dashboard 聚合用）
- POST /internal/backup — 触发备份（config 改配置后调）
- GET /internal/backups/{device_id} — 查设备已有备份
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Backup
from app.schemas import APIResponse

logger = logging.getLogger("app")

router = APIRouter(prefix="/internal", tags=["internal"])


class BackupRequest(BaseModel):
    device_id: int
    types: Optional[List[str]] = None


@router.get("/assets", response_model=APIResponse)
def internal_list_assets(db: Session = Depends(get_db)):
    """返回所有资产数据（供 ctrl dashboard 聚合用）"""
    assets = db.query(Asset).all()
    data = []
    for a in assets:
        data.append({
            "id": a.id,
            "device_id": a.device_id,
            "status": a.status,
            "model": a.model,
            "serial_number": a.serial_number,
            "firmware_version": a.firmware_version,
        })
    return {"success": True, "data": data}


@router.post("/backup", response_model=APIResponse)
def internal_trigger_backup(req: BackupRequest, db: Session = Depends(get_db)):
    """触发备份（供 config 容器调，改配置后自动备份）

    注意：这是同步内部备份，不走异步任务队列（内部调用不需要前端轮询）。
    v2.4.1 简化：内部备份端点暂未实现完整逻辑（需要设备信息从 ctrl 获取）。
    """
    return {"success": False, "error": "内部备份端点暂未实现，请通过前端 /backup-async 触发"}


@router.get("/backups/{device_id}", response_model=APIResponse)
def internal_list_backups(device_id: int, db: Session = Depends(get_db)):
    """查设备已有备份（供 config 容器备份前检查用）"""
    backups = db.query(Backup).filter(Backup.device_id == device_id).all()
    data = []
    for b in backups:
        data.append({
            "id": b.id,
            "filename": b.filename,
            "backup_type": b.backup_type,
            "size": b.size,
            "locked": b.locked,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return {"success": True, "data": data}
