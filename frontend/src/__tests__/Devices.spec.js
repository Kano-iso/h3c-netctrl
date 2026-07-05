// v2.5 设备视图组件测试 —— 6 个 case 覆盖列表加载 / 创建 / 编辑 / 删除 / 连接测试 / 搜索过滤
//
// Mock 策略：
// - vi.mock('../api/index.js', ...) 整体替换 api 模块，所有 apiCall 不发真实请求
// - 每个用例按需 mockResolvedValue / mockImplementation 构造 fixture 数据
// - beforeEach 清 mock 调用记录 + 重置默认空返回；afterEach unmount + 清理 Teleport 残留
// - 用 vue-router createMemoryHistory 构造 mock router，避免 $router.push 警告
// - 用 vi.stubGlobal('alert', ...) 拦截 testConnection 里的 alert 弹窗
// - 用 @vue/test-utils mount（非 shallow）真实渲染子组件；Modal 走 Teleport 到 body，用 document.body 断言
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'

vi.mock('../api/index.js', () => ({
  deviceApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
  },
  assetApi: {
    get: vi.fn(),
    update: vi.fn(),
    refresh: vi.fn(),
  },
  executeApi: { run: vi.fn() },
  batchApi: { execute: vi.fn() },
}))

import Devices from '../views/Devices.vue'
import { deviceApi, assetApi } from '../api/index.js'

// 测试独立 i18n 实例（避免污染全局 + 解决 'Need to install with app.use' 错）
const testI18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

// 测试用设备 fixtures
const DEVICES = [
  { id: 1, name: 'Spine-01', host: '192.168.1.1', port: 830, protected_interfaces: [1, 5] },
  { id: 2, name: 'Leaf-01', host: '192.168.1.2', port: 830, protected_interfaces: [] },
  { id: 3, name: 'Leaf-02', host: '192.168.1.3', port: 830, protected_interfaces: [] },
]

const ASSETS = {
  1: { model: 'S5560', software_package: 'R2607', status: 'online', location: '机房A', tags: '核心' },
  2: { model: 'S5130', software_package: 'R3115', status: 'offline', location: '机房B', tags: '' },
  3: { model: 'S5120', software_package: 'R3110', status: 'maintenance', location: '机房C', tags: '' },
}

// 构造 memory-history router，避免模板里 $router.push 警告
function mockRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div/>' } },
      { path: '/batch', name: 'batch', component: { template: '<div/>' } },
    ],
  })
}

const mountOpts = () => {
  const router = mockRouter()
  return {
    global: {
      plugins: [testI18n, router],
      stubs: {
        PageHeader: { template: '<div><slot /><slot name="actions" /></div>' },
      },
    },
  }
}

