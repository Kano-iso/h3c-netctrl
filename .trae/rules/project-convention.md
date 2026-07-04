# 项目规范（v2.4.2.1 强化）

> 本文档是必然被读到的项目级规范（每次 AI 启动必读），与 `.trae/rules/qa规范.md` 并列。
> **范围**：项目背景 / PRD 入口 / A/B 文档分类 / 同步时机 / 责任分工 / OpenSpec 闭环回归
> **不包含**：QA 工具/流程/凭据/排错/容器清理 → 见 [.trae/rules/qa规范.md](qa规范.md)

---

## 📋 项目背景 / PRD 入口

- **项目背景**：[`/PRD-V2.0.md`](../../PRD-V2.0.md)（v2.0 蓝图定稿）+ [`/PRD-基于NETCONF的H3C网络控制平台（个人自研项目）V1.0.md`](../../PRD-基于NETCONF的H3C网络控制平台（个人自研项目）V1.0.md)（v1.0 MVP）
- **大方向**：[`/VERSION-ROADMAP.md` §1 全景表](../../VERSION-ROADMAP.md) + `§v3.0 VPC`
- **未来演进**：[`/VERSION-ROADMAP.md` §v2.5 backlog](../../VERSION-ROADMAP.md) + `§v3.0 VPC`
- **历史快照**：[`/openspec/changes/archive/`](../../openspec/changes/archive/)
- **当前发版**：见 [`/README.md`](../../README.md) 顶部版本表

---

## 📚 A/B 文档分类（v2.4.2.1 强化）

### A. 长期维护文档（每次发版前必同步）

- **位置**：根目录 + `docs/`，文件名稳定，更新 = 在原文件追加新节
- **特征**：被 README / VERSION-ROADMAP / 工具 / QA 流程引用
- **失效后果**：链接断链 / 工具路径错 / QA 流程不一致

### B. 临时性文档（仅在 1 个 change 内使用）

- **位置**：`openspec/changes/<id>/` 下，change archive 闭环后**删除**（不是归档）
- **特征**：指引 / 笔记 / 中间稿 / 调研，只服务于当前 change
- **失效后果**：污染 OpenSpec 目录、影响其他 change 查找

---

## 📋 A 类：长期维护文档清单（15 项）

| # | 路径 | 名字 | 更新时机 | 谁负责 |
|---|------|------|----------|--------|
| 1 | [`/README.md`](../../README.md) | 项目说明 | 每发版同步顶部版本表 + 当前架构表 | 每次发版 |
| 2 | [`/VERSION-ROADMAP.md`](../../VERSION-ROADMAP.md) | 版本路线图 | 每发版加 §X.Y.Z 章节 + §1 全景表加 1 行 | 每次发版 |
| 3 | [`/RELEASE-NOTES-vX.Y.Z.md`](../../RELEASE-NOTES-v2.4.2.1.md) | 发版说明（每版 1 个） | 发版时新建 | 每次发版 |
| 4 | `/PRD-V*.md` | 蓝图定稿（V1.0 / V2.0 已定稿） | 大版本启动时新建 | 大版本启动 |
| 5 | [`/docs/CONTAINER-INVENTORY.md`](../../docs/CONTAINER-INVENTORY.md) | 容器基线清单 | 容器变化时 | 容器变更 |
| 6 | [`/docs/CONTAINER-DECOUPLING.md`](../../docs/CONTAINER-DECOUPLING.md) | 容器解耦蓝图 | v2.4.1 实施后基本稳定 | 大版本变化 |
| 7 | [`/docs/CONTAINER-CLEANUP-SOP.md`](../../docs/CONTAINER-CLEANUP-SOP.md) | 容器清理 SOP | SOP 变化时 | 清理流程变化 |
| 8 | [`/docs/QA-GUIDE.md`](../../docs/QA-GUIDE.md) | QA 流程指南 | QA 流程变化时 | QA 流程变化 |
| 9 | [`/docs/ops-toolkit.md`](../../docs/ops-toolkit.md) | 运维工具手册 | 工具新增 / 用法变化 | 工具变化 |
| 10 | `/docs/REVIEW-vXYZ-*.md` | Review 报告 | 每个 review 周期新建 | Review 周期 |
| 11 | `/docs/PERF-RESULTS-vX.Y.Z.md` | 压测报告 | 每次有压测时新建 | 压测完成 |
| 12 | [`/docs/implementation.md`](../../docs/implementation.md) | 开发者文档 | 与代码同步 | 代码变化 |
| 13 | [`/docs/tutorial.md`](../../docs/tutorial.md) | 教程 | 教程内容变化 | 教程更新 |
| 14 | [`.trae/rules/qa规范.md`](qa规范.md) | 必然被读的项目规则 | 任何工具/脚本/规范变化必同步 | 任何变化 |
| 15 | `/openspec/specs/<name>/spec.md` | 沉淀后的 spec | vN.0 大变更时 | 大版本 |

