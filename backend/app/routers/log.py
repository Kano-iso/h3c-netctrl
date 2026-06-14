import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Log
from app.schemas import APIResponse, LogResponse

logger = logging.getLogger("app")

router = APIRouter(tags=["log"])


@router.get("/logs", response_model=APIResponse)
def get_logs(
    device_id: Optional[int] = Query(None, description="按设备ID筛选"),
    action: Optional[str] = Query(None, description="按操作类型筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """查询操作日志，支持筛选和分页"""
    query = db.query(Log)

    if device_id is not None:
        query = query.filter(Log.device_id == device_id)
    if action:
        query = query.filter(Log.action == action)

    total = query.count()
    items = query.order_by(Log.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    data = {
        "items": [LogResponse.model_validate(log).model_dump() for log in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
    return APIResponse(success=True, data=data)
