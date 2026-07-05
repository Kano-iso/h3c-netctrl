// CMDB.vue 组件测试
// 覆盖：列表加载 / 单设备采集 / 编辑资产 / 状态筛选 / 位置更新 / 标签管理
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// ---- mock api 模块（CMDB.vue 依赖 deviceApi.list / assetApi.get|refresh|update / backupApi）----
vi.mock('../api/index.js', () => ({
  assetApi: {
    get: vi.fn(),
    update: vi.fn(),
    refresh: vi.fn(),
  },
  deviceApi: { list: vi.fn(), get: vi.fn() },
  backupApi: { createAll: vi.fn() },
  taskApi: { backupAsync: vi.fn() },
}))

// ---- mock task store（CMDB.vue setup 顶部即调用 useTaskStore()，必须 stub）----
vi.mock('../stores/task.js', () => ({
  useTaskStore: () => ({
    submitBatchBackup: vi.fn(),
    runningTasks: [],
    hasRunning: false,
    runningCount: 0,
    recentTasks: [],
  }),
}))

import CMDB from '../views/CMDB.vue'
import AssetEditModal from '../components/AssetEditModal.vue'
import { assetApi, deviceApi } from '../api/index.js'

// ---- 测试夹具 ----
const DEVICES = [
  { id: 1, name: 'leaf-01', host: '10.0.0.1' },
  { id: 2, name: 'leaf-02', host: '10.0.0.2' },
]

const ASSETS = {
  1: { model: 'S5560X', software_package: 'R2607', location: '上海 IDC-A', tags: '核心,生产', status: 'online' },
  2: { model: 'S5560X', software_package: 'R2607', location: '北京 IDC-B', tags: '边缘', status: 'offline' },
}

// AssetEditModal 用 <Teleport to="body">，modal 内容脱离 wrapper root，需直接查 document.body
function findBodyButton(textSub) {
  return Array.from(document.body.querySelectorAll('button'))
    .find(b => (b.textContent || '').includes(textSub))
}

function findBodyInput(placeholderSub) {
  return Array.from(document.body.querySelectorAll('input'))
    .find(i => (i.placeholder || '').includes(placeholderSub))
}

async function setBodyInputValue(placeholderSub, value) {
  const input = findBodyInput(placeholderSub)
  if (!input) throw new Error(`未找到 placeholder 含 "${placeholderSub}" 的 input`)
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
}

describe('CMDB.vue 组件测试', () => {
  let wrapper

  beforeEach(() => {
    vi.clearAllMocks()
    deviceApi.list.mockResolvedValue({ success: true, data: DEVICES })
    deviceApi.get.mockResolvedValue({ success: true, data: {} })
    assetApi.get.mockImplementation(async (id) => ({ success: true, data: ASSETS[id] || {} }))
    assetApi.refresh.mockResolvedValue({ success: true, data: {} })
    assetApi.update.mockResolvedValue({ success: true, data: {} })
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
  })

  async function mountCmdb() {
    wrapper = mount(CMDB, { attachTo: document.body })
    await flushPromises() // 等 onMounted → loadAssets（deviceApi.list + assetApi.get）完成
    return wrapper
  }

  it('1. 列表加载：mount 后调 deviceApi.list + assetApi.get，渲染资产表格', async () => {
    const w = await mountCmdb()
    // API 调用断言
    expect(deviceApi.list).toHaveBeenCalledTimes(1)
    expect(assetApi.get).toHaveBeenCalledWith(1)
    expect(assetApi.get).toHaveBeenCalledWith(2)
    // 表格渲染断言：两台设备名 + 型号 + 位置均出现
    expect(w.text()).toContain('leaf-01')
    expect(w.text()).toContain('leaf-02')
    expect(w.text()).toContain('S5560X')
    expect(w.text()).toContain('上海 IDC-A')
  })

  it('2. 单设备采集：点击采集按钮，调 assetApi.refresh(deviceId)', async () => {
    const w = await mountCmdb()
    // 表格首行的"采集"按钮
    const refreshBtn = w.findAll('button').find(b => b.text().includes('采集'))
    expect(refreshBtn).toBeTruthy()
    await refreshBtn.trigger('click')
    await flushPromises()
    expect(assetApi.refresh).toHaveBeenCalledWith(1)
  })

  it('3. 编辑资产：点击编辑按钮，AssetEditModal 打开，调 assetApi.update', async () => {
    const w = await mountCmdb()
    const editBtn = w.findAll('button').find(b => b.text().includes('编辑资产'))
    expect(editBtn).toBeTruthy()
    await editBtn.trigger('click')
    await flushPromises()
    // AssetEditModal 应处于 open 状态，deviceId 透传正确
    const modal = w.findComponent(AssetEditModal)
    expect(modal.exists()).toBe(true)
    expect(modal.props('open')).toBe(true)
    expect(modal.props('deviceId')).toBe(1)
    // 点击 modal 内"保存"按钮（teleport 到 body）
    const saveBtn = findBodyButton('保存')
    expect(saveBtn).toBeTruthy()
    saveBtn.click()
    await flushPromises()
    expect(assetApi.update).toHaveBeenCalled()
    expect(assetApi.update.mock.calls[0][0]).toBe(1)
  })

  it('4. 状态筛选：输入搜索关键词后 filtered 列表变化', async () => {
    const w = await mountCmdb()
    // 初始 2 行
    expect(w.findAll('tbody tr').length).toBe(2)
    // 在搜索框输入关键词（CMDB 自身模板唯一的 input）
    const searchInput = w.find('input')
    await searchInput.setValue('leaf-01')
    // filtered 缩减为 1 行
    expect(w.findAll('tbody tr').length).toBe(1)
    expect(w.text()).toContain('leaf-01')
    expect(w.text()).not.toContain('leaf-02')
  })

  it('5. 位置更新：编辑位置字段后保存，调 assetApi.update 含 location', async () => {
    const w = await mountCmdb()
    const editBtn = w.findAll('button').find(b => b.text().includes('编辑资产'))
    await editBtn.trigger('click')
    await flushPromises()
    // 修改位置字段（placeholder 含"上海"的 input）
    await setBodyInputValue('上海', '深圳 IDC-C')
    // 保存
    const saveBtn = findBodyButton('保存')
    saveBtn.click()
    await flushPromises()
    expect(assetApi.update).toHaveBeenCalledWith(1, expect.objectContaining({ location: '深圳 IDC-C' }))
  })

  it('6. 标签管理：编辑标签字段后保存，调 assetApi.update 含 tags', async () => {
    const w = await mountCmdb()
    const editBtn = w.findAll('button').find(b => b.text().includes('编辑资产'))
    await editBtn.trigger('click')
    await flushPromises()
    // 修改标签字段（placeholder 含"核心"的 input）
    await setBodyInputValue('核心', '核心,生产,核心交换机')
    // 保存
    const saveBtn = findBodyButton('保存')
    saveBtn.click()
    await flushPromises()
    expect(assetApi.update).toHaveBeenCalledWith(1, expect.objectContaining({ tags: '核心,生产,核心交换机' }))
  })
})
