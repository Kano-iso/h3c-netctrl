# ztp-stack 容器 + H3C V7 ZTP 真机验证 SOP

> **变更**：v3.1 ZTP 调研 T3-T4 基建 + v3.1.1 ZTP 落地（[archive](../openspec/changes/archive/2026-07-18-v311-ztp-landing/)）
> **创建时间**：2026-07-17
> **更新**：2026-07-18
> **目标**：在受控局域网内，对 H3C V7 设备做 Zero Touch Provisioning / autocfg 自动配置验证

---

## 1. 容器职责

`ztp-server` 是 v3.1 ZTP 调研的**独立基建容器**，**不**影响 ops-toolkit 的开箱即用原则：

| 容器 | 职责 | 网络 | 凭据 | 启动方式 |
|---|---|---|---|---|
| **ops-toolkit** | 设备排错 / 探针 / 单功能验证 | docker bridge | .env 注入 | `docker compose ... --profile ops run --rm ops-toolkit` |
| **ztp-server**（新）| ZTP 服务的 DHCP + TFTP 二合一 | **host network**（共享宿主机网络栈）| .env 注入（ZTP_* 变量）| `docker compose ... --profile ops up -d ztp-server` |

---

## 2. 容器组件

**镜像**：`alpine:3.20`（轻量，约 7MB）+ `dnsmasq`（DHCP 67/UDP + TFTP 69/UDP 二合一）+ `python3/py3-jinja2`（v3.1.1 起渲染 `autocfg.cfg.j2`）

**目录结构**：
```
docker/ztp-stack/
├── Dockerfile                        # alpine + dnsmasq + python3 + py3-jinja2
├── entrypoint.sh                     # 渲染 env vars 到 dnsmasq.conf + autocfg.cfg
├── dnsmasq.conf.template             # DHCP + TFTP 模板
└── tftp/
    └── autocfg.cfg.j2                # H3C V7 启动配置 jinja2 模板
```

**渲染流程**（entrypoint.sh）：
1. `sed` 替换 `dnsmasq.conf.template` 中 `${ZTP_*}` 占位符 → `/etc/dnsmasq.conf`
2. `python3 + jinja2` 渲染 `autocfg.cfg.j2` → `/var/tftp/autocfg.cfg`
3. `exec dnsmasq -k -C /etc/dnsmasq.conf -d`（前台运行，日志到 stderr）

---

## 3. 关键设计

### 3.1 host network 模式

```yaml
ztp-server:
  network_mode: host  # 共享宿主机网络栈
```

**原因**：H3C V7 设备的 DHCP discover 是 **L2 广播**，不能跨网段。ops-toolkit 容器在 docker bridge network（172.x.x.x），不在 .177 物理网段（192.168.100.0/24），广播不通。`host network` 模式下，容器直接绑定宿主机网络接口，能接收物理网段的 L2 广播。

### 3.2 DHCP 临时池与 static 管理池（v3.1.1 当前口径）

```conf
dhcp-range=192.168.100.151,192.168.100.190,12h
```

- DHCP 池：`.151-.190`，只作为新设备首启临时地址
- Static 池：`.101-.140`，由 `ZTP_MGMT_IP` 渲染进 `autocfg.cfg` 并写入 physical OOB 口
- v3.1.1 已验证：`.177 → .101`、`.26 → .102`
- v3.1.2 再接入 controller 自动递增/自动分配；本轮不从 dnsmasq lease 自动反推 static 地址
- Gap：`.141-.150` 空出 10 个地址，避免误配时 DHCP/static 池贴边
- 不做 `dhcp-host=MAC,IP,infinite`，不做 `dhcp-leasefile` 持久化

### 3.3 v3.1.1 autocfg.cfg 当前策略

按 user 2026-07-17 02:13 明确：
- ✅ 只做基础配置：SSH 22 + NETCONF 830 + 凭据 + 带外 IP
- ❌ 不做业务配置：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ 不做配置联动：ZTP 完成后由 controller 继续推业务配置
- ✅ v3.1.1 起由 `autocfg.cfg` 写 physical OOB 口 static IP
- ✅ LSTN 当前 OOB 口：`M-GigabitEthernet0/0/0`
- ✅ RSTN `.26` 当前 OOB 口：配置文件全名 `M-GigabitEthernet0/0/0`，display brief 简写 `MGE0/0/0`；不要把接口名写成绝对规则，后续以现网探测到的 physical OOB 口为准

### 3.4 凭据走 env vars

`autocfg.cfg` 模板中所有占位符（`${ZTP_*}`）由 .env 注入：
- 避免硬编码密码（user memory 红线）
- 同一份模板可用于不同设备（仅 .env 变量不同）
- v3.1.1 统一使用项目主账密变量：`ZTP_ADMIN_USER=python` / `ZTP_ADMIN_PASS=Admin123!@#`

### 3.5 v3.1.1 验证顺序

| 顺序 | 设备 | 目的 |
|---|---|---|
| 1 | `.177` S6850/T7064P15-hcl | 完整 ZTP 主验证：空配置 → DHCP → TFTP → autocfg → static `.101` → save → 重启持久 |
| 2 | `.26` V9850/R7643P02 | EVE-NG 借用 RSTN 设备的适配性验证：空配置 → DHCP → TFTP → autocfg → static `.102` → save → 重启持久 |
| - | `.5` S6850/T7064P15-prod | 不跑完整 ZTP；仅保留已完成的 OOB/static 命令探针作为 LSTN 佐证 |

`.26` 的背景：它是 v3.0 起用于 RSTN/schema NETCONF 路径验证的 EVE-NG 借用测试设备。v3.1.1 继续让它承担 RSTN 平台适配验证；v3.2 会把这条思路扩展为 EVENG 平台迁移和完整数据面验证。

