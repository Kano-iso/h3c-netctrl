# v311-ztp-landing — Notes

> **状态**：T1 探针完成（.5 + .26 + .177 探针完毕），T2-T8 已实现/验证；后续主线是 **先 .177 完整 ZTP 验证，再 .26 适配性验证**，`.5` 不跑完整 ZTP。
> **关键发现 1**：V9850-256H R7643P02 当前现网实测 OOB 口 = **`MGE0/0/0`**（不是 PRD V3.1.1 L146 写的 `MEth0/0/0`）；后续模板口径不强制名字，而是必须确保取到真实 physical OOB 口。
> **关键发现 2**：`.177` 凭据 = **`python/Admin123!@#`**（user 2026-07-18 提供），与项目主账密一致，ZTP 模板统一用此账密
> **关键发现 3**：V9850 同时支持 `network-admin` 和 `level-15` 两种 user-role（都成功），RSTN 模板统一用 `network-admin` 与 S6850 一致
> **决策**：
> - RSTN 物理 OOB 口当前现网 = `MGE0/0/0`（已实测验证）；实现/文档表述按“探测到的 physical OOB 口”处理，不把 `MGE` 名字写成跨设备绝对规则
> - 账密统一 = `python/Admin123!@#`（user 2026-07-18 拍板，**删除 admin/admin / admin/Admin123!@# 等第二套账密**）
> - **T9 真机验证主线仍是 .177**——先在 .177 验证一切无误，再转 .26 做适配性验证；`.5` 不进入完整 ZTP 验证范围
> - **高危操作红线**（2026-07-18 user 批评复盘）—— 后续 `undo` / `save force` / `reboot` / `reset saved-configuration` 类操作必须**先列清单 → user 审批**才能执行

---

---

## §T1 探针结果（2026-07-18 完成）

### 设备与软件版本核对

| 设备 IP | 设备型号 | 软件版本 | ZTP_PLATFORM 值 |
|---|---|---|---|
| 192.168.100.5 | S6850 | **T7064P15-prod**（HCL 商用版）| `lstn`（LSTN 主分支）|
| 192.168.100.26 | V9850-256H | R7643P02 | `rstn` |
| 192.168.100.177 | S6850 | T7064P15-**hcl**（HCL 测试版）| `lstn` + `ZTP_HCL_T7064P15=true`（HCL 子分支）|

---

### .5 (T7064P15-prod) 探针结果

> 状态：✅ 完成

| 命令 | 结果 | 备注 |
|---|---|---|
| `display version` | ✅ S6850 + 7.1.070 T7064P15 + uptime 4d 14h | |
| `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.50 255.255.255.0` | ✅ 工作（无警告）| 物理 OOB 口 static IP 支持 |
| `interface M-GigabitEthernet0/0/0 + ip address ... + undo` | ✅ 完整还原 | 探针安全可逆 |
| `display ssh server status` | ✅ Stelnet=Enable, NETCONF=Enable | SSH/NETCONF 都已 enabled |
| `password-control login-password-change disable` | ❌ **Unrecognized** | 商用版不支持 HCL 独有命令 |
| `password-control change-password first-login enable` | ✅ 工作（no-op）| 通用命令，prod 显式 enable 显式 disable 不支持 |
| `save force` | ✅ 工作 | |

**.5 探针结论**：
- 物理 OOB 口 `M-GigabitEthernet0/0/0` ✅ static IP 支持
- LSTN 主分支用 `password-control change-password first-login enable`（no-op 安全）
- **不**用 `password-control login-password-change disable`（prod Unrecognized）

---

### .26 (R7643P02 V9850) 探针结果

> 状态：✅ 完成

