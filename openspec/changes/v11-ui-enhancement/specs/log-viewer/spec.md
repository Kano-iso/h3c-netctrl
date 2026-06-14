## Capability: log-viewer

操作日志查看能力，前端展示后端日志，支持筛选和分页。

## Goal

为运维人员提供操作日志查看页面，记录所有设备操作（连接、VLAN 变更等），支持按设备、操作类型、时间筛选。

## Scope

### In Scope
- 后端日志记录中间件，自动记录所有设备操作
- 日志数据库表（logs）
- 日志查询 API（支持筛选、分页）
- 前端日志查看页面（`/logs`）
- 日志筛选：按设备、操作类型、时间范围
- 日志分页展示

### Out of Scope
- 实时日志推送（WebSocket）
- 日志导出（CSV/Excel）
- 日志自动清理策略
- 日志级别过滤（仅记录操作日志，不含 debug/info 系统日志）

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs` | 查询操作日志 |

**查询参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| `device_id` | int? | 按设备筛选 |
| `action` | string? | 按操作类型筛选（connect, vlan_create, vlan_update, vlan_delete） |
| `start_time` | datetime? | 起始时间 |
| `end_time` | datetime? | 结束时间 |
| `page` | int | 页码，默认 1 |
| `page_size` | int | 每页条数，默认 20 |

**响应格式：**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 1,
        "device_id": 1,
        "device_name": "SW-Core-1",
        "action": "vlan_create",
        "detail": "创建 VLAN 100 (name=Test)",
        "status": "success",
        "created_at": "2026-06-13T10:30:00"
      }
    ],
    "total": 50,
    "page": 1,
    "page_size": 20
  }
}
```

## Data Model Changes

### 新增 `logs` 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | Integer | 主键，自增 | |
| `device_id` | Integer | 外键 → devices.id | 关联设备 |
| `action` | String(50) | NOT NULL | 操作类型 |
| `detail` | String(500) | NOT NULL | 操作详情 |
| `status` | String(20) | NOT NULL | 操作结果（success/failed） |
| `created_at` | DateTime | 默认 now() | 操作时间 |

**操作类型枚举：**
- `connect` — 设备连接测试
- `vlan_create` — 创建 VLAN
- `vlan_update` — 修改 VLAN
- `vlan_delete` — 删除 VLAN

## Acceptance Criteria

- [ ] logs 表创建成功，含 device_id 外键
- [ ] 设备操作（连接测试、VLAN 增删改）自动写入日志
- [ ] GET /api/logs 返回分页日志数据
- [ ] 支持按 device_id、action、时间范围筛选
- [ ] 前端日志页面展示日志列表（时间、设备、操作、详情、状态）
- [ ] 前端支持筛选和分页操作
