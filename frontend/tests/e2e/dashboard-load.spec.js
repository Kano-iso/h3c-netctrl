// v2.5 Task 6.6: 仪表盘加载 e2e
// 覆盖流程：访问 / → 拉取 dashboard + devices + assets → 渲染 KPI + 设备总览 + 最近操作 + 快速入口
import { test, expect } from '@playwright/test'
import { installApiMocks, DEVICES, DASHBOARD } from './mocks/api-mocks.js'

test.describe('Dashboard 仪表盘', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('加载仪表盘：渲染 KPI + 设备总览 + 最近操作 + 快速入口', async ({ page }) => {
    // 访问 / （hash 路由）
    await page.goto('/#/', { waitUntil: 'networkidle' })

    // 等关键文本出现
    await expect(page.getByText('网络运维总览', { exact: false })).toBeVisible()

    // KPI 卡片标签
    await expect(page.getByText('在管设备')).toBeVisible()
    await expect(page.getByText('在线设备')).toBeVisible()
    await expect(page.getByText('管理接口')).toBeVisible()
    await expect(page.getByText('今日操作')).toBeVisible()

    // KPI 数值：total=4 / online=3 / interfaces=— / ops=1
    const kpiNums = page.locator('.kpi-num')
    await expect(kpiNums).toHaveCount(4)
    await expect(kpiNums.nth(0)).toHaveText('4')
    await expect(kpiNums.nth(1)).toHaveText('3')
    await expect(kpiNums.nth(2)).toHaveText('—')
    await expect(kpiNums.nth(3)).toHaveText('1')

    // 设备总览：渲染 mock 中的设备名
    await expect(page.getByText('设备总览')).toBeVisible()
    for (const d of DEVICES) {
      await expect(page.getByText(d.name).first()).toBeVisible()
    }

    // 最近操作：渲染 mock 中的日志
    await expect(page.getByText('最近操作')).toBeVisible()
    await expect(page.getByText('backup_create')).toBeVisible()

    // 快速入口：4 个 RouterLink（用 .first() 避开 sidebar 同名链接）
    await expect(page.getByText('运维终端').first()).toBeVisible()
    await expect(page.getByText('接口管理').first()).toBeVisible()
    await expect(page.getByText('批量操作').first()).toBeVisible()
    await expect(page.getByText('CMDB').first()).toBeVisible()
  })

  test('刷新按钮：点击重新加载 dashboard + devices + assets', async ({ page }) => {
    await page.goto('/#/', { waitUntil: 'networkidle' })
    await expect(page.getByText('网络运维总览')).toBeVisible()

    // 等待初始加载完成
    await page.waitForTimeout(200)

    // 点击"刷新"按钮
    const refreshBtn = page.getByRole('button', { name: '刷新' })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()

    // 等待重新加载（KPI 数值仍可见）
    await expect(page.locator('.kpi-num').first()).toBeVisible()
  })

  test('失败态：dashboard API 返回 error，显示错误面板', async ({ page }) => {
    // 覆盖 dashboard mock 返回失败
    await page.route('**/api/dashboard', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: '后端不可达' }),
      })
    })

    await page.goto('/#/', { waitUntil: 'networkidle' })

    // 显示错误面板
    await expect(page.getByText('仪表盘加载失败')).toBeVisible()
    await expect(page.getByText('后端不可达')).toBeVisible()
    // 重试按钮
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
  })
})
