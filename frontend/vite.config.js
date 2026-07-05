import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// v2.5: 双模式 proxy，由 VITE_API_MODE 控制（split | core，默认 split）
// - split（默认，3 容器）：按路径分发到 ctrl / config / data
// - core（monolith，--profile core）：全部转发到 backend:8000
const API_MODE = process.env.VITE_API_MODE || 'split'
const isSplit = API_MODE === 'split'

// split 模式按服务分发的 target
const CTRL = 'http://ctrl:8000'
const CONFIG = 'http://config:8000'
const DATA = 'http://data:8000'
const BACKEND = 'http://backend:8000'

// core 模式全部走 backend，split 模式按服务分发
const targetFor = (svc) => isSplit ? svc : BACKEND

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // ctrl 容器：设备身份 / 日志 / 仪表盘
      '/api/devices': { target: targetFor(CTRL), changeOrigin: true },
      '/api/logs': { target: targetFor(CTRL), changeOrigin: true },
      '/api/dashboard': { target: targetFor(CTRL), changeOrigin: true },
      // config 容器：接口 / VLAN / 执行 / 批量
      '/api/interfaces': { target: targetFor(CONFIG), changeOrigin: true },
      '/api/vlans': { target: targetFor(CONFIG), changeOrigin: true },
      '/api/execute': { target: targetFor(CONFIG), changeOrigin: true },
      '/api/batch': { target: targetFor(CONFIG), changeOrigin: true },
      // data 容器：资产 / 备份 / 任务
      '/api/assets': { target: targetFor(DATA), changeOrigin: true },
      '/api/backups': { target: targetFor(DATA), changeOrigin: true },
      '/api/tasks': { target: targetFor(DATA), changeOrigin: true },
      // 兜底：其他 /api 请求走 backend（core 模式）或 ctrl（split 模式，ctrl 兜底）
      '/api': { target: targetFor(BACKEND), changeOrigin: true },
    },
  },
})
