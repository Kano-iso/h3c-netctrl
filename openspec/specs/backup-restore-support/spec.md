# backup-restore-support Specification

## Purpose
TBD - created by archiving change fix-backup-restore-support. Update Purpose after archive.

## Requirements

### Requirement: backup-restore-support 后端 probe 检测

`BackupManager.check_restore_support()` MUST 检测设备是否支持 SCP 推回（v2.6.2 Task 1）。

#### Scenario: H3C V7 S6850 设备 probe 失败

- **WHEN** 调用 `check_restore_support()` 在 H3C V7 S6850（CMW 7.1.070）设备
- **THEN** `scp.putfo(1 字节 dummy, "_probe_<ts>.tmp")` 抛 `paramiko.ssh_exception.SSHException("Channel closed.")`
- **AND** 函数返回 `{"supported": False, "reason": "Channel closed.", "error_type": "SSHException"}`

#### Scenario: H3C V7 .177 测试设备 probe 成功

- **WHEN** 调用 `check_restore_support()` 在 .177 设备
- **THEN** `scp.putfo` 成功
- **AND** 清理 dummy 文件（`delete /unreserved flash:/_probe_<ts>.tmp`）
- **AND** 返回 `{"supported": True, "reason": "scp push ok"}`

### Requirement: backup-restore-support restore_async 端点预检

`POST /api/devices/{id}/backup/{bid}/restore-async` MUST 在启动后台 task 前先 probe（v2.6.2 Task 2）。

#### Scenario: 不支持设备 restore_async 立即 422

- **WHEN** 后端收到 restore_async 请求
- **AND** `check_restore_support()` 返回 `{supported: False}`
- **THEN** 立即返回 `APIResponse(success=False, error_key="backup.restore_not_supported", ...)`
- **AND** 不创建后台 task（task_manager.submit 不调用）
- **AND** `error.fallback` 含设备型号 / 设备 IP / 失败原因

#### Scenario: 支持设备 restore_async 正常启动

- **WHEN** 后端收到 restore_async 请求
- **AND** `check_restore_support()` 返回 `{supported: True}`
- **THEN** 走原流程（task_manager.submit → 后台执行 `_async_restore_fn`）

#### Scenario: probe 自身失败兜底

- **WHEN** `check_restore_support()` 抛异常（如 SSH 连接失败）
- **THEN** MUST 不阻塞原 task 流程，按"支持"处理
- **AND** MUST 记录 ERROR 日志（device_id / host / 异常详情）

### Requirement: backup-restore-support 详细 paramiko 错误日志

`_restore_via_scp` 失败 MUST 记录详细错误日志（v2.6.2 Task 3）。

#### Scenario: SCP 推回失败日志

- **WHEN** `_restore_via_scp` 抛异常
- **THEN** 错误日志 MUST 包含 `device_model` / `host` / `backup_id` / `error_type` / `error_message`
- **AND** `BackupError` 抛给上层调用（带 device + type 前缀）

### Requirement: backup-restore-support 前端 toast 系统

前端 MUST 新建 toast 组件 + store（v2.6.2 Task 4）。

#### Scenario: taskStore 任务从 running 变 failed 弹 toast

- **WHEN** `_pollOnce` 检测 task 状态从 `pending` / `running` 变 `failed`
- **THEN** 调用 `toastStore.error(...)` 弹错误 toast
- **AND** toast message MUST 包含 task_id 和 error message

#### Scenario: Toast 4 种类型

- **WHEN** 调用 `toastStore.success/error/warning/info(msg)`
- **THEN** ToastContainer 显示对应类型 toast
- **AND** 自动 5s 消失（error 8s）
- **AND** 用户可手动关闭

### Requirement: backup-restore-support BackgroundTaskPanel 失败高亮

`BackgroundTaskPanel.vue` MUST 显示失败任务高亮（v2.6.2 Task 5）。

#### Scenario: 面板折叠时有失败任务

- **WHEN** 任务面板处于折叠态（无 running）
- **AND** 存在 status=failed 的任务
- **THEN** MUST 仍显示面板（折叠态条件放宽）
- **AND** panel 容器加 `ring-2 ring-bad/40` 描边
- **AND** 头部显示红色警示图标 + "N 失败" chip

#### Scenario: 面板展开时失败任务高亮

- **WHEN** 任务面板展开
- **AND** 任务 status=failed
- **THEN** 任务行已用 `text-bad` 高亮
- **AND** 显示 error message（前 2 行）

### Requirement: backup-restore-support device.status restore_unsupported 字段

`device.status` MUST 包含 `restore_unsupported` 字段（v2.6.2 Task 6）。

#### Scenario: device.status 返回 restore_unsupported

- **WHEN** 客户端请求 `GET /api/devices` 或 `GET /api/devices/{id}`
- **THEN** 响应体 MUST 包含 `restore_unsupported: Optional[bool]`
- **AND** 字段值由 `check_restore_support()` 决定（5s TTL 缓存）
- **AND** `device_model` 来自 `device.asset.model`（不在 Device ORM 上）

#### Scenario: 缓存命中

- **WHEN** 同一设备 5s 内多次请求 device list/detail
- **THEN** 复用 5s TTL 缓存
- **AND** 不重复 probe

#### Scenario: 探测失败不阻塞

- **WHEN** `_get_restore_support_cached` 内部异常（如 SSH 不可达）
- **THEN** MUST 返回 `None`（"未知"）
- **AND** MUST 写 WARNING 日志
- **AND** MUST 不阻塞 device list 返回
