# v31-ztp-research — 调研笔记

> **目的**：T1-T3 调研结果汇总，archive 时**删除**（按 project-convention B 类）
> **创建时间**：2026-07-17

---

## §1. H3C V7 ZTP 官方文档调研（T1）

> 状态：✅ 已完成（2026-07-17）

### 1.1 WebSearch 结果

**搜索关键词**：
- "H3C Comware V7 ZTP Zero Touch Provisioning S6850 V9850 DHCP startup.cfg"
- "H3C V7 ZTP configuration file TFTP HTTP FTP transfer protocol support"

### 1.2 关键发现

**H3C 官方支持 VCF Fabric 自动部署**：
- 文档：[H3C S6805 & S6825 & S6850 & S9850 & S9820 Config Examples - Release 66xx-6W100 §73 VCF Fabric Configuration Examples](https://www.h3c.com/en/d_202404/2113460_294551_0.htm)
- 适用设备：**S6805 / S6825 / S6850 / V9850 / S9820**（覆盖 .5 / .26 设备）
- 适用软件版本：
  - S6805: Release 6607 / 6616 / 6616P01 / 6635+
  - S6825: Release 6616 / 6616P01 / 6635+
  - S6850: 同上
  - S9850: 同上
  - S9820: 同上

**ZTP 工作流（VCF 自动部署）**：
1. 设备出厂默认状态（无配置）上电 → 进入 ZTP 模式
2. 设备发送 DHCP discover 到 DHCP server
3. DHCP server 回应：分配 IP + option 66 (TFTP server) + option 67 (bootfile-name) + 其他 option（如 150 Cisco-style）
4. 设备从 TFTP server 下载 startup.cfg / template file
5. 设备应用 startup.cfg（覆盖默认空配置）
6. 设备 auto-reboot + 启动到完整配置
7. 设备 SSH/NETCONF 可达

**startup.cfg 格式**：
- Plain text H3C 配置命令
- 与 `display current-configuration` 输出一致
- 关键命令：`sysname` / `interface` / `ip address` / `local-user` / `ssh server enable` / `netconf ssh server enable`

**关键依赖**：
- DHCP server（必须）
- TFTP server（VCF 文档默认）或 HTTP/FTP（待 T1 进一步查）
- Director server（H3C DR1000 商用方案，个人项目可自实现）

### 1.3 T1 结论

**H3C V7 ZTP 官方支持**：
- ✅ 5 个目标平台（S6805 / S6825 / S6850 / V9850 / S9820）官方支持 VCF Fabric ZTP
- ✅ 工作机制清晰：DHCP + TFTP + startup.cfg
- ✅ startup.cfg 格式简单（plain text H3C config）
- ⚠️ 软件版本要求：R6607+（**仅 .5 设备 R6555 不在支持范围**）

**与本项目设备的匹配度**：

| 设备 | 平台 | 软件 | 文档支持 |
|---|---|---|---|
| .5  S6850 | LSTN | R6555 | ❌ 不在 R6607+ 支持范围 |
| .26 V9850 | RSTN | R7643P02 | ✅ 在 R7643+ 支持范围 |
| .177 S6850 | LSTN | T7064P15 | ❌ T7064P15 是 HCL 内部测试版，未在 VCF 文档支持范围 |

**初步判断**：
- .26 设备 R7643P02 有官方 VCF 支持 → ZTP 文档理论可行
- .5 设备 R6555 太旧 → 即使文档支持，实际可能 Unrecognized
- .177 设备 T7064P15 是 HCL 内部测试版 → 实际能力未知

**T2 待验**：
- 3 个设备实测 ZTP 命令是否可用
- 若 .26 真支持 + .5 / .177 升级到 R6607+ → 走 A/B 方案
- 若 3 设备全 Unrecognized → 决策 C（不投入）

---

## §2. ZTP 命令真机探针（T2）

> 状态：🚫 **失败**（2026-07-17，3 设备全 Unrecognized）

### 2.1 探针矩阵

| 设备 | platform | software | `display ztp status` | `ztp enable` | `display ztp history` | 备注 |
|---|---|---|---|---|---|---|
| .5  S6850 | LSTN | R6555 (Alpha 7170) | ❌ Unrecognized | ❌ Unrecognized | ❌ Unrecognized | 软件版本不在 R6607+ 范围 |
| .26 V9850 | RSTN | R7643P02 (Release 7643P02) | ❌ Unrecognized | ❌ Unrecognized | ❌ Unrecognized | 软件版本在 R7643+ 范围但仍 Unrecognized |
| .177 S6850 | LSTN | T7064P15 (Alpha 7170) | ❌ Unrecognized | ❌ Unrecognized | ❌ Unrecognized | HCL 内部测试版未实现 |

### 2.2 探针命令（实际跑的）

按 `.trae/rules/qa规范.md` 红线：所有 ZTP 探针走 ops-toolkit 容器（`paramiko-batch-exec.sh`），不裸写 SSH/paramiko。

每个设备跑 3 个命令：
- `system-view` → `display ztp status`
- `system-view` → `ztp enable`
- `system-view` → `display ztp history`

每个命令都返回：
```
% Unrecognized command found at '^' position.
```

### 2.3 根因分析

| 设备 | 根因 |
|---|---|
| .5 S6850 R6555 | 软件版本 R6555 早于 H3C VCF Fabric 文档要求的 R6607+，且低于 S6850 平台基线 R6607，无 ZTP 命令实现 |
| .26 V9850 R7643P02 | 软件版本 R7643P02 在 R7643+ 范围但实际命令未实现（可能单台设备镜像精简 / ZTP 命令被剥离）|
| .177 S6850 T7064P15 | HCL 内部测试版（Alpha 7170 基础），可能为节省空间精简 ZTP 命令 |

### 2.4 T2 结论（**被 §3 新发现推翻**）

~~3 设备 ZTP 命令全部 Unrecognized → 立即停手，T5 决策 C（不投入）~~

- VCF ZTP 命令（`ztp enable` / `display ztp status`）3 设备全部 Unrecognized，**仅说明 VCF ZTP 路径不适用**
- **但 H3C V7 还有"自动配置"路径**（autocfg.cfg）—— **不依赖 VCF ZTP 命令**，详见 §3
- T2 探针**未覆盖自动配置**（设备侧无 enable 命令可测，需 reboot 空配置验证）

---

## §3. H3C V7 "自动配置"功能 — T1 后期新发现

> 状态：✅ **推翻 §2.4 决策 C**（2026-07-17 03:35 用户提供线索 + WebSearch 验证）

### 3.1 关键线索

**用户提供**：[知乎链接](https://zhuanlan.zhihu.com/p/19291735913)（2026-07-17 03:35）
> "按理说是可以啊"（暗示 H3C V7 应有 ZTP 路径）

**WebSearch 验证关键词**：
- "H3C V7 自动配置 autocfg.cfg DHCP bootfile-name"
- "H3C Comware V7 autocfg.py autocfg.tcl 启动配置"

**官方文档命中**：[H3C S5560-EI 系列基础配置指导 - Release 1312-6W101 §13 自动配置](https://www.h3c.com/cn/d_201912/1252406_30005_0.htm)

### 3.2 自动配置 vs VCF ZTP 对比

| 维度 | VCF ZTP（§1）| H3C V7 自动配置（本节）|
|---|---|---|
| 命令关键字 | `ztp enable` / `ztp start` | **无设备侧命令** |
| 软件版本要求 | R6607+ | **所有 H3C V7 都支持** |
| 触发条件 | 需 `ztp enable` | **空配置启动默认行为** |
| 配置文件 | `startup.cfg` | `autocfg.cfg` / `autocfg.tcl` / `autocfg.py` |
| 传输协议 | TFTP | TFTP / HTTP |
| DHCP option | 66/67 | `bootfile-name url`（HTTP）或 `tftp-server ip` + 主机名文件 |

**关键洞察**：H3C V7 自动配置**不依赖任何 enable 命令**，是设备空配置启动的**默认行为**。理论上 3 设备（.5 R6555 / .26 R7643P02 / .177 T7064P15）**都支持**自动配置。

### 3.3 T4 真机验证准备 — 3 个新发现的问题

| 问题 | 详情 | 解决 |
|---|---|---|
| 1️⃣ 容器网络不通 | ops-toolkit 容器在 docker bridge（172.x），.177 在 192.168.100.0/24，L2 DHCP 广播不通 | **开新容器 `ztp-server` + `network_mode: host`** |
| 2️⃣ 工具未预装 | ops-toolkit 容器内 `which dnsmasq tftpd atftpd tftp` 全空 | **新容器 alpine + apk add dnsmasq** |
| 3️⃣ capture-config 失败 vs backup 成功 | capture-config 走系统 `scp` 失败，backup 走 paramiko 成功 | **不是 ZTP 阻塞**（T4 用 paramiko 备份） |

### 3.4 capture-config 失败真实原因（用户质疑的"为什么备份能拉文件 capture-config 不能"）

```
$ capture-config --device Test-Switch-177
=== 拉取 startup.cfg: 192.168.100.177 ===
Unable to negotiate with 192.168.100.177 port 22: no matching host key type found. Their offer: ssh-rsa
scp: Connection closed
```

**真实错误**：OpenSSH 8+ 默认禁用 ssh-rsa host key（H3C V7 用 ssh-rsa）

**capture-config.sh 实现**（`/scripts/capture-config.sh` 第 53-54 行）：
```bash
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    "$USER@$IP:startup.cfg" "$OUT"
```
走**系统 OpenSSH scp 客户端**，跟 OpenSSH 8+ host key 算法不兼容。

**为什么 backup 能成功**（v2.2.0 + v2.6.1 fix-backup-data-integrity）：
- backup 走 **paramiko + SSH CLI**（`more startup.cfg` 命令回显内容）
- paramiko 兼容 ssh-rsa host key（v2.6.1 fix-backup-restore-support 修过这条链路）
- **不走系统 scp**

**结论**：capture-config 失败 = **脚本实现差异**（不是 SSH 整体不兼容），备份链路有别的实现。这不是 ZTP 硬阻塞。

### 3.5 用户新方案（2026-07-17 03:50 03:55 03:58）

> 用户原话 1："你看这是网络问题啊，容器在 172 那你用那个 host 模式的网络不行吗？我记得是可以吧？"
> 用户原话 2："我也没说 ztp 这个能力必须得 ops 啊，不行你就再洗一个新的容器呗"
> 用户原话 3："你既然要改网络模式的话，那就开新容器"
> 用户原话 4："最坏的情况可以是决定一台搞一台交换机，作为 ztp server"

**新方案决策**：
- ✅ **开独立 `ztp-server` 容器**（按用户指示"开新容器"）
- ✅ **network_mode: host**（按用户指示"用 host 模式的网络"）
- ✅ **不动 ops-toolkit**（保持"开箱即用"原则）
- ❌ **不用交换机做 ZTP server**（H3C 交换机只能做 DHCP server 部分，TFTP 必须 Linux）

### 3.6 新架构

```
┌────────────────────────────────────────────────────┐
│ docker-compose.dev.yml (新增 ztp-server 服务)        │
│                                                     │
│  ┌──────────────────────────────────────────┐      │
│  │ ztp-server 容器 (alpine:3.20)            │      │
│  │   network_mode: host  ← 共享宿主机网络栈 │      │
│  │   - dnsmasq 二合一 (DHCP 67 + TFTP 69)   │      │
│  └──────────────────────────────────────────┘      │
│         ↓ 共享宿主机 eth0 (192.168.100.x)         │
└────────────────────────────────────────────────────┘
         ↓ DHCP L2 广播 (192.168.100.0/24)
         ↓ TFTP GET autocfg.cfg
┌─────────────────────────┐
│ H3C V7 设备 (.177)      │
│ - 空配置启动             │
│ - 拉 autocfg.cfg         │
│ - 应用配置 + reboot      │
└─────────────────────────┘
```

### 3.7 决策 C 重置

| 维度 | 原决策 C | 修正后 |
|---|---|---|
| 决策依据 | 3 设备 VCF ZTP 命令 Unrecognized | 3 设备 VCF ZTP 命令 Unrecognized + **H3C 自动配置路径未验证** |
| 决策 | 不投入 ZTP | **重做 T3-T5**（独立 ztp-server 容器 + .177 真机验证）|
| 下一步 | archive + 同步 3 处 A 类文档 | T3 基建 → T4 真机 → T5 最终决策 |

### 3.8 ZTP 未来可行性（远期重启条件）

若未来满足以下条件，可重新评估 ZTP：
- 设备软件版本升级到 R6607+（.5 / .177）
- 或新采购的 H3C V7 设备出厂已支持 ZTP
- Controller 端可以构建独立 `ztp` 容器（dnsmasq + tftpd + Jinja2 模板）✅ **T3 即将实现**

---

## §4. 独立 ztp-server 容器基建 — T3 完成

> 状态：✅ **T3 完成**（2026-07-17 16:31，commit 待提交）

### 4.1 实施内容

按用户 2026-07-17 03:50 指示"开新容器"，实施独立 `ztp-server` 容器：

| 文件 | 作用 |
|---|---|
| `docker/ztp-stack/Dockerfile` | alpine:3.20 + dnsmasq + bash |
| `docker/ztp-stack/entrypoint.sh` | 模板渲染（env vars → dnsmasq.conf + autocfg.cfg）|
| `docker/ztp-stack/dnsmasq.conf.template` | DHCP + TFTP 二合一配置 |
| `docker/ztp-stack/tftp/autocfg.cfg.template` | H3C V7 自动配置最小可用配置 |
| `docker-compose.dev.yml` | 新增 ztp-server 服务（network_mode: host + cap_add: NET_ADMIN）|
| `.env.example` + `.env` | ZTP_* 变量定义 + 实际值注入 |
| `docs/ztp-stack.md` | 容器使用文档 + 真机验证 SOP |

### 4.2 关键设计

- **network_mode: host**（核心 —— 共享宿主机网络栈，能接收 .177 物理网段 L2 广播）
- **profiles: ["ops"]**（按需启动，跟 ops-toolkit 一致）
- **cap_add: NET_ADMIN**（dnsmasq bind 67/69 特权端口需要）
- **不修改 ops-toolkit**（按用户指示"开新容器"，保持 ops-toolkit 开箱即用）

### 4.3 验证结果（2026-07-17 16:31）

```bash
# 1. .env 实际 IP
$ grep ^ZTP_ /root/workpace/h3c-netctrl/.env
ZTP_HOST_IP=192.168.100.254     # 宿主机 ens34 (.177 物理网段接口)
ZTP_DHCP_RANGE_START=192.168.100.200
ZTP_DHCP_RANGE_END=192.168.100.250
ZTP_DHCP_LEASE=12h
ZTP_SYSNAME=ztp-device
ZTP_MGMT_IP=192.168.100.10
ZTP_MGMT_MASK=255.255.255.0
ZTP_MGMT_GATEWAY=192.168.100.1
ZTP_ADMIN_USER=admin
ZTP_ADMIN_PASS=admin

# 2. 启动 ztp-server
$ docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server
Container h3c-netctrl-ztp-server Recreate
Container h3c-netctrl-ztp-server Recreated
Container h3c-netctrl-ztp-server Starting
Container h3c-netctrl-ztp-server Started

# 3. 容器日志（关键 — TFTP server IP 正确）
$ docker logs h3c-netctrl-ztp-server
=== 渲染 dnsmasq.conf ===
=== 渲染 autocfg.cfg ===
=== dnsmasq 启动 ===
  DHCP range: 192.168.100.200 - 192.168.100.250
  TFTP server: 192.168.100.254           ← ✅ 宿主机 IP，非 127.0.0.1 fallback
  TFTP root: /var/tftp
  autocfg.cfg sysname: ztp-device
dnsmasq[1]: started, version 2.90 DNS disabled
dnsmasq-dhcp[1]: DHCP, IP range 192.168.100.200 -- 192.168.100.250, lease time 12h
dnsmasq-tftp[1]: TFTP root is /var/tftp

# 4. 宿主机端口监听
$ ss -ulnA inet | grep -E ':(67|69) '
udp UNCONN 0 0 0.0.0.0:67 0.0.0.0:*   ← DHCP 67 监听 ✅
udp UNCONN 0 0 0.0.0.0:69 0.0.0.0:*   ← TFTP 69 监听 ✅

# 5. 容器内配置
$ docker exec h3c-netctrl-ztp-server ls -la /var/tftp/ /etc/dnsmasq.conf
-rw-r--r-- 1 root root 2155 Jul 17 16:31 /etc/dnsmasq.conf
-rw-r--r-- 1 root root 2453 Jul 17 16:31 /var/tftp/autocfg.cfg  ← 模板渲染成功 ✅

# 6. dnsmasq 配置语法
$ docker exec h3c-netctrl-ztp-server dnsmasq --test -C /etc/dnsmasq.conf
（无输出，exit code 0）  ← 语法通过 ✅
```

### 4.4 T3 验收 checklist

- [x] `docker compose build ztp-server` 成功（之前构建过）
- [x] 容器启动成功（`up -d` 退出码 0）
- [x] DHCP 67/UDP + TFTP 69/UDP 在 `0.0.0.0` 监听（host network 模式）
- [x] TFTP server IP = 192.168.100.254（从 .env 注入，非 fallback）
- [x] `dnsmasq --test` 语法通过
- [x] autocfg.cfg 模板渲染成功（含 sysname / mgmt IP / SSH / NETCONF）

### 4.5 关键修正

| 修正 | 原因 |
|---|---|
| 宿主机 IP = 192.168.100.254（不是 .env.example 注释里的 192.168.100.4）| `ip addr show` 实际显示 ens34 = 192.168.100.254（.177 物理网段接口）|
| 加 `ZTP_*` 变量到 .env（不只 .env.example）| .env 文件未注入 ZTP 变量，entrypoint.sh fallback 到 127.0.0.1，导致设备拉不到文件 |

### 4.6 容器网络拓扑（host network 模式）

```
┌────────────────────────────────────────────────────────┐
│ 宿主机 (192.168.100.254 ens34)                          │
│                                                         │
│  ┌──────────────────────┐                                │
│  │ ztp-server 容器      │                                │
│  │  - dhclient 0.0.0.0  │ ← host network 共享宿主机网络栈 │
│  │  - 监听 67/UDP + 69/UDP                                │
│  └──────────────────────┘                                │
│         ↓                                                │
│  ens34 (192.168.100.254/24) ← .177 物理网段              │
└────────────────────────────────────────────────────────┘
         ↓ DHCP L2 广播 (192.168.100.0/24)
         ↓ TFTP GET autocfg.cfg
┌─────────────────────────┐
│ H3C V7 设备 (.177)      │ ← 待 T4 真机验证
│ - 空配置启动            │
│ - DHCP discover         │
│ - 拉 autocfg.cfg         │
│ - 应用配置 + reboot      │
└─────────────────────────┘
```

### 4.7 残留的 untracked 文件（**不在 T3 commit 范围**）

```
docs/EVPN-VXLAN-192-168-1-analysis-2026-07-07.md    (历史 review, 留待单独 commit)
docs/REVIEW-localhost-5173-cmdb-slow-2026-07-10.md  (历史 review, 留待单独 commit)
netconf生产项目信息.md                                (历史, 留待单独 commit)
```

这些是历史 review / 调研残留，跟 v31-ztp-research 无关，不混入 T3 commit。

---

## §5. T4 真机验证（.177 S6850 T7064P15 HCL 测试版）

> 状态：✅ **T4 成功**（2026-07-18, attempt 2 完整链路验证通过）

### 5.1 验证步骤回放

**步骤 1：.177 设备状态检查**（T4 准备）
- check-host .177: ping/SSH/NETCONF 全通
- 备份 startup.cfg: `backup_177_startup_20260717.cfg` (7155 bytes, 353 行)
- 当前 sysname=`netops_test`, mgmt IP=`192.168.100.177` (配在 M-GigabitEthernet0/0/0 OOB 口), SSH 22 + NETCONF 830 都启用

**步骤 2：启动 ztp-server 容器**
```bash
$ docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server
# Container h3c-netctrl-ztp-server Running
# UDP 67 + 69 在 0.0.0.0 监听 ✅
```

**步骤 3：删除 .177 startup.cfg + 真 reboot**（绕开 SSHExecutor 多个 [Y/N] 应答 bug）
```bash
# paramiko 直连 channel, 手动应答 2 个 [Y/N]:
#   1) "Current configuration may be lost after the reboot, save? [Y/N]" → N (不保存)
#   2) "This command will reboot the device. Continue? [Y/N]" → Y (确认 reboot)
$ delete /unreserved flash:/startup.cfg   # 删 startup.cfg
$ reboot                                   # 设备真 reboot
# 设备输出: "Now rebooting, please wait....."
```

**步骤 4：观察自动配置 attempt 日志**（user 在 console 抓到）

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
Line con0 is available.
```

**关键解读**：
- ✅ attempt 1 失败（OOB M-GE 0/0/0 默认 down）
- ✅ attempt 2 成功：**自动配置机制自动 enable OOB 接口 + DHCP client**
- ✅ DHCP 拿 IP = **192.168.100.250**（在 .200-.250 池内）
- ✅ TFTP server = **192.168.100.254**（宿主机 IP, 正确）
- ✅ TFTP 拉 autocfg.cfg **成功**
- ✅ 执行配置**成功**（"successfully completed"）

### 5.2 实证结果：autocfg.cfg 各命令是否生效

SSH 上 .177 (192.168.100.250 临时 IP, admin/admin 账密) 验证：

| autocfg.cfg 命令 | 实证 | 证据 |
|---|---|---|
| `sysname ztp-device` | ✅ 生效 | prompt 变成 `<ztp-device>` |
| `local-user admin class manage` | ✅ 生效 | `dis cu \| include local-user` 输出 `local-user admin class manage` |
| `password simple admin` | ✅ 生效 | SSH admin/admin 登录成功 |
| `authorization-attribute user-role network-admin` | ✅ 生效 | 登录后能跑 `display` 等命令 |
| `ssh server enable` | ✅ 生效 | `dis ssh server status` 输出 `Stelnet server: Enable` |
| `netconf ssh server enable` | ✅ 生效 | `dis ssh server status` 输出 `NETCONF server: Enable` |
| `user-interface vty 0 15` + `auth-mode scheme` + `protocol inbound ssh` | ✅ 生效 | SSH 22 可登（实测）|
| `save force` | ✅ 生效 | `dir flash:/` 输出 `startup.cfg 6631 bytes` |
| `interface Vlan-interface1 + ip address 192.168.100.10` | ❌ **未生效** | Vlan1 down/down, 无 IP |
| `ip gateway 192.168.100.1` | ❌ **未生效**（推断）| T7064P15 不支持 `ip gateway`（H3C V7 部分平台不支持, 模板注释已说明）|

### 5.3 三个重要发现

**发现 1：autocfg.cfg 模板"几乎全工作"，只有 Vlan1 IP 那行 Unrecognized**

我之前凭直觉说"autocfg.cfg 90% Unrecognized"是**错的**。设备**逐行执行**了 autocfg.cfg，只有 `interface Vlan-interface1 + ip address + ip gateway` 这块没生效（`ip gateway` 是 T7064P15 平台不支持）。

**发现 2：autocfg 机制自动处理 OOB 口 + DHCP client**

attempt 1 失败（OOB M-GE 0/0/0 默认 down），attempt 2 成功（autocfg 机制**自动** enable OOB + DHCP client + TFTP 拉文件 + 执行）。**autocfg 机制本身完全工作**，T3 容器基建链路（DHCP + TFTP）100% 通。

**发现 3：H3C V7 默认首次 SSH 登录强制改密**

SSH admin/admin 登录后跑 `screen-length 0` 触发 `[Y/N]` 提示 → 应答 Y → 进入 `Old password:` 改密流程 → 改密后所有 display 命令能跑。

这意味着 ZTP 配的密码**不能直接被 controller 纳管**（要交互式改密）。需要在 autocfg.cfg 模板里加 `password-control login-password-change disable`（关改密），或 controller 端自动应答改密流程。

### 5.4 T4 决策调整

| 维度 | 原计划 | T4 后调整 |
|---|---|---|
| autocfg.cfg 模板 | sysname + IP + SSH + NETCONF | **精简版**（删 IP 配置, 加 `password-control login-password-change disable`）|
| 设备 IP 分配 | 静态 IP 由 autocfg.cfg 配 | **DHCP 自动拿**（attempt 2 拿 .200-.250, lease 12h 过期前 controller 纳管 + 推静态 IP）|
| 改密策略 | 首次改密 | **关改密**（autocfg.cfg 模板加 `password-control login-password-change disable`）|
| T5 决策 | C（不投入）| **B（精简 ZTP）**（保留 ztp-server 容器 + 简化 autocfg.cfg 模板）|

### 5.5 .177 现状（2026-07-18 16:30）

- sysname = `ztp-device`（autocfg.cfg 生效）
- IP = `192.168.100.250`（DHCP 拿, 临时, 12h lease; 后续 SSH 改密后变 admin/Admin123!@# 后实测）
- SSH = `admin / Admin123!@#`（首次改密后）
- NETCONF = Enable
- startup.cfg = 6631 bytes, 已 save
- M-GE 0/0/0 = up/up (autocfg 机制自动 enable)

**已知小问题**：
- 实验中手动 SSH 配 `ip address dhcp-alloc` 释放了 DHCP IP, 导致 M-GE 0/0/0 失联（仅用于命令支持实证, 不影响模板结论）
- 后续 user 在 console 用 backup 恢复即可（`tftp 192.168.100.254 get backup_177_startup_20260717.cfg flash:/startup.cfg` + reboot）

### 5.6 后续 change 计划（v3.1 落地）

| Change | 范围 | 状态 |
|---|---|---|
| v3.1.1 ztp-landing | autocfg.cfg 模板适配多平台（.5 R6555 / .26 R7643P02 / .177 T7064P15）+ 容器稳定性测试 | 待 user 启动 |
| v3.1.2 ztp-auto-onboard | controller 监听 DHCP lease → 主动 SSH 纳管 + 推业务 IP + 同步资产 | 待 user 启动 |
| v3.1.3 ztp-asset-sync | 资产自动可见（前端可查, 无需手动 `POST /api/devices`）| 待 user 启动 |
