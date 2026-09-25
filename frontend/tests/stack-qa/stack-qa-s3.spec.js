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

test('S3 real stack: GUARD evaluates, records history, saves preference, and performs no device I/O', async ({ page, request }) => {
  await openGuard(page)
  const guard = page.locator('.guard-view')
  const vpcId = await vpcIdOf(request)
  const ioBefore = ioLines()

  await expect(guard).toContainText('当前版本只保存周期偏好，不会自动定时执行')
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

  const policyResponse = await request.get(`/api/sdn/vpcs/${vpcId}/assurance-policy`)
  expect(policyResponse.ok()).toBeTruthy()
  expect((await policyResponse.json()).data).toMatchObject({
    enabled: true,
    cadence: '30m',
    response_mode: 'observe_only',
    version: 1,
  })
  expect(ioLines()).toBe(ioBefore)
})