| 命令 | 结果 | 备注 |
|---|---|---|
| `display version` | ✅ V9850-256H + 7.1.070 R7643P02 + uptime 1d 17h | |
| `display interface brief` | ✅ 找到 `MGE0/0/0 UP UP`（**不是 PRD 写的 `MEth0/0/0`！**）| 物理 OOB 口是 MGE0/0/0 |
| `display interface MEth0/0/0` | ❌ Wrong parameter | **MEth0/0/0 不存在** |
| `interface MGE0/0/0 + ip address 192.168.100.50 255.255.255.0` | ✅ 工作（无警告）| V9850 OOB 口 static IP 支持 |
| `netconf ssh server enable` | ✅ 工作（默认已 enable，no-op 安全）| 模板显式 enable 无副作用 |
| `netconf soap http enable` | ✅ 工作（备选）| 备选协议 |
| `authorization-attribute user-role level-15` | ✅ 工作 | V9850 数字等级支持 |
| `authorization-attribute user-role network-admin` | ✅ 工作 | V9850 字符串角色也支持 |
| `display netconf server status` | ❌ Unrecognized | R7643P02 语法不同，无影响（autocfg.cfg 模板不依赖此命令）|
| `save force` | ✅ 工作 | |

**.26 探针结论**：
- **RSTN 物理 OOB 口 = `MGE0/0/0`**（不是 PRD 写的 `MEth0/0/0`）—— **PRD 修正**
- RSTN NETCONF 协议：`netconf ssh server enable`（与 S6850 一致，no-op 安全）
- RSTN user-role：`network-admin`（V9850 同时支持 level-15，但用 network-admin 与 S6850 统一）
- RSTN password-control：`change-password first-login enable`（与 S6850-prod 一致）

---

### .177 (T7064P15-hcl) 探针状态

> 状态：⚠️ **凭据不可知**（v3.1.0 T4 reset 后有人动过 .177）

**已知情况**（v3.1.0 T4 之前 backup_177_startup_20260717.cfg）：
- sysname: `netops_test`
- M-GigabitEthernet0/0/0 IP: `192.168.100.177`（静态）
- local-user `python` + password hash（`$h$6$5gGyxiEGG/...`，原密码 Admin123!@#）
- netconf ssh server enable, ssh server enable

**v3.1.0 T4 之后**（autocfg 跑过）：
- 应该被改成 sysname=ztp-device + local-user admin/admin + login-password-change disable + save force
- 但 2026-07-18 验证：python/Admin123!@# / admin/admin / ric/ric **全 AuthenticationException**
- SSH 22 + NETCONF 830 **端口在 LISTEN** + 设备接受 password prompt → **.177 上一定有 local-user，只是密码不匹配**

**KEX 诊断**（paramiko 4.0.0 + Comware-7.1.070）：
- `Kex: ecdh-sha2-nistp256` ✅
- `HostKey: ssh-rsa` ✅
- `Authentication (password) failed.` ❌ 密码错

**接手修正**（user 2026-07-18 后续明确）：
- **T9 真机验证仍以 .177 为主线**：先在 `.177` 验证一切无误，再转 `.26` 做适配性验证
- `.177` T7064P15-hcl 不是“仅模板支持”，而是 v3.1.1 主验证对象
- `.5` 不跑完整 ZTP；它只保留已经完成的命令探针作为 S6850/LSTN 佐证
- **优化建议**（user 提出"做一个收束"）：ops-toolkit 加 `--probe-user` 自动尝试常见凭据 —— **v3.1.2 范畴，不阻塞 v3.1.1**

---

## §RSTN 模板设计（基于 T1.2 实测结果更新）

```jinja2
# 平台条件分支（RSTN = V9850 R7643P02）
{% if platform == 'rstn' %}
interface MGE0/0/0                              # ← 关键修正（PRD 错的 MEth0/0/0 → 实测 MGE0/0/0）
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% elif platform == 'lstn' %}
interface M-GigabitEthernet0/0/0                # ← S6850 物理 OOB 口
 ip address {{ mgmt_ip }} 255.255.255.0
quit
{% endif %}

# NETCONF 通用（两个平台都显式 enable，no-op 安全）
netconf ssh server enable

# user-role 统一用 network-admin（V9850 同时支持 level-15，但用 network-admin 统一）
authorization-attribute user-role network-admin

# password-control 通用（no-op 安全）
password-control change-password first-login enable

# HCL 子分支（仅 lstn + ZTP_HCL_T7064P15=true 时）
{% if platform == 'lstn' and hcl_t7064p15 %}
password-control login-password-change disable   # HCL 独有，prod Unrecognized
{% endif %}
```