describe('Devices 组件', () => {
  let wrapper
  let alertSpy

  beforeEach(async () => {
    vi.clearAllMocks()
    // 默认 mock 返回空列表 / 空资产，避免未设置的用例误触 fetch
    deviceApi.list.mockResolvedValue({ success: true, data: [] })
    assetApi.get.mockResolvedValue({ success: true, data: {} })
    // testConnection / 删除失败路径会调 alert，stub 掉避免 happy-dom 抛错
    alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
  })

  afterEach(() => {
    if (wrapper) wrapper.unmount()
    vi.unstubAllGlobals()
    // 清理 Teleport 到 body 的 Modal 残留
    document.body.innerHTML = ''
  })

  it('case 1: 列表加载 —— mount 后调 deviceApi.list + assetApi.get，渲染设备表格', async () => {
    deviceApi.list.mockResolvedValue({ success: true, data: DEVICES })
    assetApi.get.mockImplementation((id) =>
      Promise.resolve({ success: true, data: ASSETS[id] || {} })
    )

    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 调用了 deviceApi.list 一次
    expect(deviceApi.list).toHaveBeenCalledTimes(1)
    // 对每个设备调 assetApi.get
    expect(assetApi.get).toHaveBeenCalledWith(1)
    expect(assetApi.get).toHaveBeenCalledWith(2)
    expect(assetApi.get).toHaveBeenCalledWith(3)
    // 表格渲染所有设备名
    expect(wrapper.text()).toContain('Spine-01')
    expect(wrapper.text()).toContain('Leaf-01')
    expect(wrapper.text()).toContain('Leaf-02')
    // 资产信息（型号 / 位置）被渲染
    expect(wrapper.text()).toContain('S5560')
    expect(wrapper.text()).toContain('机房A')
  })

  it('case 2: 创建 —— 点击"新增设备"按钮，DeviceFormModal 打开（create 模式）', async () => {
    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 初始无 Modal
    expect(document.body.textContent).not.toContain('新增设备')

    // 点击 PageHeader actions slot 里的"新增设备"按钮
    const btn = wrapper.findAll('button').find((b) => b.text().includes('新增设备'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    await flushPromises()

    // DeviceFormModal 打开（Teleport 到 body），标题为"新增设备"
    expect(document.body.textContent).toContain('新增设备')
    // 不应进入编辑模式
    expect(document.body.textContent).not.toContain('编辑设备')
  })

  it('case 3: 编辑 —— 点击设备的编辑按钮，DeviceFormModal 打开（edit 模式）', async () => {
    deviceApi.list.mockResolvedValue({ success: true, data: [DEVICES[0]] })
    assetApi.get.mockResolvedValue({ success: true, data: ASSETS[1] })

    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 找到行内"编辑"按钮（按钮文本精确为"编辑"）
    const editBtn = wrapper.findAll('button').find((b) => b.text().trim() === '编辑')
    expect(editBtn).toBeTruthy()
    await editBtn.trigger('click')
    await flushPromises()

    // DeviceFormModal 打开，标题为"编辑设备：Spine-01"
    expect(document.body.textContent).toContain('编辑设备：Spine-01')
  })

  it('case 4: 删除 —— 点击删除按钮，ConfirmModal 打开（含设备名 + host）', async () => {
    deviceApi.list.mockResolvedValue({ success: true, data: [DEVICES[0]] })
    assetApi.get.mockResolvedValue({ success: true, data: ASSETS[1] })

    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 找到行内"删除"按钮
    const delBtn = wrapper.findAll('button').find((b) => b.text().trim() === '删除')
    expect(delBtn).toBeTruthy()
    await delBtn.trigger('click')
    await flushPromises()

    // ConfirmModal 打开（Teleport 到 body），标题为"删除设备"
    expect(document.body.textContent).toContain('删除设备')
    // message 包含设备名 + host（ConfirmModal 用 whitespace-pre-line 渲染）
    expect(document.body.textContent).toContain('Spine-01')
    expect(document.body.textContent).toContain('192.168.1.1')
    // 此时还没确认，deviceApi.delete 不应被调
    expect(deviceApi.delete).not.toHaveBeenCalled()
  })

  it('case 5: 连接测试 —— 点击测试按钮，调 deviceApi.test，状态变化', async () => {
    deviceApi.list.mockResolvedValue({ success: true, data: [DEVICES[0]] })
    assetApi.get.mockResolvedValue({ success: true, data: ASSETS[1] })
    deviceApi.test.mockResolvedValue({ success: true, data: { ok: true } })

    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 找到"连接测试"按钮
    const testBtn = wrapper.findAll('button').find((b) => b.text().includes('连接测试'))
    expect(testBtn).toBeTruthy()

    // 点击触发 testConnection
    await testBtn.trigger('click')
    await flushPromises()

    // deviceApi.test 被调用，参数为设备 id（具体文案因实现而异，不强断言）
    expect(deviceApi.test).toHaveBeenCalledWith(1)
  })

  it('case 6: 搜索过滤 —— 输入搜索词，filtered 列表变化', async () => {
    deviceApi.list.mockResolvedValue({ success: true, data: DEVICES })
    assetApi.get.mockImplementation((id) =>
      Promise.resolve({ success: true, data: ASSETS[id] || {} })
    )

    wrapper = mount(Devices, mountOpts())
    await flushPromises()

    // 初始 3 个设备都渲染
    expect(wrapper.text()).toContain('Spine-01')
    expect(wrapper.text()).toContain('Leaf-01')
    expect(wrapper.text()).toContain('Leaf-02')

    // 输入搜索词 "leaf"（匹配 name，filtered 计算属性会重新计算）
    const searchInput = wrapper.find('input[placeholder*="搜索"]')
    expect(searchInput.exists()).toBe(true)
    await searchInput.setValue('leaf')
    await flushPromises()

    // 过滤后只剩 Leaf-01 / Leaf-02（Spine-01 不含 "leaf"）
    expect(wrapper.text()).not.toContain('Spine-01')
    expect(wrapper.text()).toContain('Leaf-01')
    expect(wrapper.text()).toContain('Leaf-02')

    // 再精确到 "leaf-01"
    await searchInput.setValue('leaf-01')
    await flushPromises()
    expect(wrapper.text()).not.toContain('Leaf-02')
    expect(wrapper.text()).toContain('Leaf-01')
  })
})
