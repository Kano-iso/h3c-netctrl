#!/bin/bash
# check-host.sh — 主机连通性检查（ping + SSH 22 + NETCONF 830）
# 用法:
#   check-host                                # v242: 默认 test 设备
#   check-host --device <name|ip|alias> [count]
#   check-host <ip> [count]                   # 兼容 v2.3
# 例:
#   check-host                                # → 192.168.100.177
#   check-host --device leaf-04               # → 192.168.100.5
#   check-host 192.168.100.5 3
set -euo pipefail

source /scripts/_lib.sh

COUNT="3"
DEVICE_INPUT=$(_get_device_arg "$@")

# 剩余参数（count）
for arg in "$@"; do
    case "$arg" in
        --device|--device=*) ;;
        *) [[ "$arg" != "${DEVICE_INPUT}" ]] && COUNT="$arg" ;;
    esac
done

# 默认设备提示
_print_device_banner "$DEVICE_INPUT"

# check-host 只需 IP，不需凭据（但 _resolve_alias 已处理别名）
DEVICE_INPUT=$(_resolve_alias "$DEVICE_INPUT")

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
