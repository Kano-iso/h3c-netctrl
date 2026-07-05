// v2.5 vitest 框架 smoke test
// 验证：happy-dom 环境 + @vue/test-utils mount + Select 组件渲染
// v2.6 加 i18n smoke test：vue-i18n 实例创建 + locale 切换响应式
// v2.6 加 locale store test：localStorage 持久化 + toggleLocale 切换
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import Select from '../components/Select.vue'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'
import { useLocaleStore, LOCALE_STORAGE_KEY } from '../stores/locale.js'
import { i18n as globalI18n } from '../i18n'

describe('vitest smoke test', () => {
  // v2.6: Select 使用 useI18n()，mount 时需要 i18n 插件
  let i18n

  beforeEach(() => {
    i18n = createI18n({
      legacy: false,
      locale: 'zh-CN',
      fallbackLocale: 'zh-CN',
      messages: { 'zh-CN': zhCN, 'en-US': enUS },
    })
  })

  it('happy-dom 环境可用（document 定义存在）', () => {
    expect(document).toBeDefined()
    expect(document.createElement).toBeDefined()
  })

  it('Select 组件 mount 成功，渲染 placeholder', () => {
    const wrapper = mount(Select, {
      props: {
        options: [
          { id: 1, name: '设备A' },
          { id: 2, name: '设备B' },
        ],
        modelValue: null,
        placeholder: '请选择设备',
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('请选择设备')
  })

  it('Select 组件点击触发器后下拉菜单展开', async () => {
    const wrapper = mount(Select, {
      props: {
        options: [
          { id: 1, name: '设备A' },
          { id: 2, name: '设备B' },
        ],
        modelValue: null,
      },
      global: { plugins: [i18n] },
    })
    // 初始菜单不展开
    expect(wrapper.findAll('button').length).toBe(1) // 只有触发器按钮

    // 点击触发器
    await wrapper.find('button').trigger('click')
    expect(wrapper.findAll('button').length).toBe(3) // 触发器 + 2 个选项
    expect(wrapper.text()).toContain('设备A')
    expect(wrapper.text()).toContain('设备B')
  })
})

// v2.6 i18n smoke test（独立 describe 块：独立 i18n 实例）
describe('i18n smoke test (v2.6)', () => {
  let i18n

  beforeEach(() => {
    // 每个 case 独立 i18n 实例，避免 locale 污染
    i18n = createI18n({
      legacy: false,
      locale: 'zh-CN',
      fallbackLocale: 'zh-CN',
      messages: { 'zh-CN': zhCN, 'en-US': enUS },
    })
  })

  it('i18n 实例创建成功，默认 locale 为 zh-CN', () => {
    expect(i18n).toBeDefined()
    expect(i18n.global.locale.value).toBe('zh-CN')
  })

  it('i18n t() 默认 locale 翻译中文', () => {
    const wrapper = mount(
      { template: '<div>{{ $t("nav.dashboard") }}</div>' },
      { global: { plugins: [i18n] } }
    )
    expect(wrapper.text()).toBe('总览')
  })

  it('i18n 切换 locale 后 t() 翻译响应式更新', async () => {
    const wrapper = mount(
      { template: '<div>{{ $t("nav.dashboard") }}</div>' },
      { global: { plugins: [i18n] } }
    )
    expect(wrapper.text()).toBe('总览')

    // 切到 en-US
    i18n.global.locale.value = 'en-US'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toBe('Dashboard')

    // 切回 zh-CN
    i18n.global.locale.value = 'zh-CN'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toBe('总览')
  })

  it('i18n fallback：未知 key 走 fallbackLocale（中文）', () => {
    const wrapper = mount(
      { template: '<div>{{ $t("nonexistent.key") }}</div>' },
      { global: { plugins: [i18n] } }
    )
    // vue-i18n fallback 返回 key 本身（无翻译时）
    expect(wrapper.text()).toBe('nonexistent.key')
  })
})

// v2.6 locale store test：localStorage 持久化 + toggleLocale 切换
// 关键路径：i18n/index.js 启动时读 localStorage → setLocale 写 localStorage
describe('locale store (v2.6)', () => {
  beforeEach(() => {
    // 重置 i18n 全局状态（locale store 共享全局 i18n singleton）
    setActivePinia(createPinia())
    localStorage.removeItem(LOCALE_STORAGE_KEY)
    globalI18n.global.locale.value = 'zh-CN'
  })

  it('setLocale 切换 locale 并持久化到 localStorage', () => {
    const store = useLocaleStore()
    // 默认 zh-CN
    expect(store.current).toBe('zh-CN')

    // 切到 en-US
    store.setLocale('en-US')
    expect(store.current).toBe('en-US')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en-US')

    // 切回 zh-CN
    store.setLocale('zh-CN')
    expect(store.current).toBe('zh-CN')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN')
  })

  it('toggleLocale 在 zh-CN ↔ en-US 之间切换', () => {
    const store = useLocaleStore()
    expect(store.current).toBe('zh-CN')

    // 第一次 toggle：zh-CN → en-US
    store.toggleLocale()
    expect(store.current).toBe('en-US')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en-US')

    // 第二次 toggle：en-US → zh-CN
    store.toggleLocale()
    expect(store.current).toBe('zh-CN')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN')
  })

  it('setLocale 拒绝不支持的 locale（保持当前值）', () => {
    const store = useLocaleStore()
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    store.setLocale('fr-FR')  // 不支持
    expect(store.current).toBe('zh-CN')  // 不变
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })
})

// v2.6 utils/status.js + api/index.js i18n 测试
// 关键路径：非组件模块通过 i18n.global.t 走翻译，locale 切换响应式
import { getStatusLabel, getStatusDot, getIfaceStatusLabel } from '../utils/status.js'
import { apiCall } from '../api/index.js'

describe('utils/status.js i18n (v2.6)', () => {
  beforeEach(() => {
    globalI18n.global.locale.value = 'zh-CN'
  })

  it('getStatusLabel: zh-CN 返回中文标签', () => {
    expect(getStatusLabel('online')).toBe('在线')
    expect(getStatusLabel('offline')).toBe('离线')
    expect(getStatusLabel('unknown')).toBe('未采集')
  })

  it('getStatusLabel: en-US 返回英文标签', () => {
    globalI18n.global.locale.value = 'en-US'
    expect(getStatusLabel('online')).toBe('Online')
    expect(getStatusLabel('offline')).toBe('Offline')
    expect(getStatusLabel('unknown')).toBe('Not collected')
  })

  it('getStatusLabel: 未知状态走 unknown fallback', () => {
    expect(getStatusLabel('garbage')).toBe('未采集')
  })

  it('getIfaceStatusLabel: zh-CN 返回接口状态', () => {
    expect(getIfaceStatusLabel('up')).toBe('UP')
    expect(getIfaceStatusLabel('administratively_down')).toBe('禁用')
  })

  it('getIfaceStatusLabel: en-US 返回英文接口状态', () => {
    globalI18n.global.locale.value = 'en-US'
    expect(getIfaceStatusLabel('up')).toBe('UP')
    expect(getIfaceStatusLabel('administratively_down')).toBe('Disabled')
  })

  it('getStatusDot: 跟 locale 无关，返回 css class', () => {
    expect(getStatusDot('online')).toBe('bg-good')
    expect(getStatusDot('offline')).toBe('bg-bad')
  })
})

describe('api/index.js i18n (v2.6)', () => {
  beforeEach(() => {
    globalI18n.global.locale.value = 'zh-CN'
    // 重置 fetch mock
    global.fetch = vi.fn()
  })

  it('apiCall 网络异常时返回 zh-CN 错误', async () => {
    global.fetch.mockRejectedValueOnce(new Error('NetworkError'))
    const r = await apiCall('/test')
    expect(r.success).toBe(false)
    expect(r.error).toBe('网络请求失败，请检查后端服务是否运行')
  })

  it('apiCall 网络异常时返回 en-US 错误', async () => {
    globalI18n.global.locale.value = 'en-US'
    global.fetch.mockRejectedValueOnce(new Error('NetworkError'))
    const r = await apiCall('/test')
    expect(r.success).toBe(false)
    expect(r.error).toBe('Network request failed, please check if the backend service is running')
  })
})
