# add-ops-toolkit

## Why

v2.3 用户反馈：每次排查问题都临时敲命令（ping / nc / ssh），且不同环境下命令路径/版本差异大。
需要一个"统一检查"工具容器：预装 ping / nc / SSH client / ncclient，附带预制脚本。

## What Changes

新增 docker-compose service `ops-toolkit`（profile: ops）：

### 1. 预装工具
- `iputils-ping` (ping)
- `netcat-openbsd` (nc)
- `openssh-client` (ssh / scp)
- `python3` + `ncclient` (NETCONF client)
- `python3` + `paramiko` (SSH client lib)
- `curl` + `jq`

### 2. 预制脚本（挂载进 /usr/local/bin/）
- `check-host.sh <ip>`：ICMP ping + TCP 22 + TCP 830
- `check-netconf.sh <ip>`：ncclient 连 + schema-capabilities
- `ssh-test.sh <ip>`：paramiko SSH + show version
- `check-config-diff.sh <ip>`：拉 startup vs running-config，对比 diff
- `interface-info.sh <ip>`：NETCONF 拉接口列表

### 3. 复用方式
```bash
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit check-host.sh 192.168.100.4
```

## 约束
- 后端无侵入（独立容器，不进 docker-compose 默认启动）
- 只用 profile: ops 显式启动
- 不装业务依赖（与 dev/prod 容器解耦）

## Verification
- `docker compose --profile ops run --rm ops-toolkit check-host.sh 192.168.100.4`
- 期望输出：ping OK + ssh 22 OK + netconf 830 OK

## Files Changed
- `docker/ops-toolkit/Dockerfile`（新增）
- `docker/ops-toolkit/scripts/*.sh`（5 个脚本）
- `docker-compose.dev.yml`（新增 ops-toolkit service + profile）
