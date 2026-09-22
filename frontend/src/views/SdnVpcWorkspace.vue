<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { deviceApi, interfaceApi, sdnApi } from '../api/index.js'

const { t } = useI18n()
const isPreview = import.meta.env.VITE_NEXT_DEMO === 'true' || globalThis.location?.port === '5174'
const loading = ref(true)
const contextLoading = ref(false)
const busy = ref('')
const error = ref('')
const message = ref('')
const tenants = ref([])
const vpcs = ref([])
const devices = ref([])
const overview = ref({ bindings: [], operations: [], latest_validation: [], observations: [] })
const stateProjection = ref({ leaves: [], excluded: [], aggregate: 'unknown' })
const selectedVpcId = ref(null)
const selectedObject = ref(null)
const inspectorTab = ref('summary')
const workspaceMode = ref('atlas')
const projectionFilter = ref('all')
const projectionHistory = ref({})
const historyOpenDeviceId = ref(null)

const accessOpen = ref(false)
const accessStep = ref('form')
const accessInterfaces = ref([])
const accessForm = ref({ device_id: '', if_index: '', interface_name: '', service_instance: 3200, expected_host_ip: '' })
const accessPlan = ref(null)
const currentOperation = ref(null)

const resourcesOpen = ref(false)
const tenantForm = ref({ name: '', description: '' })
const vpcForm = ref({ name: '', tenant_id: '', cidr: '192.168.10.0/24' })
const fabricDeviceId = ref('')
const fabricAutoApply = ref(false)

const selectedVpc = computed(() => vpcs.value.find((item) => item.id === Number(selectedVpcId.value)) || null)
const leafs = computed(() => devices.value.filter((item) => String(item.sdn_role || '').toLowerCase() === 'evpn_leaf'))
const bindings = computed(() => overview.value.bindings || [])
const operations = computed(() => overview.value.operations || [])
const observations = computed(() => overview.value.observations || [])
const previewBlocked = computed(() => (accessPlan.value?.blocking || []).length > 0)
const selectedLeaf = computed(() => leafs.value.find((item) => item.id === Number(accessForm.value.device_id)) || null)
const focusedOperation = computed(() => {
  if (selectedObject.value?.kind === 'operation') return selectedObject.value.value
  return currentOperation.value
})
const focusedAttempts = computed(() => focusedOperation.value?.attempts || [])
const focusedUnits = computed(() => focusedAttempts.value.flatMap((attempt) =>
  (attempt.units || []).map((unit) => ({ ...unit, attempt_kind: attempt.kind, attempt_status: attempt.status }))
))
const operationImpact = computed(() => focusedOperation.value?.explanation?.impact || null)
const projectionCounts = computed(() => {
  const counts = { all: 0, aligned: 0, attention: 0, unknown: 0 }
  for (const leaf of stateProjection.value.leaves || []) {
    counts.all += 1
    if (leaf.aggregate === 'aligned') counts.aligned += 1
    else if (['drifted', 'stale'].includes(leaf.aggregate)) counts.attention += 1
    else counts.unknown += 1
  }
  return counts
})
const filteredProjectionLeaves = computed(() => {
  const leaves = stateProjection.value.leaves || []
  if (projectionFilter.value === 'aligned') return leaves.filter((leaf) => leaf.aggregate === 'aligned')
  if (projectionFilter.value === 'attention') return leaves.filter((leaf) => ['drifted', 'stale'].includes(leaf.aggregate))
  if (projectionFilter.value === 'unknown') return leaves.filter((leaf) => !['aligned', 'drifted', 'stale'].includes(leaf.aggregate))
  return leaves
})
function statusMeta(status) {
  const key = String(status || 'unknown').toLowerCase()
  const good = ['active', 'success', 'succeeded', 'validated', 'online', 'ready', 'aligned']
  const warn = ['planned', 'pending', 'awaiting_wiring', 'awaiting_validation', 'expanding', 'applying', 'validating', 'reconciling', 'stale']
  const bad = ['failed', 'failed_known', 'degraded', 'offline', 'drifted']
  const tone = good.includes(key) ? 'good' : warn.includes(key) ? 'warn' : bad.includes(key) ? 'bad' : 'mute'
  const translated = t(`sdn.next.status.${key}`)
  return { tone, label: translated === `sdn.next.status.${key}` ? (status || t('sdn.next.status.unknown')) : translated }
}

