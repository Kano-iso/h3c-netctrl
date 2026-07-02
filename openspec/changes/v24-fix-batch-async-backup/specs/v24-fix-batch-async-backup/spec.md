# v24-fix-batch-async-backup Spec

## 目标

全量备份接异步模式，与单设备备份行为一致（BackgroundTaskPanel 显示任务 + 切页面不丢）。

## 范围

- 前端 only（不改后端）
- 复用 `POST /api/devices/{id}/backup-async` 端点
- 改动：task.js + Backup.vue + CMDB.vue

## 验收标准

1. ASYNC 模式：全量备份 → BackgroundTaskPanel 显示 N 个任务 → 串行执行 → 全部到终态
2. ASYNC 模式：切页面后任务状态不丢（Pinia + localStorage）
3. 同步模式：行为不变（阻塞 + 结果 Modal）
4. 前端 build 通过