---

## §用户 2026-07-18 接手修正

### 决策 A：OOB 口按现网探测，不把接口名写死成绝对规则

- **原 PRD V3.1.1 L146**：`MEth0/0/0`
- **T1 实测**：`MGE0/0/0`（V9850-256H R7643P02 实际接口名）
- **修复**：当前 `.26` jinja2 RSTN 分支用 `MGE0/0/0`
- **用户修正**：口径不必强行统一成 `MGE`；后续可继续试探，但必须确保命中的是真实 physical OOB 口

### 决策 B：完整 ZTP 验证顺序

- **主线**：先在 `.177` 验证完整 ZTP 链路，一切无误后再转 `.26` 做适配性验证
- **`.26` 背景**：`.26` 是 EVE-NG 借来的 V9850/RSTN 测试设备，v3.0 已用它验证 RSTN/schema NETCONF 配置面；v3.1.1 用它验证新平台 autocfg/OOB 口模板适配
- **`.5` 范围**：`.5` 不跑完整 ZTP。它是生产/现网 S6850 参考设备，已发生的 OOB/static 命令探针只作为 LSTN 佐证，不作为本 change 的完整链路验收对象

### 决策 C：.177 凭据不可知的优化（v3.1.2 范畴）

- **问题**：每次 reset 设备后凭据丢失，需要 user 告知或猜
- **user 建议**："做一个收束，别每次都问"
- **提议**：ops-toolkit 加 `--probe-user` 工具，自动尝试常见凭据
  - python/Admin123!@#（项目默认）
  - admin/admin（v3.1.0 T4 写入）
  - admin/Admin@123（H3C 默认）
  - ric/ric（user 提的）
  - 报告哪个成功 + 记录到 ops-toolkit 内部
- **状态**：v3.1.2 范畴，不阻塞 v3.1.1

---

## §T1 探针命令记录（完整）

### .5 探针

```bash
# 用 ops-toolkit paramiko-batch-exec.sh
paramiko-batch-exec.sh --device 192.168.100.5 --command "interface M-GigabitEthernet0/0/0; ip address 192.168.100.50 255.255.255.0; quit; display this; undo ip address"
# ✅ 成功

paramiko-batch-exec.sh --device 192.168.100.5 --command "display version"
# ✅ S6850 + 7.1.070 T7064P15

paramiko-batch-exec.sh --device 192.168.100.5 --command "display ssh server status"
# ✅ Stelnet=Enable, NETCONF=Enable

paramiko-batch-exec.sh --device 192.168.100.5 --command "password-control login-password-change disable"
# ❌ Unrecognized
```

### .26 探针

```bash
paramiko-batch-exec.sh --device 192.168.100.26 --command "display version"
# ✅ V9850-256H + 7.1.070 R7643P02

paramiko-batch-exec.sh --device 192.168.100.26 --command "display interface brief"
# ✅ MGE0/0/0 UP UP（不是 MEth0/0/0！）

paramiko-batch-exec.sh --device 192.168.100.26 --command "display interface MEth0/0/0"
# ❌ Wrong parameter

paramiko-batch-exec.sh --device 192.168.100.26 --command "interface MGE0/0/0; ip address 192.168.100.50 255.255.255.0; quit; display this"
# ✅ 成功

paramiko-batch-exec.sh --device 192.168.100.26 --command "netconf soap http enable; undo netconf soap http enable; save force"
# ✅ 全成功

paramiko-batch-exec.sh --device 192.168.100.26 --command "local-user ztp_probe1 class manage; authorization-attribute user-role level-15; quit; local-user ztp_probe2 class manage; authorization-attribute user-role network-admin; quit"
# ✅ 两种 user-role 都成功
```

### .177 诊断

```bash
# KEX 诊断脚本（/tmp/diag_177.py）
python3 -c "import paramiko; c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy()); c.connect('192.168.100.177', 22, username='python', password='Admin123!@#', timeout=10, allow_agent=False, look_for_keys=False)"
# ❌ AuthenticationException（KEX 成功，password 错）

# KEX 阶段日志：
# Kex: ecdh-sha2-nistp256
# HostKey: ssh-rsa
# Cipher: aes128-ctr
# userauth is OK
# Authentication (password) failed.  ← 根因
```

