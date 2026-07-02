#!/bin/bash
# ssh-test.sh — SSH 交互测试（登录 + 执行命令）
# 用法:
#   ssh-test --device <name|ip> [command]
#   ssh-test <ip> <user> <pass> [command]   # 兼容 v2.3
# 默认命令: display version
set -euo pipefail

source /scripts/_lib.sh

DEVICE_INPUT=""
USER=""
PASS=""
CMD="display version"

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --user) USER="$2"; shift 2 ;;
        --user=*) USER="${1#*=}"; shift ;;
        --pass) PASS="$2"; shift 2 ;;
        --pass=*) PASS="${1#*=}"; shift ;;
        --cmd) CMD="$2"; shift 2 ;;
        --cmd=*) CMD="${1#*=}"; shift ;;
        --help|-h)
            echo "用法: ssh-test --device <name|ip> [command]"
            echo "      ssh-test <ip> <user> <pass> [command]"
            _print_doc_links "ssh-test"
            exit 0
            ;;
        *)
            if [[ -z "$DEVICE_INPUT" ]]; then
                DEVICE_INPUT="$1"
            elif [[ -z "$USER" ]]; then
                USER="$1"
            elif [[ -z "$PASS" ]]; then
                PASS="$1"
            else
                CMD="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$DEVICE_INPUT" ]]; then
    echo "用法: ssh-test --device <name|ip> [command]"
    _print_doc_links "ssh-test"
    exit 1
fi

# 解析设备 → IP USER PASS
read -r IP USER_RESOLVED PASS_RESOLVED < <(_parse_device_args "$DEVICE_INPUT" "$USER" "$PASS" 2>/dev/null) || {
    # _parse_device_args 失败时 fallback 位置参数
    if [[ -n "$USER" && -n "$PASS" ]]; then
        IP="$DEVICE_INPUT"
    else
        _die "无法解析设备 '${DEVICE_INPUT}'，请检查设备名或显式传 --user --pass"
    fi
}
[[ -z "$USER" ]] && USER="$USER_RESOLVED"
[[ -z "$PASS" ]] && PASS="$PASS_RESOLVED"
[[ -z "$PASS" ]] && _die "未提供密码（--pass 或 SSH_PASS 环境变量）"

echo "=== SSH 测试: $IP (cmd: $CMD) ==="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$USER@$IP" "$CMD" 2>&1
echo ""
echo "=== 完成 ==="
_print_doc_links "ssh-test"
