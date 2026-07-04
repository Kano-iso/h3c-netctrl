#!/bin/bash
# finetune_backup.sh — SSH 备份细档位压测（v2.4.2 补）
#
# 目的：精确定位 .177 设备 SSH max-session 临界点
# 5/10/20 粗档结论"~ 16-20"是插值猜的，8/12/15/18 细档才能定准
#
# 用法（在 qa-backend 容器内）：
#   bash backend/tests/perf/scenarios/finetune_backup.sh
# 预期：每档 30s，6 档共 ~4 分钟
set -euo pipefail

CONCURRENCY_LEVELS=(3 4 5 6 7 8)
DURATION=30s
RAMP_UP=3
HOST="http://backend:8000"
LOCUSTFILE="tests/perf/locustfile.py"

echo "════════════════════════════════════════════════════════════"
echo "  🔬 v2.4.2 SSH 备份细档位压测"
echo "  📌 目标设备: Test-Switch-177 (id=7)"
echo "  📊 档位: ${CONCURRENCY_LEVELS[*]}"
echo "  ⏱️  每档时长: $DURATION"
echo "════════════════════════════════════════════════════════════"
echo ""

for u in "${CONCURRENCY_LEVELS[@]}"; do
    echo "────────────────────────────────────────"
    echo "  ▶ 档位: $u 并发用户"
    echo "────────────────────────────────────────"
    # 清 .177 24h 内 backup（避免轮转影响）
    echo "  🧹 清理 .177 旧 backup..."
    rm -rf /workspace/backend/data/backups/7/* 2>/dev/null || true
    # SSH-only：选 SshBackupUser 类（不混 NETCONF）
    locust -f "$LOCUSTFILE" \
        --headless \
        --class-picker SshBackupUser \
        -u "$u" \
        -r "$RAMP_UP" \
        --run-time "$DURATION" \
        --host "$HOST" \
        --only-summary \
        2>&1 | tail -25
    # 设备 session 释放（防 H3C V7 NETCONF 锁）
    sleep 20
    echo ""
done

echo "════════════════════════════════════════════════════════════"
echo "  ✅ 细档位压测完成"
echo "  📊 看 PERF-RESULTS-v2.4.2.md §临界点分析"
echo "════════════════════════════════════════════════════════════"
