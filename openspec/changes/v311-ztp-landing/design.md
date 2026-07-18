# v311-ztp-landing — Design

> **状态**：Propose → Design 阶段（**Apply 前必读**）
> **目的**：技术方案 + 关键决策 + 实施风险 + 部署回退
> **用户 2026-07-18 复盘后修订**：从"mac-binding + dhcp-leasefile 持久化"改为"autocfg.cfg 推 static IP 写物理 OOB 口 + offset 50 跨池映射"
> **接手修订**：`.177` 是完整 ZTP 主验证设备；`.26` 是 EVE-NG 借用的 V9850/RSTN 测试设备，必须做适配性验证；`.5` 不跑完整 ZTP。OOB 口按现网探测结果使用，当前 `.26` 实测为 `MGE0/0/0`，不是旧 PRD 的 `MEth0/0/0`。

---

## Context

### v3.1.0 现状（已闭环）

- ✅ `docker/ztp-stack/` 基建就绪：alpine:3.20 + dnsmasq 二合一（DHCP + TFTP）
- ✅ `docker-compose.dev.yml` `--profile ops` 集成 ztp-server 服务（`network_mode: host`）
- ✅ `autocfg.cfg.template` 在 **.177 T7064P15** 验证通过：
  - sysname / local-user / SSH / NETCONF / save force 全工作
  - **Vlan1 IP `ip address` Unrecognized**（T7064P15 不支持 Vlan-interface1 配 static）
  - **Vlan1 `ip gateway` Unrecognized**（T7064P15 不支持）
  - 默认首次登录改密需 `password-control login-password-change disable`
- ✅ 设备实际 DHCP 走 `M-GigabitEthernet0/0/0` 物理 OOB 口（v3.1.0 release notes L67-72 真机日志）
- ❌ **遗留 2 问题**：
  1. **IP 不持久**：DHCP lease 12h 过期后设备失联
  2. **多平台未适配**：.5 R6555 / .26 R7643P02 命令差异未知

### v3.1.1 目标（本次 change）

- **核心**：解决上述 2 遗留问题，**为 v3.1.2 / v3.1.3 解锁**
- **约束**：
  - 静态 IP 推送通道：**autocfg.cfg 推 static IP 写物理 OOB 口**（用户 2026-07-18 拍板）
  - 物理 OOB 口：按现网探测到的 physical OOB 口写入（S6850 当前 `M-GigabitEthernet0/0/0`；`.26` V9850 当前 `MGE0/0/0`）
  - 模板方案：**jinja2 通用 + 2 平台条件分支**（LSTN / RSTN）
  - 1:1 映射 = **offset 50 跨池**（DHCP .151-.190 ↔ static .101-.140，user 拍板）
  - **不走** mac-binding / `dhcp-host=MAC,IP,infinite` / dhcp-leasefile 持久化（user 2026-07-18 明确反对）
  - **不走** Vlan-interface1（v3.1.0 失败路径）
  - **不绑** VRF（autocfg.cfg 阶段简化）
  - **零业务代码**（`backend/` / `frontend/` 不动）
- **依赖**：v3.1.0 基建（ztp-server 容器 + autocfg.cfg T7064P15 模板）
- **后续**：v3.1.2（controller 自动纳管）/ v3.1.3（资产可见）

### Stakeholders

- **user**：项目 owner，决策拍板
- **AI（assistant）**：实施 + 测试
- **设备**：.177 T7064P15（完整 ZTP 主验证）/ .26 R7643P02（V9850/RSTN 适配性验证）/ .5 R6555（S6850/LSTN 命令探针佐证，不跑完整 ZTP）

---

## Goals / Non-Goals

### Goals

