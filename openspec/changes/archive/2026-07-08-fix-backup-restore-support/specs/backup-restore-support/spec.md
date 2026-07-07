# backup-restore-support — Delta Spec

> **v2.6.2 实施的 spec**（实施完成后会从 delta 转 main spec 沉淀到 `openspec/specs/backup-restore-support/spec.md`）
> **当前阶段**：delta（变更规范）

## 范围

本 spec 描述 v2.6.2 修复"备份回滚无反应"的 9 个 task：

| Task | 目标 | 实施位置 |
|---|---|---|
| T1 | 后端 probe 检测 SCP 推回支持 | `backend/app/utils/backup_manager.py` |
| T2 | restore_async 端点预检 + 422 | `backend/app/routers/backup.py` |
| T3 | 详细 paramiko 错误日志 | `backend/app/utils/backup_manager.py` |
| T4 | 前端 toast 系统（taskStore 失败时弹） | 新建 toast 组件 + store + App.vue + i18n |
| T5 | BackgroundTaskPanel 失败高亮 | `frontend/src/components/BackgroundTaskPanel.vue` |
| T6 | device.status 加 `restore_unsupported` 字段 | `backend/app/schemas/*.py` + router |
| T7 | mock scp.put Channel closed 测试 | `backend/tests/test_backup_api.py` |
| T8 | 真机 .177 + .5 双向验证 | — |
| T9 | docs/ops-toolkit.md S6850 SCP 限制说明 | `docs/ops-toolkit.md` |

不影响：备份拉取（v2.6.1 已加固）/ 备份历史 UI / v2.4.1 split 模式 / v2.6.0 i18n / 其他路由（VLAN/接口/VPN/资产/拓扑/CMDB）。

---

## ADDED Requirements

### Requirement: backup-restore-support 后端 probe 检测

`BackupManager.check_restore_support()` MUST 检测设备是否支持 SCP 推回（v2.6.2 Task 1）：

#### Scenario: H3C V7 S6850 设备 probe 失败

- **WHEN** 调用 `check_restore_support()` 在 H3C V7 S6850（CMW 7.1.070）设备
- **THEN** `scp.putfo(1 字节 dummy, "_probe_<ts>.tmp")` 抛 `paramiko.ssh_exception.SSHException("Channel closed.")`
- **AND** 函数返回 `{"supported": False, "reason": "Channel closed.", "error_type": "SSHException"}`

#### Scenario: H3C V7 .177 测试设备 probe 成功

- **WHEN** 调用 `check_restore_support()` 在 .177 设备
- **THEN** `scp.putfo` 成功
- **AND** 清理 dummy 文件（`delete /unreserved flash:/_probe_<ts>.tmp`）
- **AND** 返回 `{"supported": True, "reason": "scp push ok"}`

---

### Requirement: backup-restore-support restore_async 端点预检

`POST /api/devices/{id}/backup/{bid}/restore-async` MUST 在启动后台 task 前先 probe（v2.6.2 Task 2）：

#### Scenario: 不支持设备 restore_async 立即 422

- **WHEN** 后端收到 restore_async 请求
- **AND** `check_restore_support()` 返回 `{supported: False}`
- **THEN** 立即返回 `APIResponse(success=False, error={key: "BACKUP_RESTORE_NOT_SUPPORTED", ...})`
- **AND** 不创建后台 task（task_manager.submit 不调用）
- **AND** `error.fallback` 含设备型号 / 设备 IP / 失败原因

#### Scenario: 支持设备 restore_async 正常启动

- **WHEN** 后端收到 restore_async 请求
- **AND** `check_restore_support()` 返回 `{supported: True}`
- **THEN** 走原流程（task_manager.submit → 后台执行 `_async_restore_fn`）

---

### Requirement: backup-restore-support 详细 paramiko 错误日志

`_restore_via_scp` 失败 MUST 记录详细错误日志（v2.6.2 Task 3）：

#### Scenario: SCP 推回失败日志

- **WHEN** `_restore_via_scp` 抛异常
- **THEN** 错误日志 MUST 包含：
  - `device_model`（设备型号）
  - `host`（设备 IP）
  - `backup_id`
  - `error_type`（异常类名）
  - `error_message`（完整 error message）
- **AND** `BackupError` 抛给上层调用

---

### Requirement: backup-restore-support 前端 toast 系统

前端 MUST 新建 toast 组件 + store（v2.6.2 Task 4）：

#### Scenario: taskStore 任务从 running 变 failed 弹 toast

- **WHEN** `_pollOnce` 检测 task 状态从 `running` 变 `failed`
- **THEN** 调用 `toastStore.error(...)` 弹错误 toast
- **AND** toast message MUST 包含 task 类型（backup / restore）和 error message

#### Scenario: Toast 4 种类型

- **WHEN** 调用 `toastStore.success/error/warning/info(msg)`
- **THEN** ToastContainer 显示对应类型 toast
- **AND** 自动 5s 消失（error 8s）
- **AND** 用户可手动关闭

---

### Requirement: backup-restore-support BackgroundTaskPanel 失败高亮

`BackgroundTaskPanel.vue` MUST 显示失败任务红点（v2.6.2 Task 5）：

#### Scenario: 面板折叠时有失败任务

- **WHEN** 任务面板处于折叠态
- **AND** 存在 status=failed 的任务
- **THEN** 右下角显示红点 + "{count} 个失败任务" 提示
- **AND** 点击红点 → 面板自动展开

#### Scenario: 面板展开时失败任务高亮

- **WHEN** 任务面板展开
- **AND** 任务 status=failed
- **THEN** 任务行用 `text-bad` 高亮
- **AND** 显示 error message（前 2 行）

---

### Requirement: backup-restore-support device.status restore_unsupported 字段

`device.status` MUST 包含 `restore_unsupported: bool` 字段（v2.6.2 Task 6）：

#### Scenario: device.status 返回 restore_unsupported

- **WHEN** 客户端请求 `GET /api/devices/{id}/status`
- **THEN** 响应体 MUST 包含 `restore_unsupported: bool`
- **AND** 字段值由 `check_restore_support()` 决定（5s TTL 缓存）

#### Scenario: 缓存命中

- **WHEN** 同一设备 5s 内多次请求 `device.status`
- **THEN** 复用 5s TTL 缓存（v2.6.1 引入的 internal-api 5s TTL 机制）
- **AND** 不重复 probe

---

## 整体回归

### 不破坏

- v2.6.1 fix-asset-backup-state-sync（asset 状态前置校验）
- v2.6.1 fix-backup-data-integrity（备份数据完整性 4 防线）
- v2.6.0 i18n 任何代码
- v2.4.1 split 模式架构（ctrl / config / data 3 容器）
- v2.5.0 vitest + playwright 测试体系
- BACKUP_KEEP=5 轮转逻辑

### 测试 baseline

- qa-backend：245+ → 248+ tests（T7 新增 ≥ 1 mock 测试）
- qa-frontend：lint + build + vitest + playwright 全过
- 真机：.177 + .5 双向验证通过

### 性能

- T1 probe：每次 restore_async 增加 1 次 SSH 连接 + scp.push（1 字节），< 2s
- T2 端点预检：probe 在端点启动前执行，fail-fast 不阻塞后台 task
- T3 错误日志：仅在失败时记录，零性能开销
- T4 toast 系统：轻量组件，< 1ms 渲染开销
- T5 面板高亮：computed 计算，< 1ms
- T6 status 字段：5s TTL 缓存复用，避免重复 probe
