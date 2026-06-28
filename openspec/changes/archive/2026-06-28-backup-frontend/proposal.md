## Why

v2.1.x patch (`archive/2026-06-28-v21x-patch-backup-backend`) 完成了**备份后端**能力：
- 数据库 `backups` 表 + 7 个 REST 端点（list / create / delete / lock / restore / 全量）
- SFTP 拉 startup.cfg / running.cfg 落盘
- 轮转（每设备保留 5 份非锁定，锁定不参与）
- 真机测试 192.168.100.4 已通过

但**前端仍是占位**：
- `frontend/src/views/Backup.vue` 是 141 行 preview 页，hardcoded "23 KB / 02:00 / 4 次"，注释明确写"V2.1 阶段：配置备份 / 回滚尚未对接后端，预览版留作后续"
- `frontend/src/api/index.js` 中**无 backupApi**（grep `backup` 0 命中）
- 设备/资产管理页面无任何"备份"入口
- 用户要"上线"得能实际用

### 用户需求（v2.2 备份前端专项）

- **3 个入口**：
  1. 侧边栏 `Backup.vue` 完整页：所有设备 × 所有备份的全局视图（按设备分组 / 设备筛选 / 锁定筛选 / 全量备份按钮）
  2. `Devices.vue` 单设备行：操作列加"备份"按钮 → 弹 BackupListModal（看该设备历史 + 立即备份）
  3. `CMDB.vue` 顶部：加"全量备份"按钮（POST `/api/backups`）
- **核心操作**：列表 / 立即备份 / 下载 / 删除 / 锁定切换 / 一键回滚
- **二次确认**：删除 / 回滚 / 锁定切换 必经 `ConfirmModal`
- **错误处理**：操作失败显示中文错误（API 已返回）

### 关键设计约束（继承 v2.1.x patch）

- 不做定时备份（用户明确拒绝）
- 不做"今日份"等花哨数据
- 不另起 FTP/SCP server
- 测试目标设备：192.168.100.4（与 v2.2 第一项一致）

### 风险

- 后端已上线，前端是最后一步；不做的话**整个备份能力等于不可用**
- 回滚是高风险操作（会把设备配置覆盖），UI 必须二次确认 + 显示关键信息

## What Changes

### 前端 API 客户端（`frontend/src/api/index.js` 新增）

```js
export const backupApi = {
  list(deviceId) { return http.get(`/api/devices/${deviceId}/backup`) },
  create(deviceId) { return http.post(`/api/devices/${deviceId}/backup`) },
  createAll() { return http.post('/api/backups') },
  download(deviceId, backupId) { return http.get(..., { responseType: 'blob' }) },
  remove(deviceId, backupId) { return http.delete(...) },
  toggleLock(deviceId, backupId, locked) { return http.post(..., { locked }) },
  restore(deviceId, backupId) { return http.post(...) },
}
```

### 前端 Modal 组件（`frontend/src/components/BackupListModal.vue` 新建）

- Props: `deviceId`, `visible`, `deviceName`
- 列表（id / 时间 / 大小 / 锁定状态 / hash 前 8 位）
- 操作列：下载 / 删除（锁定禁删）/ 锁定切换 / 回滚（二次确认）
- 顶部"立即备份"按钮
- 关闭按钮 + ESC

### 前端接入

- `Backup.vue` 重写：从 preview → 真实表格（全设备 × 全备份 / 按设备分组）
  - 顶部 4 个 KPI：备份总数 / 锁定数 / 总占用 / 今日新增
  - 表格：设备名 / 备份时间 / 大小 / 类型 / 锁定 / hash / 操作
  - 顶部"立即全量备份"按钮
- `Devices.vue` 操作列加"备份"按钮 → 弹 BackupListModal
- `CMDB.vue` 顶部加"全量备份"按钮 → 调用 backupApi.createAll() + 显示结果

## Capabilities

### 新增能力

- `backup-frontend`：完整备份前端能力（API 客户端 + 3 入口 + Modal）

### 影响的能力

无（v2.1.x patch 的 `v21x-patch-backup-backend` spec 仍生效；本次只补前端层）
