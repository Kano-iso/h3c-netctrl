#!/bin/bash
# interface-config.sh — 接口配置（VLAN/Access/Trunk）的 CLI 入口
# v2.5 Task 7：ops-toolkit 第 8 脚本
#
# 背景：
#   - 后端已经实现了完整的接口配置 API（POST /api/devices/{id}/vlans, /interfaces/config 等）
#   - 通过 ops-toolkit 容器 CLI 调用，方便真机环境/排错/巡检
#   - 不重复造 NETCONF，直接调后端 API
#
# 用法:
#   interface-config.sh vlan add    <device> <vlan_id> <name>     # 创建 VLAN
#   interface-config.sh vlan del    <device> <vlan_id>            # 删除 VLAN
#   interface-config.sh access set  <device> <if_index> <vlan>   # 设置 access vlan
#   interface-config.sh trunk allow <device> <if_index> <vlans>  # 设置 trunk 允许 vlan
#                                                            # <vlans> 格式: 100,200,300
#
# 参数:
#   <device>    设备名 / IP / 别名（test=192.168.100.177）
#   <vlan_id>   VLAN ID（1-4094）
#   <if_index>  接口索引（NETCONF IfIndex，通过 capture-config.sh 查）
#   <name>      VLAN 名称
#   <vlan>      access vlan id（1-4094）
#   <vlans>     trunk 允许 vlan 列表（逗号分隔，如 100,200,300）
#
# 输出:
#   成功 → ✅ 信息（含 backend 返回的 detail）
#   失败 → ❌ 信息（含 backend 返回的 error 字段）
#
# 示例:
#   interface-config.sh vlan add test 100 "业务 A"
#   interface-config.sh vlan del test 100
#   interface-config.sh access set test 2 100
#   interface-config.sh trunk allow test 3 100,200,300
#
# 凭据：与后端 API 一致（不重复落地，凭据从 .env 注入，容器内 API 调用不带凭据）
set -euo pipefail

source /scripts/_lib.sh

# 后端 API base（v2.5 split 模式下 ctrl 容器 8000 端口）
# 但 interface config 走 config 容器（INTERNAL_CONFIG_URL 默认 http://config:8000）
# ops-toolkit 容器内访问 backend service（v2.4.1+ 统一 3 容器架构）
# - split 模式（默认）：config 容器跑 interface + vlan
# - core 模式（--profile core）：backend 容器跑所有
# 用 VITE_API_MODE 对应后端变量做兼容
API_BASE="${API_BASE:-http://config:8000/api}"
# core 模式 fallback（如果 config 不可达就试 backend）
API_BASE_FALLBACK="${API_BASE_FALLBACK:-http://backend:8000/api}"

# ============================================================
# 帮助
# ============================================================
usage() {
    cat <<EOF
用法: interface-config.sh <子命令> [参数...]

子命令:
  vlan add    <device> <vlan_id> <name>     创建 VLAN
  vlan del    <device> <vlan_id>            删除 VLAN
  access set  <device> <if_index> <vlan>    设置 access vlan
  trunk allow <device> <if_index> <vlans>   设置 trunk 允许 vlan（逗号分隔）
  --help | -h                                显示本帮助

示例:
  interface-config.sh vlan add test 100 "业务 A"
  interface-config.sh vlan del test 100
  interface-config.sh access set test 2 100
  interface-config.sh trunk allow test 3 100,200,300

设备标识: 设备名 / IP / 别名（test=192.168.100.177 默认测试设备）
EOF
    _print_doc_links "interface-config"
    exit 0
}

# ============================================================
# 工具函数
# ============================================================

