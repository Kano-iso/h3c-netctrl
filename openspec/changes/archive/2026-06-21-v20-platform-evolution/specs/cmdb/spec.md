## Capability: cmdb

CMDB 资产管理，设备资产台账。

## Goal

为每台设备建立资产档案，记录型号、SN、固件版本等硬件信息，支持物理位置、业务标签、管理状态等手动维护字段，支持一键刷新硬件信息。

## Scope

### In Scope
- assets 数据库表（关联 devices 表）
- 设备详情页增加"资产信息"标签页
- 手动编辑资产信息（位置、标签、状态）
- 一键刷新硬件信息（SSH 命令采集：型号/SN/固件/CPU/内存）
- 设备列表页展示关键资产列（型号、状态）

### Out of Scope
- 资产变更历史
- 资产导入/导出
- 资产关联关系（设备间依赖）
- IP 地址段管理

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/devices/{id}/asset | 获取资产信息 |
| PUT | /api/devices/{id}/asset | 更新资产信息 |
| POST | /api/devices/{id}/asset/refresh | 刷新硬件信息 |

**资产信息响应：**
```json
{
  "success": true,
  "data": {
    "device_id": 1,
    "model": "H3C S6850",
    "serial_number": "CN12345678",
    "firmware_version": "Release 7808",
    "cpu_usage": "15%",
    "memory_usage": "42%",
    "location": "机房A-机架03-U15",
    "tags": "核心,数据中心",
    "status": "online",
    "updated_at": "2026-06-14T10:00:00"
  }
}
```

## Data Model Changes

### 新增 `assets` 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | 主键，自增 | |
| device_id | Integer | 外键→devices.id, UNIQUE | 一对一关联 |
| model | String | 可空 | 设备型号 |
| serial_number | String | 可空 | SN 序列号 |
| firmware_version | String | 可空 | 固件版本 |
| cpu_usage | String | 可空 | CPU 使用率 |
| memory_usage | String | 可空 | 内存使用率 |
| location | String | 可空 | 物理位置 |
| tags | String | 可空 | 业务标签（逗号分隔） |
| status | String | 默认"unknown" | 管理状态（online/offline/maintenance/decommissioned/unknown） |
| updated_at | DateTime | 默认now()，更新时刷新 | 更新时间 |

## Acceptance Criteria

- [ ] assets 表创建成功，device_id 外键关联 devices 表
- [ ] 设备详情页展示资产信息标签页
- [ ] 可手动编辑位置、标签、状态
- [ ] 一键刷新通过 SSH 命令采集型号/SN/固件/CPU/内存
- [ ] 设备列表页展示型号和状态列
- [ ] 创建设备时自动创建空资产记录
