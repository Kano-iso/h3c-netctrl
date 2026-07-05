// v2.5 vitest 框架 smoke test
// 验证：happy-dom 环境 + @vue/test-utils mount + Select 组件渲染
// v2.6 加 i18n smoke test：vue-i18n 实例创建 + locale 切换响应式
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import Select from '../components/Select.vue'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'

describe('vitest smoke test', () => {
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
