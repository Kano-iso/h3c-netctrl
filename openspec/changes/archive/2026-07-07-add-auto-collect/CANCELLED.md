# add-auto-collect — CANCELLED（2026-07-07）

**状态**：⛔ 取消，未实施。

**取消原因（v2.6.0 复盘）**：

v2.6.0 subagent 一次跑出 9 commit 但 qa-backend / 真机都没真验证。add-auto-collect 的 9 task 拆细版**只是 planning，没有实际 commit**（`cfdaeb2 chore(openspec): add-auto-collect proposal + 2 个 bug 草稿` 仅 proposal + bug 草稿，不是功能实现）。

v2.6.1 闭环时（fix-asset-stale-status / fix-asset-collect-failure 已实施）：
- **自动降级机制**（ASSET_STALE_HOURS + dashboard 阈值过滤）已替代"自动采集保持数据新鲜"的初衷
- 即使不自动采集，data 容器也能按阈值把过期数据降为 offline，dashboard 不会再现陈旧 online 计数
- "自动采集"变成 nice-to-have，不再是 v2.6.1 的 P0

**复盘结论**：

> v2.6.0 复盘反思 + v2.6.1 实施经验：**子 change 拆细 + 真机验证 + 单独 qa 跑通** 是闭环底线。
> add-auto-collect 只有 proposal 没 commit，违反"先有 Spec 再有代码"的项目硬约束。
> 砍掉不 archive 不浪费（v2.6.1 已有替代方案），但保留 proposal 备查（v2.6.2 重新评估）。

**v2.6.2 backlog 评估**：

- **重新评估条件**：用户对 dashboard online 计数有更严格要求（如要求"15 分钟内必须新鲜"），或定时采集成为合规需求
- **重新评估时**：从 v2.6.1 实施的 AutoCollectScheduler 设计（已在 v2.6.1 fix-asset-collect-failure 的 backup-internal-api 路径上跑通）出发，**只补全 proposal → Apply 链路**
- **重做原则**：单 task = 1 commit + 1 qa-backend 真跑 + 1 报告，禁止 subagent 一次过

**本 archive 内容**：
- `proposal.md` — 原 v2.6.0 复盘后的 9 task 拆细规划（保留作 v2.6.2 起点）
- `specs/` — delta spec 草稿（保留作 v2.6.2 起点）
- `tasks.md` — 9 task 全部 ⏳ 状态（**未实施**）

**未 archive 到 openspec/specs/**：因为无实际实施，无 main spec 可写。

---

**状态时间线**：
- 2026-07-06：v2.6.0 复盘后写入（v261-roadmap 子 change 5）
- 2026-07-07：v2.6.1 闭环时砍掉，本 archive 创建
- 待定：v2.6.2 重新评估（按需）
