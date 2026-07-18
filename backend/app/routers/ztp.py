import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n_keys import err, error_response
from app.schemas import APIResponse, ZtpOnboardRequest, ZtpRecoveryOverrideRequest
from app.services.ztp_recovery import (
    clear_recovery_override,
    read_recovery_override,
    write_recovery_override,
)
from app.services.ztp_onboarding import onboard_ztp_device

logger = logging.getLogger("app")

router = APIRouter(prefix="/api/ztp", tags=["ztp"])


@router.post("/onboard", response_model=APIResponse)
def onboard_device(body: ZtpOnboardRequest, db: Session = Depends(get_db)):
    """ztp-server 确认设备上线后回调，完成纳管入库与资产同步。"""
    try:
        data = onboard_ztp_device(db, body)
        return APIResponse(success=True, data=data)
    except ValueError as e:
        return error_response(err.INVALID_PARAM, params={"param": str(e)})
    except Exception as e:
        error_msg = str(e)
        logger.error(f"ZTP 纳管失败: host={body.host} error={error_msg}", exc_info=True)
        return error_response(
            err.OPERATION_FAILED,
            params={"error": error_msg},
            fallback=error_msg,
        )


@router.get("/recovery-override", response_model=APIResponse)
def get_recovery_override():
    """查询当前 ZTP 恢复上线旁路配置。"""
    try:
        return APIResponse(success=True, data=read_recovery_override())
    except Exception as e:
        error_msg = str(e)
        logger.error(f"ZTP recovery override 查询失败: {error_msg}", exc_info=True)
        return error_response(err.OPERATION_FAILED, params={"error": error_msg}, fallback=error_msg)


@router.post("/recovery-override", response_model=APIResponse)
def set_recovery_override(body: ZtpRecoveryOverrideRequest):
    """写入一次性 ZTP 恢复上线旁路配置。"""
    try:
        return APIResponse(success=True, data=write_recovery_override(body))
    except ValueError as e:
        return error_response(err.INVALID_PARAM, params={"param": str(e)})
    except Exception as e:
        error_msg = str(e)
        logger.error(f"ZTP recovery override 写入失败: {error_msg}", exc_info=True)
        return error_response(err.OPERATION_FAILED, params={"error": error_msg}, fallback=error_msg)


@router.delete("/recovery-override", response_model=APIResponse)
def delete_recovery_override():
    """清除 ZTP 恢复上线旁路配置，ztp-server 将回到默认配置。"""
    try:
        return APIResponse(success=True, data=clear_recovery_override())
    except Exception as e:
        error_msg = str(e)
        logger.error(f"ZTP recovery override 清除失败: {error_msg}", exc_info=True)
        return error_response(err.OPERATION_FAILED, params={"error": error_msg}, fallback=error_msg)
