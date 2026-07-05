// v2.5: Playwright 配置 + webServer 自动起 vite
import { defineConfig, devices } from '@playwright/test'

// 调试：确认环境变量在容器内被读
const _chromiumPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
console.log(`[playwright.config] PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=${_chromiumPath}`)

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
      use: {
        ...devices['Desktop Chrome'],
        // qa 容器内 Playwright 没自带 chromium，用系统 chromium（apk add chromium）
        // v2.5 fix: Playwright 1.49+ 默认用 chrome-headless-shell，executablePath 优先级不够
        // 改用 channel: 'chromium' + executablePath 双保险
        channel: 'chromium',
        launchOptions: {
          executablePath: _chromiumPath || undefined,
        },
      },
    },
  ],
})