# _resolve_device_id <device_name_or_ip>
# 调 backend API 把设备名 → device_id（IP 模式：直接用 _resolve_alias）
# 输出: device_id（数字）到 stdout，失败退出
_resolve_device_id() {
    local input="$1"
    local resolved
    resolved=$(_resolve_alias "$input")

    # IP 模式：调 backend 查设备列表匹配 host
    if [[ "$resolved" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        local ip="$resolved"
        local resp
        resp=$(curl -sf "${API_BASE}/devices" 2>/dev/null \
            || curl -sf "${API_BASE_FALLBACK}/devices" 2>/dev/null) || {
            _die "无法访问 backend API: ${API_BASE}/devices（确认 config/backend 容器在运行）"
        }
        # 用 python 解析（容器内无 jq）
        local device_id
        device_id=$(echo "$resp" | BACKEND_URL="$API_BASE" python3 -c '
import sys, os, json
try:
    data = json.load(sys.stdin)
    items = data.get("data", data) if isinstance(data, dict) else data
    target_ip = os.environ.get("BACKEND_IP", "")
    for d in items:
        if d.get("host") == target_ip or d.get("ip_address") == target_ip:
            print(d["id"])
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
' BACKEND_URL="$API_BASE" BACKEND_IP="$ip" 2>/dev/null) || {
            _die "未找到 IP=${ip} 对应的设备（backend 设备列表里没有）"
        }
        echo "$device_id"
    else
        # 设备名模式：直接查
        local resp
        resp=$(curl -sf "${API_BASE}/devices?name=${input}" 2>/dev/null \
            || curl -sf "${API_BASE_FALLBACK}/devices?name=${input}" 2>/dev/null) || {
            _die "无法访问 backend API 查设备名 '${input}'"
        }
        local device_id
        device_id=$(echo "$resp" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, list) and len(items) > 0:
        print(items[0]["id"])
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
' 2>/dev/null) || _die "未找到设备 '${input}'"
        echo "$device_id"
    fi
}

# _api_call <method> <path> [json_body]
# 调 backend API，输出返回 JSON 到 stdout
# 失败：stderr 输出错误并 exit 1
_api_call() {
    local method="$1"
    local path="$2"
    local body="${3:-}"

    local url="${API_BASE}${path}"
    local resp http_code

    if [[ -n "$body" ]]; then
        resp=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$body" "$url" 2>/dev/null) || {
            # fallback 到 backend 容器
            url="${API_BASE_FALLBACK}${path}"
            resp=$(curl -s -w "\n%{http_code}" -X "$method" \
                -H "Content-Type: application/json" \
                -d "$body" "$url" 2>/dev/null) || {
                _die "API 调用失败: $method $path（config 和 backend 容器都不可达）"
            }
        }
    else
        resp=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            "$url" 2>/dev/null) || {
            url="${API_BASE_FALLBACK}${path}"
            resp=$(curl -s -w "\n%{http_code}" -X "$method" \
                -H "Content-Type: application/json" \
                "$url" 2>/dev/null) || {
                _die "API 调用失败: $method $path（config 和 backend 容器都不可达）"
            }
        }
    fi

    http_code=$(echo "$resp" | tail -n 1)
    local json_body
    json_body=$(echo "$resp" | sed '$d')

    if [[ "$http_code" -ge 400 ]]; then
        local err
        err=$(echo "$json_body" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("error", d.get("detail", "HTTP 错误")))
except Exception:
    print("响应解析失败")
' 2>/dev/null)
        _die "API 返回 $http_code: $err"
    fi

    echo "$json_body"
}

# _print_result <success> <data_json>
# 把 backend 响应格式化输出（绿勾 / 红叉）
_print_result() {
    local success="$1"
    local data="$2"
    if [[ "$success" == "true" ]]; then
        local detail
        detail=$(echo "$data" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("message", d.get("vlan_id", d.get("name", "完成"))))
except Exception:
    print("完成")
' 2>/dev/null)
        echo "✅ 成功: ${detail}"
    else
        local err
        err=$(echo "$data" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("error", "未知错误"))
except Exception:
    print("响应解析失败")
' 2>/dev/null)
        echo "❌ 失败: ${err}"
        exit 1
    fi
}

# ============================================================
# 子命令实现
# ============================================================

cmd_vlan_add() {
    local device="$1"
    local vlan_id="$2"
    local name="$3"

    if [[ -z "$device" || -z "$vlan_id" || -z "$name" ]]; then
        _die "用法: interface-config.sh vlan add <device> <vlan_id> <name>"
    fi
    if ! [[ "$vlan_id" =~ ^[0-9]+$ ]] || [[ "$vlan_id" -lt 1 ]] || [[ "$vlan_id" -gt 4094 ]]; then
        _die "VLAN ID 必须在 1-4094 范围（实际: $vlan_id）"
    fi

    _print_device_banner "$device"
    local device_id
    device_id=$(_resolve_device_id "$device")

    echo "=== 创建 VLAN ${vlan_id}（${name}）on 设备 ${device}（id=${device_id}）==="

    local body
    body=$(python3 -c "import json; print(json.dumps({'vlan_id': $vlan_id, 'name': '$name'}))")
    local resp
    resp=$(_api_call POST "/devices/${device_id}/vlans" "$body")

    local success
    success=$(echo "$resp" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("success",False)).lower())' 2>/dev/null)
    _print_result "$success" "$resp"
}

