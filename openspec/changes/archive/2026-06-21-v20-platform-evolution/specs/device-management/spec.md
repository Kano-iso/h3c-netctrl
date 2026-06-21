## Capability: device-management (Modified)

V2.0 变更：设备详情页增加资产信息标签页，创建设备时自动创建空资产记录。

## What Changes

- 设备详情页新增"资产信息"标签页（与 VLAN 管理并列）
- 创建设备时自动创建 assets 表关联记录
- 设备列表页新增"型号"和"状态"列（从 assets 表读取）
- 删除设备时级联删除 assets 记录

## API Changes

无新增端点。现有端点行为变更：
- `POST /api/devices`：创建设备后自动创建空 assets 记录
- `DELETE /api/devices/{id}`：级联删除 assets 记录
- `GET /api/devices`：响应中可选包含 asset 摘要信息

## Data Model Changes

assets 表新增（由 cmdb spec 定义），devices 表无变更。
需在 Device 模型添加 `asset` relationship（一对一）。

## Acceptance Criteria

- [ ] 创建设备后 assets 表自动创建对应记录
- [ ] 删除设备时 assets 表对应记录级联删除
- [ ] 设备详情页展示资产信息标签页
- [ ] 设备列表页展示型号和状态列
