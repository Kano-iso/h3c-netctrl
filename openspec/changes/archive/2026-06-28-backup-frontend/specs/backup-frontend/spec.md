# Spec: backup-frontend

## Purpose

H3C 设备配置备份 / 回滚能力的**前端层**：3 个入口（全局 Backup 页 / 设备行 / CMDB 顶部）+ 1 个 Modal 组件 + 1 套 API 客户端，对接 v2.1.x patch 已完成的后端 REST 端点。

## Requirements

### REQ-1: 备份 API 客户端

`frontend/src/api/index.js` MUST 暴露 `backupApi`，包含以下 7 个方法：

| 方法 | HTTP | 路径 | 返回 |
|---|---|---|---|
| `list(deviceId)` | GET | `/api/devices/{id}/backup` | `Promise<APIResponse<Backup[]>>` |
| `create(deviceId)` | POST | `/api/devices/{id}/backup` | `Promise<APIResponse<{id, filename, ...}>>` |
| `createAll()` | POST | `/api/backups` | `Promise<APIResponse<{success: Backup[], failed: {device_id, error}[]}>>` |
| `download(deviceId, backupId)` | GET | `/api/devices/{id}/backup/{bid}` | `Promise<Blob>` |
| `remove(deviceId, backupId)` | DELETE | `/api/devices/{id}/backup/{bid}` | `Promise<APIResponse>` |
| `toggleLock(deviceId, backupId, locked)` | POST | `/api/devices/{id}/backup/{bid}/lock` | `Promise<APIResponse>` |
| `restore(deviceId, backupId)` | POST | `/api/devices/{id}/backup/{bid}/restore` | `Promise<APIResponse>` |

### REQ-2: BackupListModal 组件

`frontend/src/components/BackupListModal.vue` MUST：

- Props: `visible: Boolean`, `deviceId: Number`, `deviceName: String`
- 表格列：备份 ID / 文件名 / 时间（`created_at`）/ 大小（`size` B/KB/MB 自适应）/ 类型（`backup_type`）/ 锁定（`locked` 状态图标）/ hash 前 8 位
- 操作列按钮：
  - **下载**：触发浏览器下载，文件名 = 后端返回的 `filename`
  - **锁定切换**：locked → unlocked（确认）/ unlocked → locked（确认）
  - **删除**：未锁定可用（必须 ConfirmModal）；锁定时按钮禁用 + tooltip "已锁定，禁止删除"
  - **回滚**：必须 ConfirmModal，确认框显示 `时间 + 大小 + hash 前 8 位`
- 顶部"立即备份"按钮 → 调用 `backupApi.create(deviceId)` → 刷新列表
- 关闭：X 按钮 / ESC 键 / 遮罩点击（默认不点遮罩关闭，避免误操作）
- 错误信息：调用失败时显示后端返回的 `error` 字段（中文）

### REQ-3: Backup.vue 全局页

`frontend/src/views/Backup.vue` MUST 重写为真实页（替换现有 141 行 preview）：

- 顶部 4 个 KPI 卡片：备份总数 / 锁定数 / 总占用（自动 KB/MB）/ 今日新增（按 `created_at` 当天）
- 顶部"立即全量备份"按钮 → 调用 `backupApi.createAll()` → 弹结果 Modal（成功 N / 失败 M / 失败列表）
- 表格按**设备分组**：每设备一段小表格（设备名 header + 该设备的备份列表）
- 每行操作：下载 / 锁定切换 / 删除 / 回滚（同 REQ-2）
- 锁定 / 删除 / 回滚 必经 ConfirmModal

### REQ-4: Devices.vue 单设备入口

`frontend/src/views/Devices.vue` MUST：

- 操作列加"备份"按钮（与现有"连接测试/资产/编辑/删除"并列）
- 引入 `BackupListModal` 组件
- 点击"备份" → 弹 Modal，传入 `deviceId` 和 `deviceName`

### REQ-5: CMDB.vue 全量入口

`frontend/src/views/CMDB.vue` MUST：

- 顶部工具栏加"全量备份"按钮（资产表头右侧，与现有"新建资产"并列）
- 点击 → 调用 `backupApi.createAll()` → 弹结果 Modal（成功 N / 失败 M）
- 失败时显示中文错误

### REQ-6: 二次确认

所有危险操作（删除 / 锁定切换 / 回滚）MUST 弹 `ConfirmModal` 二次确认，配置项：

| 操作 | 确认文案 | 确认按钮 |
|---|---|---|
| 删除非锁定 | "确定删除备份 {filename}？此操作不可恢复" | 红色 "删除" |
| 锁定切换 | "确定 {操作} 备份 {filename}？" | "确认" |
| 回滚 | "确定回滚到 {filename}？设备配置将被覆盖，时间：{time}，hash：{hash前8位}" | 红色 "回滚" |

### REQ-7: 错误处理

所有 API 调用失败 MUST：
- 显示后端返回的 `error` 字段（中文，透传）
- 不抛原生异常到 UI
- 不静默吞错

## Non-Functional

- **UX 一致**：3 个入口风格统一（按钮位置 / 配色 / 表格列宽 / 二次确认文案）
- **性能**：列表加载 < 3s（实测后端 6 台 1 次 get-config 2s 内）
- **可访问性**：所有按钮 keyboard 可达（Tab + Enter）
- **不引入新依赖**：只用现有 Vue 3 + 现有组件库

## Out of Scope

- **不做定时备份**（用户明确拒绝）
- **不做"今日份"**等花哨数据
- **不做"备份版本对比 UI"**（diff 留 follow-up）
- **不做"备份文件预览"**（下载到本地看）
- **不做新依赖**
