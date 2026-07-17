# v31-ztp-research — Design

> **状态**：调研阶段（**T1-T4 待执行，T5 待决策**）
> **目的**：评估 H3C V7 ZTP 可行性 + Controller 集成复杂度 + 给出 A/B/C 决策

---

## 1. H3C V7 ZTP 机制（T1 文档调研结论）

### 1.0 调研结论速览

**H3C 官方 VCF Fabric 自动部署支持**（[H3C S6805 & S6825 & S6850 & V9850 & S9820 Config Examples §73](https://www.h3c.com/en/d_202404/2113460_294551_0.htm)）：
- ✅ S6805 / S6825 / S6850 / V9850 / S9820 5 个平台官方支持 ZTP
- ✅ 软件版本要求：R6607+（覆盖 .26 R7643P02，但不覆盖 .5 R6555 / .177 T7064P15）
- ✅ ZTP 工作流：DHCP + TFTP + startup.cfg（plain text H3C config）

### 1.1 H3C Comware V7 ZTP 工作原理

H3C Comware V7 支持 **ZTP (Zero Touch Provisioning)** 自动化部署，核心流程：

```
[设备上电/重启]
       ↓
[无配置状态自动检测]
       ↓
[广播 DHCP DISCOVER]
       ↓
[DHCP server 回应 OFFER]
   - option 66 (TFTP server) 或 option 67 (bootfile-name)
   - option 150 (Cisco-style TFTP) 或自定义 option
       ↓
[设备从 TFTP / HTTP / FTP server 下载 startup.cfg]
       ↓
[设备应用 startup.cfg（覆盖默认空配置）]
       ↓
[auto-reboot + 启动到完整配置]
       ↓
[ZTP 完成，设备 SSH/NETCONF 可达]
```

### 1.2 H3C V7 ZTP 关键命令（待 T2 探针验证）

| 命令 | 作用 | 备注 |
|---|---|---|
| `display ztp status` | 查看当前 ZTP 状态 | 不依赖 ZTP 开启 |
| `display ztp history` | 查看 ZTP 历史 | 包含历次 ZTP 时间 / 文件源 / 结果 |
| `ztp enable` | 开启 ZTP | 设备下次重启触发 |
| `ztp disable` | 关闭 ZTP | |
| `ztp start` | 手动触发 ZTP | 不重启也能用 |
| `ztp reboot` | ZTP 完成后自动 reboot | 配合 `ztp enable` |
| `ztp workflow` | 配置 ZTP 工作流（高级）| H3C V7 Rxxxx+ 支持 |

### 1.3 startup.cfg 格式

H3C V7 startup.cfg 是 **plain text** H3C 配置命令（与 `display current-configuration` 输出格式一致），无 YAML/JSON 头。例如：

```
#
sysname vpc-leaf-01
#
interface GigabitEthernet0/0
 ip address 192.168.100.5 255.255.255.0
#
local-user admin class manage
 password hash $h$6$...  (或 simple 形式，但 security 最佳实践用 hash)
 authorization-attribute user-role network-admin
 service-type ssh terminal
#
ssh server enable
ssh server port 22
#
netconf ssh server enable
#
return
```

### 1.4 平台支持差异（**T1 + T2 待验**）

| 平台 | 设备 | 调研重点 |
|---|---|---|
| LSTN 老芯片 | S6850 / S6850-56HF（.5 / .177）| ZTP 命令是否可用？startup.cfg 传输支持 TFTP 还是仅 HTTP？|
| RSTN 新芯片 | V9850（.26）| 同上，与 LSTN 是否一致？|

### 1.5 已知风险

按 user memory + 已知约束：
- H3C V7 SSH **不支持 shell sessions**（v2.4 已验）→ ZTP 文件传输不能用 SSH 协议
- H3C V7 S6850 默认禁 SCP subsystem（v2.6.2 已验）→ 同样适用于文件传输
- **TFTP / HTTP / FTP 才是 H3C V7 ZTP 的合法文件传输通道**（需 T2 探针确认）
- .26 设备管理 IP `192.168.100.26`，避开作为 ZTP 客户端的目标网段

### 1.6 H3C V7 "自动配置"功能（**T1 新发现**，不依赖 VCF ZTP 命令）

> **用户 2026-07-17 03:35 提供**：[知乎链接](https://zhuanlan.zhihu.com/p/19291735913) 提示 H3C V7 还有更基础的 ZTP 路径
> **官方文档**：[H3C S5560-EI 系列基础配置指导 - Release 1312-6W101 §13 自动配置](https://www.h3c.com/cn/d_201912/1252406_30005_0.htm)

**H3C V7 自动配置（autocfg）vs VCF ZTP 对比**：

| 维度 | VCF ZTP（§1.1）| H3C V7 自动配置（本节）|
|---|---|---|
| 命令关键字 | `ztp enable` / `ztp start` | **无设备侧命令**（空配置启动自动触发）|
| 软件版本要求 | R6607+ | **所有 H3C V7 都支持**（不依赖 R6607+）|
| 触发条件 | 需 `ztp enable` | **空配置启动默认行为** |
| 配置文件 | `startup.cfg` | `autocfg.cfg` / `autocfg.tcl` / `autocfg.py`（按优先级）|
| 传输协议 | TFTP | TFTP / HTTP（HTTP 支持 Tcl/Python 脚本）|
| DHCP option | 66/67 | `bootfile-name url`（HTTP）或 `tftp-server ip` + 主机名文件（network.cfg）|
| 文档支持 | VCF Fabric §73（R6607+）| 基础配置指导 §13（**所有 V7**）|

**H3C V7 自动配置工作流**：
```
[设备上电/重启]
       ↓
[空配置状态自动检测]
       ↓
[检查根目录是否存在 autocfg.py / autocfg.tcl / autocfg.cfg]
       ↓ (不存在)
[广播 DHCP DISCOVER]
       ↓
[DHCP server 回应 OFFER]
   - 普通 IP + 路由
   - option 66 (TFTP server) 或 option 67 (bootfile-name)
   - 或 option 150 / 67 携带 HTTP URL
       ↓
[设备从 TFTP / HTTP server 下载 autocfg.cfg / .tcl / .py]
       ↓
[设备应用配置（覆盖默认空配置）]
       ↓
[auto-reboot + 启动到完整配置]
       ↓
[ZTP 完成，设备 SSH/NETCONF 可达]
```

**关键发现**：
- H3C V7 自动配置**不依赖任何 enable 命令**，是设备空配置启动的**默认行为**
- 这意味着本项目 3 设备（.5 R6555 / .26 R7643P02 / .177 T7064P15）理论上**都支持** ZTP（不依赖 R6607+）
- 之前 T2 探针只测了 VCF ZTP 命令，**未测自动配置**（设备侧无命令可测）
- Controller 侧需要 DHCP + TFTP/HTTP 服务（独立 ztp-server 容器，详见 §2.5）

**T1 结论修正**：
- 原结论："H3C 官方 VCF ZTP 仅 R6607+ 支持，3 设备多数不在范围"
- 修正后："H3C V7 自动配置（autocfg.cfg）**不依赖 R6607+**，3 设备理论上都支持"
- 决策 C 重置 → 重做 T3-T5（独立 ztp-server 容器 + .177 真机验证）

## 2. Controller 集成方案（待 T3 + T4 设计）

### 2.1 整体架构（候选 A 方案）

```
┌─────────────────┐         DHCP option 66/67         ┌──────────────┐
│  H3C V7 设备    │ ───────────────────────────────→ │  Controller  │
│  (无配置状态)   │                                     │  (新增 ztp 容器) │
│                 │ ←─────── TFTP/HTTP startup.cfg ── │              │
│                 │                                     │  ┌─────────┐ │
│                 │                                     │  │ dnsmasq │ │  DHCP server
│                 │                                     │  └─────────┘ │
│                 │                                     │  ┌─────────┐ │
│                 │                                     │  │  tftpd  │ │  TFTP server
│                 │                                     │  └─────────┘ │
│                 │                                     │  ┌─────────┐ │
│                 │                                     │  │ jinja2  │ │  startup.cfg 渲染
│                 │                                     │  └─────────┘ │
└─────────────────┘                                     └──────────────┘
                                                                ↓
                                                       ┌─────────────────┐
                                                       │  POST /api/devices │
                                                       │  (ctrl 容器自动纳管) │
                                                       └─────────────────┘
```

### 2.2 候选方案对比

| 维度 | A. 全 PoC | B. 半 PoC | C. 不投入 |
|---|---|---|---|
| **新增容器** | `ztp`（dnsmasq + tftpd + 模板引擎）| 复用现有 ops-toolkit 跑 tftpd | 无 |
| **DHCP server** | dnsmasq（轻量）| 现有路由器 | 无 |
| **文件 server** | tftpd / atftpd | tftpd | 无 |
| **startup.cfg 模板** | Jinja2 模板 + env vars | 手动 1 份固定文件 | 无 |
| **设备纳管** | ZTP 完成后自动调用 ctrl API | 手动 `POST /api/devices` | 手动全流程 |
| **新代码量** | ~500-1000 行 | ~200 行 | 0 |
| **新运维成本** | 1 个新容器 | 0（复用 ops-toolkit）| 0 |
| **T2 探针** | 必须 | 必须 | 必须 |
| **T3 真机验证** | 必须 | 必须 | 不需要 |
| **决策依赖** | T1+T2+T3 全过 | T1+T2 过即可 | 任意一步失败 |

### 2.3 startup.cfg 模板（草案，待 T4 设计）

```jinja2
#
sysname {{ hostname }}
#
vlan {{ mgmt_vlan }}
#
interface Vlan-interface{{ mgmt_vlan }}
 ip address {{ mgmt_ip }} {{ mgmt_mask }}
#
interface GigabitEthernet0/0
 port link-mode bridge
 port access vlan {{ mgmt_vlan }}
#
local-user {{ username }} class manage
 password simple {{ password }}  # 走 SSH 22 后由 controller 立即 push hash 版本
 authorization-attribute user-role network-admin
 service-type ssh terminal
#
ssh server enable
ssh server port 22
#
netconf ssh server enable
#
acl number 2000
 rule 0 permit source {{ admin_subnet }} 0.0.0.255
#
save force
return
```

**安全考量**（T4 任务）：
- `password simple` 形如明文在 startup.cfg 传输——TFTP 协议是明文，**必须**改用 HTTP/FTP 协议
- 或 DHCP option 67 指向一个 HTTPS URL（H3C V7 是否支持 HTTPS 文件传输？需 T1 查文档 + T2 探针）
- **推荐**：HTTP 协议 + `password hash`（H3C V7 支持 `password hash` 命令存哈希）+ 内置 default username 不可登录

### 2.4 设备纳管（ZTP 完成后）

**3 个候选**：
- a. 设备启动后主动 callback controller（HTTP POST /api/devices/auto-register）—— **需设备支持**
- b. controller 周期扫描网段（基于已知 IP 段 + SSH 22/NETCONF 830 探测）—— **侵入小，工作量大**
- c. 维持手动纳管（ZTP 只做基础配置，纳管仍走 `POST /api/devices`）—— **最简单**

**T4 任务**：根据 T1+T2 调研给出推荐。

### 2.5 独立 ztp-server 容器（**T3 新方案**，用户 2026-07-17 03:50 指示）

> **用户原话**："如果这个我也没说 ztp 这个能力，ztp 这个能力必须得 ops 啊，不行你就再洗一个新的容器呗...你既然要改网络模式的话，那就开新容器"

**目标**：解决 T4 真机验证的 2 个硬阻塞：
1. ops-toolkit 容器网络在 docker bridge（172.x），不在 .177 物理网段（192.168.100.0/24），L2 DHCP 广播不通
2. ops-toolkit 容器未预装 dnsmasq / tftpd

**架构**：

```
┌────────────────────────────────────────────────────┐
│ docker-compose.dev.yml (新增 ztp-server 服务)        │
│                                                     │
│  ┌──────────────────────────────────────────┐      │
│  │ ztp-server 容器 (alpine:3.20)            │      │
│  │   network_mode: host  ← 共享宿主机网络栈 │      │
│  │                                          │      │
│  │  ┌────────────────────────────────────┐  │      │
│  │  │ dnsmasq 进程（单进程二合一）         │  │      │
│  │  │  - DHCP server: 67/UDP              │  │      │
│  │  │  - TFTP server: 69/UDP              │  │      │
│  │  └────────────────────────────────────┘  │      │
│  │                                          │      │
│  │  /etc/dnsmasq.conf                       │      │
│  │  /var/tftp/autocfg.cfg  ← mount 挂载    │      │
│  └──────────────────────────────────────────┘      │
│         ↓ 共享宿主机 eth0 (192.168.100.x)         │
└────────────────────────────────────────────────────┘
         ↓ DHCP L2 广播 (192.168.100.0/24)
         ↓ TFTP GET autocfg.cfg
┌─────────────────────────┐
│ H3C V7 设备 (.177)      │
│ - 空配置启动             │
│ - DHCP discover         │
│ - 拉 autocfg.cfg         │
│ - 应用配置 + reboot      │
└─────────────────────────┘
```

**关键设计**：
- **image**: `alpine:3.20`（轻量，约 7MB + dnsmasq ~200KB）
- **network_mode**: `host`（核心 —— 共享宿主机网络栈，能接收 .177 物理网段 L2 广播）
- **profiles**: `ops`（按需启动，跟 ops-toolkit 一致，不常驻）
- **command**: `dnsmasq -k -C /etc/dnsmasq.conf -d`（`-k` 不 fork，`-d` debug log）
- **env vars**:
  - `ZTP_HOST_IP`（宿主机 IP，dnsmasq 启动时注入到 dhcp-option=66）
  - `ZTP_ADMIN_USER` / `ZTP_ADMIN_PASS`（autocfg.cfg 模板占位符，凭据走 .env）

**dnsmasq.conf 模板**：
```conf
# DHCP server
dhcp-range=192.168.100.200,192.168.100.250,12h
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
```

**autocfg.cfg 模板**（最小可用配置）：
```h3c
#
# H3C V7 自动配置 - autocfg.cfg
# 生成时间: {{ZTP_DATE}}
# 用途: 新设备首次上线基础配置
#

sysname {{ZTP_SYSNAME}}

# 带外管理
vlan 1
interface Vlan-interface1
 ip address {{ZTP_MGMT_IP}} 255.255.255.0
 quit

# SSH 服务
ssh server enable
ssh server authentication-timeout 300
local-user {{ZTP_ADMIN_USER}} class manage
 password simple {{ZTP_ADMIN_PASS}}
 service-type ssh terminal
 authorization-attribute user-role network-admin
quit
user-interface vty 0 15
 authentication-mode scheme
 protocol inbound ssh
quit

# NETCONF 服务
netconf ssh server enable

# 保存
save force
```

**与 ops-toolkit 的关系**：
- **不**修改 ops-toolkit（按用户指示"开新容器"）
- ops-toolkit 保持"开箱即用"原则（不预装 dnsmasq/tftpd）
- ztp-server 独立管理，按需启动

**T3 验证步骤**：
1. `docker compose -f docker-compose.dev.yml --profile ops build ztp-server` 构建成功
2. `dnsmasq --test -C /etc/dnsmasq.conf` 配置语法通过
3. 容器启动后宿主机 `ss -uln` 看到 `*:67` + `*:69` 监听
4. 在宿主机上 `tcpdump -i eth0 -n port 67 or port 69` 验证 L2 广播可达

**T4 真机验证流程**（详见 `tasks.md §T4`）：
1. 启动 ztp-server 容器
2. 备份 .177 当前 startup.cfg（用 paramiko 绕开 scp 兼容问题）
3. reset .177 saved-configuration
4. reboot .177
5. 观察 60s 内 SSH 22 + NETCONF 830 是否自动起
6. 验证 120s 后 .177 配置是否含 autocfg.cfg 内容
7. 失败立即 restore 备份

## 3. 可行性决策（T5 输出）

### 3.1 决策矩阵

| 探针结果 | 推荐决策 |
|---|---|
| T1 文档证实 V7 ZTP 支持 + T2 探针命令全部可达 | A 或 B（看用户预算）|
| T1 文档证实 V7 ZTP 支持 + T2 探针部分失败（如仅 .5 支持，.26 不支持）| B |
| T1 文档证实 V7 ZTP 支持 + T3 真机验证失败（如 startup.cfg 不能 boot）| C |
| T1 文档无 V7 ZTP 资料 / T2 探针全部失败 | C（强制）|

### 3.2 决策回退条件（按 user 原话）

- T2 探针失败 ≥ 3 次 → 立即停手
- T3 真机验证失败 ≥ 1 次 → 立即停手
- 工作量 > 2 个 session（用户预算外）→ 走 B
- 用户主动选择 C → 直接 archive + 回退 v3.1 计划

### 3.3 决策报告模板

T5 任务完成后，本节填入：

```markdown
### 3.4 最终决策（YYYY-MM-DD）

- **选项**：A / B / C
- **理由**：...
- **下一步**：...
- **回退条件**：...
```

> **决策重置**（2026-07-17）：原"决策 C"基于"3 设备 VCF ZTP 命令 Unrecognized"得出，但 H3C V7 还有更基础的"自动配置"功能（autocfg.cfg）—— **不依赖 VCF ZTP 命令**，空配置启动自动触发。决策 C 不再适用，重做 T3-T5。
>
> 用户 2026-07-17 03:50 指示："开新容器做 ZTP server" → 解决 Controller 侧基建缺失。
>
> **决策重置**（2026-07-18，T4 实证后）：autocfg.cfg 模板**几乎全工作**（sysname / local-user / netconf / ssh / save force 都生效），仅 Vlan1 IP 那行 Unrecognized。决策从 C 调整为 **B（精简 ZTP）**：保留 ztp-server 容器 + autocfg.cfg 模板精简（删 IP 配置 + 加 `password-control login-password-change disable`）。

### 3.4 最终决策（2026-07-18）

- **选项**：**B**（精简 ZTP）
- **理由**：
  1. ✅ **autocfg 机制完全工作**：T4 实证 attempt 2 完整链路通（DHCP → TFTP → 执行 → "successfully completed"）
  2. ✅ **autocfg.cfg 模板大部分生效**：sysname / local-user / ssh / netconf / save force 全工作（详见 [notes.md §5.2](../v31-ztp-research/notes.md)）
  3. ⚠️ **唯一不生效**：Vlan1 IP 配置行（`ip gateway` 在 T7064P15 平台不支持，Vlan1 也因无物理接口 up 而 down）
  4. ⚠️ **副作用**：H3C V7 默认首次 SSH 登录强制改密，ZTP 配的密码不能直接纳管
  5. ✅ **autocfg 机制自动处理 OOB 口 + DHCP client**：attempt 2 自动 enable M-GE 0/0/0 + DHCP 拿 IP，**autocfg.cfg 模板不需要管 IP**
- **决策 B 含义**：
  - ✅ 保留 `ztp-server` 容器（DHCP + TFTP 基建完整）
  - ✅ 简化 `autocfg.cfg` 模板：删 IP 配置 + 加 `password-control login-password-change disable` + 加 sysname / SSH / NETCONF / save
  - ✅ 设备 IP 由 autocfg 机制 OOB DHCP 自动拿（pool .200-.250, lease 12h）
  - ⏳ 远期 v3.1.1 才考虑适配多平台（.5 / .26 / .177 各一份模板）+ 适配商用 R6607+ 设备（届时可配静态 IP）
  - ⏳ 远期 v3.1.2 才做"controller 主动 SSH 纳管 + 推业务 IP"
  - ⏳ 远期 v3.1.3 才做"资产自动可见"
- **下一步**：
  1. ✅ Commit 3：T4 真机验证成功 + autocfg.cfg 模板修订（精简版 + 关改密）
  2. ⏳ Commit 4：T5 决策 B + archive + 同步 3 处 A 类文档
  3. ⏳ 等 user 启动后续 v3.1.1 change（ztp 落地 + 多平台适配）
- **回退条件**：
  - v3.1.1 真机验证失败（多平台不兼容）→ 决策 C 重新评估
  - v3.1.1 投入产出比不划算（autocfg.cfg 模板适配成本高）→ 决策 C
  - user 主动选择 C → 直接 archive 后续 change 计划

## 4. 风险与边界

### 4.1 业务边界（user 明确）

按 user 原话 2026-07-17 02:13：
- ✅ ZTP **只做基础配置**：SSH 22 + 带外 IP + NETCONF 830 + 凭据 + 基础路由/ACL
- ❌ ZTP **不做业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ ZTP **不做前端界面**：v3.1 仅 backend PoC
- ❌ ZTP **不做 DHCP 高可用**：单 dnsmasq 容错

### 4.2 安全风险

- startup.cfg 含明文密码 → **必须**走 HTTP/HTTPS（**不**用 TFTP 明文）
- 或预共享 `password hash` 模板（设备 reset 后 hash 不会变，但用户密码仍然明文存于 startup.cfg）
- 推荐：startup.cfg 含 `password simple` 临时密码，ZTP 完成后 controller 立即 SSH 推 `password hash` 覆盖
- **DHCP 信任边界**：仅在受控局域网启用 ZTP，避免外部 DHCP 干扰
- **设备序列号绑定**（option 82 或自定义 option）：可选，仅 B 方案以上实施

### 4.3 不与 v3.0 冲突

- v3.0 是"已纳管设备的 SDN 业务"（VPC/端口绑定）
- v3.1 是"设备首次上线"（ZTP）
- 两者**正交**，不互相依赖
- v3.1 完成后，新设备流程 = ZTP 上线 → ctrl 自动纳管 → 进入 v3.0 SDN 业务

## 5. 后续 change 规划（视 T5 决策结果）

| 决策 | 后续 change |
|---|---|
| A | v3.1.1 ztp-poc-implementation（实现 + .177 验证）|
| B | v3.1.1 ztp-template-only（仅模板 + tftpd 复用 ops-toolkit）|
| C | v3.1 计划回退 / 留作 v3.x 远期评估 |

## 6. OpenSpec 合规

- [ ] 调研笔记在 `notes.md`（archive 时删除）
- [ ] 真机测试结果在 `tasks.md` 各 task
- [ ] 决策报告在 `design.md §3.4`
- [ ] 不写业务代码（除 startup.cfg 模板）
- [ ] 探针全部走 ops-toolkit 容器
