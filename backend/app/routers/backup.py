"""配置备份 API 路由（v2.2）

端点：
- POST   /api/devices/{id}/backup              单设备备份
- GET    /api/devices/{id}/backup              列表该设备备份
- GET    /api/devices/{id}/backup/{bid}        下载备份
- DELETE /api/devices/{id}/backup/{bid}        删除备份（锁定 403）
- POST   /api/devices/{id}/backup/{bid}/lock   锁定/解锁
- POST   /api/devices/{id}/backup/{bid}/restore 回滚
- POST   /api/backups                           全量备份

**前端 UI 留待 v2.2 实现（API 已就绪，可通过 curl 直接调用）**
"""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Backup, Device
from app.schemas import APIResponse
from app.utils.backup_manager import BackupError, BackupManager
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")
router = APIRouter(tags=["backup"])


# 启动时确保备份目录存在
def _ensure_backup_root():
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    logger.info(f"backup_dir={settings.BACKUP_DIR}, exists={os.path.exists(settings.BACKUP_DIR)}, keep={settings.BACKUP_KEEP}")


_ensure_backup_root()


class BackupCreateRequest(BaseModel):
    types: Optional[List[str]] = None  # ["startup", "running"]；默认两者都拉


class BackupLockRequest(BaseModel):
    locked: bool


