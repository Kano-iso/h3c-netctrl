#!/bin/bash
# reboot-wait.sh — 触发 H3C reboot + 等待 SSH 恢复
# 用法:
#   reboot-wait                                  # v242: 默认 test 设备
#   reboot-wait --device <name|ip|alias>
#   reboot-wait --device test --reset-saved --wait-ip 192.168.100.101 --timeout 240
#   reboot-wait <ip> <user> <pass>               # 兼容 v2.3
# 注意: 会触发设备重启，谨慎使用
set -euo pipefail

source /scripts/_lib.sh

DEVICE_INPUT=$(_get_device_arg "$@")
USER=""
PASS=""
RESET_SAVED=false
SAVE_CURRENT="no"
WAIT_IP=""
TIMEOUT=180

while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --user) USER="$2"; shift 2 ;;
        --user=*) USER="${1#*=}"; shift ;;
        --pass) PASS="$2"; shift 2 ;;
        --pass=*) PASS="${1#*=}"; shift ;;
        --reset-saved) RESET_SAVED=true; shift ;;
        --save-current) SAVE_CURRENT="yes"; shift ;;
        --no-save-current) SAVE_CURRENT="no"; shift ;;
        --wait-ip) WAIT_IP="$2"; shift 2 ;;
        --wait-ip=*) WAIT_IP="${1#*=}"; shift ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --timeout=*) TIMEOUT="${1#*=}"; shift ;;
        --help|-h)
            cat <<'EOF'
用法:
  reboot-wait [--device <name|ip|alias>] [--timeout <seconds>]
  reboot-wait --device test --reset-saved --wait-ip 192.168.100.101 --timeout 240
  reboot-wait <ip> <user> <pass>

参数:
  --reset-saved       reboot 前先执行 reset saved-configuration 并确认 Y
  --save-current      reboot 时保存当前配置
  --no-save-current   reboot 时不保存当前配置（默认，避免覆盖 startup）
  --wait-ip <ip>      重启后等待的 SSH IP，适合 ZTP 后 IP 改变
  --timeout <seconds> 等待 SSH 恢复时间，默认 180

警告:
  该工具会触发设备重启；--reset-saved 会清空 startup 配置。
EOF
            _print_doc_links "reboot-wait"
            exit 0
            ;;
        *)
            if [[ -z "$USER" ]]; then USER="$1"
            elif [[ -z "$PASS" ]]; then PASS="$1"
            fi
            shift
            ;;
    esac
done

_print_device_banner "$DEVICE_INPUT"
DEVICE_INPUT=$(_resolve_alias "$DEVICE_INPUT")

read -r IP USER_RESOLVED PASS_RESOLVED < <(_parse_device_args "$DEVICE_INPUT" "$USER" "$PASS" 2>/dev/null) || {
    if [[ -n "$USER" && -n "$PASS" ]]; then IP="$DEVICE_INPUT"
    else _die "无法解析设备 '${DEVICE_INPUT}'"; fi
}
[[ -z "$USER" ]] && USER="$USER_RESOLVED"
[[ -z "$PASS" ]] && PASS="$PASS_RESOLVED"
[[ -z "$PASS" ]] && _die "未提供密码"
[[ -z "$WAIT_IP" ]] && WAIT_IP="$IP"

export _REBOOT_HOST="$IP"
export _REBOOT_USER="$USER"
export _REBOOT_PASS="$PASS"
export _REBOOT_WAIT_IP="$WAIT_IP"
export _REBOOT_TIMEOUT="$TIMEOUT"
export _REBOOT_RESET_SAVED="$RESET_SAVED"
export _REBOOT_SAVE_CURRENT="$SAVE_CURRENT"

python3 /scripts/_reboot_wait.py
_print_doc_links "reboot-wait"
