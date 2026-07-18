import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n_keys import err, error_response
from app.schemas import APIResponse, ZtpOnboardRequest
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
