# fix-asset-collect-failure — Proposal

## Why

v2.6.0 i18n 发版后用户报告"采集不采集会失败"。v2.6.1 `fix-asset-stale-status` Apply 后排查发现**真因是 v2.5.0 split 模式的路由设计错误**，不是 SSH 采集本身。

### 根因现场

1. **前端调** `assetApi.refresh(1)` → `POST /api/devices/1/asset/refresh`（[api/index.js:131-132](file:///root/workpace/h3c-netctrl/frontend/src/api/index.js#L131-L132)）
2. **vite proxy 规则** `/api/devices/*` → `ctrl:8000`（[vite.config.js:30](file:///root/workpace/h3c-netctrl/frontend/vite.config.js#L30)）
3. **ctrl 容器注册 router**：`device / log / dashboard / ctrl_internal` — **没有 asset**（[ctrl/main.py:50-54](file:///root/workpace/h3c-netctrl/backend/ctrl/main.py#L50-L54)）
4. **ctrl 容器 openapi** 实测 `asset` 路径数 = **0**（curl `localhost:8001/openapi.json` 过滤）
5. **手动 curl** `POST localhost:8001/api/devices/1/asset/refresh` → `{"detail": "Not Found"}`

**根因结论**：v2.5.0 split 模式下，asset 业务归 data 容器，但 router path 用了 `/api/devices/{id}/asset/...`（device_id 是 ctrl 容器语义）；vite proxy 把 `/api/devices/*` 全部路由到 ctrl，ctrl 容器没注册 asset 路由 → 永远 404。

**影响面**（v2.5.0 split 模式上线后所有 asset 功能都不可用）：
- `Devices.vue` 详情 / 资产 / 状态 → 404
- `CMDB.vue` 采集 / 编辑 → 404
- `Dashboard.vue` 设备状态 → 404
- 仅 ctrl 容器自带的 device CRUD 正常工作

用户原话"采集不采集会失败"实际是"采集按钮点了没反应"（POST 立即 404，前端不报错只显示 loading 完）。

## What Changes

- **后端 asset 路由路径独立**：从 `/api/devices/{id}/asset/*` 改为 `/api/assets/device/{id}/*`
  - 匹配 vite proxy `/api/assets → data` 规则
  - data 容器内 asset router path 改写
  - 路由函数签名不变（device_id 仍为路径参数）
- **前端 api/index.js 同步改路径**：`assetApi.get/refresh/update` 全部改为 `/assets/device/{id}/...`
- **monolith 模式兼容**：core 模式（`VITE_API_MODE=core`）下 backend 单容器注册 asset router，新 path 仍生效
- **i18n key 加 `asset.route.*`**：错误信息可读
- **回归**：Devices.vue / CMDB.vue / Dashboard.vue 全部功能恢复
- **spec 修订**：归到 `add-ops-toolkit` / `device-crud-ui` 等现有 capability，**新建独立 capability** `asset-route-split-fix` 记录此次 bug 修复

## 设计决策

### 决策 1：路径命名 `/api/assets/device/{id}/...`

- 改前：`/api/devices/{id}/asset`（asset 业务在前缀 devices 下）
- 改后：`/api/assets/device/{id}`（asset 业务在前缀 assets 下）
- 理由：asset 业务在 data 容器，path 前缀必须匹配 vite proxy `/api/assets → data` 规则
- 不动 `device_id` 路径参数 — API 签名保持兼容性

### 决策 2：不动 ctrl 容器注册 asset router

- 理由：保持 v241 拆分原则（ctrl 只管身份，不管数据）
- 不在 ctrl 容器加转发层（避免 ctrl 容器有"代理职责"）
- 3 容器架构清晰：data 拥有 asset 全业务

### 决策 3：不动 vite.config.js

- 现有 `/api/assets → data:8000` 规则已经正确
- 改 path 后所有 asset 端点自动路由到 data 容器，零配置

### 决策 4：monolith 模式不破

- `core` 模式（`VITE_API_MODE=core`）下 backend 单容器注册 asset router，新 path 仍生效
- 现有 test_smoke.py / test_asset_staleness.py 等测试需同步改 path

### 决策 5：错误信息可读

- 路径改后，前端 API 错误能精确到"assetApi 调用失败"而非笼统"网络失败"
- i18n key `asset.route.not_found` / `asset.route.refresh_failed` 等加进 i18n_keys.py

## Capabilities

### New Capabilities

- `asset-route-split-fix`: asset 路由在 3 容器 split 模式下从 `/api/devices/{id}/asset/*` 改为 `/api/assets/device/{id}/*`，匹配 vite proxy 规则，根治 split 模式下 asset 功能 404 问题

## Impact

- **代码**：
  - `backend/app/routers/asset.py`（path 改：`/devices/{device_id}/asset` → `/assets/device/{device_id}`）
  - `frontend/src/api/index.js`（`assetApi.get/refresh/update` path 同步改）
  - `backend/app/i18n_keys.py`（加 `asset.route.*` 错误 key）
  - `backend/tests/test_asset_staleness.py`（path 同步）
  - `backend/tests/test_smoke.py`（path 同步）
  - `frontend/src/views/Devices.vue` / `CMDB.vue` / `Dashboard.vue`（如直接调路径，搜索替换）
  - `frontend/src/__tests__/*.spec.js`（如有 mock URL 同步改）
  - `frontend/tests/e2e/*.spec.js`（如有 URL 同步改）
- **API**：
  - **BREAKING**：`/api/devices/{id}/asset` → `/api/assets/device/{id}`（变更前 404 → 变更后 200）
  - **BREAKING**：`/api/devices/{id}/asset/refresh` → `/api/assets/device/{id}/refresh`
  - **BREAKING**：`/api/devices/{id}/asset` PUT → `/api/assets/device/{id}`
- **配置**：无
- **文档**：
  - `RELEASE-NOTES-v2.6.1.md` 标注 BREAKING：asset API 路径变化
  - `VERSION-ROADMAP.md` §v2.6.1 + §1 全景表更新（修复 split 路由冲突）
  - `docs/ops-toolkit.md` / `docs/QA-GUIDE.md`（如引用旧路径需同步）
- **测试 baseline**：238 → 240+ passed（path 同步后 + 2 新 i18n key 测试）
- **用户体验**：
  - 修复前：split 模式所有 asset 功能 404
  - 修复后：split / core 模式都正常工作

## Non-Goals

- 不动 v2.4.1 拆分原则（ctrl / config / data 3 容器职责不变）
- 不动 vite.config.js（规则已正确）
- 不动 add-auto-collect（独立 change；auto-collect 调 data 容器内 `_refresh_asset_for_device` 不受影响）
- 不动 backend / frontend 业务逻辑（只改 path）
- 不动 fix-asset-stale-status（独立 change；本 change 仅路由修复）

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | `/api/assets/device/{id}` GET | `backend/app/routers/asset.py` |
| 后端 API | `/api/assets/device/{id}` PUT | 同上 |
| 后端 API | `/api/assets/device/{id}/refresh` POST | 同上 |
| 前端 API 客户端 | `assetApi` | `frontend/src/api/index.js` |
| 前端 UI | `Devices.vue` / `CMDB.vue` / `Dashboard.vue` | - |
| 真实设备 | 192.168.100.177 (Test-Switch-177) | - |
| 真实设备 | 192.168.100.4/.5 (Leaf-03/04) | - |

### 2. QA 验证项

#### 2.1 后端单元 / 集成（qa-backend 容器跑）

- [ ] 旧 path `/api/devices/1/asset` 返回 404（确认旧路径失效，无回归）
- [ ] 新 path `/api/assets/device/1` 返回 200 + asset 数据
- [ ] 新 path `/api/assets/device/1/refresh` POST 返回 200 / 500（设备可达性决定）
- [ ] 新 path PUT `/api/assets/device/1` body `{"location": "..."}` 返回 200
- [ ] 3 容器模式下 curl 走前端 5173 端口 → vite proxy → data 容器 8003 链路通
- [ ] 现有 test_smoke.py / test_asset_staleness.py 同步改 path 后全过
- [ ] i18n key `asset.route.refresh_failed` 翻译正确

#### 2.2 前端 UI 验证

- [ ] `npm run build` 编译过
- [ ] `qa-frontend` 容器 lint + build + vitest 全过
- [ ] `qa-frontend` 容器 playwright e2e 关键流程（CMDB.vue 采集 / Devices.vue 详情 / Dashboard.vue 状态）通过
- [ ] MCP 浏览器手动验证：split 模式下 Devices.vue 点"资产"按钮显示 asset 数据（不再 404）

#### 2.3 真机集成（pytest --integration 跑 .177/.4/.5）

- [ ] .177 触发 refresh（POST `/api/assets/device/{id}/refresh`）→ 验证 asset.status=online
- [ ] .4 触发 refresh（已知 SSH 失败）→ 验证 asset.status=offline + 错误信息可读
- [ ] **最后必须 restore_original_state**

#### 2.4 回归

- [ ] 不破坏 v2.6.0 i18n 任何功能
- [ ] 不破坏 v2.6.1 fix-asset-stale-status（dashboard 数字仍按 staleness 过滤）
- [ ] 不破坏 add-auto-collect（auto-collect 调 data 容器内函数，不受影响）
- [ ] qa-backend 240+ tests 全 PASS
- [ ] qa-frontend lint + build 全过
