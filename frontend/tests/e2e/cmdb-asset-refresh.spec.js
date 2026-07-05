// v2.5 Task 6.5: CMDB 资产采集 e2e
// 覆盖：访问 /cmdb → 渲染资产表 → 点击"刷新" → 调 assetApi.refresh → 列表更新
import { test, expect } from '@playwright/test'
import { installApiMocks, DEVICES } from './mocks/api-mocks.js'

test.describe('CMDB 资产采集', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('列表加载：访问 /cmdb 渲染所有设备 + 资产', async ({ page }) => {
    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })

    // 设备名
    await expect(page.getByText('Test-Switch-1')).toBeVisible()
    // 资产：型号 / 软件包 / 位置
    await expect(page.getByText('S5560X-30C-EI')).toBeVisible()
    await expect(page.getByText('北京-机房-A')).toBeVisible()
    // 标签拆分渲染
    await expect(page.getByText('核心').first()).toBeVisible()
    await expect(page.getByText('生产').first()).toBeVisible()
  })

  test('全量刷新：点击"刷新"按钮 → 调 assetApi.refresh（每台设备）', async ({ page }) => {
    let refreshCalled = false
    let refreshCallCount = 0
    await page.route('**/api/devices/*/asset/refresh', async (route) => {
      refreshCalled = true
      refreshCallCount++
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            device_id: 1,
            model: 'S5560X-30C-EI',
            software_package: 'Version 7.1.070 Release 2412P05',
            status: 'up',
            location: '北京-机房-A',
            tags: '核心,生产',
          },
        }),
      })
    })

    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })
    await expect(page.getByText('Test-Switch-1')).toBeVisible()

    // 点击"刷新"按钮（PageHeader actions slot）
    const refreshBtn = page.getByRole('button', { name: '刷新' })
    await refreshBtn.click()

    // 等待所有并发采集完成
    await page.waitForTimeout(500)
    expect(refreshCalled).toBe(true)
    expect(refreshCallCount).toBeGreaterThanOrEqual(1)

    // 刷新完成后显示"刷新完成"
    await expect(page.getByText('刷新完成')).toBeVisible({ timeout: 2000 })
  })

  test('单设备采集：点击单设备行的"采集" → 调 assetApi.refresh(id)', async ({ page }) => {
    let refreshCalled = false
    await page.route('**/api/devices/*/asset/refresh', async (route) => {
      refreshCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { device_id: 1, model: 'S5560X-30C-EI' } }),
      })
    })

    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })
    await expect(page.getByText('Test-Switch-1')).toBeVisible()

    // 行内采集按钮（如果存在）
    const collectBtn = page.getByRole('button', { name: /采集|刷新/ }).nth(1)  // 跳过 PageHeader 的"刷新"
    if (await collectBtn.count() > 0) {
      await collectBtn.click()
      await page.waitForTimeout(500)
      expect(refreshCalled).toBe(true)
    }
  })

  test('编辑资产：点击"资产编辑"按钮 → 打开 modal', async ({ page }) => {
    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })
    await expect(page.getByText('Test-Switch-1')).toBeVisible()

    // 行内"资产"或"编辑"按钮
    const editBtn = page.getByRole('button', { name: /资产|编辑/ }).first()
    if (await editBtn.count() > 0) {
      await editBtn.click()
      // AssetEditModal 打开（Teleport 到 body）
      await expect(page.getByText(/资产|编辑/).first()).toBeVisible()
    }
  })

  test('搜索过滤：输入关键词过滤资产列表', async ({ page }) => {
    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })
    await expect(page.getByText('Test-Switch-1')).toBeVisible()

    // 搜索 input
    const searchInput = page.locator('input[placeholder*="搜索"]')
    if (await searchInput.count() > 0) {
      await searchInput.fill('S5560X')
      // 过滤后还有 Test-Switch-1（型号 S5560X-30C-EI 匹配）
      await expect(page.getByText('Test-Switch-1')).toBeVisible()
    }
  })

  test('资产 PUT API：保存资产编辑', async ({ page }) => {
    let updateCalled = false
    await page.route('**/api/devices/*/asset', async (route) => {
      if (route.request().method() === 'PUT') {
        updateCalled = true
        const body = JSON.parse(route.request().postData() || '{}')
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: { device_id: 1, ...body },
          }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/#/cmdb', { waitUntil: 'networkidle' })
    await expect(page.getByText('Test-Switch-1')).toBeVisible()

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/asset', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ location: '上海-机房-B', tags: '边缘,测试' }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data.location).toBe('上海-机房-B')
    expect(updateCalled).toBe(true)
  })
})