1. ✅ 1:1 静态 IP 池子（offset 50 跨池，DHCP .151-.190 ↔ static .101-.140）
2. ✅ autocfg.cfg 推 static IP 写**物理 OOB 口**（S6850 当前 = M-GigabitEthernet0/0/0；`.26` V9850 当前 = MGE0/0/0；后续按现网探测）
3. ✅ autocfg.cfg jinja2 通用模板 + 2 平台条件分支（LSTN / RSTN）
4. ✅ ZTP 模板路由（`ZTP_PLATFORM` env var：lstn / rstn）
5. ✅ .177 真机验证完整 ZTP 链路（空配置 → DHCP .151 → static .101 → 重启持久）
6. ✅ .26 真机适配性验证（`.177` 主验证通过后）；`.5` 仅命令探针佐证
7. ✅ 文档同步（docs/ztp-stack.md + VERSION-ROADMAP + README）

### Non-Goals

- ❌ **业务配置**（VPC / 端口绑定 / 路由协议）—— v3.0 + v3.2 负责
- ❌ **controller 自动纳管**（DHCP lease → POST /api/devices）—— v3.1.2
- ❌ **前端 ZTP 管理界面**（设备列表实时刷新）—— v3.1.3
- ❌ **DHCP 高可用**（单 dnsmasq 足够测试）
- ❌ **HTTP 协议替换 TFTP**（H3C V7 TFTP 明文风险）—— v3.x 远期
- ❌ **设备序列号绑定**（option 82）—— 远期
- ❌ **per-MAC 静态 IP 分配**（multi-device ZTP）—— v3.1.2 范畴
- ❌ **mac-binding / `dhcp-host=MAC,IP,infinite`**（用户 2026-07-18 明确反对）
- ❌ **dhcp-leasefile 持久化**（用户 2026-07-18 明确反对）
- ❌ **Vlan-interface1 路径**（v3.1.0 失败，已走物理 OOB 口）
- ❌ **VRF 绑定**（autocfg.cfg 阶段简化）

---

## Decisions

### Decision 1: 1:1 映射 = offset 50 跨池（DHCP `.151+X` ↔ static `.101+X`）

**方案**：

| 段 | 范围 | 大小 | 用途 |
|---|---|---|---|
| DHCP 池 | `192.168.100.151-.190` | 40 IP | 设备首启"一无所知"时分配临时地址（"动态壁纸"）|
| Static 池 | `192.168.100.101-.140` | 40 IP | autocfg.cfg 推的最终 static IP（写物理 OOB 口）|
| gap 安全余量 | `192.168.100.141-.150` | 10 IP | DHCP 池和 static 池之间留 10 IP 安全间隔 |
| 映射公式 | `static = DHCP - 50` | offset 50 | .151→.101，.152→.102，...，.190→.140 |

**为什么 offset 50**：
- user 原话"250 映射到 150"体现 offset 思想
- 2 池**完全分离**（user 2026-07-18 明确指出"250 写 250 = 抢占池子"会冲突）
- 40 对 40 完全对称，0 冲突
- 避开 .100 Spine（已有设备）

**autocfg.cfg 应用时序**（H3C V7 autocfg 机制 + 物理 OOB 口 static IP）：

```
① 设备空配置首启
   物理 OOB 口 M-GigabitEthernet0/0/0 默认 DHCP client（H3C 内置）
   ↓
② DHCP 给 .151 临时 IP（autocfg.cfg 不参与，H3C 内置 OOB 行为）
   ↓
③ 设备用 .151 主动从 TFTP 拉 autocfg.cfg
   ↓
④ 设备应用 autocfg.cfg（不重启，H3C V7 autocfg 机制）
   interface M-GigabitEthernet0/0/0
    ip address 192.168.100.101 255.255.255.0   ← static IP（offset 50 映射 .151 - 50 = .101）
   ↓
⑤ M-GigabitEthernet0/0/0 从 DHCP client 切到 static IP
   .151 DHCP 释放，.101 static 生效
   ↓
⑥ save force 持久化
   ↓
⑦ 设备 OOB 口 = .101 static IP，永久脱离 DHCP 池
   DHCP lease 12h 过期不影响
```

