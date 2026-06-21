## Capability: batch-operations

批量操作，多设备命令批量执行。

## Goal

支持选择多台设备，执行同一命令，汇总展示每台设备的执行结果。

## Scope

### In Scope
- 设备列表页多选功能（勾选框）
- 批量执行命令弹窗
- 并行执行（每台设备独立 SSH 连接）
- 结果汇总表格（设备名、成功/失败、输出/错误）
- 操作日志批量记录

### Out of Scope
- 批量配置下发（接口/VLAN 批量操作）
- 定时批量任务
- 批量结果导出
- 批量执行进度条（简化为完成后展示）

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/batch/execute | 批量执行命令 |

**请求体：**
```json
{
  "device_ids": [1, 2, 3],
  "command": "display version"
}
```

**响应体：**
```json
{
  "success": true,
  "data": {
    "total": 3,
    "success_count": 2,
    "failed_count": 1,
    "results": [
      { "device_id": 1, "device_name": "SW-1", "success": true, "output": "..." },
      { "device_id": 2, "device_name": "SW-2", "success": true, "output": "..." },
      { "device_id": 3, "device_name": "SW-3", "success": false, "error": "连接超时" }
    ]
  }
}
```

## Data Model Changes

无新表。批量执行结果不持久化，每条命令执行记录操作日志。

## Acceptance Criteria

- [ ] 设备列表页支持多选
- [ ] 选中后弹出批量操作弹窗，输入命令
- [ ] 执行后展示汇总结果表格
- [ ] 部分设备失败不影响其他设备执行
- [ ] 每条命令执行自动记录操作日志
