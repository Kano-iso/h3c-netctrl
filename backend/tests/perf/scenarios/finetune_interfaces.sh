#!/bin/bash
# finetune_interfaces.sh — NETCONF 接口查询细档位压测（v2.4.2 补）
#
# 目的：精确定位 .177 设备 NETCONF max-session 临界点
# 5/10/20/100 粗档结论"~ 8"是插值猜的，6/8/10/12 细档才能定准
#
# 用法（在 qa-backend 容器内）：
#   bash backend/tests/perf/scenarios/finetune_interfaces.sh
# 预期：每档 30s，5 档共 ~3 分钟
set -uo pipefail

CONCURRENCY_LEVELS=(5 6 7 8 9 10 12)
DURATION=30s
RAMP_UP=5  # 每秒起 5 个用户
HOST="http://backend:8000"
LOCUSTFILE="tests/perf/locustfile.py"

echo "════════════════════════════════════════════════════════════"
echo "  🔬 v2.4.2 NETCONF 接口查询细档位压测"
echo "  📌 目标设备: Test-Switch-177 (id=7)"
echo "  📊 档位: ${CONCURRENCY_LEVELS[*]}"
echo "  ⏱️  每档时长: $DURATION"
echo "════════════════════════════════════════════════════════════"
echo ""

for u in "${CONCURRENCY_LEVELS[@]}"; do
    echo "────────────────────────────────────────"
    echo "  ▶ 档位: $u 并发用户"
    echo "────────────────────────────────────────"
    locust -f "$LOCUSTFILE" \
        --headless \
        -u "$u" \
        -r "$RAMP_UP" \
        --run-time "$DURATION" \
        --host "$HOST" \
        --only-summary \
        2>&1 | tail -25
    echo ""
done

echo "════════════════════════════════════════════════════════════"
echo "  ✅ 细档位压测完成"
echo "  📊 看 PERF-RESULTS-v2.4.2.md §临界点分析"
echo "════════════════════════════════════════════════════════════"
