#!/bin/bash
# _lib.sh — ops-toolkit 公共函数库
# Part of v24-toolkit-ux-and-doc-discovery (v2.4 roadmap)
#
# 功能:
#   - _print_doc_links: 输出文档链接段（📖 用法 / 排错 SOP / 凭据来源）
#   - _resolve_device: 从后端 API 查设备 IP+凭据，或直接用 IP
#   - _die: 带上下文的错误退出

set -euo pipefail

# 文档前缀（可被环境变量覆盖）
OPS_DOCS_PREFIX="${OPS_DOCS_PREFIX:-/opt/docs}"

# 后端 API 地址（ops-toolkit 容器内通过 docker network 访问 backend）
BACKEND_URL="${BACKEND_URL:-http://backend:8000}"

# _print_doc_links <script_name>
# 输出文档链接段，所有脚本末尾调用
_print_doc_links() {
    local script_name="$1"
    echo ""
    echo "── 文档 ─────────────────────────────────"
    echo "📖 用法:        ${OPS_DOCS_PREFIX}/ops-toolkit.md#${script_name}"
    echo "📖 排错 SOP:    ${OPS_DOCS_PREFIX}/CONTAINER-CLEANUP-SOP.md"
    echo "📖 凭据来源:    ${OPS_DOCS_PREFIX}/ops-toolkit.md#凭据来源"
    echo "─────────────────────────────────────────"
}

# _resolve_device <device_name_or_ip>
# 如果参数是 IP 格式 → 直接返回，凭据从环境变量读
# 如果参数是设备名 → 从后端 API 查 IP + 凭据
# 输出: IP USER PASS（空格分隔），或失败退出
_resolve_device() {
    local input="$1"

    # 判断是否 IP 格式（简单正则）
    if [[ "$input" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        # IP 模式：凭据从环境变量
        local ip="$input"
        local user="${SSH_USER:-${DEVICE_USER:-admin}}"
        local pass="${SSH_PASS:-${DEVICE_PASS:-}}"
        if [[ -z "$pass" ]]; then
            echo "⚠️  IP 模式未提供凭据，请设置 SSH_USER + SSH_PASS 环境变量" >&2
            echo "   例: SSH_USER=admin SSH_PASS=xxx $0 $ip" >&2
            return 1
        fi
        echo "$ip $user $pass"
    else
        # 设备名模式：从后端 API 查
        local device_name="$input"
        if ! command -v curl &>/dev/null; then
            echo "❌ 设备名模式需要 curl，容器内未安装" >&2
            return 1
        fi
        local resp
        resp=$(curl -sf "${BACKEND_URL}/api/devices?name=${device_name}" 2>/dev/null) || {
            echo "❌ 后端 API 查询失败: ${BACKEND_URL}/api/devices?name=${device_name}" >&2
            echo "   确认 backend 容器在运行 + 设备名拼写正确" >&2
            return 1
        }
        # 解析 JSON（容器内无 jq，用 python）
        local parsed
        parsed=$(echo "$resp" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('data', data) if isinstance(data, dict) else data
    if isinstance(items, list) and len(items) > 0:
        d = items[0]
        print(f\"{d['ip_address']} {d.get('username','admin')} {d.get('password','')}\")
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
" 2>/dev/null) || {
            echo "❌ 设备 '${device_name}' 未找到或凭据缺失" >&2
            return 1
        }
        echo "$parsed"
    fi
}

# _die <message>
_die() {
    echo "❌ $1" >&2
    exit 1
}

# _parse_device_args <args...>
# 解析 --device <name> 或位置参数 <ip> [user] [pass]
# 输出: DEVICE_INPUT USER PASS
_parse_device_args() {
    local device_input=""
    local user=""
    local pass=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --device)
                device_input="$2"
                shift 2
                ;;
            --device=*)
                device_input="${1#*=}"
                shift
                ;;
            --user)
                user="$2"
                shift 2
                ;;
            --user=*)
                user="${1#*=}"
                shift
                ;;
            --pass)
                pass="$2"
                shift 2
                ;;
            --pass=*)
                pass="${1#*=}"
                shift
                ;;
            --help|-h)
                return 2  # 触发 usage
                ;;
            *)
                if [[ -z "$device_input" ]]; then
                    device_input="$1"
                elif [[ -z "$user" ]]; then
                    user="$1"
                elif [[ -z "$pass" ]]; then
                    pass="$1"
                fi
                shift
                ;;
        esac
    done

    [[ -z "$device_input" ]] && return 2

    # 如果显式传了 user/pass，优先用
    if [[ -n "$user" && -n "$pass" ]]; then
        echo "$device_input $user $pass"
    else
        # 否则走 _resolve_device（IP 模式读环境变量，设备名模式查 API）
        _resolve_device "$device_input"
    fi
}
