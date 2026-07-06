# fix-vite-proxy-route — Proposal

## Why

v2.5.0 split 模式上线时 vite proxy 路由配置有 bug——只配置了**容器业务前缀**（`/api/devices`, `/api/interfaces`, `/api/assets` 等），没考虑 `/api/devices/{id}/...` 这种"在 device 子路径下但属于其他容器"的端点。

**结果**：vite http-proxy 用 prefix match 匹配，浏览器发 `/api/devices/1/execute` → 命中 `/api/devices` 规则 → 路由到 **ctrl 容器** → 404（ctrl 没 execute 路由）。

### 受影响端点清单（v2.5.0 split 模式起就坏了）

| 端点 | vite proxy 路由到 | 实际在 | 状态 |
|---|---|---|---|
| `POST /api/devices/{id}/execute` | ctrl | config | ❌ 404 |
| `GET /api/devices/{id}/interfaces` | ctrl | config | ❌ 404 |
| `POST /api/devices/{id}/interfaces/config` | ctrl | config | ❌ 404 |
| `PATCH /api/devices/{id}/interfaces/{idx}/link-type` | ctrl | config | ❌ 404 |
| `PATCH /api/devices/{id}/interfaces/{idx}/link-mode` | ctrl | config | ❌ 404 |
| `POST/DELETE /api/devices/{id}/interfaces/{idx}/ipv4-address` | ctrl | config | ❌ 404 |
| `GET/POST /api/devices/{id}/vpn-instances` | ctrl | config | ❌ 404 |
| `DELETE /api/devices/{id}/vpn-instances/{name}` | ctrl | config | ❌ 404 |
| `POST/DELETE /api/devices/{id}/interfaces/{idx}/vpn-instance` | ctrl | config | ❌ 404 |
| `GET/POST/PUT/DELETE /api/devices/{id}/vlans[/{id}]` | ctrl | config | ❌ 404 |
| `POST /api/devices/{id}/backup` | ctrl | data | ❌ 404 |
| `GET/DELETE /api/devices/{id}/backup[/{id}]` | ctrl | data | ❌ 404 |
| `POST /api/devices/{id}/backup/{id}/lock` | ctrl | data | ❌ 404 |
| `POST /api/devices/{id}/backup/{id}/restore` | ctrl | data | ❌ 404 |
| `POST /api/devices/{id}/backup-async` | ctrl | data | ❌ 404 |
| `POST /api/devices/{id}/backup/{id}/restore-async` | ctrl | data | ❌ 404 |

### 不受影响的端点

- `GET/POST /api/devices` (CRUD) → ctrl ✓
- `GET/PUT/DELETE /api/devices/{id}` (CRUD) → ctrl ✓
- `POST /api/devices/{id}/test` (连接测试) → ctrl ✓
- `GET /api/dashboard` → ctrl ✓
- `GET /api/logs` → ctrl ✓
- `POST /api/batch/execute` → config ✓
- `GET /api/vlans` (deprecated) → config ✓
- `GET /api/assets/device/{id}` → data ✓
- `GET /api/backups` / `/api/tasks/*` → data ✓

### 用户视角影响

前端 ops 页面（运维终端）执行命令显示"命令执行失败"；接口配置 / VLAN / VPN 实例 / 备份 / 异步备份 / 回滚 等 16+ 端点 404；**只 CRUD + test + dashboard + logs 能用**——这就是用户说"前端很灾难性"。

### 后端 / 单元测试为什么没发现

- 后端 curl 直连各容器（8001/8002/8003）都正常
- qa-backend 单元测试不经过 vite proxy
- 集成测试默认 skip
- MCP 浏览器只走过 Dashboard / Devices / CMDB 三个页面（CRUD 还能用），没走过 ops / interfaces / backup 等坏掉的页面

### 修复

vite proxy 把"长前缀"放前面（http-proxy 库 prefix match 按 proxy 对象 key 顺序先到先得）。新配置：
- data 容器长前缀（备份 / 任务）放最前
- config 容器长前缀（执行 / 接口 / VLAN / VPN）放中间
- ctrl 容器（CRUD / test / dashboard / logs）兜底

## What Changes

- **`frontend/vite.config.js` 改 proxy 配置**：长前缀优先 + data 容器 backup 路径分发
- **新增 1 个 qa-frontend 测试**（可选）：验证 vite proxy 配置加载正确
- **无后端改动**
- **无前端业务改动**
- **MCP 浏览器逐菜单回归验证**

## 设计决策

### 决策 1：长前缀优先（http-proxy 库先到先得）

- **理由**：vite http-proxy 库用 prefix 匹配，按 proxy 对象 key 顺序遍历
- **实现**：在 proxy 对象中**先列长前缀规则**（如 `/api/devices/{id}/backup`），再列短前缀兜底（如 `/api/devices`）
- **路径**：`/api/devices/1/backup` → 先匹配 `/api/devices/{id}/backup` 失败（key 不存在，但 http-proxy 实际是 prefix 匹配 `/api/devices/1/backup` 不会命中 `/api/devices/{id}/backup`）→ 兜底 `/api/devices` → ctrl 错
- **修正思路**：用 `/api/devices/${id}/backup` 不行（http-proxy 不支持变量），改用 `/api/devices/1/backup` 之类不行（id 是动态的）
- **真正可行方案**：删除 `/api/devices` 通用规则，改用更具体的子路径规则；或保留 `/api/devices` 但路径匹配改为"/api/devices(?!/\\d+/(execute|interfaces|vlans|vpn-instances|backup))"正则

### 决策 2：用 `bypass` + 多个具体规则

