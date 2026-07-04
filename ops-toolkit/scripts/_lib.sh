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

# === v242-qa-and-tooling: 默认设备 + 别名映射 ===

# 默认设备：qa 工具反复跑，避免误连生产
DEFAULT_DEVICE="${DEFAULT_DEVICE:-test}"

# _resolve_alias <device_name_or_alias>
# 把设备名/别名映射成 IP（已知设备的小型映射表，避免查 API）
# 输入: test / Test-Switch-177 / leaf-04 / Spine-01 / IP
# 输出: IP（透传 IP 格式，其他按表查）
# 未知输入: 透传（让调用方走 _resolve_device 查 API）
_resolve_alias() {
    local input="$1"
    # 已是 IP → 透传
    if [[ "$input" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "$input"
        return 0
    fi
    # 小写化匹配
    local lc
    lc=$(echo "$input" | tr '[:upper:]' '[:lower:]')
    case "$lc" in
        test|test-switch|test-switch-177|test-switch-177)
            echo "192.168.100.177" ;;
        leaf-03|leaf03)
            echo "192.168.100.4" ;;
        leaf-04|leaf04)
            echo "192.168.100.5" ;;
        spine-01|spine01)
            echo "192.168.100.100" ;;
        *)
            # 未知别名：透传，让调用方走 API 查
            echo "$input" ;;
    esac
}

# _get_device_arg <args...>
# 解析 --device 参数，缺省返回 DEFAULT_DEVICE
# 输出: 设备名/IP（未做别名映射，调用方再 _resolve_alias）
_get_device_arg() {
    local device=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --device) device="$2"; shift 2 ;;
            --device=*) device="${1#*=}"; shift ;;
            *) shift ;;
        esac
    done
    echo "${device:-${DEFAULT_DEVICE}}"
}

# _print_device_banner <device_input>
# 打印默认设备 / 显式生产 IP 的提示横幅
# 规则：
#   - 等于 DEFAULT_DEVICE（test）→ 📌 默认目标
#   - 是 IP 且不是 192.168.100.177 → ⚠️ 生产设备
#   - 设备名 / 别名 → 静默
# 输出走 stderr，避免污染 JSON 解析（pytest 友好）
_print_device_banner() {
    local input="$1"
    if [[ "$input" == "${DEFAULT_DEVICE}" ]]; then
        echo "📌 默认目标: Test-Switch-177 (192.168.100.177)" >&2
    elif [[ "$input" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$input" != "192.168.100.177" ]]; then
        echo "⚠️  目标为生产设备: ${input}（QA 工具默认应是 .177 test 设备，注意操作）" >&2
    fi
}

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
        # 用户名从设备表读（不能 fallback 到 admin，admin 应该是显式 admin，不是占位符）
        u = d.get('username','') or ''
        p = d.get('password','') or ''
        if not u or not p:
            sys.exit(2)
        print(f'{d[\"ip_address\"]} {u} {p}')
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
" 2>/dev/null) || {
            local rc=$?
            if [[ $rc -eq 2 ]]; then
                echo "❌ 设备 '${device_name}' 凭据缺失（DB username/password 为空）" >&2
            else
                echo "❌ 设备 '${device_name}' 未找到" >&2
            fi
            return 1
        }
        echo "$parsed"
    fi
}

# _fernet_decrypt <cipher_text>
# 用 $ENCRYPTION_KEY 环境变量（.env 注入）解 Fernet 密文
# 输出: 明文密码（stdout）
# 失败: 返回非零 + stderr 提示
#
# 用法:
#   PASS=$(_fernet_decrypt "$PASS_CIPHER") || exit 1
#
# 密钥生成:
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 加密密码:
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet(b'KEY').encrypt(b'PASS').decode())"
_fernet_decrypt() {
    local cipher="$1"
    if [[ -z "${ENCRYPTION_KEY:-}" ]]; then
        echo "❌ ENCRYPTION_KEY 环境变量未设置（容器启动应通过 env_file: .env 自动注入）" >&2
        return 1
    fi
    # 用环境变量传 key + sys.argv 传密文，避免 shell 注入
    ENCRYPTION_KEY="$ENCRYPTION_KEY" python3 -c '
import os, sys
from cryptography.fernet import Fernet, InvalidToken
try:
    key = os.environ["ENCRYPTION_KEY"].encode()
    cipher = sys.argv[1].encode()
    print(Fernet(key).decrypt(cipher).decode())
except InvalidToken:
    print("❌ Fernet 解密失败：密钥错误或密文已损坏", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"❌ Fernet 解密失败: {e}", file=sys.stderr)
    sys.exit(1)
' "$cipher"
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