cmd_vlan_del() {
    local device="$1"
    local vlan_id="$2"

    if [[ -z "$device" || -z "$vlan_id" ]]; then
        _die "用法: interface-config.sh vlan del <device> <vlan_id>"
    fi
    if ! [[ "$vlan_id" =~ ^[0-9]+$ ]] || [[ "$vlan_id" -lt 1 ]] || [[ "$vlan_id" -gt 4094 ]]; then
        _die "VLAN ID 必须在 1-4094 范围（实际: $vlan_id）"
    fi

    _print_device_banner "$device"
    local device_id
    device_id=$(_resolve_device_id "$device")

    echo "=== 删除 VLAN ${vlan_id} on 设备 ${device}（id=${device_id}）==="

    local resp
    resp=$(_api_call DELETE "/devices/${device_id}/vlans/${vlan_id}")

    local success
    success=$(echo "$resp" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("success",False)).lower())' 2>/dev/null)
    _print_result "$success" "$resp"
}

cmd_access_set() {
    local device="$1"
    local if_index="$2"
    local vlan="$3"

    if [[ -z "$device" || -z "$if_index" || -z "$vlan" ]]; then
        _die "用法: interface-config.sh access set <device> <if_index> <vlan>"
    fi
    if ! [[ "$if_index" =~ ^[0-9]+$ ]]; then
        _die "if_index 必须是数字（实际: $if_index）"
    fi
    if ! [[ "$vlan" =~ ^[0-9]+$ ]] || [[ "$vlan" -lt 1 ]] || [[ "$vlan" -gt 4094 ]]; then
        _die "VLAN ID 必须在 1-4094 范围（实际: $vlan）"
    fi

    _print_device_banner "$device"
    local device_id
    device_id=$(_resolve_device_id "$device")

    echo "=== 设置 access vlan ${vlan} on ${device}（id=${device_id}）IfIndex=${if_index} ==="

    local body
    body=$(python3 -c "import json; print(json.dumps({'if_index': $if_index, 'mode': 'access', 'access_vlan': $vlan, 'force': False}))")
    local resp
    resp=$(_api_call POST "/devices/${device_id}/interfaces/config" "$body")

    local success
    success=$(echo "$resp" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("success",False)).lower())' 2>/dev/null)
    _print_result "$success" "$resp"
}

cmd_trunk_allow() {
    local device="$1"
    local if_index="$2"
    local vlans="$3"

    if [[ -z "$device" || -z "$if_index" || -z "$vlans" ]]; then
        _die "用法: interface-config.sh trunk allow <device> <if_index> <vlans>"
    fi
    if ! [[ "$if_index" =~ ^[0-9]+$ ]]; then
        _die "if_index 必须是数字（实际: $if_index）"
    fi

    # 解析 vlan 列表为 JSON 数组
    local vlan_array_json
    vlan_array_json=$(python3 -c "
import json
vlans_str = '$vlans'
arr = [int(v.strip()) for v in vlans_str.split(',') if v.strip()]
for v in arr:
    if v < 1 or v > 4094:
        raise ValueError(f'VLAN ID {v} 越界')
print(json.dumps(arr))
" 2>/dev/null) || _die "VLAN 列表格式错误（应为逗号分隔的数字，实际: $vlans）"

    _print_device_banner "$device"
    local device_id
    device_id=$(_resolve_device_id "$device")

    echo "=== 设置 trunk 允许 vlan [${vlans}] on ${device}（id=${device_id}）IfIndex=${if_index} ==="

    local body
    body=$(python3 -c "
import json
print(json.dumps({
    'if_index': $if_index,
    'mode': 'trunk',
    'pvid': 1,
    'allowed_vlans': json.loads('$vlan_array_json'),
    'force': False
}))
")
    local resp
    resp=$(_api_call POST "/devices/${device_id}/interfaces/config" "$body")

    local success
    success=$(echo "$resp" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("success",False)).lower())' 2>/dev/null)
    _print_result "$success" "$resp"
}

# ============================================================
# 入口
# ============================================================
[[ $# -eq 0 ]] && usage

SUBCMD="$1"
shift

case "$SUBCMD" in
    --help|-h) usage ;;
    vlan)
        ACTION="${1:-}"
        shift || true
        case "$ACTION" in
            add) cmd_vlan_add "$@" ;;
            del) cmd_vlan_del "$@" ;;
            *) _die "未知 vlan 子命令: $ACTION（支持 add/del）" ;;
        esac
        ;;
    access)
        ACTION="${1:-}"
        shift || true
        case "$ACTION" in
            set) cmd_access_set "$@" ;;
            *) _die "未知 access 子命令: $ACTION（仅 set）" ;;
        esac
        ;;
    trunk)
        ACTION="${1:-}"
        shift || true
        case "$ACTION" in
            allow) cmd_trunk_allow "$@" ;;
            *) _die "未知 trunk 子命令: $ACTION（仅 allow）" ;;
        esac
        ;;
    *)
        _die "未知子命令: $SUBCMD（运行 --help 查看用法）"
        ;;
esac

_print_doc_links "interface-config"
