import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createI18n } from 'vue-i18n'
import SdnVpcWorkspace from '../views/SdnVpcWorkspace.vue'
import zhCN from '../i18n/zh-CN.js'
import enUS from '../i18n/en-US.js'
import { deviceApi, interfaceApi, sdnApi } from '../api/index.js'

vi.mock('../api/index.js', () => ({
  deviceApi: { list: vi.fn() },
  interfaceApi: { list: vi.fn() },
  sdnApi: {
    listTenants: vi.fn(), createTenant: vi.fn(), listVpcs: vi.fn(), createVpc: vi.fn(),
    deployVpc: vi.fn(), withdrawVpc: vi.fn(), accessOverview: vi.fn(), stateProjection: vi.fn(), stateProjectionHistory: vi.fn(), previewAccess: vi.fn(),
    executeAccess: vi.fn(), getOperation: vi.fn(), completeOperation: vi.fn(), syncValidation: vi.fn(),
    withdrawOperation: vi.fn(), reconcileOperation: vi.fn(),
  },
}))

const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zhCN, 'en-US': enUS } })
const mountPage = () => mount(SdnVpcWorkspace, { global: { plugins: [i18n], stubs: { Teleport: true } } })

const operationDetail = {
  operation_id: 41, operation_type: 'terminal_access', device_id: 5, status: 'awaiting_validation', expected_host_ip: '192.168.1.3',
  updated_at: '2026-09-14T10:00:00Z', attempts: [{ attempt_id: 8, kind: 'apply', status: 'success', units: [] }],
  explanation: {
    intent: 'access_bind',
    scope_summary: 'vpc=vpc-demo device=Leaf-04 if=GigabitEthernet1/0/3(3) host=192.168.1.3',
    safety_boundary: { target_only: true, ambiguous_claims: false },
    impact: {
      nodes: [
        { kind: 'vpc', id: 2, label: 'vpc-demo', truth_kind: 'desired', source: 'operation_scope' },
        { kind: 'device', id: 5, label: 'Leaf-04', truth_kind: 'desired', source: 'operation_scope' },
        { kind: 'interface', id: 'device:5:if_index:3', label: 'GigabitEthernet1/0/3', truth_kind: 'desired', source: 'operation_scope' },
        { kind: 'host', id: '192.168.1.3', label: '192.168.1.3', truth_kind: 'desired', source: 'operation_record' },
      ],
      relations: [
        { from_kind: 'vpc', from_id: 2, relation: 'targets', to_kind: 'device', to_id: 5 },
        { from_kind: 'device', from_id: 5, relation: 'exposes', to_kind: 'interface', to_id: 'device:5:if_index:3' },
        { from_kind: 'interface', from_id: 'device:5:if_index:3', relation: 'expects', to_kind: 'host', to_id: '192.168.1.3' },
      ],
      changes: [], safety: { target_only: true, ambiguous_claims: false, shared_vpc_gateway_not_target: true },
    },
  },
}