def _get_device_with_password(db: Session, device_id: int):
    """获取设备 + 解密密码"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return None, None, APIResponse(success=False, error=f"设备不存在: id={device_id}")
    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return None, None, APIResponse(success=False, error="密码解密失败，请检查 ENCRYPTION_KEY 配置")
    return device, password, None


def _make_manager(device: Device, password: str) -> BackupManager:
    """构造 BackupManager

    全文本 + SCP 统一方案：
    - startup 备份：paramiko SSH + scp 库拉 flash:/startup.cfg
    - running 备份：SSHExecutor 跑 `display current-configuration`（自动关分页）
    - 恢复：统一 SCP 推 + `startup saved-configuration`，不依赖 NETCONF

    故统一用 SSH 端口 22。
    """
    return BackupManager(
        device_id=device.id,
        host=device.host,
        port=22,  # SSH 端口（startup 走 SCP，running 走 SSH CLI）
        username=device.username,
        password=password,
    )


# ============ 单设备备份 ============


@router.post("/devices/{device_id}/backup", response_model=APIResponse)
def create_backup(device_id: int, body: BackupCreateRequest, db: Session = Depends(get_db)):
    """对指定设备创建配置备份（拉取 startup.cfg / running.cfg）"""
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    types = body.types or ["startup", "running"]
    # 校验类型
    valid_types = {"startup", "running"}
    invalid = [t for t in types if t not in valid_types]
    if invalid:
        return APIResponse(success=False, error=f"不支持的备份类型: {invalid}（仅支持 startup / running）")

    mgr = _make_manager(device, password)
    try:
        results = mgr.create_backup(types=types, db=db)
        if not results:
            return APIResponse(success=False, error="所有类型备份均失败，请查看 logs")
        return APIResponse(
            success=True,
            data={"backups": results, "device_id": device_id, "types_requested": types},
        )
    except BackupError as e:
        return APIResponse(success=False, error=f"备份失败: {e}")
    except Exception as e:
        logger.error(f"备份异常 device_id={device_id}: {e}", exc_info=True)
        return APIResponse(success=False, error=f"备份异常: {e}")


@router.get("/devices/{device_id}/backup", response_model=APIResponse)
def list_backups(device_id: int, db: Session = Depends(get_db)):
    """列出指定设备的所有备份（按 created_at DESC）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return APIResponse(success=False, error=f"设备不存在: id={device_id}")

    backups = (
        db.query(Backup)
        .filter(Backup.device_id == device_id)
        .order_by(Backup.created_at.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data={
            "device_id": device_id,
            "total": len(backups),
            "backups": [
                {
                    "id": b.id,
                    "filename": b.filename,
                    "type": b.backup_type,
                    "size": b.size,
                    "content_hash": b.content_hash,
                    "locked": b.locked,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in backups
            ],
        },
    )


@router.get("/devices/{device_id}/backup/{backup_id}")
def download_backup(device_id: int, backup_id: int, db: Session = Depends(get_db)):
    """下载备份文件"""
    backup = (
        db.query(Backup)
        .filter(Backup.id == backup_id, Backup.device_id == device_id)
        .first()
    )
    if not backup:
        raise HTTPException(status_code=404, detail=f"备份不存在: id={backup_id}")
    if not os.path.exists(backup.file_path):
        raise HTTPException(status_code=410, detail=f"备份文件已丢失: {backup.file_path}")

    return FileResponse(
        path=backup.file_path,
        media_type="application/octet-stream",
        filename=backup.filename,
    )


@router.delete("/devices/{device_id}/backup/{backup_id}", response_model=APIResponse)
def delete_backup(device_id: int, backup_id: int, db: Session = Depends(get_db)):
    """删除备份（locked=True 返回 403）"""
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        deleted = mgr.delete_backup(backup_id, db=db)
        if not deleted:
            return APIResponse(
                success=False,
                error="备份已锁定，请先解锁再删除",
            )
        return APIResponse(success=True, data={"deleted": backup_id})
    except BackupError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"删除备份异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return APIResponse(success=False, error=f"删除异常: {e}")


@router.post("/devices/{device_id}/backup/{backup_id}/lock", response_model=APIResponse)
def lock_backup(device_id: int, backup_id: int, body: BackupLockRequest, db: Session = Depends(get_db)):
    """切换备份锁定状态（true 锁定 / false 解锁）"""
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        mgr.set_locked(backup_id, body.locked, db=db)
        return APIResponse(success=True, data={"id": backup_id, "locked": body.locked})
    except BackupError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"锁定切换异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return APIResponse(success=False, error=f"操作异常: {e}")


class BackupRestoreRequest(BaseModel):
    """回滚请求体"""
    with_reboot: bool = False  # 是否触发设备 reboot + retry + verify（默认 False，符合业界"backup 工具不负责 reboot"边界）


@router.post("/devices/{device_id}/backup/{backup_id}/restore", response_model=APIResponse)
def restore_backup(device_id: int, backup_id: int, body: BackupRestoreRequest = BackupRestoreRequest(), db: Session = Depends(get_db)):
    """从指定备份回滚配置

    body.with_reboot = False（默认）：只做"推 + set as startup"，不 reboot，前端提示运维手动 reload
    body.with_reboot = True：推 + set as startup + reboot + retry SSH + verify running-config（端到端）

    业界主流（Oxidized / Ansible Network / NAPALM / H3C iMC）都是"工具不负责 reboot"，
    但 v2.2 用户场景是"页面点一下就完成回滚"，所以 with_reboot=True 走端到端流程。
    """
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        result = mgr.restore(backup_id, with_reboot=body.with_reboot, db=db)
        if not result["success"]:
            return APIResponse(success=False, error=result["message"], data=result)
        return APIResponse(success=True, data=result)
    except BackupError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"回滚异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return APIResponse(success=False, error=f"回滚异常: {e}")


# ============ 全量备份 ============


@router.post("/backups", response_model=APIResponse)
def create_all_backups(db: Session = Depends(get_db)):
    """对所有设备并发触发备份"""
    devices = db.query(Device).all()
    if not devices:
        return APIResponse(success=False, error="无设备可备份")

    # 并发备份（串行实现 - SQLite 写并发问题；如切 Postgres 可改 asyncio.gather）
    success_list = []
    failed_list = []

    for device in devices:
        try:
            password = decrypt_password(device.password_encrypted)
        except Exception as e:
            failed_list.append({"device_id": device.id, "error": f"密码解密失败: {e}"})
            record_log(db, device.id, device.name, "backup_create_all",
                       "密码解密失败", "failed", error_message=str(e))
            continue

        mgr = _make_manager(device, password)
        try:
            results = mgr.create_backup(types=["startup", "running"], db=db)
            if results:
                success_list.append({
                    "device_id": device.id,
                    "device_name": device.name,
                    "backups": results,
                })
            else:
                failed_list.append({"device_id": device.id, "device_name": device.name, "error": "所有类型备份均失败"})
        except BackupError as e:
            failed_list.append({"device_id": device.id, "device_name": device.name, "error": str(e)})
        except Exception as e:
            logger.error(f"全量备份异常 device_id={device.id}: {e}", exc_info=True)
            failed_list.append({"device_id": device.id, "device_name": device.name, "error": str(e)})

    return APIResponse(
        success=True,
        data={
            "total": len(devices),
            "success_count": len(success_list),
            "failed_count": len(failed_list),
            "success": success_list,
            "failed": failed_list,
        },
    )
