## Why

V1.x 是一个"VLAN 管理工具"，功能可用但缺乏平台感：前端只是功能按钮堆砌，没有导航体系；只能管理 VLAN，无法执行命令、查看接口、管理资产；单设备操作无法批量下发。V2.0 要将其升级为"网络运维平台"，补齐命令执行、接口管理、CMDB、批量操作能力，同时前端从简陋页面演进为具备侧边栏导航 + Dashboard 的平台级体验。

## What Changes

- 新增网络运维终端：命令派发式执行（输入命令 → paramiko SSH → 返回输出），非交互式终端
- 新增接口管理：NETCONF 拉取接口列表，Access/Trunk 联动配置下发
- 新增 CMDB 资产管理：设备资产台账（型号/SN/固件/位置/标签/状态），一键刷新硬件信息
- 新增批量操作：多设备勾选 → 批量执行命令 → 汇总结果
- 前端平台化演进：顶部导航 → 侧边栏导航，新增 Dashboard 仪表盘，视觉升级
- 工程保障：引入 Alembic 管理数据库迁移，GitHub Actions 基础 CI（推送自动验证）
- **BREAKING**：前端导航结构从顶部改为侧边栏，所有页面布局需适配

## Capabilities

### New Capabilities
- `ops-terminal`: 网络运维终端——命令派发式执行，SSH 命令输入/输出展示，命令历史
- `interface-management`: 接口管理——接口列表查看，Access/Trunk 联动配置下发
- `cmdb`: CMDB 资产管理——设备资产台账，硬件信息自动采集，位置/标签/状态管理
- `batch-operations`: 批量操作——多设备命令批量执行，结果汇总
- `platform-ui`: 前端平台化——侧边栏导航、Dashboard 仪表盘、视觉升级
- `engineering-infra`: 工程基础设施——Alembic 数据库迁移、GitHub Actions CI

### Modified Capabilities
- `device-management`: 新增资产信息关联（assets 表外键），设备详情页增加资产标签页
- `log-viewer`: 新增命令执行日志类型（execute），批量操作日志

## Impact

- **前端**：导航结构重构（顶部→侧边栏），新增 4 个页面（运维终端、接口管理、CMDB、批量操作），Dashboard 新页面
- **后端**：新增 7 个 API 端点，新增 assets 表，新增 paramiko SSH 命令执行能力
- **数据库**：新增 assets 表，引入 Alembic 迁移管理
- **依赖**：后端新增 paramiko SSH exec_command 用法（已有 paramiko 依赖），前端无新依赖
- **部署**：docker-compose 无变更，GitHub Actions 新增 `.github/workflows/ci.yml`
