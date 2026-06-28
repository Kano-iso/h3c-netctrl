#!/bin/bash
# check-netconf.sh — NETCONF 连接测试（ncclient hello）
# 用法: ./check-netconf.sh <ip> <username> <password>
set -euo pipefail

IP="${1:?用法: $0 <ip> <username> <password>}"
USER="${2:?}"
PASS="${3:?}"

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