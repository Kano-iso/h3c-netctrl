"""ZTP recovery override service（v3.1.3）.

用于已有设备清空配置后的兜底恢复：后端写共享 state 文件，
ztp-server 运行时读取并临时渲染 autocfg.cfg。
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.schemas import ZtpRecoveryOverrideRequest
from app.services.ztp_onboarding import derive_ztp_name

OVERRIDE_FILE = "recovery_override.json"


def _state_dir() -> Path:
    path = Path(settings.ZTP_STATE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _override_path() -> Path:
    return _state_dir() / OVERRIDE_FILE


def _validate_ipv4(host: str) -> None:
    if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host):
        raise ValueError("host 必须是 IPv4 地址")
    parts = [int(p) for p in host.split(".")]
    if any(p < 0 or p > 255 for p in parts):
        raise ValueError("host IPv4 地址不合法")


def read_recovery_override() -> dict:
    path = _override_path()
    if not path.exists():
        return {"active": False, "override": None}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {"active": True, "override": data}


def write_recovery_override(body: ZtpRecoveryOverrideRequest) -> dict:
    _validate_ipv4(body.host)
    name = body.name or derive_ztp_name(body.host)
    data = {
        "mode": "recovery",
        "host": body.host,
        "mgmt_ip": body.host,
        "sysname": name,
        "platform": body.platform,
        "hcl_t7064p15": body.hcl_t7064p15,
        "username": body.username,
        "password": body.password,
        "netconf_port": body.netconf_port,
        "collect_asset": body.collect_asset,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    path = _override_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return {"active": True, "override": data}


def clear_recovery_override() -> dict:
    path = _override_path()
    if path.exists():
        path.unlink()
    return {"active": False, "override": None}
