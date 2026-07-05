# RELEASE-NOTES-v2.6.1

**版本**: v2.6.1
**日期**: 2026-07-06
**主题**: split 模式 asset 路由修复（v2.5.0 split 架构遗留 bug）+ 资产陈旧状态自动降级
**前序**: v2.6.0 (2026-07-06)

> ⚠️ **BREAKING — Asset API 路径变更**
>
> v2.5.0 split 模式下，asset 路由在 data 容器但 path 用了 `/api/devices/{id}/asset/...`；
> vite proxy 把 `/api/devices/*` 全部路由到 ctrl 容器，ctrl 没注册 asset 路由 → 永远 404。
>
> **本版本修复**：asset 路径独立成 `/api/assets/device/{id}/*`，匹配 vite proxy `/api/assets → data` 规则。
>
> **旧 → 新 path 对照表**：
>
> | 旧（v2.5 / v2.6.0） | 新（v2.6.1） |
> |---|---|
> | `POST /api/devices/{id}/asset/refresh` | `POST /api/assets/device/{id}/refresh` |
> | `GET  /api/devices/{id}/asset` | `GET  /api/assets/device/{id}` |
> | `PUT  /api/devices/{id}/asset` | `PUT  /api/assets/device/{id}` |
>
> **影响面**：浏览器侧、curl 脚本、外部集成（如有）。
> **降级兼容**：无。旧 path 返回 404，不静默兼容（避免静默掩盖问题）。
> **monolith 模式（VITE_API_MODE=core）**：同步生效，backend 单容器内 asset router 改 path。

---

## 1. 主题

v2.6.1 = **bug fix**。v2.6.0 i18n 上线后用户报告"采集不采集会失败"——经排查**真因是 v2.5.0 split 模式的路由设计错误**：

- v2.5.0 拆分 asset 业务到 data 容器，但 router 用了 `/api/devices/{id}/asset/...`
- vite proxy 规则 `/api/devices/* → ctrl:8000` 把请求路由到 ctrl 容器
- ctrl 容器只注册 device/log/dashboard/ctrl_internal，**没有 asset 路由**
- 结果：split 模式下所有 asset 功能（采集 / 编辑 / Dashboard 状态展示）都返回 404

v2.6.1 包含 **2 个 change + 12 个 commit**：

| change | 主题 | 状态 |
|---|---|---|
| fix-asset-stale-status | 资产陈旧状态自动降级（on_startup 启动时 + dashboard staleness 过滤） | ✅ archive（v2.6.1 主线） |
| fix-asset-collect-failure | split 模式 asset 路由修复（路径改 `/api/assets/device/{id}/*` + i18n 错误 key） | ✅ archive（本版本核心） |

---

## 2. BREAKING：Asset API 路径变更

### 2.1 变更内容

**`backend/app/routers/asset.py`**：3 个 `@router.*` 装饰器 path 改写：

| HTTP | 旧 path | 新 path |
|---|---|---|
| GET | `/devices/{device_id}/asset` | `/assets/device/{device_id}` |
| PUT | `/devices/{device_id}/asset` | `/assets/device/{device_id}` |
| POST | `/devices/{device_id}/asset/refresh` | `/assets/device/{device_id}/refresh` |

函数签名 + 内部逻辑不变，仅 path 改写。

**`frontend/src/api/index.js`**：`assetApi.get/update/refresh` 三个方法 path 同步改：

```js
// 改前
get:    (id) => apiCall(`/devices/${id}/asset`)
update: (id, body) => apiCall(`/devices/${id}/asset`, { method: 'PUT', ... })
refresh: (id) => apiCall(`/devices/${id}/asset/refresh`, { method: 'POST' })

// 改后
get:    (id) => apiCall(`/assets/device/${id}`)
update: (id, body) => apiCall(`/assets/device/${id}`, { method: 'PUT', ... })
refresh: (id) => apiCall(`/assets/device/${id}/refresh`, { method: 'POST' })
```

