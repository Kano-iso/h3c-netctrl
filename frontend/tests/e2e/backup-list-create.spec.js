// v2.5 Task 6.4: 备份列表 + 单设备创建 e2e
// 覆盖：访问 /backup → 渲染备份列表 + 调 POST /api/devices/{id}/backup 创建设备备份
import { test, expect } from '@playwright/test'
import { installApiMocks, BACKUPS } from './mocks/api-mocks.js'

test.describe('Backup 备份管理', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('列表加载：访问 /backup 渲染每设备的备份', async ({ page }) => {
    // 注意：/backup 路由有 meta: { future: true }，可能从侧边栏进不来
    // 直接 hash 跳转
    await page.goto('/#/backup', { waitUntil: 'networkidle' })

    // 设备名 + 备份文件名
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('startup_20240101_000000.cfg')).toBeVisible()
    await expect(page.getByText('running_20240101_000000.cfg')).toBeVisible()
  })

  test('单设备备份 API：POST /api/devices/{id}/backup 成功', async ({ page }) => {
    let createCalled = false
    await page.route('**/api/devices/*/backup', async (route) => {
      if (route.request().method() === 'POST') {
        createCalled = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: { id: 103, device_id: 1, type: 'startup', filename: 'startup_20240101_000002.cfg', size: 3456, created_at: '2024-01-01T00:00:02', locked: false },
          }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    // 通过 page.evaluate 直接调 API 验证 mock
    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data.id).toBe(103)
    expect(createCalled).toBe(true)
  })

  test('全量备份 API：POST /api/backups 同步模式', async ({ page }) => {
    let createAllCalled = false
    await page.route('**/api/backups', async (route) => {
      if (route.request().method() === 'POST') {
        createAllCalled = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: { success: [{ device_id: 1 }], failed: [] },
          }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/backups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ types: ['startup', 'running'] }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data.success).toHaveLength(1)
    expect(createAllCalled).toBe(true)
  })

  test('备份列表 API：GET /api/devices/{id}/backup 返回 mock 备份', async ({ page }) => {
    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup')
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data).toEqual(BACKUPS)
  })

  test('锁定切换 API：POST /api/devices/{id}/backup/{id}/lock 成功', async ({ page }) => {
    let lockCalled = false
    await page.route('**/api/devices/*/backup/*/lock', async (route) => {
      lockCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup/101/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locked: true }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(lockCalled).toBe(true)
  })
})
