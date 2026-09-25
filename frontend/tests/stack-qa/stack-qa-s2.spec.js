// S2-018 真实应用栈隔离联调 spec（S2 用户故事验收）
//
// 与 S1（stack-qa.spec.js）同一通道：全程【真实 API 请求】——vite dev 代理到
// 真实 FastAPI（隔离 SQLite，alembic 空库 upgrade head），无任何 page.route mock；
// 设备 I/O 由后端进程内边界 fake 承担（run_stack_qa.sh 事后断言 device-io.log）。
//
// 覆盖（seed 基线：Leaf-Stack targeted+aligned、Leaf-Spare 未覆盖、Access-QA 非 EVPN）：
//   1) STRATA 真实读取 state-projection：覆盖 1/2、逐 Leaf 分类、attention coverage_gap
//      （不把覆盖缺口显示成漂移）、非 EVPN 不进 scope 分母。
//   2) 从未覆盖 Leaf 打开范围例外：真实 PUT maintenance_pause + reason + 未来到期；
//      刷新后仍 not_targeted、exception active、active_exception+1、
//      attention coverage_gap → coverage_deferred；无 deployment/binding/snapshot
//      新增、fake device-I/O 日志无新增调用。
//   3) 真实 DELETE 清除例外：刷新后恢复 coverage_gap、例外行删除、父对象与历史不受影响。
//   4) 构造 targeted Leaf 的真实持久化漂移快照（fake 采集 drifted → 真实 API sync 落库）；
//      即使给该 Leaf 设置 active maintenance exception，attention 仍保留
//      confirmed_drift blocking 并携带 exception，不被 deferred 吞掉。
//   5) 浏览器层固定文案：「不下发配置、不隐藏漂移」与「不代表根因、不会自动修复」。
import { test, expect } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const STACK_QA_DIR = process.env.STACK_QA_DIR || '/tmp/stack-qa'

async function openWorkbench(page) {
  await page.goto('/#/sdn-vpc', { waitUntil: 'networkidle' })
  await expect(page.locator('.next-workbench')).toBeVisible()
  await expect(page.getByText('stack-vpc').first()).toBeVisible()
}

async function openStrata(page) {
  await page.getByRole('button', { name: /STRATA/ }).click()
  await expect(page.getByText('从业务目标深入到设备承载')).toBeVisible()
}

async function projection(request, vpcId) {
  const res = await request.get(`/api/sdn/vpcs/${vpcId}/state-projection`)
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  expect(body.success).toBe(true)
  return body.data
}

async function vpcIdOf(request) {
  const res = await request.get('/api/sdn/vpcs')
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  const vpc = body.data.vpcs.find((v) => v.name === 'stack-vpc')
  expect(vpc).toBeTruthy()
  return vpc.id
}

function ioLines() {
  try {
    return readFileSync(join(STACK_QA_DIR, 'device-io.log'), 'utf-8')
      .split('\n').filter(Boolean).length
  } catch {
    return 0
  }
}

test('S2 真实栈：STRATA 覆盖 1/2、逐 Leaf 分类、attention coverage_gap（不当漂移）', async ({ page, request }) => {
  await openWorkbench(page)
  await openStrata(page)
  const strata = page.locator('.strata-view')

  // 覆盖 1/2（真实 state-projection 汇总）
  await expect(strata.locator('.scope-coverage')).toContainText('当前覆盖 1 / 2 台 EVPN Leaf')

  // 逐 Leaf 分类：targeted / not_targeted；非 EVPN 不进 scope 分母
  await expect(strata.locator('.scope-member-list')).toContainText('Leaf-Stack')
  await expect(strata.locator('.scope-member-list')).toContainText('当前覆盖')
  await expect(strata.locator('.scope-member-list')).toContainText('Leaf-Spare')
  await expect(strata.locator('.scope-member-list')).toContainText('尚未纳入')
  await expect(strata.locator('.scope-member-list')).not.toContainText('Access-QA')
  await expect(strata).toContainText('1 台非 EVPN 设备已排除，不计入结果。')

  // attention：coverage_gap 存在且不显示成 drift
  await expect(strata.locator('.attention-panel')).toBeVisible()
  await expect(strata.locator('.attention-panel')).toContainText('需要关注')
  await expect(strata.locator('.attention-panel')).toContainText('存在覆盖缺口')
  await expect(strata.locator('.attention-panel')).not.toContainText('已确认配置差异')
  // 浏览器层固定文案：关注队列不代表根因、不自动修复
  await expect(strata.locator('.attention-panel')).toContainText('不代表根因，也不会自动修复')

  // 真实 API 复核（与 UI 同一数据源，非 mock）
  const vpcId = await vpcIdOf(request)
  const proj = await projection(request, vpcId)
  expect(proj.scope.summary).toMatchObject({ eligible: 2, targeted: 1 })
  expect(proj.scope.members.some((m) => m.name === 'Access-QA')).toBe(false)
  const gap = proj.attention.items.find((i) => i.category === 'coverage_gap')
  expect(gap).toBeTruthy()
  expect(proj.scope.members.find((m) => m.device_id === gap.device_id).name).toBe('Leaf-Spare')
  expect(proj.attention.items.some((i) => i.category === 'confirmed_drift')).toBe(false)
})

