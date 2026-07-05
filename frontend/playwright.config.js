// v2.5: Playwright 配置 + webServer 自动起 vite
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  // 8 e2e 场景超时 30s（mock 路由快）
  timeout: 30 * 1000,
  // 全局失败前重试 1 次
  retries: 0,
  // 串行跑（避免 dev server 端口/资源竞争）
  workers: 1,
  // 失败时保留 trace
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // 自动起 vite dev server，等待 5173 端口就绪
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
