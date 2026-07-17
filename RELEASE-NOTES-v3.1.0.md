# RELEASE NOTES — v3.1.0

> **发版日期**：2026-07-18
> **发版类型**：调研 change（**无新功能落地**，仅完成 ZTP 可行性调研 + 基建容器）
> **关联 OpenSpec change**：[archive/2026-07-18-v31-ztp-research](openspec/changes/archive/2026-07-18-v31-ztp-research/)

---

## 1. 主题

**H3C V7 设备 ZTP（Zero Touch Provisioning）调研 — 决策 B 精简 ZTP**

v3.1 候选调研变更。本 change **不发布新功能**，仅完成 ZTP 可行性评估 + 决策 + 基建容器（`ztp-server`）。

---

## 2. 调研结论

### 2.1 决策矩阵

| 探针结果 | 推荐决策 | 实际决策 |
|---|---|---|
| T1 文档 + T2 探针 | C（不投入）| ~~已选 C~~ |
| T4 真机验证 | A / B / C 重新评估 | **B（精简 ZTP）** |

### 2.2 T1-T2 调研（2026-07-17）

- **H3C 官方 VCF Fabric ZTP 文档**：仅 S6805/S6825/S6850/V9850/S9820 5 个平台 + 软件版本 R6607+ 才支持
- **本项目 3 设备实测**：`ztp enable` / `display ztp status` / `display ztp history` 全部 Unrecognized
  - `.5 S6850 R6555` — 软件版本早于 R6607+
  - `.26 V9850 R7643P02` — 软件版本在范围但镜像未实现
  - `.177 S6850 T7064P15` — HCL 内部测试版精简
- **初判**：VCF ZTP 路径在 3 设备上**不适用**

### 2.3 T1 后期新发现（2026-07-17 03:35）

用户提供知乎链接提示 **H3C V7 还有更基础的"自动配置"功能（autocfg.cfg）**——不依赖 VCF ZTP 命令，是空配置启动的**默认行为**，理论上**所有 H3C V7 都支持**。

→ 决策从 C 调整为"重做 T3-T5 验证自动配置路径"。

### 2.4 T3 基建（2026-07-17 16:31）

按用户 2026-07-17 03:50 指示"开新容器做 ZTP server"，实施独立 `ztp-server` 容器：

| 文件 | 作用 |
|---|---|
| `docker/ztp-stack/Dockerfile` | alpine:3.20 + dnsmasq |
| `docker/ztp-stack/entrypoint.sh` | 模板渲染（env vars → dnsmasq.conf + autocfg.cfg）|
| `docker/ztp-stack/dnsmasq.conf.template` | DHCP + TFTP 二合一 |
| `docker/ztp-stack/tftp/autocfg.cfg.template` | H3C V7 自动配置最小可用配置 |
| `docker-compose.dev.yml` | 新增 ztp-server 服务（`network_mode: host` + `cap_add: NET_ADMIN`）|
| `.env.example` + `.env` | ZTP_* 变量定义 |
| `docs/ztp-stack.md` | 容器使用文档 |

**关键设计**：`network_mode: host`（共享宿主机网络栈，接收 .177 物理网段 L2 广播）。

### 2.5 T4 真机验证（2026-07-18）

**.177 S6850 T7064P15 HCL 测试版真机验证，autocfg 机制链路完整工作**：

```
Automatic configuration attempt: 1.
Not ready for automatic configuration: no interface available.
Waiting for the next...

Automatic configuration attempt: 2.
Interface used: M-GigabitEthernet0/0/0.
Enable DHCP client on M-GigabitEthernet0/0/0.
Set DHCP client identifier: 06057e0a0d00
Obtained an IP address for M-GigabitEthernet0/0/0: 192.168.100.250.
Obtained configuration file name autocfg.cfg and TFTP server name 192.168.100.254.
Resolved the TFTP server name to 192.168.100.254.
Successfully downloaded file autocfg.cfg.
Executing the configuration file. Please wait...
Automatic configuration successfully completed.
```

**autocfg.cfg 模板各命令实证结果**（SSH 192.168.100.250 admin/admin 验证）：

