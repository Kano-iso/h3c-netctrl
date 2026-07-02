#!/bin/bash
# check-host.sh — 主机连通性检查（ping + SSH 22 + NETCONF 830）
# 用法:
#   check-host --device <name|ip> [count]
#   check-host <ip> [count]                  # 兼容 v2.3
# 例:
#   check-host --device Leaf-04
#   check-host 192.168.100.5 3
set -euo pipefail

source /scripts/_lib.sh

COUNT="3"
DEVICE_INPUT=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --help|-h)
            echo "用法: check-host --device <name|ip> [count]"
            echo "例:   check-host --device Leaf-04"
            echo "      check-host 192.168.100.5 3"
            _print_doc_links "check-host"
            exit 0
            ;;
        *)
            if [[ -z "$DEVICE_INPUT" ]]; then
                DEVICE_INPUT="$1"
            else
                COUNT="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$DEVICE_INPUT" ]]; then
    echo "用法: check-host --device <name|ip> [count]"
    echo "例:   check-host --device Leaf-04"
    _print_doc_links "check-host"
    exit 1
fi

# check-host 只需 IP，不需凭据（但 _resolve_device 会校验设备名）
# 如果是设备名，从 API 查 IP；如果是 IP，直接用
if [[ "$DEVICE_INPUT" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    IP="$DEVICE_INPUT"
else
    # 设备名模式：从后端 API 查 IP（不需要凭据，只要 IP）
    IP=$(curl -sf "${BACKEND_URL}/api/devices?name=${DEVICE_INPUT}" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('data', data) if isinstance(data, dict) else data
    if isinstance(items, list) and len(items) > 0:
        print(items[0]['ip_address'])
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null) || _die "设备 '${DEVICE_INPUT}' 未找到或后端 API 不可达"
fi

echo "=== 连通性检查: $IP (count=$COUNT) ==="
echo ""

# 1. ping
echo "--- ping ---"
ping -c "$COUNT" -W 2 "$IP" 2>&1 || echo "❌ ping 失败"

# 2. SSH 22
echo ""
echo "--- SSH 22 ---"
timeout 5 nc -zv "$IP" 22 2>&1 || echo "❌ SSH 22 不通"

# 3. NETCONF 830
echo ""
echo "--- NETCONF 830 ---"
timeout 5 nc -zv "$IP" 830 2>&1 || echo "❌ NETCONF 830 不通"

echo ""
echo "=== 完成 ==="
_print_doc_links "check-host"