### .177 探针（凭据 = python/Admin123!@#，10/10 成功，但触发失联事故）

> 状态：✅ 探针全过 / ❌ 探针后设备失联

**凭据找到**：user 2026-07-18 提供 `admin/Admin123!@#` → 实际凭据（KEX 诊断确认 `python/Admin123!@#` 也通——v3.1.0 T4 之后用户改密到 Admin123!@#）

**探针结果（10/10 成功）**：
- `display version` → S6850 + 7.1.070 T7064P15
- `display interface M-GigabitEthernet0/0/0` → UP + 现有 IP `192.168.100.177/24`（v3.1.0 T4 之后被手配）
- `interface M-GigabitEthernet0/0/0` → ✅
- `ip address 192.168.100.50 255.255.255.0` → ✅（临时探针）
- `quit` → ✅
- `display this` → ✅
- `undo ip address` → ❌ **清掉了所有 IP（包括 .177）**
- `password-control login-password-change disable` → ✅
- `netconf ssh server enable` → ✅
- `save force` → ❌ **把"OOB 口无 IP"持久化** → 设备失联

**根因**：
- `undo ip address` 在 interface 配置模式下，**清掉所有 IP**（不是只清最后一条）
- `.177` OOB 口之前是 static IP `.177/24`，没配 DHCP client
- `undo ip address` + `save force` 后 OOB 口无 IP + 无 DHCP fallback → 完全失联

**挽救方案**（user console 手工）：
1. console 直连 .177
2. system-view
3. interface M-GigabitEthernet0/0/0
4. ip address 192.168.100.177 255.255.255.0
5. quit
6. local-user python class manage
7. password simple Admin123!@#  ← 改回主账密
8. service-type ssh terminal
9. authorization-attribute user-role network-admin
10. quit
11. user-interface vty 0 15
12. authentication-mode scheme
13. protocol inbound ssh
14. quit
15. password-control login-password-change disable
16. save force

---

## §高危操作红线（2026-07-18 user 批评复盘）

### 事件

执行 .177 探针时，未先列操作清单让 user 审批，直接执行 `undo ip address` + `save force` 导致设备 OOB 口 IP 被清 + 持久化，`.177` 失联。

### 根因分析

| 失误 | 详情 |
|---|---|
| 1️⃣ **未列操作清单** | 探针命令是组合命令（10 条），没有逐条说明"执行这条会改变什么状态" |
| 2️⃣ **未考虑 `undo` 副作用** | `undo ip address` 会清掉所有 IP，不是只清最后一条——我没意识到 |
| 3️⃣ **未先备份** | 探针前没走 backup-config.sh 备份 .177 startup.cfg |
| 4️⃣ **未问 user 审批** | 高危操作（涉及 `save force` + `undo`）必须 user 审批后才能执行 |

### 红线规则（v3.1.1 起生效）

> **任何涉及以下命令的探针或操作，必须先列清单 → user 审批 → 才能执行**：

- ❌ `undo ip address`（会清掉所有 IP，**不是只清最后一条**）
- ❌ `undo interface` / `undo vlan`（会删除接口/虚拟口）
- ❌ `save force` / `save`（持久化到 startup.cfg，不可逆）
- ❌ `reboot` / `reset saved-configuration`（设备重启/配置清空）
- ❌ `delete` / `erase`（删除文件）
- ❌ `local-user ... remove`（删除用户）
- ❌ `password-recovery enable`（启用密码恢复，影响安全）

### 红线配套规范

1. **探针前必 backup**（优先走 `capture-config.sh`；v3.1.1 起已补齐 OpenSSH `ssh-rsa` 兼容参数。若设备 SCP server 未启用，先显式开启或退回 paramiko 文本备份）
2. **探针后必 verify**（`display this` / `display current-configuration` 确认状态）
3. **`undo` 类操作前先 `display`**（看清楚当前状态再 undo）
4. **`save force` 前先 `display saved-configuration`**（确认要保存的内容）

### 任务跟踪

