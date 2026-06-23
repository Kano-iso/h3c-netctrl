## Capability: backend-integration

新 frontend（基于 PoC 视觉系统的 Vite + Vue 3 + Tailwind 工程）必须完成与 V2.0 后端 7 个 API 的真实对接，删除所有 mock 数据。

## Goal

PoC 阶段所有数据走 `frontend-poc/src/mock.js`，仅做视觉验证。V2.1 阶段必须：

- 7 个核心 view 全部改用真实后端 API
- 错误处理可读、可追溯（中文错误提示 + 原因 + 建议）
- Loading / Empty / Error 三态齐备
- 与现有后端 API 契约保持一致（不破坏后端）

## Scope

### In Scope

- 新增 `frontend/src/api/index.js` —— fetch 封装 + 7 个 API 客户端模块
- 删除 `frontend/src/mock.js`（PoC 临时数据）
- 7 个 view 改为真实 API 调用：
  - `Dashboard.vue` → `dashboardApi`
  - `Devices.vue` → `deviceApi`
  - `OpsTerminal.vue` → `executeApi`
  - `Interfaces.vue` → `interfaceApi`
  - `Batch.vue` → `batchApi`
  - `CMDB.vue` → `assetApi`
  - `Logs.vue` → `logApi`
- 统一 Loading / Empty / Error 三态组件
- 网络异常中文友好提示
- API 基础路径 `/api`（与 V2.0 后端一致）

### Out of Scope

- 不修改后端 API
- 不修改后端数据库
- 不引入 axios（用原生 fetch，避免新增依赖）
- 不做请求重试 / 离线缓存 / 鉴权拦截
- 不做接口 Mock 服务（开发期用真后端 `make dev` 验证）

## API 契约（V2.0 后端已实现）

| View | HTTP | 路径 | 后端模块 |
|------|------|------|----------|
| Dashboard | GET | /api/dashboard | `views/dashboard.py` |
| Devices | GET / POST | /api/devices | `views/devices.py` |
| Devices | GET / PUT / DELETE | /api/devices/:id | `views/devices.py` |
| Devices | POST | /api/devices/:id/test | `views/devices.py` |
| OpsTerminal | POST | /api/devices/:id/execute | `views/execute.py` |
| Interfaces | GET | /api/devices/:id/interfaces | `views/interfaces.py` |
| Interfaces | GET / POST | /api/devices/:id/interfaces/config | `views/interfaces.py` |
| Batch | POST | /api/batch/execute | `views/batch.py` |
| CMDB | GET / POST | /api/devices/:id/asset | `views/cmdb.py` |
| CMDB | POST | /api/devices/:id/asset/refresh | `views/cmdb.py` |
| Logs | GET | /api/logs | `views/logs.py` |

**统一响应格式**：
```json
{ "success": true, "data": {...} }
{ "success": false, "error": "可读的中文错误信息" }
```

## Data Model 映射

前端 view 直接消费后端返回的 `data` 字段，不做冗余转换（保持数据流显式）。字段名差异（如 `id` vs `device_id`）在 view 内局部处理，避免引入中间层。

## API 客户端设计

```js
// frontend/src/api/index.js
const API_BASE = '/api'

export async function apiCall(path, options = {}) {
  // 统一处理：headers、错误捕获、JSON 解析
}

// 按域拆分 7 个客户端
export const dashboardApi  = { get: () => apiCall('/dashboard') }
export const deviceApi     = { list, get, create, update, delete, test }
export const executeApi    = { run: (id, cmd) => apiCall(`/devices/${id}/execute`, { method: 'POST', body: JSON.stringify(cmd) }) }
export const interfaceApi  = { list, getConfig, applyConfig }
export const batchApi      = { execute: (payload) => apiCall('/batch/execute', { method: 'POST', body: JSON.stringify(payload) }) }
export const assetApi      = { get, refresh, update }
export const logApi        = { list: (params) => apiCall('/logs?' + new URLSearchParams(params)) }
```

## 错误处理规范

- 网络层失败：`{ success: false, error: '网络请求失败，请检查后端服务是否运行' }`
- 业务层失败：直接透传后端 `error` 字段（中文描述）
- UI 层：在 view 顶部展示错误条 + 重试按钮（仅 GET 类接口）
- 绝不静默 catch，绝不弹技术异常到用户

## 三态规范

每个 view 必须实现：

- **Loading**：骨架屏或 spinner，禁用交互
- **Empty**：空状态插画 + 引导文案（如「暂无设备，点击新增」）
- **Error**：错误条 + 原因 + 重试按钮

## Acceptance Criteria

- [ ] 7 个 view 全部对接真实后端 API，无任何 mock.js 引用
- [ ] `frontend/src/api/index.js` 包含 7 个 API 客户端模块
- [ ] 所有 GET 类接口支持 Loading / Empty / Error 三态
- [ ] 网络异常显示「网络请求失败，请检查后端服务是否运行」
- [ ] 后端业务错误直接透传中文 error 字段
- [ ] `make dev` 启动后，7 个 view 都能正确拉取/发送数据
- [ ] 浏览器 Network 面板看到真实 `/api/*` 请求，无 mock 数据
- [ ] 旧 `frontend.bak` 不被引用，新 `frontend/` 完全独立