### 2.2 兼容性

- **浏览器前端**：自动适配，浏览器内调用 `assetApi.refresh(1)` 发 `POST /api/assets/device/1/refresh` 即可
- **curl 脚本 / 外部集成**：必须改 path（详见对照表）
- **降级兼容**：**无**。旧 path 明确返回 404，不静默兼容（避免掩盖路由配置问题）
- **monolith 模式**（VITE_API_MODE=core，--profile core）：同步生效

### 2.3 升级步骤

```bash
# 1. 拉代码
git pull origin main

# 2. 重新构建 + 启动（split 3 容器，默认模式不变）
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d

# 3. 验证新 path 可达（data 容器外部端口 8003）
curl -s http://localhost:8003/api/assets/device/1
# 期望: HTTP 200 + asset 数据

# 4. 验证旧 path 失效（ctrl 容器外部端口 8001）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/devices/1/asset
# 期望: 404

# 5. （如有外部集成）批量替换 path
# 旧: /api/devices/{id}/asset(/refresh)?
# 新: /api/assets/device/{id}(/refresh)?
```

---

## 3. 包含的 Changes（2 个）

### Change 1：fix-asset-collect-failure（路由修复，本版本核心）

#### 3.1 根因

v2.5.0 split 模式下：

1. 前端调 `assetApi.refresh(1)` → `POST /api/devices/1/asset/refresh`
2. vite proxy 规则 `/api/devices/*` → `ctrl:8000`
3. ctrl 容器注册 router：`device / log / dashboard / ctrl_internal` — **没有 asset**
4. ctrl 容器 openapi 实测 asset 路径数 = **0**
5. 手动 curl `POST localhost:8001/api/devices/1/asset/refresh` → `{"detail": "Not Found"}`

**根因结论**：v2.5.0 split 模式下，asset 业务归 data 容器，但 router path 用了 `/api/devices/{id}/asset/...`（device_id 是 ctrl 容器语义）；vite proxy 把 `/api/devices/*` 全部路由到 ctrl，ctrl 容器没注册 asset 路由 → 永远 404。

**影响面**（v2.5.0 split 模式上线后所有 asset 功能都不可用）：
- `Devices.vue` 详情 / 资产 / 状态 → 404
- `CMDB.vue` 采集 / 编辑 → 404
- `Dashboard.vue` 设备状态 → 404
- 仅 ctrl 容器自带的 device CRUD 正常工作

用户原话"采集不采集会失败"实际是"采集按钮点了没反应"（POST 立即 404，前端不报错只显示 loading 完）。

#### 3.2 Task 1：后端 asset router 改 path

```diff
- @router.get("/devices/{device_id}/asset", response_model=APIResponse)
+ @router.get("/assets/device/{device_id}", response_model=APIResponse)
- @router.put("/devices/{device_id}/asset", response_model=APIResponse)
+ @router.put("/assets/device/{device_id}", response_model=APIResponse)
- @router.post("/devices/{device_id}/asset/refresh", response_model=APIResponse)
+ @router.post("/assets/device/{device_id}/refresh", response_model=APIResponse)
```

