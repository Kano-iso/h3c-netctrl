import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createI18n } from 'vue-i18n'
import ZtpRecovery from '../views/ZtpRecovery.vue'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'
import { ztpApi } from '../api/index.js'

vi.mock('../api/index.js', () => ({
  ztpApi: {
    getRecoveryOverride: vi.fn(),
    setRecoveryOverride: vi.fn(),
    clearRecoveryOverride: vi.fn(),
  },
}))

const testI18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

const PageHeaderStub = {
  props: ['title', 'subtitle'],
  template: '<div><h1>{{ title }}</h1><p>{{ subtitle }}</p><slot name="actions" /></div>',
}

function mountPage() {
  return mount(ZtpRecovery, {
    global: {
      plugins: [testI18n],
      stubs: { PageHeader: PageHeaderStub },
    },
  })
}

describe('ZtpRecovery.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ztpApi.getRecoveryOverride.mockResolvedValue({ success: true, data: { active: false, override: null } })
    ztpApi.setRecoveryOverride.mockResolvedValue({
      success: true,
      data: {
        active: true,
        override: {
          host: '192.168.100.2',
          sysname: 'Leaf-01',
          platform: 'lstn',
          updated_at: '2026-07-18T12:00:00Z',
        },
      },
    })
    ztpApi.clearRecoveryOverride.mockResolvedValue({ success: true, data: { active: false, override: null } })
  })

  it('loads status and submits recovery override', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('ZTP 恢复上线')
    await wrapper.find('input[placeholder="192.168.100.2"]').setValue('192.168.100.2')
    await wrapper.find('input[placeholder="ztp-switch-2"]').setValue('Leaf-01')
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()

    expect(ztpApi.setRecoveryOverride).toHaveBeenCalledWith(expect.objectContaining({
      host: '192.168.100.2',
      name: 'Leaf-01',
      platform: 'lstn',
      username: 'python',
      netconf_port: 830,
    }))
    expect(wrapper.text()).toContain('恢复配置已启用')
    expect(wrapper.text()).toContain('恢复模式')
  })

  it('clears recovery override', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    await buttons.find((b) => b.text() === '清除恢复配置').trigger('click')
    await flushPromises()

    expect(ztpApi.clearRecoveryOverride).toHaveBeenCalled()
    expect(wrapper.text()).toContain('已恢复默认 ZTP 配置')
  })
})