describe('SdnVpcWorkspace.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sdnApi.listTenants.mockResolvedValue({ success: true, data: { tenants: [{ id: 1, name: 'tenant-a' }] } })
    sdnApi.listVpcs.mockResolvedValue({ success: true, data: { vpcs: [{
      id: 2, name: 'vpc-demo', tenant_id: 1, tenant_name: 'tenant-a', cidr: '192.168.1.0/24',
      gateway_ip: '192.168.1.254', vni: 10, vsi_name: 'vpna', status: 'active',
    }] } })
    deviceApi.list.mockResolvedValue({ success: true, data: [
      { id: 4, name: 'Leaf-03', host: '192.168.100.4', platform: 'LSTN', sdn_role: null },
      { id: 5, name: 'Leaf-04', host: '192.168.100.5', platform: 'LSTN', sdn_role: 'evpn_leaf' },
    ] })
    interfaceApi.list.mockResolvedValue({ success: true, data: [{ if_index: 3, name: 'GigabitEthernet1/0/3', status: 'up' }] })
    sdnApi.accessOverview.mockResolvedValue({ success: true, data: {
      bindings: [{ id: 9, vpc_id: 2, device_id: 5, interface_name: 'GigabitEthernet1/0/3', if_index: 3, service_instance: 3100, status: 'active' }],
      operations: [{ operation_id: 41, status: 'awaiting_validation', expected_host_ip: '192.168.1.3', updated_at: '2026-09-14T10:00:00Z' }],
      latest_validation: [{ id: 3, device_id: 5, validation_result: 'active' }],
      observations: [{ operation_id: 41, device_id: 5, expected_host_ip: '192.168.1.3', host_observed: true, items: [] }],
    } })
    sdnApi.stateProjection.mockResolvedValue({ success: true, data: {
      aggregate: 'drifted', excluded: [{ device_id: 4, reason: 'not_evpn_leaf' }], leaves: [{
        device_id: 5, device_name: 'Leaf-04', device_host: '192.168.100.5', aggregate: 'drifted',
        desired: {
          vsi: { present: true }, vsi_up: { expected: true }, vsi_interface: { present: true }, l3_vni: { present: true },
          port_bindings: [{ binding_id: 9, interface_name: 'GigabitEthernet1/0/3', service_instance: 3100, access_vlan: null }],
        },
        observed: { collected_at: '2026-09-14T10:00:00Z', facts: { vsi_exists: true, vsi_up: true, vsi_interface_exists: true, l3_vni_present: false } },
        diff: {
          vsi: { status: 'aligned', reason_code: 'vsi_present', evidence: { desired_source: { kind: 'deployment', deployment_id: 17, version: 2 }, observed_source: { kind: 'snapshot', snapshot_id: 3, collected_at: '2026-09-14T10:00:00Z', command: 'display l2vpn vsi name vpna verbose' } } }, vsi_up: { status: 'aligned', reason_code: 'vsi_up' },
          vsi_interface: { status: 'aligned', reason_code: 'vsi_interface_present' }, l3_vni: { status: 'drifted', reason_code: 'l3_vni_missing' },
          port_bindings: [{ binding_id: 9, interface_name: 'GigabitEthernet1/0/3', service_instance: { status: 'aligned', reason_code: 'service_instance_present', observed: [3100] }, access_vlan: { status: 'not_applicable', reason_code: 'not_required', observed: null } }],
        },
      }],
    } })
    sdnApi.stateProjectionHistory.mockResolvedValue({ success: true, data: { timelines: [{
      device_id: 5, points: [{
        snapshot_id: 2, collected_at: '2026-09-13T10:00:00Z', validation_result: 'degraded', aggregate: 'drifted',
        desired: { basis: 'current_target' },
        diff: { vsi: { status: 'aligned' }, vsi_interface: { status: 'aligned' }, l3_vni: { status: 'drifted' } },
        correlation: {
          status: 'linked', operation_id: 41, attempt_id: 8,
          operation: { id: 41, operation_type: 'terminal_access', status: 'awaiting_validation' },
          attempt: { id: 8, kind: 'validate', status: 'succeeded' },
        },
      }],
    }] } })
    sdnApi.getOperation.mockResolvedValue({ success: true, data: operationDetail })
    sdnApi.previewAccess.mockResolvedValue({ success: true, data: { plan_id: 'plan-1', predeploy_status: 'ready', blocking: [] } })
    sdnApi.executeAccess.mockResolvedValue({ success: true, data: { operation_id: 42, status: 'awaiting_validation', expected_host_ip: '192.168.1.4' } })
    sdnApi.completeOperation.mockResolvedValue({ success: true, data: { status: 'validated' } })
    sdnApi.withdrawOperation.mockResolvedValue({ success: true, data: { status: 'withdrawn' } })
    sdnApi.reconcileOperation.mockResolvedValue({ success: true, data: { status: 'validated' } })
    sdnApi.syncValidation.mockResolvedValue({ success: true, data: { cached: false } })
  })

  it('renders a VPC-centered map and excludes non-EVPN devices', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('网络业务工作台')
    expect(wrapper.text()).toContain('vpc-demo')
    expect(wrapper.text()).toContain('192.168.1.0/24')
    expect(wrapper.text()).toContain('Leaf-04')
    expect(wrapper.text()).toContain('GigabitEthernet1/0/3')
    expect(wrapper.text()).toContain('192.168.1.3')
    expect(wrapper.text()).not.toContain('Leaf-03')
    expect(sdnApi.accessOverview).toHaveBeenCalledWith(2)
    expect(sdnApi.stateProjection).toHaveBeenCalledWith(2)
  })

  it('renders the persisted operation impact chain in PULSE', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.operation-table button').trigger('click')
    await flushPromises()

    expect(sdnApi.getOperation).toHaveBeenCalledWith(41)
    expect(wrapper.find('.impact-map').exists()).toBe(true)
    expect(wrapper.text()).toContain('操作影响范围')
    expect(wrapper.text()).toContain('vpc-demo')
    expect(wrapper.text()).toContain('Leaf-04')
    expect(wrapper.text()).toContain('GigabitEthernet1/0/3')
    expect(wrapper.text()).toContain('192.168.1.3')
    expect(wrapper.text()).toContain('作用于')
    expect(wrapper.text()).toContain('承载接口')
    expect(wrapper.text()).toContain('预期接入')
    expect(wrapper.text()).toContain('不代表物理拓扑、实时转发路径或因果关系')
  })

  it('keeps desired, observed, and drift as separate STRATA facts', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')

    expect(wrapper.text()).toContain('存在差异')
    expect(wrapper.text()).toContain('三层网关接口')
    expect(wrapper.text()).toContain('SI 3100')
    expect(wrapper.text()).toContain('1 台非 EVPN 设备已排除')
  })

  it('only collects device evidence after an explicit STRATA refresh', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(sdnApi.syncValidation).not.toHaveBeenCalled()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')
    await wrapper.find('button[title="重新采集此设备的状态证据"]').trigger('click')
    await flushPromises()

    expect(sdnApi.syncValidation).toHaveBeenCalledWith(2, 5, true)
    expect(wrapper.text()).toContain('设备证据已更新')
  })

  it('opens a sanitized evidence pointer for a STRATA dimension', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')
    await wrapper.findAll('.projection-row').find((row) => row.text().startsWith('VSI')).trigger('click')

    expect(wrapper.text()).toContain('部署记录 #17 · 版本 2')
    expect(wrapper.text()).toContain('设备快照 #3')
    expect(wrapper.text()).toContain('display l2vpn vsi name vpna verbose')
    expect(wrapper.text()).toContain('VSI 已存在')
  })

  it('filters STRATA leaves without changing the selected VPC context', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')

    expect(wrapper.find('.projection-card').exists()).toBe(true)
    await wrapper.findAll('.projection-filters button').find((button) => button.text().includes('一致')).trigger('click')
    expect(wrapper.text()).toContain('当前筛选条件下没有 Leaf')
    expect(wrapper.text()).toContain('vpc-demo')
    await wrapper.findAll('.projection-filters button').find((button) => button.text().includes('差异')).trigger('click')
    expect(wrapper.find('.projection-card').text()).toContain('Leaf-04')
  })

  it('loads a Leaf evidence trail only when the user expands it', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(sdnApi.stateProjectionHistory).not.toHaveBeenCalled()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')
    await wrapper.find('.history-toggle').trigger('click')
    await flushPromises()

    expect(sdnApi.stateProjectionHistory).toHaveBeenCalledWith(2, 5, 10)
    expect(wrapper.text()).toContain('历史设备快照均与当前目标配置比较')
    expect(wrapper.text()).toContain('#2 · degraded')
    await wrapper.find('.history-track button').trigger('click')
    expect(wrapper.text()).toContain('采集结论')
    expect(wrapper.text()).toContain('已关联，仅表示证据归属')
    expect(wrapper.text()).toContain('#41 · terminal_access · awaiting_validation')
    await wrapper.find('.history-operation-link').trigger('click')
    await flushPromises()
    expect(sdnApi.getOperation).toHaveBeenCalledWith(41)
    expect(wrapper.text()).toContain('一次操作的完整生命线')
  })

  it('reloads an open evidence trail after an explicit device refresh', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('STRATA')).trigger('click')
    await wrapper.find('.history-toggle').trigger('click')
    await flushPromises()
    await wrapper.find('button[title="重新采集此设备的状态证据"]').trigger('click')
    await flushPromises()

    expect(sdnApi.syncValidation).toHaveBeenCalledWith(2, 5, true)
    expect(sdnApi.stateProjectionHistory).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('#2 · degraded')
  })

  it('previews an access request before executing it', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('接入终端')).trigger('click')
    await flushPromises()

    await wrapper.find('select[name="sdn_access_interface"]').setValue('3')
    await wrapper.find('input[placeholder="192.168.1.0/24"]').setValue('192.168.1.4')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(sdnApi.previewAccess).toHaveBeenCalledWith(2, expect.objectContaining({
      device_id: 5, if_index: 3, interface_name: 'GigabitEthernet1/0/3', expected_host_ip: '192.168.1.4',
    }))
    expect(wrapper.text()).toContain('可以安全执行')

    await wrapper.findAll('button').find((button) => button.text() === '确认并下发').trigger('click')
    await flushPromises()
    expect(sdnApi.executeAccess).toHaveBeenCalledWith(2, expect.objectContaining({ plan_id: 'plan-1', auto_apply: true }))
    expect(wrapper.text()).toContain('配置已下发，等待接线验证')
  })

  it('does not allow execution when preview contains blockers', async () => {
    sdnApi.previewAccess.mockResolvedValue({ success: true, data: {
      plan_id: 'blocked-plan', predeploy_status: 'unknown',
      blocking: [{ code: 'sdn.predeploy_unknown', detail: 'evidence is stale' }],
    } })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('接入终端')).trigger('click')
    await flushPromises()
    await wrapper.find('select[name="sdn_access_interface"]').setValue('3')
    await wrapper.find('input[placeholder="192.168.1.0/24"]').setValue('192.168.1.4')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const confirm = wrapper.findAll('button').find((button) => button.text() === '确认并下发')
    expect(wrapper.text()).toContain('当前不能执行')
    expect(wrapper.text()).toContain('evidence is stale')
    expect(confirm.attributes('disabled')).toBeDefined()
    expect(sdnApi.executeAccess).not.toHaveBeenCalled()
  })

  it('resumes a persisted operation and exposes only valid actions', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('#41')).trigger('click')
    await flushPromises()

    expect(sdnApi.getOperation).toHaveBeenCalledWith(41)
    expect(wrapper.text()).toContain('完成接线并验证')
    expect(wrapper.text()).toContain('撤回此接入口')
    expect(wrapper.text()).not.toContain('核对真实状态')

    await wrapper.findAll('button').find((button) => button.text() === '完成接线并验证').trigger('click')
    await flushPromises()
    expect(sdnApi.completeOperation).toHaveBeenCalledWith(41, { force_validation: true })
  })

  it('keeps legacy Fabric controls in the resource tools', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '资源工具').trigger('click')

    expect(wrapper.text()).toContain('当前 VPC 的设备落地')
    expect(wrapper.text()).toContain('生成下发变更单')
    expect(wrapper.text()).toContain('生成撤回变更单')
  })
})
