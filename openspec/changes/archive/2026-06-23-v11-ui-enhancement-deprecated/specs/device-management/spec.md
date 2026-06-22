## Capability: device-management (Modified)

从单设备扩展为多设备，API 路径从 `/api/device` 变为 `/api/devices`。

## Goal

重构后端设备管理 API，从单设备模式（隐式获取唯一设备）改为多设备模式（通过 ID 指定设备），同时重构 VLAN API 使其归属到具体设备下。

## Scope

### In Scope
- 重构设备路由：`/api/device` → `/api/devices`，支持多设备 CRUD
- 重构 VLAN 路由：`/api/vlans` → `/api/devices/{id}/vlans`，VLAN 操作需指定设备
- 新增删除设备端点：`DELETE /api/devices/{id}`
- 新增获取单个设备端点：`GET /api/devices/{id}`
- v1.0 兼容路由层（`/api/device` 重定向到 `/api/devices`）
- NETCONF 客户端适配：根据设备 ID 查找设备配置建立连接
- 数据库迁移：无结构变更，Device 表已有 id 主键

### Out of Scope
- 设备自动发现
- 设备分组
- 设备配置备份

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 获取设备列表 |
| GET | `/api/devices/{id}` | 获取单个设备 |
| DELETE | `/api/devices/{id}` | 删除设备 |

### 变更端点
| v1.0 | v1.1 | 变更说明 |
|------|------|---------|
| `GET /api/device` | `GET /api/devices` | 返回列表而非单个 |
| `POST /api/device` | `POST /api/devices` | 路径变更 |
| `PUT /api/device` | `PUT /api/devices/{id}` | 需指定设备 ID |
| `POST /api/device/test` | `POST /api/devices/{id}/test` | 需指定设备 ID |
| `GET /api/vlans` | `GET /api/devices/{id}/vlans` | 需指定设备 ID |
| `POST /api/vlans` | `POST /api/devices/{id}/vlans` | 需指定设备 ID |
| `PUT /api/vlans/{vlan_id}` | `PUT /api/devices/{id}/vlans/{vlan_id}` | 需指定设备 ID |
| `DELETE /api/vlans/{vlan_id}` | `DELETE /api/devices/{id}/vlans/{vlan_id}` | 需指定设备 ID |

### 兼容路由
- `GET /api/device` → 返回第一个设备（兼容 v1.0 前端）
- `POST /api/device` → 等同 `POST /api/devices`
- `PUT /api/device` → 更新第一个设备
- `POST /api/device/test` → 测试第一个设备连接
- 兼容路由标记 `DeprecationWarning` 响应头

## Data Model Changes

无结构变更。Device 表已有 `id` 自增主键。

## Implementation Notes

1. **路由重构**：将 `routers/device.py` 拆分为新的多设备路由，保留旧路由作为兼容层
2. **VLAN 路由**：`routers/vlan.py` 增加 `device_id` 路径参数，NETCONF 连接根据 device_id 查找设备
3. **NETCONF 客户端**：`netconf_client.py` 无需修改，仍接收 host/port/username/password 参数
4. **Pydantic 模型**：新增 `DeviceListResponse`，`DeviceCreate`/`DeviceUpdate` 无需变更

## Acceptance Criteria

- [ ] `GET /api/devices` 返回设备列表
- [ ] `GET /api/devices/{id}` 返回指定设备
- [ ] `POST /api/devices` 创建新设备
- [ ] `PUT /api/devices/{id}` 更新指定设备
- [ ] `DELETE /api/devices/{id}` 删除指定设备
- [ ] `POST /api/devices/{id}/test` 测试指定设备连接
- [ ] VLAN API 全部挂载到 `/api/devices/{id}/vlans` 下
- [ ] v1.0 兼容路由仍可正常工作
- [ ] 兼容路由响应头包含 `Deprecation` 标记