- [ ] v3.1.1 T11 阶段把"高危操作红线"写进 `.trae/rules/qa规范.md`（C 类规则）
- [ ] v3.1.1 T11 阶段把"高危操作红线"写进 `docs/ops-toolkit.md`（操作 SOP）

---

## §账密统一规范（2026-07-18 user 拍板）

### 决策

> **项目所有账密统一为 `python/Admin123!@#`**（来自 .env `DEVICE_USERNAME` / `DEVICE_PASSWORD`）
> 不再使用任何第二套账密（admin/admin、admin/Admin123!@#、ric/ric 等全部删除）

### 影响范围

| 文件 | 修改 |
|---|---|
| `docker/ztp-stack/tftp/autocfg.cfg.j2` | `local-user {{ admin_user }} class manage + password simple {{ admin_pass }}` 中 `admin_user=python` / `admin_pass=Admin123!@#` |
| `.env` | `ZTP_ADMIN_USER=python` / `ZTP_ADMIN_PASS=Admin123!@#`（替换原 `admin` / `admin`）|
| `.env.example` | 同上（默认模板也改）|
| `docs/ztp-stack.md` | 删除"ZTP 专用账密"章节，统一引用项目主账密 |

### 实施时机

- T2 阶段：autocfg.cfg.j2 模板用 `python/Admin123!@#`
- T11 阶段：.env / .env.example 同步更新

---

## §T9/T10 真机 ZTP 链路验证 — 当前接手口径

### 现状

- `.177` 曾因 `undo ip address + save force` 高危探针失联，后续是否已 console 救回以实际连通性检查为准
- `.5` 认证通 + 命令验证全过（prod）
- `.26` 认证通 + 命令验证全过（rstn）

### 验证顺序

| 顺序 | 设备 | 目的 | 备注 |
|---|---|---|---|
| 1 | `.177` S6850/T7064P15-hcl | 主验证：空配置 → DHCP → TFTP → autocfg → static `.101` → save → 重启持久 | 必须先验证 |
| 2 | `.26` V9850/R7643P02 | 适配性验证：RSTN 平台 OOB 口、user-role、NETCONF、save 行为 | 必须验证 |
| - | `.5` S6850/T7064P15-prod | 不跑完整 ZTP | 保留既有命令探针记录即可 |

### 原因理解

- v3.1.0 证明的是 `.177` 上 H3C V7 `autocfg.cfg` 自动配置路径真实可行；v3.1.1 首先要把这个路径从“临时 DHCP 可用”推进到“static IP 持久可用”。
- `.26` 来自 EVE-NG 借用的 V9850/RSTN 测试设备，v3.0 已用于跨平台配置面验证；它代表后续 EVENG/虚拟化验证方向，因此 v3.1.1 必须确认 ZTP 模板在 RSTN 上也能落地。
- 做 ZTP 的背景不是当前环境不能手工配，而是为了后续白屏/批量/虚拟设备接入：设备首启只需要接线，系统提供 DHCP+TFTP+autocfg 基础配置，后续 v3.1.2/v3.1.3 再自动纳管、资产可见，v3.2 再迁移到 EVENG 做完整数据面验证。

---

## §T7 容器层 CI 验证（2026-07-18 通过）

> **目的**：T2-T6 完成后跑容器层 QA 验证（不需真机）
> **user 2026-07-18 拍板**：
> - T1.1 .5 探针**跳过**（.5 不跑 ZTP 验证，T10 仅 .26）
> - T10 仅 .26 R7643P02 真机 ZTP 验证

### 验证结果

