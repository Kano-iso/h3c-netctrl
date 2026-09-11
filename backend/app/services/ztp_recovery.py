"""ZTP recovery override service（v3.1.3 / S1-023 凭据卫生）.

用于已有设备清空配置后的兜底恢复：后端写共享 state 文件，
ztp-server 运行时读取并临时渲染 autocfg.cfg。

S1-023 凭据卫生契约：
- 密码来源（写操作）优先级：请求显式提交 password → 既有 override 已存密码 →
  ``ZTP_ADMIN_PASS`` 环境变量；全部缺失 → 明确 ``ValueError``，绝不回退代码内口令。
- recovery state 为渲染需要会把密码明文写入 git 忽略的 ``ZTP_STATE_DIR``，
  但文件权限收紧为 0600（仅 ztp-server 渲染读取）。
- API 读写响应一律脱敏：不返回 password 明文，只返回 ``password_set`` 布尔。
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

# API 可见字段中不得出现的敏感键（脱敏集合）
_SENSITIVE_KEYS = {"password"}


def _state_dir() -> Path:
    path = Path(settings.ZTP_STATE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _override_path() -> Path:
    return _state_dir() / OVERRIDE_FILE


def _redact(data: dict) -> dict:
    """递归/明确脱敏：API 响应不携带任何密码明文。"""
    out = {}
    for k, v in data.items():
        if k in _SENSITIVE_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


def _validate_ipv4(host: str) -> None:
    if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host):
        raise ValueError("host 必须是 IPv4 地址")
    parts = [int(p) for p in host.split(".")]
    if any(p < 0 or p > 255 for p in parts):
        raise ValueError("host IPv4 地址不合法")


def _resolve_password(submitted: str | None, existing: str | None) -> str:
    """写操作密码解析；全部缺失 → 明确失败（不回退代码内口令）。"""
    if submitted and submitted.strip():
        return submitted
    if existing and existing.strip():
        return existing
    env_pass = os.getenv("ZTP_ADMIN_PASS")
    if env_pass and env_pass.strip():
        return env_pass
    raise ValueError(
        "recovery 密码缺失：请在请求中显式提交 password，或配置 ZTP_ADMIN_PASS 环境变量"
        "（不回退代码内默认口令）"
    )


def read_recovery_override() -> dict:
    path = _override_path()
    if not path.exists():
        return {"active": False, "override": None}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    password_set = bool(data.get("password"))
    redacted = _redact(data)
    redacted["password_set"] = password_set
    return {"active": True, "override": redacted}


def write_recovery_override(body: ZtpRecoveryOverrideRequest) -> dict:
    _validate_ipv4(body.host)
    name = body.name or derive_ztp_name(body.host)
    existing = {}
    path = _override_path()
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    password = _resolve_password(body.password, existing.get("password"))

    data = {
        "mode": "recovery",
        "host": body.host,
        "mgmt_ip": body.host,
        "sysname": name,
        "platform": body.platform,
        "hcl_t7064p15": body.hcl_t7064p15,
        "username": body.username,
        "password": password,
        "netconf_port": body.netconf_port,
        # Recovery is a bypass path for already-known devices: restore OOB/SSH/NETCONF only.
        "collect_asset": False,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    # 明文密码只落盘 git 忽略的 state 目录；权限收紧 0600（仅 ztp-server 渲染读取）
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)

    resp = _redact(data)
    resp["password_set"] = True
    return {"active": True, "override": resp}


def clear_recovery_override() -> dict:
    path = _override_path()
    if path.exists():
        path.unlink()
    return {"active": False, "override": None}
