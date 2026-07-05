// v2.5 Task 5.3 + Task 6: e2e 公共 mock 框架
// 用 Playwright route interception mock 所有 /api/* 请求，不依赖真实后端
// mock 数据结构与 Pydantic schema 对齐

const DEVICE_ID = 1

// 设备列表 mock
const DEVICES = [
  { id: 1, name: 'Test-Switch-1', host: '192.168.100.4', port: 830, username: 'admin', protected_interfaces: [] },
]

// 设备详情 mock
const DEVICE_DETAIL = (id) => DEVICES.find(d => d.id === id) || DEVICES[0]

// 资产 mock
const ASSET = (deviceId) => ({
  device_id: deviceId,
  model: 'S5560X-30C-EI',
  software_package: 'Version 7.1.070 Release 2412P05',
  status: 'up',
  location: '北京-机房-A',
  tags: '核心,生产',
})

// 接口列表 mock
const INTERFACES = [
  { if_index: 2, name: 'GigabitEthernet1/0/1', mode: 'access', access_vlan: 100, layer: 'L2', status: 'up' },
  { if_index: 3, name: 'GigabitEthernet1/0/2', mode: 'trunk', allowed_vlans: [100, 200], layer: 'L2', status: 'up' },
]

// VLAN 列表 mock
const VLANS = [
  { id: 1, name: 'VLAN 1' },
  { id: 100, name: '业务 A' },
]

// 备份列表 mock
const BACKUPS = [
  { id: 101, device_id: 1, type: 'startup', filename: 'startup_20240101_000000.cfg', size: 1234, created_at: '2024-01-01T00:00:00', locked: false },
  { id: 102, device_id: 1, type: 'running', filename: 'running_20240101_000000.cfg', size: 2345, created_at: '2024-01-01T00:00:01', locked: false },
]

// 仪表盘 mock（device_stats 字段对齐 Dashboard.vue：online / offline / total）
const DASHBOARD = {
  device_stats: { total: 4, online: 3, offline: 1 },
  recent_logs: [
    { id: 1, device_id: 1, action: 'backup_create', status: 'success', created_at: '2024-01-01T00:00:00', device_name: 'Test-Switch-1', detail: '创建备份' },
  ],
  recent_failures: [],
}

// 安装所有 mock 路由
async function installApiMocks(page, options = {}) {
  // 设备
  await page.route('**/api/devices', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DEVICES }) })
    } else if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { id: 2, ...JSON.parse(route.request().postData() || '{}') } }) })
    } else {
      await route.continue()
    }
  })

  // 单设备
  await page.route(/\/api\/devices\/\d+$/, async (route) => {
    const m = route.request().url().match(/\/api\/devices\/(\d+)/)
    const id = m ? parseInt(m[1]) : DEVICE_ID
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DEVICE_DETAIL(id) }) })
    } else if (method === 'PUT') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DEVICE_DETAIL(id) }) })
    } else if (method === 'DELETE') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
    } else {
      await route.continue()
    }
  })

  // 设备连接测试
  await page.route('**/api/devices/*/test', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { reachable: true } }) })
  })

  // 资产
  await page.route('**/api/devices/*/asset', async (route) => {
    const m = route.request().url().match(/\/api\/devices\/(\d+)\/asset/)
    const id = m ? parseInt(m[1]) : DEVICE_ID
    if (route.request().method() === 'PUT') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: ASSET(id) }) })
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: ASSET(id) }) })
    }
  })

  // 资产采集
  await page.route('**/api/devices/*/asset/refresh', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: ASSET(DEVICE_ID) }) })
  })

  // 接口列表
  await page.route('**/api/devices/*/interfaces', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: INTERFACES }) })
  })

  // VLAN
  await page.route('**/api/vlans*', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: VLANS }) })
    } else if (method === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { id: 200 } }) })
    } else if (method === 'DELETE') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
    } else {
      await route.continue()
    }
  })

  // 备份
  await page.route('**/api/devices/*/backup', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: BACKUPS }) })
    } else if (method === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { id: 103, ...BACKUPS[0] } }) })
    } else {
      await route.continue()
    }
  })

  // 备份操作（lock/restore）
  await page.route('**/api/devices/*/backup/*/lock', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) })
  })
  await page.route('**/api/devices/*/backup/*/restore', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { message: '回滚成功' } }) })
  })
  // 备份异步回滚（v2.4 task-monitor）
  await page.route('**/api/devices/*/backup/*/restore-async', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: { task_id: 'task-mock-001' } }) })
  })

  // 任务管理（v2.4 async task-monitor）
  await page.route('**/api/tasks/*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { task_id: 'task-mock-001', status: 'running', progress: 50, message: '处理中...' },
      }),
    })
  })

  // 仪表盘
  await page.route('**/api/dashboard', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DASHBOARD }) })
  })

  // 资产列表（dashboard 用）
  await page.route('**/api/assets', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DEVICES.map(d => ASSET(d.id)) }) })
  })

  // 日志
  await page.route('**/api/logs*', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data: DASHBOARD.recent_logs }) })
  })
}

export { installApiMocks, DEVICES, ASSET, INTERFACES, VLANS, BACKUPS, DASHBOARD }
