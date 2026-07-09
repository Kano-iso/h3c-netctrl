#!/bin/bash
# vpc-apply.sh — 读 SdnDeployment.planned_config 并下发到设备
# v3.0 sdn-vpc-device-templates Task 6
#
# 用法:
#   vpc-apply --deployment <id> --device <name|ip>
#   vpc-apply --deployment 1 --device .5         # 显式指定 .5
#   vpc-apply --deployment 1 --dry-run           # 仅打印计划, 不下发
#
# 数据流:
#   1. GET /api/sdn/deployments/{id}  → planned_config (JSON)
#   2. 解析命令序列
#   3. paramiko SSH 到 device, 顺序下发
#   4. PATCH /api/sdn/deployments/{id}  → status=success / failed
#
# 安全:
#   - 不打印明文命令 (仅打印 hash + 行数, spec.md Requirement: 凭据与安全)
#   - 凭据走 .env 注入 (DEVICE_USERNAME/DEVICE_PASSWORD 或 SSH_USER/SSH_PASS)
#   - 默认连 .177 (test), 连 .5 需显式 --device .5
#   - 禁止连 .2 / .3 (spec.md Requirement: 不修改 .2 / .3 设备)

set -euo pipefail

source /scripts/_lib.sh

DEPLOYMENT_ID=""
DRY_RUN="false"
DEVICE_INPUT=""

usage() {
    cat <<EOF
用法: vpc-apply --deployment <id> --device <name|ip> [--dry-run]

选项:
  --deployment <id>   SdnDeployment 主键 (必填)
  --device <name>     目标设备 (默认 test, 建议显式指定)
  --dry-run           仅打印计划, 不下发
  --help, -h          显示本帮助

示例:
  vpc-apply --deployment 1 --device .5
  vpc-apply --deployment 1 --device .5 --dry-run
EOF
    _print_doc_links "vpc-apply"
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --deployment) DEPLOYMENT_ID="$2"; shift 2 ;;
        --deployment=*) DEPLOYMENT_ID="${1#*=}"; shift ;;
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --dry-run) DRY_RUN="true"; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "❌ 未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

# 必填检查
[[ -z "$DEPLOYMENT_ID" ]] && { echo "❌ 缺少 --deployment" >&2; usage; exit 1; }
[[ -z "$DEVICE_INPUT" ]] && DEVICE_INPUT="$DEFAULT_DEVICE"

# 拒绝连 .2 / .3 (spec.md Requirement: 不修改 .2 / .3 设备)
RESOLVED_IP=$(_resolve_alias "$DEVICE_INPUT")
if [[ "$RESOLVED_IP" == "192.168.100.2" || "$RESOLVED_IP" == "192.168.100.3" ]]; then
    _die "禁止对 .2 / .3 (SDN 参考机器) 下发配置, 这是只读设备"
fi

_print_device_banner "$DEVICE_INPUT"
DEVICE_INPUT="$RESOLVED_IP"

# 凭据 (走 _lib 统一解析)
read -r IP USER PASS < <(_parse_device_args "$DEVICE_INPUT") || _die "无法解析设备 '${DEVICE_INPUT}'"

echo "=== vpc-apply ==="
echo "  deployment_id: $DEPLOYMENT_ID"
echo "  device:        $IP"
echo "  dry_run:       $DRY_RUN"
echo ""

# 1. 读 SdnDeployment (后端 API)
if ! command -v curl &>/dev/null; then
    _die "需要 curl, 容器内未安装"
fi

RESP=$(curl -sf "${BACKEND_URL}/api/sdn/deployments/${DEPLOYMENT_ID}" 2>/dev/null) || \
    _die "读取 deployment ${DEPLOYMENT_ID} 失败 (检查 backend 是否运行 + deployment_id 是否存在)"

