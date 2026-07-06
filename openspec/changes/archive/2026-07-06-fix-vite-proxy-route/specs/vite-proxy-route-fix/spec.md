# vite-proxy-route-fix — Spec

> v2.6.1 fix-vite-proxy-route

## 背景

v2.5.0 split 模式上线时 vite proxy 路由配置有 bug——只配置了**容器业务前缀**（`/api/devices`, `/api/interfaces`, `/api/assets` 等），没考虑 `/api/devices/{id}/...` 这种"在 device 子路径下但属于其他容器"的端点。

## 根因

vite http-proxy 库用 prefix 匹配（按 proxy 对象 key 顺序遍历）：

```js
// 现状（错配）
proxy: {
  '/api/devices': → ctrl,         // /api/devices/1/execute 也命中这条 → 路由到 ctrl → 404
  '/api/interfaces': → config,    // /api/devices/1/interfaces 不会命中（被 /api/devices 吃掉）
  ...
}
```

`/api/devices/1/execute` 命中 `/api/devices` prefix → 路由到 ctrl → ctrl 容器没这个端点 → 404。

## 修复

删除 prefix 规则，改用 `configure` 钩子 + 正则精确分发：

```js
configure: (proxyServer) => {
  proxyServer.on('request', (req, res) => {
    const url = req.url

    // 1. data 容器：备份 / 任务 / 资产 / 异步备份 / 异步回滚
    if (/^\/api\/(devices\/\d+\/(backup|backup-async|backup\/\d+\/(lock|restore|restore-async))|tasks|assets|backups)/.test(url)) {
      return proxyServer.web(req, res, { target: isSplit ? DATA : BACKEND, changeOrigin: true })
    }
    // 2. config 容器：执行 / 接口 / VLAN / VPN / batch
    if (/^\/api\/(devices\/\d+\/(execute|interfaces|vlans|vpn-instances|interfaces\/\d+\/(link-type|link-mode|ipv4-address|vpn-instance))|batch)/.test(url)) {
      return proxyServer.web(req, res, { target: isSplit ? CONFIG : BACKEND, changeOrigin: true })
    }
    // 3. ctrl 容器：CRUD + test + dashboard + logs（兜底）
    if (/^\/api\//.test(url)) {
      return proxyServer.web(req, res, { target: isSplit ? CTRL : BACKEND, changeOrigin: true })
    }
  })
}
```

## 设计决策

### 决策 1：删除 prefix 规则，改用 `configure` 钩子

- **理由**：vite http-proxy prefix 匹配无法处理"长前缀"和"短前缀"重叠问题
- **替代方案（已否决）**：保留 prefix 规则，依赖 http-proxy "长前缀优先"行为
  - **否决理由**：http-proxy 是先到先得，按 proxy 对象 key 顺序，需要每个长前缀都列在前面，且 http-proxy 不支持 path variable

### 决策 2：正则匹配放在 `configure` 钩子（不放在 `proxy` 对象的 path）

- **理由**：`configure(proxyServer, options)` 提供完整 proxy server 访问权限，可以拦截请求
- **实现**：用 `proxyServer.on('request', (req, res) => { ... })` 在请求到达前分发

### 决策 3：3 段式正则（data / config / ctrl 兜底）

- **理由**：清晰分层，新增端点易扩展
- **匹配顺序**：data → config → ctrl（精确优先）

### 决策 4：保留 `core` 模式走 BACKEND

- **理由**：core 模式（VITE_API_MODE=core）用 monolith 容器，所有路由都走 BACKEND
- **实现**：target 改用 `isSplit ? DATA : BACKEND` 三元运算

## 验证

### MCP 浏览器 8 个菜单 smoke test

1. 设备管理 /devices（CRUD）→ ctrl ✓
2. 运维终端 /ops（执行命令）→ config ✓
3. 接口配置 /interfaces → config ✓
4. VLAN /vlan → config ✓
5. VPN 实例 /vpn → config ✓
6. CMDB 资产 /cmdb → data ✓
7. 备份 / 回滚 /backup → data ✓
8. 批量操作 /batch → config ✓

### 单元测试

- qa-frontend vitest 已有 `vite.config.js` 加载测试（如果有）→ 通过
- qa-frontend lint + build → 通过
- qa-backend 全量 → 302+ passed 无回归

## 影响

- **代码**：`frontend/vite.config.js`（proxy 配置重写）
- **文档**：`RELEASE-NOTES-v2.6.1.md` §3 增补
- **baseline**：qa-backend 302+ passed 无变化（前端 bug）
