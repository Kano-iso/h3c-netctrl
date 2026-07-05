#!/bin/bash
# task-monitor.sh — 轮询异步任务状态（v2.5 Task 8：ops-toolkit 第 9 脚本）
#
# 背景：
#   - v2.4 引入异步任务机制（备份 / 回滚 / 长时间操作）
#   - 任务提交后立即返回 task_id，后台执行
#   - 通过 GET /api/tasks/{task_id} 查询状态
#   - ops-toolkit 容器作为 CLI 入口，方便真机/排错/CI 监控任务进度
#
# 用法:
#   task-monitor.sh <task_id>                          # 轮询直到任务完成（默认 300s 超时）
#   task-monitor.sh <task_id> --timeout <seconds>      # 自定义超时
#   task-monitor.sh <task_id> --interval <seconds>     # 自定义轮询间隔（默认 2s）
#   task-monitor.sh <task_id> --follow                 # 即使任务完成也保持轮询（持续输出）
#   task-monitor.sh <task_id> --json                   # 输出 JSON 格式（CI 友好）
#
# 退出码:
#   0 任务成功（success）
#   1 任务失败（failed）
#   2 任务超时
#   3 API 不可达 / task_id 不存在
#
# 示例:
#   task-monitor.sh task-restore-001
#   task-monitor.sh task-restore-001 --timeout 600
#   task-monitor.sh task-restore-001 --interval 5 --json
set -euo pipefail

source /scripts/_lib.sh

# 后端 API（task 走 data 容器）
API_BASE="${API_BASE:-http://data:8000/api}"
API_BASE_FALLBACK="${API_BASE_FALLBACK:-http://backend:8000/api}"

# ============================================================
# 参数解析
# ============================================================
TASK_ID=""
TIMEOUT=300
INTERVAL=2
FOLLOW=false
JSON_OUTPUT=false

usage() {
    cat <<EOF
用法: task-monitor.sh <task_id> [选项]

参数:
  <task_id>                  任务 ID（从异步 API 返回）

选项:
  --timeout <seconds>        总超时时间（默认 300s）
  --interval <seconds>       轮询间隔（默认 2s）
  --follow                   任务完成后继续轮询（持续输出）
  --json                     输出 JSON 格式（每行一个状态对象）
  --help | -h                显示本帮助

退出码:
  0  任务成功
  1  任务失败
  2  任务超时
  3  API 不可达 / task_id 不存在

示例:
  task-monitor.sh task-restore-001
  task-monitor.sh task-restore-001 --timeout 600 --interval 5
  task-monitor.sh task-restore-001 --json
EOF
    _print_doc_links "task-monitor"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h) usage ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --timeout=*) TIMEOUT="${1#*=}"; shift ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        --interval=*) INTERVAL="${1#*=}"; shift ;;
        --follow) FOLLOW=true; shift ;;
        --json) JSON_OUTPUT=true; shift ;;
        -*)
            _die "未知选项: $1（运行 --help 查看用法）"
            ;;
        *)
            if [[ -z "$TASK_ID" ]]; then
                TASK_ID="$1"
                shift
            else
                _die "多余的位置参数: $1"
            fi
            ;;
    esac
done

[[ -z "$TASK_ID" ]] && _die "缺少 task_id 参数（运行 --help 查看用法）"

# 参数校验
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT" -lt 1 ]]; then
    _die "--timeout 必须是正整数（实际: $TIMEOUT）"
fi
if ! [[ "$INTERVAL" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ "$(python3 -c "print(int($INTERVAL <= 0))")" == "1" ]]; then
    _die "--interval 必须是正数（实际: $INTERVAL）"
fi

# ============================================================
# 主循环
# ============================================================

# _fetch_status <task_id>
# 调 GET /api/tasks/{id}，输出 "status|progress|message" 格式到 stdout
# 失败：exit 3
_fetch_status() {
    local task_id="$1"
    local url="${API_BASE}/tasks/${task_id}"
    local resp http_code

    resp=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null) || {
        # fallback 到 backend 容器（core 模式）
        url="${API_BASE_FALLBACK}/tasks/${task_id}"
        resp=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null) || {
            echo "API_UNREACHABLE|0|无法访问 ${API_BASE}/tasks/${task_id}（data/backend 容器都不可达）" >&2
            exit 3
        }
    }

    http_code=$(echo "$resp" | tail -n 1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [[ "$http_code" == "404" ]]; then
        echo "NOT_FOUND|0|Task ${task_id} 不存在" >&2
        exit 3
    fi
    if [[ "$http_code" -ge 400 ]]; then
        local err
        err=$(echo "$body" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("error", d.get("detail", "HTTP 错误")))
except Exception:
    print("响应解析失败")
' 2>/dev/null)
        echo "API_ERROR|0|HTTP ${http_code}: ${err}" >&2
        exit 3
    fi

    # 解析 success + data 字段
    echo "$body" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    if not d.get("success"):
        err = d.get("error", "success=false")
        print(f"API_ERROR|0|{err}", file=sys.stderr)
        sys.exit(3)
    data = d.get("data", {})
    status = data.get("status", "unknown")
    progress = data.get("progress", 0)
    message = data.get("message", "")
    print(f"{status}|{progress}|{message}")
except Exception as e:
    print(f"PARSE_ERROR|0|JSON 解析失败: {e}", file=sys.stderr)
    sys.exit(3)
'
}

