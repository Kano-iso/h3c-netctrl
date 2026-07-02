# v24-feat-async-backup-status

## Why

v2.3.1 (2026-07-01) 发版后用户反馈：
> "目前来讲，明显需要转圈的事情是什么呢？备份。备份这个事情需要转圈，包括回滚，那么这点这几个动作呢，在做的时候，我希望是后台进行的，就是说我点了那个操作之后，我可以叉出去，或者是就是我也可以错杀数据，或者是怎么样的，就是回滚中，它在滚中或者是备份中，这个时候我可以出去，然后他的那个条目上的状态依旧在转圈圈，或者是在回滚中的转圈圈，然后即使我切页面再回来，他依旧在转圈圈"

具体痛点：
- 备份 / 回滚（特别是回滚带 `with_reboot=true`）耗时 60-120s
- 当前是同步阻塞，用户必须等
- 切页面后状态丢失，回来不知进度
- 误点操作想取消也取消不了

## What Changes

### 架构
- 引入 **Pinia store** 集中管理异步操作状态
- 后端用**任务 ID** 返回 202 Accepted，客户端轮询
- 前端 store 持久化（localStorage）保证切页面 / 刷新后状态保留

### 后端
- 新增 `POST /api/devices/{id}/backup-async` / `POST /api/devices/{id}/backup/{bid}/restore-async`
- 返回 `{ task_id, status_url, status: "pending" }`
- 新增 `GET /api/tasks/{task_id}` 返回 `{ status, progress, result, error }`
- status: `pending` / `running` / `success` / `failed` / `cancelled`
- progress: 0-100 整数（备份进度从 backup_manager 拿，回滚从设备 SSH 拿）

### 前端 Pinia store
- `useTaskStore` 维护 `tasks: Record<taskId, TaskState>`
- 启动时从 localStorage 恢复未完成任务
- 后台轮询 `GET /api/tasks/{task_id}` 每 2s 一次（失败时退避到 5s）
- 状态变更时写 localStorage
- 任务完成（success / failed）后保留 5 分钟方便查看，然后清理

### UI 反馈
- 备份 / 回滚按钮点了立即关闭弹窗，提示"任务已提交，task_id=xxx"
- 设备详情页 + 备份列表页底部加"后台任务" 区域，显示所有 running 任务的转圈
- 每个任务行有"取消"按钮（调 `POST /api/tasks/{task_id}/cancel`）
- 任务完成时 toast 通知 + 状态变绿/红
- 切页面回来后台任务区域状态保留

### 取消
- `POST /api/tasks/{task_id}/cancel` 调后端取消（备份中是 `cancel_event.set()`，回滚中要先等当前 step 完成）

## Impact

- **后端**：新 3 端点（async 提交 / 状态查 / 取消）+ task_manager 模块 + SQLAlchemy Task 表
- **前端**：Pinia + useTaskStore + 后台任务 UI 组件 + Devices.vue / BackupListModal.vue 接入
- **数据库**：新增 `tasks` 表（task_id, type, device_id, status, progress, result_json, error, created_at, updated_at）
- **测试**：3 单测（task_manager 状态机）+ 1 集成测试（真机备份+回滚异步）
- **新依赖**：前端 pinia（按需装）
- **不破坏**：现有 `POST /api/devices/{id}/backup` 同步端点保留（兼容）
- **可回退**：前端不启用 store 仍走同步（feature flag 控制）

## 真机验证

- **设备**：192.168.100.5（生产）
- **async 提交**：备份提交后立即返回 task_id，前端 toast
- **轮询**：任务 running 时前端转圈 + progress 更新
- **取消**：回滚中点取消，备份能中断（或等当前 step 完成）
- **持久化**：切页面 / 刷新浏览器后任务状态保留
- **回归**：v2.3.1 archive 8 change 不能破坏

## Out of Scope

- 不引入 WebSocket（用轮询简单，个人项目 ROI 高）
- 不做任务调度 / cron（手动触发）
- 不做分布式 task queue（单 backend 够用）
- 不改同步端点（保留兼容）

## 关联

- 现有同步端点：[backend/app/routers/backup.py `POST /backup`](../backend/app/routers/backup.py)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
- 设备详情页：[frontend/src/views/Devices.vue](../frontend/src/views/Devices.vue)
- 备份弹窗：[frontend/src/components/BackupListModal.vue](../frontend/src/components/BackupListModal.vue)
