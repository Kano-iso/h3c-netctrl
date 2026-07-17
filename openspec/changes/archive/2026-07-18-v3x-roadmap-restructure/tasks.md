# v3x-roadmap-restructure — Tasks

> **变更定位**：v3.x 大版本路线图重整
> **每个 Task = 1 commit**（按 OpenSpec "小步增量" 规范）
> **本 change 不写业务代码**（仅文档拆分 + 发版收尾）

---

## Task 1: v3.1.0 调研 change 收尾（T1）

**目的**：把 v31-ztp-research 调研 change 的最后 1 个 commit 补上 + push + tag v3.1.0。

**步骤**：
- [x] 写 `openspec/changes/v3x-roadmap-restructure/proposal.md` + `tasks.md` + `design.md`（本 change 自身）
- [ ] 修改 `VERSION-ROADMAP.md`（v3.1 行 + §3.1 章节已就位）
- [ ] git mv `openspec/changes/v31-ztp-research/*` → `openspec/changes/archive/2026-07-18-v31-ztp-research/`（5 个文件）
- [ ] 1 个 commit: `docs(ztp): T5 决策报告 + archive + 同步 3 处 A 类文档`
- [ ] push 到 origin（需用户确认）
- [ ] git tag v3.1.0（需用户确认）
- [ ] 1 个 commit: `docs(roadmap): v3.1.0 tag 标注（VERSION-ROADMAP 加 tag 行）`（如果 tag 后需要再改文档）

**T1 验收**：
- [ ] v31-ztp-research 5 个文件全部 git mv 到 archive
- [ ] VERSION-ROADMAP.md §1 全景表 v3.1 行有 "tag v3.1.0" 标注
- [ ] origin 上有 v3.1.0 tag
- [ ] no untracked 文件

---

## Task 2: v3.0 骨架发版闭环（T2）

**目的**：v3.0.0 骨架（sdn-vpc-netconf-schema-xml change）作为独立大版本 tag 发版。

**步骤**：
- [ ] 新建 `RELEASE-NOTES-v3.0.0.md`（骨架发版说明）
- [ ] 修改 `VERSION-ROADMAP.md` §1 全景表 v3.0 行（状态 ✅ tag v3.0.0）
- [ ] 修改 `VERSION-ROADMAP.md` §3 详细版本史加 v3.0 章节
- [ ] 修改 `README.md` 顶部版本表（v3.0.0 行）+ 当前架构表
- [ ] 1 个 commit: `docs(v3.0): v3.0.0 骨架发版（sdn-vpc-netconf-schema-xml change 闭环）`
- [ ] push 到 origin（需用户确认）
- [ ] git tag v3.0.0（需用户确认）

**T2 验收**：
- [ ] RELEASE-NOTES-v3.0.0.md 写完（含 commit 序列 + 测试统计 + 关键产出）
- [ ] VERSION-ROADMAP.md v3.0 行有 "tag v3.0.0" 标注
- [ ] README.md 顶部版本表有 v3.0.0 行
- [ ] origin 上有 v3.0.0 tag

---

## Task 3: PRD 拆分（T3）

**目的**：v3.0 PRD 补充"子能力拆解说明" + 新建 4 个 v3.1~v3.4 PRD 蓝图。

**步骤**：
- [ ] 修改 `PRD-V3.0.md`（在文件开头加"v3.0 实际交付范围" + "v3.0 PRD 子能力拆解到 v3.1.1 / v3.2 / v3.3 / v3.4"说明）
- [ ] 新建 `PRD-V3.1.md`（ZTP 整体功能大版本蓝图：v3.1.0 调研 + v3.1.1 落地 + v3.1.2 纳管 + v3.1.3 可见）
- [ ] 新建 `PRD-V3.2.md`（加固切换 + 大迁移：EVENG 平台 + 全 QA + VPC 全能力验证）
- [ ] 新建 `PRD-V3.3.md`（剩余 VPC 能力：端口随接随入 / L3VNI / 集中式网关）
- [ ] 新建 `PRD-V3.4.md`（前端大屏 + UX）
- [ ] 1 个 commit: `docs(roadmap): v3.x PRD 拆分（V3.0 收口 + V3.1~V3.4 新建）`

