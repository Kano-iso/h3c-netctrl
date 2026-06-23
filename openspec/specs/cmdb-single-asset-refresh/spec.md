# cmdb-single-asset-refresh Specification

## Purpose
TBD - created by archiving change cmdb-single-asset-refresh. Update Purpose after archive.
## Requirements
### Requirement: CMDB 表格行提供单设备采集入口

`frontend/src/views/CMDB.vue` 表格行操作列 MUST 在"编辑资产"按钮左侧增加"采集"按钮。点击 MUST 触发 `assetApi.refresh(deviceId)` 调 `POST /api/devices/{id}/asset/refresh`。按钮在采集期间 MUST 显示"采集中..." + spinner 图标，并处于 disabled 状态。采集完成（成功或失败）MUST 自动调 `loadAssets()` 刷新该行数据。

#### Scenario: 单设备采集成功
- **WHEN** 用户点击某行的"采集"按钮
- **THEN** 前端调 `assetApi.refresh(id)`；按钮立即变 disabled + spinner；后端返回 `success=true` 后 `loadAssets()` 触发，表格该行 model/firmware 等硬件字段更新为最新值

#### Scenario: 单设备采集失败
- **WHEN** 后端返回 `success=false, error="SSH 连接失败"`
- **THEN** 前端 MUST 通过 `alert` 显示后端 error；按钮恢复可点击；`loadAssets()` 仍执行（防止部分成功时 UI 与数据不一致）

#### Scenario: 同一设备重复点击
- **WHEN** 某设备采集中用户再次点击该设备的"采集"按钮
- **THEN** 前端 MUST 忽略第二次点击（按钮已 disabled）

### Requirement: CMDB 卡片视图提供单设备采集入口

`frontend/src/views/CMDB.vue` 卡片视图右上角 MUST 在"编辑"图标左侧增加"采集"图标按钮（与"编辑"同尺寸、相同 SVG style）。点击行为 MUST 与表格行"采集"按钮一致。

#### Scenario: 卡片采集成功
- **WHEN** 用户点击某卡片的"采集"图标
- **THEN** 图标变 spinner + 灰色；后端返回 success 后 `loadAssets()` 触发，相应卡片 model/firmware 更新

#### Scenario: 卡片采集失败
- **WHEN** 后端返回 `success=false`
- **THEN** alert 显示错误；图标恢复可点击

### Requirement: 多设备并发采集

CMDB MUST 允许多台设备同时采集（不同设备互不阻塞）。当设备 A 采集中时，设备 B 的采集按钮 MUST 仍可点击。

#### Scenario: 两台设备并发采集
- **WHEN** 用户依次点击设备 A、采集按钮，再点击设备 B 采集按钮
- **THEN** A 和 B 按钮同时处于 disabled + spinner 状态；后端两个 `POST /api/devices/{id}/asset/refresh` 并发执行；各自完成后各自 `loadAssets()` 刷新（共享一个 `loadAssets` 因其内部 `loading` 防重入，多余调用快速返回）

### Requirement: 全量刷新按钮保持不变

CMDB 顶部"全量刷新"按钮 MUST 行为不变：点击触发所有设备并发 SSH 采集，采集期间显示"采集中..." + spinner，采集完成显示"刷新完成"提示。

#### Scenario: 全量刷新不受影响
- **WHEN** 用户点击"全量刷新"
- **THEN** 现有 `refresh()` 函数被调用，行为与上一版本完全一致

