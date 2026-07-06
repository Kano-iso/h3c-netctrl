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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app.models import Backup, Device
from app.schemas import APIResponse
from app.i18n_keys import err, error_response
from app.task_manager import task_manager
from app.utils.asset_guard import check_asset_online  # v2.6.1 fix-asset-backup-state-sync Task 1.2
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
    """获取设备 + 解密密码

    monolith 模式：查本地 Device 表
    split 模式（data 容器无 devices 表）：走 internal_api 调 ctrl 容器
    """
    from app.utils.device_access import get_device_with_password
    return get_device_with_password(db, device_id)


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
def create_backup(
    device_id: int,
    body: BackupCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """对指定设备创建配置备份（拉取 startup.cfg / running.cfg）

    日志记录：BackupManager.create_backup() 内部已经按 btype 粒度（startup / running）
    成功/失败都 record_log，路由层不重复记日志（避免重复 + device_name 字段不一致）。

    v2.6.1 fix-asset-backup-state-sync Task 1.2: asset 状态前置校验
    - 资产 offline/never_collected → 422 拒绝（除非 ?force=true）
    """
    # v2.6.1 fix-asset-backup-state-sync Task 1.2: 资产状态前置校验
    force = request.query_params.get("force", "").lower() == "true"
    try:
        check_asset_online(device_id, force=force)
    except BackupError as e:
        return error_response(
            err.BACKUP_DEVICE_OFFLINE,
            params={"device_id": device_id},
            fallback=f"设备 {device_id} 资产未采集/离线，请先采集后再备份",
        )

    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    types = body.types or ["startup", "running"]
    # 校验类型
    valid_types = {"startup", "running"}
    invalid = [t for t in types if t not in valid_types]
    if invalid:
        return error_response(
            err.INVALID_PARAM,
            params={"param": "backup types"},
            fallback=f"不支持的备份类型: {invalid}（仅支持 startup / running）",
        )

    mgr = _make_manager(device, password)
    try:
        results = mgr.create_backup(types=types, db=db, forced=force)  # v2.6.1 Task 2.5
        if not results:
            return error_response(err.OPERATION_FAILED, params={"error": "所有类型备份均失败"}, fallback="所有类型备份均失败，请查看 logs")
        return APIResponse(
            success=True,
            data={"backups": results, "device_id": device_id, "types_requested": types},
        )
    except BackupError as e:
        return error_response(err.BACKUP_CREATE_FAILED, params={"error": str(e)}, fallback=f"备份失败: {e}")
    except Exception as e:
        logger.error(f"备份异常 device_id={device_id}: {e}", exc_info=True)
        return error_response(err.BACKUP_CREATE_FAILED, params={"error": str(e)}, fallback=f"备份异常: {e}")


@router.get("/devices/{device_id}/backup", response_model=APIResponse)
def list_backups(device_id: int, db: Session = Depends(get_db)):
    """列出指定设备的所有备份（按 created_at DESC）"""
    # 统一设备访问（monolith 本地查 / split 走 internal_api）
    from app.utils.device_access import get_device_or_error
    device, error = get_device_or_error(db, device_id)
    if error:
        return error

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
    """删除备份（locked=True 返回 403）

    日志记录：BackupManager.delete_backup() 内部已 record_log，路由层不重复记。
    """
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        deleted = mgr.delete_backup(backup_id, db=db)
        if not deleted:
            return error_response(err.BACKUP_LOCKED_NO_DELETE)
        return APIResponse(success=True, data={"deleted": backup_id})
    except BackupError as e:
        return error_response(err.BACKUP_DELETE_FAILED, params={"error": str(e)}, fallback=str(e))
    except Exception as e:
        logger.error(f"删除备份异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return error_response(err.BACKUP_DELETE_FAILED, params={"error": str(e)}, fallback=f"删除异常: {e}")


@router.post("/devices/{device_id}/backup/{backup_id}/lock", response_model=APIResponse)
def lock_backup(device_id: int, backup_id: int, body: BackupLockRequest, db: Session = Depends(get_db)):
    """切换备份锁定状态（true 锁定 / false 解锁）

    日志记录：BackupManager.set_locked() 内部已 record_log，路由层不重复记。
    """
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        mgr.set_locked(backup_id, body.locked, db=db)
        return APIResponse(success=True, data={"id": backup_id, "locked": body.locked})
    except BackupError as e:
        return error_response(err.BACKUP_LOCK_FAILED if body.locked else err.BACKUP_UNLOCK_FAILED, params={"error": str(e)}, fallback=str(e))
    except Exception as e:
        logger.error(f"锁定切换异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return error_response(err.OPERATION_FAILED, params={"error": str(e)}, fallback=f"操作异常: {e}")


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

    日志记录：BackupManager.restore() 内部已 record_log（包含 reboot / verify），
    路由层不重复记。
    """
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    mgr = _make_manager(device, password)
    try:
        result = mgr.restore(backup_id, with_reboot=body.with_reboot, db=db)
        if not result["success"]:
            return error_response(
                err.BACKUP_RESTORE_FAILED,
                params={"error": result["message"]},
                fallback=result["message"],
            )
        return APIResponse(success=True, data=result)
    except BackupError as e:
        return error_response(err.BACKUP_RESTORE_FAILED, params={"error": str(e)}, fallback=str(e))
    except Exception as e:
        logger.error(f"回滚异常 device_id={device_id} bid={backup_id}: {e}", exc_info=True)
        return error_response(err.BACKUP_RESTORE_FAILED, params={"error": str(e)}, fallback=f"回滚异常: {e}")


# ============ 全量备份 ============


class BackupAllRequest(BaseModel):
    """全量备份请求体"""
    types: Optional[List[str]] = None  # 不传 = 全部（startup + running）


@router.post("/backups", response_model=APIResponse)
def create_all_backups(body: Optional[BackupAllRequest] = None, db: Session = Depends(get_db)):
    """对所有设备并发触发备份（v2.3 支持指定 type）"""
    if body is None:
        body = BackupAllRequest()
    # 统一设备访问（monolith 本地查 / split 走 internal_api）
    from app.utils.device_access import get_devices_batch
    # 传 None 表示拉所有（特殊处理）
    try:
        # monolith 模式：本地查所有
        devices = db.query(Device).all()
    except Exception as e:
        logger.warning(f"本地 Device 表不可用，走内部 API: {e}")
        from app.internal_api import get_devices
        resp = get_devices()
        if not resp.get("success"):
            return error_response(err.NOT_FOUND, params={"resource": "devices"}, fallback="无设备可备份")
        from app.utils.device_access import _wrap_device_dict
        devices = [_wrap_device_dict(d) for d in resp["data"]]
    if not devices:
        return error_response(err.NOT_FOUND, params={"resource": "devices"}, fallback="无设备可备份")

    types = body.types or ["startup", "running"]
    # 校验类型
    valid_types = {"startup", "running"}
    invalid = [t for t in types if t not in valid_types]
    if invalid:
        return error_response(
            err.INVALID_PARAM,
            params={"param": "backup types"},
            fallback=f"不支持的备份类型: {invalid}（仅支持 startup / running）",
        )

    # 并发备份（串行实现 - SQLite 写并发问题；如切 Postgres 可改 asyncio.gather）
    success_list = []
    failed_list = []

    for device in devices:
        try:
            # split 模式 device 是 SimpleNamespace，_password_decrypted 已解密
            # monolith 模式 device 是 ORM 对象，需要 decrypt_password
            password = getattr(device, "_password_decrypted", None) or decrypt_password(device.password_encrypted)
        except Exception as e:
            failed_list.append({"device_id": device.id, "error": f"密码解密失败: {e}"})
            record_log(db, device.id, device.name, "backup_create_all",
                       "密码解密失败", "failed", error_message=str(e))
            continue

        mgr = _make_manager(device, password)
        try:
            results = mgr.create_backup(types=types, db=db)
            if results:
                success_list.append({
                    "device_id": device.id,
                    "device_name": device.name,
                    "backups": results,
                })
                record_log(db, device.id, device.name, "backup_create_all",
                           f"全量备份成功：{len(results)} 份新备份", "success")
            else:
                failed_list.append({"device_id": device.id, "device_name": device.name, "error": "所有类型备份均失败"})
                record_log(db, device.id, device.name, "backup_create_all",
                           "全量备份失败：所有类型均失败", "failed",
                           error_message="所有类型备份均失败")
        except BackupError as e:
            failed_list.append({"device_id": device.id, "device_name": device.name, "error": str(e)})
            record_log(db, device.id, device.name, "backup_create_all",
                       "全量备份失败", "failed", error_message=str(e))
        except Exception as e:
            logger.error(f"全量备份异常 device_id={device.id}: {e}", exc_info=True)
            failed_list.append({"device_id": device.id, "device_name": device.name, "error": str(e)})
            record_log(db, device.id, device.name, "backup_create_all",
                       "全量备份异常", "failed", error_message=str(e))

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


# ============ v24-feat-async-backup-status: 异步备份/回滚 ============


def _async_backup_fn(task_id, cancel_event, progress_cb, device_id: int, types: list[str]):
    """异步备份执行函数（在后台线程中运行）"""
    db = SessionLocal()
    try:
        device, password, error = _get_device_with_password(db, device_id)
        if error:
            raise Exception(error.error)

        progress_cb(10)
        if cancel_event.is_set():
            return {"cancelled": True}

        mgr = _make_manager(device, password)
        results = mgr.create_backup(types=types, db=db)
        progress_cb(90)

        if not results:
            raise Exception("所有类型备份均失败，请查看 logs")
        return {"backups": results, "device_id": device_id, "types_requested": types}
    finally:
        db.close()


def _async_backup_all_fn(task_id, cancel_event, progress_cb, types: list[str]):
    """异步全量备份执行函数（多设备串行）

    在后台线程中运行，串行遍历所有设备，每设备走 _async_backup_fn 的核心逻辑。
    进度更新：每完成 1 设备更新一次（10% → 90% 分配给各设备）。
    """
    db = SessionLocal()
    try:
        # 1. 拉所有设备
        from app.utils.device_access import get_devices_batch
        from app.utils.crypto import decrypt_password

        try:
            devices = db.query(Device).all()
            if not devices:
                raise Exception("无设备可备份")
        except Exception as e:
            logger.warning(f"本地 Device 表不可用，走内部 API: {e}")
            from app.internal_api import get_devices
            resp = get_devices()
            if not resp.get("success") or not resp.get("data"):
                raise Exception("无设备可备份")
            from app.utils.device_access import _wrap_device_dict
            devices = [_wrap_device_dict(d) for d in resp["data"]]

        if cancel_event.is_set():
            return {"cancelled": True}
        progress_cb(5)

        total = len(devices)
        success_list = []
        failed_list = []
        # 进度区间 5% ~ 95% 留给设备备份，每设备均分
        start_pct, end_pct = 5, 95
        for idx, device in enumerate(devices):
            if cancel_event.is_set():
                return {"cancelled": True, "completed": idx, "total": total}

            try:
                password = getattr(device, "_password_decrypted", None) or decrypt_password(device.password_encrypted)
            except Exception as e:
                failed_list.append({"device_id": device.id, "device_name": device.name, "error": f"密码解密失败: {e}"})
                continue

            mgr = _make_manager(device, password)
            try:
                results = mgr.create_backup(types=types, db=db)
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

            # 更新进度
            pct = start_pct + int((idx + 1) / total * (end_pct - start_pct))
            progress_cb(pct)

        progress_cb(100)
        return {
            "total": total,
            "success_count": len(success_list),
            "failed_count": len(failed_list),
            "success": success_list,
            "failed": failed_list,
        }
    finally:
        db.close()


def _async_restore_fn(
    task_id, cancel_event, progress_cb, device_id: int, backup_id: int, with_reboot: bool
):
    """异步回滚执行函数（在后台线程中运行）"""
    db = SessionLocal()
    try:
        device, password, error = _get_device_with_password(db, device_id)
        if error:
            raise Exception(error.error)

        progress_cb(10)
        if cancel_event.is_set():
            return {"cancelled": True}

        mgr = _make_manager(device, password)
        # 回滚阶段 1：SCP 推 + set as startup
        progress_cb(30)
        result = mgr.restore(backup_id, with_reboot=with_reboot, db=db)
        progress_cb(90)

        if not result.get("success"):
            raise Exception(result.get("message", "回滚失败"))
        return result
    finally:
        db.close()


@router.post("/devices/{device_id}/backup-async", response_model=APIResponse)
def create_backup_async(
    device_id: int,
    body: BackupCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """异步备份（v24-feat-async-backup-status）

    立即返回 task_id，后台执行备份。前端轮询 GET /api/tasks/{task_id} 获取进度。

    v2.6.1 fix-asset-backup-state-sync Task 1.3: asset 状态前置校验
    - 资产 offline/never_collected → 422 拒绝（除非 ?force=true）
    """
    # v2.6.1 fix-asset-backup-state-sync Task 1.3: 资产状态前置校验
    force = request.query_params.get("force", "").lower() == "true"
    try:
        check_asset_online(device_id, force=force)
    except BackupError as e:
        return error_response(
            err.BACKUP_DEVICE_OFFLINE,
            params={"device_id": device_id},
            fallback=f"设备 {device_id} 资产未采集/离线，请先采集后再备份",
        )

    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    types = body.types or ["startup", "running"]
    valid_types = {"startup", "running"}
    invalid = [t for t in types if t not in valid_types]
    if invalid:
        return error_response(
            err.INVALID_PARAM,
            params={"param": "backup types"},
            fallback=f"不支持的备份类型: {invalid}（仅支持 startup / running）",
        )

    task_id = task_manager.submit("backup", device_id, _async_backup_fn, device_id, types, force)  # v2.6.1 Task 2.5
    logger.info(f"异步备份已提交: device_id={device_id}, task_id={task_id}, force={force}")
    return APIResponse(
        success=True,
        data={"task_id": task_id, "status_url": f"/api/tasks/{task_id}", "status": "pending"},
    )


@router.post("/devices/{device_id}/backup/{backup_id}/restore-async", response_model=APIResponse)
def restore_backup_async(
    device_id: int, backup_id: int, body: BackupRestoreRequest = BackupRestoreRequest(), db: Session = Depends(get_db)
):
    """异步回滚（v24-feat-async-backup-status）

    立即返回 task_id，后台执行回滚。前端轮询 GET /api/tasks/{task_id} 获取进度。
    """
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    # 校验备份存在
    backup = db.query(Backup).filter(Backup.id == backup_id, Backup.device_id == device_id).first()
    if not backup:
        return error_response(err.BACKUP_NOT_FOUND, params={"id": backup_id})

    task_id = task_manager.submit(
        "restore", device_id, _async_restore_fn, device_id, backup_id, body.with_reboot
    )
    logger.info(f"异步回滚已提交: device_id={device_id}, backup_id={backup_id}, task_id={task_id}")
    return APIResponse(
        success=True,
        data={"task_id": task_id, "status_url": f"/api/tasks/{task_id}", "status": "pending"},
    )


@router.post("/backups-async", response_model=APIResponse)
def create_all_backups_async(body: Optional[BackupAllRequest] = None):
    """全量备份异步模式（v241-supplement Task 8.4）

    立即返回 task_id，后台串行遍历所有设备执行备份。
    前端轮询 GET /api/tasks/{task_id} 获取进度。

    与 POST /api/backups（同步）共存：
    - 同步端点：CLI / 脚本可继续用
    - 异步端点：前端默认走这个，避免 7 设备 × 2 type 阻塞 2-4 分钟
    """
    if body is None:
        body = BackupAllRequest()
    types = body.types or ["startup", "running"]
    valid_types = {"startup", "running"}
    invalid = [t for t in types if t not in valid_types]
    if invalid:
        return error_response(
            err.INVALID_PARAM,
            params={"param": "backup types"},
            fallback=f"不支持的备份类型: {invalid}（仅支持 startup / running）",
        )

    # device_id 传 0 表示全量（不绑定单设备）
    task_id = task_manager.submit("backup_all", 0, _async_backup_all_fn, types)
    logger.info(f"异步全量备份已提交: task_id={task_id}, types={types}")
    return APIResponse(
        success=True,
        data={"task_id": task_id, "status_url": f"/api/tasks/{task_id}", "status": "pending"},
    )


@router.get("/tasks/{task_id}", response_model=APIResponse)
def get_task_status(task_id: int):
    """查询异步任务状态（v24-feat-async-backup-status）

    前端每 2s 轮询此端点，获取任务进度。
    """
    status = task_manager.get_status(task_id)
    if not status:
        return error_response(err.BATCH_TASK_NOT_FOUND, params={"task_id": task_id})
    return APIResponse(success=True, data=status)


@router.post("/tasks/{task_id}/cancel", response_model=APIResponse)
def cancel_task(task_id: int):
    """取消异步任务（v24-feat-async-backup-status）

    协作式取消：设置 cancel_event，任务在下一个检查点退出。
    """
    cancelled = task_manager.cancel(task_id)
    if not cancelled:
        return APIResponse(
            success=False,
            error="任务不存在或已完成（无法取消）",
            data={"cancelled": False},
        )
    return APIResponse(success=True, data={"cancelled": True})

