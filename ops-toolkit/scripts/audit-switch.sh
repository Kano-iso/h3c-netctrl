#!/bin/bash
# audit-switch.sh — 一键巡检交换机（display version + device + interface brief）
# 用法:
#   audit-switch --device <name|ip>
#   audit-switch <ip> <user> <pass>     # 兼容 v2.3
# 输出三段巡检报告
set -euo pipefail

source /scripts/_lib.sh

DEVICE_INPUT=""
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
            echo "用法: audit-switch --device <name|ip>"
            _print_doc_links "audit-switch"
            exit 0
            ;;
        *)
            if [[ -z "$DEVICE_INPUT" ]]; then DEVICE_INPUT="$1"
            elif [[ -z "$USER" ]]; then USER="$1"
            elif [[ -z "$PASS" ]]; then PASS="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$DEVICE_INPUT" ]]; then
    echo "用法: audit-switch --device <name|ip>"
    _print_doc_links "audit-switch"
    exit 1
fi

read -r IP USER_RESOLVED PASS_RESOLVED < <(_parse_device_args "$DEVICE_INPUT" "$USER" "$PASS" 2>/dev/null) || {
    if [[ -n "$USER" && -n "$PASS" ]]; then IP="$DEVICE_INPUT"
    else _die "无法解析设备 '${DEVICE_INPUT}'"; fi
}
[[ -z "$USER" ]] && USER="$USER_RESOLVED"
[[ -z "$PASS" ]] && PASS="$PASS_RESOLVED"
[[ -z "$PASS" ]] && _die "未提供密码"

SSH_CMD() {
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        "$USER@$IP" "$1" 2>&1
}

echo "═══════════════════════════════════════"
echo "  交换机巡检报告: $IP"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════"
echo ""

# 1. 版本
echo "── [1/3] display version ──"
SSH_CMD "display version" || echo "❌ display version 失败"
echo ""

# 2. 设备信息
echo "── [2/3] display device ──"
SSH_CMD "display device" || echo "❌ display device 失败"
echo ""

# 3. 接口简表
echo "── [3/3] display interface brief ──"
SSH_CMD "display interface brief" || echo "❌ display interface brief 失败"
echo ""

echo "═══════════════════════════════════════"
echo "  ✅ 巡检完成"
echo "═══════════════════════════════════════"
_print_doc_links "audit-switch"
