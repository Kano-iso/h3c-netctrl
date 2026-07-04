#!/bin/bash
# paramiko-batch-exec.sh — 单设备 SSH 批命令执行器（v242-paramiko-tool Task 1）
#
# 定位：研发场景的"前置加配置 + 后置验证"开发辅助工具。
# 边界：单设备（明确不做 5 设备批量配置，那是工程工具的活）。
#
# 用法:
#   paramiko-batch-exec.sh --device <name|ip> --command "display version"
#   paramiko-batch-exec.sh --device test --command "display version" --output-format json
#   paramiko-batch-exec.sh --device 192.168.100.5 --user admin --pass xxx --command "display vlan 100"
#
# 例:
#   paramiko-batch-exec.sh --device test --command "display version"
#   paramiko-batch-exec.sh --device leaf-04 --command "display version" --output-format json
#
# Task 1: 单命令 + 文本/JSON 输出
# Task 3: --commands "cmd1" "cmd2" + --commands-file
# Task 5: --timeout + --retries
set -uo pipefail

source /scripts/_lib.sh

# === 参数解析 ===
DEVICE_INPUT=""
USER=""
PASS=""
COMMANDS=()  # 数组
COMMANDS_FILE=""
OUTPUT_FORMAT="text"
TIMEOUT=30
RETRIES=0
CONTINUE_ON_ERROR=true

usage() {
    sed -n '2,20p' "$0"
    cat <<'EOF'

参数:
  --device <name|ip|alias>      设备（默认 test = .177）
  --command <cmd>               单条命令（Task 1 用法）
  --commands <cmd1> <cmd2> ...  批命令（Task 3 用法，与 --commands-file 互斥）
  --commands-file <path>        命令文件（每行 1 条，# 开头为注释）
  --user <user>                 SSH 用户（默认 admin）
  --pass <pass>                 SSH 密码（明文，不推荐，建议 --pass-cipher）
  --pass-cipher <gAAAAA...>     SSH 密码密文（Fernet，Task 2 实现）
  --timeout <seconds>           单命令 timeout（默认 30s）
  --retries <n>                 失败重试次数（默认 0，Task 5 实现）
  --output-format <text|json>   输出格式（默认 text）
  --continue-on-error           遇错继续（默认 true）
  --stop-on-error               遇错停止

文档: docs/ops-toolkit.md §4.7
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --user) USER="$2"; shift 2 ;;
        --user=*) USER="${1#*=}"; shift ;;
        --pass) PASS="$2"; shift 2 ;;
        --pass=*) PASS="${1#*=}"; shift ;;
        --command) COMMANDS+=("$2"); shift 2 ;;
        --command=*) COMMANDS+=("${1#*=}"); shift ;;
        --commands)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                COMMANDS+=("$1")
                shift
            done
            ;;
        --commands-file) COMMANDS_FILE="$2"; shift 2 ;;
        --commands-file=*) COMMANDS_FILE="${1#*=}"; shift ;;
        --output-format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --output-format=*) OUTPUT_FORMAT="${1#*=}"; shift ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --timeout=*) TIMEOUT="${1#*=}"; shift ;;
        --retries) RETRIES="$2"; shift 2 ;;
        --retries=*) RETRIES="${1#*=}"; shift ;;
        --continue-on-error) CONTINUE_ON_ERROR=true; shift ;;
        --stop-on-error) CONTINUE_ON_ERROR=false; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "❌ 未知参数: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -z "$DEVICE_INPUT" ]] && DEVICE_INPUT="${DEFAULT_DEVICE:-test}"
[[ ${#COMMANDS[@]} -eq 0 && -z "$COMMANDS_FILE" ]] && { echo "❌ 缺少 --command / --commands / --commands-file" >&2; exit 1; }
[[ ${#COMMANDS[@]} -gt 0 && -n "$COMMANDS_FILE" ]] && { echo "❌ --commands 和 --commands-file 互斥" >&2; exit 1; }

# === 设备解析 + 凭据 ===
_print_device_banner "$DEVICE_INPUT"

# 凭据来源（优先级）:
#   1. --user / --pass / --pass-cipher 显式参数
#   2. SSH_USER / SSH_PASS 环境变量
# 3. /api/devices 公共端点不返 password，所以**不**用 _resolve_device 走 API
ALIAS_RESOLVED=$(_resolve_alias "$DEVICE_INPUT")
if [[ "$ALIAS_RESOLVED" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    IP="$ALIAS_RESOLVED"
else
    # 透传（让参数原样传给后端 API 之类的后续处理）
    IP="$ALIAS_RESOLVED"
fi

# 显式 --user/--pass
[[ -n "$USER" && -z "$PASS" ]] && _die "指定 --user 必须同时指定 --pass（或 --pass-cipher）"
[[ -z "$USER" && -n "$PASS" ]] && _die "指定 --pass 必须同时指定 --user"

# 无显式凭据时读环境变量（默认走 .env 的 DEVICE_USERNAME/DEVICE_PASSWORD，开箱即用）
# 优先级: SSH_USER > DEVICE_USERNAME > admin
if [[ -z "$USER" ]]; then
    if [[ -n "${SSH_USER:-}" ]]; then
        USER="$SSH_USER"
    elif [[ -n "${DEVICE_USERNAME:-}" ]]; then
        USER="$DEVICE_USERNAME"
    elif [[ -n "${DEVICE_USER:-}" ]]; then
        USER="$DEVICE_USER"
    else
        USER="admin"
    fi
fi
# 优先级: SSH_PASS > DEVICE_PASSWORD > DEVICE_PASS
if [[ -z "$PASS" ]]; then
    if [[ -n "${SSH_PASS:-}" ]]; then
        PASS="$SSH_PASS"
    elif [[ -n "${DEVICE_PASSWORD:-}" ]]; then
        PASS="$DEVICE_PASSWORD"
    elif [[ -n "${DEVICE_PASS:-}" ]]; then
        PASS="$DEVICE_PASS"
    fi
fi

if [[ -z "$PASS" ]]; then
    _die "未提供凭据。请以下任一方式:
  - --user <user> --pass <pass>（明文，不推荐）
  - --user <user> --pass-cipher <gAAAAA...>（Fernet 密文，Task 2）
  - .env 配置 DEVICE_USERNAME + DEVICE_PASSWORD（开箱即用）
  - SSH_USER + SSH_PASS 环境变量"
fi

# === 命令文件解析 ===
if [[ -n "$COMMANDS_FILE" ]]; then
    [[ ! -f "$COMMANDS_FILE" ]] && _die "命令文件不存在: $COMMANDS_FILE"
    while IFS= read -r line; do
        # 跳过空行 + # 注释
        line="${line%%#*}"  # 去掉行内注释
        line="$(echo "$line" | xargs)"  # trim
        [[ -z "$line" ]] && continue
        COMMANDS+=("$line")
    done < "$COMMANDS_FILE"
fi

[[ ${#COMMANDS[@]} -eq 0 ]] && _die "解析后命令列表为空"

# === 调 Python 核心（env vars 传参避免 bash 解析 --pass）===
export _PMK_HOST="$IP"
export _PMK_USER="$USER"
export _PMK_PASS="$PASS"
export _PMK_COMMANDS_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${COMMANDS[@]}")"
export _PMK_TIMEOUT="$TIMEOUT"
export _PMK_OUTPUT_FORMAT="$OUTPUT_FORMAT"
export _PMK_RETRIES="$RETRIES"
export _PMK_CONTINUE_ON_ERROR="$CONTINUE_ON_ERROR"

exec python3 /scripts/_paramiko_batch_exec.py
