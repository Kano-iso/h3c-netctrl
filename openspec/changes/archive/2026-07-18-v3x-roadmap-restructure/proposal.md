# v3x-roadmap-restructure — Proposal

> **变更定位**：v3.x 大版本路线图重整
> **触发原因**：v3.0 蓝图定稿 + 骨架 change（sdn-vpc-netconf-schema-xml）已闭环，但 PRD 列的 7 个子能力 change 一直挂"⏳ 后续"未拆解归属，导致 v3.0 在路线图永远"🚧 待闭环"；v3.1 调研 change 也未做最后收尾。需将 v3.0 / v3.1.0 闭环 + v3.0 PRD 子能力按新规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4 大版本。
> **变更范围**：**纯文档类（无业务代码）** — 改 VERSION-ROADMAP.md / PRD-V3.0.md / README.md / 新建 4 个 PRD（V3.1 / V3.2 / V3.3 / V3.4）+ 新建 RELEASE-NOTES-v3.0.0.md + 收尾 v31-ztp-research archive
> **不含**：业务代码改动 / 容器改动 / 测试改动

---

## 1. 目标

按用户 2026-07-18 拍板的新规划，把 v3.x 大版本路线图理清：

| 版本 | 主题 | 状态（after）|
|---|---|---|
| **v3.0** | 骨架（业务下发通道 + 双套 payload 模板 + 跨平台验证）| ✅ tag v3.0.0 |
| **v3.1 大版本 = ZTP 整体** | — | — |
| v3.1.0 | ZTP 调研（决策 B 精简 ZTP）| ✅ tag v3.1.0 |
| v3.1.1 | ZTP 落地（1:1 静态 IP 池子 + 多平台适配）| ⏳ 下一个 change |
| v3.1.2 | controller 主动 SSH 纳管 + 推业务 IP | ⏳ |
| v3.1.3 | 资产自动可见 | ⏳ |
| **v3.2** | 加固切换 + 大迁移（架构切 EVENG + 全 QA + VPC 验证）| ⏳ |
| **v3.3** | 剩余 VPC 能力 | ⏳ |
| **v3.4** | 前端大屏 + UX | ⏳ |
| **v3.5 远期** | etcd 协调等 | ⏳ 远期 |

## 2. 范围

### 2.1 必做（本次 change 内）

- **v3.1.0 调研 change 收尾**：commit 5 收尾 + push + tag v3.1.0
- **v3.0 骨架发版闭环**：RELEASE-NOTES-v3.0.0.md 新建 + VERSION-ROADMAP.md v3.0 行 + README.md 顶部版本表 + push + tag v3.0.0
- **PRD-V3.0.md 补充**：加"v3.0 仅交付骨架，PRD 子能力按本规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4 大版本"说明
- **新建 PRD-V3.1.md**（ZTP 整体功能大版本）
- **新建 PRD-V3.2.md**（加固切换 + 大迁移）
- **新建 PRD-V3.3.md**（剩余 VPC 能力）
- **新建 PRD-V3.4.md**（前端大屏 + UX）
- **VERSION-ROADMAP.md §1 全景表 + §3 详细版本史拆分**：v3.0 / v3.1.0 / v3.1.1 / v3.1.2 / v3.1.3 / v3.2 / v3.3 / v3.4 各占章节
- **README.md 顶部版本表 + 当前架构表同步**
- **本 change archive**

### 2.2 不做（推到后续 change）

- ❌ v3.1.1 起的 ZTP 落地代码
- ❌ v3.2 EVENG 平台切换代码
- ❌ v3.3 / v3.4 实际功能代码
- ❌ 业务代码改动 / 容器改动 / 测试改动

## 3. 设计决策

### 3.1 v3.0 PRD 子能力归属拆解

