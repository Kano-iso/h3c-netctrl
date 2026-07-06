"""资产状态校验（v2.6.1 fix-asset-backup-state-sync Task 1.1）

backup 端点入口前置校验：
- asset.status=online → 放行
- asset.status=offline/never_collected/stale → 抛 BackupError("BACKUP_DEVICE_OFFLINE")
- force=True → 跳过校验 + WARNING 日志（审计）

设计：
- 纯函数 check_asset_online(device_id, force=False)
- 自己开 SessionLocal（短生命周期，调用方无需管 session）
- 不影响 v2.6.0 backup 业务逻辑
"""
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Asset
from app.utils.backup_manager import BackupError

logger = logging.getLogger("app")


def check_asset_online(device_id: int, force: bool = False) -> bool:
    """校验设备资产状态是否 online。

    Args:
        device_id: 设备 ID。
        force: True 时跳过校验（仍记录 WARNING 日志用于审计）。

    Returns:
        True（始终；非 online 时抛 BackupError）。

    Raises:
        BackupError: asset.status ≠ online 时抛 ``BACKUP_DEVICE_OFFLINE``。
    """
    if force:
        # 审计：记录 force_backup 操作
        logger.warning(f"force_backup device_id={device_id} skip asset check")
        return True

    db: Session = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.device_id == device_id).first()
        if asset is None:
            raise BackupError(
                f"BACKUP_DEVICE_OFFLINE device_id={device_id} status=never_collected"
            )
        if asset.status != "online":
            raise BackupError(
                f"BACKUP_DEVICE_OFFLINE device_id={device_id} status={asset.status}"
            )
        return True
    finally:
        db.close()