**关键修复点（相对 v3.1.0）**：
- ❌ v3.1.0 走 `interface Vlan-interface1 + ip address`（虚拟口 Unrecognized）
- ✅ v3.1.1 改走 `interface M-GigabitEthernet0/0/0 + ip address`（物理 OOB 口，v2.x 验证成功）

**备选方案**（已 user 排除）：
- ❌ DHCP .200-.250 ↔ static .100-.150（offset 100，但 .100 占用）
- ❌ DHCP .200-.250 ↔ static .150-.200（.200 撞 DHCP .200）
- ❌ mac-binding / `dhcp-host=MAC,IP,infinite`（user 2026-07-18 明确反对）
- ❌ 自映射（DHCP 给 X，autocfg.cfg 写 X）—— 抢占池子冲突

**PoC 实施**：
- .177 测试：DHCP .151 ↔ static .101（autocfg.cfg 硬编码 .101）
- 多设备路由（per-MAC）留 v3.1.2

### Decision 2: 静态 IP 推送通道 = autocfg.cfg 内嵌（写物理 OOB 口）

**方案**：autocfg.cfg 模板中含 `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.101 255.255.255.0` 命令（LSTN 平台），autocfg 跑完 `save force` 持久化。

**为什么**：
- 符合 user 2026-07-18 拍板（"我们用静态啊，我们只在第 1 步刚上线的时候获取的时候用动态壁纸而已"）
- 不依赖 controller / SSH 推送（架构解耦）
- 最简实现"白屏零操作"愿景
- v2.x 真实配置路径（`.177 startup.cfg L236-238` 已验证）

**备选方案**（已 user 排除）：
- ❌ controller SSH 推送静态 IP（依赖 controller，架构耦合）
- ❌ Vlan-interface1 路径（v3.1.0 T7064P15 Unrecognized）
- ❌ mac-binding（user 2026-07-18 明确反对）
- ❌ dhcp-leasefile 持久化（user 2026-07-18 明确反对）

### Decision 3: 物理 OOB 口命名（2 平台差异）

| 平台 | 设备型号 | 软件版本 | 物理 OOB 口 | 依据 |
|------|---------|---------|-----------|------|
| **LSTN** | .5 S6850 / .177 S6850 | R6555 / T7064P15 | **`M-GigabitEthernet0/0/0`** | v2.x .177 startup.cfg L236-238 真实配置 |
| **RSTN** | .26 V9850 | R7643P02 | **当前现网实测 `MGE0/0/0`** | T1 探针发现；旧 PRD 写的 `MEth0/0/0` 在 `.26` 上不存在 |

**autocfg.cfg.j2 模板物理 OOB 口命令**（jinja2 条件分支）：

```jinja2
{% if platform == 'lstn' %}
interface M-GigabitEthernet0/0/0
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% elif platform == 'rstn' %}
interface MGE0/0/0
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% endif %}
```

**jinja2 模板变量**：
- `platform`：`lstn` / `rstn`（由 `ZTP_PLATFORM` env var 路由）
- `mgmt_ip`：static 池的 IP（如 .101）
- `sysname`：设备名
- `admin_user` / `admin_pass`：本地用户凭据

### Decision 4: autocfg.cfg 模板 = jinja2 通用 + 2 平台条件分支

**完整 autocfg.cfg.j2 模板草案**（v3.1.1 设计）：

```jinja2
#
# H3C V7 自动配置 - autocfg.cfg
# 平台: {{ platform }} (LSTN=S6850 / RSTN=V9850)
# 生成时间: {{ ztp_date }}
# 用途: 新设备首次上线基础配置（sysname + 物理 OOB 口 static IP + SSH + NETCONF + 凭据）
#

# 系统名
sysname {{ sysname }}

# === 物理 OOB 口 static IP（offset 50 跨池映射）===
{% if platform == 'lstn' %}
interface M-GigabitEthernet0/0/0
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% elif platform == 'rstn' %}
interface MGE0/0/0
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% endif %}

# === SSH 服务（通用）===
ssh server enable
ssh server authentication-timeout 300
local-user {{ admin_user }} class manage
 password simple {{ admin_pass }}
 service-type ssh terminal
 authorization-attribute user-role {% if platform == 'lstn' %}network-admin{% elif platform == 'rstn' %}level-15{% endif %}
quit
user-interface vty 0 15
 authentication-mode scheme
 protocol inbound ssh
quit

# === NETCONF 服务（平台条件分支）===
{% if platform == 'lstn' %}
netconf ssh server enable
{% elif platform == 'rstn' %}
netconf soap http enable
{% endif %}

# === 关闭首次登录改密（通用，T7064P15 可能不支持但 T1 探针验证）===
password-control login-password-change disable

# === 持久化 ===
save force
```

