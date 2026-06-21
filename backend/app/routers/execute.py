import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import APIResponse
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["execute"])


class ExecuteRequest(BaseModel):
    command: str


@router.post("/devices/{device_id}/execute", response_model=APIResponse)
def execute_command(device_id: int, body: ExecuteRequest, db: Session = Depends(get_db)):
    """在设备上执行命令"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return APIResponse(success=False, error=f"设备不存在: id={device_id}")

    if not body.command or not body.command.strip():
        return APIResponse(success=False, error="命令不能为空")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        return APIResponse(success=False, error="密码解密失败")

    try:
        from app.utils.ssh_executor import SSHExecutor
        executor = SSHExecutor(
            host=device.host,
            port=22,
            username=device.username,
            password=password,
        )
        result = executor.execute(body.command.strip())

        if result["success"]:
            record_log(db, device.id, device.name, "execute", f"执行命令: {body.command.strip()}", "success")
            return APIResponse(success=True, data={
                "output": result["output"],
                "device_name": device.name,
                "execution_time": result["execution_time"],
            })
        else:
            record_log(db, device.id, device.name, "execute", f"执行命令失败: {body.command.strip()}", "failed")
            return APIResponse(success=False, error=f"命令执行失败: {result['output']}")
    except Exception as e:
        error_msg = f"命令执行异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        record_log(db, device.id, device.name, "execute", f"执行命令异常: {body.command.strip()}", "failed")
        return APIResponse(success=False, error=error_msg)
