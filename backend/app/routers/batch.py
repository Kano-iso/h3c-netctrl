import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import APIResponse
from app.i18n_keys import err, error_response
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["batch"])


class BatchExecuteRequest(BaseModel):
    device_ids: list[int]
    command: str


@router.post("/batch/execute", response_model=APIResponse)
def batch_execute(body: BatchExecuteRequest, db: Session = Depends(get_db)):
    """批量在多台设备上执行命令"""
    if not body.device_ids:
        return error_response(err.BATCH_NO_DEVICES)
    if not body.command or not body.command.strip():
        return error_response(err.BATCH_EMPTY_COMMAND)

    # 统一设备批量访问（monolith 本地查 / split 走 internal_api）
    from app.utils.device_access import get_devices_batch
    devices = get_devices_batch(db, body.device_ids)
    if not devices:
        return error_response(err.NOT_FOUND, params={"resource": "devices"})

    command = body.command.strip()
    results = []

    def execute_on_device(device):
        try:
            # split 模式 device 是 SimpleNamespace，_password_decrypted 已解密
            # monolith 模式 device 是 ORM 对象，需要 decrypt_password
            password = getattr(device, "_password_decrypted", None) or decrypt_password(device.password_encrypted)
            from app.utils.ssh_executor import SSHExecutor
            executor = SSHExecutor(host=device.host, port=22, username=device.username, password=password)
            result = executor.execute(command)
            return {
                "device_id": device.id,
                "device_name": device.name,
                "success": result["success"],
                "output": result["output"] if result["success"] else None,
                "error": result["output"] if not result["success"] else None,
            }
        except Exception as e:
            return {
                "device_id": device.id,
                "device_name": device.name,
                "success": False,
                "output": None,
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(execute_on_device, d): d for d in devices}
        for future in as_completed(futures):
            results.append(future.result())

    success_count = sum(1 for r in results if r["success"])
    failed_count = len(results) - success_count

    # 记录批量操作日志
    for device in devices:
        status = "success" if any(r["device_id"] == device.id and r["success"] for r in results) else "failed"
        error_msg = None
        if status == "failed":
            error_msg = next((r.get("error", "") for r in results if r["device_id"] == device.id and not r["success"]), "")
        record_log(db, device.id, device.name, "batch_execute", f"批量执行: {command}", status, error_message=error_msg)

    return APIResponse(success=True, data={
        "total": len(results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    })
