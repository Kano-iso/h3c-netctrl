#!/bin/bash
# check-netconf.sh — NETCONF 连接测试（ncclient hello + 能力集）
# 用法:
#   check-netconf                                # v242: 默认 test 设备
#   check-netconf --device <name|ip|alias>
#   check-netconf <ip> <user> <pass>              # 兼容 v2.3
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
            echo "用法: check-netconf [--device <name|ip|alias>] [user] [pass]"
            _print_doc_links "check-netconf"
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

echo "=== NETCONF 连接测试: $IP ==="
python3 -c "
from ncclient import manager
import sys

try:
    with manager.connect(
        host='$IP',
        port=830,
        username='$USER',
        password='$PASS',
        hostkey_verify=False,
        timeout=15,
        device_params={'name': 'h3c'},
    ) as m:
        print('✅ NETCONF 连接成功')
        print(f'   服务端能力集: {len(m.server_capabilities)} 项')
except Exception as e:
    print(f'❌ NETCONF 连接失败: {e}')
    sys.exit(1)
"
echo ""
echo "=== 完成 ==="
_print_doc_links "check-netconf"