| # | 验收点 | 命令 | 结果 |
|---|--------|------|------|
| 7.1 | 容器构建 | `docker compose -f docker-compose.dev.yml --profile ops build ztp-server` | ✅ `Image h3c-netctrl-ztp-server Built` |
| 7.2 | dnsmasq 配置语法 | `docker exec ztp-server dnsmasq --test -C /etc/dnsmasq.conf` | ✅ `dnsmasq: syntax check OK.` |
| 7.3 | 端口监听 67/69 | `ss -ulnA inet` (host) | ✅ `0.0.0.0:67` + `0.0.0.0:69` (host network) |
| 7.4 | LSTN 渲染 | `docker exec ztp-server cat /var/tftp/autocfg.cfg` | ✅ `interface M-GigabitEthernet0/0/0` + `ip address 192.168.100.101 255.255.255.0` + `local-user python` + `Admin123!@#` |
| 7.5 | RSTN 渲染 | 手动跑 `python3 + jinja2 Template(platform='rstn')` | ✅ `interface MGE0/0/0` + `ip address 192.168.100.101 255.255.255.0` |
| 7.6 | 平台路由 | `ZTP_PLATFORM=rstn` → RSTN 分支 | ✅ 工作正常（lstn → M-GigabitEthernet，rstn → MGE0/0/0）|
| 7.7 | DHCP 池范围 | `grep dhcp-range /etc/dnsmasq.conf` | ✅ `dhcp-range=192.168.100.151,192.168.100.190,12h` |
| 7.8 | 无 mac-binding / leasefile | `grep -v '^#' /etc/dnsmasq.conf \| grep dhcp-host` | ✅ 实际配置 0 条（仅注释提到"v3.1.1 不做"）|

### 关键发现

1. **物理 OOB 口命令支持（已验证）**：
   - LSTN (S6850 T7064P15) = `M-GigabitEthernet0/0/0` ✓
   - RSTN (V9850 R7643P02) = `MGE0/0/0` ✓
2. **DHCP 池 + TFTP server 联动**：67/UDP DHCP + 69/UDP TFTP 同时监听，host network 模式直接接收 .177 物理网段 L2 广播
3. **Jinja2 平台条件分支**：LSTN/RSTN 渲染互斥正确，HCL 子分支由 `ZTP_HCL_T7064P15` 控制
4. **方案 C 撤销确认**：autocfg.cfg 模板**只创建 `python` 一个用户**（不创建 admin），与 user 2026-07-18 "禁止第二账号" 原则一致
5. **.177 admin 用户存在但模板不复用**：当前 .177 残留 admin 用户（与 python 共存），T9 真机验证时模板会自然覆盖（autocfg 只创建 python，不删 admin）

### T7 commit

- `test(ztp): T7 容器层 CI 验证（build + dnsmasq test + jinja2 render + 平台路由）`

---

## §T8 qa-backend 回归 — N/A（user 2026-07-18 拍板跳过）

> **user 反馈**：
> "qa-backend 是 backend 代码 pytest 回归，ztp-server 是个新基建小工具。虽然将来可能集成到平台里，但现在没必要走 qa-backend。每发版全量 QA 合理，但每次都上线一个新机器不可控。"

### 决策

- **T8 qa-backend 回归不适用 v3.1.1**（已从 tasks.md 标记 N/A）
- **理由**：
  1. `qa-backend` = backend 代码 pytest 回归（覆盖 FastAPI 业务代码）
  2. v3.1.1 = 新增 ztp-server 基建工具，**零 backend 代码改动**
  3. qa-backend 跑 245+ passed baseline ≠ ztp-server 验证
  4. 工具分层：基建工具变更 → 工具层 CI（T7 容器层 CI 才是正确验证）
- **未来**：
  - v3.1.2 / v3.1.3 把 ztp-server 集成进 controller → 那时 controller 改 backend 代码 → qa-backend 回归才适用
  - 现阶段 ztp-server 独立运行，qa-backend 跳过

### 工具边界（user 2026-07-18 强化）

| 工具 | 适用场景 | 不适用场景 |
|------|----------|------------|
| `qa-backend` | backend 代码变更回归 | 新基建工具（容器/脚本/配置）|
| `qa-frontend` | frontend 代码变更回归 | 同上 |
| **工具层 CI**（T7 模式）| 基建工具容器（build + 配置 + 渲染）| backend/frontend 代码 |
| `ops-toolkit` | 真机端到端（探针/排错）| 容器级 CI 验证 |
| MCP 浏览器 | UI 单功能验证 | 全量回归 / 组件测试 |

> **核心原则**：用对工具，不要"反正能跑就跑一下"。每次发版必跑 qa-backend（全量回归是发版门槛），但**新基建小工具不应绑 qa-backend 必跑**。

