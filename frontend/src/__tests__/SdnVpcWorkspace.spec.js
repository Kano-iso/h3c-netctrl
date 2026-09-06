import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createI18n } from 'vue-i18n'
import SdnVpcWorkspace from '../views/SdnVpcWorkspace.vue'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'
import { deviceApi, interfaceApi, sdnApi } from '../api/index.js'

vi.mock('../api/index.js', () => ({
  deviceApi: {
    list: vi.fn(),
  },
  interfaceApi: {
    list: vi.fn(),
  },
  sdnApi: {
    listTenants: vi.fn(),
    createTenant: vi.fn(),
    listVpcs: vi.fn(),
    getVpc: vi.fn(),
    createVpc: vi.fn(),
    deployVpc: vi.fn(),
    withdrawVpc: vi.fn(),
    listPortBindings: vi.fn(),
    createPortBinding: vi.fn(),
    startExpansion: vi.fn(),
    completeExpansion: vi.fn(),
    listDeployments: vi.fn(),
    syncValidation: vi.fn(),
    latestValidation: vi.fn(),
  },
}))

const testI18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

const PageHeaderStub = {
  props: ['title', 'subtitle', 'badge'],
  template: '<div><h1>{{ title }}</h1><p>{{ subtitle }}</p><slot name="actions" /></div>',
}

const RouterLinkStub = {
  props: ['to'],
  template: '<a href="#"><slot /></a>',
}

function mountPage() {
  return mount(SdnVpcWorkspace, {
    global: {
      plugins: [testI18n],
      stubs: { PageHeader: PageHeaderStub, RouterLink: RouterLinkStub },
    },
  })
}

describe('SdnVpcWorkspace.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.body.innerHTML = ''
    sdnApi.listTenants.mockResolvedValue({
      success: true,
      data: { total: 1, tenants: [{ id: 1, name: 'tenant-a', rd: '100:1', import_rt: '100:1', export_rt: '100:1', l3_vni: 10000, vpc_count: 1 }] },
    })
    sdnApi.listVpcs.mockResolvedValue({
      success: true,
      data: {
        total: 1,
        vpcs: [{
          id: 2,
          name: 'vpc-demo',
          tenant_id: 1,
          tenant_name: 'tenant-a',
          cidr: '192.168.1.0/24',
          gateway_ip: '192.168.1.254',
          gateway_mac: '00-00-00-00-4e21-01',
          vni: 20001,
          vsi_name: 'vpc0002',
          vsi_interface: 1001,
          vlan_id: 1001,
          status: 'active',
          binding_count: 1,
        }],
      },
    })
    deviceApi.list.mockResolvedValue({
      success: true,
      data: [
        { id: 4, name: 'Leaf-03', host: '192.168.100.4', platform: 'LSTN', sdn_role: null },
        { id: 5, name: 'Leaf-04', host: '192.168.100.5', platform: 'LSTN', sdn_role: 'evpn_leaf' },
      ],
    })
    interfaceApi.list.mockResolvedValue({
      success: true,
      data: [{ if_index: 3, name: 'GigabitEthernet1/0/3', status: 'up' }],
    })
    sdnApi.listPortBindings.mockResolvedValue({
      success: true,
      data: { total: 1, port_bindings: [{ id: 9, vpc_id: 2, device_id: 5, interface_name: 'GigabitEthernet1/0/3', if_index: 3, service_instance: 3100, access_vlan: null, status: 'active' }] },
    })
    sdnApi.listDeployments.mockResolvedValue({
      success: true,
      data: { total: 1, deployments: [{ id: 12, vpc_id: 2, device_id: 5, action: 'create', unit: 'vpc-create-all', status: 'success' }] },
    })
    sdnApi.latestValidation.mockResolvedValue({
      success: true,
      data: { validation_result: 'active', cached: false, validation_details: { bgp_peer: true } },
    })
    sdnApi.deployVpc.mockResolvedValue({ success: true, data: { total: 1, deployments: [] } })
    sdnApi.syncValidation.mockResolvedValue({
      success: true,
      data: { validation_result: 'active', cached: false, validation_details: { arp: true } },
    })
  })

  it('loads and renders VPC workspace data', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('SDN / VPC 工作台')
    expect(wrapper.text()).toContain('vpc-demo')
    expect(wrapper.text()).toContain('192.168.1.0/24')
    expect(wrapper.text()).toContain('GigabitEthernet1/0/3')
    expect(wrapper.text()).toContain('状态快照')
    expect(wrapper.text()).toContain('最佳实践')
    expect(wrapper.text()).not.toContain('Leaf-03 · 192.168.100.4')
  })

  it('requests a VPC deploy change for selected EVPN node', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '生成下发变更单').trigger('click')
    await flushPromises()

    expect(sdnApi.deployVpc).toHaveBeenCalledWith(2, {
      device_ids: [5],
      auto_apply: false,
      include_port_bindings: true,
    })
    expect(wrapper.text()).toContain('下发变更单已生成，设备尚未改动')
  })

  it('syncs validation for selected VPC and device', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '同步状态').trigger('click')
    await flushPromises()

    expect(sdnApi.syncValidation).toHaveBeenCalledWith(2, 5, true)
    expect(wrapper.text()).toContain('状态快照已同步')
  })

  it('keeps manual if_index input available when interface list is unavailable', async () => {
    interfaceApi.list.mockResolvedValue({ success: true, data: [] })

    const wrapper = mountPage()
    await flushPromises()

    const interfaceSelect = wrapper.find('select[name="sdn_access_interface"]')
    const ifIndexInput = wrapper.find('input[name="sdn_access_if_index"]')

    expect(interfaceSelect.exists()).toBe(true)
    expect(interfaceSelect.attributes('disabled')).toBeDefined()
    expect(ifIndexInput.exists()).toBe(true)
    expect(ifIndexInput.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('接口列表只是辅助选择')
  })

  it('opens best-practice guide', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '最佳实践').trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('SDN / VPC 最佳实践')
    expect(document.body.textContent).toContain('新建一个 VPC')
    expect(document.body.textContent).toContain('已有 VPC 扩容接入口')
  })
})