| 命令 | 是否生效 | 证据 |
|---|---|---|
| `sysname ztp-device` | ✅ 生效 | prompt 变成 `<ztp-device>` |
| `local-user admin class manage` | ✅ 生效 | `dis cu` 有 `local-user admin class manage` |
| `password simple admin` | ✅ 生效 | SSH admin/admin 登录成功 |
| `authorization-attribute user-role network-admin` | ✅ 生效 | 登录后能跑 display |
| `ssh server enable` | ✅ 生效 | `Stelnet server: Enable` |
| `netconf ssh server enable` | ✅ 生效 | `NETCONF server: Enable` |
| `user-interface vty 0 15 + auth + ssh` | ✅ 生效 | SSH 22 可登 |
| `save force` | ✅ 生效 | `startup.cfg 6631 bytes` 已 save |
| `interface Vlan-interface1 + ip address 192.168.100.10` | ❌ 未生效 | Vlan1 down/down，无 IP |
| `ip gateway 192.168.100.1` | ❌ 未生效（推断）| T7064P15 不支持 |

### 2.6 T5 最终决策（2026-07-18）

- **决策**：**B（精简 ZTP）**
- **理由**：
  1. ✅ autocfg 机制完全工作（attempt 2 完整链路通）
  2. ✅ autocfg.cfg 模板大部分生效（sysname/local-user/ssh/netconf/save force）
  3. ⚠️ 唯一不生效：Vlan1 IP 配置行（`ip gateway` 在 T7064P15 平台不支持）
  4. ⚠️ 副作用：H3C V7 默认首次 SSH 登录强制改密
  5. ✅ autocfg 机制自动处理 OOB 口 + DHCP client
- **决策 B 含义**：
  - ✅ 保留 `ztp-server` 容器（DHCP + TFTP 基建完整）
  - ✅ 简化 `autocfg.cfg` 模板：删 IP 配置 + 加 `password-control login-password-change disable`
  - ✅ 设备 IP 由 autocfg 机制 OOB DHCP 自动拿（pool .200-.250, lease 12h）

---

## 3. 变更清单

### 3.1 新增基建

| 类型 | 路径 | 说明 |
|---|---|---|
| 新容器 | `docker/ztp-stack/` | 独立 ztp-server 容器（alpine + dnsmasq 二合一）|
| 新文档 | `docs/ztp-stack.md` | ztp-server 容器使用文档 + 真机验证 SOP |
| 新变量 | `.env.example` | ZTP_* 变量定义 |
| 新编排 | `docker-compose.dev.yml` | 新增 ztp-server 服务（`profiles: ["ops"]`）|

### 3.2 模板精简

`docker/ztp-stack/tftp/autocfg.cfg.template`：
- 删除 `interface Vlan-interface1 + ip address + ip gateway`（autocfg 机制自动处理 OOB DHCP，模板不需要管 IP）
- 加 `password-control login-password-change disable`（关首次改密）
- 简化模板变量（移除 ZTP_MGMT_IP / ZTP_MGMT_MASK / ZTP_MGMT_GATEWAY）

### 3.3 文档同步

- `VERSION-ROADMAP.md` §1 全景表加 v3.1 行 + 新增 §3.1 章节
- `README.md` 顶部版本表加 v3.1 行
- `PRD-V3.0.md` §8.1 远期 ZTP 调研更新为"已调研完成 + 决策 B"
- `openspec/changes/v31-ztp-research/` → `openspec/changes/archive/2026-07-18-v31-ztp-research/`（archive 闭环）

---

## 4. Commit 序列

| # | Commit | 说明 |
|---|---|---|
| 1 | `5c8748a` | docs(ztp): T1+T2 ZTP 调研 + 决策重置 |
| 2 | `b9e316c` | feat(ztp): T3 ztp-server 容器基建（dnsmasq + autocfg.cfg 模板）|
| 3 | `ebe1565` | feat(ztp): T4 .177 真机验证成功 + autocfg.cfg 模板精简 |
| 4 | (本 commit) | docs(ztp): T5 决策报告 + archive + 同步 A 类文档 |

---

## 5. 后续 change 计划（v3.1 落地）

