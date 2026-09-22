import { test, expect } from '@playwright/test'

const devices = [
  { id: 4, name: 'Access-01', host: '192.168.100.4', platform: 'LSTN', sdn_role: null },
  { id: 5, name: 'Leaf-04', host: '192.168.100.5', platform: 'LSTN', sdn_role: 'evpn_leaf' },
  { id: 6, name: 'Leaf-05', host: '192.168.100.6', platform: 'LSTN', sdn_role: 'evpn_leaf' },
]

const overview = {
  bindings: [{ id: 9, vpc_id: 2, device_id: 5, interface_name: 'GigabitEthernet1/0/3', if_index: 3, service_instance: 3100, status: 'active' }],
  operations: [{ operation_id: 41, status: 'awaiting_validation', expected_host_ip: '192.168.1.3', updated_at: '2026-09-14T10:00:00Z' }],
  latest_validation: [{ id: 3, device_id: 5, validation_result: 'active' }],
  observations: [{ operation_id: 41, device_id: 5, expected_host_ip: '192.168.1.3', host_observed: true, items: [] }],
}

const stateProjection = {
  aggregate: 'aligned', excluded: [{ device_id: 4, reason: 'not_evpn_leaf' }], leaves: [{
    device_id: 5, device_name: 'Leaf-04', device_host: '192.168.100.5', aggregate: 'aligned',
    desired: {
      vsi: { present: true }, vsi_up: { expected: true }, vsi_interface: { present: true }, l3_vni: { present: true },
      port_bindings: [{ binding_id: 9, interface_name: 'GigabitEthernet1/0/3', service_instance: 3100, access_vlan: null }],
    },
    observed: { collected_at: '2026-09-14T10:00:00Z', facts: { vsi_exists: true, vsi_up: true, vsi_interface_exists: true, l3_vni_present: true } },
    diff: {
      vsi: { status: 'aligned', reason_code: 'vsi_present' }, vsi_up: { status: 'aligned', reason_code: 'vsi_up' },
      vsi_interface: { status: 'aligned', reason_code: 'vsi_interface_present' }, l3_vni: { status: 'aligned', reason_code: 'l3_vni_present' },
      port_bindings: [{ binding_id: 9, interface_name: 'GigabitEthernet1/0/3', service_instance: { status: 'aligned', reason_code: 'service_instance_present', observed: [3100] }, access_vlan: { status: 'not_applicable', reason_code: 'not_required', observed: null } }],
    },
  }],
}

const stateProjectionHistory = {
  desired_basis: 'current_target',
  timelines: [{
    device_id: 5,
    points: [{
      snapshot_id: 2,
      collected_at: '2026-09-13T10:00:00Z',
      validation_result: 'degraded',
      aggregate: 'drifted',
      desired: { basis: 'current_target' },
      diff: { vsi: { status: 'aligned' }, vsi_interface: { status: 'aligned' }, l3_vni: { status: 'drifted' } },
      correlation: {
        status: 'linked', operation_id: 41, attempt_id: 8,
        operation: { id: 41, operation_type: 'terminal_access', status: 'awaiting_validation' },
        attempt: { id: 8, kind: 'validate', status: 'succeeded' },
      },
    }],
  }],
}

const operation = {
  ...overview.operations[0],
  device_id: 5,
  scope: { vpc_id: 2, vpc_name: 'production-a', device_id: 5, device_name: 'Leaf-04', if_index: 3, interface_name: 'GigabitEthernet1/0/3', expected_host_ip: '192.168.1.3' },
  explanation: {
    intent: 'access_bind',
    scope_summary: 'vpc=production-a device=Leaf-04 if=GigabitEthernet1/0/3(3) host=192.168.1.3',
    truth_state: 'pending',
    safety_boundary: { target: { device_id: 5, if_index: 3, interface_name: 'GigabitEthernet1/0/3' }, target_only: true, ambiguous_claims: false },
    impact: {
      nodes: [
        { kind: 'vpc', id: 2, label: 'production-a', truth_kind: 'desired', source: 'operation_scope' },
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
  attempts: [{
    attempt_id: 8,
    kind: 'execute',
    status: 'succeeded',
    units: [
      { unit_index: 0, unit_name: 'vsi-l2', state: 'succeeded', completed_at: '2026-09-14T10:00:01Z', evidence: null, explanation: { category: 'execution_record', truth_kind: 'desired', source: 'execution_record', scope: null, observed_at: null, freshness: null } },
      { unit_index: 1, unit_name: 'port-bind', state: 'succeeded', completed_at: '2026-09-14T10:00:06Z', evidence: { reconciled: true }, explanation: { category: 'readback_verified', truth_kind: 'observed', source: 'snapshot', scope: operationScope(), observed_at: '2026-09-14T10:00:06Z', freshness: null } },
    ],
  }],
}

function operationScope() {
  return { vpc_name: 'production-a', device_name: 'Leaf-04', interface_name: 'GigabitEthernet1/0/3', expected_host_ip: '192.168.1.3' }
}

async function installMocks(page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    let data = null
    if (url.pathname === '/api/devices') data = devices
    if (url.pathname === '/api/sdn/tenants') data = { tenants: [{ id: 1, name: 'tenant-a' }] }
    if (url.pathname === '/api/sdn/vpcs') data = { vpcs: [{ id: 2, name: 'production-a', tenant_id: 1, tenant_name: 'tenant-a', cidr: '192.168.1.0/24', gateway_ip: '192.168.1.254', vni: 10, vsi_name: 'vpna', status: 'active' }] }
    if (url.pathname === '/api/sdn/vpcs/2/access-overview') data = overview
    if (url.pathname === '/api/sdn/vpcs/2/state-projection') data = stateProjection
    if (url.pathname === '/api/sdn/vpcs/2/state-projection/history') data = stateProjectionHistory
    if (url.pathname === '/api/devices/5/interfaces') data = [{ if_index: 3, name: 'GigabitEthernet1/0/3', status: 'up' }]
    if (url.pathname === '/api/sdn/vpcs/2/access-preview') data = { plan_id: 'visual-plan', predeploy_status: 'ready', blocking: [] }
    if (url.pathname === '/api/sdn/vpcs/2/access') data = { operation_id: 42, status: 'awaiting_validation', expected_host_ip: '192.168.1.4' }
    if (url.pathname === '/api/sdn/operations/41') data = operation
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, data }) })
  })
}

