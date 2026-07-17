# v3x-roadmap-restructure — Design

> **变更定位**：v3.x 大版本路线图重整
> **核心问题**：v3.0 蓝图定稿 + 骨架（sdn-vpc-netconf-schema-xml）已闭环，但 PRD 7 个子能力 change 全"⏳ 后续"未拆解归属；v3.1 调研 change 也未做最后收尾。需把 v3.0 / v3.1.0 闭环 + v3.x 后续按新规划拆到独立大版本。

---

## 1. 背景与现状

### 1.1 v3.0 现状

- ✅ **PRD-V3.0.md**（2026-06-30 起草，2026-07-18 增量更新）：蓝图定稿，写了 VPC 能力 / 端口随接随入 / 分布式网关 / 状态校验闭环等愿景
- ✅ **sdn-vpc-netconf-schema-xml** change（2026-07-16 archive）：骨架闭环
  - 业务下发通道选型（L3vpn schema + L2vpn 按 device.platform 路由 LSTN→SSH / RSTN→NETCONF）
  - 双套 payload 模板（5 unit × 4 字段）
  - 跨平台真机验证（.5 LSTN/SSH + .26 RSTN/NETCONF）
  - 73 SDN 单测 + 全量 432 PASS / 3 pre-existing FAIL
  - 42 commits push to origin/main
- ⏳ 7 个子能力 change 全"后续"未起：
  - sdn-vpc-prd-and-model
  - sdn-vpc-foundation
  - sdn-l3vni-validation
  - sdn-port-binding
  - sdn-gateway-fallback
  - sdn-visual-overview
  - sdn-ops-toolkit-probes
  - sdn-etcd-coordination

### 1.2 v3.1 现状

- ✅ **v31-ztp-research** change（2026-07-18 archive 阶段）：ZTP 调研完成
  - 5 个 task 内容已写：T1 文档调研 / T2 真机探针 / T3 独立 ztp-server 容器基建 / T4 .177 真机验证 / T5 决策 B 精简 ZTP
  - 3 个 commit 已 push：`5c8748a` (T1+T2) / `b9e316c` (T3) / `ebe1565` (T4)
  - ⏳ Commit 5（T5 + archive）待做

### 1.3 根本问题

- v3.0 在 VERSION-ROADMAP.md 一直"🚧 待闭环"（sdn-vpc-netconf-schema-xml 已闭环但 PRD 子能力没拆解归属）
- v3.1 在 VERSION-ROADMAP.md 也"🚧 待闭环"（5 个 commit 还差 1 个）
- 用户视角：发到 v3.1 了但 v3.0 还有大量子能力"未实现"，版本管理混乱

## 2. 重整方案

### 2.1 v3.x 大版本号方案（用户拍板）

| 版本 | 主题 | 关键内容 | 状态 |
|---|---|---|---|
| **v3.0** | 骨架 | sdn-vpc-netconf-schema-xml 闭环 | ✅ tag v3.0.0 |
| **v3.1 大版本 = ZTP 整体** | — | — | — |
| v3.1.0 | ZTP 调研 | 决策 B 精简 ZTP | ✅ tag v3.1.0 |
| v3.1.1 | ZTP 落地 | 1:1 静态 IP 池子 + 多平台适配 | ⏳ |
| v3.1.2 | 自动纳管 | controller 主动 SSH 纳管 + 推业务 IP | ⏳ |
| v3.1.3 | 资产可见 | 设备主动注册到后端 + 白屏可见 | ⏳ |
| **v3.2** | 加固切换 + 大迁移 | 架构切 EVENG + 全 QA + VPC 全能力验证 | ⏳ |
| **v3.3** | 剩余 VPC 能力 | 端口随接随入 / L3VNI / 集中式网关 | ⏳ |
| **v3.4** | 前端大屏 + UX | 大屏 / 端口矩阵 / 用户体验 | ⏳ |
| **v3.5 远期** | etcd 协调等 | sdn-etcd-coordination | ⏳ 远期 |

### 2.2 v3.0 PRD 子能力归属

| 原 sdn-* change（PRD-V3.0 7 个子能力）| 归属大版本 | 理由 |
|---|---|---|
| sdn-vpc-prd-and-model（数据模型 + PRD/Spec 定稿）| **v3.2** | 数据模型 + VPC 验证时一起做 |
| sdn-vpc-foundation（VPC CRUD + 业务配置）| **v3.2** | VPC 全能力验证时做 |
| sdn-port-binding（端口随接随入）| **v3.2** | VPC 全能力验证时做 |
| sdn-l3vni-validation（L3VNI 状态采集）| **v3.2** | VPC 全能力验证时做 |
| sdn-gateway-fallback（集中式网关降级/恢复）| **v3.3** | 剩余 VPC 能力 |
| sdn-visual-overview（前端大屏、端口矩阵）| **v3.4** | 前端集中做 |
| sdn-ops-toolkit-probes（VPC/EVPN 专用探测）| **v3.4** | 工具随前端 |
| sdn-etcd-coordination（轻量协调方案）| **v3.5 远期** | 远期评估 |

### 2.3 v3.2 大版本定义

