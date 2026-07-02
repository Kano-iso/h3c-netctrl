# v24-fix-batch-async-backup

> **类型**：bugfix（v2.4.0 遗漏）
> **优先级**：P0
> **前序**：v2.4.0 (tag v2.4.0, 2026-07-02)

---

## Why

v2.4.0 实现了单设备异步备份（`v24-feat-async-backup-status`），但**全量备份**漏了。

**现象**：
- 单设备"立即备份"→ 弹窗立即关闭 + BackgroundTaskPanel 显示转圈 ✓
- 全量"立即全量备份"→ 按钮转圈阻塞 + 无 BackgroundTaskPanel + 切页面丢状态 ✗

**根因**：
- [Backup.vue#L132-L148](../../../frontend/src/views/Backup.vue#L132-L148) `handleFullBackup` 调同步端点 `backupApi.createAll()`（`POST /api/backups`）
- [CMDB.vue#L123-L136](../../../frontend/src/views/CMDB.vue#L123-L136) 同理
- 两个页面都没接 ASYNC_MODE 分支，`fullBackingUp` 是组件局部状态，切页面就丢

---

## What Changes

### 前端 only（不改后端）

复用已有的 `POST /api/devices/{id}/backup-async` 端点。ASYNC 模式下，全量备份 = 循环所有设备，每个设备调 `taskStore.submitBackup()`。

**改动范围**：
1. `frontend/src/views/Backup.vue` — `handleFullBackup` 加 ASYNC 分支
2. `frontend/src/views/CMDB.vue` — `handleFullBackup` 加 ASYNC 分支 + import taskStore
3. `frontend/src/stores/task.js` — 加 `submitBatchBackup(deviceList, types)` 便捷方法（循环调 submitBackup）

**ASYNC 模式行为**：
- 点"立即全量备份"→ 立即为每台设备提交一个异步任务 → 按钮不阻塞
- BackgroundTaskPanel 显示 N 个任务（第 1 个 running，其余 pending，串行执行）
- 切页面不丢（Pinia 全局 + localStorage 持久化）
- 不弹全量结果 Modal（每任务在 BackgroundTaskPanel 独立显示结果）

**同步模式**：保持 v2.3 行为不变（阻塞 + 结果 Modal）

---

## Design Decisions

### D1: 不新建后端批量异步端点

**选 A（推荐）**：前端循环调 N 次 `POST /backup-async`
- 优点：不改后端，复用已有端点 + TaskManager 串行保证 SQLite 安全
- 缺点：N 台设备 = N 个 task（BackgroundTaskPanel 显示 N 条）

**选 B**：新建 `POST /api/backup-all-async` 后端批量端点
- 优点：1 个批量 task，BackgroundTaskPanel 显示 1 条
- 缺点：后端要改，且批量 task 内部还是要循环 N 台设备

**决策**：选 A。个人轻量项目，N 条 task 比 1 条批量 task 更直观（每台设备独立进度/结果）。TaskManager max_workers=1 保证串行，不会 SQLite 冲突。

### D2: 不弹全量结果 Modal

ASYNC 模式下，每台设备的备份结果在 BackgroundTaskPanel 独立显示（成功显示"新增 X 份备份"，失败显示错误信息）。全量结果 Modal 是同步模式的聚合视图，异步模式不需要。

### D3: fullBackingUp 状态

ASYNC 模式下 `fullBackingUp` 不再需要（按钮不阻塞）。保留变量但 ASYNC 分支直接 return。

---

## Acceptance Criteria

- [ ] ASYNC 模式：点"立即全量备份"→ 按钮立即恢复 → BackgroundTaskPanel 显示 N 个任务
- [ ] N 个任务串行执行（TaskManager max_workers=1）
- [ ] 切页面后 BackgroundTaskPanel 任务状态不丢
- [ ] 同步模式（VITE_ASYNC_BACKUP≠true）：行为不变（阻塞 + 结果 Modal）
- [ ] CMDB.vue 全量备份也接 ASYNC 模式
- [ ] 前端 build 通过

---

## QA 验证计划

1. ASYNC 模式：Backup.vue 点全量备份 → BackgroundTaskPanel 显示 N 任务 → 等待全部 success
2. ASYNC 模式：CMDB.vue 点全量备份 → 同上
3. ASYNC 模式：备份中切到 Devices 页 → BackgroundTaskPanel 仍显示任务
4. 同步模式：全量备份 → 阻塞 + 结果 Modal（回归 v2.3 行为）
5. 前端 `npm run build` 通过