**为什么 jinja2 条件分支（vs 2 份独立 .cfg 文件）**：
- 1 份模板维护成本低（vs PRD V3.1.1 提议的 2 份独立 .cfg）
- 通用段（sysname / SSH / 凭据 / save force）所有平台共用
- 平台差异隔离在条件分支内，可读性 OK
- 路由逻辑简单（env var 切换）

**备选方案**（已排除）：
- ❌ 2 份独立 .cfg 文件（PRD V3.1.1 提议，但同步维护成本高）
- ❌ 3 平台条件分支（v3.1.1 旧 proposal，但 R6555 / T7064P15 都在 S6850 平台，命令一致）

### Decision 5: 模板路由 = `ZTP_PLATFORM` env var

**方案**：
- `.env` 新增 `ZTP_PLATFORM=lstn`（默认 `lstn`，覆盖 .5 / .177 两个 LSTN 设备）
- `entrypoint.sh` 读取 `ZTP_PLATFORM` → jinja2 渲染时传 `platform=lstn` / `rstn`

**为什么**：
- 简单，1 个 env var 控制
- 默认值 `lstn` 兼容 v3.1.0（无需立即改 .env，autocfg.cfg 内容升级到 2 平台分支）

**备选方案**（已排除）：
- ❌ DHCP option 60 vendor-class 识别（dnsmasq 支持但配置复杂）
- ❌ MAC 前缀识别（不可靠）

### Decision 6: 不做 mac-binding / dhcp-leasefile 持久化

**为什么**：
- user 2026-07-18 原话："不是 mac 绑定，不用了啊"
- v3.1.1 设计只用 static IP + offset 50 跨池，autocfg.cfg 应用后设备 OOB 口从 DHCP client 切到 static IP
- DHCP 仅设备首启用一次（"动态壁纸"），设备切到 static IP 后永久脱离 DHCP 池
- v3.1.2 controller 自动纳管（监听 DHCP lease 变化）暂时不需要，纳管靠 SSH 推到 controller

**dnsmasq.conf.template 关键配置**（v3.1.1）：

```conf
# DHCP server（设备首启 "动态壁纸"）
dhcp-range=192.168.100.151,192.168.100.190,12h
dhcp-option=66,${ZTP_HOST_IP}            # TFTP server IP
dhcp-option=67,autocfg.cfg                # bootfile name

# TFTP server
enable-tftp
tftp-root=/var/tftp
tftp-no-blocksize                          # 兼容 H3C V7 TFTP 客户端

# Log
log-queries
log-dhcp
log-facility=/var/log/dnsmasq.log

# === 不做 mac-binding（user 反对）===
# === 不做 dhcp-leasefile 持久化（user 反对）===
```

**v3.1.0 → v3.1.1 dnsmasq.conf.template 变更**：
- DHCP 池：`.200-.250`（51 IP）→ `.151-.190`（40 IP）
- 删除 `dhcp-host=MAC,IP,infinite`（v3.1.1 不做）
- 删除 `dhcp-leasefile=/var/lib/misc/dnsmasq.leases`（v3.1.1 不做）
- 删除 `docker-compose.dev.yml` volume 挂载 `/var/lib/misc`（v3.1.1 不做）

---

## Risks / Trade-offs

