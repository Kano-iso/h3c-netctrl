# ztp-stack 容器 + H3C V7 ZTP 真机验证 SOP

> **变更**：v3.1 ZTP 调研 T3-T4 基建（[proposal](../../openspec/changes/v31-ztp-research/proposal.md)）
> **创建时间**：2026-07-17
> **目标**：在受控局域网内，对 H3C V7 设备做 Zero Touch Provisioning 验证

---

## 1. 容器职责

`ztp-server` 是 v3.1 ZTP 调研的**独立基建容器**，**不**影响 ops-toolkit 的开箱即用原则：

| 容器 | 职责 | 网络 | 凭据 | 启动方式 |
|---|---|---|---|---|
| **ops-toolkit** | 设备排错 / 探针 / 单功能验证 | docker bridge | .env 注入 | `docker compose ... --profile ops run --rm ops-toolkit` |
| **ztp-server**（新）| ZTP 服务的 DHCP + TFTP 二合一 | **host network**（共享宿主机网络栈）| .env 注入（ZTP_* 变量）| `docker compose ... --profile ops up -d ztp-server` |

---

## 2. 容器组件

**镜像**：`alpine:3.20`（轻量，约 7MB）+ `dnsmasq`（DHCP 67/UDP + TFTP 69/UDP 二合一）

**目录结构**：
```
docker/ztp-stack/
├── Dockerfile                        # alpine + dnsmasq
├── entrypoint.sh                     # 渲染 env vars 到 dnsmasq.conf + autocfg.cfg
├── dnsmasq.conf.template             # DHCP + TFTP 模板
└── tftp/
    └── autocfg.cfg.template          # H3C V7 启动配置模板
```

**渲染流程**（entrypoint.sh）：
1. `sed` 替换 `dnsmasq.conf.template` 中 `${ZTP_*}` 占位符 → `/etc/dnsmasq.conf`
2. `sed` 替换 `autocfg.cfg.template` 中 `${ZTP_*}` 占位符 → `/var/tftp/autocfg.cfg`
3. `exec dnsmasq -k -C /etc/dnsmasq.conf -d`（前台运行，日志到 stderr）

---

## 3. 关键设计

### 3.1 host network 模式

```yaml
ztp-server:
  network_mode: host  # 共享宿主机网络栈
```

**原因**：H3C V7 设备的 DHCP discover 是 **L2 广播**，不能跨网段。ops-toolkit 容器在 docker bridge network（172.x.x.x），不在 .177 物理网段（192.168.100.0/24），广播不通。`host network` 模式下，容器直接绑定宿主机网络接口，能接收物理网段的 L2 广播。

### 3.2 DHCP 范围设计

```conf
dhcp-range=192.168.100.200,192.168.100.250,12h
```

- 仅分配 `.200-.250`，**避开现有 `.1-.199`**（`.4` 宿主机 + `.5/.26/.177` 设备）
- 12h 租约（容器停止即清空，不污染网络）

### 3.3 autocfg.cfg 最小配置

按 user 2026-07-17 02:13 明确：
- ✅ 只做基础配置：SSH 22 + NETCONF 830 + 凭据 + 带外 IP
- ❌ 不做业务配置：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ 不做配置联动：ZTP 完成后由 controller 继续推业务配置

### 3.4 凭据走 env vars

`autocfg.cfg` 模板中所有占位符（`${ZTP_*}`）由 .env 注入：
- 避免硬编码密码（user memory 红线）
- 同一份模板可用于不同设备（仅 .env 变量不同）

---

## 4. 容器用法

### 4.1 配置 .env

在 `.env` 中加入（参考 `.env.example`）：
```bash
# ZTP 宿主机 IP（按实际修改）
ZTP_HOST_IP=192.168.100.4

# DHCP 范围（默认 .200-.250）
ZTP_DHCP_RANGE_START=192.168.100.200
ZTP_DHCP_RANGE_END=192.168.100.250
ZTP_DHCP_LEASE=12h

# 设备自动配置（autocfg.cfg 渲染变量）
ZTP_SYSNAME=ztp-177
ZTP_MGMT_IP=192.168.100.10
ZTP_MGMT_MASK=255.255.255.0
ZTP_MGMT_GATEWAY=192.168.100.1
ZTP_ADMIN_USER=admin
ZTP_ADMIN_PASS=admin
```

### 4.2 构建镜像

```bash
docker compose -f docker-compose.dev.yml --profile ops build ztp-server
```

### 4.3 配置语法检查

```bash
docker compose -f docker-compose.dev.yml --profile ops run --rm ztp-server dnsmasq --test -C /etc/dnsmasq.conf
```

### 4.4 启动容器

```bash
# 后台启动
docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server

# 前台启动（debug 模式）
docker compose -f docker-compose.dev.yml --profile ops up ztp-server
```

### 4.5 验证端口监听

```bash
# 宿主机检查
ss -uln | grep -E ':(67|69) '
# 预期: udp UNCONN 0 0 0.0.0.0:67   0.0.0.0:*
#        udp UNCONN 0 0 0.0.0.0:69   0.0.0.0:*

# 查看日志
docker logs -f h3c-netctrl-ztp-server
```

### 4.6 停止容器

```bash
docker compose -f docker-compose.dev.yml --profile ops down ztp-server
```

---

## 5. T4 真机验证 SOP

> **风险等级**：⚠️ **中高**（设备 reset + reboot）
> **前提**：.177 设备物理可达（console 线 + 串口）

### 5.1 准备阶段

