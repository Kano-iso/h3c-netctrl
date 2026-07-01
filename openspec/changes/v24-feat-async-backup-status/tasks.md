# v24-feat-async-backup-status Tasks

> **设备**：192.168.100.5（生产）
> **新依赖**：前端 pinia（如未装）
> **数据库**：新增 `tasks` 表

---

## 1. 后端：task_manager 模块

- [ ] 1.1 backend/app/models.py 加 `Task` 模型（task_id, type, device_id, status, progress, result_json, error, created_at, updated_at）
- [ ] 1.2 alembic migration：创建 tasks 表
- [ ] 1.3 backend/app/task_manager.py 写 TaskManager 类
  - `submit(type, device_id, payload) -> task_id`
  - `get_status(task_id) -> TaskState`
  - `cancel(task_id) -> bool`
  - 状态机：pending → running → success/failed/cancelled
  - 进度回调：备份 manager / SSH executor 调 `update_progress(task_id, n)`
- [ ] 1.4 单测 `test_task_manager_state_machine`（5 状态转换）
- [ ] 1.5 单测 `test_task_manager_persistence`（重启后任务恢复）
- [ ] 1.6 单测 `test_task_manager_cancel`（取消流程）

## 2. 后端：API 端点

- [ ] 2.1 backend/app/routers/backup.py 加 3 端点
  - `POST /api/devices/{id}/backup-async` → 202 { task_id, status_url }
  - `POST /api/devices/{id}/backup/{bid}/restore-async` → 202 同上
  - `GET /api/tasks/{task_id}` → { status, progress, result, error }
  - `POST /api/tasks/{task_id}/cancel` → { cancelled: bool }
- [ ] 2.2 保留原同步端点（兼容）
- [ ] 2.3 单测 `test_backup_async_submit`（提交返回 task_id）
- [ ] 2.4 单测 `test_restore_async_submit`（同上）
- [ ] 2.5 单测 `test_task_get_status`（轮询路径）
- [ ] 2.6 单测 `test_task_cancel`（取消 API）

## 3. 前端：Pinia store

- [ ] 3.1 装 pinia：`cd frontend && npm install pinia`
- [ ] 3.2 frontend/src/stores/task.js 写 useTaskStore
  - state: `tasks: Record<taskId, TaskState>`
  - actions: `submitTask`, `pollTask`, `cancelTask`, `restoreFromLocalStorage`
  - localStorage 持久化（每 5s 写一次）
- [ ] 3.3 单测（vitest 框架阻塞中，暂用 store 单元测试）
- [ ] 3.4 启动时 localStorage 恢复未完成任务

## 4. 前端：UI 组件

- [ ] 4.1 frontend/src/components/BackgroundTaskPanel.vue 新建（底部抽屉）
  - 列出所有 running 任务
  - 每行：转圈 + 进度条 + 取消按钮
  - 状态变更时 toast
- [ ] 4.2 frontend/src/views/Devices.vue 接入
  - 备份按钮 → 调 `submitTask('backup', ...)` → 立即关弹窗
  - 回滚按钮 → 调 `submitTask('restore', ...)`
  - 底部加 BackgroundTaskPanel
- [ ] 4.3 frontend/src/components/BackupListModal.vue 接入（同样）
- [ ] 4.4 feature flag：`VITE_ASYNC_BACKUP=true` 启用异步模式（默认 false，保持兼容）

## 5. 集成测试

- [ ] 5.1 真机 192.168.100.5：备份异步提交 → 立即返回 task_id → 前端 toast
- [ ] 5.2 轮询：任务 running → progress 0→100
- [ ] 5.3 切页面 / 刷新浏览器 → 任务状态保留
- [ ] 5.4 取消：回滚中点取消 → 当前 step 完成后停
- [ ] 5.5 集成测试 `test_backup_async_e2e`（test_async.py）：提交 → 轮询 → 完成

## 6. 收尾

- [ ] 6.1 commit `feat(backend): task_manager + 3 异步端点`
- [ ] 6.2 commit `feat(frontend): Pinia task store + BackgroundTaskPanel`
- [ ] 6.3 commit `test: 4 单测 + 1 集成测试`
- [ ] 6.4 archive 进 `archive/2026-07-XX-v24-feat-async-backup-status/`
- [ ] 6.5 进 v2.4 release notes 合并

## 设备最终状态

- 192.168.100.5 备份/配置不动（仅异步化交互）
- 192.168.100.4 / .177 不动

## 关联

- [proposal.md](proposal.md)
- 现有同步端点：[backend/app/routers/backup.py `POST /backup`](../backend/app/routers/backup.py)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