- **方案**：删除 `/api/devices` 通用规则，改成：
  - `/api/devices` → ctrl（匹配 CRUD）
  - `/api/devices/{id}/test` → ctrl（但 http-proxy 不支持变量，需要保留 `/api/devices` 让所有 `/api/devices/*` 都先到 ctrl，再用 `router` 重写分发？）
- **不优雅**：vite proxy 不支持 path rewrite + 二级路由分发

### 决策 3：用 vite proxy `bypass` + 自定义 rewrite

- **方案**：保留 `/api/devices` 通用规则路由到 ctrl，但在 ctrl 容器内**实现** execute/interfaces/vlans/vpn-instances/backup 这些端点的**内部转发**（通过 internal_api 调 config/data 容器）
- **代价**：ctrl 容器需要集成所有路由（退化为 monolith 模式）
- **拒绝理由**：违反 split 模式设计原则

### 决策 4（采用）：删除 `/api/devices` 通用规则，用 path-rewrite + 多规则

- **方案**：vite proxy 删除 `/api/devices` 通用规则，改成 4 类：
  - 长前缀优先：`/api/devices/{id}/backup` 不行（id 变量）
  - 改用**穷举**所有 `/api/devices/{id}/*` 子路径，按业务分发：
    - `/api/devices/{id}/test` → ctrl
    - `/api/devices/{id}/execute` → config
    - `/api/devices/{id}/interfaces` → config
    - `/api/devices/{id}/vlans` → config
    - `/api/devices/{id}/vpn-instances` → config
    - `/api/devices/{id}/backup` → data
    - `/api/devices/{id}/backup-async` → data
  - **关键**：vite http-proxy 不支持 path variable，必须用 prefix 匹配：
    - `/api/devices/1/backup` 会匹配 `/api/devices/${id}/backup` 吗？**不会**（http-proxy 是字符串 prefix 匹配，不是模板）
  - **真正可行**：用 vite http-proxy `bypass` + 自定义 router 拦截

### 决策 5（最终采用）：用 vite `configure` 钩子 + 自定义 router

- **方案**：删掉所有 prefix 规则，改用 `configure: (proxy, options) => { proxy.on('proxyReq', ...) }` 钩子，根据 path 正则匹配精确分发
- **实现**：
  ```js
  configure: (proxyServer) => {
    proxyServer.on('request', (req, res) => {
      const url = req.url
      // 备份 / 任务 / 资产 → data
      if (/^\/api\/(devices\/\d+\/backup|tasks|assets)/.test(url)) return proxy.web(req, res, { target: DATA })
      // 执行 / 接口 / VLAN / VPN / batch → config
      if (/^\/api\/(devices\/\d+\/(execute|interfaces|vlans|vpn-instances)|batch)/.test(url)) return proxy.web(req, res, { target: CONFIG })
      // 其他 /api/* → ctrl (含 /api/devices CRUD + test + dashboard + logs)
      if (/^\/api\//.test(url)) return proxy.web(req, res, { target: CTRL })
    })
  }
  ```
- **优点**：精确路由，无歧义
- **代价**：配置复杂一点，但能彻底解决 prefix 匹配问题

## Capabilities

### Modified Capabilities

- 无（修复 bug，不改 spec 语义）

## Impact

- **代码**：`frontend/vite.config.js`（proxy 配置重写，约 30 行）
- **无后端 / 无业务改动**
- **API**：无破坏性变更（行为修复）
- **配置**：无
- **文档**：`RELEASE-NOTES-v2.6.1.md` §3 增补 vite proxy 路由修复
- **测试**：
  - qa-frontend：lint + build 通过
  - qa-backend：302+ passed 无回归
  - MCP 浏览器：8 个菜单全验证（设备 / 命令 / 接口 / VLAN / VPN / 备份 / CMDB / Batch / 拓扑）

## Non-Goals

- 不改后端容器职责划分（ctrl / config / data 边界保持）
- 不改前端业务代码（只改 vite proxy）
- 不改 monolith 模式行为（core 模式走 BACKEND，无此 bug）
- 不重构成 monolithic 模式
- 不重构成 monorepo 路由方案（保持 split 模式）

## QA 验证计划

### 1. 受影响端点真机验证（MCP 浏览器）

| # | 端点 | 验证方法 | 期望 |
|---|---|---|---|
| 1 | `POST /api/devices/1/execute` | ops 页面点"执行" | 200 + H3C 输出 |
| 2 | `GET /api/devices/1/interfaces` | interface 页面 | 200 + 接口列表 |
| 3 | `GET /api/devices/1/vlans` | VLAN 页面 | 200 + VLAN 列表 |
| 4 | `GET /api/devices/1/vpn-instances` | VPN 页面 | 200 + VPN 列表 |
| 5 | `POST /api/devices/1/backup` | backup 页面 | 200 + 备份记录 |
| 6 | `GET /api/backups` | backup 页面 | 200 + 备份列表 |
| 7 | `POST /api/devices/1/backup-async` | backup 异步 | 200 + task_id |
| 8 | `POST /api/batch/execute` | batch 页面 | 200 + 执行结果 |

### 2. 不受影响端点（防回归）

- `GET/POST /api/devices` → 200
- `POST /api/devices/1/test` → 200
- `GET /api/dashboard` → 200
- `GET /api/logs` → 200
- `GET /api/assets/device/1` → 200

### 3. qa 回归

- [ ] qa-frontend lint + build 通过
- [ ] qa-backend 302+ passed 无回归
- [ ] MCP 浏览器 8 个菜单全部 smoke test
