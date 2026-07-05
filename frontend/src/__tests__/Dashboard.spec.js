// Dashboard.vue 组件测试
// 覆盖 6 个 case：统计加载 / 最近操作 / 最近告警 / 数据可视化 / 路由跳转 / 刷新
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'

// 测试独立 i18n 实例
const testI18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

vi.mock('../api/index.js', () => ({
  dashboardApi: { get: vi.fn() },
  deviceApi: { list: vi.fn() },
  assetApi: { get: vi.fn() },
}))

import Dashboard from '../views/Dashboard.vue'
import { dashboardApi, deviceApi, assetApi } from '../api/index.js'

// RouterLink 桩：渲染为 <a>，点击时调用 $router.push(to)，便于断言跳转
const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a class="router-link-stub" @click.prevent="navigate"><slot /></a>',
  methods: {
    navigate() {
      if (this.$router && this.$router.push) this.$router.push(this.to)
    },
  },
}

const mockDashboardData = {
  success: true,
  data: {
    device_stats: { total: 5, online: 3, offline: 2 },
    recent_logs: [
      { id: 1, created_at: '2026-07-05 10:00:00', device_name: 'leaf-01', action: 'backup', detail: 'startup 配置备份', status: 'success' },
      { id: 2, created_at: '2026-07-05 11:30:00', device_name: 'spine-01', action: 'execute', detail: 'display version', status: 'failed' },
    ],
    recent_failures: [
      { id: 2, created_at: '2026-07-05 11:30:00', device_name: 'spine-01', action: 'execute', detail: 'display version', status: 'failed' },
    ],
  },
}

const mockDevicesList = {
  success: true,
  data: [
    { id: 1, name: 'leaf-01', host: '10.0.0.1', protected_interfaces: [] },
    { id: 2, name: 'spine-01', host: '10.0.0.2', protected_interfaces: [] },
  ],
}

const mockAsset = {
  success: true,
  data: {
    model: 'S5560X',
    software_package: 'R2607',
    ports: 48,
    location: '机房A · 机柜1',
    status: 'online',
    tags: 'core, leaf',
  },
}

function setupMocks() {
  dashboardApi.get.mockResolvedValue(mockDashboardData)
  deviceApi.list.mockResolvedValue(mockDevicesList)
  assetApi.get.mockResolvedValue(mockAsset)
}

function mountDashboard(routerPush = vi.fn()) {
  return mount(Dashboard, {
    global: {
      plugins: [testI18n],
      stubs: { RouterLink: RouterLinkStub },
      mocks: {
        $router: { push: routerPush },
        $route: { path: '/', name: 'dashboard' },
      },
    },
  })
}

