# v21-frontend-v2 Proposal

## Why

V2.0 阶段后端功能补齐完成（运维终端/接口管理/CMDB/批量操作/Dashboard 7 个 API），但前端仍停留在 V1.x 时代的 js/css 静态结构，视觉粗糙、导航松散、缺乏平台感。

之前在 `frontend-poc/` 完成了视觉/导航的 PoC 验证（米白调 + 顶部 mega menu + 10 views + Footer），但 PoC 没用真实后端 API，全部数据走 mock.js，且仅首页经过真实验证、子页面在 PoC 阶段未走查。

V2.1 阶段将 PoC 视觉成果正式落地为生产前端，并完成与后端 7 个 API 的对接，删掉 mock.js；本地端到端走查 10 个 view 并对子页面做适配升级；通过 QA 容器迭代修整确保 CI 流程稳定；最后旧 `frontend/` 保留为 `frontend.bak`（不被引用、可回滚）。`frontend-poc/` 仅本地保留，V2.1 归档后删除。

## What Changes

- **新开正式 frontend**：从 `frontend-poc/` 复制作为脚手架起步，删除 mock.js
- **后端对接**：7 个 view（Dashboard / Devices / Ops / Interfaces / Batch / CMDB / Logs）改用真 API 调用，替换 mock 数据
- **视觉系统**：复用 PoC 验证过的米白色板 / 阴影 / 圆角 / 字体 / 背景光晕
- **导航重构**：从旧 V2.0 平铺 5 tab 改为顶部 sticky nav + 三组 mega menu（运维操作 / 运营管理 / 排查诊断）
- **新增 5 个 view**（V2.0 缺失）：Interfaces / Batch（接 API）+ Topology / Backup / AIAssistant（未来占位）
- **新增官网式 Footer**
- **Dockerfile 适配**：支持 Vite + Tailwind 构建流程
- **本地端到端走查 + 子页面适配升级**：PoC 中未真验证的子页面，按视觉系统规范做适配
- **QA 容器修整迭代**：用 QA 测后端 → 本地补前端/适配 → 修整容器 → QA 再测，迭代至稳定
- **旧 frontend backup 推迟到 Phase 5**：新 frontend 稳定后 `git mv frontend frontend.bak`（不被引用、可回滚）
- **`frontend-poc/` 本地保留**：V2.1 归档后删除

### Non-Goals

- 不改后端 API（V2.0 已稳定）
- 不改数据库
- 不做暗色主题
- 不做移动端适配
- 不做国际化
- 不引入新依赖（Vue 3 / Vue Router / Vite / Tailwind 已在 PoC 验证）

## Capabilities

### New Capabilities

- `visual-system`: 视觉系统——米白色板、阴影层级、圆角规范、字体栈、背景光晕
- `top-nav`: 顶部导航——sticky nav + 三组 mega menu 下拉面板
- `app-footer`: 官网式底部——四列信息架构
- `content-width-control`: 内容区收束——max-w-1200px
- `backend-integration`: 后端对接——API 客户端封装 + 7 个 view 改用真实 API

### Modified Capabilities

- `platform-ui`: V2.0 侧边栏 → V2.1 顶部 nav，BREAKING 视觉风格切换
- `device-management`: V2.0 DeviceList → V2.1 Devices，视觉重做 + 保持 API 对接
- `log-viewer`: V2.0 LogViewer → V2.1 Logs，视觉重做 + 保持 API 对接

## Impact

- **前端**：目录切换 + 10 个 view 重构 + 后端对接（mock → API）+ Dockerfile 适配
- **后端**：零变更
- **数据库**：零变更
- **依赖**：前端新增 fetch（已有），无新依赖
- **部署**：Dockerfile.dev / Dockerfile.qa 适配 Vite + Tailwind 构建流程

## Rollback

- 旧 frontend 保留为 `frontend.bak`，不被任何 compose/CI 引用
- 回滚：`git mv frontend frontend-poc-restore && git mv frontend.bak frontend`
- `frontend-poc/` 本地保留至 V2.1 验证完毕

## Dependencies on Backend

V2.0 后端已实现的 7 个 API（直接对接）：

| API | View |
|---|---|
| GET /api/dashboard | Dashboard |
| GET/POST/PUT/DELETE /api/devices[/:id[/test]] | Devices |
| POST /api/devices/:id/execute | OpsTerminal |
| GET/POST /api/devices/:id/interfaces[/config] | Interfaces |
| POST /api/batch/execute | Batch |
| GET/PUT/POST /api/devices/:id/asset[/refresh] | CMDB |
| GET /api/logs | Logs |
