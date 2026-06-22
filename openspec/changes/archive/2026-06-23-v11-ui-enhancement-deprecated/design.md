## Context

v1.0 使用原生 HTML + Bootstrap CDN 实现了单页面前端，功能上可用但存在以下限制：
- 无导航结构，无法扩展子页面
- 仅支持单设备，无设备切换能力
- 无运维视角（日志查看）
- 原生 JS 无组件化，后续维护成本高

当前后端 API 设计为单设备模式（`/api/device`），需扩展为多设备模式。

## Goals / Non-Goals

**Goals:**
- 引入 Vue 3 + Vite 前端框架，实现组件化开发
- 实现导航栏 + Vue Router 多页面路由
- 实现多设备管理（设备列表、添加/删除、切换设备视图）
- 实现日志查看页面（运维视角）
- 后端 API 扩展为多设备模式
- 保持后端对前端框架的零耦合（纯 REST API）

**Non-Goals:**
- 不做监控、故障排查、资产信息等后续功能页面（仅预留导航位）
- 不做用户认证/权限系统
- 不做 WebSocket 实时推送
- 不做国际化

## Decisions

### D1: 前端框架选型 — Vue 3 + Vite

**选择**：Vue 3 (Composition API) + Vite + Vue Router

**备选方案**：
| 方案 | 优点 | 缺点 |
|---|---|---|
| React + Vite | 生态最大 | JSX 学习曲线，对网络管理场景偏重 |
| Vue 3 + Vite | 上手简单，中文生态好，模板语法直观 | 生态小于 React |
| 继续原生 HTML | 零依赖 | 无法组件化，无法路由，无法扩展 |

**理由**：
- Vue 模板语法对网络管理场景直观（表单、表格多）
- Composition API 逻辑复用清晰
- Vite 开发体验好（HMR 快，构建快）
- 对后端零影响，前端独立构建

### D2: 前端构建策略 — Docker 多阶段构建

**选择**：前端容器使用多阶段构建（Node.js 构建 → Nginx 运行）

```dockerfile
# 阶段1: Node.js 构建
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# 阶段2: Nginx 运行
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

**理由**：
- 生产镜像不含 Node.js，保持轻量
- 开发环境仍可挂载源码 + Vite dev server 热重载

### D3: API 路径变更 — 单数变复数

**选择**：`/api/device` → `/api/devices`，VLAN API 增加 device_id 参数

| v1.0 | v1.1 |
|---|---|
| `GET /api/device` | `GET /api/devices` |
| `POST /api/device` | `POST /api/devices` |
| `PUT /api/device` | `PUT /api/devices/{id}` |
| `POST /api/device/test` | `POST /api/devices/{id}/test` |
| `GET /api/vlans` | `GET /api/devices/{id}/vlans` |
| `POST /api/vlans` | `POST /api/devices/{id}/vlans` |

**理由**：RESTful 规范，资源嵌套表达从属关系

### D4: 日志存储 — 数据库表

**选择**：新增 `logs` 表存储操作日志，提供查询 API

**备选方案**：
| 方案 | 优点 | 缺点 |
|---|---|---|
| 读日志文件 | 简单 | 无法筛选、分页，文件格式不稳定 |
| 数据库表 | 可筛选、分页、结构化 | 写入开销 |

**理由**：操作日志量不大（人工操作），数据库表可提供更好的查询体验

### D5: 开发环境前端热重载

**选择**：开发环境使用 Vite dev server（端口 5173），通过 docker-compose 暴露

**理由**：Vite HMR 毫秒级热重载，开发体验远优于 nginx 静态服务。生产环境仍用 nginx。

## Risks / Trade-offs

- **[API Breaking Change]** → 提供 v1 兼容路由（`/api/device` 重定向到 `/api/devices`），过渡期后移除
- **[前端重构范围大]** → 分阶段实施：先框架迁移 → 再多设备 → 再日志，每阶段可独立验证
- **[Docker 构建变慢]** → 前端新增 Node.js 构建阶段，利用 Docker 缓存层优化（package.json 单独 COPY）
- **[日志表增长]** → 初期不做自动清理，后续可加定时任务清理 30 天前日志
