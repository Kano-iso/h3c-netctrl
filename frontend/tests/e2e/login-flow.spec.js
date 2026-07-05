// v2.5 Task 6.7: 登录流程 e2e（可选）
// 说明：当前项目无 auth 页面，登录流程不存在；改为"应用入口可达"基础验证
// 覆盖：访问 / → 渲染 layout → 侧边栏 / 内容区可见
import { test, expect } from '@playwright/test'
import { installApiMocks } from './mocks/api-mocks.js'

test.describe('应用入口（无 auth 模式）', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('应用可达：访问根路径正常渲染主框架', async ({ page }) => {
    await page.goto('/#/', { waitUntil: 'networkidle' })

    // 仪表盘主标题
    await expect(page.getByText('网络运维总览')).toBeVisible()
    // KPI 卡片
    await expect(page.getByText('在管设备')).toBeVisible()
  })

  test('路由切换：访问不同 hash 路径都正常渲染', async ({ page }) => {
    const routes = [
      { hash: '#/', checkText: '网络运维总览' },
      { hash: '#/devices', checkText: 'Test-Switch-1' },
      { hash: '#/interfaces', checkText: 'GigabitEthernet1/0/1' },
      { hash: '#/cmdb', checkText: 'S5560X-30C-EI' },
    ]

    for (const r of routes) {
      await page.goto(`/${r.hash}`, { waitUntil: 'networkidle' })
      await expect(page.getByText(r.checkText).first()).toBeVisible({ timeout: 5000 })
    }
  })
})
