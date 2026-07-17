# H3C NetCtrl V3.1.1 PRD：ZTP 落地

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.1.1 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.1.1 = ZTP 落地：1:1 静态 IP 池子 + autocfg.cfg 多平台适配（v3.1.0 调研已闭环 T7064P15，本版扩到 .5 R6555 / .26 R7643P02） |

---

## 1. 背景与目标

### 1.1 背景

v3.1.0 ZTP 调研 change（`v31-ztp-research`）已闭环，决策 B = **精简 ZTP**（只做基础配置：sysname + SSH + NETCONF + 凭据），独立 `ztp-server` 容器（alpine + dnsmasq 二合一）已可用，autocfg.cfg 模板在 `.177 T7064P15` 验证通过。

但 v3.1.0 留下 2 个未解决问题：

1. **IP 不持久**：当前 OOB 口 DHCP lease 12h 后过期，设备 IP 漂移
2. **多平台模板未适配**：autocfg.cfg 仅在 `.177 T7064P15` 验证通过，`.5 R6555` / `.26 R7643P02` 未测

### 1.2 目标

**让 ZTP 在多平台 + IP 持久 2 个维度落地**：

1. 1:1 静态 IP 池子方案：DHCP 拿 IP 即绑定静态 IP（避免 lease 过期漂移）
2. autocfg.cfg 多平台适配：.5 / .26 / .177 三平台各一份模板（按 sysname 路由）

### 1.3 关键约束

- ✅ **只做基础配置**：SSH 22 + NETCONF 830 + sysname + 凭据
- ❌ **不做业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ **不做配置联动**：ZTP 完成后由 v3.1.2 controller 推业务配置
- ✅ **白屏用户零操作**：设备上线 = 平台可见，无需人工

### 1.4 依赖

- **v3.1.0 已闭环**：独立 `ztp-server` 容器（alpine + dnsmasq）+ autocfg.cfg 模板（T7064P15 验证）
- **v3.0 骨架已闭环**：业务下发通道（SSH 22 / NETCONF 830）+ SSH executor
- **v2.4.1 已闭环**：ctrl + config + data 3 容器拆分

---

## 2. V3.1.1 范围

### 2.1 1:1 静态 IP 池子方案

#### 2.1.1 问题

当前 OOB 口走 DHCP，lease 12h 过期后 IP 漂移，controller 维护的"设备 ↔ IP"映射失效。

#### 2.1.2 方案

**1:1 静态 IP 池子映射**：

```
┌────────────┐                ┌──────────────────┐
│  DHCP 池    │   1:1 映射     │  静态 IP 池       │
│ .200~.250  │ ────────────> │  .200~.250       │
│ (50 地址)   │                │  (controller 推)  │
└────────────┘                └──────────────────┘
```

**流程**：

1. 设备空配置启动 → OOB 口 DHCP 请求 → 拿 `.250`（或其他池中地址）
2. 设备从 TFTP 拉 autocfg.cfg → 应用基础配置（含默认 OOB IP）
3. **v3.1.2 controller 监听到新 lease → 触发纳管（v3.1.1 暂不实现，由 v3.1.2 接手）**

**v3.1.1 实际做的事**：

- ztp-server 容器 dnsmasq 配 `dhcp-host` 1:1 静态映射
- autocfg.cfg 模板新增"静态 IP 推送"占位（v3.1.1 暂用 SSH 22 推，v3.1.2 改 controller 主动纳管）
- `.177` 真机验证：空配置启动 → DHCP 拿 `.250` → controller 推 `.250` 静态 IP → 重启后 `.250` 持久

#### 2.1.3 静态 IP 持久化方案对比

| 方案 | 实现 | 优势 | 劣势 |
|---|---|---|---|
| **A：autocfg.cfg 模板内置** | autocfg.cfg 写死 IP | 零额外步骤 | 每设备需独立模板 |
| **B：SSH 推 + save force** | controller SSH 推 IP + save | 模板通用 | 需 controller 介入（v3.1.1 简化：手动测试用） |
| **C：DHCP 永久租约** | dnsmasq 配 `dhcp-host=MAC,IP,infinite` | 零代码改动 | 仅当设备 MAC 固定时有效 |

**v3.1.1 决策**：**A + B 组合**

- autocfg.cfg 模板内置"静态 IP 段 + DHCP 兜底"（A）
- 后续 v3.1.2 controller 纳管时 SSH 推 IP（B，叠加在 A 之上）

### 2.2 autocfg.cfg 多平台适配

#### 2.2.1 平台差异

| 平台 | 设备型号 | 软件版本 | autocfg 支持 | 已知差异 |
|---|---|---|---|---|
| **LSTN** | .5 S6850 / .177 S6850 | R6555 / T7064P15 | ✅ | SSH 推基础配置 |
| **RSTN** | .26 V9850 | R7643P02 | ✅ | NETCONF 推基础配置（**v3.1.1 仅 SSH 兜底，NETCONF 在 v3.1.2 验证**）|

#### 2.2.2 模板方案

**方案 A：每平台 1 份 autocfg.cfg 模板（按 sysname 路由）** ✅ **决策**

