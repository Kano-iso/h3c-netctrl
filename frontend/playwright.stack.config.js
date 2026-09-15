// S1-027 真实应用栈联调 Playwright 配置。
// 与默认 playwright.config.js 分离：本配置不自动起 vite（由 run_stack_qa.sh 管理），
// 只跑 tests/stack-qa 下的真实栈 spec，绝不影响默认 e2e（tests/e2e，mock 基线）。
import { defineConfig, devices } from '@playwright/test'

const _chromiumPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

export default defineConfig({
  testDir: './tests/stack-qa',
  timeout: 60 * 1000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.STACK_QA_BASE_URL || 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // 无 webServer：vite 与后端都由 run_stack_qa.sh 拉起并等待就绪
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chromium',
        launchOptions: {
          executablePath: _chromiumPath || undefined,
        },
      },
    },
  ],
})