| 风险 | 严重度 | 缓解 |
|------|------|------|
| 2 平台 OOB 口命名差异（M-GigabitEthernet0/0/0 vs `.26` 当前 MGE0/0/0）| 🟡 中 | jinja2 条件分支隔离；T1 探针 #1/#2 验证 OOB 口存在；后续按现网 physical OOB 口探测结果更新 |
| .5 R6555 完整 ZTP 风险 | 🟢 低 | `.5` 不跑完整 ZTP；仅保留已完成的 OOB/static 命令探针作为 LSTN 佐证 |
| .26 R7643P02 NETCONF 差异（SSH vs SOAP）| 🟡 中 | T1 探针 #6 验证 `.26 + netconf ssh server enable` vs `netconf soap http enable` |
| .26 R7643P02 user-role 差异（network-admin vs level-15）| 🟡 中 | T1 探针 #7 验证 `.26 + authorization-attribute user-role level-15` |
| H3C V7 TFTP 传输 autocfg.cfg 明文密码 | 🟡 中 | 接受 v3.1.1 风险，HTTP 协议 + password hash 留 v3.x 远期 |
| .26 设备实际验证不可达 | 🟡 中 | T1 `check-host` / `check-netconf` 探针先验，不通则文档记录"RSTN 适配性验证待设备恢复" |
| 设备失联（reset saved-configuration 后无法 SSH）| 🔴 高 | 真机测试前必 backup startup.cfg + 准备 restore 脚本（走 ops-toolkit）|
| autocfg 失败时设备进入不一致状态 | 🟡 中 | T4 失败立即 `restore 备份`（参数化 restore 脚本）|
| ZTP_PLATFORM 误配（用户填错）| 🟢 低 | `entrypoint.sh` 启动时校验 `ZTP_PLATFORM ∈ {lstn, rstn}`，不在则 warning + 用 lstn 默认 |
| TFTP 文件名硬编码 `autocfg.cfg` | 🟢 低 | H3C V7 自动配置固定文件名（基础配置指导 §13），无需多文件 |
| jinja2 模板条件分支爆炸（3 差异点 × 2 平台 = 6 分支）| 🟢 低 | 差异点 < 5 个；超阈值则降级为 2 份独立 .cfg 文件 |
| v3.1.0 决策 B 回归风险（删 Vlan1 IP 命令）| 🟢 低 | v3.1.1 改走物理 OOB 口，命令完全不同；qa 回归测试必跑 |

---

## Migration Plan

### 部署步骤

```bash
# 1. 拉取代码
git pull origin main

# 2. 更新 .env（新增 ZTP_PLATFORM，删除 ZTP_MGMT_IP/MASK/GATEWAY）
# 编辑 .env:
#   ZTP_PLATFORM=lstn                # 默认 lstn，覆盖 .5 / .177
#   删除 ZTP_MGMT_IP / ZTP_MGMT_MASK / ZTP_MGMT_GATEWAY（autocfg.cfg 不再需要这些变量）

# 3. 重建 ztp-server 镜像
docker compose -f docker-compose.dev.yml --profile ops build ztp-server

# 4. 停止旧容器（如在跑）
docker compose -f docker-compose.dev.yml --profile ops down ztp-server

# 5. 启动新容器
docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server

# 6. 验证
docker exec h3c-netctrl-ztp-server dnsmasq --test -C /etc/dnsmasq.conf
docker exec h3c-netctrl-ztp-server cat /var/tftp/autocfg.cfg | head -20
```

### 回退策略

```bash
# 回退到 v3.1.0 状态（1 步）
git revert <v3.1.1 commit hash>
docker compose -f docker-compose.dev.yml --profile ops build ztp-server
docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server
```

**回退点**：
- T1 探针失败 → 决策 C（v3.1.1 不实施）→ git revert 所有 v3.1.1 commit
- T5 真机验证失败 → 文档记录"该平台需商用 R6607+ 升级后才能 ZTP" → 仅删除该平台 template 分支
- v3.1.1 整体失败 → git revert + VERSION-ROADMAP 标 v3.1.1 "⏸️ 回退"