```
ops-toolkit/ztp/autocfg/
├── tpl_lstn_s6850.cfg      # .5 / .177 适用（R6555 + T7064P15）
├── tpl_rstn_v9850.cfg      # .26 适用（R7643P02）
└── README.md
```

**路由逻辑**（在 ztp-server 容器 TFTP 侧）：
- 按设备 sysname 前缀（LSTN / RSTN / 其他）路由
- 未知平台走 SSH CLI 兜底（`ssh-push-base-config.sh`）

**方案 B：通用模板 + 平台差异条件分支（jinja2 渲染）** ❌ 不采用

- 理由：H3C V7 不同平台 autocfg.cfg 语法差异大（命令字 / 顺序 / 注释都不同），jinja2 条件分支会变成"看似通用实则满屏 if"，不如直接 3 份模板

#### 2.2.3 模板内容（LSTN S6850 通用版）

```text
#
sysname ${SYS_NAME}
#
interface M-GigabitEthernet0/0/0
 ip address dhcp-alloc
#
local-user ${USERNAME}
 password simple ${PASSWORD}
 authorization-attribute user-role network-admin
 service-type ssh
#
ssh server enable
ssh user ${USERNAME} service-type all authentication-type password
ssh client source-interface M-GigabitEthernet0/0/0
#
netconf ssh server enable
#
line vty 0 15
 authentication-mode scheme
 user-role network-admin
#
password-control login-password-change disable
#
save force
```

**RSTN V9850 差异点**：

- 不需要 `interface M-GigabitEthernet0/0/0`（V9850 OOB 口是 `MEth0/0/0`）
- `netconf ssh server enable` 替换为 `netconf soap http enable`（V9850 默认 SOAP 端口）
- `authorization-attribute user-role network-admin` 替换为 `authorization-attribute user-role level-15`

### 2.3 关闭首次登录改密

v3.1.0 已加 `password-control login-password-change disable`，v3.1.1 确认 3 平台均支持。

### 2.4 真机验证场景

| 场景 | 设备 | 验证内容 |
|---|---|---|
| **S1：空配置 + LSTN** | .177 T7064P15 | 恢复出厂 → autocfg 自动配置 → DHCP 拿 .250 → SSH 推 .250 静态 IP → 重启后 .250 持久 |
| **S2：空配置 + LSTN** | .5 R6555 | 同上 |
| **S3：空配置 + RSTN** | .26 R7643P02 | 同上（V9850 MEth0/0/0 差异） |
| **S4：静态 IP 已配 + DHCP 重叠** | .177 | 已配 .250 静态 + DHCP 也分 .250 → 不冲突（静态优先）|
| **S5：lease 过期** | .177 | DHCP lease 12h 后过期 → 设备 IP 仍是 .250（静态生效）|

---

## 3. 设计决策

### 3.1 DHCP 池 vs 静态 IP 池：1:1 映射（用户已拍板）

- 池大小：50 地址（.200~.250）
- 1:1 映射：DHCP 分到的 IP 即静态 IP（避免分配漂移）
- controller 维护"设备 MAC ↔ 静态 IP"映射（v3.1.2 实现）

### 3.2 静态 IP 推送通道

- **首选**：SSH 22 + paramiko 推送（v3.0 骨架已用）
- **fallback**：autocfg.cfg 模板内置（v3.1.1 简化版）
- **未来**：controller 主动纳管（v3.1.2）

### 3.3 静态 IP 持久化

- autocfg.cfg 模板内置"静态 IP 段 + DHCP 兜底"（A 方案）
- 后续 controller 推 IP 叠加（v3.1.2）

### 3.4 模板版本管理

- 每平台 1 份模板，按 sysname 前缀路由
- 模板改动走 OpenSpec change（v3.1.1 = `v3-1-1-ztp-landing`）

### 3.5 不做（明确边界）

- ❌ 不做 controller 主动纳管（推 v3.1.2）
- ❌ 不做业务配置（VPC / 路由 / 业务 VLAN）
- ❌ 不做 etcd 协调（v3.5 远期）
- ❌ 不做商用 R6607+ 设备 ZTP（v3.1.1 仅 .5 / .26 / .177）

---

## 4. 验收标准

### 4.1 1:1 静态 IP 池子

- [ ] ztp-server 容器 dnsmasq 配 `dhcp-host=MAC,IP,infinite` 1:1 映射
- [ ] `.177` 验证：空配置启动 → DHCP 拿 .250 → controller SSH 推 .250 静态 IP → 重启后 .250 持久
- [ ] DHCP lease 过期后设备 IP 仍是 .250（静态 IP 生效）
- [ ] 静态 IP 配置覆盖 OOB 口（确保 IP 持久）

### 4.2 autocfg.cfg 多平台适配

- [ ] `.5` R6555 验证通过（autocfg 拉取 + 基础配置应用 + save force）
- [ ] `.26` R7643P02 验证通过（V9850 MEth0/0/0 差异处理）
- [ ] `.177` T7064P15 回归（v3.1.0 已过，v3.1.1 复测）
- [ ] 3 平台模板独立维护（tpl_lstn_s6850.cfg / tpl_rstn_v9850.cfg）
- [ ] 模板按 sysname 前缀路由（LSTN / RSTN / 其他）