| 原 sdn-* change（PRD-V3.0 7 个子能力）| 归属 |
|---|---|
| sdn-vpc-prd-and-model（数据模型 + PRD/Spec 定稿）| **v3.2**（VPC 验证时一起做）|
| sdn-vpc-foundation（VPC CRUD + 业务配置）| **v3.2**（VPC 验证时做）|
| sdn-port-binding（端口随接随入）| **v3.2**（VPC 验证时做）|
| sdn-l3vni-validation（L3VNI 状态采集）| **v3.2**（VPC 验证时做）|
| sdn-gateway-fallback（集中式网关降级/恢复）| **v3.3**（剩余 VPC 能力）|
| sdn-visual-overview（前端大屏、端口矩阵）| **v3.4**（前端集中做）|
| sdn-ops-toolkit-probes（VPC/EVPN 专用探测）| **v3.4**（工具随前端）|
| sdn-etcd-coordination（轻量协调方案）| **v3.5 远期** |

### 3.2 v3.2 大版本核心定义

- **架构切到 EVENG 平台**（用户原话"加固切换"）：利用 EVENG 提供完整 L2/L3 模拟环境，绕开真机环境受限
- **全 QA 覆盖 SDN 后端已有能力**：v2.4.2 / v2.5.0 的 QA 体系扩张到 SDN 后端全部能力
- **VPC 全能力验证**：v3.0 骨架（sdn-vpc-netconf-schema-xml）在 EVENG 环境做一次完整 VPC 验证
- 走法：v3.2 先做基础设施（EVENG 切换 + QA 体系），再做 VPC 验证

### 3.3 v3.4 前端原则

- 后端做时同步想前端 UX（不影响后端节奏）
- 前端实际实现统一放 v3.4
- 不追求十全十美（用户原话）

### 3.4 版本号风格

- 沿用 v2.x 风格（v3.0.0 / v3.1.0 / v3.1.1 这种三级版本号）
- v3.1 大版本 = ZTP 整体，v3.1.0~v3.1.3 各阶段
- v3.2 / v3.3 / v3.4 大版本各自一个 .0 发版（视子能力复杂度再拆 .0.x patch）

## 4. 验收标准

- [ ] v3.1.0 调研 change 完整归档（5 个文件 git mv + commit + push + tag v3.1.0）
- [ ] v3.0.0 骨架发版闭环（RELEASE-NOTES-v3.0.0.md + push + tag v3.0.0）
- [ ] 4 个新 PRD 文件存在且内容完整：PRD-V3.1.md / PRD-V3.2.md / PRD-V3.3.md / PRD-V3.4.md
- [ ] PRD-V3.0.md 补充"子能力拆解"说明
- [ ] VERSION-ROADMAP.md §1 全景表更新到 v3.0 / v3.1.0 / v3.1.1~.3 / v3.2 / v3.3 / v3.4
- [ ] VERSION-ROADMAP.md §3 详细版本史拆分章节
- [ ] README.md 顶部版本表 + 当前架构表同步
- [ ] 本 change `v3x-roadmap-restructure` 完整归档
- [ ] 所有 commit 走 `docs(roadmap): ...` 或 `docs(ztp): ...` 或 `docs(v3.0): ...` 前缀
- [ ] 全部 push 到 origin（需用户确认）
- [ ] git tag v3.0.0 + v3.1.0（需用户确认）
- [ ] no hardcoded credentials / no debug print / no TODO

## 5. 风险

- **风险 1：PRD-V3.0.md 改动大**：v3.0 蓝图原本是大愿景，补充"拆解说明"后措辞要小心，避免读者误以为"v3.0 没做"
  - 缓解：明确写"v3.0 = 骨架（已闭环 tag v3.0.0），子能力按本规划推到 v3.2+ 大版本"
- **风险 2：v3.1.1/2/3 都是 ⏳ 状态，没有具体 change 启动文档**
  - 缓解：本次只做"路线图标注 + PRD 蓝图"，具体 change 等下一轮启动
- **风险 3：push 时权限问题**（历史曾发生 .git/objects 权限损坏）
  - 缓解：commit 前 `sudo chown -R bytedance:bytedance .git/`（如果需要）
