#!/bin/bash
# vpc-reset.sh — 清理 VPC 全部配置 (保留 l3vpn)
# v3.0 sdn-vpc-device-templates Task 6
#
# 用法:
#   vpc-reset --vpc <id> --device <name> --force
#
# 警告: --force 必填 (不可逆操作, 设备上 VSI / Vsi-interface 直接删)
# 保留: l3vpn vpn-instance / vxlan tunnel mac-learning disable (设备级, 共享)
#
# 数据流:
#   1. 读 SdnVpc (vsi_name, vsi_interface) - 通过后端 API
#   2. 拼反向删除命令 (2 条: undo vsi + undo interface)
#   3. paramiko 下发
#   4. PATCH /api/sdn/vpcs/{id} status=deleted
#
# 安全:
#   - 必须 --force 才执行
#   - 禁止连 .2 / .3 (spec.md Requirement)

set -euo pipefail

source /scripts/_lib.sh

VPC_ID=""
DEVICE_INPUT=""
FORCE="false"
DRY_RUN="false"

usage() {
    cat <<EOF
用法: vpc-reset --vpc <id> --device <name|ip> --force [--dry-run]

选项:
  --vpc <id>         SdnVpc 主键 (必填)
  --device <name>    目标设备 (建议显式指定)
  --force            强制执行 (不可逆, 必填)
  --dry-run          仅打印计划, 不下发
  --help, -h         显示本帮助

警告: 此操作会删除设备上的 VSI / Vsi-interface, 不可撤销!
      l3vpn / vxlan tunnel mac-learning disable 保留 (设备级共享)
EOF
    _print_doc_links "vpc-reset"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vpc) VPC_ID="$2"; shift 2 ;;
        --vpc=*) VPC_ID="${1#*=}"; shift ;;
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --force) FORCE="true"; shift ;;
        --dry-run) DRY_RUN="true"; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "❌ 未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

# 必填检查
[[ -z "$VPC_ID" ]] && { echo "❌ 缺少 --vpc" >&2; usage; exit 1; }
[[ -z "$DEVICE_INPUT" ]] && DEVICE_INPUT="$DEFAULT_DEVICE"
[[ "$FORCE" != "true" && "$DRY_RUN" != "true" ]] && _die "缺少 --force (不可逆操作)"

# 拒绝连 .2 / .3
RESOLVED_IP=$(_resolve_alias "$DEVICE_INPUT")
if [[ "$RESOLVED_IP" == "192.168.100.2" || "$RESOLVED_IP" == "192.168.100.3" ]]; then
    _die "禁止对 .2 / .3 (SDN 参考机器) 下发配置"
fi

_print_device_banner "$DEVICE_INPUT"
DEVICE_INPUT="$RESOLVED_IP"

read -r IP USER PASS < <(_parse_device_args "$DEVICE_INPUT") || _die "无法解析设备 '${DEVICE_INPUT}'"

echo "=== vpc-reset ==="
echo "  vpc_id:    $VPC_ID"
echo "  device:    $IP"
echo "  force:     $FORCE"
echo "  dry_run:   $DRY_RUN"
echo ""

# 1. 读 SdnVpc
if ! command -v curl &>/dev/null; then
    _die "需要 curl, 容器内未安装"
fi

RESP=$(curl -sf "${BACKEND_URL}/api/sdn/vpcs/${VPC_ID}" 2>/dev/null) || \
    _die "读取 vpc ${VPC_ID} 失败"

# 2. 解析 vpc 字段 (vsi_interface + vni 推 vsi_name)
read VSI_INTERFACE VNI < <(echo "$RESP" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    inner = data.get('data', data)
    if not isinstance(inner, dict):
        sys.exit(1)
    vsi_interface = inner.get('vsi_interface')
    vni = inner.get('vni')
    if vsi_interface is None or vni is None:
        sys.exit(2)
    print(int(vsi_interface), int(vni))
except SystemExit:
    raise
except Exception:
    sys.exit(1)
") || _die "解析 vpc 字段失败"

# vsi_name = vpc{vpc_id:04d} (ADR-103)
VSI_NAME=$(printf "vpc%04d" "$VPC_ID")

CMDS=$(cat <<EOF
undo vsi ${VSI_NAME}
undo interface Vsi-interface${VSI_INTERFACE}
EOF
)
CMD_COUNT=$(echo "$CMDS" | wc -l)
CMD_HASH=$(echo "$CMDS" | sha256sum | cut -c1-12)

echo "  vsi_name:      $VSI_NAME"
echo "  vsi_interface: $VSI_INTERFACE"
echo "  commands:      ${CMD_COUNT} 条 (sha256:${CMD_HASH})"
echo ""

# 3. dry-run
if [[ "$DRY_RUN" == "true" ]]; then
    echo "── dry-run 模式, 不下发 ──"
    echo "  设备: $IP"
    echo "  计划:"
    echo "$CMDS" | sed 's/^/    /'
    _print_doc_links "vpc-reset"
    exit 0
fi

# 4. 真实下发 (与 vpc-apply 一致的 paramiko 模式)
TEMP_FILE=$(mktemp)
trap "rm -f '$TEMP_FILE'" EXIT
echo "$CMDS" > "$TEMP_FILE"

echo "── 下发清理命令到 $IP ──"

SSH_USER="$USER" SSH_PASS="$PASS" python3 - "$IP" "$TEMP_FILE" <<'PYEOF'
import os, sys, time
import paramiko

ip = sys.argv[1]
cmd_file = sys.argv[2]
user = os.environ['SSH_USER']
passwd = os.environ['SSH_PASS']

with open(cmd_file) as f:
    commands = [line.rstrip() for line in f if line.strip()]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(ip, username=user, password=passwd, timeout=10, look_for_keys=False, allow_agent=False)

try:
    shell = client.invoke_shell()
    shell.settimeout(15)
    time.sleep(0.5)
    initial = shell.recv(65535).decode(errors='ignore')

    success = 0
    failed = 0
    for i, cmd in enumerate(commands, 1):
        cmd_short = cmd[:30] + '...' if len(cmd) > 30 else cmd
        print(f"  [{i}/{len(commands)}] {cmd_short}", flush=True)
        shell.send(cmd + '\n')
        time.sleep(0.3)
        try:
            resp = shell.recv(65535).decode(errors='ignore')
        except Exception:
            resp = ''
        if any(err in resp for err in ('% Unknown', '% Invalid', 'Error:')):
            print(f"    ❌ 命令可能被设备拒绝: {resp.strip()[:120]}", flush=True)
            failed += 1
        else:
            success += 1

    print(f"\n  完成: {success} 成功, {failed} 失败 / {len(commands)} 总计")
    sys.exit(0 if failed == 0 else 1)
finally:
    client.close()
PYEOF

RESET_RC=$?

# 5. 更新 SdnVpc.status
NEW_STATUS="deleted"
if [[ $RESET_RC -ne 0 ]]; then
    NEW_STATUS="reset_failed"
fi

curl -sf -X PATCH "${BACKEND_URL}/api/sdn/vpcs/${VPC_ID}" \
    -H "Content-Type: application/json" \
    -d "{\"status\": \"${NEW_STATUS}\"}" >/dev/null 2>&1 || \
    echo "⚠️  更新 vpc 状态失败" >&2

if [[ $RESET_RC -eq 0 ]]; then
    echo "✅ vpc-reset 成功: vpc ${VPC_ID} → ${NEW_STATUS}"
else
    echo "❌ vpc-reset 失败: vpc ${VPC_ID} → ${NEW_STATUS}"
fi

_print_doc_links "vpc-reset"
exit $RESET_RC