按用户原话："v3.2 这里 3.2 我们会做一个是加固切换，3.2 叫加固切换，配合 ztp 的能力，做架构切换，切换到 eveng 平台。3.2 的时 候呢，把所有的 qa 做了，就是包括 sdn 的后端现在已有能力，就是有一些没实现的能力先不管啊，已有能力先都做一遍"

**v3.2 三件大事**：

1. **架构切换到 EVENG 平台**
   - 原因：当前 .26 / .5 真机环境受限（L2 模拟环境不完整）
   - EVENG = 完整 L2/L3 模拟环境（开源网络仿真平台）
   - 切换后所有 SDN 业务可在 EVENG 验证

2. **全 QA 覆盖 SDN 后端已有能力**
   - 把 v2.4.2 / v2.5.0 的 QA 体系扩张到 SDN 后端全部能力
   - 集成测试 + e2e + 性能压测

3. **VPC 全能力验证**
   - 在 EVENG 环境做一次完整 VPC 验证
   - 覆盖 v3.0 骨架能力 + 部分 PRD 子能力（sdn-vpc-prd-and-model / foundation / port-binding / l3vni-validation）
   - 验证后正式收编 v3.0 PRD 这部分子能力

**v3.2 走法**：
- 阶段 1：EVENG 平台接入 + 测试用例迁移
- 阶段 2：SDN 后端 QA 体系扩张
- 阶段 3：VPC 全能力 EVENG 验证
- 阶段 4：v3.2 整体发版 tag v3.2.0

### 2.4 v3.3 / v3.4 大版本定义

**v3.3 剩余 VPC 能力**：
- 端口随接随入（sdn-port-binding 剩余）
- L3VNI 状态采集（sdn-l3vni-validation 剩余）
- 集中式网关降级/恢复（sdn-gateway-fallback）
- 内容量视实际情况定

**v3.4 前端大屏 + UX**：
- 大屏 / 端口矩阵 / VPC 详情
- 后端做时同步想前端 UX（不影响后端节奏）
- 不追求十全十美（用户原话）
- sdn-visual-overview + sdn-ops-toolkit-probes 工具随前端

### 2.5 文档结构

| 文档 | 位置 | 作用 |
|---|---|---|
| **PRD-V3.0.md** | 根目录 | 改：补充"v3.0 = 骨架，子能力按本规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4" |
| **PRD-V3.1.md** | 根目录 | 新建：ZTP 整体大版本蓝图 |
| **PRD-V3.2.md** | 根目录 | 新建：加固切换 + 大迁移蓝图 |
| **PRD-V3.3.md** | 根目录 | 新建：剩余 VPC 能力蓝图 |
| **PRD-V3.4.md** | 根目录 | 新建：前端大屏 + UX 蓝图 |
| **VERSION-ROADMAP.md** | 根目录 | 改：§1 全景表 + §3 详细版本史拆分 |
| **README.md** | 根目录 | 改：顶部版本表 + 当前架构表 |
| **RELEASE-NOTES-v3.0.0.md** | 根目录 | 新建：骨架发版说明 |
| **RELEASE-NOTES-v3.1.0.md** | 根目录 | 已有：调研发版说明（待 commit） |
| **openspec/changes/archive/2026-07-18-v3x-roadmap-restructure/** | openspec/ | 本 change archive |

## 3. 关键决策记录

### 3.1 为什么 v3.0 独立 tag v3.0.0 而不是 v3.0.0.x patch 拆分

用户原话："已经到点一了，就不可能往点零退了呀" + "不能发着 3.1 的板，回去又发 3.0 的板"。

→ v3.0 独立 tag，v3.1 独立 tag，v3.2 / v3.3 / v3.4 也独立 tag。
→ 不在 v3.0 大版本内部拆 v3.0.0 / v3.0.1 / v3.0.2（避免版本号回退 + 用户视角混乱）。

### 3.2 为什么 v3.1 是大版本而不是 v3.0.1 patch

v3.1 ZTP 是**新功能**（不是 v3.0 骨架的 patch），独立成大版本更清晰。

### 3.3 为什么 v3.2 包含 EVENG 平台切换

用户原话："v3.2 加固切换，配合 ztp 的能力，做架构切换，切换到 eveng 平台"。

→ EVENG 切换是 v3.2 核心动作。
→ 不放到 v3.0 / v3.1（时机不对，v3.0 骨架已闭环，v3.1 ZTP 不依赖 EVENG）。

### 3.4 为什么前端不跟后端每个 change 走

用户原话："3.4 做前端其实我觉得这个前端的逻辑也很重要啊，这也是我们之前提到的，要在 3.0 版本和 3.3 版本的时候，做后端功能的时候，考虑到前端到时候怎么逻辑，考虑到用户体验... 但是你也不可能往十全十美，这个在后面再考虑吧"。

→ 后端做时想前端 UX（写在 PRD / design.md 注释里），但前端实现统一放 v3.4。
→ v3.4 = 前端大屏 + UX 集中实现。

## 4. 不做（明确边界）

- ❌ 不写业务代码（本次 change 纯文档）
- ❌ 不动容器 / 测试 / 工具
- ❌ 不重启 v3.1.1 / v3.2 / v3.3 / v3.4 任何具体 change（仅在 PRD 中描述）
- ❌ 不修历史 archive change 的 docs（仅新建 PRD + 改当前版本相关 A 类文档）
