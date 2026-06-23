## Why

CMDB.vue 当前只有"全量刷新"按钮（`refresh()` 触发所有设备并发 SSH 采集）。用户需求：

- 只想刷新单台设备的资产（如某台刚配置好、新接入的设备）时，**不必全量**
- 单台刷新时**反馈即时**，无需等其他设备
- 单台失败不阻塞其他设备（虽然在全量模式下已经是并发的，但单台刷新能明确"针对哪台"）

**来源**：发布前 user feedback 建议"CMDB 这块还是有单独采集吧，就是有全量采集，有单独采集"。

**关键发现**：后端 `POST /api/devices/{id}/asset/refresh` 已实现（asset.py L80-118，SSH 采集 + 自动写库），前端 `assetApi.refresh(deviceId)` 也已导出（api/index.js L75-76）。**仅缺 UI 入口**。

## What Changes

### CMDB.vue 改造

- **表格行操作列**新增"采集"按钮（与现有"编辑资产"并列），调 `assetApi.refresh(d.id)` 触发单设备 SSH 采集
- **卡片视图**每张卡片右上角加"采集"图标按钮（与"编辑"图标并列）
- **采集进行中**状态：按钮 disabled + loading 图标 + "采集中..." 文本
- **采集完成**：
  - 成功 → 调 `loadAssets()` 刷新该行/卡片数据
  - 失败 → alert 显示后端 error 信息，按钮恢复可点击
- **顶部"全量刷新"按钮**：保持不变，行为不变
- **禁止并行采集**同一台设备：通过 `refreshingIds = new Set()` 跟踪正在采集的设备 id，重复点击同一设备的采集按钮被忽略

### 不改动

- `assetApi.refresh` API 客户端（已存在）
- 后端 `POST /api/devices/{id}/asset/refresh`（已存在）
- 全量刷新按钮行为

## Capabilities

### New Capabilities
- `cmdb-single-asset-refresh`：CMDB 单设备资产采集入口

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：
  - `frontend/src/views/CMDB.vue`：表格行 + 卡片视图加"采集"按钮
  - `refreshingIds: Set<number>` 跟踪并发采集状态
- **API 兼容性**：纯前端，调用现有 `assetApi.refresh(deviceId)`
- **数据库**：无迁移
- **依赖**：无新增
- **回归**：全量刷新按钮行为不变
- **并发安全**：单设备采集期间该设备按钮 disabled，多设备并发采集无限制