---

## 📂 B 类：临时性文档（change 内使用，archive 后删除）

| 类型 | 位置 | 处理 |
|------|------|------|
| change proposal / design / tasks | `openspec/changes/<id>/` | archive 迁到 `archive/<date>-<id>/`（**保留**）|
| **调研笔记 / 中间稿** | `openspec/changes/<id>/notes.md` | archive 时**删除**（不归档）|
| **临时指引 / README** | `openspec/changes/<id>/README.md` | archive 时**删除**（不归档）|
| **临时截图 / 草稿** | `openspec/changes/<id>/screenshots/` | archive 时**删除**（不归档）|

> 原则：`archive/` 目录 = 历史快照（**不删除**）；change 内临时笔记 = 服务当前 change，archive 后失效

---

## 🔄 同步触发时机（3 个 checkpoint）

### Checkpoint 1: change archive 闭环前

- 涉及 `docs/CONTAINER-INVENTORY.md` / `ops-toolkit.md` / `QA-GUIDE.md` 变化 → 必同步
- 涉及新工具 / 新测试 / 新排错规范 → 必同步 [qa规范.md](qa规范.md)
- 涉及架构变化 → 必同步 `CONTAINER-DECOUPLING.md` + `README.md` 当前架构表

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
| **每次发版（必做）** | README + VERSION-ROADMAP + RELEASE-NOTES + change archive |
| **每次 change archive（按 change 类型）** | docs/* 涉及章节 + qa 规范 |
| **每次大版本 review** | docs/REVIEW-* + 三大表清理 + project_memory lessons learned |
| **AI 启动时** | 必读 `.trae/rules/qa规范.md` + `.trae/rules/project-convention.md`（**A 类的"准入检查表"**）|

---

## 🔁 OpenSpec 流程闭环回归清单

当 change 走完 Apply + Archive 阶段后，必须按以下顺序回归检查（对应 Checkpoint 1 + 2）：

### 1. 自查

- [ ] `git status` 干净
- [ ] `openspec/changes/` 目录无未 archive 的 change（除当前正在做的）
- [ ] 涉及 docs/* 章节的 change → 必查对应 docs 同步
- [ ] 涉及工具 / 脚本 / QA / 凭据规范变化 → 必查 qa 规范同步

### 2. 文档同步（A 类清单必查）

- [ ] **`RELEASE-NOTES-vX.Y.Z.md`** 写完（含 commit 序列 + 测试统计 + 真机示例）
- [ ] **`VERSION-ROADMAP.md`** 加 §X.Y.Z 章节 + §1 全景表加 1 行
- [ ] **`README.md`** 顶部版本表 + 当前架构表同步
- [ ] **本文档**（A 类清单）涉及 → 必查 + 同步

### 3. 提交与发版

- [ ] git tag vX.Y.Z + push（**需用户确认**）
- [ ] change archive 闭环（`git mv openspec/changes/<id>/ → archive/<date>-<id>/`）
- [ ] 通知用户 review，等待反馈后再 push

---

## 📌 一句话总结

> **A 类 = 项目骨架**（每次发版前同步）；**B 类 = change 内一次性用品**（archive 后删除）。两类不混。
> **qa 规范 + 本文档 = AI 启动的"准入检查表"**（必然被读 → 强制力最强）。