**T3 验收**：
- [ ] 5 个 PRD 文件存在（PRD-V3.0.md 改 + 4 个新 PRD）
- [ ] 每个 PRD 包含：目标 / 范围 / 设计决策 / 验收标准（按 OpenSpec 规范）
- [ ] v3.0 PRD 补充说明清楚"v3.0 = 骨架，子能力按本规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4"
- [ ] 4 个新 PRD 内容相互引用关系清晰（v3.2 依赖 v3.1.1 收尾 / v3.3 依赖 v3.2 验证 / v3.4 跟随）

---

## Task 4: VERSION-ROADMAP v3.x 详细版本史拆分（T4）

**目的**：VERSION-ROADMAP.md §3 详细版本史把 v3.x 大版本按版本号拆分章节。

**步骤**：
- [ ] 改 `VERSION-ROADMAP.md` §1 全景表更新（v3.0 / v3.1.0 / v3.1.1 / v3.1.2 / v3.1.3 / v3.2 / v3.3 / v3.4 各占一行）
- [ ] 改 `VERSION-ROADMAP.md` §3 详细版本史：
  - §v3.0 骨架
  - §v3.1 ZTP 整体
  - §v3.2 加固切换
  - §v3.3 剩余 VPC
  - §v3.4 前端
- [ ] 1 个 commit: `docs(roadmap): VERSION-ROADMAP v3.x 详细版本史拆分`

**T4 验收**：
- [ ] VERSION-ROADMAP.md §1 全景表 8 行（v3.0 / v3.1.0 / v3.1.1 / v3.1.2 / v3.1.3 / v3.2 / v3.3 / v3.4）
- [ ] VERSION-ROADMAP.md §3 各章节内容完整
- [ ] 链接可落地（指向 archive 目录 / PRD 文件 / RELEASE-NOTES）

---

## Task 5: archive 本 change（T5）

**目的**：v3x-roadmap-restructure change 闭环。

**步骤**：
- [ ] git mv `openspec/changes/v3x-roadmap-restructure/` → `openspec/changes/archive/2026-07-18-v3x-roadmap-restructure/`
- [ ] 1 个 commit: `docs(roadmap): v3x-roadmap-restructure change 闭环`
- [ ] push 到 origin（需用户确认）

**T5 验收**：
- [ ] `openspec/changes/` 目录无未 archive 的 change（除当前正在做的）
- [ ] `openspec/changes/archive/2026-07-18-v3x-roadmap-restructure/` 目录有完整 3 文件
- [ ] git status 干净

---

## 验收 checklist

- [ ] T1: v3.1.0 调研 change 完整归档 + push + tag v3.1.0
- [ ] T2: v3.0.0 骨架发版闭环 + push + tag v3.0.0
- [ ] T3: 5 个 PRD 文件完整（V3.0 改 + V3.1~V3.4 新建）
- [ ] T4: VERSION-ROADMAP.md v3.x 拆分章节完整
- [ ] T5: 本 change archive
- [ ] 5 个 commit 顺序与 task 顺序一致
- [ ] 每个 commit 仅含对应 task 的文档改动（不跨 task 攒 commit）
- [ ] 全部 push 到 origin（需用户确认）
- [ ] git tag v3.0.0 + v3.1.0（需用户确认）
- [ ] 文档链接可落地（无断链）
- [ ] no hardcoded credentials / no debug print / no TODO

## Commit 格式（5 个 commit）

```
1. docs(ztp): T5 决策报告 + archive + 同步 3 处 A 类文档  (T1)
2. docs(v3.0): v3.0.0 骨架发版（sdn-vpc-netconf-schema-xml change 闭环）  (T2)
3. docs(roadmap): v3.x PRD 拆分（V3.0 收口 + V3.1~V3.4 新建）  (T3)
4. docs(roadmap): VERSION-ROADMAP v3.x 详细版本史拆分  (T4)
5. docs(roadmap): v3x-roadmap-restructure change 闭环  (T5)
```
