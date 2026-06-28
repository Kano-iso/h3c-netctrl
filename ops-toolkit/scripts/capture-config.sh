#!/bin/bash
# capture-config.sh — SCP 拉取 startup.cfg 到 /captures/
# 用法: ./capture-config.sh <ip> <username> <password>
set -euo pipefail

IP="${1:?用法: $0 <ip> <username> <password>}"
USER="${2:?}"
PASS="${3:?}"
TS=$(date +%Y%m%dT%H%M%S)
OUT="/captures/${IP}_${TS}_startup.cfg"

echo "=== 拉取 startup.cfg: $IP ==="
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$USER@$IP:startup.cfg" "$OUT" 2>&1

if [ -f "$OUT" ]; then
    SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null || echo "?")
    echo "✅ 成功拉到: $OUT ($SIZE bytes)"
else
    echo "❌ 拉取失败"
    exit 1
fi