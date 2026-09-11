#!/bin/sh
# entrypoint.sh — ztp-server 容器启动脚本
#
# 流程:
# 1. 从 env vars 渲染 dnsmasq.conf.template → /etc/dnsmasq.conf（sed 简单替换）
# 2. 从 env vars 渲染 autocfg.cfg.j2 → /var/tftp/autocfg.cfg（jinja2 条件分支渲染）
# 3. 校验 ZTP_PLATFORM 路由（不在 lstn/rstn 范围 → warning + fallback lstn）
# 4. exec dnsmasq (DHCP 67/UDP + TFTP 69/UDP)

set -eu

TFTP_DIR="/var/tftp"
DNSMASQ_CONF="/etc/dnsmasq.conf"
AUTOCFG_J2="${TFTP_DIR}/autocfg.cfg.j2"
AUTOCFG_OUT="${TFTP_DIR}/autocfg.cfg"

# === 默认值（可被 env vars 覆盖）===
# ZTP 平台路由（jinja2 autocfg.cfg.j2 条件分支路由）
ZTP_PLATFORM="${ZTP_PLATFORM:-lstn}"                        # lstn | rstn
ZTP_HCL_T7064P15="${ZTP_HCL_T7064P15:-false}"               # true | false（HCL 测试版独有 login-password-change disable）
ZTP_MGMT_IP="${ZTP_MGMT_IP:-192.168.100.101}"               # autocfg.cfg 推的 static IP（v3.1.1 硬编码 .101，v3.1.2 公式化）

# ZTP 通用变量
ZTP_MGMT_LAST_OCTET="${ZTP_MGMT_IP##*.}"
ZTP_SYSNAME="${ZTP_SYSNAME:-ztp-switch-${ZTP_MGMT_LAST_OCTET}}"
if [ "$ZTP_SYSNAME" = "ztp-device" ]; then
    ZTP_SYSNAME="ztp-switch-${ZTP_MGMT_LAST_OCTET}"
fi
ZTP_ADMIN_USER="${ZTP_ADMIN_USER:-python}"
ZTP_ADMIN_PASS="${ZTP_ADMIN_PASS:?ZTP_ADMIN_PASS 必须在环境中提供（拒绝代码内默认口令）}"
ZTP_STATE_DIR="${ZTP_STATE_DIR:-/ztp-state}"
export ZTP_PLATFORM ZTP_HCL_T7064P15 ZTP_MGMT_IP ZTP_SYSNAME ZTP_ADMIN_USER ZTP_ADMIN_PASS ZTP_STATE_DIR

# ZTP DHCP / TFTP 变量
ZTP_HOST_IP="${ZTP_HOST_IP:-127.0.0.1}"
ZTP_DHCP_RANGE_START="${ZTP_DHCP_RANGE_START:-192.168.100.151}"   # 跨池映射：DHCP .151-.190 ↔ static .101-.140
ZTP_DHCP_RANGE_END="${ZTP_DHCP_RANGE_END:-192.168.100.190}"
ZTP_DHCP_LEASE="${ZTP_DHCP_LEASE:-12h}"

mkdir -p "$TFTP_DIR"

# === 平台路由校验 ===
case "$ZTP_PLATFORM" in
    lstn|rstn) ;;
    *)
        echo "⚠️  ZTP_PLATFORM=$ZTP_PLATFORM not in [lstn, rstn], fallback to lstn"
        ZTP_PLATFORM="lstn"
        ;;
esac

# 平台全名（用于 autocfg.cfg 注释）
case "$ZTP_PLATFORM" in
    lstn)
        if [ "$ZTP_HCL_T7064P15" = "true" ]; then
            ZTP_PLATFORM_LONG="S6850 S6850/T7064P15-hcl（HCL 测试版）"
        else
            ZTP_PLATFORM_LONG="S6850 S6850/T7064P15-prod（商用版）"
        fi
        ;;
    rstn)
        ZTP_PLATFORM_LONG="V9850 V9850-256H/R7643P02"
        ;;
esac
export ZTP_PLATFORM_LONG   # 渲染变量经环境传递（Python 从 os.environ 读取）

