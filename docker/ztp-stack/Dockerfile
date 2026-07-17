# ztp-stack 容器镜像（v3.1 ZTP 调研 T3 基建）
#
# 基础: Alpine 3.20 (轻量, ~7MB)
# 组件: dnsmasq (DHCP + TFTP 二合一)
# 网络: host (共享宿主机网络栈，接收 H3C V7 物理设备 L2 广播)
# 凭据: 通过 docker-compose environment 注入（.env）
#
# 构建: docker compose -f docker-compose.dev.yml --profile ops build ztp-server
# 启动: docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server
# 验证: docker compose -f docker-compose.dev.yml --profile ops run --rm ztp-server dnsmasq --test -C /etc/dnsmasq.conf

FROM alpine:3.20

# 安装 dnsmasq（DHCP + TFTP 二合一）
# tftp-hpa 是 TFTP 客户端（dnsmasq 自带 TFTP server，客户端用于本地验证）
RUN apk add --no-cache \
        dnsmasq \
        bash \
    && mkdir -p /var/tftp /var/log

# 复制模板文件 + entrypoint
# build context 是项目根目录, COPY 路径要加 docker/ztp-stack/ 前缀
COPY docker/ztp-stack/dnsmasq.conf.template /dnsmasq.conf.template
COPY docker/ztp-stack/tftp/autocfg.cfg.template /var/tftp/autocfg.cfg.template
COPY docker/ztp-stack/entrypoint.sh /entrypoint.sh

# entrypoint.sh 会渲染模板到 /etc/dnsmasq.conf + /var/tftp/autocfg.cfg，然后 exec dnsmasq
RUN chmod +x /entrypoint.sh

# 暴露 DHCP 67/UDP + TFTP 69/UDP（host network 模式下端口直接暴露在宿主机）
EXPOSE 67/udp 69/udp

ENTRYPOINT ["/entrypoint.sh"]