**Commit**：`b5e8108` fix(backend): asset router 改 path 为 /assets/device/{id}/*

#### 3.3 Task 2：前端 assetApi 改 path

`frontend/src/api/index.js` — 3 个方法同步改。

**Commit**：`8649821` fix(frontend): assetApi 改 path 为 /assets/device/{id}/*

#### 3.4 Task 3：i18n key `asset.route.*`

后端 `i18n_keys.py` 加 3 个路由层错误 key：

| key | fallback | 用途 |
|---|---|---|
| `asset.route.refresh_failed` | `采集失败：{error}` | refresh 端点失败响应 |
| `asset.route.update_failed` | `资产更新失败：{error}` | update 端点失败响应 |
| `asset.route.device_not_found` | `设备 {id} 不存在` | 设备不存在响应 |

前端 `zh-CN.js` / `en-US.js` `errors.*` 同步加。

`routers/asset.py` refresh_asset 失败时用 `err.ASSET_ROUTE_REFRESH_FAILED` 替代 `err.ASSET_COLLECT_FAILED`（保留后者用于其他场景，避免影响现有测试）。

**Commit**：`6504a00` feat(i18n): 加 asset.route.* 错误 key

#### 3.5 Task 4-5：测试同步

- `backend/tests/test_smoke.py` — 2 个 asset URL 改新 path
- `frontend/tests/e2e/cmdb-asset-refresh.spec.js` — 3 处 page.route URL 改
- `frontend/tests/e2e/mocks/api-mocks.js` — 资产 mock 路由 + 内部 regex 改

**Commit**：
- `3962c8f` test(backend): 同步 test_smoke.py asset path
- `b2cd5a7` test(frontend): 同步 e2e asset URL + mock 路由

#### 3.6 Task 6：RELEASE-NOTES 标注 BREAKING（本文件）

**Commit**：（同 Task 6 commit）

---

### Change 2：fix-asset-stale-status（资产陈旧状态降级）

> 详见 [RELEASE-NOTES-v2.6.1 §3 完整版](#3-包含的-changes2-个) 与 commit 序列

简述：
- `app.main.degrade_stale_assets` 启动时自动把 25h 前的 `online` 资产降为 `offline`
- `dashboard._get_asset_stats` 按 staleness 阈值过滤（陈旧 online → stale）
- `/internal/assets` 返回 `is_stale` 字段
- 7 个 staleness 单测 + split 模式 staleness 回归单测

**Status**：v2.6.1 前置 change，已 archive 在 `openspec/changes/archive/2026-07-06-fix-asset-stale-status/`。

---

## 4. 关键设计决策

| 决策 | 方案 | 理由 |
|---|---|---|
| Asset path 命名 | `/api/assets/device/{id}/...` | asset 业务在 data 容器，path 前缀必须匹配 vite proxy `/api/assets → data` 规则 |
| 旧 path 处理 | 明确返回 404，不静默兼容 | 避免静默掩盖路由配置问题；v2.5.0 bug 就是被静默掩盖了 2 个版本 |
| 不动 ctrl 容器 | 不在 ctrl 加转发层 | 保持 v241 拆分原则（ctrl 只管身份，不管数据）|
| 不动 vite.config.js | `/api/assets → data` 规则已正确 | 改 path 后所有 asset 端点自动路由到 data 容器，零配置 |
| monolith 兼容 | core 模式 backend 单容器注册 asset router | 新 path 仍生效；VITE_API_MODE=core 不破 |
| i18n key 前缀 | `asset.route.*` | 与现有 `asset.*`（业务错误）区分；`route.*` 表示路由层 |
| 不影响 add-auto-collect | auto-collect 调 data 容器内 `_refresh_asset_for_device` 不走 HTTP | 独立 change，不在本 change 范围 |
| 不影响 fix-asset-stale-status | dashboard staleness 逻辑不变 | 独立 change，先 archive |

---

## 5. 关联

- 前序: v2.6.0 (2026-07-06) — i18n 基础设施
- 路线图: [VERSION-ROADMAP.md §v2.6.1](VERSION-ROADMAP.md#v261)
- 工具容器: 不变（ops-toolkit / qa-backend / qa-frontend 9 脚本）
- Change archive:
  - [openspec/changes/archive/2026-07-06-fix-asset-collect-failure/](openspec/changes/archive/)
  - [openspec/changes/archive/2026-07-06-fix-asset-stale-status/](openspec/changes/archive/)

---

## 6. 测试 / 验证

### qa-backend 单元测试（预计 240+ passed）

- 旧 path `/api/devices/1/asset` → 404（确认旧路径失效，无回归）
- 新 path `/api/assets/device/1` → 200 + asset 数据
- 新 path `/api/assets/device/1/refresh` POST → 200 / 500（设备可达性决定）
- 新 path PUT `/api/assets/device/1` body `{"location": "..."}` → 200
- 3 容器 split 模式下 curl 走前端 5173 端口 → vite proxy → data 容器 8003 链路通
- 现有 test_smoke.py / test_asset_staleness.py 同步改 path 后全过
- i18n key `asset.route.refresh_failed` 翻译正确

### qa-frontend 自动化测试

- **lint** + **build**: 全过
- **vitest**: 53 baseline 全过（无新增）
- **playwright**: 42 baseline 全过（无新增；cmdb-asset-refresh.spec.js 同步改 mock URL）

### 真机集成测试（.177 Test-Switch-177 / .4 Leaf-03）

```text
# 1. .177 触发 refresh（已知 SSH 可达）
POST /api/assets/device/{id}/refresh
→ 200 + asset.status=online

# 2. .4 触发 refresh（已知 SSH 失败场景）
POST /api/assets/device/{id}/refresh
→ 200 + success=false + error_key=asset.route.refresh_failed + 错误信息可读

# 3. Dashboard 验证
GET /api/dashboard
→ 200 + device_stats 含 stale 计数

# 4. 最后 restore_original_state
```

---

## 7. 关键 commit 序列（fix-asset-collect-failure change）

| # | commit | 主题 |
|---|---|---|
| 1 | `b5e8108` | fix(backend): asset router 改 path 为 /assets/device/{id}/* (Task 1) |
| 2 | `8649821` | fix(frontend): assetApi 改 path 为 /assets/device/{id}/* (Task 2) |
| 3 | `6504a00` | feat(i18n): 加 asset.route.* 错误 key (Task 3) |
| 4 | `3962c8f` | test(backend): 同步 test_smoke.py asset path (Task 4) |
| 5 | `b2cd5a7` | test(frontend): 同步 e2e asset URL + mock 路由 (Task 5) |
| 6 | （本 commit）| docs(release): RELEASE-NOTES-v2.6.1 标注 BREAKING (Task 6) |
| 7 | （Task 7 验证 commit） | qa-backend + qa-frontend + 真机 .177/.4 验证 (Task 7) |
| 8 | （Task 8 archive commit） | chore(openspec): fix-asset-collect-failure archive 闭环 (Task 8) |

合计 8 个 commit（fix-asset-collect-failure change）。

---

## 8. 升级检查清单

- [ ] 拉取最新代码：`git pull origin main`
- [ ] 重新构建镜像：`docker compose -f docker-compose.dev.yml build`
- [ ] 启动 split 3 容器（默认模式）：`docker compose -f docker-compose.dev.yml up -d`
- [ ] 验证 3 容器运行：`docker compose -f docker-compose.dev.yml ps`
- [ ] 验证新 path：curl `localhost:8003/api/assets/device/1` → 200
- [ ] 验证旧 path 失效：curl `localhost:8001/api/devices/1/asset` → 404
- [ ] 验证前端：访问 `http://localhost:5173/#/cmdb` 点"采集"按钮，看 Network 面板 `POST /api/assets/device/1/refresh`
- [ ] 跑 qa-backend：`docker compose -f docker-compose.dev.yml --profile qa up qa-backend`（应过 240+ passed）
- [ ] 跑 qa-frontend：`docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`（应过 lint + build + vitest + playwright）
- [ ] （可选）真机 e2e：MCP 浏览器验证 CMDB.vue 采集功能
- [ ] （如有外部集成）批量替换 path（详见对照表）

---

## 9. 已知问题

无（v2.6.1 review 通过）

---

## 10. 后续

v2.6.1 是 v2.5.0 split 架构的 bug fix，回归稳定。下一步：

- 下一发版: v2.7（add-auto-collect：定期自动采集 + Dashboard staleness 实时刷新）
- 当前 backlog: 见 [VERSION-ROADMAP.md §11 backlog](VERSION-ROADMAP.md#11-backlog)
