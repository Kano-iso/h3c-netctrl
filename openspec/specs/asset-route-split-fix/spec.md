# asset-route-split-fix Specification

## Purpose

修复 v2.5.0 split 模式下 asset 路由冲突：将 asset 路由从 `/api/devices/{id}/asset/*` 改为 `/api/assets/device/{id}/*`，匹配 vite proxy `/api/assets → data:8000` 规则，根治 split 模式下所有 asset 功能 404 问题。

## Requirements

### Requirement: 后端 asset 路由路径改写

`backend/app/routers/asset.py` MUST 将所有 `@router.*` 装饰器路径从 `/devices/{device_id}/asset[/...]` 改为 `/assets/device/{device_id}[/...]`，具体包括：

- `GET /assets/device/{device_id}` （旧：`/devices/{device_id}/asset`）
- `PUT /assets/device/{device_id}` （旧：`/devices/{device_id}/asset`）
- `POST /assets/device/{device_id}/refresh` （旧：`/devices/{device_id}/asset/refresh`）

`@router` 装饰器与函数签名除 path 外 MUST 不变；`device_id` 路径参数保持。

#### Scenario: 新 path 可达
- **WHEN** 客户端调 `GET /api/assets/device/1`
- **THEN** 后端 MUST 返回 200 + asset 数据（设备存在时）或 404 + 错误（设备不存在时）

#### Scenario: 旧 path 失效
- **WHEN** 客户端调 `GET /api/devices/1/asset`
- **THEN** 后端 MUST 返回 404 Not Found

#### Scenario: refresh 端点
- **WHEN** 客户端调 `POST /api/assets/device/1/refresh`
- **THEN** 后端 MUST 返回 200（采集成功）或 500（采集失败）+ i18n error_key

#### Scenario: update 端点
- **WHEN** 客户端调 `PUT /api/assets/device/1` body `{"location": "..."}`
- **THEN** 后端 MUST 返回 200 + 成功消息

### Requirement: 前端 assetApi 路径同步

`frontend/src/api/index.js` 的 `assetApi` MUST 同步改路径：

- `get(deviceId)` → `apiCall(\`/assets/device/${deviceId}\`)`
- `refresh(deviceId)` → `apiCall(\`/assets/device/${deviceId}/refresh\`, { method: 'POST' })`
- `update(deviceId, body)` → `apiCall(\`/assets/device/${deviceId}\`, { method: 'PUT', body: JSON.stringify(body) })`

#### Scenario: 浏览器可达
- **WHEN** 用户在 split 模式下点"采集"按钮
- **THEN** 浏览器网络面板 MUST 看到 `POST /api/assets/device/1/refresh`（不是 `/api/devices/1/asset/refresh`）

#### Scenario: 错误处理
- **WHEN** 后端返回 404 / 500
- **THEN** 前端 MUST 显示 i18n 错误信息（`asset.route.refresh_failed` 等），不显示裸技术异常

### Requirement: 3 容器 split 模式链路通

split 模式下，前端 → vite proxy → data 容器的链路 MUST 通：

- 前端容器（5173）vite proxy `/api/assets` → `data:8000`
- data 容器（8000）注册新 path `/api/assets/device/{id}/*`
- 客户端 3 跳链路 MUST 全通：浏览器 5173 → vite proxy → data 8000 → 返回 200

#### Scenario: split 模式链路
- **WHEN** 浏览器调 `/api/assets/device/1`
- **THEN** 服务端 MUST 返回 200（链路通，无 404 / 502 / 504）

#### Scenario: 旧链路 404
- **WHEN** 浏览器调 `/api/devices/1/asset`（旧 path）
- **THEN** 服务端 MUST 返回 404（明确表示旧 path 失效，无静默兼容）

### Requirement: monolith 模式兼容

`VITE_API_MODE=core` 模式下，backend 单容器注册 asset router，新 path MUST 仍生效：

- core 模式 backend 容器（8000）注册 `/api/assets/device/{id}/*`
- core 模式 vite proxy `/api/assets` → `backend:8000`
- 客户端走 core 模式 MUST 也能采

#### Scenario: core 模式链路
- **WHEN** 浏览器切到 core 模式（`VITE_API_MODE=core`）调 `/api/assets/device/1`
- **THEN** 服务端 MUST 返回 200

### Requirement: i18n 错误信息可读

后端 `backend/app/i18n_keys.py` MUST 加 `asset.route.*` 错误 key，至少包括：

- `asset.route.refresh_failed` fallback `"采集失败：{error}"`
- `asset.route.update_failed` fallback `"资产更新失败：{error}"`
- `asset.route.device_not_found` fallback `"设备 {id} 不存在"`

`backend/app/routers/asset.py` MUST 使用这些 i18n key 替代裸抛技术异常，response body MUST 包含 `error_key` + `error_params` + `fallback` 三个字段。

#### Scenario: refresh 失败错误信息
- **WHEN** 设备不可达，refresh 失败
- **THEN** 响应 MUST 包含 `error_key="asset.route.refresh_failed"` + `error_params={"error": "..."}` + `fallback="采集失败：..."`

#### Scenario: update 失败错误信息
- **WHEN** update 失败（参数非法 / 设备不存在）
- **THEN** 响应 MUST 包含 `error_key="asset.route.update_failed"` + `error_params={"error": "..."}`

### Requirement: 测试同步

所有引用旧 path 的测试 MUST 同步改：

- `backend/tests/test_smoke.py`（line 111: `client.post(f"/api/devices/{device_id}/asset/refresh")` → `client.post(f"/api/assets/device/{device_id}/refresh")`）
- `backend/tests/test_asset_staleness.py`（7 个测试中所有 URL）
- `frontend/src/__tests__/*.spec.js`（如有 mock URL）
- `frontend/tests/e2e/*.spec.js`（如有 URL 硬编码）

#### Scenario: qa-backend pytest 全过
- **WHEN** 跑 `docker compose -f docker-compose.dev.yml --profile qa up qa-backend`
- **THEN** 全部测试 MUST 通过（240+ passed）

#### Scenario: qa-frontend 全过
- **WHEN** 跑 `docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`
- **THEN** lint + build + vitest + playwright MUST 全通过

### Requirement: BREAKING 标注

`RELEASE-NOTES-v2.6.1.md` MUST 标注 **BREAKING**：asset API 路径变化，给出旧→新 path 对照表。

#### Scenario: BREAKING 标注
- **WHEN** 用户读 RELEASE-NOTES
- **THEN** MUST 看到 BREAKING 警告 + 旧/新 path 对照表 + 升级说明（如果有外部集成）

### Requirement: 不影响其他资产相关代码

本次 change MUST NOT 改动以下内容：

- `add-auto-collect` change（独立 change；auto-collect 调 data 容器内 `_refresh_asset_for_device` 不走 HTTP）
- `fix-asset-stale-status` change（已闭环，dashboard staleness 逻辑不变）
- `fix-link-mode-switch` / `fix-vpn-and-l2l3-ux-bugs` / `fix-vpn-edit-capabilities` 等已 archive 的 bug fix
- Asset 模型 / data_svc 内部实现

#### Scenario: 改动面隔离
- **WHEN** diff 跑 `git diff main openspec/changes/fix-asset-collect-failure`
- **THEN** MUST 只包含 asset router path 改 + 前端 api 改 + 测试改 + 文档改，不含其他业务逻辑
