"""备份物理文件完整性自检（v2.6.1 fix-backup-data-integrity Task 2a/2b）

data 容器启动时跑：DB 里的 backup.file_path 是否物理存在
- 存在：OK
- 不存在：自动删 DB 行（v2.6.1 T2b 决策）

设计：
- check_backup_files() 纯只读（供其他场景复用）
- cleanup_missing_backups() 执行删除（启动期一次，commit + 详细日志）
- 用独立 session 跑（启动期开销 < 100ms）
"""
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Backup

logger = logging.getLogger("app")


def check_backup_files(db: Session) -> dict:
    """启动时自检：DB 里的 backup.file_path 是否物理存在

    Args:
        db: SQLAlchemy Session

    Returns:
        {
            "total": int,           # DB 里 backup 总数
            "missing": int,         # 文件物理丢失的数量
            "missing_files": [      # 详细列表
                {"id": int, "device_id": int, "filename": str, "file_path": str}
            ]
        }
    """
    try:
        bks = db.query(Backup).all()
    except Exception as e:
        # 极端场景：backups 表不存在（data 容器 init 阶段），不阻塞启动
        logger.warning(f"backup 物理文件自检跳过（backups 表不可用）: {e}")
        return {"total": 0, "missing": 0, "missing_files": []}

    missing = []
    for b in bks:
        if not b.file_path:
            # 边界保护：file_path 为空（理论上不应发生）也视为丢失
            missing.append({
                "id": b.id,
                "device_id": b.device_id,
                "filename": b.filename or "",
                "file_path": "",
            })
            continue
        if not os.path.exists(b.file_path):
            missing.append({
                "id": b.id,
                "device_id": b.device_id,
                "filename": b.filename or "",
                "file_path": b.file_path,
            })

    return {"total": len(bks), "missing": len(missing), "missing_files": missing}


def cleanup_missing_backups() -> dict:
    """启动时清理：删除 DB 中文件物理不存在的 backup 行

    v2.6.1 T2b 决策：启动自检发现「DB 有记录但磁盘无文件」时直接删 DB 行
    - 理由：list 立即干净，避免用户点下载拿到 410
    - 风险：被删行无法回退（用户需知）

    设计：内部用独立 SessionLocal，避免 commit 后 expire 触发 ObjectDeletedError
    （check_backup_files 用 .all() 把所有 Backup 加进 session 缓存，commit 后访问
    任意实例属性会重新加载 DB；删除后再 reload 即报错）

    Returns:
        {
            "scanned": int,    # 总扫描数
            "deleted": int,    # 实际删除数
            "deleted_ids": [int, ...],   # 被删的 backup.id
        }
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        result = check_backup_files(db)
        missing_files = result["missing_files"]
        if not missing_files:
            return {"scanned": result["total"], "deleted": 0, "deleted_ids": []}

        deleted_ids = []
        for item in missing_files:
            bk_id = item["id"]
            try:
                obj = db.query(Backup).filter(Backup.id == bk_id).first()
                if obj:
                    db.delete(obj)
                    deleted_ids.append(bk_id)
            except Exception as e:
                logger.error(f"删除幽灵 backup 行失败 id={bk_id}: {e}", exc_info=True)

        if deleted_ids:
            try:
                db.commit()
                logger.warning(
                    f"启动自检清理: 删除 {len(deleted_ids)}/{result['missing']} 个物理文件缺失的 backup 行, "
                    f"ids={deleted_ids}"
                )
            except Exception as e:
                db.rollback()
                logger.error(f"启动自检清理 commit 失败（已回滚）: {e}", exc_info=True)
                return {"scanned": result["total"], "deleted": 0, "deleted_ids": []}

        return {
            "scanned": result["total"],
            "deleted": len(deleted_ids),
            "deleted_ids": deleted_ids,
        }
    finally:
        db.close()


def run_startup_check() -> dict:
    """启动期自检 + 清理入口（cleanup_missing_backups 内部管 session，调用方无需管）

    v2.6.1 T2b：发现「DB 有记录但磁盘无文件」时自动删 DB 行
    - 启动期一次，幂等
    - 删行 + commit 失败不阻塞容器启动（已 try/except 隔离）

    Returns:
        cleanup_missing_backups() 的结果
    """
    result = cleanup_missing_backups()

    if result["deleted"] > 0:
        # 已在 cleanup_missing_backups 内部记 WARN（带 ids）
        pass
    else:
        logger.info(
            f"启动自检: backup 物理文件全部存在（{result['scanned']} 份）"
        )
    return result
