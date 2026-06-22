## Why

v1.0 实现了单设备 VLAN 管理的最小可用功能，但前端为纯静态页面，缺乏导航结构、多设备管理和运维视角。随着功能扩展（监控、故障排查、资产信息等），当前单页面架构无法支撑。需要在 v1.1 阶段引入前端框架、导航体系和多设备管理，为后续功能模块奠定基础。

## What Changes

- 引入 Vue 3 前端框架，替代当前原生 HTML + Bootstrap 方案
- 实现导航栏，支持多页面切换（设备管理、VLAN 管理、日志查看等）
- 实现多设备管理：设备列表 + 点击进入设备视图（VLAN、后续路由协议等）
- 实现日志查看页面：展示操作日志，提供运维视角
- 后端 API 扩展：支持多设备 CRUD（从单设备扩展为多设备）
- 后端 API 扩展：新增日志查询接口

## Capabilities

### New Capabilities
- `multi-device`: 多设备管理能力，支持设备列表、添加/删除设备、切换设备视图
- `log-viewer`: 操作日志查看能力，前端展示后端日志，支持筛选和分页
- `nav-framework`: 导航框架，支持多页面路由切换，为后续子页面预留扩展位

### Modified Capabilities
- `device-management`: 从单设备扩展为多设备，API 路径从 `/api/device` 变为 `/api/devices`，**BREAKING**

## Impact

- **前端重构**：从原生 HTML 迁移到 Vue 3 + Vite，需要新增 Node.js 构建流程
- **后端 API 变更**：设备管理 API 路径变更（单数 → 复数），VLAN API 需要增加设备 ID 参数
- **数据库**：Device 表已有 id 主键，无需结构变更；需新增 Log 表
- **Docker**：前端容器需要 Node.js 构建阶段，nginx.conf 需适配 Vue SPA 路由
- **依赖**：前端新增 Vue 3、Vue Router、Vite；后端新增日志查询接口
