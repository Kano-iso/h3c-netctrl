# backup-frontend Specification

## Purpose

H3C 设备配置备份 / 回滚能力的**前端层**：3 个入口（全局 Backup 页 / 设备行 / CMDB 顶部）+ 1 个 Modal 组件 + 1 套 API 客户端，对接 v2.1.x patch 已完成的后端 REST 端点。

承接：
- 父 change `v21x-patch-backup-backend`（后端 7 个 API + BackupManager + 轮转 + 锁定）
- 父 change `fix-backup-manager-save-force-and-scp`（全文本 + SCP 统一回滚方案）

## Requirements

### Requirement: 备份 API 客户端

`frontend/src/api/index.js` MUST 暴露 `backupApi`，包含以下 7 个方法：

| 方法 | HTTP | 路径 | 默认 body | 返回 |
|---|---|---|---|---|
| `list(deviceId)` | GET | `/api/devices/{id}/backup` | — | `Promise<APIResponse<{device_id, total, backups[]}>>` |
| `create(deviceId)` | POST | `/api/devices/{id}/backup` | `{}`（FastAPI `BackupCreateRequest` 必填 body） | `Promise<APIResponse<{id, type, size, ...}>>` |
| `createAll()` | POST | `/api/backups` | — | `Promise<APIResponse<{success, failed, total}>>` |
| `download(deviceId, backupId)` | GET | `/api/devices/{id}/backup/{bid}` | — | `Promise<{success, data: {blob, filename}}>` |
| `remove(deviceId, backupId)` | DELETE | `/api/devices/{id}/backup/{bid}` | — | `Promise<APIResponse>` |
| `toggleLock(deviceId, backupId, locked)` | POST | `/api/devices/{id}/backup/{bid}/lock` | `{locked}` | `Promise<APIResponse>` |
| `restore(deviceId, backupId, with_reboot=true)` | POST | `/api/devices/{id}/backup/{bid}/restore` | `{with_reboot}` | `Promise<APIResponse>` |

**关键约束**：
- `create` 必须显式传 `body: JSON.stringify({})`（空 body）—— FastAPI `BackupCreateRequest` 是必填 body 形参
- `restore` 默认 `with_reboot=true`（端到端：推 + set as startup + reboot + verify）—— v2.2 用户场景"页面点一下就完成回滚"
- `download` 不走 `apiCall`（`apiCall` 用 `.json()`，下载要 `Blob`）

### Requirement: BackupListModal 组件

`frontend/src/components/BackupListModal.vue` MUST：

- **Props**：`visible: Boolean` (v-model)、`deviceId: Number`、`deviceName: String`
- **顶部"立即备份"按钮** → `backupApi.create(deviceId)` → 刷新列表
- **表格列**：备份 ID / 文件名 / 时间（`created_at` 格式化）/ 大小（B/KB/MB 自适应）/ 类型（`type || backup_type`）/ 锁定（图标）/ hash 前 8 位
- **操作列**：
  - **下载**：从后端取 Blob + `Content-Disposition` 文件名 → 浏览器下载
  - **锁定切换**：locked ↔ unlocked，经 ConfirmModal 二次确认
  - **删除**：未锁定可点（红色按钮 + ConfirmModal）；锁定时按钮禁用 + tooltip "已锁定，禁止删除"
  - **回滚**：经 ConfirmModal，确认框显示 `时间 + 大小 + hash 前 8 位 + ⚠️ 设备将重启 60-120s`；按钮文案"回滚并重启"
- **关闭**：X 按钮 / ESC 键
- **错误处理**：API 失败时显示后端返回的 `error` 字段（中文），不抛原生异常
- **v-if 挂载守卫**：父组件用 `v-if="deviceId"` 避免 `deviceId=null` 的 Vue warn

### Requirement: Backup.vue 全局页

`frontend/src/views/Backup.vue` MUST（重写 141 行 preview）：

- **顶部 4 个 KPI 卡片**：备份总数 / 锁定数 / 总占用（自动 KB/MB）/ 今日新增（`created_at` 当天）
- **顶部"立即全量备份"按钮** → `backupApi.createAll()` → 弹结果 Modal（成功 N / 失败 M / 失败列表）
- **设备下拉过滤**：显示所有设备（含"全部"），可按设备筛选
- **锁定过滤**：全部 / 仅锁定 / 仅未锁定
- **表格按设备分组**：每设备一段（设备名 header + 该设备备份小表格）
- **每行操作**：下载 / 锁定切换 / 删除 / 回滚（同 Modal 逻辑，二次确认一致）

### Requirement: Devices.vue 单设备入口

`frontend/src/views/Devices.vue` MUST：

- 操作列加"备份"按钮（与"连接测试 / 资产 / 编辑 / 删除"并列）
- 引入 `BackupListModal` 组件
- 点击"备份" → 弹 Modal，传入 `deviceId` 和 `deviceName`

### Requirement: CMDB.vue 全量入口

`frontend/src/views/CMDB.vue` MUST：

- 顶部工具栏加"全量备份"按钮（资产表头右侧）
- 点击 → `backupApi.createAll()` → 弹结果 Modal（成功 N / 失败 M）
- 失败时显示后端 `error` 字段

