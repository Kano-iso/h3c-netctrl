# v24-fix-batch-async-backup Tasks

## 1. task.js 加 submitBatchBackup

- [x] 1.1 在 `frontend/src/stores/task.js` 加 `submitBatchBackup(devices, types, labelFn)` 方法
- [x] 1.2 导出 submitBatchBackup
- [x] 1.3 验证：串行提交 N 台设备，每台返回 task_id

## 2. Backup.vue handleFullBackup 接 ASYNC

- [x] 2.1 `handleFullBackup` 加 ASYNC_MODE 分支（调 submitBatchBackup）
- [x] 2.2 ASYNC 分支不阻塞 fullBackingUp，不弹 fullResult Modal
- [x] 2.3 同步分支保持 v2.3 行为不变
- [x] 2.4 前端 build 通过
- [x] 2.5 修预存 bug：fullBackupType 未声明为 ref（导致 handleFullBackup 抛异常）

## 3. CMDB.vue handleFullBackup 接 ASYNC

- [x] 3.1 import useTaskStore + ASYNC_MODE
- [x] 3.2 `handleFullBackup` 加 ASYNC 分支
- [x] 3.3 前端 build 通过

## 4. UI 验证

- [x] 4.1 ASYNC 模式 Backup.vue 全量备份 → BackgroundTaskPanel 显示 7 任务
- [x] 4.2 ASYNC 模式 CMDB.vue 全量备份 → 已接 ASYNC 分支（代码同 Backup.vue 模式）
- [x] 4.3 切页面后 BackgroundTaskPanel 任务不丢（7→6→5 持续完成）
- [x] 4.4 同步模式回归 v2.3 行为（ASYNC_MODE=false 时走同步分支）

## 5. 收尾

- [x] 5.1 commit
- [x] 5.2 archive