describe('Dashboard.vue 组件测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  it('统计加载：mount 后调 dashboardApi.get，渲染统计卡片', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    // onMounted 触发一次拉取
    expect(dashboardApi.get).toHaveBeenCalledTimes(1)

    const text = wrapper.text()
    // 4 个 KPI 卡片标签
    expect(text).toContain('在管设备')
    expect(text).toContain('在线设备')
    expect(text).toContain('管理接口')
    expect(text).toContain('今日操作')

    // KPI 数值：total=5 / online=3 / interfaces=— / ops=2(recent_logs.length)
    const kpiNums = wrapper.findAll('.kpi-num')
    expect(kpiNums.length).toBe(4)
    expect(kpiNums[0].text()).toBe('5')
    expect(kpiNums[1].text()).toBe('3')
    expect(kpiNums[2].text()).toBe('—')
    expect(kpiNums[3].text()).toBe('2')

    // PageHeader subtitle 拼装
    expect(text).toContain('5 台设备')
    expect(text).toContain('3 在线')
  })

  it('最近操作：渲染最近操作列表', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    const text = wrapper.text()
    // 第一条：成功
    expect(text).toContain('leaf-01')
    expect(text).toContain('backup')
    expect(text).toContain('startup 配置备份')
    expect(text).toContain('成功')
    // 第二条：失败
    expect(text).toContain('spine-01')
    expect(text).toContain('execute')
    expect(text).toContain('display version')
    expect(text).toContain('失败')
    // 时间字段（substring(11,19)）
    expect(text).toContain('10:00:00')
    expect(text).toContain('11:30:00')
  })

  it('最近告警：渲染失败计数与失败标记', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    const text = wrapper.text()
    // 今日操作卡 sub = `${recent_failures.length} 失败` → "1 失败"
    expect(text).toContain('1 失败')
    // 离线计数（device_stats.offline）
    expect(text).toContain('2 离线')
    // 失败操作在最近操作列表中以"失败"chip 呈现
    const chips = wrapper.findAll('.chip-bad')
    expect(chips.length).toBeGreaterThanOrEqual(1)
  })

  it('图表渲染：组件无独立图表，渲染设备总览可视化卡片', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    const text = wrapper.text()
    // 设备总览区块标题
    expect(text).toContain('设备总览')
    // 设备卡片：name / host / model / tags
    expect(text).toContain('leaf-01')
    expect(text).toContain('spine-01')
    expect(text).toContain('10.0.0.1')
    expect(text).toContain('10.0.0.2')
    expect(text).toContain('S5560X')
    // tags 拆分（'core, leaf' → ['core','leaf']）
    expect(text).toContain('core')
    expect(text).toContain('leaf')
    // 在线状态 chip
    expect(text).toContain('在线')
  })

  it('跳转：点击快速入口 RouterLink 触发路由跳转', async () => {
    const push = vi.fn()
    const wrapper = mountDashboard(push)
    await flushPromises()

    // 找到"运维终端"链接（快速入口第一个）
    const links = wrapper.findAll('a.router-link-stub')
    const opsLink = links.find((a) => a.text().includes('运维终端'))
    expect(opsLink).toBeTruthy()

    await opsLink.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'ops' })

    // 顺带验证"接口管理"指向 interfaces
    const ifLink = links.find((a) => a.text().includes('接口管理'))
    expect(ifLink).toBeTruthy()
    await ifLink.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'interfaces' })
  })

  it('刷新：点击刷新按钮，重新调 dashboardApi.get', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    // mount 时已调用 1 次，清空计数以便隔离验证刷新行为
    dashboardApi.get.mockClear()

    // 找到刷新按钮（PageHeader actions slot 内）
    const buttons = wrapper.findAll('button')
    const refreshBtn = buttons.find((b) => b.text().includes('刷新'))
    expect(refreshBtn).toBeTruthy()

    await refreshBtn.trigger('click')
    await flushPromises()

    // 刷新触发一次新的 dashboardApi.get
    expect(dashboardApi.get).toHaveBeenCalled()
    // deviceApi.list 也会被 loadDevicesOverview 再次调用（至少 1 次）
    expect(deviceApi.list).toHaveBeenCalled()
  })

  // v2.6 i18n: 切换 en-US 后 Dashboard 标题/KPI 标签变英文
  it('i18n: 切换 en-US 后 Dashboard 显示英文（Network Operations Overview / Managed Devices / Refresh）', async () => {
    const enI18n = createI18n({
      legacy: false,
      locale: 'en-US',
      fallbackLocale: 'zh-CN',
      messages: { 'zh-CN': zhCN, 'en-US': enUS },
    })
    const enWrapper = mount(Dashboard, {
      global: {
        plugins: [enI18n],
        stubs: { RouterLink: RouterLinkStub },
        mocks: {
          $router: { push: vi.fn() },
          $route: { path: '/', name: 'dashboard' },
        },
      },
    })
    await flushPromises()
    const text = enWrapper.text()
    expect(text).toContain('Network Operations Overview')
    expect(text).toContain('Managed Devices')
    expect(text).toContain('Refresh')
  })
})
