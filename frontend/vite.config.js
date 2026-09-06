import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import http from 'node:http'

// v2.5: 双模式 proxy，由 VITE_API_MODE 控制（split | core，默认 split）
// - split（默认，3 容器）：按路径精确分发到 ctrl / config / data
// - core（monolith，--profile core）：全部转发到 backend:8000
const API_MODE = process.env.VITE_API_MODE || 'split'
const isSplit = API_MODE === 'split'

// split 模式按服务分发的 target
const CTRL = 'http://ctrl:8000'
const CONFIG = 'http://config:8000'
const DATA = 'http://data:8000'
const BACKEND = 'http://backend:8000'

// v2.6.1 fix-vite-proxy-route: 用路径正则精确分发，避免 prefix 匹配导致
// /api/devices/{id}/execute 等端点被错误路由到 ctrl 容器。
// 优先级：data 容器（备份/任务/资产）→ config 容器（执行/接口/VLAN/VPN/batch）→ ctrl 兜底（CRUD/test/dashboard/logs）
const DATA_PATTERN = /^\/api\/(?:devices\/\d+\/backup(?:-async)?(?:\/\d+\/(?:lock|restore|restore-async))?|tasks(?:\/.*)?|assets(?:\/.*)?|backups(?:-async)?(?:\/.*)?)\/?$/
const CONFIG_PATTERN = /^\/api\/(?:devices\/\d+\/(?:execute|interfaces|vlans|vpn-instances|interfaces\/\d+\/(?:link-type|link-mode|ipv4-address|vpn-instance))|batch(?:\/.*)?|interfaces(?:\/.*)?|vlans(?:\/.*)?|execute(?:\/.*)?|sdn(?:\/.*)?)\/?$/

// v2.6.1 fix-backup-data-integrity Task 1: 纯 GET 下载 URL（/api/devices/{id}/backup/{id} 无后缀）
// 上面 DATA_PATTERN 只覆盖了 lock/restore/restore-async 后缀，纯下载 URL 走兜底 → ctrl → 404
// 单独加 DOWNLOAD_PATTERN 优先匹配，路由到 data 容器
const DOWNLOAD_PATTERN = /^\/api\/devices\/\d+\/backup\/\d+\/?$/

function pickTarget(url) {
  if (DOWNLOAD_PATTERN.test(url)) {
    return isSplit ? DATA : BACKEND
  }
  if (DATA_PATTERN.test(url)) {
    return isSplit ? DATA : BACKEND
  }
  if (CONFIG_PATTERN.test(url)) {
    return isSplit ? CONFIG : BACKEND
  }
  return isSplit ? CTRL : BACKEND
}

// 简易 HTTP forward（避免引入 http-proxy 依赖）
function forward(req, res, target) {
  const url = new URL(req.url, target)
  const opts = {
    hostname: url.hostname,
    port: url.port || 80,
    path: url.pathname + url.search,
    method: req.method,
    headers: { ...req.headers, host: url.host },
  }
  const proxyReq = http.request(opts, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers)
    proxyRes.pipe(res)
  })
  proxyReq.on('error', (err) => {
    console.error(`[vite-proxy] forward error: ${err.message} (${req.method} ${req.url} → ${target})`)
    if (!res.headersSent) {
      res.statusCode = 502
      res.setHeader('Content-Type', 'application/json')
    }
    res.end(JSON.stringify({ success: false, error: `proxy error: ${err.message}` }))
  })
  req.pipe(proxyReq)
}

// API 路由 plugin（拦截 /api/* 请求到对应容器）
function apiRouterPlugin() {
  return {
    name: 'h3c-api-router',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url || !req.url.startsWith('/api/')) {
          return next()
        }
        const target = pickTarget(req.url)
        forward(req, res, target)
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), apiRouterPlugin()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/__tests__/**/*.spec.js'],
  },
})
