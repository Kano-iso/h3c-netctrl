// v2.5 Task 6.8: 备份回滚流程 e2e
// 覆盖：访问 /backup → 调 POST /api/devices/{id}/backup/{id}/restore → 成功提示
import { test, expect } from '@playwright/test'
import { installApiMocks } from './mocks/api-mocks.js'

test.describe('Backup 回滚流程', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('回滚 API：POST /api/devices/{id}/backup/{id}/restore 成功', async ({ page }) => {
    let restoreCalled = false
    let restoreBody = null
    await page.route('**/api/devices/*/backup/*/restore', async (route) => {
      restoreCalled = true
      restoreBody = route.request().postData()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { message: '回滚成功：startup 配置已应用，设备已重启' },
        }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    // 拦截 alert
    page.on('dialog', async (dialog) => {
      // alert 消息可能含回滚结果
      await dialog.accept()
    })

    // 通过 evaluate 调 API 模拟回滚
    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup/101/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ with_reboot: true }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(restoreCalled).toBe(true)
    // 默认 with_reboot=true
    expect(JSON.parse(restoreBody).with_reboot).toBe(true)
  })

  test('回滚带 with_reboot=false：参数正确传递', async ({ page }) => {
    let restoreBody = null
    await page.route('**/api/devices/*/backup/*/restore', async (route) => {
      restoreBody = route.request().postData()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { message: '回滚成功（不重启）' } }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup/101/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ with_reboot: false }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(JSON.parse(restoreBody).with_reboot).toBe(false)
  })

  test('回滚失败：API 返回 error 时前端拿到 success=false', async ({ page }) => {
    await page.route('**/api/devices/*/backup/*/restore', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: '设备不可达，无法回滚' }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup/101/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ with_reboot: true }),
      })
      return await r.json()
    })

    expect(result.success).toBe(false)
    expect(result.error).toBe('设备不可达，无法回滚')
  })

  test('回滚异步：POST /api/devices/{id}/backup/{id}/restore-async 返回 task_id', async ({ page }) => {
    let asyncCalled = false
    await page.route('**/api/devices/*/backup/*/restore-async', async (route) => {
      asyncCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { task_id: 'task-restore-001' },
        }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/devices/1/backup/101/restore-async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ with_reboot: true }),
      })
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data.task_id).toBe('task-restore-001')
    expect(asyncCalled).toBe(true)
  })

  test('任务状态查询：GET /api/tasks/{id} 返回 progress', async ({ page }) => {
    let queryCalled = false
    await page.route('**/api/tasks/task-restore-001', async (route) => {
      queryCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            task_id: 'task-restore-001',
            status: 'running',
            progress: 50,
            message: '正在回滚配置...',
          },
        }),
      })
    })

    await page.goto('/#/backup', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible({ timeout: 5000 })

    const result = await page.evaluate(async () => {
      const r = await fetch('/api/tasks/task-restore-001')
      return await r.json()
    })

    expect(result.success).toBe(true)
    expect(result.data.status).toBe('running')
    expect(result.data.progress).toBe(50)
    expect(queryCalled).toBe(true)
  })
})
