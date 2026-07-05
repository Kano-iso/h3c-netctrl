"""data 容器内部端点（v241-container-split）

供 ctrl / config 容器调用的内部 API：
- GET /internal/assets — 拉所有资产数据（dashboard 聚合用）
- POST /internal/backup — 触发备份（config 改配置后调）
- GET /internal/backups/{device_id} — 查设备已有备份
- DELETE /internal/devices/{id}/cleanup — 删设备时清理关联 asset/backup（v241-supplement Task 4.2）
"""
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
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
    """返回所有资产数据（供 ctrl dashboard 聚合用）

    v2.6.1 fix-asset-stale-status：当 ASSET_STALE_ENABLED=True 时，
    每个 asset dict 增加 is_stale: bool 字段（(now - updated_at) > threshold）。
    关闭时 MUST NOT 加此字段（避免污染 split 模式 ctrl 端过滤逻辑）。
    """
    assets = db.query(Asset).all()
    now = datetime.utcnow() if settings.ASSET_STALE_ENABLED else None
    threshold_hours = settings.ASSET_STALE_HOURS if settings.ASSET_STALE_ENABLED else None
    data = []
    for a in assets:
        item = {
            "id": a.id,
            "device_id": a.device_id,
            "status": a.status,
            "model": a.model,
            "serial_number": a.serial_number,
            "firmware_version": a.firmware_version,
        }
        if settings.ASSET_STALE_ENABLED and a.updated_at is not None:
            age_hours = (now - a.updated_at).total_seconds() / 3600.0
            item["is_stale"] = age_hours > threshold_hours
        data.append(item)
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


@router.delete("/devices/{device_id}/cleanup", response_model=APIResponse)
def internal_cleanup_device(device_id: int, db: Session = Depends(get_db)):
    """清理设备关联的 asset / backup 数据 + 本地备份文件

    触发场景：split 模式下 ctrl 容器 `DELETE /api/devices/{id}` 成功 →
    通过 `internal_api.cleanup_device()` 调本端点清理 data 容器关联数据。

    实现：
    1. 删 assets 表 device_id 关联行（return count）
    2. 删 backups 表 device_id 关联行 + 本地文件（return count）
    3. 文件已丢失不抛异常，继续清元数据

    Args:
        device_id: 设备数据库 ID

    Returns:
        APIResponse(success=True, data={deleted_assets: N, deleted_backups: M})
    """
    # 1. 删 asset 行
    deleted_assets = db.query(Asset).filter(Asset.device_id == device_id).delete()
    db.flush()
    logger.info(f"cleanup_device: device_id={device_id} deleted_assets={deleted_assets}")

    # 2. 删 backup 行 + 本地文件
    backups = db.query(Backup).filter(Backup.device_id == device_id).all()
    deleted_backups = 0
    files_deleted = 0
    files_missing = 0
    for b in backups:
        # 删本地文件（不存在的文件不抛异常）
        if b.file_path and os.path.exists(b.file_path):
            try:
                os.remove(b.file_path)
                files_deleted += 1
            except OSError as e:
                logger.warning(f"cleanup_device: 删除备份文件失败 {b.file_path}: {e}")
        else:
            files_missing += 1
            logger.warning(f"cleanup_device: 备份文件已丢失 backup_id={b.id} path={b.file_path}")
        # 删元数据
        db.delete(b)
        deleted_backups += 1
    db.commit()

    logger.info(
        f"cleanup_device: device_id={device_id} deleted_assets={deleted_assets}"
        f" deleted_backups={deleted_backups} files_deleted={files_deleted} files_missing={files_missing}"
    )
    return {
        "success": True,
        "data": {
            "device_id": device_id,
            "deleted_assets": deleted_assets,
            "deleted_backups": deleted_backups,
            "files_deleted": files_deleted,
            "files_missing": files_missing,
        },
    }