#### 步骤 1：检查 .177 设备状态

```bash
# 走 ops-toolkit（不开新窗口）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-host.sh --device Test-Switch-177
```

确认：
- ✅ ping 通
- ✅ SSH 22 通
- ✅ NETCONF 830 通

#### 步骤 2：备份 .177 当前 startup.cfg

**不能**用 ops-toolkit 的 capture-config.sh（系统 scp 客户端不兼容 H3C V7 ssh-rsa host key）—— 用 paramiko 备份：

```bash
# 进 ops-toolkit 容器交互式 paramiko
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit python3 <<'EOF'
import paramiko
import os
from datetime import datetime

# 凭据从 .env 注入（DEVICE_USERNAME/DEVICE_PASSWORD）
user = os.environ['DEVICE_USERNAME']
passwd = os.environ['DEVICE_PASSWORD']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.100.177', port=22, username=user, password=passwd, timeout=10)

# 用 'more startup.cfg' 拉内容（与 backup 一致的实现）
stdin, stdout, stderr = ssh.exec_command('more startup.cfg')
content = stdout.read().decode('utf-8', errors='replace')

# 保存到 /captures 目录
ts = datetime.now().strftime('%Y%m%dT%H%M%S')
out = f'/captures/192.168.100.177_{ts}_startup.cfg.bak'
with open(out, 'w') as f:
    f.write(content)
print(f'✅ 备份到 {out}, 大小: {len(content)} bytes')
ssh.close()
EOF
```

#### 步骤 3：启动 ztp-server 容器

```bash
# 确保 .env 已配
docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server

# 验证端口监听
ss -uln | grep -E ':(67|69) '
# 预期: 0.0.0.0:67 + 0.0.0.0:69

# 实时看日志（保持打开）
docker logs -f h3c-netctrl-ztp-server
```

### 5.2 reset + reboot 阶段

#### 步骤 4：reset .177 saved-configuration

**必须**在 ztp-server 容器运行后执行，否则设备会失联。

```bash
# 进 ops-toolkit 交互式 paramiko
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit python3 <<'EOF'
import paramiko
import os

user = os.environ['DEVICE_USERNAME']
passwd = os.environ['DEVICE_PASSWORD']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.100.177', port=22, username=user, password=passwd, timeout=10)

# 清空 startup.cfg + reboot
commands = [
    'system-view',
    'reset saved-configuration',
    'reboot',
]
for cmd in commands:
    print(f'>>> {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd)
    print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
EOF
```

#### 步骤 5：观察 .177 启动行为

- 设备 DHCP discover → 收到 ztp-server 的 OFFER
- 设备 TFTP GET `autocfg.cfg` → 收到完整配置
- 设备应用配置 + reboot
- 设备启动到完整配置（SSH 22 + NETCONF 830 通）

**预期时间线**：
- 0-30s：设备 reboot + 启动到空配置
- 30-60s：DHCP discover + TFTP 拉取 + 应用
- 60-120s：设备 reboot + 启动到完整配置

#### 步骤 6：验证 SSH + NETCONF

```bash
# 60s 后检查
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-host.sh --device ztp-177
# 预期: SSH 22 + NETCONF 830 通

# 验证 autocfg.cfg 内容已应用
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit paramiko-batch-exec.sh --device ztp-177 --command "display current-configuration | include sysname"
# 预期: sysname ztp-177
```

### 5.3 兜底阶段（T4 失败时）

#### 步骤 7：失败恢复

如果 T4 失败（60s 内 SSH 22 没起），立即恢复 .177 备份：

```bash
# 1. 停止 ztp-server（避免重复干扰）
docker compose -f docker-compose.dev.yml --profile ops down ztp-server

# 2. 通过 console 线 + 串口登录 .177（需用户物理操作）
# 3. 手动粘贴备份内容到 .177
# 4. save force + reboot
```

### 5.4 收尾阶段

#### 步骤 8：T4 结果记录 + 决策

- **成功** → T5 决策 B（投入 ZTP，v3.1.1 实现）
- **失败** → T5 决策 C（不投入 ZTP，留作 v3.x 远期）

#### 步骤 9：环境清理

```bash
# 停止 ztp-server（避免 DHCP 持续分配）
docker compose -f docker-compose.dev.yml --profile ops down ztp-server
```

---

## 6. 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| DHCP 干扰现有网络 | 可能冲突 | 范围仅 `.200-.250`，12h 租约，容器停止即清空 |
| autocfg.cfg 含明文密码 | TFTP 协议明文传输 | 短期方案，ZTP 完成后 controller 立即 SSH 推 password hash |
| 设备 reset 失联 | .177 不可达 | 备份 startup.cfg + console 线兜底 |
| host network 容器异常 | 影响宿主机网络 | 容器自带 restart: "no"，异常退出不会重启 |

---

## 7. 相关文档

- [v31-ztp-research/proposal.md](../../openspec/changes/v31-ztp-research/proposal.md) — 调研立项
- [v31-ztp-research/design.md §2.5](../../openspec/changes/v31-ztp-research/design.md) — ztp-server 容器设计
- [v31-ztp-research/notes.md §3](../../openspec/changes/v31-ztp-research/notes.md) — capture-config 失败 + 新发现
- [H3C S5560-EI 基础配置指导 §13 自动配置](https://www.h3c.com/cn/d_201912/1252406_30005_0.htm) — 官方文档
- [H3C VCF Fabric §73](https://www.h3c.com/en/d_202404/2113460_294551_0.htm) — VCF ZTP 文档（R6607+）
