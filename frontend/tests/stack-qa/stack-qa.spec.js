// S1-027 真实应用栈隔离联调 spec
//
// 与 tests/e2e（mock 基线）分离：本 spec 全程【真实 API 请求】——vite dev 代理到
// 真实 FastAPI（隔离 SQLite），无任何 page.route mock。设备 I/O 由后端进程内
// 边界 fake 承担（run_stack_qa.sh 事后断言 device-io.log）。
//
// 覆盖：
//   1) 接入故事：选已有 VPC → 选 Leaf/业务口 → 服务端 preview → execute（不下发
//      真机）→ 持久化 operation → PULSE 展示 intent/scope/safety + 逐单元 truth
//      kind（执行记录，未由设备回读验证）→ STRATA 同一上下文。
//   2) 诚实状态：验证证据不足 → 保持 unknown + ambiguous_claims，不得冒充设备验证。
//      （第二个用例换用另一业务口，避免第一个用例留下的 active 绑定造成端口冲突。）
import { test, expect } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

const STACK_QA_DIR = process.env.STACK_QA_DIR || '/tmp/stack-qa'
const VPC = 'stack-vpc'
const TENANT = 'stack-qa'
const LEAF = 'Leaf-Stack'
const LEAF_HOST = '192.0.2.10' // TEST-NET 合成地址

async function openWorkbench(page) {
  await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
  await expect(page.locator('.next-workbench')).toBeVisible()
  // 真实后端返回的合成 VPC 已加载
  await expect(page.getByText(VPC).first()).toBeVisible()
}

// 完整接入故事：preview（服务端）→ execute（auto_apply，边界 fake，无真机下发）
async function runAccessStory(page, { ifIndex, ifaceName, host }) {
  await page.getByRole('button', { name: /接入终端/ }).click()
  await page.locator('.access-modal select').first().selectOption({ label: `${LEAF} · ${LEAF_HOST}` })
  // 接口来自真实 GET /api/devices/{id}/interfaces（fake netconf 合成回读）
  await expect(page.locator(`select[name="sdn_access_interface"] option[value="${ifIndex}"]`)).toHaveCount(1)
  await page.locator('select[name="sdn_access_interface"]').selectOption(ifIndex)
  await page.getByLabel('期望主机 IP').fill(host)
  await page.getByRole('button', { name: '预览变更' }).click()
  await expect(page.getByText('可以安全执行')).toBeVisible()
  await page.getByRole('button', { name: '确认并下发' }).click()
  await expect(page.getByText('配置已下发，等待接线验证')).toBeVisible()
  await page.getByRole('button', { name: /关闭并跟踪/ }).click()
}

function opRow(page, host) {
  return page.locator('.operation-table').getByRole('button', { name: new RegExp(host) })
}

test('真实栈：接入故事 → PULSE 诚实展示执行记录未由设备验证 → STRATA 同一上下文', async ({ page }) => {
  await openWorkbench(page)
  await runAccessStory(page, { ifIndex: '10', ifaceName: 'GigabitEthernet1/0/10', host: '10.1.0.2' })

  // 持久化 operation 出现在活动表（真实 access-overview 回读）
  const row = opRow(page, '10.1.0.2')
  await expect(row).toBeVisible()
  await row.click()

  // PULSE：intent / scope / safety boundary（真实 scope_summary：if/svc/host）
  await expect(page.getByText('一次操作的完整生命线')).toBeVisible()
  await expect(page.locator('.intent-ribbon')).toContainText(`让 10.1.0.2 接入当前 VPC`)
  await expect(page.locator('.intent-ribbon')).toContainText('GigabitEthernet1/0/10')
  await expect(page.locator('.intent-ribbon')).toContainText('仅本次接入口')

  // 逐单元 truth kind：执行记录成功，但无设备回读 → 诚实显示“未由设备验证”
  await expect(page.locator('.timeline')).toContainText('执行记录')
  await expect(page.locator('.timeline')).toContainText('配置执行已记录，但尚未由设备回读验证。')
  await expect(page.locator('.pulse-view .status-chip')).not.toContainText(/已验证|已回读/)

  // STRATA：同一上下文（同一 VPC / 租户 / 设备承载）
  await page.getByRole('button', { name: /STRATA/ }).click()
  await expect(page.getByText('从业务目标深入到设备承载')).toBeVisible()
  await expect(page.locator('.strata-view')).toContainText('VNI 10001 · vsi-stack')
  await expect(page.locator('.strata-view')).toContainText(LEAF)
  await expect(page.locator('.strata-view')).toContainText(VPC)
  await expect(page.locator('.strata-view')).toContainText(`${TENANT} · 10.1.0.0/24`)
})

test('真实栈：验证证据不足 → 保持 unknown + ambiguous_claims（不得冒充设备验证）', async ({ page, request }) => {
  await openWorkbench(page)
  await runAccessStory(page, { ifIndex: '11', ifaceName: 'GigabitEthernet1/0/11', host: '10.1.0.3' })

  const row = opRow(page, '10.1.0.3')
  await expect(row).toBeVisible()
  const opIdText = await row.locator('.operation-id').textContent()
  const opId = (opIdText || '').replace('#', '').trim()
  expect(opId).not.toBe('')
  await row.click()

  await expect(page.getByText('一次操作的完整生命线')).toBeVisible()
  await expect(page.locator('.timeline')).toContainText('执行记录')

  // 让验证采集“证据不足”（后端 fake 按控制文件返回 insufficient）
  writeFileSync(join(STACK_QA_DIR, 'collector-mode'), 'insufficient')

  // 限定 PULSE 动作区（aside 检查器对同一 operation 也有同文案按钮）
  await page.locator('.pulse-view').getByRole('button', { name: '完成接线并验证' }).click()

  // 诚实状态：operation 保持 unknown（证据不足 ≠ 失败 ≠ 已验证）
  await expect(page.locator('.pulse-view .status-chip')).toContainText('未知')
  await expect(page.locator('.pulse-view').getByRole('button', { name: '核对真实状态' })).toBeVisible()
  await expect(page.locator('.pulse-view .status-chip')).not.toContainText(/已验证|已回读/)

  // 执行记录单元仍然保留（执行成功不等于设备已验证）
  await expect(page.locator('.timeline')).toContainText('执行记录')

  // 持久化 operation 的 safety_boundary 标注 ambiguous_claims（真实 API 读回，非 mock）
  const res = await request.get(`/api/sdn/operations/${opId}`)
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  expect(body.success).toBe(true)
  expect(body.data.explanation.safety_boundary.ambiguous_claims).toBe(true)
  expect(body.data.status).toBe('unknown')
})