test('S2 真实栈：范围例外 PUT/DELETE 闭环（不新增记录、无设备 I/O、attention 变 deferred）', async ({ page, request }) => {
  await openWorkbench(page)
  await openStrata(page)
  const strata = page.locator('.strata-view')

  const vpcId = await vpcIdOf(request)
  const proj0 = await projection(request, vpcId)
  const spare = proj0.scope.members.find((m) => m.name === 'Leaf-Spare')
  expect(spare).toBeTruthy()
  const spareId = spare.device_id
  expect(spare.classification).toBe('not_targeted')
  expect(spare.record_sources).toMatchObject({ deployment: { count: 0 }, binding: { count: 0 }, snapshot: { count: 0 } })
  const io0 = ioLines()
  const dep0 = (await (await request.get(`/api/sdn/deployments?vpc_id=${vpcId}`)).json()).data.total
  const bind0 = (await (await request.get(`/api/sdn/port-bindings?vpc_id=${vpcId}`)).json()).data.total

  // 从未覆盖 Leaf 打开范围例外 → 真实 PUT（类型/原因/未来到期）
  await strata.locator('.scope-member', { hasText: 'Leaf-Spare' }).click()
  const modal = page.locator('.scope-exception-modal')
  await expect(modal).toBeVisible()
  // 浏览器层固定文案：不下发配置、不隐藏漂移
  await expect(modal).toContainText('此记录只补充业务背景，不会向设备下发配置，也不会隐藏漂移或改变覆盖事实。')
  await modal.locator('select[name="scope_exception_type"]').selectOption('maintenance_pause')
  await modal.locator('textarea[name="scope_exception_reason"]').fill('维护窗口 09-20 至 09-21')
  const future = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 16)
  await modal.locator('input[name="scope_exception_expiry"]').fill(future)
  await modal.getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.notice.success')).toContainText('范围例外已保存')

  // 刷新后：仍 not_targeted、exception active、active_exception+1、attention → coverage_deferred
  const proj1 = await projection(request, vpcId)
  const spare1 = proj1.scope.members.find((m) => m.device_id === spareId)
  expect(spare1.classification).toBe('not_targeted') // 保留原分类
  expect(spare1.exception).toBeTruthy()
  expect(spare1.exception.state).toBe('active')
  expect(spare1.exception.exception_type).toBe('maintenance_pause')
  expect(proj1.scope.summary.active_exception).toBe(1)
  expect(proj1.attention.items.find((i) => i.device_id === spareId && i.category === 'coverage_deferred')).toBeTruthy()
  expect(proj1.attention.items.find((i) => i.device_id === spareId && i.category === 'coverage_gap')).toBeUndefined()
  // UI 同步：成员徽标、有效例外计数、attention 项
  await expect(strata.locator('.scope-member', { hasText: 'Leaf-Spare' })).toContainText('维护暂停')
  await expect(strata.locator('.scope-coverage')).toContainText('1 条有效例外')
  await expect(strata.locator('.attention-panel')).toContainText('覆盖已按例外暂缓')
  await expect(strata.locator('.attention-panel')).not.toContainText('存在覆盖缺口')

  // 证明无 deployment/binding/snapshot 新增、fake device-I/O 无新增调用
  expect((await (await request.get(`/api/sdn/deployments?vpc_id=${vpcId}`)).json()).data.total).toBe(dep0)
  expect((await (await request.get(`/api/sdn/port-bindings?vpc_id=${vpcId}`)).json()).data.total).toBe(bind0)
  const spare1sources = (await projection(request, vpcId)).scope.members.find((m) => m.device_id === spareId).record_sources
  expect(spare1sources).toMatchObject({ deployment: { count: 0 }, binding: { count: 0 }, snapshot: { count: 0 } })
  expect(ioLines()).toBe(io0)

  // 真实 DELETE 清除例外
  await strata.locator('.scope-member', { hasText: 'Leaf-Spare' }).click()
  await expect(page.locator('.scope-exception-modal')).toBeVisible()
  await page.locator('.scope-exception-modal').getByRole('button', { name: '清除例外' }).click()
  await expect(page.locator('.notice.success')).toContainText('范围例外已清除')

  // 刷新后：恢复 coverage_gap、例外行删除、父对象与历史不受影响
  const proj2 = await projection(request, vpcId)
  const spare2 = proj2.scope.members.find((m) => m.device_id === spareId)
  expect(spare2.exception).toBeNull()
  expect(spare2.classification).toBe('not_targeted')
  expect(proj2.scope.summary.active_exception).toBe(0)
  expect(proj2.attention.items.find((i) => i.device_id === spareId && i.category === 'coverage_gap')).toBeTruthy()
  const exc = (await (await request.get(`/api/sdn/vpcs/${vpcId}/scope-exceptions`)).json()).data.exceptions
  expect(exc).toHaveLength(0)
  expect((await (await request.get(`/api/sdn/deployments?vpc_id=${vpcId}`)).json()).data.total).toBe(dep0)
  expect((await (await request.get(`/api/sdn/port-bindings?vpc_id=${vpcId}`)).json()).data.total).toBe(bind0)
  expect(ioLines()).toBe(io0)
  await expect(strata.locator('.attention-panel')).toContainText('存在覆盖缺口')
  await expect(strata.locator('.scope-member', { hasText: 'Leaf-Spare' })).not.toContainText('维护暂停')
})

