#!/usr/bin/env python3
"""H3C reboot helper for ops-toolkit.

This helper intentionally lives under ops-toolkit instead of ztp-stack:
it is a validation/troubleshooting entrypoint for real devices, not ZTP
business logic.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from dataclasses import dataclass

import paramiko


@dataclass
class Options:
    host: str
    user: str
    password: str
    wait_ip: str
    timeout: int
    reset_saved: bool
    save_current: str


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_options() -> Options:
    host = os.environ.get("_REBOOT_HOST", "").strip()
    user = os.environ.get("_REBOOT_USER", "").strip()
    password = os.environ.get("_REBOOT_PASS", "")
    wait_ip = os.environ.get("_REBOOT_WAIT_IP", "").strip() or host
    timeout = int(os.environ.get("_REBOOT_TIMEOUT", "180"))
    save_current = os.environ.get("_REBOOT_SAVE_CURRENT", "no").strip().lower()
    if save_current not in {"yes", "no"}:
        raise ValueError("_REBOOT_SAVE_CURRENT must be yes or no")
    if not host or not user or not password:
        raise ValueError("missing _REBOOT_HOST / _REBOOT_USER / _REBOOT_PASS")
    return Options(
        host=host,
        user=user,
        password=password,
        wait_ip=wait_ip,
        timeout=timeout,
        reset_saved=_env_bool("_REBOOT_RESET_SAVED"),
        save_current=save_current,
    )


def connect_ssh(host: str, user: str, password: str, timeout: int = 10) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=22,
        username=user,
        password=password,
        timeout=timeout,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def drain(chan: paramiko.Channel, seconds: float = 0.2) -> str:
    end = time.time() + seconds
    chunks: list[bytes] = []
    while time.time() < end:
        if chan.recv_ready():
            chunks.append(chan.recv(8192))
            end = time.time() + seconds
        else:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", errors="replace")


def send_and_wait(
    chan: paramiko.Channel,
    command: str,
    handlers: list[tuple[str, str, str]],
    timeout: int,
) -> str:
    chan.send((command + "\n").encode())
    all_out = ""
    answered: set[str] = set()
    start = time.time()

    while time.time() - start < timeout:
        out = drain(chan, 0.2)
        if out:
            all_out += out
            lowered = all_out.lower()
            for key, pattern, answer in handlers:
                if key not in answered and pattern in lowered:
                    chan.send((answer + "\n").encode())
                    answered.add(key)
                    print(f"  answer {key}: {answer}")

            if command == "reset saved-configuration" and answered:
                done_markers = (
                    "configuration file is cleared",
                    "reset saved-configuration successfully",
                    "succeeded",
                    "successfully",
                )
                if any(marker in lowered for marker in done_markers):
                    return all_out
                # Some H3C versions return to prompt without a strong done marker.
                if ">" in all_out[-80:] or "]" in all_out[-80:]:
                    time.sleep(1)
                    all_out += drain(chan, 0.5)
                    return all_out

            if command == "reboot" and "continue" in answered:
                reboot_markers = ("system is rebooting", "now rebooting", "rebooting")
                if any(marker in lowered for marker in reboot_markers):
                    return all_out
        else:
            time.sleep(0.2)

    raise TimeoutError(f"{command!r} interaction timeout; tail={all_out[-500:]!r}")


def wait_ssh(opts: Options) -> None:
    print(f"=== wait SSH: {opts.wait_ip} (timeout={opts.timeout}s) ===")
    print("=== wait SSH drop ===")
    drop_start = time.time()
    dropped = False
    while time.time() - drop_start < 45:
        try:
            with socket.create_connection((opts.wait_ip, 22), timeout=2):
                pass
            print("  still reachable, waiting for reboot to take effect...")
            time.sleep(3)
        except Exception:
            dropped = True
            print("  SSH is down; start recovery wait")
            break
    if not dropped:
        print("  WARN: SSH did not go down within 45s; continuing recovery check")

    start = time.time()
    attempt = 0
    last_error = ""
    while time.time() - start < opts.timeout:
        attempt += 1
        try:
            with socket.create_connection((opts.wait_ip, 22), timeout=3):
                pass
            client = connect_ssh(opts.wait_ip, opts.user, opts.password, timeout=5)
            client.close()
            elapsed = int(time.time() - start)
            print(f"OK: SSH is ready after {elapsed}s (attempt {attempt})")
            return
        except Exception as exc:  # noqa: BLE001 - troubleshooting output should show actual error class.
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"  wait... {attempt} ({last_error})")
            time.sleep(5)
    raise TimeoutError(f"SSH did not become ready on {opts.wait_ip} within {opts.timeout}s; last={last_error}")


def main() -> int:
    opts = load_options()
    print(f"=== connect: {opts.host} ===")
    client = connect_ssh(opts.host, opts.user, opts.password)
    try:
        chan = client.invoke_shell(width=200, height=1000)
        chan.settimeout(20)
        time.sleep(1)
        drain(chan, 0.5)

        if opts.reset_saved:
            print("=== reset saved-configuration ===")
            send_and_wait(
                chan,
                "reset saved-configuration",
                [("reset", "saved configuration will be erased", "Y"), ("reset", "[y/n]", "Y")],
                timeout=40,
            )

        print("=== reboot ===")
        save_answer = "Y" if opts.save_current == "yes" else "N"
        send_and_wait(
            chan,
            "reboot",
            [
                ("save-current", "save current configuration", save_answer),
                ("continue", "continue?", "Y"),
            ],
            timeout=40,
        )
        try:
            chan.close()
        except Exception:
            pass
    finally:
        client.close()

    wait_ssh(opts)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
