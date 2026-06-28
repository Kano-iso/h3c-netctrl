#!/bin/bash
# ssh-test.sh — SSH 交互测试（登录 + 执行命令）
# 用法: ./ssh-test.sh <ip> <username> <password> [command]
set -euo pipefail

IP="${1:?用法: $0 <ip> <username> <password> [command]}"
USER="${2:?}"
PASS="${3:?}"
CMD="${4:-display version}"

echo "=== SSH 测试: $IP ==="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$USER@$IP" "$CMD" 2>&1
echo ""
echo "=== 完成 ==="