test('S2 真实栈：targeted Leaf 漂移 + active 例外 → attention 仍 confirmed_drift blocking 且携带例外', async ({ page, request }) => {
  await openWorkbench(page)
  await openStrata(page)
  const strata = page.locator('.strata-view')

  const vpcId = await vpcIdOf(request)
  const proj0 = await projection(request, vpcId)
  const stack = proj0.scope.members.find((m) => m.name === 'Leaf-Stack')
  expect(stack).toBeTruthy()
  const stackId = stack.device_id
  expect(stack.classification).toBe('targeted')

  // 构造 targeted Leaf 的真实持久化漂移快照：fake 采集 drifted → 真实 API sync 落库
  writeFileSync(join(STACK_QA_DIR, 'collector-mode'), 'drifted')
  await strata
    .locator('.projection-card', { hasText: 'Leaf-Stack' })
    .locator('button[title="重新采集此设备的状态证据"]')
    .click()
  await expect(strata.locator('.projection-card', { hasText: 'Leaf-Stack' })).toContainText('存在差异')

  const proj1 = await projection(request, vpcId)
  const leaf1 = proj1.leaves.find((l) => l.device_id === stackId)
  expect(leaf1).toBeTruthy()
  expect(leaf1.aggregate).toBe('drifted')
  expect(proj1.attention.items.find((i) => i.device_id === stackId && i.category === 'confirmed_drift')).toBeTruthy()

  // 给该 Leaf 设置 active maintenance 例外（真实 PUT）
  await strata.locator('.scope-member', { hasText: 'Leaf-Stack' }).click()
  const modal = page.locator('.scope-exception-modal')
  await expect(modal).toBeVisible()
  await modal.locator('select[name="scope_exception_type"]').selectOption('maintenance_pause')
  await modal.locator('textarea[name="scope_exception_reason"]').fill('维护窗口内允许漂移观察')
  await modal.getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.notice.success')).toContainText('范围例外已保存')

  // attention 仍保留 confirmed_drift blocking 并携带 exception，不被 deferred 吞掉
  const proj2 = await projection(request, vpcId)
  const drift2 = proj2.attention.items.find((i) => i.device_id === stackId && i.category === 'confirmed_drift')
  expect(drift2).toBeTruthy()
  expect(drift2.severity).toBe('blocking')
  expect(drift2.exception).toBeTruthy()
  expect(drift2.exception.state).toBe('active')
  expect(proj2.attention.items.find((i) => i.device_id === stackId && i.category === 'coverage_deferred')).toBeUndefined()
  expect(proj2.leaves.find((l) => l.device_id === stackId).aggregate).toBe('drifted')
  // UI：优先项保留 + 成员携带例外徽标 + 边界文案
  await expect(strata.locator('.attention-panel')).toContainText('已确认配置差异')
  await expect(strata.locator('.attention-panel')).toContainText('不代表根因，也不会自动修复')
  await expect(strata.locator('.scope-member', { hasText: 'Leaf-Stack' })).toContainText('维护暂停')

  // 清理：恢复 fresh 并重新采集对齐证据，避免影响同容器中按文件顺序运行的 S1 spec
  // （S1 接入故事的 predeploy 证明需要 Leaf-Stack 最新快照为对齐状态）
  writeFileSync(join(STACK_QA_DIR, 'collector-mode'), 'fresh')
  await strata
    .locator('.projection-card', { hasText: 'Leaf-Stack' })
    .locator('button[title="重新采集此设备的状态证据"]')
    .click()
  await expect(strata.locator('.projection-card', { hasText: 'Leaf-Stack' })).toContainText('一致')
  const proj3 = await projection(request, vpcId)
  expect(proj3.leaves.find((l) => l.device_id === stackId).aggregate).toBe('aligned')

  // 清掉本故事创建的业务上下文，确保同一容器内后续 spec 也从 seed 基线开始。
  const clear = await request.delete(`/api/sdn/vpcs/${vpcId}/devices/${stackId}/scope-exception`)
  expect(clear.ok()).toBeTruthy()
  const proj4 = await projection(request, vpcId)
  expect(proj4.scope.members.find((m) => m.device_id === stackId).exception).toBeNull()
})
