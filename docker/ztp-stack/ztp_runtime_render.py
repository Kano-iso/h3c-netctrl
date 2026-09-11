#!/usr/bin/env python3
"""Runtime renderer for ztp-server autocfg.cfg.

It watches a shared recovery override file. When present, autocfg.cfg is rendered
for the recovery target; when absent, it falls back to env defaults.
"""
import json
import os
import time
from pathlib import Path

from jinja2 import Template

TFTP_DIR = Path(os.getenv("ZTP_TFTP_DIR", "/var/tftp"))
TEMPLATE_PATH = TFTP_DIR / "autocfg.cfg.j2"
OUTPUT_PATH = TFTP_DIR / "autocfg.cfg"
STATE_DIR = Path(os.getenv("ZTP_STATE_DIR", "/ztp-state"))
OVERRIDE_PATH = STATE_DIR / "recovery_override.json"



def _require_admin_pass(reason: str) -> str:
    """密码只允许来自环境；缺失 → 明确失败（fail closed，不回退代码内口令）。"""
    value = os.getenv("ZTP_ADMIN_PASS")
    if not value:
        raise RuntimeError(f"ZTP_ADMIN_PASS 未配置，无法{reason}——拒绝回退代码内口令")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def platform_long(platform: str, hcl: bool) -> str:
    if platform == "rstn":
        return "V9850 V9850-256H/R7643P02"
    if hcl:
        return "S6850 S6850/T7064P15-hcl（HCL 测试版）"
    return "S6850 S6850/T7064P15-prod（商用版）"


def default_context() -> dict:
    platform = os.getenv("ZTP_PLATFORM", "lstn")
    if platform not in {"lstn", "rstn"}:
        platform = "lstn"
    mgmt_ip = os.getenv("ZTP_MGMT_IP", "192.168.100.101")
    last = mgmt_ip.rsplit(".", 1)[-1]
    sysname = os.getenv("ZTP_SYSNAME") or f"ztp-switch-{last}"
    if sysname == "ztp-device":
        sysname = f"ztp-switch-{last}"
    hcl = env_bool("ZTP_HCL_T7064P15", False)
    return {
        "mode": "default",
        "platform": platform,
        "platform_long": platform_long(platform, hcl),
        "mgmt_ip": mgmt_ip,
        "sysname": sysname,
        "admin_user": os.getenv("ZTP_ADMIN_USER", "python"),
        "admin_pass": _require_admin_pass("渲染默认 autocfg"),
        "hcl_t7064p15": hcl,
        "ztp_date": time.strftime("%Y-%m-%d"),
    }


def load_override() -> dict | None:
    try:
        with OVERRIDE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[ztp-runtime] ignore invalid override: {e}", flush=True)
        return None

    platform = data.get("platform") or "lstn"
    if platform not in {"lstn", "rstn"}:
        platform = "lstn"
    hcl = bool(data.get("hcl_t7064p15", False))
    mgmt_ip = data.get("mgmt_ip") or data.get("host")
    if not mgmt_ip:
        return None
    last = mgmt_ip.rsplit(".", 1)[-1]
    return {
        "mode": "recovery",
        "platform": platform,
        "platform_long": platform_long(platform, hcl),
        "mgmt_ip": mgmt_ip,
        "sysname": data.get("sysname") or f"ztp-switch-{last}",
        "admin_user": data.get("username") or os.getenv("ZTP_ADMIN_USER", "python"),
        "admin_pass": data.get("password") or _require_admin_pass("渲染 recovery override"),
        "hcl_t7064p15": hcl,
        "ztp_date": time.strftime("%Y-%m-%d"),
    }


def _atomic_write_secret(path: Path, content: str) -> None:
    """安全原子写（内容含明文密码）：
    - 临时文件创建即 0600（创建前临时收紧 umask 077，规避进程 umask 放宽）
    - os.replace 原子替换；替换后显式 chmod 0600，杜绝重渲染把权限放宽
    - 异常/中断清理临时文件，不残留宽权限或含口令的中间文件
    """
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    prev_umask = os.umask(0o077)
    try:
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        finally:
            os.umask(prev_umask)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def render_once() -> str:
    context = load_override() or default_context()
    with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        content = Template(f.read()).render(**context)
    old = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else None
    if old != content:
        _atomic_write_secret(OUTPUT_PATH, content)
        print(
            f"[ztp-runtime] rendered autocfg.cfg mode={context['mode']} "
            f"platform={context['platform']} ip={context['mgmt_ip']} sysname={context['sysname']}",
            flush=True,
        )
    return context["mode"]


def main() -> int:
    interval = int(os.getenv("ZTP_RUNTIME_RENDER_INTERVAL", "2"))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    last_signature = None
    while True:
        try:
            override_mtime = OVERRIDE_PATH.stat().st_mtime if OVERRIDE_PATH.exists() else 0
            template_mtime = TEMPLATE_PATH.stat().st_mtime if TEMPLATE_PATH.exists() else 0
            signature = (override_mtime, template_mtime, tuple(sorted((k, os.getenv(k, "")) for k in [
                "ZTP_PLATFORM", "ZTP_HCL_T7064P15", "ZTP_MGMT_IP",
                "ZTP_SYSNAME", "ZTP_ADMIN_USER", "ZTP_ADMIN_PASS",
            ])))
            if signature != last_signature:
                render_once()
                last_signature = signature
        except Exception as e:
            print(f"[ztp-runtime] render failed: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
