# 项目规范（v2.4.2.1 强化）

> 本文档是必然被读到的项目级规范（每次 AI 启动必读），与 `.trae/rules/qa规范.md` 并列。
> **范围**：项目背景 / PRD 入口 / A/B 文档分类 / 同步时机 / 责任分工 / OpenSpec 闭环回归
> **不包含**：QA 工具/流程/凭据/排错/容器清理 → 见 [.trae/rules/qa规范.md](qa规范.md)

---

## 📋 项目背景 / PRD 入口

- **项目背景**：[`/PRD-V2.0.md`](../../PRD-V2.0.md)（v2.0 蓝图定稿）+ [`/PRD-基于NETCONF的H3C网络控制平台（个人自研项目）V1.0.md`](../../PRD-基于NETCONF的H3C网络控制平台（个人自研项目）V1.0.md)（v1.0 MVP）
- **大方向 + 远期愿景**：[`/VERSION-ROADMAP.md`](../../VERSION-ROADMAP.md) §1 全景表 + §v3.0 VPC + **§12 远期愿景**（v2.4.2.1 加）
- **历史快照**：[`/openspec/changes/archive/`](../../openspec/changes/archive/)
- **当前发版**：见 [`/README.md`](../../README.md) 顶部版本表

---

## 📚 A/B 文档分类（v2.4.2.1 强化）

### A. 长期维护文档（**项目级别**，指导未来演进）

- **位置**：根目录 + `docs/`，文件名稳定，更新 = 在原文件追加新节
- **数量**：**3 项**（精简后）——多了 = 不可维护，少了 = 缺指导
- **特征**：被 AI 启动时 + README / VERSION-ROADMAP / 工具 / QA 流程引用
- **失效后果**：项目级"将来念想"丢失 / 项目门面过时

### B. 临时性文档（仅在 1 个 change 或 1 个发版中使用）

- **位置**：`openspec/changes/<id>/` 下（change 内） + 根目录 `RELEASE-NOTES-vX.Y.Z.md`（每发版新建 1 个） + `docs/REVIEW-*` / `docs/PERF-*`（按需）
- **特征**：发版时新建 1 个，文件本身不被"维护"
- **失效后果**：与 A 类混 = 维护成本指数上升

### C. 规则类（一次定稿，不跟版本走，但 AI 启动必读）

- **位置**：`.trae/rules/`
- **特征**：定稿后不跟版本走，但仍是 AI 启动必读
- **C 类 ≠ A 类**：A 类跟项目演进，C 类是"准入规则"
- **示例**：`.trae/rules/qa规范.md`（QA 工具/流程/凭据/排错/容器清理）+ `.trae/rules/project-convention.md`（本文档）

---

## 📋 A 类：长期维护文档清单（**3 项**，项目级别）

| # | 路径 | 名字 | 作用 | 更新时机 |
|---|------|------|------|----------|
| 1 | [`/README.md`](../../README.md) | 项目说明 | **项目门面**（顶部版本表 + 当前架构表）| 每发版同步 |
| 2 | [`/VERSION-ROADMAP.md`](../../VERSION-ROADMAP.md) | 版本路线图 | **版本史 + 大方向 + 远期愿景**（§1 全景表 + §3 详细版本史 + §12 远期愿景）| 每发版加 §X.Y.Z 章节 + §1 加 1 行 + 远期愿景按需 |
| 3 | `/PRD-V*.md` | 蓝图定稿 | **PRD（v1.0 / v2.0 已定稿）**——记录当时的产品愿景 / 业务边界 / 功能清单 | 大版本启动时新建 |

---

## 📂 B 类：临时性文档（按需新建，不算长期维护）

| 类型 | 位置 | 处理 |
|------|------|------|
| **发版说明** | `/RELEASE-NOTES-vX.Y.Z.md` | 每发版新建 1 个（文件本身不被"维护"，下次发版新建下一个）|
| **Review 报告** | `/docs/REVIEW-vXYZ-*.md` | 每个 review 周期新建（v2.4.2 已有 1 个）|
| **压测报告** | `/docs/PERF-RESULTS-vX.Y.Z.md` | 每次压测新建（v2.4.2 已有 1 个）|
| **change proposal / design / tasks** | `openspec/changes/<id>/` | archive 迁到 `archive/<date>-<id>/`（**保留**）|
| **调研笔记 / 临时指引** | `openspec/changes/<id>/notes.md` | archive 时**删除**（不归档）|

---

## 🔄 同步触发时机（3 个 checkpoint）

### Checkpoint 1: change archive 闭环前

- 涉及 A 类（README / VERSION-ROADMAP / PRD）变化 → 必同步
- 涉及 C 类（qa 规范 / project-convention）变化 → 必同步
- 涉及工具 / 流程 / 容器职责变化 → 必同步对应 docs 章节

### Checkpoint 2: tag 前（commit + push 前）

- `RELEASE-NOTES-vX.Y.Z.md` 写完（commit 序列 + 测试统计 + 真机示例）
- `VERSION-ROADMAP.md` 加 §X.Y.Z 章节 + §1 全景表加 1 行
- `README.md` 顶部版本表 + 当前架构表同步

### Checkpoint 3: 半年 / 全年 review

- `docs/REVIEW-vXYZ-*.md` 写完整版本 review
- 三大表（容器 / 工具 / QA）是否还准确
- `project_memory.md` 是否需要新增 lessons learned

---

## 👥 责任分工

| 角色 | 责任范围 |
|------|----------|
| **每次发版（必做）** | A 类（README / VERSION-ROADMAP）+ B 类（RELEASE-NOTES）+ change archive |
| **每次 change archive（按 change 类型）** | A 类（VERSION-ROADMAP 加 §）+ C 类（qa / convention 同步）|
| **每次大版本 review** | A 类（VERSION-ROADMAP §12 远期愿景调整）+ `docs/REVIEW-*` + `project_memory` lessons learned |
| **AI 启动时** | 必读 C 类（`.trae/rules/qa规范.md` + `.trae/rules/project-convention.md`）|

---

## 🔁 OpenSpec 流程闭环回归清单

当 change 走完 Apply + Archive 阶段后，必须按以下顺序回归检查（对应 Checkpoint 1 + 2）：

### 1. 自查

- [ ] `git status` 干净
- [ ] `openspec/changes/` 目录无未 archive 的 change（除当前正在做的）
- [ ] 涉及 A 类（README / VERSION-ROADMAP / PRD）变化 → 必查
- [ ] 涉及 C 类（qa 规范 / project-convention）变化 → 必查

### 2. 文档同步（A 类清单必查）

- [ ] **`RELEASE-NOTES-vX.Y.Z.md`** 写完（含 commit 序列 + 测试统计 + 真机示例）
- [ ] **`VERSION-ROADMAP.md`** 加 §X.Y.Z 章节 + §1 全景表加 1 行
- [ ] **`README.md`** 顶部版本表 + 当前架构表同步

### 3. 提交与发版

- [ ] git tag vX.Y.Z + push（**需用户确认**）
- [ ] change archive 闭环（`git mv openspec/changes/<id>/ → archive/<date>-<id>/`）
- [ ] 通知用户 review，等待反馈后再 push

---

## 📌 一句话总结

> **A 类（3 项）= 项目骨架**（每发版必同步）——指导未来演进
> **B 类 = 一次性用品**（按需新建）——RELEASE-NOTES / REVIEW / PERF / change 内文档
> **C 类（2 项）= 准入规则**（AI 启动必读）——qa 规范 / project-convention
> **A / B / C 三类不混**。

