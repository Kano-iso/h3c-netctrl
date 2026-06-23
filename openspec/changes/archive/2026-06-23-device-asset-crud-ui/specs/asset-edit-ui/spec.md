## ADDED Requirements

### Requirement: 资产编辑 Modal 通用组件

`AssetEditModal.vue` MUST 接受 props `deviceId`、`v-model:open`、可选 `initial: {location, tags, status}`。Modal 内 MUST 包含 3 个字段：
- 位置（text input，预填 `initial.location`）
- 标签（text input，逗号分隔字符串，预填 `initial.tags`，占位提示"多个标签用逗号分隔"）
- 状态（Select 组件，选项 5 个值：online / offline / maintenance / decommissioned / unknown，label 通过 `getStatusLabel` 显示中文）

提交时 MUST 调 `PUT /api/devices/{deviceId}/asset` body `{location, tags, status}`，后端 `success=true` 后关闭 Modal 并 emit `('updated')`。

#### Scenario: 编辑位置 + 标签 + 状态
- **WHEN** 用户在 Modal 改 location="上海 IDC 3-A"、tags="核心,生产"、status="maintenance" 并提交
- **THEN** 前端调 `assetApi.update(deviceId, {location: "上海 IDC 3-A", tags: "核心,生产", status: "maintenance"})`；后端更新成功 → Modal 关闭、emit('updated')

#### Scenario: 状态字段可选值校验
- **WHEN** Modal 打开时 Select 组件 MUST 列出 5 个选项（在线 / 离线 / 维护 / 已下线 / 未采集）
- **THEN** 用户选择后 Select 显示对应中文 label，但提交 body 用英文 status 值

### Requirement: CMDB 页面提供资产编辑入口

`frontend/src/views/CMDB.vue` 表格行 / 卡片 MUST 显示"编辑资产"按钮，点击 MUST 打开 `AssetEditModal` 并预填当前设备的 asset 数据（location / tags / status）。Modal emit('updated') 后 MUST 重新调 `loadAssets()` 刷新列表。

#### Scenario: 表格行编辑资产
- **WHEN** 用户点击某设备行的"编辑资产"按钮
- **THEN** 打开 `AssetEditModal`，preload 该设备 asset 数据；用户修改后保存 → 表格对应行更新

#### Scenario: 卡片视图编辑资产
- **WHEN** 用户点击某设备卡片的"编辑"图标
- **THEN** 打开 `AssetEditModal`，preload 数据，保存 → 卡片位置/标签/状态更新

### Requirement: Devices 页面也提供资产编辑入口（一致性）

`frontend/src/views/Devices.vue` 表格每行 MUST 在"操作"列增加"编辑资产"按钮（与"连接测试"并列），点击 MUST 打开 `AssetEditModal`。Modal emit('updated') 后 MUST 重新调 `loadDevices()` 刷新列表。

#### Scenario: Devices 页编辑资产
- **WHEN** 用户在 Devices 表格点击"编辑资产"
- **THEN** Modal 打开预填数据，保存后 Devices 列表该行 status/location/tags 更新

### Requirement: 资产编辑不破坏 SSH 自动采集

用户编辑资产字段（位置 / 标签 / 状态）后 MUST 不影响"全量刷新"按钮触发的 SSH 采集。SSH 采集仅覆盖 model / serial_number / firmware_version / software_package 4 个硬件字段，不覆盖 location / tags。

#### Scenario: 手动编辑后全量刷新
- **WHEN** 用户手动设置 location="北京" 后点击"全量刷新"
- **THEN** SSH 采集完成后 location MUST 仍为"北京"（不丢失手填数据）；model / serial_number / firmware_version / software_package 被覆盖为最新硬件信息