### 数据库迁移

**无 Alembic 迁移**（本 change 不动 backend 表结构）。

### 配置变更

- `.env.example` 新增：
  - `ZTP_PLATFORM`（默认 `lstn`）
  - `ZTP_DHCP_RANGE_START`（默认 `192.168.100.151`，从 v3.1.0 的 `.200` 调整）
  - `ZTP_DHCP_RANGE_END`（默认 `192.168.100.190`，从 v3.1.0 的 `.250` 调整）
- `.env.example` 删除：
  - `ZTP_MGMT_IP`（autocfg.cfg 不再单独传 mgmt_ip，改由 jinja2 模板硬编码 `.101`）
  - `ZTP_MGMT_MASK`（autocfg.cfg 模板硬编码 `255.255.255.0`）
  - `ZTP_MGMT_GATEWAY`（autocfg.cfg 不写 `ip gateway`，v3.1.0 已证 T7064P15 不支持）
- 已部署用户：手动更新 `.env`（**BREAKING** —— DHCP 池范围变更 + 变量名变更）

### 影响范围

- **新增**：`docker/ztp-stack/tftp/autocfg.cfg.j2`（jinja2 通用模板 + 2 平台条件分支）
- **修改**：`docker/ztp-stack/entrypoint.sh`（jinja2 渲染 + ZTP_PLATFORM 路由）
- **修改**：`docker/ztp-stack/Dockerfile`（apk add jinja2-cli）
- **修改**：`docker/ztp-stack/dnsmasq.conf.template`（DHCP 池 .151-.190，**删** dhcp-host / dhcp-leasefile）
- **修改**：`docker-compose.dev.yml`（删除 `/var/lib/misc` volume 挂载，**不需要 lease 持久化**）
- **修改**：`.env.example`（新增 ZTP_PLATFORM，**删** ZTP_MGMT_IP/MASK/GATEWAY）
- **修改**：`docs/ztp-stack.md`（多平台验证 SOP + offset 50 跨池映射原理图）
- **修改**：`VERSION-ROADMAP.md`（v3.1.1 行状态更新）
- **修改**：`README.md`（v3.1.1 行状态更新）
- **零业务代码**：`backend/` / `frontend/`（本 change 不动）

---

## Open Questions

1. **H3C V7 `interface M-GigabitEthernet0/0/0 + ip address X X` 在 .5 R6555 / .26 V9850 是否支持？**
   - **T1 探针解决**（走 ops-toolkit `paramiko-batch-exec.sh`）
   - 不支持则备选：`ip address dhcp-alloc`（v3.1.0 决策 B 留下的）/ 备选命令
2. **.26 R7643P02 NETCONF 启用方式（SSH vs SOAP）？**
   - T1 探针 #6 验证
   - PRD V3.1.1 写 `netconf soap http enable`，但 .26 实际可能跟 S6850 一样支持 `netconf ssh server enable`
3. **.26 R7643P02 user-role 命名（network-admin vs level-15）？**
   - T1 探针 #7 验证
   - PRD V3.1.1 写 `level-15`，但 .26 实际可能跟 S6850 一样支持 `network-admin`
4. **.177 / .26 真机是否可达？**
   - `.177` 是完整 ZTP 主验证设备，必须先确认可达/可恢复
   - `.26` 是 EVE-NG 借用的 V9850/RSTN 适配性验证设备
   - `.5` 不跑完整 ZTP
5. **autocfg.cfg 中 sysname 来源？**
   - 固定 `{{ sysname }}` env var（v3.1.0 模式）
   - 或 DHCP option 12 hostname（dnsmasq 支持，但增加复杂度）
   - **当前决策**：固定 env var（简单）
6. **DHCP option 60 vendor-class 用于平台识别？**
   - 可选优化（让 dnsmasq 自动识别 LSTN / RSTN）
   - v3.1.1 不做（ZTP_PLATFORM env var 路由已够用）
