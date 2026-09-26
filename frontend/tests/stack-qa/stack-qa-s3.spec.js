// S3 GUARD real-stack acceptance: real Vue -> FastAPI -> isolated SQLite.
// Assurance evaluates persisted projection facts only; device-I/O must not grow.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const STACK_QA_DIR = process.env.STACK_QA_DIR || '/tmp/stack-qa'

function ioLines() {
  try {
    return readFileSync(join(STACK_QA_DIR, 'device-io.log'), 'utf-8')
      .split('\n').filter(Boolean).length
  } catch {
    return 0
  }
}

async function openGuard(page) {
  await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
  await expect(page.locator('.next-workbench')).toBeVisible()
  await expect(page.getByText('stack-vpc').first()).toBeVisible()
  await page.getByRole('button', { name: /GUARD/ }).click()
  await expect(page.locator('.guard-view')).toBeVisible()
}

async function vpcIdOf(request) {
  const response = await request.get('/api/sdn/vpcs')
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  return body.data.vpcs.find((vpc) => vpc.name === 'stack-vpc').id
}

test('S3 real stack: GUARD evaluates manual and business events without device I/O', async ({ page, request }) => {
  await openGuard(page)
  const guard = page.locator('.guard-view')
  const vpcId = await vpcIdOf(request)
  const ioBefore = ioLines()

  await expect(guard).toContainText('保障未启用')
  await expect(guard).toContainText('周期检查只读取平台已有证据')
  await expect(guard).toContainText('还没有评估记录')

  await guard.getByRole('button', { name: '立即评估' }).click()
  await expect(page.locator('.notice.success')).toContainText('只读评估已完成')
  await expect(guard.locator('.guard-history-list button')).toHaveCount(1)
  await expect(guard).toContainText('存在覆盖缺口')

  const runsResponse = await request.get(`/api/sdn/vpcs/${vpcId}/assurance-runs`)
  expect(runsResponse.ok()).toBeTruthy()
  const runs = (await runsResponse.json()).data.runs
  expect(runs).toHaveLength(1)
  expect(runs[0]).toMatchObject({ trigger: 'manual', status: 'completed', overall: 'attention' })
  expect(runs[0].items.some((item) => item.category === 'coverage_gap')).toBe(true)
  expect(ioLines()).toBe(ioBefore)

  await guard.locator('.toggle-row input').check()
  await guard.locator('.guard-policy select').selectOption('30m')
  await guard.getByRole('button', { name: '保存偏好' }).click()
  await expect(page.locator('.notice.success')).toContainText('保障偏好已保存')
  await expect(guard).toContainText('等待调度')

  const policyResponse = await request.get(`/api/sdn/vpcs/${vpcId}/assurance-policy`)
  expect(policyResponse.ok()).toBeTruthy()
  expect((await policyResponse.json()).data).toMatchObject({
    enabled: true,
    cadence: '30m',
    response_mode: 'observe_only',
    version: 1,
  })
  expect(ioLines()).toBe(ioBefore)

  // A persisted business-context change triggers an event evaluation.  Re-open GUARD
  // through the real UI so the user-visible history, not only the API row, is verified.
  const projectionResponse = await request.get(`/api/sdn/vpcs/${vpcId}/state-projection`)
  expect(projectionResponse.ok()).toBeTruthy()
  const projection = (await projectionResponse.json()).data
  const spare = projection.scope.members.find((member) => member.name === 'Leaf-Spare')
  expect(spare).toBeTruthy()

  const addException = await request.put(
    `/api/sdn/vpcs/${vpcId}/devices/${spare.device_id}/scope-exception`,
    { data: { exception_type: 'maintenance_pause', reason: 'S3 event assurance probe' } },
  )
  expect(addException.ok()).toBeTruthy()
  const exceptionListResponse = await request.get(`/api/sdn/vpcs/${vpcId}/scope-exceptions`)
  expect(exceptionListResponse.ok()).toBeTruthy()
  const addedException = (await exceptionListResponse.json()).data.exceptions.find(
    (entry) => entry.device_id === spare.device_id,
  )
  expect(addedException).toBeTruthy()
  expect(ioLines()).toBe(ioBefore)

  await page.reload({ waitUntil: 'networkidle' })
  await openGuard(page)
  await expect(page.locator('.guard-history-list button')).toHaveCount(2)
  await expect(page.locator('.guard-history-list')).toContainText('事件')

  const clearException = await request.delete(
    `/api/sdn/vpcs/${vpcId}/devices/${spare.device_id}/scope-exception`,
  )
  expect(clearException.ok()).toBeTruthy()
  expect(ioLines()).toBe(ioBefore)

  const finalRunsResponse = await request.get(`/api/sdn/vpcs/${vpcId}/assurance-runs`)
  expect(finalRunsResponse.ok()).toBeTruthy()
  const finalRuns = (await finalRunsResponse.json()).data.runs
  expect(finalRuns).toHaveLength(3)
  expect(finalRuns.filter((run) => run.trigger === 'event')).toHaveLength(2)
  expect(finalRuns.filter((run) => run.trigger === 'event').every((run) => run.status === 'completed')).toBe(true)
  const eventKeys = finalRuns.filter((run) => run.trigger === 'event').map((run) => run.event_key).sort()
  expect(eventKeys[0]).toMatch(/^scope-exc:\d+:cleared$/)
  expect(eventKeys[1]).toMatch(/^scope-exc:\d+:v1$/)
  expect(eventKeys[0].split(':')[1]).toBe(eventKeys[1].split(':')[1])

  await page.reload({ waitUntil: 'networkidle' })
  await openGuard(page)
  await expect(page.locator('.guard-history-list button')).toHaveCount(3)
  await expect(page.locator('.guard-history-list').getByText(/事件/)).toHaveCount(2)
  expect(ioLines()).toBe(ioBefore)
})
