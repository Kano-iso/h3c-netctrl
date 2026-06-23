## Context

发布前 user feedback："CMDB 这块还是有单独采集吧，就是有全量采集，有单独采集"。

关键现状：
- 后端 `POST /api/devices/{id}/asset/refresh` 已实现（asset.py L80-118，SSH 采集 + 自动写库）
- 前端 `assetApi.refresh(deviceId)` 已导出（api/index.js L75-76）
- CMDB.vue 只有"全量刷新"按钮（Promise.all 并发触发所有设备的 refresh），无单设备入口
- 表格行/卡片已有"编辑资产"按钮（上一 change 加的）

修复本质是**单按钮 UI 增量**，最小化变更。

## Goals / Non-Goals

**Goals:**
- 表格行操作列新增"采集"按钮
- 卡片视图右上角加"采集"图标按钮
- 单设备采集期间按钮 disabled + loading 图标
- 采集完成（成功/失败）刷新该设备资产数据
- 多设备并发采集无限制
- 同一台设备重复点击采集按钮被忽略

**Non-Goals:**
- 不改后端
- 不改全量刷新按钮
- 不实现批量选中采集
- 不实现采集进度条（SSH 采集时间不可控，无进度反馈）

## Decisions

### 1. 按钮位置：表格行 + 卡片

- **选择**：
  - 表格行：操作列已有"编辑资产"按钮，再加"采集"按钮
  - 卡片：右上角已有"编辑"图标，再加"采集"图标
- **理由**：与现有 UI 一致
- **替代**：仅在表格行加。卡片缺失，UX 不一致

### 2. 状态管理：`refreshingIds: Set<number>`

- **选择**：用 `ref(new Set())` 跟踪正在采集的设备 id；按钮 `:disabled="refreshingIds.has(d.id)"` + `:class="..."` 切换样式
- **理由**：允许多设备并发采集（不全局 disable），同时防止同一台重复点击
- **替代**：全局 `refreshing` 标志。会导致一台采集中其他设备按钮全 disabled，UX 差

### 3. 采集反馈

- **选择**：
  - 成功 → 调 `loadAssets()` 刷新数据，按钮恢复
  - 失败 → `alert(r.error)` 显示后端错误，按钮恢复（finally 子句）
- **理由**：与现有"全量刷新"错误反馈一致（也是 alert）
- **替代**：toast 通知。引入新组件

### 4. 加载图标复用

- **选择**：复用 `btn-soft` 样式 + 已有 SVG spinner（与 AssetEditModal / DeviceFormModal 一致）
- **理由**：保持 UI 一致，无新增样式

## Risks / Trade-offs

- **[风险] 同一设备并发采集会引发 SSH 连接竞争** → **缓解**：后端 `SSHExecutor` 每次连接独立创建，NetconfClient 短连接模式；前端的 `refreshingIds` 防止用户并发触发同一设备
- **[风险] 单设备采集失败后 alert 干扰 UX** → **缓解**：与现有全量刷新错误反馈一致，不引入新模式
- **[风险] 用户连续点击不同设备的采集按钮 → 多次 loadAssets() 并发** → **缓解**：`loadAssets()` 内部 `loading.value = true` 防重入（已有逻辑）
- **[回归] 全量刷新按钮** → **不受影响**（独立状态变量 `refreshing` 已存在）
- **[回归] 编辑资产按钮** → **不受影响**（独立 `editingAsset` ref）

## Migration Plan

- **部署**：纯前端改动，vite HMR 自动热更新；无后端重启、无 DB 迁移
- **回退**：仅前端 UI 改动，回退简单（`git revert` 即可），无数据损坏
- **数据**：不影响后端存储结构
