# asset-backup-state-sync Specification

## Purpose
TBD - created by archiving change fix-asset-backup-state-sync. Update Purpose after archive.

## Requirements

### Requirement: 离线/未采集设备备份默认禁用

`POST /api/devices/{id}/backup`（同步）和 `POST /api/devices/{id}/backup-async`（异步）端点 MUST 在设备 `asset.status` 为 `offline` / `never_collected` / `stale` 时返回 422 错误（error_key=`error.backup.device_offline`），不允许走完整备份链路。

#### Scenario: 在线设备正常备份
- **WHEN** 设备 asset.status = `online`
- **THEN** 备份端点 MUST 正常执行，返回 200 + 新建 backup 行

#### Scenario: 离线设备无 force 拒绝
- **WHEN** 设备 asset.status = `offline`（或 never_collected / stale）且未传 `force=true`
- **THEN** 端点 MUST 返回 422 + `error_key=error.backup.device_offline`

#### Scenario: 异步端点行为一致
- **WHEN** 异步备份端点收到离线设备请求
- **THEN** MUST 同步/异步行为一致（拒绝或接受 force），不允许出现"异步端点绕过校验"

### Requirement: force=true 逃生通道

备份端点 MUST 支持 `?force=true` 查询参数绕过 asset 状态校验，强制执行备份并在 `backups.forced` 字段写 1 + 日志记录 `force_backup device_id=... user=...`。

#### Scenario: force=true 离线设备
- **WHEN** 离线设备请求 backup 端点 + `?force=true`
- **THEN** MUST 返回 200 + 新建 backup 行 + `backups.forced=1`

#### Scenario: force=true 走审计日志
- **WHEN** 强制备份成功
- **THEN** MUST 写日志 `force_backup device_id=<id> skip asset check`

### Requirement: 全量备份端点 force 支持

`POST /api/backups`（同步全量）和 `POST /api/backups-async`（异步全量）端点 MUST 支持 `force` 参数，与单设备行为一致。

#### Scenario: 全量端点 force 透传
- **WHEN** CMDB.vue 全量备份按钮 + 勾选 force + 提交
- **THEN** 后端 MUST 逐设备调用 BackupManager.create_backup(forced=force)，offline 设备按 force 决定拒绝/通过

### Requirement: backups 表加 forced 审计列

`backups` 表 MUST 增加 `forced BOOLEAN NOT NULL DEFAULT 0` 列，Alembic 006 迁移带 `IF EXISTS` 守卫（ctrl/config 容器无 backups 表 → 跳过，避免 alembic 启动失败）。

#### Scenario: 迁移升级
- **WHEN** `alembic upgrade head` 在 data 容器执行
- **THEN** MUST 成功加 `forced` 列，server_default=0

#### Scenario: 迁移降级
- **WHEN** `alembic downgrade -1` 在 data 容器执行
- **THEN** MUST 成功删除 `forced` 列

#### Scenario: split 容器兼容
- **WHEN** `alembic upgrade head` 在 ctrl / config 容器执行（无 backups 表）
- **THEN** MUST 跳过 006 迁移，不报错

### Requirement: 前端 force 勾选 UI

`frontend/src/views/Devices.vue` 行内 MUST 在 `asset.status != online` 的设备显示"强制"checkbox + 备份按钮（`:disabled="!forceChecked"`），勾选后按钮 enabled + tooltip 提示 `button.disabled.asset_offline`。

#### Scenario: 在线设备无 force 复选框
- **WHEN** 设备 asset.status = `online`
- **THEN** 行内 MUST 只显示"备份"按钮（无 force 复选框），按钮 enabled

#### Scenario: 离线设备未勾选
- **WHEN** 设备 asset.status = `offline` + 未勾选 force
- **THEN** 备份按钮 MUST disabled + tooltip 显示"资产未采集/离线"

#### Scenario: 离线设备已勾选
- **WHEN** 设备 asset.status = `offline` + 勾选 force
- **THEN** 备份按钮 MUST enabled，可点击

### Requirement: 强制备份二次确认

点击离线设备的备份按钮（force 已勾选）MUST 弹 ConfirmModal（标题 `backup.force_confirm_title` + 消息含设备名 + 状态 `backup.force_confirm_msg`），用户确认后才提交 `force=true` 请求。

#### Scenario: 二次确认弹窗内容
- **WHEN** 点击 force 备份按钮
- **THEN** Modal MUST 显示标题"强制备份确认" + 消息含设备名 + 状态 offline + 取消/强制备份按钮

#### Scenario: 取消不提交
- **WHEN** 用户在 Modal 点"取消"
- **THEN** MUST 不发请求，Modal 关闭

#### Scenario: 确认后提交
- **WHEN** 用户在 Modal 点"强制备份"
- **THEN** MUST 调 `backupApi.create(id, { force: true })` + DB.forced=1

### Requirement: CMDB 全量备份 force 选项

`frontend/src/views/CMDB.vue` 全量备份按钮 MUST 支持 force 复选框（`cmdb.full_backup_force` + `cmdb.full_backup_force_hint`），勾选后全量备份按 force 透传到所有设备。

#### Scenario: 默认全量备份
- **WHEN** 不勾选 force 全量备份
- **THEN** MUST 按 v2.6.0 行为（offline 设备拒绝，error_key 翻译）

#### Scenario: 勾选 force 全量备份
- **WHEN** 勾选 force 全量备份
- **THEN** MUST 逐设备 force 透传，offline 设备也执行 + 全部 DB.forced=1

### Requirement: 10 个 i18n key 中英文同步

`frontend/src/i18n/zh-CN.js` + `en-US.js` MUST 同步加以下 10 个 key，CMDB.vue / Devices.vue 引用全部正确翻译：

| key | zh-CN | en-US |
|---|---|---|
| `button.disabled.asset_offline` | 资产未采集，无法备份 | Asset not collected, cannot backup |
| `backup.force_label` | 强制 | Force |
| `backup.force_confirm_title` | 强制备份确认 | Force Backup Confirmation |
| `backup.force_confirm_msg` | 设备资产未采集/离线，继续备份可能获取到陈旧配置。是否继续？ | Device asset is uncollected/offline, backup may get stale config. Continue? |
| `backup.force_confirm_btn` | 强制备份 | Force Backup |
| `backup.force_success` | 强制备份已启动（审计已记录 forced=1） | Force backup started (forced=1 audit logged) |
| `backup.force_failed` | 强制备份失败 | Force backup failed |
| `cmdb.full_backup_force` | 强制全量备份（含离线/未采集设备） | Force full backup (including offline/uncollected) |
| `cmdb.full_backup_force_hint` | 勾选后将跳过资产状态校验，备份可能获取到陈旧配置 | Skip asset status check, backup may get stale config |
| `error.backup.device_offline` | 设备 {device_id} 资产未采集/离线 | Device {device_id} asset uncollected/offline |

#### Scenario: 切换中英文
- **WHEN** 用户点顶导 EN 按钮
- **THEN** Devices.vue / CMDB.vue 上述 10 个 key MUST 切到英文，反之亦然

#### Scenario: 二次确认 i18n
- **WHEN** 离线设备 + 勾选 force + 点击备份
- **THEN** ConfirmModal 标题 + 消息 MUST 按当前 locale 翻译
