#!/usr/bin/env python3
"""ZTP static-IP online confirmer and backend callback.

Runs inside ztp-server. It waits for the configured static management IP to
open SSH 22 and NETCONF 830, then POSTs /api/ztp/onboard.
"""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STATE_DIR = Path(os.getenv("ZTP_STATE_DIR", "/ztp-state"))
OVERRIDE_PATH = STATE_DIR / "recovery_override.json"


def getenv_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body or "{}")


def load_override() -> dict:
    try:
        with OVERRIDE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}


def current_payload(netconf_port: int) -> dict:
    override = load_override()
    host = override.get("host") or override.get("mgmt_ip") or os.getenv("ZTP_MGMT_IP", "192.168.100.101")
    return {
        "host": host,
        "name": override.get("sysname") or os.getenv("ZTP_SYSNAME") or None,
        "username": override.get("username") or os.getenv("ZTP_ADMIN_USER", "python"),
        "password": override.get("password") or os.getenv("ZTP_ADMIN_PASS", "Admin123!@#"),
        "port": int(override.get("netconf_port") or netconf_port),
        "platform": override.get("platform") or os.getenv("ZTP_PLATFORM") or None,
        "collect_asset": override.get(
            "collect_asset",
            os.getenv("ZTP_ONBOARD_COLLECT_ASSET", "true").lower() == "true",
        ),
        "source": "ztp-server",
    }


def main() -> int:
    api_url = os.getenv("ZTP_ONBOARD_API_URL", "http://127.0.0.1:8001/api/ztp/onboard")
    timeout = getenv_int("ZTP_ONBOARD_TIMEOUT", 300)
    interval = getenv_int("ZTP_ONBOARD_INTERVAL", 5)
    initial_delay = getenv_int("ZTP_ONBOARD_INITIAL_DELAY", 20)
    netconf_port = getenv_int("ZTP_ONBOARD_NETCONF_PORT", 830)

    print(
        f"=== ZTP onboard watcher === api={api_url} "
        f"timeout={timeout}s interval={interval}s",
        flush=True,
    )
    time.sleep(initial_delay)

    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = current_payload(netconf_port)
        host = payload["host"]
        port = payload["port"]
        ssh_ok = tcp_open(host, 22)
        netconf_ok = tcp_open(host, port)
        print(f"[ztp-onboard] probe host={host} ssh22={ssh_ok} netconf{port}={netconf_ok}", flush=True)
        if ssh_ok and netconf_ok:
            try:
                resp = post_json(api_url, payload)
                print(f"[ztp-onboard] callback response: {json.dumps(resp, ensure_ascii=False)}", flush=True)
                return 0 if resp.get("success") else 2
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                print(f"[ztp-onboard] callback failed: {e}", file=sys.stderr, flush=True)
                return 3
        time.sleep(interval)

    print(f"[ztp-onboard] timeout waiting for static IP online: {host}", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
