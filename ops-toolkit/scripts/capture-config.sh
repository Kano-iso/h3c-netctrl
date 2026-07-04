#!/bin/bash
# capture-config.sh — SCP 拉取 startup.cfg 到 /captures/
# 用法:
#   capture-config                              # v242: 默认 test 设备
#   capture-config --device <name|ip|alias>
#   capture-config <ip> <user> <pass>           # 兼容 v2.3
# 输出: /captures/<ip>_<timestamp>_startup.cfg
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
            echo "用法: capture-config [--device <name|ip|alias>] [user] [pass]"
            _print_doc_links "capture-config"
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

TS=$(date +%Y%m%dT%H%M%S)
OUT="/captures/${IP}_${TS}_startup.cfg"

echo "=== 拉取 startup.cfg: $IP ==="
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$USER@$IP:startup.cfg" "$OUT" 2>&1

if [ -f "$OUT" ]; then
    SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null || echo "?")
    echo "✅ 成功拉到: $OUT ($SIZE bytes)"
else
    _die "拉取失败"
fi

echo ""
echo "=== 完成 ==="
_print_doc_links "capture-config"