---

## §T9 真机验证进展（2026-07-18）

### 已确认
- ✅ `ztp-server` 已启动，DHCP/TFTP 语法通过，当前池为 `.151-.190`，TFTP server 为 `.254`
- ✅ `autocfg.cfg` 当前渲染 static OOB IP 为 `192.168.100.101`
- ✅ 项目已有可参考的 H3C V7 reboot 完整交互：`backend/app/utils/backup_manager.py::_reboot_and_wait`
- ✅ 新增临时脚本里的 `reset-reboot-177.py` 交互思路接近正确：`reset saved-configuration` 答 `Y`，`reboot` 时先答 `N` 不保存当前配置，再答 `Y` 确认重启

### 纠偏结论
- ❌ “设备不支持 reboot”不是当前证据支持的结论。H3C V7 支持 reboot；失败更可能来自临时工具没有处理完整的 `N/Y` 二段交互。
- ❌ 不建议为 T9 临时需求扩展全局 `SSHExecutor / paramiko-batch-exec` 自定义应答。该路径会把 ZTP reset/reboot 的高危交互扩散到通用批命令工具。
- ❌ `docker/ztp-stack/tmp-reboot.py` 只处理了 `save current configuration` 的 `N`，没有继续处理 `continue?` 的 `Y`，不能作为 reboot 结论依据。
- ❌ `docker/ztp-stack/reset-reboot-177.py` 虽然交互方向对，但放在 `docker/ztp-stack` 且硬编码凭据、裸 paramiko，不符合“设备操作走 ops-toolkit”的规则。

### 当前阻塞点
- `.177` 与目标 static `.101` 当前均不可达（2026-07-18 使用 `check-host` 验证）。
- 当前 `.env` 为 `ZTP_HCL_T7064P15=false`，因此 `ztp-server` 渲染的是 `.177` 不需要的 prod 分支；T9 主验证 `.177` 前应切到 `ZTP_HCL_T7064P15=true` 并重启 `ztp-server`。
- `backup_177_current_20260718_211812.cfg` 与 `restore-177.cfg` 均显示 `.177` 原始 OOB 口配置为 `M-GigabitEthernet0/0/0 + 192.168.100.177/24`，恢复材料存在，但设备当前是否已进入空配置/重启中状态需要控制台或重新上线后确认。

### 下一步建议
- 先把 `ZTP_HCL_T7064P15=true` 生效到 `ztp-server`，确认 autocfg.cfg 渲染 HCL 分支。
- 用一个作用域很窄的 ops-toolkit 验证工具承载 `reset saved-configuration + reboot + wait`，内部复用 `BackupManager._reboot_and_wait` 的交互逻辑，不改全局 `SSHExecutor`。
- 真机执行前按红线规则列清单并由 user 审批：目标 `.177`、动作 `reset saved-configuration`、动作 `reboot`、reboot 不保存当前配置、等待 `.101` 上线、失败时按 `restore-177.cfg` 恢复。

---

## §T9/T10 接手实测进展（2026-07-18 Codex）

### T9 .177 主链路结果

- ✅ 新增通用 `reboot-wait.sh` 交互工具：支持 H3C `reboot` 二段提示（先 `N` 不保存 running，再 `Y` 确认重启）。
- ✅ `reboot-wait.sh --reset-saved --wait-ip 192.168.100.101` 验证通过：`.177` reset saved-configuration 后空配置启动，88s 后 `.101` SSH 恢复。
- ✅ `ztp-server` 日志确认：`.177` DHCP Discover/Request，临时拿到 `.190`，从 `.254` TFTP 拉取 `autocfg.cfg`。
- ✅ `.101` 验证通过：SSH 22 通、NETCONF 830 通、current/saved 均含 `sysname ztp-device`、`M-GigabitEthernet0/0/0`、`ip address 192.168.100.101/24`、`local-user python`。
- ✅ 二次 reboot 持久性验证通过：`.101` 先掉线，再 33s 恢复，配置仍保留在 current/saved。