---

## 4. 容器用法

### 4.1 配置 .env

在 `.env` 中加入（参考 `.env.example`）：
```bash
# ZTP 宿主机 IP（按实际修改）
ZTP_HOST_IP=192.168.100.4

# DHCP 范围（v3.1.1 默认 .151-.190）
ZTP_DHCP_RANGE_START=192.168.100.151
ZTP_DHCP_RANGE_END=192.168.100.190
ZTP_DHCP_LEASE=12h

# 设备自动配置（autocfg.cfg 渲染变量）
ZTP_PLATFORM=lstn
ZTP_HCL_T7064P15=false
# 留空时按 ZTP_MGMT_IP 自动生成, 例如 .101 -> ztp-switch-101
ZTP_SYSNAME=
# 本次要写入设备 OOB 口的 static 管理地址；验证下一台设备前手动/由控制器递增
ZTP_MGMT_IP=192.168.100.101
ZTP_ADMIN_USER=python
ZTP_ADMIN_PASS=Admin123!@#
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

## 5. v3.1.1 真机验证结果

| 设备 | 平台 | ZTP static IP | 结果 | 证据 |
|---|---|---:|---|---|
| `.177` | S6850 / T7064P15-hcl / LSTN | `.101` | ✅ DHCP 临时地址 → TFTP → static `.101` → SSH/NETCONF → 二次 reboot 持久 | `openspec/changes/archive/2026-07-18-v311-ztp-landing/captures/ztp-test/config_101_after_ztp_20260718.log` |
| `.26` | V9850-256H / R7643P02 / RSTN | `.102` | ✅ DHCP 临时地址 → TFTP → static `.102` → SSH/NETCONF → 二次 reboot 持久 | `openspec/changes/archive/2026-07-18-v311-ztp-landing/captures/ztp-test/config_102_after_ztp_20260718.log` |
| `.5` | S6850 / T7064P15-prod / LSTN | 不做完整 ZTP | ✅ 仅保留 OOB/static 命令探针佐证 | 记录随 v3.1.1 archive 进入 release notes |

> 说明：`.177` 的证据来自动态 sysname 逻辑调整前，日志中仍是 `ztp-device`；当前模板已按 `ZTP_MGMT_IP` 派生 `ztp-switch-101` / `ztp-switch-102`，`.26` 已验证 `ztp-switch-102`。

## 6. 真机验证 SOP

> **风险等级**：中高（设备 reset + reboot）
> **前提**：设备物理可达，且已有 startup/current 配置备份或 console 兜底。

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

优先用 ops-toolkit 的 `capture-config.sh`。v3.1.1 起脚本已补齐 H3C V7 `ssh-rsa` 兼容参数；如果设备未启用 SCP server，先在设备上执行 `scp server enable`。

```bash
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/capture-config.sh --device 192.168.100.177
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
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/reboot-wait.sh \
  --device 192.168.100.177 \
  --reset-saved \
  --wait-ip 192.168.100.101 \
  --timeout 300
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
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-host.sh --device ztp-177
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-netconf.sh --device ztp-177

# 验证 autocfg.cfg 内容已应用
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit paramiko-batch-exec.sh --device ztp-177 --command "display current-configuration | include sysname"
# 预期: sysname / OOB static IP / ssh server enable / netconf ssh server enable 均存在
```

### 6.3 兜底阶段（验证失败时）

#### 步骤 7：失败恢复

如果验证失败（超时内 SSH 22 没起），立即恢复设备备份：

```bash
# 1. 停止 ztp-server（避免重复干扰）
docker compose -f docker-compose.dev.yml --profile ops down ztp-server

# 2. 通过 console 线 + 串口登录 .177（需用户物理操作）
# 3. 手动粘贴备份内容到 .177
# 4. save force + reboot
```

### 6.4 收尾阶段

#### 步骤 8：结果记录 + 决策

- **成功** → 记录真机证据，进入 OpenSpec archive
- **失败** → 记录失败平台和命令，回 Spec 重新对齐

#### 步骤 9：环境清理

```bash
# 停止 ztp-server（避免 DHCP 持续分配）
docker compose -f docker-compose.dev.yml --profile ops down ztp-server
```

---

## 7. 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| DHCP 干扰现有网络 | 可能冲突 | 范围仅 `.151-.190`，12h 租约，容器停止即清空；仅受控局域网启用 |
| autocfg.cfg 含明文密码 | TFTP 协议明文传输 | 短期方案，ZTP 完成后 controller 立即 SSH 推 password hash |
| 设备 reset 失联 | 设备不可达 | 备份 startup.cfg + console 线兜底；重启动作走 ops-toolkit `reboot-wait.sh` |
| host network 容器异常 | 影响宿主机网络 | 容器自带 restart: "no"，异常退出不会重启 |
| 构建镜像受外部仓库影响 | 当前环境曾遇到 alpine 镜像代理 401 | 代码逻辑已验证；必要时复用本地镜像或修复镜像源后再 build |

---

## 8. 相关文档

- [v31-ztp-research/proposal.md](../openspec/changes/archive/2026-07-18-v31-ztp-research/proposal.md) — 调研立项
- [v31-ztp-research/design.md](../openspec/changes/archive/2026-07-18-v31-ztp-research/design.md) — ztp-server 容器设计
- [v3.1.1 release notes](../RELEASE-NOTES-v3.1.1.md) — 落地结论、真机验证与已知注意点
- [H3C S5560-EI 基础配置指导 §13 自动配置](https://www.h3c.com/cn/d_201912/1252406_30005_0.htm) — 官方文档
- [H3C VCF Fabric §73](https://www.h3c.com/en/d_202404/2113460_294551_0.htm) — VCF ZTP 文档（R6607+）
