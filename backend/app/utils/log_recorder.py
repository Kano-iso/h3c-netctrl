import logging
from sqlalchemy.orm import Session

from app.models import Log

logger = logging.getLogger("app")


def record_log(db: Session, device_id: int, device_name: str, action: str, detail: str, status: str, error_message: str = None):
    """记录操作日志到数据库"""
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
    except Exception as e:
        logger.error(f"记录操作日志失败: {e}")
        db.rollback()
