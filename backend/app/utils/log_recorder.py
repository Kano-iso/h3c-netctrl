import logging
from sqlalchemy.orm import Session

from app.models import Log

logger = logging.getLogger("app")


def record_log(db: Session, device_id: int, device_name: str, action: str, detail: str, status: str, error_message: str = None):
    """记录操作日志到数据库

    monolith 模式：直接写本地 logs 表
    split 模式（config/data 容器无 logs 表）：本地写失败 → 走 internal_api 调 ctrl 容器
    """
    # 1. 先尝试本地写（monolith 模式）
    try:
        log = Log(
            device_id=device_id,
            device_name=device_name,
            action=action,
            detail=detail,
            status=status,
            error_message=error_message,
        )
        db.add(log)
        db.commit()
        return
    except Exception as e:
        logger.warning(f"本地记录操作日志失败，走内部 API: {e}")
        try:
            db.rollback()
        except Exception:
            pass

    # 2. 走内部 API（split 模式，config/data 容器调 ctrl 容器写日志）
    try:
        from app.internal_api import write_log
        write_log(
            device_id=device_id,
            action=action,
            status=status,
            detail=detail,
        )
        logger.info(f"通过内部 API 写日志成功: device_id={device_id} action={action}")
    except Exception as api_err:
        # 内部 API 也失败，日志丢失但不阻塞主流程
        logger.error(f"内部 API 写日志也失败: {api_err}")
