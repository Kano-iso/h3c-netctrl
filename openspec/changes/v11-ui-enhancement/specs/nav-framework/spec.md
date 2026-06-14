## Capability: nav-framework

导航框架，支持多页面路由切换，为后续子页面预留扩展位。

## Goal

引入 Vue 3 + Vue Router 实现前端导航框架，替代当前单页面架构，支持多页面切换和后续功能模块扩展。

## Scope

### In Scope
- Vue 3 + Vite 项目初始化（替代原生 HTML + Bootstrap）
- Vue Router 配置，支持以下路由：
  - `/` — 设备列表页（首页）
  - `/devices/:id` — 设备详情页（VLAN 管理等）
  - `/logs` — 日志查看页
- 顶部导航栏组件，包含：品牌标识、页面导航链接、当前页面高亮
- 基础布局组件（导航栏 + 内容区）
- Vite 开发服务器配置（端口 5173，API 代理到后端 8000）

### Out of Scope
- 各页面具体业务逻辑（由其他 spec 覆盖）
- 用户认证/权限
- 移动端适配
- 面包屑导航

## API Changes

无新增后端 API。前端通过 Vite proxy 转发 `/api` 请求到后端。

## Data Model Changes

无数据库变更。

## Acceptance Criteria

- [ ] Vue 3 + Vite 项目可正常启动（`npm run dev`）
- [ ] Vue Router 配置 3 条路由，页面切换无刷新
- [ ] 导航栏显示品牌标识 + 3 个导航链接
- [ ] 当前页面导航链接高亮
- [ ] Vite dev server 代理 `/api` 到后端 8000 端口
- [ ] 原有前端功能在 Vue 迁移后仍正常工作