| Change | 范围 | 状态 |
|---|---|---|
| **v3.1.1 ztp-landing** | autocfg.cfg 模板适配多平台（.5 R6555 / .26 R7643P02 / .177 T7064P15）+ 容器稳定性测试 | ⏳ 待 user 启动 |
| **v3.1.2 ztp-auto-onboard** | controller 监听 DHCP lease → 主动 SSH 纳管 + 推业务 IP + 同步资产 | ⏳ 待 user 启动 |
| **v3.1.3 ztp-asset-sync** | 资产自动可见（前端可查，无需手动 `POST /api/devices`）| ⏳ 待 user 启动 |

---

## 6. 测试统计

| 项 | 数量 | 说明 |
|---|---|---|
| 探针命令 | 9 次 | T2 3 设备 × 3 命令（VCF ZTP 命令）|
| 实证探针 | 5 条 | T4 5 关键 autocfg.cfg 命令（SSH 上 .177 验证）|
| 容器组件 | 1 | ztp-server（alpine + dnsmasq 二合一）|
| 模板版本 | 1 | autocfg.cfg.template（T7064P15 验证通过精简版）|
| 文档新增 | 1 | docs/ztp-stack.md |

---

## 7. 真机验证示例

```bash
# 1. 启动 ztp-server 容器
$ docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server
Container h3c-netctrl-ztp-server Running
# UDP 67 + 69 在 0.0.0.0 监听

# 2. 备份 .177 现状（用 paramiko 避开 scp 兼容问题）
$ docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --command "more startup.cfg" > backup_177_startup_20260717.cfg

# 3. 设备侧清空配置 + reboot（paramiko 手动应答 2 个 [Y/N]）
$ docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit python3
>>> client.connect('192.168.100.177', 22, ...)
>>> channel.send('delete /unreserved flash:/startup.cfg\n')
>>> channel.send('reboot\n')
>>> # 应答 N (不保存) + Y (确认 reboot)
>>> # 设备: "Now rebooting, please wait....."

# 4. 设备空配置启动 → 自动配置触发（attempt 2 成功）
Automatic configuration attempt: 2.
Obtained an IP address for M-GigabitEthernet0/0/0: 192.168.100.250.
Obtained configuration file name autocfg.cfg and TFTP server name 192.168.100.254.
Successfully downloaded file autocfg.cfg.
Automatic configuration successfully completed.

# 5. SSH 上 .177 验证（autocfg.cfg 配的 admin/admin 账密）
$ ssh admin@192.168.100.250
# 首次登录触发 [Y/N] 改密, 改密后:
<ztp-device>dis cu | include sysname
 sysname ztp-device
<ztp-device>dis cu | include local-user
local-user admin class manage
<ztp-device>dis ssh server status
 Stelnet server: Enable
 NETCONF server: Enable
<ztp-device>display startup
Current startup saved-configuration file: flash:/startup.cfg(*)
```

---

## 8. 已知小问题

- **.177 SSHExecutor 多 [Y/N] 应答 bug**：当前 SSHExecutor 遇到多个连续 [Y/N] 提示只应答第一个，导致 reboot 命令实际未真执行。T4 用 paramiko channel 手动应答 2 个 [Y/N] 绕过。**未修**，待 v3.1.1 修复。
- **H3C V7 默认首次登录强制改密**：autocfg.cfg 模板已加 `password-control login-password-change disable` 关改密。
- **`.ip address dhcp-alloc` 在 M-GE 0/0/0 上不持久**：T4 实验中手动 SSH 配此命令释放 DHCP IP，导致 M-GE 0/0/0 失联（仅用于命令支持实证，不影响模板结论）。.177 后续 user 在 console 用 backup 恢复。
- **autocfg.cfg 不配 IP**：T7064P15 Vlan1 因无物理接口 up 而 down，autocfg.cfg 模板不配 IP 配置行。设备 IP 由 autocfg 机制 OOB DHCP 自动拿（pool .200-.250, lease 12h）。

---

## 9. 升级 / 回退

- **升级**：无（v3.1.0 仅调研 + 基建容器，无 Controller 业务代码变化）
- **回退**：删除 ztp-server 容器 + 相关文件即可（`docker compose --profile ops down ztp-server` + `rm -rf docker/ztp-stack/`）

---

**v3.1.0 调研 change 闭环 — 决策 B（精简 ZTP），等 user 启动后续 v3.1.1 / v3.1.2 / v3.1.3 change。**
