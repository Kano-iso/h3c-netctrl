## Capability: interface-management

接口管理，查看接口列表和配置，下发 Access/Trunk 联动配置。

## Goal

通过 SSH 命令获取接口列表和状态，通过 NETCONF edit-config 下发接口配置，支持 Access/Trunk 联动操作。

## Scope

### In Scope
- 接口列表查看（名称、状态、模式、允许 VLAN、PVID）
- Access 接口配置：设置模式 + 所属 VLAN
- Trunk 接口配置：设置模式 + 允许 VLAN + PVID
- 联动配置一次性下发（模式+VLAN 原子操作）
- 接口配置页面在设备详情页内

### Out of Scope
- 接口流量统计
- 接口速率/双工配置
- 接口描述（description）修改
- 批量接口配置（由 batch-operations 覆盖）

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/devices/{id}/interfaces | 获取接口列表 |
| PUT | /api/devices/{id}/interfaces/{name}/config | 下发接口配置 |

**接口列表响应：**
```json
{
  "success": true,
  "data": [
    { "name": "GigabitEthernet1/0/1", "status": "up", "mode": "access", "access_vlan": 10, "allowed_vlans": [], "pvid": 10 }
  ]
}
```

**接口配置请求体：**
```json
// Access 模式
{ "mode": "access", "access_vlan": 100 }

// Trunk 模式
{ "mode": "trunk", "allowed_vlans": [10, 20, 30], "pvid": 10 }
```

## Data Model Changes

无新表。接口信息从设备实时获取，不持久化。

## Implementation Notes

1. 接口列表获取：SSH `display interface brief` → 解析输出
2. 接口配置下发：NETCONF edit-config，需探测 H3C 接口 XML 结构
3. 联动配置：Access 模式需同时下发接口类型+VLAN，Trunk 模式需同时下发类型+允许VLAN+PVID

## Acceptance Criteria

- [ ] 接口列表正确展示设备所有接口
- [ ] Access 配置：选择接口 → 设置模式 → 选择 VLAN → 一次下发成功
- [ ] Trunk 配置：选择接口 → 设置模式 → 选择允许 VLAN + PVID → 一次下发成功
- [ ] 配置失败时返回友好错误提示，设备配置不变
- [ ] 操作日志自动记录
