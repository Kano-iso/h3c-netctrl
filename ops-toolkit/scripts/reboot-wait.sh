#!/bin/bash
# reboot-wait.sh — 触发 reboot + 等待 SSH 恢复（最多 120s）
# 用法: ./reboot-wait.sh <ip> <username> <password>
set -euo pipefail

IP="${1:?用法: $0 <ip> <username> <password>}"
USER="${2:?}"
PASS="${3:?}"

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
        exit 0
    fi
    echo "  等待... (${i}/24)"
done

echo "❌ SSH 超时未恢复（120s）"
exit 1