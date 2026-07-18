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
ZTP_ADMIN_PASS="${ZTP_ADMIN_PASS:-Admin123!@#}"

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

ZTP_DATE=$(date +%Y-%m-%d)
HCL_FLAG="False"
if [ "$ZTP_HCL_T7064P15" = "true" ]; then
    HCL_FLAG="True"
fi

python3 -c "
import os
from jinja2 import Template

with open('${AUTOCFG_J2}') as f:
    tmpl = Template(f.read())

print(tmpl.render(
    platform='${ZTP_PLATFORM}',
    platform_long='${ZTP_PLATFORM_LONG}',
    mgmt_ip='${ZTP_MGMT_IP}',
    sysname='${ZTP_SYSNAME}',
    admin_user='${ZTP_ADMIN_USER}',
    admin_pass='${ZTP_ADMIN_PASS}',
    hcl_t7064p15=${HCL_FLAG},
    ztp_date='${ZTP_DATE}',
))
" > "$AUTOCFG_OUT"
chmod 644 "$AUTOCFG_OUT"

# === 3. 启动日志 ===
echo "=== dnsmasq 启动 ==="
echo "  Platform:    ${ZTP_PLATFORM} (${ZTP_PLATFORM_LONG})"
echo "  HCL T7064P15: ${ZTP_HCL_T7064P15}"
echo "  DHCP range:  ${ZTP_DHCP_RANGE_START} - ${ZTP_DHCP_RANGE_END}"
echo "  TFTP server: ${ZTP_HOST_IP}"
echo "  TFTP root:   ${TFTP_DIR}"
echo "  autocfg.cfg sysname:  ${ZTP_SYSNAME}"
echo "  autocfg.cfg mgmt IP:  ${ZTP_MGMT_IP}"
echo "  autocfg.cfg 平台分支: 物理 OOB 口 + 凭据（python/Admin123!@#）"
echo ""
echo "=== autocfg.cfg 渲染前 10 行 ==="
head -10 "$AUTOCFG_OUT"
echo "..."

# === 4. exec dnsmasq (前台运行, -d 保留 log 到 stderr) ===
exec dnsmasq -k -C "$DNSMASQ_CONF" -d