# _print_status <status> <progress> <message> [json_mode]
# 格式化输出当前状态
_print_status() {
    local status="$1"
    local progress="$2"
    local message="$3"
    local json_mode="${4:-false}"

    if [[ "$json_mode" == "true" ]]; then
        python3 -c "
import json, time
print(json.dumps({
    'task_id': '$TASK_ID',
    'status': '$status',
    'progress': $progress,
    'message': '$message',
    'timestamp': time.time(),
}, ensure_ascii=False))
"
    else
        # 终端友好输出：进度条 + 状态
        local bar=""
        local filled=$((progress / 5))
        local empty=$((20 - filled))
        for ((i=0; i<filled; i++)); do bar+="█"; done
        for ((i=0; i<empty; i++)); do bar+="░"; done

        case "$status" in
            pending)   echo "⏳ [${bar}] ${progress}% 等待中 | ${message}" ;;
            running)   echo "🔄 [${bar}] ${progress}% 执行中 | ${message}" ;;
            success)   echo "✅ [${bar}] ${progress}% 成功 | ${message}" ;;
            failed)    echo "❌ [${bar}] ${progress}% 失败 | ${message}" ;;
            cancelled) echo "⏹  [${bar}] ${progress}% 取消 | ${message}" ;;
            *)         echo "❓ [${bar}] ${progress}% ${status} | ${message}" ;;
        esac
    fi
}

# 主循环
START_TS=$(date +%s)
LAST_STATUS=""
LAST_PROGRESS=""

while true; do
    # 查状态
    raw_status=$(_fetch_status "$TASK_ID" 2>/dev/null) || {
        # _fetch_status 已输出到 stderr，exit code 3
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo "{\"task_id\": \"$TASK_ID\", \"error\": \"API 不可达\"}"
        else
            echo "❌ API 不可达或 task 不存在"
        fi
        exit 3
    }
    status=$(echo "$raw_status" | cut -d'|' -f1)
    progress=$(echo "$raw_status" | cut -d'|' -f2)
    message=$(echo "$raw_status" | cut -d'|' -f3-)

    # 输出（状态变化时一定输出，相同状态在 JSON 模式也输出，终端模式按需）
    if [[ "$status" != "$LAST_STATUS" || "$progress" != "$LAST_PROGRESS" || "$JSON_OUTPUT" == "true" ]]; then
        _print_status "$status" "$progress" "$message" "$JSON_OUTPUT"
        LAST_STATUS="$status"
        LAST_PROGRESS="$progress"
    fi

    # 终态判断
    case "$status" in
        success)
            [[ "$JSON_OUTPUT" != "true" ]] && echo ""
            echo "🎉 任务 ${TASK_ID} 执行成功"
            _print_doc_links "task-monitor"
            exit 0
            ;;
        failed)
            [[ "$JSON_OUTPUT" != "true" ]] && echo ""
            echo "💥 任务 ${TASK_ID} 执行失败：${message}"
            _print_doc_links "task-monitor"
            exit 1
            ;;
        cancelled)
            [[ "$JSON_OUTPUT" != "true" ]] && echo ""
            echo "⏹  任务 ${TASK_ID} 已取消"
            _print_doc_links "task-monitor"
            exit 1
            ;;
    esac

    # 超时检查
    NOW_TS=$(date +%s)
    ELAPSED=$((NOW_TS - START_TS))
    if [[ "$ELAPSED" -ge "$TIMEOUT" ]]; then
        [[ "$JSON_OUTPUT" != "true" ]] && echo ""
        _die "任务 ${TASK_ID} 在 ${TIMEOUT}s 内未完成（当前状态: ${status} ${progress}%）"
    fi

    # --follow 模式下即使完成也不退（在终态分支已 exit），继续轮询就 break 即可
    # （因为终态已 exit，这里只 sleep 继续）
    sleep "$INTERVAL"
done
