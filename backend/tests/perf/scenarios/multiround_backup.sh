#!/bin/bash
# multiround_backup.sh — SSH 备份多轮压测（v2.4.2 补）
#
# 目的：消除单轮压测的随机性，确定 SSH 临界点区间
# 细档位单轮结论"SSH max-session = 6"可能是设备瞬时波动
#
# 设计：
# - 档位 7（细档位临界点 +1） × 3 轮：验证"6 临界"是否稳定
# - 档位 14（2 倍）           × 3 轮：验证设备能否突破 7 上限
# - 每轮间 sleep 30s 让设备 session 释放
# - 每档前 sleep 60s 让设备完全冷却
#
# 用法（在 qa-backend 容器内）：
#   bash backend/tests/perf/scenarios/multiround_backup.sh
# 预期：6 轮 × (30s + 30s sleep) = ~6 分钟
set -uo pipefail

ROUNDS=3
DURATION=30s
SLEEP_BETWEEN_ROUNDS=30
SLEEP_BETWEEN_LEVELS=60
HOST="http://backend:8000"
LOCUSTFILE="tests/perf/locustfile.py"

LEVELS=(7 14)

echo "════════════════════════════════════════════════════════════"
echo "  🔬 v2.4.2 SSH 备份多轮压测（v2.4.2 补 2）"
echo "  📌 目标设备: Test-Switch-177 (id=7)"
echo "  📊 档位: ${LEVELS[*]}"
echo "  🔄 每档轮数: $ROUNDS"
echo "  ⏱️  每轮时长: $DURATION"
echo "  💤 轮间 sleep: ${SLEEP_BETWEEN_ROUNDS}s, 档间 sleep: ${SLEEP_BETWEEN_LEVELS}s"
echo "════════════════════════════════════════════════════════════"
echo ""

for level in "${LEVELS[@]}"; do
    echo "=========================================="
    echo "  📊 档位: $level 并发用户（共 $ROUNDS 轮）"
    echo "=========================================="
    for round in $(seq 1 $ROUNDS); do
        echo ""
        echo "  ▶ 轮次: $round / $ROUNDS"
        echo "  ----------------------------------------"
        logfile="/tmp/multiround_ssh_${level}_r${round}.log"
        locust -f "$LOCUSTFILE" \
            --headless \
            --class-picker SshBackupUser \
            -u "$level" \
            -r 3 \
            --run-time "$DURATION" \
            --host "$HOST" \
            --only-summary \
            2>&1 | tee "$logfile" | tail -20
        if [ "$round" -lt "$ROUNDS" ]; then
            echo "  💤 sleep ${SLEEP_BETWEEN_ROUNDS}s（设备 SSH session 释放）..."
            sleep "$SLEEP_BETWEEN_ROUNDS"
        fi
    done
    if [ "$level" != "${LEVELS[-1]}" ]; then
        echo ""
        echo "  💤 sleep ${SLEEP_BETWEEN_LEVELS}s（设备完全冷却）..."
        sleep "$SLEEP_BETWEEN_LEVELS"
    fi
    echo ""
done

echo "════════════════════════════════════════════════════════════"
echo "  ✅ 多轮压测完成"
echo "  📊 详细 log: /tmp/multiround_ssh_*.log"
echo "════════════════════════════════════════════════════════════"
echo ""

for level in "${LEVELS[@]}"; do
    echo "--- SSH $level 并发 × $ROUNDS 轮 ---"
    for round in $(seq 1 $ROUNDS); do
        logfile="/tmp/multiround_ssh_${level}_r${round}.log"
        if [ -f "$logfile" ]; then
            reqs=$(grep "POST     POST" "$logfile" | awk '{print $NF}' | head -1)
            fails=$(grep -c "POST POST" "$logfile" 2>/dev/null || echo 0)
            echo "  轮 $round: reqs=$reqs, POST 失败数=$fails"
        fi
    done
done
