## Context

v2.1.x patch 完成备份后端（数据库 / 7 个 REST 端点 / SFTP 拉取 / 轮转 / 锁定 / 回滚）。本 change 只做**前端层**对接，不改后端。

### 后端 API 盘点（来自 `backend/app/routers/backup.py`）

| 端点 | 方法 | 说明 | 关键字段 |
|---|---|---|---|
| `/api/devices/{id}/backup` | POST | 单设备备份 | `{backup_type: "startup" \| "running"}` |
| `/api/devices/{id}/backup` | GET | 列表 | `[{id, filename, backup_type, size, content_hash, locked, created_at}]` |
| `/api/devices/{id}/backup/{bid}` | GET | 下载 | 返回 binary（Content-Disposition: attachment） |
| `/api/devices/{id}/backup/{bid}` | DELETE | 删除 | 锁定 → 403 |
| `/api/devices/{id}/backup/{bid}/lock` | POST | 锁切换 | `{locked: true/false}` |
| `/api/devices/{id}/backup/{bid}/restore` | POST | 回滚 | 无 body |
| `/api/backups` | POST | 全量 | 6 台并发，结果聚合 |

### 前端现状

- `views/Backup.vue`（141 行）：占位页，hardcoded 数据
- `components/`：无 BackupListModal，需新建
- `api/index.js`：无 backupApi，需新增
- `views/Devices.vue`：操作列已有 4 个按钮（连接/资产/编辑/删除）
- `views/CMDB.vue`：顶部有"新建资产"按钮

### 设计决策

1. **不引入新的状态管理**：备份列表在组件内 `ref` 管理，不上 Pinia/Vuex（避免过度设计）
2. **下载用 Blob + a[download]**：避免新开窗口 + 浏览器原生下载体验
3. **回滚二次确认显示 3 项关键信息**：备份时间 / 大小 / hash 前 8 位（让用户知道还原到哪个点）
4. **全量备份结果显示聚合**：成功 N / 失败 M / 失败列表可点开
5. **Backup.vue 用"按设备分组"展示**：每设备一段表格，缩进 + 折叠，避免一张大表
6. **hash 截断显示前 8 位**：完整 hash 太长无意义，前 8 位足够识别

## Goals / Non-Goals

**Goals:**
- 3 个入口都能用（全局页 / 设备行 / CMDB 顶部）
- 7 个 API 全部前端打通
- 危险操作（删除 / 回滚 / 锁定）必经 ConfirmModal
- 真机 192.168.100.4 跑通核心流程

**Non-Goals:**
- 不做定时备份（用户明确拒绝）
- 不做"今日份"等花哨数据
- 不引入新依赖
- 不做"备份文件预览"（下载到本地看）
- 不做"备份版本对比 UI"（diff 是未来 follow-up）

## File Changes

### 新增

- `frontend/src/components/BackupListModal.vue`（~180 行）：单设备备份列表 + 操作
- `openspec/specs/backup-frontend/spec.md`：capability spec

### 修改

- `frontend/src/api/index.js`：新增 `backupApi`（~30 行）
- `frontend/src/views/Backup.vue`：重写为真实页（~250 行）
- `frontend/src/views/Devices.vue`：操作列加"备份"按钮 + 引入 BackupListModal
- `frontend/src/views/CMDB.vue`：顶部加"全量备份"按钮

### 不改

- 后端所有文件（API 行为已稳定）
- 数据库（schema 不动）
- OpenSpec 中 `v21x-patch-backup-backend` 的 archive（已包含后端 spec）

## Test Strategy

### 后端（继承 v2.1.x patch）

不再重复验证（已 archive 通过）。必要时单独跑 1 次端到端。

### 前端

- 单元（手动）：
  - `backupApi` 7 个方法签名正确
  - `BackupListModal` 接收 visible / deviceId / deviceName props
- 集成（真机 / 浏览器）：
  - 侧边栏 Backup.vue 加载 → 列表有数据
  - 立即全量备份 → 6 条新记录出现
  - Devices.vue 行"备份"按钮 → 弹 Modal → 看到该设备历史
  - Modal 中"立即备份" → 列表刷新
  - 下载 → 文件落盘且内容可看
  - 锁定切换 → 图标变化
  - 删除（未锁定） → 列表减少
  - 删除（已锁定） → 二次确认前就被禁
  - 回滚 → ConfirmModal 显示 hash + 时间 + 大小 → 二次确认后设备配置恢复
  - 错误场景：设备不可达 → 中文错误显示

### 真机 192.168.100.4 必跑

- 立即全量备份（确认 6 条新增；192.168.100.4 在内）
- 192.168.100.4 单设备备份 + 锁定 + 删除非锁定 + 列表刷新
- 192.168.100.4 下载 → 文件可读
- 192.168.100.4 回滚 → 设备配置恢复（用前后 hash 对比验证）

## Risk

- **回滚是高风险操作**：UI 必须 ConfirmModal + 显示 hash + 时间
- **轮转是隐性风险**：每设备 5 份非锁定自动删，需在 UI 上明确"自动保留最新 5 份"
- **下载大型 startup.cfg 慢**：浏览器原生下载体验，可接受
- **全量备份并发 6 台**：单台失败不影响其他，结果聚合显示

## Rollback

- 本 change 只改前端 + OpenSpec 文档，不动后端 / 数据库 / 部署
- 回滚：`git revert` 即可
- 不需要数据库迁移

## 关联

- 父 change：`v21x-patch-backup-backend`（后端能力，本 change 的依赖）
- 同版本 v2.2 另一项：`interface-vpn-instance-and-l2-l3`（已 archive）
