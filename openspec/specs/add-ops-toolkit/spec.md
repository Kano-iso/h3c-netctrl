# spec: add-ops-toolkit

## 能力

容器化运维工具包（profile: ops），预装 ping/nc/SSH/ncclient + 5 预制脚本。

## 范围

### 预装工具
- `iputils-ping` (ping)
- `netcat-openbsd` (nc)
- `openssh-client` (ssh / scp)
- `python3` + `ncclient` / `netmiko` / `paramiko`
- `sshpass`

### 预制脚本
- `check-host.sh <ip>` — ICMP + TCP 22 + TCP 830
- `check-netconf.sh <ip>` — ncclient + schema-capabilities
- `reboot-wait.sh <ip>` — reboot 等待（90s retry）
- `capture-config.sh <ip>` — 拉 startup + running-config

## 设计决策

- **profile: ops**：不默认启动，避免污染 dev/prod
- **PATH 注入**：脚本 cp 到 /usr/local/bin
- **后端无侵入**：独立容器，不影响 FastAPI

## 验收标准

- [x] `docker compose --profile ops run --rm ops-toolkit check-host.sh <ip>` 工作
- [x] 脚本在 PATH 中
- [x] 真机 192.168.100.4 check-host 三个端口全 OK

## 关联 change
- `openspec/changes/archive/2026-06-29-add-ops-toolkit/`
- `ops-toolkit/Dockerfile`
- `ops-toolkit/scripts/*.sh`
