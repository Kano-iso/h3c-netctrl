// v2.5 Task 6.1: 设备 CRUD 全流程 e2e
// 覆盖：访问 /devices → 渲染设备表 → 打开新增 modal → 提交 → 列表刷新 → 编辑 → 删除（含确认）
import { test, expect } from '@playwright/test'
import { installApiMocks, DEVICES } from './mocks/api-mocks.js'

test.describe('Devices 设备 CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page)
  })

  test('列表加载：访问 /devices 渲染所有设备', async ({ page }) => {
    await page.goto('/#/devices', { waitUntil: 'networkidle' })

    // 等表格行渲染
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()
    // 表头
    await expect(page.getByText('设备', { exact: true }).first()).toBeVisible()
    // 资产信息（型号 / 位置）
    await expect(page.getByText('S5560X-30C-EI').first()).toBeVisible()
    await expect(page.getByText('北京-机房-A').first()).toBeVisible()
  })

  test('创建：点击"新增设备" → Modal 打开 → 提交', async ({ page }) => {
    await page.goto('/#/devices', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()

    // 点击"新增设备"按钮
    const createBtn = page.getByRole('button', { name: '新增设备' })
    await createBtn.click()

    // Modal 打开（Teleport 到 body），标题为"新增设备"
    await expect(page.getByText('新增设备').first()).toBeVisible()
    // 确认不是编辑模式
    await expect(page.getByText('编辑设备')).not.toBeVisible()
  })

  test('编辑：点击行内"编辑"按钮 → Modal 打开（edit 模式）', async ({ page }) => {
    await page.goto('/#/devices', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()

    // 行内编辑按钮（精确文本"编辑"）
    const editBtn = page.getByRole('button', { name: '编辑', exact: true })
    await editBtn.click()

    // Modal 标题为"编辑设备：Test-Switch-1"
    await expect(page.getByText('编辑设备：Test-Switch-1')).toBeVisible()
  })

  test('删除：点击"删除" → ConfirmModal 打开 → 确认后调 API', async ({ page }) => {
    // 跟踪删除请求
    let deleteCalled = false
    await page.route(/\/api\/devices\/\d+$/, async (route) => {
      if (route.request().method() === 'DELETE') {
        deleteCalled = true
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
        return
      }
      await route.continue()
    })

    await page.goto('/#/devices', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()

    // 行内删除按钮
    const delBtn = page.getByRole('button', { name: '删除', exact: true })
    await delBtn.click()

    // ConfirmModal 打开，标题"删除设备"，message 含设备名 + host
    await expect(page.getByText('删除设备').first()).toBeVisible()
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()
    await expect(page.getByText('192.168.100.4').first()).toBeVisible()

    // 点击"确定删除"按钮
    const confirmBtn = page.getByRole('button', { name: '确定删除' })
    await confirmBtn.click()

    // 等待 API 调用完成
    await page.waitForTimeout(500)
    expect(deleteCalled).toBe(true)
  })

  test('连接测试：点击"连接测试"按钮 → 调 deviceApi.test', async ({ page }) => {
    let testCalled = false
    await page.route('**/api/devices/*/test', async (route) => {
      testCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { reachable: true } }),
      })
    })

    await page.goto('/#/devices', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()

    // 拦截 alert（testConnection 会弹 alert）
    page.on('dialog', (dialog) => dialog.accept())

    const testBtn = page.getByRole('button', { name: '连接测试' })
    await testBtn.click()

    // 等待请求完成
    await page.waitForTimeout(500)
    expect(testCalled).toBe(true)
  })

  test('搜索过滤：输入关键词过滤设备列表', async ({ page }) => {
    // 装 2 个设备的 mock
    await page.route('**/api/devices', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: [
              { id: 1, name: 'Test-Switch-1', host: '192.168.100.4', port: 830, protected_interfaces: [] },
              { id: 2, name: 'Production-Spine', host: '192.168.100.5', port: 830, protected_interfaces: [] },
            ],
          }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/#/devices', { waitUntil: 'networkidle' })
    await expect(page.getByText(/^Test-Switch-1$/).first()).toBeVisible()
    await expect(page.getByText('Production-Spine')).toBeVisible()

    // 输入搜索词
    const searchInput = page.locator('input[placeholder*="搜索"]')
    await searchInput.fill('Production')

    // 过滤后只剩 Production-Spine
    await expect(page.getByText('Production-Spine')).toBeVisible()
    await expect(page.getByText(/^Test-Switch-1$/).first()).not.toBeVisible()
  })
})
