#!/bin/bash
# vpc-show.sh — 设备侧 VPC 状态只读查看
# v3.0 SDN 排错工具（仅读，不下发配置、不写 DB）
#
# 用法:
#   vpc-show --vpc <id> --device <name>
#   vpc-show --vpc 1 --device .5
#
# 行为:
#   - 调 3 条 display 命令 (read-only):
#     1. display l2vpn vsi verbose (VPC 状态)
#     2. display vxlan tunnel (VXLAN 隧道)
#     3. display bgp peer l2vpn evpn (BGP EVPN 邻居)
#   - 不下发任何配置命令
#   - 不写 SdnDeployment / SdnVpc
#   - 允许连 .2 / .3 (只读 OK, 与 paramiko-batch-exec 一致)
#
# 注意:
#   - 业务配置下发走 backend POST /api/sdn/deployments/{id}/apply 端点
#   - 本脚本仅供排错使用，不要用于业务配置下发

set -euo pipefail

source /scripts/_lib.sh

VPC_ID=""
DEVICE_INPUT=""
DRY_RUN="false"

usage() {
    cat <<EOF
用法: vpc-show --vpc <id> --device <name|ip>

选项:
  --vpc <id>         SdnVpc 主键 (用于显示/过滤, 可选)
  --device <name>    目标设备 (建议显式指定)
  --help, -h         显示本帮助

只读工具, 不下发任何配置, 不写 DB。
EOF
    _print_doc_links "vpc-show"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vpc) VPC_ID="$2"; shift 2 ;;
        --vpc=*) VPC_ID="${1#*=}"; shift ;;
        --device) DEVICE_INPUT="$2"; shift 2 ;;
        --device=*) DEVICE_INPUT="${1#*=}"; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "❌ 未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

[[ -z "$DEVICE_INPUT" ]] && DEVICE_INPUT="$DEFAULT_DEVICE"

RESOLVED_IP=$(_resolve_alias "$DEVICE_INPUT")
_print_device_banner "$DEVICE_INPUT"
DEVICE_INPUT="$RESOLVED_IP"

read -r IP USER PASS < <(_parse_device_args "$DEVICE_INPUT") || _die "无法解析设备 '${DEVICE_INPUT}'"

echo "=== vpc-show ==="
echo "  vpc_id: $VPC_ID"
echo "  device: $IP"
echo ""

# 3 条 display 命令 (只读)
DISPLAY_CMDS=(
    "display l2vpn vsi verbose"
    "display vxlan tunnel"
    "display bgp peer l2vpn evpn"
)

# 通过 paramiko 顺序执行, 仅读输出
SSH_USER="$USER" SSH_PASS="$PASS" python3 - "$IP" "${DISPLAY_CMDS[@]}" <<'PYEOF'
import os, sys, time
import paramiko

ip = sys.argv[1]
commands = sys.argv[2:]
user = os.environ['SSH_USER']
passwd = os.environ['SSH_PASS']

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(ip, username=user, password=passwd, timeout=10, look_for_keys=False, allow_agent=False)

try:
    shell = client.invoke_shell()
    shell.settimeout(15)
    time.sleep(0.5)
    # 清掉初始 prompt
    initial = shell.recv(65535).decode(errors='ignore')

    for i, cmd in enumerate(commands, 1):
        print(f"\n── [{i}/{len(commands)}] {cmd} ──", flush=True)
        shell.send(cmd + '\n')
        time.sleep(1.0)  # display 命令通常 0.5-2s
        try:
            resp = shell.recv(65535).decode(errors='ignore')
            # 过滤 ANSI 控制字符 (terminal escape)
            import re
            resp = re.sub(r'\x1b\[[0-9;]*[mGKH]', '', resp)
            # 去掉命令回显 (第一行)
            lines = resp.splitlines()
            # 找到真正的输出 (跳过 cmd echo + 末尾 prompt)
            output_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped == cmd:
                    continue
                if stripped.endswith(']') or stripped.endswith('>'):
                    continue
                output_lines.append(line)
            print('\n'.join(output_lines).strip())
        except Exception as e:
            print(f"  ⚠️  读取响应失败: {e}")
finally:
    client.close()
PYEOF

echo ""
_print_doc_links "vpc-show"