# === 1. 渲染 dnsmasq.conf（sed 简单变量替换）===
echo "=== 渲染 dnsmasq.conf ==="
sed \
    -e "s|\${ZTP_HOST_IP}|${ZTP_HOST_IP}|g" \
    -e "s|\${ZTP_DHCP_RANGE_START}|${ZTP_DHCP_RANGE_START}|g" \
    -e "s|\${ZTP_DHCP_RANGE_END}|${ZTP_DHCP_RANGE_END}|g" \
    -e "s|\${ZTP_DHCP_LEASE}|${ZTP_DHCP_LEASE}|g" \
    /dnsmasq.conf.template > "$DNSMASQ_CONF"

# === 2. 渲染 autocfg.cfg（jinja2 条件分支）===
echo "=== 渲染 autocfg.cfg ==="
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 未安装（jinja2 渲染需要）"
    exit 1
fi
if ! python3 -c "import jinja2" 2>/dev/null; then
    echo "❌ jinja2 模块未安装（jinja2 渲染需要）"
    exit 1
fi

# CR43: 渲染变量只经环境传递——Python 一律从 os.environ 读取，
# 不把 ZTP_ADMIN_PASS 等秘密拼进源码/命令行（特殊字符不再语法失败/代码注入）。
export ZTP_AUTOCFG_TEMPLATE="$AUTOCFG_J2"
export ZTP_DATE="$(date +%Y-%m-%d)"

# CR43: 输出含明文密码——安全临时文件（mktemp 创建即 0600）+ 原子替换，
# 替换后显式 chmod 600；失败/中断经 trap 清理，不残留宽权限或含口令的中间文件。
AUTOCFG_TMP="$(mktemp "${TFTP_DIR}/autocfg.cfg.XXXXXX")"
trap 'rm -f "$AUTOCFG_TMP"' EXIT
python3 -c '
import os
from jinja2 import Template

with open(os.environ["ZTP_AUTOCFG_TEMPLATE"], encoding="utf-8") as f:
    tmpl = Template(f.read())

print(tmpl.render(
    platform=os.environ["ZTP_PLATFORM"],
    platform_long=os.environ["ZTP_PLATFORM_LONG"],
    mgmt_ip=os.environ["ZTP_MGMT_IP"],
    sysname=os.environ["ZTP_SYSNAME"],
    admin_user=os.environ["ZTP_ADMIN_USER"],
    admin_pass=os.environ["ZTP_ADMIN_PASS"],
    hcl_t7064p15=os.environ.get("ZTP_HCL_T7064P15", "false").lower() in {"1", "true", "yes", "on"},
    ztp_date=os.environ["ZTP_DATE"],
))
' > "$AUTOCFG_TMP"
chmod 600 "$AUTOCFG_TMP"
mv -f "$AUTOCFG_TMP" "$AUTOCFG_OUT"
trap - EXIT

# === 3. 启动日志 ===
echo "=== dnsmasq 启动 ==="
echo "  Platform:    ${ZTP_PLATFORM} (${ZTP_PLATFORM_LONG})"
echo "  HCL T7064P15: ${ZTP_HCL_T7064P15}"
echo "  DHCP range:  ${ZTP_DHCP_RANGE_START} - ${ZTP_DHCP_RANGE_END}"
echo "  TFTP server: ${ZTP_HOST_IP}"
echo "  TFTP root:   ${TFTP_DIR}"
echo "  autocfg.cfg sysname:  ${ZTP_SYSNAME}"
echo "  autocfg.cfg mgmt IP:  ${ZTP_MGMT_IP}"
echo "  autocfg.cfg 平台分支: 物理 OOB 口 + 凭据（ZTP_ADMIN_USER / ZTP_ADMIN_PASS 环境注入，无代码内口令）"
echo ""
echo "=== autocfg.cfg 渲染前 10 行 ==="
head -10 "$AUTOCFG_OUT"
echo "..."

# === 4. exec dnsmasq (前台运行, -d 保留 log 到 stderr) ===
echo "=== ZTP runtime renderer enabled ==="
echo "  State dir: ${ZTP_STATE_DIR}"
python3 /ztp_runtime_render.py &

if [ "${ZTP_ONBOARD_ENABLED:-false}" = "true" ]; then
    echo "=== ZTP onboard watcher enabled ==="
    echo "  API URL: ${ZTP_ONBOARD_API_URL:-http://127.0.0.1:8001/api/ztp/onboard}"
    python3 /ztp_onboard_callback.py &
else
    echo "=== ZTP onboard watcher disabled (ZTP_ONBOARD_ENABLED != true) ==="
fi

exec dnsmasq -k -C "$DNSMASQ_CONF" -d
