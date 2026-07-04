#!/bin/bash
# 50_concurrent_backup.sh — SSH 备份压测（locust）
# 目标: 50 并发用户持续 60s 调 POST /api/devices/7/backup
# 阈值: P99 < 30s, 失败率 < 1%
#
# 用法:
#   docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \
#     bash tests/perf/scenarios/50_concurrent_backup.sh
#
# 前置:
#   - 后端已起
#   - .177 SSH 22 可达
#   - backup 目录空间充足（>500MB 推荐）
set -euo pipefail

HOST="${PERF_HOST:-http://backend:8000}"
USERS="${PERF_USERS:-50}"
SPAWN="${PERF_SPAWN:-5}"
RUNTIME="${PERF_RUNTIME:-60s}"

echo "═══════════════════════════════════════════════════════"
echo "  🚀 50 并发备份压测"
echo "  📌 目标设备: Test-Switch-177 (192.168.100.177, id=7)"
echo "  🌐 host: $HOST"
echo "  ⚙️  并发: $USERS / spawn=$SPAWN / runtime=$RUNTIME"
echo "═══════════════════════════════════════════════════════"

# 压前检查：后端可达
echo "🔍 压前检查: $HOST/health"
if ! curl -fsS --max-time 5 "$HOST/health" >/dev/null; then
    echo "❌ 后端不可达"
    exit 1
fi
echo "✅ 后端可达"

# 压前检查：SSH 可达
echo "🔍 压前检查: .177 SSH 22"
if ! nc -z -w 3 192.168.100.177 22; then
    echo "❌ .177 SSH 22 不通"
    exit 1
fi
echo "✅ .177 SSH 可达"

# 压前清理：删 .177 24h 内 backup（避免轮转干扰）
echo "🧹 压前清理: 删 24h 内 .177 backup"
BACKUP_DIR="${BACKUP_DIR:-/app/data/backups}"
if [ -d "$BACKUP_DIR" ]; then
    find "$BACKUP_DIR" -name "*-7_*" -mmin -1440 -delete 2>/dev/null || true
    BEFORE=$(find "$BACKUP_DIR" -type f 2>/dev/null | wc -l)
    echo "  当前 backup 文件数: $BEFORE"
fi

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
    SshBackupUser

echo ""
echo "✅ 压测完成"
echo "📊 backup 文件变化: $BEFORE → $(find "$BACKUP_DIR" -type f 2>/dev/null | wc -l)"
echo "📊 轮转检查: 后端日志 grep 'rotation'"
