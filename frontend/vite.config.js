import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Vite dev server 代理 /api 到后端容器
    // monolith 模式：所有 /api → backend:8000
    // 3 容器模式（VITE_SPLIT_MODE=true）：按路径分发到 ctrl/config/data
    proxy: {
      '/api/devices': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://ctrl:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/logs': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://ctrl:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/dashboard': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://ctrl:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/interfaces': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://config:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/vlans': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://config:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/execute': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://config:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/batch': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://config:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/assets': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://data:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/backups': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://data:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      '/api/tasks': {
        target: process.env.VITE_SPLIT_MODE === 'true' ? 'http://data:8000' : 'http://backend:8000',
        changeOrigin: true,
      },
      // 兜底：其他 /api 请求走 backend（monolith 模式）
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