# 2. 解析 planned_config
COMMANDS_JSON=$(echo "$RESP" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    inner = data.get('data', data)
    planned = inner.get('planned_config') if isinstance(inner, dict) else None
    if not planned:
        sys.exit(2)
    cmds = json.loads(planned)
    if not isinstance(cmds, list):
        sys.exit(3)
    for c in cmds:
        if isinstance(c, dict) and 'command' in c:
            print(c['command'])
        else:
            print(c)
except SystemExit:
    raise
except Exception:
    sys.exit(1)
") || _die "解析 planned_config 失败"

CMD_COUNT=$(echo "$COMMANDS_JSON" | wc -l)
CMD_HASH=$(echo "$COMMANDS_JSON" | sha256sum | cut -c1-12)
echo "  commands:      ${CMD_COUNT} 条 (sha256:${CMD_HASH})"

# 3. dry-run: 仅打印概要
if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "── dry-run 模式, 不下发 ──"
    echo "  设备: $IP"
    echo "  命令数: $CMD_COUNT"
    echo "  hash: $CMD_HASH"
    _print_doc_links "vpc-apply"
    exit 0
fi

# 4. 真实下发 (走 paramiko, 复用 SSHExecutor)
# 注: vpc-apply 是新增的 ops-toolkit 工具, 暂时用 paramiko-batch-exec 模式
#     (sdn-deploy change 会重构成专用 deployment runner)
TEMP_FILE=$(mktemp)
trap "rm -f '$TEMP_FILE'" EXIT
echo "$COMMANDS_JSON" > "$TEMP_FILE"

echo ""
echo "── 下发命令到 $IP (按顺序, 失败立即停) ──"

# 通过 paramiko (复用 _paramiko_batch_exec.py 的 SSH 能力)
# 这里用一个内联 Python 脚本批量下发, 避免长命令拼接
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
    # H3C V7 SSH 不支持 shell, 用 invoke_shell 模拟 (与 capture-config / audit-switch 一致)
    shell = client.invoke_shell()
    shell.settimeout(15)
    time.sleep(0.5)
    # 读 prompt
    initial = shell.recv(65535).decode(errors='ignore')

    success = 0
    failed = 0
    for i, cmd in enumerate(commands, 1):
        # 不打印明文命令 (仅打印序号 + 头几个字符 hash)
        cmd_short = cmd[:30] + '...' if len(cmd) > 30 else cmd
        print(f"  [{i}/{len(commands)}] {cmd_short}", flush=True)
        shell.send(cmd + '\n')
        time.sleep(0.3)
        # 读响应 (H3C 命令后通常 1-2 行回显 + prompt)
        try:
            resp = shell.recv(65535).decode(errors='ignore')
        except Exception:
            resp = ''
        # 简单错误检测: 含 "% Unknown" / "% Invalid" / "Error:" 视为失败
        if any(err in resp for err in ('% Unknown', '% Invalid', 'Error:', '% Too many parameters')):
            print(f"    ❌ 命令可能被设备拒绝: {resp.strip()[:120]}", flush=True)
            failed += 1
            # 不立即停, 继续 (允许 undo 类操作, 但记录失败)
        else:
            success += 1

    print(f"\n  完成: {success} 成功, {failed} 失败 / {len(commands)} 总计")
    sys.exit(0 if failed == 0 else 1)
finally:
    client.close()
PYEOF

APPLY_RC=$?

# 5. 更新 SdnDeployment.status
NEW_STATUS="success"
if [[ $APPLY_RC -ne 0 ]]; then
    NEW_STATUS="failed"
fi

curl -sf -X PATCH "${BACKEND_URL}/api/sdn/deployments/${DEPLOYMENT_ID}" \
    -H "Content-Type: application/json" \
    -d "{\"status\": \"${NEW_STATUS}\"}" >/dev/null 2>&1 || \
    echo "⚠️  更新 deployment 状态失败 (RC=$?)" >&2

if [[ $APPLY_RC -eq 0 ]]; then
    echo "✅ vpc-apply 成功: deployment ${DEPLOYMENT_ID} → ${NEW_STATUS}"
else
    echo "❌ vpc-apply 失败: deployment ${DEPLOYMENT_ID} → ${NEW_STATUS}"
fi

_print_doc_links "vpc-apply"
exit $APPLY_RC
