## Capability: multi-device

多设备管理能力，支持设备列表、添加/删除设备、切换设备视图。

## Goal

将 v1.0 的单设备模式扩展为多设备模式，用户可管理多台交换机，点击设备进入设备详情视图。

## Scope

### In Scope
- 设备列表页面（首页），展示所有已添加设备
- 添加设备弹窗（表单：名称、IP、端口、用户名、密码）
- 删除设备（带确认弹窗）
- 设备连接状态指示（在线/离线/未知）
- 点击设备进入设备详情页（`/devices/:id`）
- 设备详情页展示设备基本信息 + VLAN 管理功能

### Out of Scope
- 设备自动发现
- 设备分组/标签
- 批量操作
- 设备配置备份/恢复

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 获取设备列表 |
| POST | `/api/devices` | 添加设备 |
| DELETE | `/api/devices/{id}` | 删除设备 |
| GET | `/api/devices/{id}` | 获取单个设备详情 |
| PUT | `/api/devices/{id}` | 更新设备信息 |
| POST | `/api/devices/{id}/test` | 测试设备连接 |

### 变更端点（BREAKING）
| v1.0 | v1.1 | 说明 |
|------|------|------|
| `GET /api/device` | `GET /api/devices` | 单数变复数 |
| `POST /api/device` | `POST /api/devices` | 单数变复数 |
| `PUT /api/device` | `PUT /api/devices/{id}` | 需指定设备 ID |
| `POST /api/device/test` | `POST /api/devices/{id}/test` | 需指定设备 ID |
| `GET /api/vlans` | `GET /api/devices/{id}/vlans` | VLAN 归属设备 |
| `POST /api/vlans` | `POST /api/devices/{id}/vlans` | VLAN 归属设备 |
| `PUT /api/vlans/{vlan_id}` | `PUT /api/devices/{id}/vlans/{vlan_id}` | VLAN 归属设备 |
| `DELETE /api/vlans/{vlan_id}` | `DELETE /api/devices/{id}/vlans/{vlan_id}` | VLAN 归属设备 |

### 兼容策略
- 保留 v1.0 路由（`/api/device`）作为兼容层，重定向到 `/api/devices`
- 兼容层标记为 deprecated，v1.2 移除

## Data Model Changes

Device 表已有 `id` 主键，无需结构变更。VLAN 仍从设备实时读取，不存数据库。

## Acceptance Criteria

- [ ] 设备列表页展示所有设备（名称、IP、状态）
- [ ] 可添加新设备（表单校验：IP 格式、端口范围、必填项）
- [ ] 可删除设备（二次确认）
- [ ] 点击设备进入详情页，URL 为 `/devices/{id}`
- [ ] 设备详情页展示设备信息 + VLAN 管理功能
- [ ] VLAN 操作（增删改查）在设备详情页内完成
- [ ] API 路径变更后，v1.0 兼容路由仍可用
