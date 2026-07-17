#!/bin/sh
# entrypoint.sh — ztp-server 容器启动脚本
#
# 流程:
# 1. 从 env vars 渲染 dnsmasq.conf.template → /etc/dnsmasq.conf
# 2. 从 env vars 渲染 autocfg.cfg.template → /var/tftp/autocfg.cfg
# 3. exec dnsmasq (DHCP 67/UDP + TFTP 69/UDP)

set -eu

TFTP_DIR="/var/tftp"
DNSMASQ_CONF="/etc/dnsmasq.conf"

# 默认值（可被 env vars 覆盖）
ZTP_SYSNAME="${ZTP_SYSNAME:-ztp-device}"
ZTP_MGMT_IP="${ZTP_MGMT_IP:-192.168.100.10}"
ZTP_MGMT_MASK="${ZTP_MGMT_MASK:-255.255.255.0}"
ZTP_MGMT_GATEWAY="${ZTP_MGMT_GATEWAY:-192.168.100.1}"
ZTP_ADMIN_USER="${ZTP_ADMIN_USER:-admin}"
ZTP_ADMIN_PASS="${ZTP_ADMIN_PASS:-admin}"
ZTP_HOST_IP="${ZTP_HOST_IP:-127.0.0.1}"
ZTP_DHCP_RANGE_START="${ZTP_DHCP_RANGE_START:-192.168.100.200}"
ZTP_DHCP_RANGE_END="${ZTP_DHCP_RANGE_END:-192.168.100.250}"
ZTP_DHCP_LEASE="${ZTP_DHCP_LEASE:-12h}"

mkdir -p "$TFTP_DIR"

echo "=== 渲染 dnsmasq.conf ==="
sed \
    -e "s|\${ZTP_HOST_IP}|${ZTP_HOST_IP}|g" \
    -e "s|\${ZTP_DHCP_RANGE_START}|${ZTP_DHCP_RANGE_START}|g" \
    -e "s|\${ZTP_DHCP_RANGE_END}|${ZTP_DHCP_RANGE_END}|g" \
    -e "s|\${ZTP_DHCP_LEASE}|${ZTP_DHCP_LEASE}|g" \
    /dnsmasq.conf.template > "$DNSMASQ_CONF"

echo "=== 渲染 autocfg.cfg ==="
sed \
    -e "s|\${ZTP_SYSNAME}|${ZTP_SYSNAME}|g" \
    -e "s|\${ZTP_MGMT_IP}|${ZTP_MGMT_IP}|g" \
    -e "s|\${ZTP_MGMT_MASK}|${ZTP_MGMT_MASK}|g" \
    -e "s|\${ZTP_MGMT_GATEWAY}|${ZTP_MGMT_GATEWAY}|g" \
    -e "s|\${ZTP_ADMIN_USER}|${ZTP_ADMIN_USER}|g" \
    -e "s|\${ZTP_ADMIN_PASS}|${ZTP_ADMIN_PASS}|g" \
    /var/tftp/autocfg.cfg.template > "$TFTP_DIR/autocfg.cfg"
chmod 644 "$TFTP_DIR/autocfg.cfg"

echo "=== dnsmasq 启动 ==="
echo "  DHCP range: ${ZTP_DHCP_RANGE_START} - ${ZTP_DHCP_RANGE_END}"
echo "  TFTP server: ${ZTP_HOST_IP}"
echo "  TFTP root: ${TFTP_DIR}"
echo "  autocfg.cfg sysname: ${ZTP_SYSNAME}"
echo ""

# exec dnsmasq (前台运行, -d 保留 log 到 stderr)
exec dnsmasq -k -C "$DNSMASQ_CONF" -d
