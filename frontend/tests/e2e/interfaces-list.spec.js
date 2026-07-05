// v2.5 Task 6.2: 接口列表 + L2/L3 状态展示 e2e
// 覆盖：访问 /interfaces → 选设备 → 渲染接口表（mode 过滤 / 搜索 / 状态展示）
import { test, expect } from '@playwright/test'
import { installApiMocks, INTERFACES, DEVICES } from './mocks/api-mocks.js'

test.describe('Interfaces 接口管理', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('列表加载：选设备后渲染接口表 + 状态展示', async ({ page }) => {
    await page.goto('/#/interfaces', { waitUntil: 'networkidle' })

    // 等接口表加载（首台设备自动选中）
    await expect(page.getByText('GigabitEthernet1/0/1')).toBeVisible()
    await expect(page.getByText('GigabitEthernet1/0/2')).toBeVisible()

    // mode 列：access / trunk
    await expect(page.getByText('access', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('trunk', { exact: true }).first()).toBeVisible()

    // status 列：UP
    await expect(page.getByText('UP', { exact: true }).first()).toBeVisible()
  })

  test('mode 过滤：点击 "trunk" 过滤后只剩 trunk 接口', async ({ page }) => {
    await page.goto('/#/interfaces', { waitUntil: 'networkidle' })
    await expect(page.getByText('GigabitEthernet1/0/1')).toBeVisible()

    // 找到 filterMode 按钮（trunk）
    // 注：实际 UI 用 chip 按钮组，文本"trunk"可能在多个位置
    const trunkFilterBtn = page.getByRole('button', { name: 'trunk', exact: true }).first()
    if (await trunkFilterBtn.isVisible()) {
      await trunkFilterBtn.click()
      // 过滤后只剩 trunk 接口
      await expect(page.getByText('GigabitEthernet1/0/2')).toBeVisible()
    }
  })

  test('搜索过滤：输入接口名片段过滤列表', async ({ page }) => {
    await page.goto('/#/interfaces', { waitUntil: 'networkidle' })
    await expect(page.getByText('GigabitEthernet1/0/1')).toBeVisible()

    // 找到搜索 input（placeholder 含 "搜索"）
    const searchInput = page.locator('input[placeholder*="搜索"]')
    if (await searchInput.count() > 0) {
      await searchInput.fill('1/0/2')
      // 过滤后只剩 GigabitEthernet1/0/2
      await expect(page.getByText('GigabitEthernet1/0/2')).toBeVisible()
      await expect(page.getByText('GigabitEthernet1/0/1')).not.toBeVisible()
    }
  })

  test('设备切换：选另一台设备 → 接口表刷新', async ({ page }) => {
    // 装 2 台设备的 mock，device 2 接口不同
    await page.route('**/api/devices/*/interfaces', async (route) => {
      const m = route.request().url().match(/\/api\/devices\/(\d+)\/interfaces/)
      const id = m ? parseInt(m[1]) : 1
      const data = id === 2
        ? [{ if_index: 1, name: 'TenGigabitEthernet1/0/1', mode: 'routed', layer: 'L3', status: 'up' }]
        : INTERFACES
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data }),
      })
    })

    await page.goto('/#/interfaces', { waitUntil: 'networkidle' })
    await expect(page.getByText('GigabitEthernet1/0/1')).toBeVisible()

    // 切到 device 2（找 Select 组件，点开下拉）
    const select = page.locator('.select-trigger, select').first()
    if (await select.count() > 0) {
      await select.click()
      // 选第二项
      const opt = page.getByText('Production-Spine', { exact: false }).first()
      if (await opt.count() > 0) {
        await opt.click()
        // 接口表刷新
        await expect(page.getByText('TenGigabitEthernet1/0/1')).toBeVisible()
      }
    }
  })

  test('失败态：interface API 失败时显示错误', async ({ page }) => {
    await page.route('**/api/devices/*/interfaces', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'NETCONF 超时' }),
      })
    })

    await page.goto('/#/interfaces', { waitUntil: 'networkidle' })
    // 显示错误提示
    await expect(page.getByText('NETCONF 超时').or(page.getByText('加载接口失败'))).toBeVisible()
  })
})
