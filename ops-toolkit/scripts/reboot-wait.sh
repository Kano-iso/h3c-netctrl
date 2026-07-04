#!/bin/bash
# reboot-wait.sh — 触发 reboot + 等待 SSH 恢复（最多 120s）
# 用法:
#   reboot-wait                                  # v242: 默认 test 设备
#   reboot-wait --device <name|ip|alias>
#   reboot-wait <ip> <user> <pass>               # 兼容 v2.3
# 注意: 会触发设备重启，谨慎使用
set -euo pipefail

source /scripts/_lib.sh

DEVICE_INPUT=$(_get_device_arg "$@")
USER=""
PASS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --user) USER="$2"; shift 2 ;;
        --user=*) USER="${1#*=}"; shift ;;
        --pass) PASS="$2"; shift 2 ;;
        --pass=*) PASS="${1#*=}"; shift ;;
        --help|-h)
            echo "用法: reboot-wait [--device <name|ip|alias>] [user] [pass]"
            echo "警告: 会触发设备重启"
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

echo "=== 触发 reboot: $IP ==="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$USER@$IP" "reboot" <<< "Y" 2>&1 || true

echo "等待 SSH 恢复（最多 120s）..."
for i in $(seq 1 24); do
    sleep 5
    if timeout 5 nc -zv "$IP" 22 2>/dev/null; then
        echo "✅ SSH 已恢复（$((i * 5))s）"
        echo ""
        echo "=== 设备版本 ==="
        sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            "$USER@$IP" "display version" 2>&1
        _print_doc_links "reboot-wait"
        exit 0
    fi
    echo "  等待... (${i}/24)"
done

_die "SSH 超时未恢复（120s）"
