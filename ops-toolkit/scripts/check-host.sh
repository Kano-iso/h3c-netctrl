#!/bin/bash
# check-host.sh — 主机连通性检查（ping + SSH 22 + NETCONF 830）
# 用法: ./check-host.sh <ip> [count]
set -euo pipefail

IP="${1:?用法: $0 <ip> [count]}"
COUNT="${2:-3}"

echo "=== 连通性检查: $IP ==="
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