import logging
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import APIResponse
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["execute"])


class ExecuteRequest(BaseModel):
    """命令执行请求

    两种入参模式，向后兼容：
    - 单命令：`{command: "display version"}`（原路径不变）
    - 多命令：`{commands: ["cmd1", "cmd2"], delay_ms: 1000}`
    至少 `command` 或 `commands` 其中一个必须非空。
    """
    command: Optional[str] = None
    commands: Optional[List[str]] = None
    delay_ms: Optional[int] = 1000

    @model_validator(mode="after")
    def _validate(self):
        if not self.command and not self.commands:
            raise ValueError("command 与 commands 至少需要一个非空")
        if self.commands is not None and len(self.commands) == 0:
            raise ValueError("commands 数组不能为空")
        return self


@router.post("/devices/{device_id}/execute", response_model=APIResponse)
def execute_command(device_id: int, body: ExecuteRequest, db: Session = Depends(get_db)):
    """在设备上执行命令（单条 / 多条顺序执行，遇错继续）"""
    # 统一设备访问（monolith 本地查 / split 走 internal_api）
    from app.utils.device_access import get_device_with_password
    device, password, error_resp = get_device_with_password(db, device_id)
    if error_resp:
        return error_resp
    if not device or not password:
        return APIResponse(success=False, error=f"设备不存在或密码获取失败: id={device_id}")

    try:
        from app.utils.ssh_executor import SSHExecutor
        executor = SSHExecutor(
            host=device.host,
            port=22,
            username=device.username,
            password=password,
        )

        # 多命令顺序执行
        if body.commands:
            commands = [c.strip() for c in body.commands if c and c.strip()]
            if not commands:
                return APIResponse(success=False, error="commands 数组不能全为空行")

            delay_ms = body.delay_ms if body.delay_ms is not None else 1000
            if delay_ms < 0:
                delay_ms = 0

            results = executor.execute_commands(commands, delay_ms=delay_ms)
            total = len(results)
            failed = [r for r in results if not r["success"]]

            if failed:
                record_log(
                    db, device.id, device.name, "execute",
                    f"批量执行 {total} 条命令（{len(failed)} 条失败）: "
                    + " | ".join(r["cmd"] for r in results),
                    "failed",
                    error_message="\n".join(f"[{i+1}] {r['cmd']}: {r['error']}" for i, r in enumerate(failed)),
                )
            else:
                record_log(
                    db, device.id, device.name, "execute",
                    f"批量执行 {total} 条命令: " + " | ".join(r["cmd"] for r in results),
                    "success",
                )

            return APIResponse(success=True, data={
                "results": results,
                "total": total,
                "failed_count": len(failed),
                "device_name": device.name,
            })

        # 单命令（向后兼容）
        cmd = body.command.strip()
        if not cmd:
            return APIResponse(success=False, error="命令不能为空")

        result = executor.execute(cmd)

        if result["success"]:
            record_log(db, device.id, device.name, "execute", f"执行命令: {cmd}", "success")
            return APIResponse(success=True, data={
                "output": result["output"],
                "device_name": device.name,
                "execution_time": result["execution_time"],
            })
        else:
            record_log(db, device.id, device.name, "execute", f"执行命令失败: {cmd}", "failed", error_message=result['output'])
            return APIResponse(success=False, error=f"命令执行失败: {result['output']}")
    except Exception as e:
        error_msg = f"命令执行异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        record_log(db, device.id, device.name, "execute", f"命令执行异常: {body.command or body.commands}", "failed", error_message=str(e))
        return APIResponse(success=False, error=error_msg)