**证据文件**：
- `captures/ztp-test/reboot_wait_177_to_101_20260718.log`
- `captures/ztp-test/ztp_server_logs_after_177_20260718.log`
- `captures/ztp-test/check_host_101_after_ztp_20260718.log`
- `captures/ztp-test/check_netconf_101_after_ztp_20260718.log`
- `captures/ztp-test/config_101_after_ztp_20260718.log`
- `captures/ztp-test/reboot_wait_101_persistence_retry_20260718.log`
- `captures/ztp-test/config_101_after_persistence_reboot_20260718.log`

### T10 .26 RSTN 暂停结论

- ⚠️ `.26` reset/reboot 验证中途被 user 中断并手工恢复，未形成完整 T10 结论。
- ✅ `.26` 恢复后只读检查：`.26` SSH 可达；NETCONF 初始为 Disable，手动进入 system-view 后 `netconf ssh server enable` 可打开，`check-netconf` 成功。
- ✅ `.26` 配置命令探针：`password-control change-password first-login enable`、`local-user python`、`service-type ssh terminal`、`authorization-attribute user-role network-admin/level-15` 在 system-view / local-user 视图下均可用。
- ✅ `.26` OOB 口完整名为 `M-GigabitEthernet0/0/0`；`MGE0/0/0` 可作为缩写，但模板应写完整名。
- ❌ 当前通用模板存在 RSTN 不兼容命令：`ssh server authentication-timeout 300` 在 V9850 R7643P02 上报 `% Wrong parameter found at '^' position`，不能放在 RSTN 分支。

**修正**：
- RSTN 分支接口改为完整 `interface M-GigabitEthernet0/0/0`
- `ssh server authentication-timeout 300` 仅在 LSTN 分支渲染

### .26 startup.cfg 抓取结论

- ✅ 按 user 建议开启 `.26` SCP server：`system-view -> scp server enable`，`display ssh server status` 确认 `SCP server: Enable`。
- ✅ `capture-config.sh` 增加 H3C V7 兼容参数（`scp -O` + `HostKeyAlgorithms=+ssh-rsa`）后，成功拉取 `.26 startup.cfg`。
- ✅ 证据文件：`captures/ztp-test/startup_26_scp_20260718.cfg`（894 行，16692 bytes）。
- ✅ 删除隔壁临时脚本：`docker/ztp-stack/reset-reboot-177.py` / `tmp-reboot.py` / `ztp-rotate-ip.py`，避免错误路径继续误导。
- ✅ sysname 改为随 static IP 自动派生：`ZTP_MGMT_IP=.101 -> ztp-switch-101`，`.102 -> ztp-switch-102`。如显式设置 `ZTP_SYSNAME` 且不是旧默认 `ztp-device`，则尊重显式值。

从 `.26 startup.cfg` 反推 RSTN 模板结构：

```text
interface M-GigabitEthernet0/0/0
 ip address 192.168.100.26 255.255.255.0

line vty 0 4
 authentication-mode scheme
 user-role network-operator
 protocol inbound ssh

line vty 5 63
 user-role network-operator

ssh server enable

local-user python class manage
 password hash ...
 service-type ssh terminal
 authorization-attribute user-role level-15
 authorization-attribute user-role network-admin
 authorization-attribute user-role network-operator

netconf ssh server enable
```

**当前策略**：T10 不继续 reset/reboot，先沉淀 RSTN 独立模板差异；v3.1.1 可基于 T9 `.177` 主链路先发版，`.26` 完整 RSTN 空配置验证作为后续补测/patch。

### RSA/旧 SSH 栈兼容规则

- H3C V7 旧版本常只提供 `ssh-rsa` host key，系统 OpenSSH/scp 默认会拒绝，典型报错：`no matching host key type found. Their offer: ssh-rsa`。
- 已知覆盖：
  - backend `SSHExecutor` / `NetconfClient` 已处理旧 KEX/算法兼容。
  - ops-toolkit `capture-config.sh` 已补 `scp -O`、`HostKeyAlgorithms=+ssh-rsa`、`PubkeyAcceptedAlgorithms=+ssh-rsa`。
- 后续任何新增 SSH/SCP/NETCONF 工具，都必须先复用既有兼容封装；不要在每次连接失败时重新怀疑业务命令或设备能力。