test.describe('NEXT S1 network service workbench', () => {
  test.beforeEach(async ({ page }) => { await installMocks(page) })

  for (const viewport of [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }]) {
    test(`${viewport.name}: VPC context remains readable without page overflow`, async ({ page }) => {
      const pageErrors = []
      const requestFailures = []
      const consoleErrors = []
      page.on('pageerror', (exception) => pageErrors.push(exception.message))
      page.on('requestfailed', (request) => requestFailures.push(`${request.url()}: ${request.failure()?.errorText}`))
      page.on('console', (entry) => { if (entry.type() === 'error') consoleErrors.push(entry.text()) })
      await page.setViewportSize(viewport)
      const response = await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
      expect(response?.status()).toBe(200)
      expect(await page.content()).toContain('/src/main.js')
      expect(pageErrors).toEqual([])
      expect(requestFailures).toEqual([])
      expect(consoleErrors).toEqual([])
      await expect(page.locator('.next-workbench')).toBeVisible()
      await expect(page.getByRole('heading', { name: '网络业务工作台' })).toBeVisible()
      await expect(page.getByText('production-a').first()).toBeVisible()
      await expect(page.getByText('Leaf-04').first()).toBeVisible()
      await expect(page.getByText('192.168.1.3').first()).toBeVisible()
      await expect(page.getByText('Access-01')).toHaveCount(0)
      await page.locator('.operation-table').getByRole('button', { name: /192\.168\.1\.3/ }).click()
      await expect(page.locator('.impact-map')).toBeVisible()
      await expect(page.locator('.impact-chain')).toContainText('GigabitEthernet1/0/3')
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow).toBeLessThanOrEqual(1)
    })
  }

  test('preview gates execution and leads to a persisted operation', async ({ page }) => {
    await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /接入终端/ }).click()
    await page.locator('select[name="sdn_access_interface"]').selectOption('3')
    await page.getByLabel('期望主机 IP').fill('192.168.1.4')
    await page.getByRole('button', { name: '预览变更' }).click()
    await expect(page.getByText('可以安全执行')).toBeVisible()
    await page.getByRole('button', { name: '确认并下发' }).click()
    await expect(page.getByText('配置已下发，等待接线验证')).toBeVisible()
  })

  test('shared context moves across Atlas, Pulse and Strata', async ({ page }) => {
    await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
    await page.locator('.operation-table').getByRole('button', { name: /192\.168\.1\.3/ }).click()
    await expect(page.getByText('一次操作的完整生命线')).toBeVisible()
    await expect(page.getByText('vsi-l2')).toBeVisible()
    await expect(page.getByText('配置执行已记录，但尚未由设备回读验证。')).toBeVisible()
    await expect(page.getByText('设备回读已确认目标状态。')).toBeVisible()
    await expect(page.locator('.impact-map')).toBeVisible()
    await expect(page.getByText('操作影响范围')).toBeVisible()
    await expect(page.locator('.impact-chain')).toContainText('production-a')
    await expect(page.locator('.impact-chain')).toContainText('Leaf-04')
    await expect(page.locator('.impact-chain')).toContainText('GigabitEthernet1/0/3')
    await expect(page.locator('.impact-chain')).toContainText('预期接入')

    await page.getByRole('button', { name: /STRATA/ }).click()
    await expect(page.getByText('从业务目标深入到设备承载')).toBeVisible()
    await expect(page.getByText('VNI 10 · vpna')).toBeVisible()
    await expect(page.getByText('一致').first()).toBeVisible()
    await expect(page.getByText('SI 3100').first()).toBeVisible()
    await page.getByRole('button', { name: '查看证据轨迹' }).click()
    await expect(page.getByText('历史设备快照均与当前目标配置比较').first()).toBeVisible()
    await expect(page.getByText('#2 · degraded · 操作 #41')).toBeVisible()
    await page.locator('.history-track').getByRole('button').click()
    await expect(page.getByText('已关联，仅表示证据归属')).toBeVisible()
    await page.getByRole('button', { name: '查看关联操作生命线' }).click()
    await expect(page.getByText('一次操作的完整生命线')).toBeVisible()

    await page.getByRole('button', { name: /ATLAS/ }).click()
    await expect(page.locator('.stage-label')).toContainText('接入关系')
  })
})