### 4.3 测试覆盖

- [ ] 17 测试覆盖：3 平台 × 5 场景（空配置 / 部分配置 / 静态 IP 已配 / DHCP 冲突 / lease 过期）
  - 3 平台：.5 / .26 / .177
  - 5 场景：S1~S5（如 §2.4）
- [ ] 模板 unit（jinja2 渲染正确性）：≥ 10 case
- [ ] 集成测试（DHCP + TFTP 端到端）：≥ 5 case
- [ ] 真机测试（3 平台 × 5 场景）：15 case

### 4.4 文档同步

- [ ] `ops-toolkit/ztp/autocfg/README.md`（模板说明 + 路由规则）
- [ ] `docs/ops-toolkit.md` §ztp 章节更新
- [ ] `VERSION-ROADMAP.md` v3.1.1 行状态更新（⏳ → ✅）
- [ ] `RELEASE-NOTES-v3.1.1.md` 新建

---

## 5. 依赖关系

### 5.1 上游依赖

- **v3.1.0**（已闭环）：独立 ztp-server 容器 + autocfg.cfg 模板（T7064P15）
- **v3.0**（已闭环）：业务下发通道（SSH 22 / NETCONF 830）
- **v2.4.1**（已闭环）：ctrl + config + data 3 容器拆分
- **v2.4.2.1**（已闭环）：paramiko-batch-exec.sh（4 级凭据 + Fernet 密文 + JSON 输出）

### 5.2 下游被依赖

- **v3.1.2**：controller 主动纳管（依赖 1:1 静态 IP 池子已落地）
- **v3.1.3**：资产可见（依赖 v3.1.2 自动纳管）

---

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **风险 1：RSTN V9850 模板差异大** | autocfg.cfg 模板需重写 | 提前做 RSTN 探针（v3.1.1 T1），确认差异点再定模板 |
| **风险 2：.5 R6555 老版本不支持某些命令** | 基础配置下发失败 | 先 .5 探针，备选 SSH CLI 兜底（v3.1.1 T1） |
| **风险 3：静态 IP 推送与 DHCP 冲突** | 设备 OOB 口启动后 IP 漂移 | autocfg.cfg 模板先配静态 IP，再启用 DHCP（避免 DHCP 抢答）|
| **风险 4：dnsmasq `dhcp-host` 语法不熟** | 1:1 映射配错 | 复用 v3.1.0 ztp-server 容器 dnsmasq 配置（已验证） |
| **风险 5：3 平台模板维护成本** | 后续改动需同步 3 份 | README 明确差异点；CI 检查模板差异是否合理 |

---

## 7. 走法（4 阶段）

| 阶段 | 主题 | 输出 | 依赖 |
|---|---|---|---|
| **T1** | 3 平台 autocfg 探针 | .5 / .26 / .177 差异报告 | v3.1.0 ztp-server 容器 |
| **T2** | 模板编写 + 路由规则 | tpl_lstn_s6850.cfg + tpl_rstn_v9850.cfg + 路由脚本 | T1 |
| **T3** | 1:1 静态 IP 池子 | ztp-server dnsmasq 配置 + autocfg 模板内置静态 IP | T1+T2 |
| **T4** | 真机验证 | 3 平台 × 5 场景 = 15 case | T1+T2+T3 |
| **T5** | 文档同步 + archive | VERSION-ROADMAP + README + RELEASE-NOTES + change archive | T1-T4 |

---

## 8. 不做（明确边界）

- ❌ **不做 controller 主动纳管**：v3.1.2
- ❌ **不做 ZTP 业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ **不做 etcd 协调**：v3.5 远期
- ❌ **不做前端大屏**：v3.4
- ❌ **不做多平台 NETCONF 适配**：v3.1.1 仅 SSH 兜底（RSTN NETCONF 推 v3.1.2+）

---

## 9. 与 PRD-V3.1 关系

- **PRD-V3.1** = V3.1 大版本蓝图（4 子版本拆解）
- **PRD-V3.1.1** = V3.1.1 子版本详细 PRD（本文件）
- **PRD-V3.1.2** = V3.1.2 子版本详细 PRD
- **PRD-V3.1.3** = V3.1.3 子版本详细 PRD
- 3 个子版本 PRD 独立 OpenSpec change 跟踪，独立 commit
- 共同构成 V3.1 大版本完整 PRD 体系

---

## 10. 参考文档

- [PRD-V3.1.md](PRD-V3.1.md) — V3.1 大版本蓝图
- [VERSION-ROADMAP.md §v3.1.1](VERSION-ROADMAP.md) — 版本路线图
- [docs/ztp-stack.md](docs/ztp-stack.md) — ZTP 容器栈详解
- [ops-toolkit/ztp/README.md](ops-toolkit/ztp/README.md) — ztp-server 容器使用
- [RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md) — v3.1.0 调研成果
