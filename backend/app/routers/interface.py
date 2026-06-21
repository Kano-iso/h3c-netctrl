import logging
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import APIResponse
from app.utils.crypto import decrypt_password
from app.utils.log_recorder import record_log

logger = logging.getLogger("app")

router = APIRouter(tags=["interface"])


class InterfaceConfig(BaseModel):
    mode: str  # "access" or "trunk"
    access_vlan: Optional[int] = None
    allowed_vlans: Optional[List[int]] = None
    pvid: Optional[int] = None


def parse_interface_brief(output: str) -> list:
    """解析 display interface brief 输出"""
    interfaces = []
    lines = output.strip().split('\n')
    for line in lines:
        # 匹配 GE/XGE 等接口行
        match = re.match(r'^(GE|XGE|FGE|Ten-GE|GigabitEthernet|Ten-GigabitEthernet)\s*(\S+)\s*(\S+)?\s*(\S+)?', line.strip())
        if match:
            interfaces.append({
                "name": match.group(2) if match.group(2) else line.strip().split()[0],
                "status": match.group(3) if match.group(3) else "unknown",
                "mode": "unknown",
                "access_vlan": None,
                "allowed_vlans": [],
                "pvid": None,
            })
    # 如果正则没匹配到，尝试更宽松的解析
    if not interfaces:
        for line in lines:
            line = line.strip()
            if re.match(r'^(GE|XGE|GigabitEthernet|Ten-GigabitEthernet)', line):
                parts = line.split()
                if len(parts) >= 2:
                    interfaces.append({
                        "name": parts[0],
                        "status": parts[1] if len(parts) > 1 else "unknown",
                        "mode": "unknown",
                        "access_vlan": None,
                        "allowed_vlans": [],
                        "pvid": None,
                    })
    return interfaces


@router.get("/devices/{device_id}/interfaces", response_model=APIResponse)
def get_interfaces(device_id: int, db: Session = Depends(get_db)):
    """获取设备接口列表"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return APIResponse(success=False, error=f"设备不存在: id={device_id}")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        return APIResponse(success=False, error="密码解密失败")

    try:
        from app.utils.ssh_executor import SSHExecutor
        executor = SSHExecutor(host=device.host, port=22, username=device.username, password=password)
        result = executor.execute("display interface brief")
        if result["success"]:
            interfaces = parse_interface_brief(result["output"])
            return APIResponse(success=True, data=interfaces)
        else:
            return APIResponse(success=False, error=f"获取接口列表失败: {result['output']}")
    except Exception as e:
        logger.error(f"获取接口列表异常: {e}", exc_info=True)
        return APIResponse(success=False, error=f"获取接口列表异常: {str(e)}")


@router.put("/devices/{device_id}/interfaces/{interface_name}/config", response_model=APIResponse)
def configure_interface(device_id: int, interface_name: str, body: InterfaceConfig, db: Session = Depends(get_db)):
    """下发接口配置"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return APIResponse(success=False, error=f"设备不存在: id={device_id}")

    if body.mode not in ("access", "trunk"):
        return APIResponse(success=False, error="模式必须是 access 或 trunk")

    try:
        password = decrypt_password(device.password_encrypted)
    except Exception as e:
        return APIResponse(success=False, error="密码解密失败")

    # 构建 CLI 配置命令
    commands = [f"system-view", f"interface {interface_name}"]

    if body.mode == "access":
        commands.append("port link-mode bridge")
        commands.append("port link-type access")
        if body.access_vlan:
            commands.append(f"port access vlan {body.access_vlan}")
    elif body.mode == "trunk":
        commands.append("port link-mode bridge")
        commands.append("port link-type trunk")
        if body.allowed_vlans:
            vlans_str = ",".join(str(v) for v in body.allowed_vlans)
            commands.append(f"port trunk permit vlan {vlans_str}")
        if body.pvid:
            commands.append(f"port trunk pvid vlan {body.pvid}")

    commands.append("return")

    try:
        from app.utils.ssh_executor import SSHExecutor
        executor = SSHExecutor(host=device.host, port=22, username=device.username, password=password)
        # 逐条发送命令
        full_command = "\n".join(commands)
        result = executor.execute(full_command)

        if result["success"]:
            record_log(db, device.id, device.name, "interface_config",
                       f"配置接口 {interface_name}: mode={body.mode}", "success")
            return APIResponse(success=True, data={"message": f"接口 {interface_name} 配置已下发"})
        else:
            record_log(db, device.id, device.name, "interface_config",
                       f"配置接口 {interface_name} 失败", "failed")
            return APIResponse(success=False, error=f"配置下发失败: {result['output']}")
    except Exception as e:
        logger.error(f"接口配置异常: {e}", exc_info=True)
        record_log(db, device.id, device.name, "interface_config",
                   f"配置接口 {interface_name} 异常", "failed")
        return APIResponse(success=False, error=f"配置下发异常: {str(e)}")
