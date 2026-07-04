#!/bin/bash
# 100_concurrent_interfaces.sh — NETCONF 接口查询压测（locust）
# 目标: 100 并发用户持续 60s 调 GET /api/devices/7/interfaces
# 阈值: P99 < 5s, 失败率 < 1%
#
# 用法:
#   docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
#     bash tests/perf/scenarios/100_concurrent_interfaces.sh
#
# 前置:
#   - 后端已起 (monolith / split 均可)
#   - .177 设备可达
set -euo pipefail

# 默认从容器内连 backend（monolith 模式默认端口 8000）
HOST="${PERF_HOST:-http://backend:8000}"
USERS="${PERF_USERS:-100}"
SPAWN="${PERF_SPAWN:-10}"
RUNTIME="${PERF_RUNTIME:-60s}"

echo "═══════════════════════════════════════════════════════"
echo "  🚀 100 并发接口查询压测"
echo "  📌 目标设备: Test-Switch-177 (192.168.100.177, id=7)"
echo "  🌐 host: $HOST"
echo "  ⚙️  并发: $USERS / spawn=$SPAWN / runtime=$RUNTIME"
echo "═══════════════════════════════════════════════════════"

# 压前检查：后端可达
echo "🔍 压前检查: $HOST/health"
if ! curl -fsS --max-time 5 "$HOST/health" >/dev/null; then
    echo "❌ 后端不可达，请先 docker compose up -d backend"
    exit 1
fi
echo "✅ 后端可达"

# 压前检查：设备可达
echo "🔍 压前检查: .177 设备可达"
if ! nc -z -w 3 192.168.100.177 830; then
    echo "❌ .177 NETCONF 830 端口不通"
    exit 1
fi
echo "✅ .177 NETCONF 可达"

# 跑压测
echo ""
echo "🚀 启动 locust..."
locust -f tests/perf/locustfile.py \
    --headless \
    -u "$USERS" \
    -r "$SPAWN" \
    --run-time "$RUNTIME" \
    --host "$HOST" \
    --only-summary \
    NetconfConfigUser

echo ""
echo "✅ 压测完成"
echo "📊 建议监控命令: watch -n 1 'ss -tan | grep 192.168.100.177 | wc -l'"