### Requirement: 二次确认

所有危险操作 MUST 弹 `ConfirmModal`：

| 操作 | 确认文案 | 按钮文案 | variant |
|---|---|---|---|
| 删除非锁定备份 | "确定删除备份 {filename}？此操作不可恢复" | 红色"删除" | danger |
| 锁定切换 | "确定 {锁定/解锁} 备份 {filename}？" | "确认" | default |
| 回滚 | "确定回滚到 {filename}？设备配置将被覆盖 + reboot 60-120s + 验证生效。⚠️ 设备将重启，请确认维护窗口" | 红色"回滚并重启" | danger |

### Requirement: 错误处理

所有 API 调用 MUST：
- 显示后端 `error` 字段（中文，透传）
- 不抛原生异常到 UI
- 不静默吞错
- 列表/下载失败时显示空状态 + 错误提示

### Requirement: 操作日志

所有 backup_* 操作 MUST 记录到 logs 表（v2.2 任务 5 收尾）：

- `backup_create`：单设备备份
- `backup_create_all`：全量备份
- `backup_delete`：删除备份
- `backup_lock`：锁定 / 取消锁定
- `backup_restore`：回滚（包含 reboot / verify 状态）

路由层不重复 `record_log`（BackupManager 内部已按 btype / 动作粒度记日志）。

## Non-Functional

- **UX 一致**：3 个入口风格统一（按钮位置 / 配色 / 表格列宽 / 二次确认文案）
- **性能**：列表加载 < 3s（实测后端 6 台 1 次 get-config 2s 内）
- **可访问性**：所有按钮 keyboard 可达（Tab + Enter）
- **不引入新依赖**：只用现有 Vue 3 + 现有组件库

## Out of Scope

- **不做定时备份**（用户明确拒绝）
- **不做"今日份"快查界面**（KPI 卡片已有当日数据）
- **不做"备份版本对比 UI"**（diff 留 follow-up）
- **不做"备份文件预览"**（下载到本地用文本编辑器看）
- **不做"auto 备份"**
- **不做 Playwright / Cypress E2E 自动化**（v2.2 投入产出比低，留 v2.3 评估）

## 真机验证

设备：192.168.100.4 (Leaf-03, H3C V7)

| 验证项 | 结果 |
|---|---|
| 6.1 Backup.vue 加载 + 列表历史数据 | ✅ API + UI |
| 6.2 立即全量备份 | ✅ UI（用户实测"全量备份可以成功的"） |
| 6.3-6.8 Devices.vue 入口 / Modal / 下载 / 锁定 / 删除 / 锁定禁删 | ⏳ UI 未逐一验证（功能代码 + 路由已就绪） |
| 6.9 回滚 + n → n+1 → n 恢复原状 | ✅ UI（用户实测"回滚确实好使"，reboot + verify 通过） |
| 6.10 CMDB.vue 顶部全量备份 | ⏳ UI 未逐一验证 |
| 6.11 设备不可达错误显示 | ⏳ UI 未逐一验证 |

## 修改文件

```
frontend/src/api/index.js                       # backupApi 7 个方法
frontend/src/components/BackupListModal.vue     # 单设备备份 Modal
frontend/src/views/Backup.vue                   # 全局 Backup 页（重写）
frontend/src/views/Devices.vue                  # 接入备份按钮 + Modal
frontend/src/views/CMDB.vue                     # 接入全量备份按钮
frontend/src/views/Logs.vue                     # actionOptions 加 backup_* 5 项
backend/app/routers/backup.py                   # record_log 去重 + 全量路由补 log
```

## 关联

- 父 change：`v21x-patch-backup-backend`（已 archive）
- 阻塞 change：`fix-backup-manager-save-force-and-scp`（已 archive，统一回滚方案）
- 同版本 change：`interface-vpn-instance-and-l2-l3` + `fix-vpn-and-l2l3-ux-bugs` + `fix-vpn-edit-capabilities`（v2.2 同批）

## Rollback

- `git revert` 本次修改
- 数据库无 schema 变更（仅前端 + 路由层 record_log 调整）
- 不破坏后端 backup API（向后兼容）

## Lessons Learned

- **前端 POST 必须显式 body**：apiCall 写死 `Content-Type: application/json` + 不传 body 字段 → FastAPI 422 → 前端 r.success undefined → "备份失败"假象。修复：所有 POST 默认 `body: JSON.stringify({})`
- **回滚默认 with_reboot=true**：v2.2 提案明确"页面点一下完成回滚"，落地时默认值 False → 推了 startup 但不 reboot → 用户实测"没效果"。修复：默认 true + UI 警告
- **UI 警告必须显式**：with_reboot=true 涉及设备 reboot 60-120s 断网，必须 ConfirmModal 弹 "⚠️ 设备将重启" + 按钮文案 "回滚并重启" 让用户知情
- **凭理论推断打 [x] 是禁止的**：tasks.md 6.x 必须分"实测 PASS / API PASS / 未测"三态，不允许用"功能代码 OK"推断 UI OK