function deviceById(id) { return devices.value.find((item) => item.id === Number(id)) || null }
function bindingForLeaf(id) { return bindings.value.filter((item) => item.device_id === id && item.status !== 'unbound') }
function formatTime(value) {
  if (!value) return t('common.dash')
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
function translatedCode(group, code, fallback = '') {
  if (!code) return fallback
  const key = `sdn.next.${group}.${code}`
  const value = t(key)
  return value === key ? (fallback || code) : value
}
function operationIntent(operation) {
  const code = operation?.explanation?.intent
  if (code === 'access_bind') return t('sdn.next.intent_connect', { host: operation.expected_host_ip || t('sdn.next.terminal') })
  return translatedCode('intent_code', code, operation?.operation_type || t('sdn.next.terminal_access'))
}
function unitExplanation(unit) {
  const explanation = unit?.explanation
  if (!explanation || explanation.unavailable) return unit?.evidence?.summary || t('sdn.next.unit_evidence_pending')
  return translatedCode('evidence_category', explanation.category, explanation.statement || t('sdn.next.unit_evidence_pending'))
}
function evidenceSource(unit) {
  const source = unit?.explanation?.source || unit?.evidence?.source || unit?.attempt_kind
  return translatedCode('evidence_source', source, source || t('sdn.next.unknown'))
}
function evidenceScope(unit) {
  const scope = unit?.explanation?.scope || unit?.evidence?.scope
  if (!scope) return selectedVpc.value?.name || t('sdn.next.unknown')
  if (typeof scope === 'string') return scope
  return [scope.vpc_name, scope.device_name, scope.interface_name, scope.expected_host_ip].filter(Boolean).join(' / ') || selectedVpc.value?.name || t('sdn.next.unknown')
}
function truthLabel(unit) {
  return translatedCode('truth_kind', unit?.explanation?.truth_kind, statusMeta(unit?.state).label)
}
function impactNodeLabel(node) {
  return node?.label || node?.interface_name || (node?.id != null ? String(node.id) : t('sdn.next.unknown'))
}
function impactNodeType(node) {
  return translatedCode('impact_node', node?.kind, node?.kind || t('sdn.next.unknown'))
}
function impactRelation(nodes, index) {
  if (index < 1) return null
  const previous = nodes[index - 1]
  const current = nodes[index]
  return operationImpact.value?.relations?.find((relation) =>
    relation.from_kind === previous.kind &&
    relation.from_id === previous.id &&
    relation.to_kind === current.kind &&
    relation.to_id === current.id
  ) || null
}
function clearNotice() { error.value = ''; message.value = '' }
function projectionMeta(status) {
  const meta = statusMeta(status)
  return { ...meta, label: translatedCode('projection_status', status, meta.label) }
}
function factValue(value) {
  if (value === true) return t('sdn.next.present')
  if (value === false) return t('sdn.next.absent')
  return t('sdn.next.not_observed')
}
function projectionDimensions(leaf) {
  const desired = leaf?.desired || {}
  const observed = leaf?.observed?.facts || {}
  const diff = leaf?.diff || {}
  const dimensions = [
    { key: 'vsi', label: 'VSI', desired: factValue(desired.vsi?.present), observed: factValue(observed.vsi_exists), result: diff.vsi },
    { key: 'vsi_up', label: t('sdn.next.vsi_runtime'), desired: desired.vsi_up?.expected ? t('sdn.next.up_required') : t('sdn.next.not_required'), observed: factValue(observed.vsi_up), result: diff.vsi_up },
    { key: 'vsi_interface', label: t('sdn.next.gateway_interface'), desired: factValue(desired.vsi_interface?.present), observed: factValue(observed.vsi_interface_exists), result: diff.vsi_interface },
    { key: 'l3_vni', label: 'L3VNI', desired: factValue(desired.l3_vni?.present), observed: factValue(observed.l3_vni_present), result: diff.l3_vni },
  ]
  for (const binding of diff.port_bindings || []) {
    const target = (desired.port_bindings || []).find((item) => item.binding_id === binding.binding_id) || {}
    if (binding.service_instance?.status !== 'not_applicable') dimensions.push({
      key: `si-${binding.binding_id}`, label: target.interface_name || binding.interface_name,
      desired: `SI ${target.service_instance}`, observed: binding.service_instance?.observed?.length ? `SI ${binding.service_instance.observed.join(', ')}` : t('sdn.next.not_observed'), result: binding.service_instance,
    })
    if (binding.access_vlan?.status !== 'not_applicable') dimensions.push({
      key: `vlan-${binding.binding_id}`, label: target.interface_name || binding.interface_name,
      desired: `VLAN ${target.access_vlan}`, observed: binding.access_vlan?.observed?.length ? `VLAN ${binding.access_vlan.observed.join(', ')}` : t('sdn.next.not_observed'), result: binding.access_vlan,
    })
  }
  return dimensions
}
function selectProjectionDimension(projection, dimension) {
  selectObject('projection', {
    ...dimension,
    device_id: projection.device_id,
    device_name: projection.device_name,
    device_host: projection.device_host,
    observed_at: projection.observed?.collected_at || null,
  })
}
function projectionSourceLabel(source) {
  if (!source) return t('sdn.next.no_source')
  if (source.kind === 'deployment') return t('sdn.next.source_deployment', { id: source.deployment_id ?? '—', version: source.version ?? '—' })
  if (source.kind === 'binding') return t('sdn.next.source_binding', { id: source.binding_id ?? '—', version: source.version ?? '—' })
  if (source.kind === 'snapshot') return t('sdn.next.source_snapshot', { id: source.snapshot_id ?? '—' })
  if (source.kind === 'operable_binding_count') return t('sdn.next.source_binding_count', { count: source.count ?? 0 })
  return source.kind || t('sdn.next.unknown')
}
function correlationLabel(correlation) {
  if (!correlation) return t('sdn.next.correlation_unlinked')
  return translatedCode('correlation_status', correlation.status, correlation.status)
}
function historyPoints(deviceId) {
  return projectionHistory.value[deviceId]?.points || []
}
async function toggleProjectionHistory(deviceId) {
  if (historyOpenDeviceId.value === deviceId) {
    historyOpenDeviceId.value = null
    return
  }
  historyOpenDeviceId.value = deviceId
  if (projectionHistory.value[deviceId]) return
  busy.value = `history-${deviceId}`
  const result = await sdnApi.stateProjectionHistory(selectedVpcId.value, deviceId, 10)
  busy.value = ''
  if (!result.success) {
    historyOpenDeviceId.value = null
    return void (error.value = result.error || t('sdn.next.history_failed'))
  }
  projectionHistory.value = {
    ...projectionHistory.value,
    [deviceId]: result.data?.timelines?.[0] || { device_id: deviceId, points: [] },
  }
}
function selectHistoryPoint(projection, point) {
  selectObject('history', {
    ...point,
    device_id: projection.device_id,
    device_name: projection.device_name,
    device_host: projection.device_host,
  })
}

async function loadBase() {
  loading.value = true
  clearNotice()
  const [tenantResult, vpcResult, deviceResult] = await Promise.all([sdnApi.listTenants(), sdnApi.listVpcs(), deviceApi.list()])
  loading.value = false
  if (!tenantResult.success || !vpcResult.success || !deviceResult.success) {
    error.value = tenantResult.error || vpcResult.error || deviceResult.error || t('sdn.load_failed')
    return
  }
  tenants.value = tenantResult.data?.tenants || []
  vpcs.value = vpcResult.data?.vpcs || []
  devices.value = deviceResult.data || []
  if (!selectedVpcId.value && vpcs.value.length) selectedVpcId.value = vpcs.value[0].id
  if (!vpcForm.value.tenant_id && tenants.value.length) vpcForm.value.tenant_id = tenants.value[0].id
}

async function loadContext() {
  if (!selectedVpcId.value) return
  contextLoading.value = true
  const [result, projectionResult] = await Promise.all([
    sdnApi.accessOverview(selectedVpcId.value),
    sdnApi.stateProjection(selectedVpcId.value),
  ])
  contextLoading.value = false
  if (!result.success) return void (error.value = result.error || t('sdn.next.context_failed'))
  overview.value = result.data || { bindings: [], operations: [], latest_validation: [], observations: [] }
  stateProjection.value = projectionResult.success
    ? (projectionResult.data || { leaves: [], excluded: [], aggregate: 'unknown' })
    : { leaves: [], excluded: [], aggregate: 'unknown' }
}

async function refreshAll() { await loadBase(); await loadContext(); message.value = t('sdn.next.refreshed') }
function selectObject(kind, value) { selectedObject.value = { kind, value }; inspectorTab.value = 'summary' }

async function refreshProjectionLeaf(deviceId) {
  busy.value = `projection-${deviceId}`
  clearNotice()
  const result = await sdnApi.syncValidation(selectedVpcId.value, deviceId, true)
  if (!result.success) {
    busy.value = ''
    return void (error.value = result.error || t('sdn.next.projection_refresh_failed'))
  }
  await loadContext()
  const nextHistory = { ...projectionHistory.value }
  delete nextHistory[deviceId]
  projectionHistory.value = nextHistory
  if (historyOpenDeviceId.value === deviceId) {
    const historyResult = await sdnApi.stateProjectionHistory(selectedVpcId.value, deviceId, 10)
    if (historyResult.success) {
      projectionHistory.value = {
        ...projectionHistory.value,
        [deviceId]: historyResult.data?.timelines?.[0] || { device_id: deviceId, points: [] },
      }
    }
  }
  busy.value = ''
  message.value = t('sdn.next.projection_refreshed')
}

async function openOperation(summary) {
  busy.value = `operation-${summary.operation_id}`
  const result = await sdnApi.getOperation(summary.operation_id)
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.next.action_failed'))
  currentOperation.value = result.data
  selectObject('operation', result.data)
  workspaceMode.value = 'pulse'
}

async function loadAccessInterfaces() {
  accessInterfaces.value = []
  if (!accessForm.value.device_id) return
  const result = await interfaceApi.list(accessForm.value.device_id)
  if (result.success) accessInterfaces.value = result.data || []
}

async function openAccess() {
  clearNotice()
  accessStep.value = 'form'
  accessPlan.value = null
  currentOperation.value = null
  accessForm.value = { device_id: leafs.value[0]?.id || '', if_index: '', interface_name: '', service_instance: 3200, expected_host_ip: '' }
  accessOpen.value = true
  await loadAccessInterfaces()
}

function chooseInterface(event) {
  const item = accessInterfaces.value.find((entry) => String(entry.if_index) === event.target.value)
  if (!item) return
  accessForm.value.if_index = item.if_index
  accessForm.value.interface_name = item.name || item.interface_name || ''
}

function accessPayload() {
  return {
    device_id: Number(accessForm.value.device_id), if_index: Number(accessForm.value.if_index),
    interface_name: accessForm.value.interface_name.trim(), access_vlan: null,
    service_instance: Number(accessForm.value.service_instance),
    expected_host_ip: accessForm.value.expected_host_ip.trim() || null, mode: 'l2',
  }
}

function makeIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `access-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function previewAccess() {
  busy.value = 'preview'; clearNotice()
  const result = await sdnApi.previewAccess(selectedVpc.value.id, accessPayload())
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.next.preview_failed'))
  accessPlan.value = result.data
  accessStep.value = 'preview'
}

async function executeAccess() {
  if (!accessPlan.value || previewBlocked.value) return
  busy.value = 'execute'
  const result = await sdnApi.executeAccess(selectedVpc.value.id, {
    ...accessPayload(), plan_id: accessPlan.value.plan_id,
    idempotency_key: makeIdempotencyKey(), auto_apply: true,
  })
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.next.execute_failed'))
  currentOperation.value = result.data
  accessStep.value = 'operation'
  await loadContext()
}

async function runOperation(action) {
  const operation = currentOperation.value || (selectedObject.value?.kind === 'operation' ? selectedObject.value.value : null)
  if (!operation) return
  busy.value = action
  let result
  if (action === 'complete') result = await sdnApi.completeOperation(operation.operation_id, { force_validation: true })
  if (action === 'reconcile') result = await sdnApi.reconcileOperation(operation.operation_id)
  if (action === 'withdraw') result = await sdnApi.withdrawOperation(operation.operation_id, t('sdn.next.withdraw_reason'))
  busy.value = ''
  if (!result?.success) return void (error.value = result?.error || t('sdn.next.action_failed'))
  message.value = t(`sdn.next.${action}_submitted`)
  const detail = await sdnApi.getOperation(operation.operation_id)
  if (detail.success) {
    currentOperation.value = detail.data
    if (selectedObject.value?.kind === 'operation') selectedObject.value.value = detail.data
  }
  await loadContext()
}

async function createTenant() {
  if (!tenantForm.value.name.trim()) return
  busy.value = 'tenant'
  const result = await sdnApi.createTenant({ name: tenantForm.value.name.trim(), description: tenantForm.value.description.trim() || null })
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.msg_failed'))
  tenantForm.value = { name: '', description: '' }; message.value = t('sdn.tenant_created'); await loadBase()
}

async function createVpc() {
  if (!vpcForm.value.name.trim() || !vpcForm.value.tenant_id || !vpcForm.value.cidr.trim()) return
  busy.value = 'vpc'
  const result = await sdnApi.createVpc({ name: vpcForm.value.name.trim(), tenant_id: Number(vpcForm.value.tenant_id), cidr: vpcForm.value.cidr.trim() })
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.msg_failed'))
  selectedVpcId.value = result.data?.id || selectedVpcId.value; vpcForm.value.name = ''; message.value = t('sdn.vpc_created'); await loadBase()
}

async function changeFabric(action) {
  if (!selectedVpc.value || !fabricDeviceId.value) return
  busy.value = `fabric-${action}`
  const payload = { device_ids: [Number(fabricDeviceId.value)], auto_apply: fabricAutoApply.value, include_port_bindings: true }
  const result = action === 'deploy' ? await sdnApi.deployVpc(selectedVpc.value.id, payload) : await sdnApi.withdrawVpc(selectedVpc.value.id, payload)
  busy.value = ''
  if (!result.success) return void (error.value = result.error || t('sdn.msg_failed'))
  message.value = t(fabricAutoApply.value ? `sdn.${action}_submitted` : `sdn.${action}_planned`)
}

const canComplete = (op) => ['awaiting_validation', 'degraded'].includes(op?.status)
const canReconcile = (op) => ['unknown', 'applying', 'validating', 'withdrawing', 'reconciling'].includes(op?.status)
const canWithdraw = (op) => !['withdrawn', 'withdrawing'].includes(op?.status)

watch(selectedVpcId, async () => {
  selectedObject.value = selectedVpc.value ? { kind: 'vpc', value: selectedVpc.value } : null
  projectionHistory.value = {}
  historyOpenDeviceId.value = null
  await loadContext()
})
watch(() => accessForm.value.device_id, loadAccessInterfaces)
onMounted(loadBase)
</script>

<template>
  <main class="next-workbench">
    <header class="workbench-bar">
      <div><p class="eyebrow">NEXT / {{ workspaceMode.toUpperCase() }}</p><h1>{{ t('sdn.next.title') }}</h1><p>{{ t('sdn.next.subtitle') }}</p></div>
      <div class="header-actions">
        <button class="icon-button" :title="t('sdn.refresh')" :disabled="loading" @click="refreshAll">↻</button>
        <button class="secondary" @click="resourcesOpen = true">{{ t('sdn.next.resource_tools') }}</button>
        <button class="primary" :disabled="!selectedVpc || !leafs.length" @click="openAccess">+ {{ t('sdn.next.connect_terminal') }}</button>
      </div>
    </header>
    <div v-if="isPreview" class="demo-banner"><strong>{{ t('sdn.next.demo_title') }}</strong><span>{{ t('sdn.next.demo_detail') }}</span></div>
    <nav class="perspective-switch" :aria-label="t('sdn.next.perspective')">
      <button :class="{ active: workspaceMode === 'atlas' }" @click="workspaceMode = 'atlas'">
        <span>ATLAS</span><small>{{ t('sdn.next.atlas_desc') }}</small>
      </button>
      <button :class="{ active: workspaceMode === 'pulse' }" @click="workspaceMode = 'pulse'">
        <span>PULSE</span><small>{{ t('sdn.next.pulse_desc') }}</small>
      </button>
      <button :class="{ active: workspaceMode === 'strata' }" @click="workspaceMode = 'strata'">
        <span>STRATA</span><small>{{ t('sdn.next.strata_desc') }}</small>
      </button>
    </nav>
    <p v-if="error" class="notice error">{{ error }}</p><p v-if="message" class="notice success">{{ message }}</p>

    <section v-if="loading" class="empty-state">{{ t('common.loading') }}</section>
    <section v-else class="workspace-grid">
      <aside class="scope-pane">
        <div class="section-heading"><div><span>01</span><h2>{{ t('sdn.next.business_scope') }}</h2></div><b>{{ vpcs.length }}</b></div>
        <button v-for="vpc in vpcs" :key="vpc.id" class="vpc-option" :class="{ selected: selectedVpcId === vpc.id }" @click="selectedVpcId = vpc.id">
          <span class="vpc-mark">{{ vpc.name.slice(0, 2).toUpperCase() }}</span><span class="vpc-copy"><strong>{{ vpc.name }}</strong><small>{{ vpc.cidr }}</small></span><span class="status-dot" :class="statusMeta(vpc.status).tone"></span>
        </button>
        <div v-if="!vpcs.length" class="pane-empty"><strong>{{ t('sdn.no_vpcs') }}</strong><button class="text-button" @click="resourcesOpen = true">{{ t('sdn.create_vpc') }}</button></div>
        <div class="legend"><span><i class="good"></i>{{ t('sdn.next.observed') }}</span><span><i class="warn"></i>{{ t('sdn.next.pending') }}</span><span><i></i>{{ t('sdn.next.unknown') }}</span></div>
      </aside>

      <section class="atlas-pane">
        <template v-if="selectedVpc">
          <div class="vpc-context">
            <div><p class="eyebrow">VPC CONTEXT</p><h2>{{ selectedVpc.name }}</h2><p>{{ selectedVpc.tenant_name }} · {{ selectedVpc.cidr }}</p></div>
            <div class="context-facts"><span><small>{{ t('sdn.next.gateway') }}</small><b>{{ selectedVpc.gateway_ip || '—' }}</b></span><span><small>VNI</small><b>{{ selectedVpc.vni }}</b></span><span><small>VSI</small><b>{{ selectedVpc.vsi_name }}</b></span><span class="status-chip" :class="statusMeta(selectedVpc.status).tone">{{ statusMeta(selectedVpc.status).label }}</span></div>
          </div>
          <div v-if="workspaceMode === 'atlas'" class="fabric-stage" :class="{ loading: contextLoading }">
            <div class="stage-label"><span>02</span>{{ t('sdn.next.access_map') }}</div>
            <div v-if="!leafs.length" class="empty-state compact">{{ t('sdn.no_evpn_targets') }}</div>
            <div v-else class="leaf-grid">
              <article v-for="leaf in leafs" :key="leaf.id" class="leaf-node" @click="selectObject('device', leaf)">
                <header><span class="device-glyph">L</span><span><strong>{{ leaf.name }}</strong><small>{{ leaf.host }}</small></span><i class="online-dot"></i></header>
                <div class="fabric-link"><span></span><b>EVPN</b><span></span></div>
                <button v-for="binding in bindingForLeaf(leaf.id)" :key="binding.id" class="port-node" @click.stop="selectObject('binding', binding)"><span class="port-icon"></span><span><strong>{{ binding.interface_name || `if_index ${binding.if_index}` }}</strong><small>{{ statusMeta(binding.status).label }}</small></span></button>
                <div v-if="!bindingForLeaf(leaf.id).length" class="no-binding">{{ t('sdn.next.no_binding_on_leaf') }}</div>
              </article>
            </div>
          </div>
          <section v-if="workspaceMode === 'atlas'" class="terminal-strip">
            <div class="section-heading inline"><div><span>03</span><h2>{{ t('sdn.next.terminals') }}</h2></div><b>{{ observations.length }}</b></div>
            <div v-if="observations.length" class="terminal-list">
              <button v-for="item in observations" :key="item.operation_id" @click="openOperation({ operation_id: item.operation_id })"><span class="host-glyph">H</span><span><strong>{{ item.expected_host_ip }}</strong><small>{{ deviceById(item.device_id)?.name || `#${item.device_id}` }}</small></span><span class="status-chip" :class="item.host_observed ? 'good' : 'mute'">{{ item.host_observed ? t('sdn.next.observed') : t('sdn.next.not_observed') }}</span></button>
            </div><p v-else class="quiet-copy">{{ t('sdn.next.no_host_evidence') }}</p>
          </section>
          <section v-if="workspaceMode === 'atlas'" class="pulse-panel">
            <div class="section-heading inline"><div><span>04</span><h2>{{ t('sdn.next.activity') }}</h2></div><b>{{ operations.length }}</b></div>
            <div class="operation-table"><button v-for="operation in operations" :key="operation.operation_id" @click="openOperation(operation)"><span class="operation-id">#{{ operation.operation_id }}</span><span><strong>{{ operation.expected_host_ip || t('sdn.next.terminal_access') }}</strong><small>{{ formatTime(operation.updated_at) }}</small></span><span class="status-chip" :class="statusMeta(operation.status).tone">{{ statusMeta(operation.status).label }}</span></button><p v-if="!operations.length" class="quiet-copy">{{ t('sdn.next.no_operations') }}</p></div>
          </section>

          <section v-if="workspaceMode === 'pulse'" class="perspective-panel pulse-view">
            <header class="perspective-heading"><div><p class="eyebrow">PULSE / OPERATION</p><h3>{{ t('sdn.next.pulse_title') }}</h3></div><span v-if="focusedOperation" class="status-chip large" :class="statusMeta(focusedOperation.status).tone">{{ statusMeta(focusedOperation.status).label }}</span></header>
            <div v-if="!focusedOperation" class="pulse-empty">
              <p>{{ t('sdn.next.pulse_empty') }}</p>
              <div class="operation-table"><button v-for="operation in operations" :key="operation.operation_id" @click="openOperation(operation)"><span class="operation-id">#{{ operation.operation_id }}</span><span><strong>{{ operation.expected_host_ip || t('sdn.next.terminal_access') }}</strong><small>{{ formatTime(operation.updated_at) }}</small></span><span class="status-chip" :class="statusMeta(operation.status).tone">{{ statusMeta(operation.status).label }}</span></button></div>
            </div>
            <template v-else>
              <div class="intent-ribbon">
                <span><small>{{ t('sdn.next.intent') }}</small><strong>{{ operationIntent(focusedOperation) }}</strong></span>
                <i></i><span><small>{{ t('sdn.next.scope') }}</small><strong>{{ focusedOperation.explanation?.scope_summary || deviceById(focusedOperation.device_id)?.name || `#${focusedOperation.device_id}` }}</strong></span>
                <i></i><span><small>{{ t('sdn.next.safety') }}</small><strong>{{ focusedOperation.explanation?.safety_boundary?.target_only === false ? t('sdn.next.shared_change') : t('sdn.next.scoped_change') }}</strong></span>
              </div>
              <section v-if="operationImpact && !operationImpact.unavailable && operationImpact.nodes?.length" class="impact-map">
                <header>
                  <span><small>{{ t('sdn.next.impact_title') }}</small><strong>{{ t('sdn.next.impact_subtitle') }}</strong></span>
                  <p>{{ t('sdn.next.impact_boundary') }}</p>
                </header>
                <div class="impact-chain">
                  <div v-for="(node, index) in operationImpact.nodes" :key="`${node.kind}-${node.id ?? index}`" class="impact-step">
                    <div v-if="index && impactRelation(operationImpact.nodes, index)" class="impact-link">
                      <span>{{ translatedCode('impact_relation', impactRelation(operationImpact.nodes, index)?.relation, impactRelation(operationImpact.nodes, index)?.relation) }}</span>
                      <i></i>
                    </div>
                    <article class="impact-node">
                      <b>{{ impactNodeType(node) }}</b>
                      <strong>{{ impactNodeLabel(node) }}</strong>
                      <small>{{ translatedCode('truth_kind', node.truth_kind, node.truth_kind) }} · {{ translatedCode('impact_source', node.source, node.source) }}</small>
                    </article>
                  </div>
                </div>
              </section>
              <div class="timeline" v-if="focusedUnits.length">
                <article v-for="(unit, index) in focusedUnits" :key="`${unit.attempt_kind}-${unit.unit_index}`" :class="statusMeta(unit.state).tone">
                  <div class="timeline-rail"><span>{{ index + 1 }}</span><i></i></div>
                  <div class="timeline-copy"><header><span><small>{{ unit.attempt_kind }}</small><strong>{{ unit.unit_name }}</strong></span><b>{{ truthLabel(unit) }}</b></header><p>{{ unitExplanation(unit) }}</p><footer><span>{{ formatTime(unit.explanation?.observed_at || unit.completed_at || unit.started_at) }}</span><button @click="selectObject('evidence', unit)">{{ t('sdn.next.inspect_evidence') }}</button></footer></div>
                </article>
              </div>
              <p v-else class="quiet-copy">{{ t('sdn.next.no_unit_evidence') }}</p>
              <div class="operation-actions pulse-actions"><button v-if="canComplete(focusedOperation)" class="primary" @click="runOperation('complete')">{{ t('sdn.next.verify_now') }}</button><button v-if="canReconcile(focusedOperation)" class="secondary" @click="runOperation('reconcile')">{{ t('sdn.next.reconcile') }}</button><button v-if="canWithdraw(focusedOperation)" class="danger-text" @click="runOperation('withdraw')">{{ t('sdn.next.withdraw_access') }}</button></div>
            </template>
          </section>

          <section v-if="workspaceMode === 'strata'" class="perspective-panel strata-view">
            <header class="perspective-heading"><div><p class="eyebrow">STRATA / STATE PROJECTION</p><h3>{{ t('sdn.next.strata_title') }}</h3></div><span class="status-chip large" :class="projectionMeta(stateProjection.aggregate).tone">{{ projectionMeta(stateProjection.aggregate).label }}</span></header>
            <div class="strata-intent">
              <span><small>{{ t('sdn.next.business_layer') }}</small><strong>{{ selectedVpc.name }}</strong><b>{{ selectedVpc.tenant_name }} · {{ selectedVpc.cidr }}</b></span>
              <i></i><span><small>{{ t('sdn.next.logic_layer') }}</small><strong>VNI {{ selectedVpc.vni }} · {{ selectedVpc.vsi_name }}</strong><b>{{ t('sdn.next.gateway') }} {{ selectedVpc.gateway_ip || '—' }}</b></span>
            </div>
            <div class="projection-filters" :aria-label="t('sdn.next.projection_filters')">
              <button v-for="filter in ['all', 'aligned', 'attention', 'unknown']" :key="filter" :class="{ active: projectionFilter === filter }" @click="projectionFilter = filter"><span>{{ t(`sdn.next.projection_filter.${filter}`) }}</span><b>{{ projectionCounts[filter] }}</b></button>
            </div>
            <div v-if="!stateProjection.leaves?.length" class="strata-empty"><strong>{{ t('sdn.next.no_projection') }}</strong><p>{{ t('sdn.next.no_projection_hint') }}</p></div>
            <div v-else-if="filteredProjectionLeaves.length" class="projection-grid">
              <article v-for="projection in filteredProjectionLeaves" :key="projection.device_id" class="projection-card" :class="`is-${projection.aggregate}`" @click="selectObject('device', deviceById(projection.device_id) || projection)">
                <header>
                  <span><small>{{ t('sdn.next.device_layer') }}</small><strong>{{ projection.device_name }}</strong><b>{{ projection.device_host }}</b></span>
                  <span class="projection-card-actions"><span class="status-chip" :class="projectionMeta(projection.aggregate).tone">{{ projectionMeta(projection.aggregate).label }}</span><button :title="t('sdn.next.refresh_device_evidence')" :disabled="busy === `projection-${projection.device_id}`" @click.stop="refreshProjectionLeaf(projection.device_id)">↻</button></span>
                </header>
                <div class="projection-evidence">
                  <span><small>{{ t('sdn.next.observed_at') }}</small><b>{{ projection.observed ? formatTime(projection.observed.collected_at) : t('sdn.next.no_evidence') }}</b></span>
                  <span><small>{{ t('sdn.next.access_ports') }}</small><b>{{ projection.desired?.port_bindings?.length || 0 }}</b></span>
                </div>
                <div class="projection-columns"><span>{{ t('sdn.next.desired_state') }}</span><span>{{ t('sdn.next.observed_state') }}</span><span>{{ t('sdn.next.comparison') }}</span></div>
                <button v-for="dimension in projectionDimensions(projection)" :key="dimension.key" type="button" class="projection-row" @click.stop="selectProjectionDimension(projection, dimension)">
                  <strong>{{ dimension.label }}</strong>
                  <span>{{ dimension.desired }}</span><span>{{ dimension.observed }}</span>
                  <b class="projection-result" :class="projectionMeta(dimension.result?.status).tone" :title="translatedCode('projection_reason', dimension.result?.reason_code, dimension.result?.reason_code)">{{ projectionMeta(dimension.result?.status).label }}</b>
                </button>
                <button type="button" class="history-toggle" :class="{ active: historyOpenDeviceId === projection.device_id }" :disabled="busy === `history-${projection.device_id}`" @click.stop="toggleProjectionHistory(projection.device_id)">
                  <span>{{ historyOpenDeviceId === projection.device_id ? t('sdn.next.hide_history') : t('sdn.next.show_history') }}</span><b>{{ historyOpenDeviceId === projection.device_id ? '−' : '+' }}</b>
                </button>
                <div v-if="historyOpenDeviceId === projection.device_id" class="history-panel" @click.stop>
                  <header><span><small>{{ t('sdn.next.history_title') }}</small><strong>{{ t('sdn.next.history_current_basis') }}</strong></span><b>{{ historyPoints(projection.device_id).length }}</b></header>
                  <div v-if="historyPoints(projection.device_id).length" class="history-track">
                    <button v-for="point in historyPoints(projection.device_id)" :key="point.snapshot_id" type="button" :class="`is-${point.aggregate}`" @click="selectHistoryPoint(projection, point)">
                      <i></i><span><strong>{{ formatTime(point.collected_at) }}</strong><small>#{{ point.snapshot_id }} · {{ point.validation_result || t('sdn.next.unknown') }}<template v-if="point.correlation?.status === 'linked'"> · {{ t('sdn.next.operation_ref', { id: point.correlation.operation_id }) }}</template></small></span><b :class="projectionMeta(point.aggregate).tone">{{ projectionMeta(point.aggregate).label }}</b>
                    </button>
                  </div>
                  <p v-else class="quiet-copy">{{ t('sdn.next.no_history') }}</p>
                </div>
              </article>
            </div>
            <div v-else class="strata-empty compact"><strong>{{ t('sdn.next.no_projection_matches') }}</strong></div>
            <p v-if="stateProjection.excluded?.length" class="projection-excluded">{{ t('sdn.next.excluded_devices', { count: stateProjection.excluded.length }) }}</p>
            <div class="truth-legend"><span><i class="desired"></i>{{ t('sdn.next.desired_state') }}</span><span><i class="observed"></i>{{ t('sdn.next.observed_state') }}</span><span><i class="inferred"></i>{{ t('sdn.next.comparison') }}</span></div>
          </section>
        </template><div v-else class="empty-state">{{ t('sdn.no_selected_vpc') }}</div>
      </section>

      <aside class="inspector-pane">
        <div class="section-heading"><div><span>05</span><h2>{{ t('sdn.next.inspector') }}</h2></div></div>
        <div v-if="!selectedObject" class="pane-empty"><strong>{{ t('sdn.next.select_object') }}</strong><p>{{ t('sdn.next.select_object_detail') }}</p></div>
        <template v-else>
          <div class="inspector-tabs"><button :class="{ active: inspectorTab === 'summary' }" @click="inspectorTab = 'summary'">{{ t('sdn.next.summary') }}</button><button :class="{ active: inspectorTab === 'technical' }" @click="inspectorTab = 'technical'">{{ t('sdn.next.technical') }}</button></div>
          <div v-if="inspectorTab === 'summary'" class="inspector-content">
            <template v-if="selectedObject.kind === 'vpc'"><p class="object-type">VPC</p><h3>{{ selectedObject.value.name }}</h3><dl><dt>{{ t('sdn.next.network') }}</dt><dd>{{ selectedObject.value.cidr }}</dd><dt>{{ t('sdn.next.gateway') }}</dt><dd>{{ selectedObject.value.gateway_ip }}</dd><dt>{{ t('sdn.tenant_name') }}</dt><dd>{{ selectedObject.value.tenant_name }}</dd></dl></template>
            <template v-else-if="selectedObject.kind === 'device'"><p class="object-type">EVPN LEAF</p><h3>{{ selectedObject.value.name }}</h3><dl><dt>{{ t('sdn.next.management_ip') }}</dt><dd>{{ selectedObject.value.host }}</dd><dt>{{ t('sdn.next.platform') }}</dt><dd>{{ selectedObject.value.platform || '—' }}</dd><dt>{{ t('sdn.next.access_count') }}</dt><dd>{{ bindingForLeaf(selectedObject.value.id).length }}</dd></dl></template>
            <template v-else-if="selectedObject.kind === 'binding'"><p class="object-type">ACCESS PORT</p><h3>{{ selectedObject.value.interface_name }}</h3><dl><dt>{{ t('sdn.next.device') }}</dt><dd>{{ deviceById(selectedObject.value.device_id)?.name || selectedObject.value.device_id }}</dd><dt>if_index</dt><dd>{{ selectedObject.value.if_index }}</dd><dt>Service instance</dt><dd>{{ selectedObject.value.service_instance }}</dd></dl></template>
            <template v-else-if="selectedObject.kind === 'operation'"><p class="object-type">OPERATION</p><h3>#{{ selectedObject.value.operation_id }}</h3><span class="status-chip large" :class="statusMeta(selectedObject.value.status).tone">{{ statusMeta(selectedObject.value.status).label }}</span><dl><dt>{{ t('sdn.next.host') }}</dt><dd>{{ selectedObject.value.expected_host_ip || '—' }}</dd><dt>{{ t('sdn.next.updated') }}</dt><dd>{{ formatTime(selectedObject.value.updated_at) }}</dd></dl><div class="operation-actions"><button v-if="canComplete(selectedObject.value)" class="primary" @click="runOperation('complete')">{{ t('sdn.next.verify_now') }}</button><button v-if="canReconcile(selectedObject.value)" class="secondary" @click="runOperation('reconcile')">{{ t('sdn.next.reconcile') }}</button><button v-if="canWithdraw(selectedObject.value)" class="danger-text" @click="runOperation('withdraw')">{{ t('sdn.next.withdraw_access') }}</button></div></template>
            <template v-else-if="selectedObject.kind === 'projection'"><p class="object-type">STRATA EVIDENCE</p><h3>{{ selectedObject.value.label }}</h3><span class="status-chip large" :class="projectionMeta(selectedObject.value.result?.status).tone">{{ projectionMeta(selectedObject.value.result?.status).label }}</span><p class="evidence-statement">{{ translatedCode('projection_reason', selectedObject.value.result?.reason_code, selectedObject.value.result?.reason_code) }}</p><dl><dt>{{ t('sdn.next.device') }}</dt><dd>{{ selectedObject.value.device_name }} · {{ selectedObject.value.device_host }}</dd><dt>{{ t('sdn.next.desired_state') }}</dt><dd>{{ selectedObject.value.desired }}</dd><dt>{{ t('sdn.next.observed_state') }}</dt><dd>{{ selectedObject.value.observed }}</dd><dt>{{ t('sdn.next.desired_source') }}</dt><dd>{{ projectionSourceLabel(selectedObject.value.result?.evidence?.desired_source) }}</dd><dt>{{ t('sdn.next.observed_source') }}</dt><dd>{{ projectionSourceLabel(selectedObject.value.result?.evidence?.observed_source) }}</dd><dt>{{ t('sdn.next.display_command') }}</dt><dd>{{ selectedObject.value.result?.evidence?.observed_source?.command || '—' }}</dd><dt>{{ t('sdn.next.observed_at') }}</dt><dd>{{ formatTime(selectedObject.value.result?.evidence?.observed_source?.collected_at || selectedObject.value.observed_at) }}</dd></dl></template>
            <template v-else-if="selectedObject.kind === 'history'"><p class="object-type">STRATA HISTORY</p><h3>{{ selectedObject.value.device_name }}</h3><span class="status-chip large" :class="projectionMeta(selectedObject.value.aggregate).tone">{{ projectionMeta(selectedObject.value.aggregate).label }}</span><p class="evidence-statement">{{ t('sdn.next.history_current_basis') }}</p><dl><dt>{{ t('sdn.next.observed_at') }}</dt><dd>{{ formatTime(selectedObject.value.collected_at) }}</dd><dt>{{ t('sdn.next.observed_source') }}</dt><dd>{{ t('sdn.next.source_snapshot', { id: selectedObject.value.snapshot_id }) }}</dd><dt>{{ t('sdn.next.validation_result') }}</dt><dd>{{ selectedObject.value.validation_result || '—' }}</dd><dt>{{ t('sdn.next.correlation') }}</dt><dd>{{ correlationLabel(selectedObject.value.correlation) }}</dd><template v-if="selectedObject.value.correlation?.operation"><dt>{{ t('sdn.next.related_operation') }}</dt><dd>#{{ selectedObject.value.correlation.operation.id }} · {{ selectedObject.value.correlation.operation.operation_type }} · {{ selectedObject.value.correlation.operation.status }}</dd></template><template v-if="selectedObject.value.correlation?.attempt"><dt>{{ t('sdn.next.related_attempt') }}</dt><dd>#{{ selectedObject.value.correlation.attempt.id }} · {{ selectedObject.value.correlation.attempt.kind }} · {{ selectedObject.value.correlation.attempt.status }}</dd></template><dt>VSI</dt><dd>{{ projectionMeta(selectedObject.value.diff?.vsi?.status).label }}</dd><dt>{{ t('sdn.next.gateway_interface') }}</dt><dd>{{ projectionMeta(selectedObject.value.diff?.vsi_interface?.status).label }}</dd><dt>L3VNI</dt><dd>{{ projectionMeta(selectedObject.value.diff?.l3_vni?.status).label }}</dd></dl><button v-if="selectedObject.value.correlation?.status === 'linked' && selectedObject.value.correlation.operation_id" class="secondary history-operation-link" @click="openOperation({ operation_id: selectedObject.value.correlation.operation_id })">{{ t('sdn.next.open_related_operation') }}</button></template>
            <template v-else><p class="object-type">EVIDENCE</p><h3>{{ selectedObject.value.unit_name }}</h3><span class="status-chip large" :class="statusMeta(selectedObject.value.state).tone">{{ truthLabel(selectedObject.value) }}</span><p class="evidence-statement">{{ unitExplanation(selectedObject.value) }}</p><dl><dt>{{ t('sdn.next.source') }}</dt><dd>{{ evidenceSource(selectedObject.value) }}</dd><dt>{{ t('sdn.next.scope') }}</dt><dd>{{ evidenceScope(selectedObject.value) }}</dd><dt>{{ t('sdn.next.observed_at') }}</dt><dd>{{ formatTime(selectedObject.value.explanation?.observed_at) }}</dd></dl></template>
          </div><pre v-else class="technical-view">{{ JSON.stringify(selectedObject.value, null, 2) }}</pre>
        </template>
      </aside>
    </section>

    <Teleport to="body">
      <div v-if="accessOpen" class="modal-backdrop" @click.self="accessOpen = false"><section class="modal access-modal">
        <header><div><p class="eyebrow">TERMINAL ACCESS</p><h2>{{ t('sdn.next.connect_terminal') }}</h2></div><button class="icon-button" :title="t('common.close')" @click="accessOpen = false">×</button></header>
        <div class="steps"><span :class="{ active: accessStep === 'form' }">1 {{ t('sdn.next.step_location') }}</span><span :class="{ active: accessStep === 'preview' }">2 {{ t('sdn.next.step_preview') }}</span><span :class="{ active: accessStep === 'operation' }">3 {{ t('sdn.next.step_validate') }}</span></div>
        <form v-if="accessStep === 'form'" class="form-grid" @submit.prevent="previewAccess">
          <label class="full">{{ t('sdn.target_leaf') }}<select v-model="accessForm.device_id" required><option disabled value="">{{ t('sdn.select_evpn_target') }}</option><option v-for="leaf in leafs" :key="leaf.id" :value="leaf.id">{{ leaf.name }} · {{ leaf.host }}</option></select></label>
          <label class="full">{{ t('sdn.next.business_port') }}<select name="sdn_access_interface" :disabled="!accessInterfaces.length" @change="chooseInterface"><option value="">{{ accessInterfaces.length ? t('sdn.select_interface') : t('sdn.no_interfaces_loaded') }}</option><option v-for="item in accessInterfaces" :key="item.if_index" :value="item.if_index">{{ item.name || item.interface_name }} · {{ item.status }}</option></select></label>
          <label>if_index<input v-model="accessForm.if_index" name="sdn_access_if_index" type="number" min="1" required></label><label>{{ t('sdn.interface_name') }}<input v-model="accessForm.interface_name" placeholder="GigabitEthernet1/0/3" required></label><label>Service instance<input v-model="accessForm.service_instance" type="number" min="1" required></label><label>{{ t('sdn.expected_host') }}<input v-model="accessForm.expected_host_ip" :placeholder="selectedVpc?.cidr" required></label>
          <p class="form-hint full">{{ t('sdn.next.preview_hint') }}</p><footer class="full"><button type="button" class="secondary" @click="accessOpen = false">{{ t('common.cancel') }}</button><button class="primary" :disabled="busy === 'preview'">{{ busy === 'preview' ? t('sdn.next.previewing') : t('sdn.next.preview_change') }}</button></footer>
        </form>
        <div v-else-if="accessStep === 'preview'" class="preview-body"><div class="preview-result" :class="previewBlocked ? 'blocked' : 'ready'"><strong>{{ t(previewBlocked ? 'sdn.next.preview_blocked' : 'sdn.next.preview_ready') }}</strong><p>{{ t(previewBlocked ? 'sdn.next.preview_blocked_detail' : 'sdn.next.preview_ready_detail') }}</p></div><dl class="preview-scope"><dt>VPC</dt><dd>{{ selectedVpc.name }}</dd><dt>{{ t('sdn.next.device') }}</dt><dd>{{ selectedLeaf?.name }}</dd><dt>{{ t('sdn.interface') }}</dt><dd>{{ accessForm.interface_name }}</dd><dt>{{ t('sdn.next.host') }}</dt><dd>{{ accessForm.expected_host_ip }}</dd></dl><ul v-if="previewBlocked" class="blocker-list"><li v-for="item in accessPlan.blocking" :key="item.code"><strong>{{ item.code }}</strong><span>{{ item.detail }}</span></li></ul><div v-else class="retained-note"><strong>{{ t('sdn.next.will_change') }}</strong><p>{{ t('sdn.next.shared_resources_kept') }}</p></div><footer><button class="secondary" @click="accessStep = 'form'">{{ t('sdn.next.preview_change') }}</button><button class="primary" :disabled="previewBlocked || busy === 'execute'" @click="executeAccess">{{ busy === 'execute' ? t('sdn.next.executing') : t('sdn.next.confirm_connect') }}</button></footer></div>
        <div v-else class="operation-ready"><span class="success-mark">✓</span><h3>{{ t('sdn.next.wire_then_validate') }}</h3><p>{{ t('sdn.next.operation_saved') }}</p><div class="operation-actions centered"><button v-if="canComplete(currentOperation)" class="primary" @click="runOperation('complete')">{{ t('sdn.next.complete_and_validate') }}</button><button class="secondary" @click="accessOpen = false">{{ t('sdn.next.close_and_track') }}</button></div></div>
      </section></div>

      <div v-if="resourcesOpen" class="modal-backdrop" @click.self="resourcesOpen = false"><section class="modal resource-modal">
        <header><div><p class="eyebrow">RESOURCE TOOLS</p><h2>{{ t('sdn.next.resource_tools') }}</h2></div><button class="icon-button" :title="t('common.close')" @click="resourcesOpen = false">×</button></header>
        <div class="resource-columns"><form @submit.prevent="createTenant"><h3>{{ t('sdn.create_tenant') }}</h3><label>{{ t('sdn.tenant_name') }}<input v-model="tenantForm.name" required></label><label>{{ t('sdn.description') }}<input v-model="tenantForm.description"></label><button class="secondary" :disabled="busy === 'tenant'">{{ t('sdn.create_tenant') }}</button></form><form @submit.prevent="createVpc"><h3>{{ t('sdn.create_vpc') }}</h3><label>{{ t('sdn.vpc_name') }}<input v-model="vpcForm.name" required></label><label>{{ t('sdn.tenant_name') }}<select v-model="vpcForm.tenant_id" required><option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option></select></label><label>CIDR<input v-model="vpcForm.cidr" required></label><button class="secondary" :disabled="busy === 'vpc'">{{ t('sdn.create_vpc') }}</button></form></div>
        <div class="fabric-tools"><h3>{{ t('sdn.fabric_actions') }}</h3><p>{{ t('sdn.next.fabric_preserved_hint') }}</p><div><select v-model="fabricDeviceId"><option disabled value="">{{ t('sdn.select_evpn_target') }}</option><option v-for="leaf in leafs" :key="leaf.id" :value="leaf.id">{{ leaf.name }} · {{ leaf.host }}</option></select><label class="check"><input v-model="fabricAutoApply" type="checkbox">{{ t('sdn.auto_apply') }}</label><button class="secondary" :disabled="!fabricDeviceId || busy.startsWith('fabric')" @click="changeFabric('deploy')">{{ t('sdn.deploy_plan') }}</button><button class="danger-text" :disabled="!fabricDeviceId || busy.startsWith('fabric')" @click="changeFabric('withdraw')">{{ t('sdn.withdraw_plan') }}</button></div></div>
      </section></div>
    </Teleport>
  </main>
</template>

<style scoped>
.next-workbench{min-height:calc(100vh - 72px);background:#f4f6f7;color:#172126;padding:24px}.workbench-bar{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:18px}.workbench-bar h1{font-size:30px;line-height:1.1;margin:4px 0 7px;letter-spacing:0}.workbench-bar p{margin:0;color:#607077}.eyebrow{font-size:11px!important;font-weight:800;color:#0d7a6b!important;text-transform:uppercase;letter-spacing:0!important}.header-actions,.operation-actions{display:flex;align-items:center;gap:9px}.primary,.secondary,.danger-text,.text-button,.icon-button{min-height:38px;border:1px solid transparent;border-radius:6px;padding:0 14px;font:inherit;font-weight:700;cursor:pointer}.primary{background:#126d62;color:#fff}.secondary{background:#fff;border-color:#cbd4d7;color:#24343a}.danger-text{background:#fff;border-color:#e7c5c5;color:#a63535}.text-button{background:transparent;color:#126d62}.icon-button{width:40px;padding:0;background:#fff;border-color:#cbd4d7;font-size:21px}.primary:disabled,.secondary:disabled,.danger-text:disabled,.icon-button:disabled{opacity:.45;cursor:not-allowed}.notice{border-radius:6px;padding:10px 13px;margin:0 0 12px;font-weight:650}.notice.error{background:#fff0ef;color:#9b2c2c;border:1px solid #efc5c1}.notice.success{background:#e9f7f2;color:#176b56;border:1px solid #b9dfd1}.workspace-grid{display:grid;grid-template-columns:minmax(210px,240px) minmax(480px,1fr) minmax(260px,310px);gap:12px;align-items:start}.scope-pane,.atlas-pane,.inspector-pane{background:#fff;border:1px solid #d9e0e2;border-radius:7px}.scope-pane,.inspector-pane{position:sticky;top:16px;padding:16px;max-height:calc(100vh - 120px);overflow:auto}.atlas-pane{padding:18px;min-width:0}.section-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.section-heading>div{display:flex;align-items:center;gap:8px}.section-heading span{font-size:10px;font-weight:900;color:#0d7a6b}.section-heading h2{font-size:13px;text-transform:uppercase;margin:0;letter-spacing:0}.section-heading>b{font-size:12px;color:#68787e}.section-heading.inline{margin:0 0 10px}.vpc-option{width:100%;display:grid;grid-template-columns:34px 1fr 8px;align-items:center;gap:10px;padding:10px 8px;margin-bottom:5px;border:1px solid transparent;border-radius:6px;background:transparent;text-align:left;cursor:pointer}.vpc-option:hover{background:#f4f7f7}.vpc-option.selected{background:#e7f4f1;border-color:#acd2c9}.vpc-mark,.device-glyph,.host-glyph{display:grid;place-items:center;width:34px;height:34px;border-radius:5px;background:#203239;color:#fff;font-size:11px;font-weight:850}.vpc-copy,.leaf-node header span,.port-node span,.terminal-list button>span:nth-child(2),.operation-table button>span:nth-child(2){min-width:0;display:flex;flex-direction:column}.vpc-copy strong,.leaf-node strong,.port-node strong,.terminal-list strong,.operation-table strong{overflow-wrap:anywhere}.vpc-copy small,.leaf-node small,.port-node small,.terminal-list small,.operation-table small{color:#748289;margin-top:3px}.status-dot,.online-dot{width:8px;height:8px;border-radius:50%;background:#98a4a8}.status-dot.good,.online-dot{background:#1b9a79}.status-dot.warn{background:#d49a24}.status-dot.bad{background:#d45656}.legend{display:flex;flex-wrap:wrap;gap:8px;margin-top:15px;padding-top:12px;border-top:1px solid #e8ecee;color:#6b797e;font-size:11px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:7px;height:7px;border-radius:50%;background:#9aa6aa}.legend i.good{background:#1b9a79}.legend i.warn{background:#d49a24}.vpc-context{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding:2px 2px 17px;border-bottom:1px solid #e4e9ea}.vpc-context h2{margin:3px 0 5px;font-size:24px}.vpc-context>div>p:last-child{margin:0;color:#65757b}.context-facts{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}.context-facts>span:not(.status-chip){display:flex;flex-direction:column;min-width:86px;padding:8px 10px;background:#f2f5f5;border-radius:5px}.context-facts small{font-size:10px;color:#6e7d82;text-transform:uppercase}.context-facts b{margin-top:3px;font-size:12px;overflow-wrap:anywhere}.status-chip{display:inline-flex;align-items:center;justify-content:center;min-height:24px;border-radius:12px;padding:2px 9px;font-size:11px;font-weight:800;background:#edf0f1;color:#536166}.status-chip.good{background:#dff3eb;color:#12674f}.status-chip.warn{background:#fff1d6;color:#8a5d08}.status-chip.bad{background:#fde5e3;color:#a02e2e}.status-chip.large{margin:5px 0 10px}.fabric-stage{margin-top:16px;border:1px solid #dce3e5;background:#f8faf9;padding:14px;border-radius:6px}.stage-label{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:900;color:#587077;text-transform:uppercase}.stage-label span{color:#0d7a6b}.leaf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:12px}.leaf-node{background:#fff;border:1px solid #d6dfe1;border-top:3px solid #176f64;padding:12px;border-radius:5px;cursor:pointer}.leaf-node:hover{border-color:#8bbdb3}.leaf-node header{display:grid;grid-template-columns:34px 1fr 8px;align-items:center;gap:9px}.fabric-link{display:flex;align-items:center;gap:6px;margin:10px 0;color:#789097;font-size:9px}.fabric-link span{height:1px;background:#d9e1e3;flex:1}.port-node{display:grid;grid-template-columns:18px 1fr;gap:8px;width:100%;align-items:center;padding:8px;border:1px solid #e1e7e8;background:#f7f9f9;border-radius:4px;text-align:left;cursor:pointer;margin-top:5px}.port-node:hover{background:#edf6f3}.port-icon{width:14px;height:11px;border:2px solid #557078;border-radius:2px;position:relative}.port-icon:after{content:'';position:absolute;width:6px;height:2px;background:#557078;bottom:-5px;left:2px}.no-binding{padding:9px;text-align:center;color:#8a969a;font-size:11px;border:1px dashed #d8dfe1;border-radius:4px}.terminal-strip,.pulse-panel{margin-top:14px;padding-top:14px;border-top:1px solid #e3e8e9}.terminal-list{display:flex;gap:8px;overflow:auto;padding-bottom:2px}.terminal-list button{min-width:205px;display:grid;grid-template-columns:32px 1fr auto;align-items:center;gap:8px;border:1px solid #dce3e5;background:#fff;border-radius:5px;padding:8px;text-align:left;cursor:pointer}.host-glyph{width:32px;height:32px;background:#44636d}.operation-table{display:flex;flex-direction:column;border:1px solid #e0e6e7;border-radius:5px;overflow:hidden}.operation-table button{display:grid;grid-template-columns:55px minmax(0,1fr) auto;align-items:center;gap:10px;padding:9px 11px;border:0;border-bottom:1px solid #e8edee;background:#fff;text-align:left;cursor:pointer}.operation-table button:hover{background:#f4f8f7}.operation-id{font:700 11px ui-monospace,monospace;color:#67777c}.inspector-tabs{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #dfe5e7;margin:0 -4px 15px}.inspector-tabs button{border:0;border-bottom:2px solid transparent;background:transparent;padding:9px;font-weight:750;color:#68777c;cursor:pointer}.inspector-tabs button.active{border-color:#14776a;color:#125f56}.object-type{color:#0d7a6b;font-size:10px;font-weight:900;margin:0}.inspector-content h3{font-size:19px;margin:5px 0 14px;overflow-wrap:anywhere}.inspector-content dl,.preview-scope{display:grid;grid-template-columns:minmax(86px,auto) minmax(0,1fr);gap:9px 12px;margin:0}.inspector-content dt,.preview-scope dt{font-size:11px;color:#748287}.inspector-content dd,.preview-scope dd{margin:0;font-size:12px;font-weight:700;overflow-wrap:anywhere}.operation-actions{margin-top:18px;flex-wrap:wrap}.technical-view{white-space:pre-wrap;overflow-wrap:anywhere;background:#172126;color:#d9ebe6;border-radius:5px;padding:12px;font:11px/1.55 ui-monospace,monospace;max-height:58vh;overflow:auto}.pane-empty,.empty-state{text-align:center;color:#7b888d;padding:34px 12px}.pane-empty strong{display:block;color:#48585e}.pane-empty p,.quiet-copy{color:#839095;font-size:12px}.empty-state.compact{padding:24px}.modal-backdrop{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:20px;background:rgba(18,30,34,.55)}.modal{width:min(680px,100%);max-height:calc(100vh - 40px);overflow:auto;background:#fff;border-radius:7px;box-shadow:0 20px 60px rgba(0,0,0,.25)}.modal>header{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;padding:18px 20px;background:#fff;border-bottom:1px solid #e0e6e7}.modal h2{margin:4px 0 0;font-size:22px}.steps{display:grid;grid-template-columns:repeat(3,1fr);background:#f1f4f4;border-bottom:1px solid #e0e6e7}.steps span{padding:10px;text-align:center;font-size:11px;font-weight:750;color:#8a969a}.steps span.active{background:#e4f2ee;color:#12685c}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:20px}.form-grid .full{grid-column:1/-1}.form-grid label,.resource-columns label{display:flex;flex-direction:column;gap:6px;font-size:11px;font-weight:750;color:#53646a}.form-grid input,.form-grid select,.resource-columns input,.resource-columns select,.fabric-tools select{width:100%;min-height:39px;border:1px solid #cbd5d8;border-radius:5px;background:#fff;padding:8px 10px;font:inherit;color:#1f2c31}.form-hint{margin:0;color:#718086;font-size:11px}.form-grid footer,.preview-body footer{display:flex;justify-content:flex-end;gap:8px;padding-top:4px}.preview-body{padding:20px}.preview-result{border-left:4px solid;padding:12px 14px;margin-bottom:17px;background:#f4f6f6}.preview-result p{margin:4px 0 0;color:#66767c;font-size:12px}.preview-result.ready{border-color:#1a936f;background:#eaf7f2}.preview-result.blocked{border-color:#cf7c1d;background:#fff4e3}.preview-scope{padding-bottom:16px}.blocker-list{list-style:none;padding:0;margin:0 0 16px}.blocker-list li{display:flex;flex-direction:column;gap:3px;padding:10px;border:1px solid #efce9f;background:#fff9f0;margin-bottom:6px;border-radius:4px}.blocker-list span{font-size:12px;color:#775928}.retained-note{padding:12px;background:#edf4f5;border-radius:5px;margin-bottom:16px}.retained-note p{margin:4px 0 0;color:#5f7076;font-size:12px}.operation-ready{text-align:center;padding:34px 22px}.success-mark{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;margin:0 auto;background:#dff3eb;color:#147057;font-size:24px}.operation-ready h3{margin:13px 0 5px}.operation-ready p{color:#6a797e}.operation-actions.centered{justify-content:center}.resource-modal{width:min(820px,100%)}.resource-columns{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:20px}.resource-columns form{display:flex;flex-direction:column;gap:11px;border:1px solid #dfe6e7;border-radius:6px;padding:15px}.resource-columns h3,.fabric-tools h3{margin:0;font-size:14px}.fabric-tools{margin:0 20px 20px;padding:15px;border-top:3px solid #405a63;background:#f5f7f7}.fabric-tools>p{font-size:12px;color:#68777c}.fabric-tools>div{display:grid;grid-template-columns:minmax(180px,1fr) auto auto auto;align-items:center;gap:8px}.check{display:flex;align-items:center;gap:6px;font-size:11px}.check input{width:auto}.loading{opacity:.55;pointer-events:none}
.perspective-switch{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));max-width:720px;margin:0 0 18px;border:1px solid #ccd6d8;border-radius:6px;overflow:hidden;background:#fff}.perspective-switch button{display:flex;align-items:baseline;gap:8px;min-width:0;padding:9px 13px;border:0;border-right:1px solid #dce3e5;background:#fff;color:#6d7c81;text-align:left;cursor:pointer}.perspective-switch button:last-child{border-right:0}.perspective-switch button.active{background:#1d3339;color:#fff}.perspective-switch span{font-size:11px;font-weight:900}.perspective-switch small{font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.perspective-switch button.active small{color:#bed4d1}.perspective-panel{margin-top:16px;min-height:470px}.perspective-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:4px 2px 16px;border-bottom:1px solid #dfe6e7}.perspective-heading h3{margin:4px 0 0;font-size:18px}.perspective-heading>p{max-width:390px;margin:0;color:#6d7b80;font-size:12px;text-align:right}.intent-ribbon{display:grid;grid-template-columns:minmax(0,1.4fr) 24px minmax(0,1fr) 24px minmax(0,1fr);align-items:center;margin:16px 0;padding:13px;background:#20343a;color:#fff;border-radius:6px}.intent-ribbon>span{display:flex;flex-direction:column;gap:4px;min-width:0}.intent-ribbon small{font-size:9px;font-weight:800;color:#9fc0bb;text-transform:uppercase}.intent-ribbon strong{font-size:12px;overflow-wrap:anywhere}.intent-ribbon>i{height:1px;margin:0 7px;background:#5f7a80;position:relative}.intent-ribbon>i:after{content:'';position:absolute;right:0;top:-3px;border-width:3px 0 3px 5px;border-style:solid;border-color:transparent transparent transparent #8ca6aa}.timeline{padding:3px 2px}.timeline article{display:grid;grid-template-columns:32px minmax(0,1fr);gap:10px;min-height:92px}.timeline-rail{display:flex;align-items:center;flex-direction:column}.timeline-rail span{display:grid;place-items:center;width:27px;height:27px;border:2px solid #94a3a7;border-radius:50%;background:#fff;font-size:10px;font-weight:900}.timeline article.good .timeline-rail span{border-color:#198568;color:#147158}.timeline article.warn .timeline-rail span{border-color:#d0972a;color:#8d620e}.timeline-rail i{width:1px;flex:1;background:#d8e0e2}.timeline article:last-child .timeline-rail i{display:none}.timeline-copy{padding:1px 0 17px}.timeline-copy>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.timeline-copy header span{display:flex;flex-direction:column}.timeline-copy small{font-size:9px;font-weight:850;color:#78868b;text-transform:uppercase}.timeline-copy strong{font-size:13px;margin-top:2px}.timeline-copy header>b{font-size:10px;color:#6a797e}.timeline-copy p{margin:7px 0;color:#53656b;font-size:12px}.timeline-copy footer{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#8a969a;font-size:10px}.timeline-copy footer button{border:0;background:transparent;color:#126d62;font-size:10px;font-weight:750;cursor:pointer}.pulse-actions{justify-content:flex-end;padding-top:12px;border-top:1px solid #e2e8e9}.pulse-empty{padding-top:18px}.pulse-empty>p{color:#68787d;font-size:12px}.strata-stack{max-width:760px;margin:18px auto}.strata-layer{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:13px;border:1px solid #d5dfe1;border-left:4px solid #516a72;border-radius:5px;background:#fff;padding:13px;box-shadow:0 5px 16px rgba(26,47,53,.05);cursor:default}.strata-layer>span{display:grid;place-items:center;width:29px;height:29px;background:#edf2f2;color:#33525a;border-radius:4px;font-size:10px;font-weight:900}.strata-layer>div{display:flex;flex-direction:column;gap:3px;min-width:0}.strata-layer small{font-size:9px;font-weight:850;color:#76868b;text-transform:uppercase}.strata-layer strong{font-size:13px;overflow-wrap:anywhere}.strata-layer p{margin:0;color:#65757a;font-size:11px}.business-layer{border-left-color:#198568}.logic-layer{border-left-color:#4b6570}.logic-layer>b{font-size:10px;color:#61747a}.dependency-line{display:flex;align-items:center;gap:8px;width:86%;margin:8px auto;color:#849196;font-size:9px;font-weight:800;text-transform:uppercase}.dependency-line i{height:1px;flex:1;background:#d7dfe1}.physical-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.device-layer{cursor:pointer}.device-layer:hover{border-color:#86aea7}.evidence-badge{font-size:9px;padding:4px 6px;border-radius:3px;background:#edf1f2;color:#65757a}.evidence-badge.good{background:#dff3eb;color:#12674f}.evidence-badge.bad{background:#fde5e3;color:#9b3030}.truth-legend{display:flex;justify-content:center;gap:16px;padding-top:14px;border-top:1px solid #e3e8e9;color:#68777c;font-size:10px}.truth-legend span{display:flex;align-items:center;gap:5px}.truth-legend i{width:10px;height:3px}.truth-legend .desired{background:#4b6570}.truth-legend .observed{background:#198568}.truth-legend .inferred{border-top:2px dashed #c28b25}.strata-view{background:linear-gradient(#fff,#f7f9f9);border:1px solid #dce3e5;border-radius:6px;padding:16px}
.strata-view{background:#f7f9f9}.strata-intent{display:grid;grid-template-columns:minmax(0,1fr) 42px minmax(0,1fr);align-items:center;margin:16px 0;padding:12px 14px;background:#20343a;color:#fff;border-radius:5px}.strata-intent>span{display:flex;flex-direction:column;min-width:0}.strata-intent small{color:#9fc0bb;font-size:9px;font-weight:850;text-transform:uppercase}.strata-intent strong{margin:3px 0;font-size:13px}.strata-intent b{color:#d3dfdf;font-size:10px;font-weight:600;overflow-wrap:anywhere}.strata-intent>i{height:1px;margin:0 10px;background:#6f878c}.projection-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px}.projection-card{min-width:0;border:1px solid #d5dfe1;border-top:3px solid #829095;border-radius:5px;background:#fff;padding:13px;cursor:pointer}.projection-card:hover{border-color:#86aea7}.projection-card.is-aligned{border-top-color:#198568}.projection-card.is-drifted{border-top-color:#c94d4d}.projection-card.is-stale{border-top-color:#c28b25}.projection-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.projection-card>header>span:first-child{display:flex;flex-direction:column;min-width:0}.projection-card header small,.projection-evidence small{font-size:9px;font-weight:850;color:#748287;text-transform:uppercase}.projection-card header strong{font-size:14px;margin:2px 0}.projection-card header b{font-size:10px;color:#6d7d82}.projection-evidence{display:flex;gap:18px;margin:11px 0;padding:8px 0;border-top:1px solid #e6ebec;border-bottom:1px solid #e6ebec}.projection-evidence span{display:flex;flex-direction:column;gap:2px}.projection-evidence b{font-size:10px;color:#42575d}.projection-columns,.projection-row{display:grid;grid-template-columns:minmax(88px,1fr) minmax(74px,.8fr) minmax(74px,.8fr) 70px;gap:7px;align-items:center}.projection-columns{padding:2px 0 6px;color:#809095;font-size:9px;font-weight:800;text-transform:uppercase}.projection-columns span:first-child{grid-column:2}.projection-row{min-height:34px;border-top:1px solid #eef1f2;font-size:10px}.projection-row>strong,.projection-row>span{overflow-wrap:anywhere}.projection-row>span{color:#52666c}.projection-result{justify-self:end;border-radius:3px;padding:3px 5px;background:#edf1f2;color:#596a70;font-size:9px}.projection-result.good{background:#dff3eb;color:#12674f}.projection-result.warn{background:#fff1d6;color:#8a5d08}.projection-result.bad{background:#fde5e3;color:#a02e2e}.strata-empty{padding:38px;text-align:center;background:#fff;border:1px dashed #ccd7d9}.strata-empty p,.projection-excluded{color:#718086;font-size:11px}.projection-excluded{text-align:right}
.impact-map{margin:0 0 18px;padding:13px;border:1px solid #d7e0e1;border-left:3px solid #16796b;background:#f7f9f9}.impact-map>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px}.impact-map>header span{display:flex;flex-direction:column;gap:2px}.impact-map>header small{color:#16796b;font-size:9px;font-weight:900;text-transform:uppercase}.impact-map>header strong{font-size:12px}.impact-map>header p{max-width:310px;margin:0;color:#75858a;font-size:10px;text-align:right}.impact-chain{display:flex;align-items:center;gap:7px}.impact-step{display:contents}.impact-node{display:flex;flex:1;flex-direction:column;min-width:0;padding:9px;border:1px solid #d5dddf;border-radius:5px;background:#fff}.impact-node>b{color:#16796b;font-size:9px;text-transform:uppercase}.impact-node>strong{margin:3px 0;font-size:11px;overflow-wrap:anywhere}.impact-node>small{color:#77868b;font-size:8px;overflow-wrap:anywhere}.impact-link{display:flex;flex:0 0 56px;align-items:center;flex-direction:column;color:#75868a;font-size:8px;font-weight:800}.impact-link i{position:relative;width:100%;height:1px;margin-top:4px;background:#aebdc0}.impact-link i:after{position:absolute;right:0;top:-3px;border-width:3px 0 3px 5px;border-style:solid;border-color:transparent transparent transparent #7c9195;content:''}
.demo-banner{display:flex;align-items:center;gap:10px;margin:0 0 10px;padding:8px 11px;border-left:3px solid #c1841c;background:#fff5df;color:#72500e;font-size:11px}.demo-banner strong{font-size:10px;text-transform:uppercase}.demo-banner span{color:#866b32}
@media(max-width:1050px){.workspace-grid{grid-template-columns:210px minmax(0,1fr)}.inspector-pane{position:static;grid-column:1/-1;max-height:none}.vpc-context{align-items:flex-start;flex-direction:column}.context-facts{justify-content:flex-start}}
@media(max-width:720px){.next-workbench{padding:14px}.workbench-bar{align-items:flex-start;flex-direction:column}.header-actions{width:100%;flex-wrap:wrap}.header-actions .primary{flex:1}.workspace-grid{grid-template-columns:1fr}.scope-pane,.inspector-pane{position:static;max-height:none}.scope-pane{display:grid;grid-template-columns:1fr 1fr;gap:5px}.scope-pane .section-heading,.scope-pane .legend,.scope-pane .pane-empty{grid-column:1/-1}.atlas-pane{padding:14px}.context-facts{display:grid;grid-template-columns:1fr 1fr;width:100%}.leaf-grid{grid-template-columns:1fr}.terminal-list{flex-direction:column}.terminal-list button{min-width:0;width:100%}.form-grid,.resource-columns{grid-template-columns:1fr}.form-grid .full{grid-column:auto}.fabric-tools>div{grid-template-columns:1fr}.modal-backdrop{padding:8px}.modal{max-height:calc(100vh - 16px)}.operation-table button{grid-template-columns:44px minmax(0,1fr)}.operation-table .status-chip{grid-column:2;justify-self:start}}
@media(max-width:720px){.perspective-switch{width:100%}.perspective-switch button{align-items:flex-start;flex-direction:column;gap:2px}.perspective-switch small{white-space:normal}.intent-ribbon,.strata-intent{grid-template-columns:1fr}.intent-ribbon>i,.strata-intent>i{width:1px;height:14px;margin:4px 0}.perspective-heading{flex-direction:column}.perspective-heading>p{text-align:left}.projection-grid{grid-template-columns:1fr}.projection-columns,.projection-row{grid-template-columns:minmax(76px,1fr) minmax(62px,.8fr) minmax(62px,.8fr)}.projection-columns span:first-child{grid-column:1}.projection-row>.projection-result{grid-column:2/4;justify-self:start;margin-bottom:6px}}
.vpc-copy strong{font-size:13px;line-height:1.2;overflow-wrap:normal}
@media(max-width:720px){.scope-pane{display:block}.vpc-copy strong{white-space:nowrap}}
.evidence-statement{margin:0 0 14px;padding:10px;border-left:3px solid #198568;background:#f1f7f5;color:#52656a;font-size:12px}
.projection-card-actions{display:flex;align-items:center;gap:5px}.projection-card-actions>button{display:grid;place-items:center;width:28px;height:28px;border:1px solid #cbd5d8;border-radius:4px;background:#fff;color:#315a60;font-size:16px;cursor:pointer}.projection-card-actions>button:disabled{opacity:.4;cursor:not-allowed}
.projection-row{width:100%;padding:0;border-right:0;border-bottom:0;border-left:0;background:transparent;color:inherit;text-align:left;cursor:pointer}.projection-row:hover{background:#f1f7f5}.projection-row:focus-visible{outline:2px solid #16796b;outline-offset:2px}
.projection-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0 0 12px;border:1px solid #d4dddf;border-radius:5px;overflow:hidden;background:#fff}.projection-filters button{display:flex;align-items:center;justify-content:center;gap:7px;min-width:0;height:36px;border:0;border-right:1px solid #e0e6e7;background:#fff;color:#607177;font-size:10px;font-weight:750;cursor:pointer}.projection-filters button:last-child{border-right:0}.projection-filters button.active{background:#20343a;color:#fff}.projection-filters b{display:grid;place-items:center;min-width:19px;height:19px;border-radius:10px;background:#edf1f2;color:#4f6268;font-size:9px}.projection-filters button.active b{background:#d3e7e3;color:#174f48}.strata-empty.compact{padding:22px}
.history-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;height:34px;margin-top:9px;padding:0 2px;border:0;border-top:1px solid #dfe6e7;background:transparent;color:#315a60;font-size:10px;font-weight:800;cursor:pointer}.history-toggle b{font-size:17px;font-weight:500}.history-toggle.active{color:#16796b}.history-panel{margin:0 -3px -3px;padding:10px;background:#f4f7f7;border:1px solid #dce4e5;border-radius:4px}.history-panel>header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px}.history-panel>header span{display:flex;flex-direction:column}.history-panel>header small{font-size:9px;font-weight:850;color:#64787d;text-transform:uppercase}.history-panel>header strong{margin-top:2px;color:#4f6268;font-size:10px;font-weight:600}.history-panel>header>b{min-width:22px;text-align:right;color:#708287;font-size:10px}.history-track{position:relative}.history-track:before{position:absolute;top:10px;bottom:10px;left:5px;width:1px;background:#c5d3d4;content:''}.history-track>button{position:relative;display:grid;grid-template-columns:12px minmax(0,1fr) auto;align-items:center;gap:7px;width:100%;min-height:38px;padding:4px 0;border:0;background:transparent;text-align:left;cursor:pointer}.history-track>button>i{z-index:1;width:11px;height:11px;border:3px solid #f4f7f7;border-radius:50%;background:#7c8d91;box-shadow:0 0 0 1px #aebdbf}.history-track>button.is-aligned>i{background:#198568}.history-track>button.is-drifted>i{background:#c94d4d}.history-track>button.is-stale>i{background:#c28b25}.history-track>button>span{display:flex;flex-direction:column;min-width:0}.history-track>button strong{color:#314a50;font-size:10px}.history-track>button small{margin-top:1px;color:#7b8a8e;font-size:9px}.history-track>button>b{padding:3px 5px;border-radius:3px;background:#e8edef;color:#5d6d72;font-size:9px}.history-track>button>b.good{background:#dff3eb;color:#12674f}.history-track>button>b.warn{background:#fff1d6;color:#8a5d08}.history-track>button>b.bad{background:#fde5e3;color:#a02e2e}.history-track>button:hover span strong{color:#0d6f61}.history-operation-link{width:100%;margin-top:12px}
@media(max-width:720px){.projection-filters{grid-template-columns:1fr 1fr}.projection-filters button:nth-child(2){border-right:0}.projection-filters button:nth-child(-n+2){border-bottom:1px solid #e0e6e7}}
@media(max-width:720px){.impact-map>header{flex-direction:column}.impact-map>header p{text-align:left}.impact-chain{align-items:stretch;flex-direction:column}.impact-link{flex:0 0 25px;min-height:25px}.impact-link i{width:1px;flex:1;min-height:13px}.impact-link i:after{right:-3px;top:auto;bottom:0;border-width:5px 3px 0;border-color:#7c9195 transparent transparent}}
</style>
