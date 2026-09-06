<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import { deviceApi, interfaceApi, sdnApi } from '../api/index.js'

const { t } = useI18n()

const loading = ref(true)
const busy = ref('')
const error = ref('')
const message = ref('')

const tenants = ref([])
const vpcs = ref([])
const devices = ref([])
const interfaces = ref([])
const bindings = ref([])
const deployments = ref([])
const validation = ref(null)
const selectedVpcId = ref(null)
const selectedDeviceId = ref(null)

const tenantForm = ref({ name: '', description: '' })
const vpcForm = ref({ name: '', tenant_id: '', cidr: '192.168.10.0/24', description: '' })
const bindForm = ref({ if_index: '', interface_name: '', service_instance: '', expected_host_ip: '' })
const autoApply = ref(false)
const guideOpen = ref(false)

const selectedVpc = computed(() => vpcs.value.find((v) => v.id === selectedVpcId.value) || null)
const sdnDevices = computed(() => devices.value.filter(isSdnFabricMember))
const hasSdnTargets = computed(() => sdnDevices.value.length > 0)
const selectedBindings = computed(() => bindings.value.filter((b) => b.vpc_id === selectedVpcId.value))
const selectedDeployments = computed(() => deployments.value.filter((d) => d.vpc_id === selectedVpcId.value).slice(0, 8))
const latestExpansionBinding = computed(() => selectedBindings.value.find((b) => b.status === 'expanding') || selectedBindings.value[0] || null)

const stats = computed(() => {
  const active = vpcs.value.filter((v) => v.status === 'active').length
  const planned = vpcs.value.filter((v) => ['planned', 'pending', 'withdraw_planned'].includes(v.status)).length
  const degraded = vpcs.value.filter((v) => ['degraded', 'failed'].includes(v.status)).length
  return {
    tenants: tenants.value.length,
    vpcs: vpcs.value.length,
    active,
    planned,
    degraded,
    bindings: bindings.value.length,
  }
})

const selectedStatusHint = computed(() => {
  if (!selectedVpc.value) return ''
  return t(`sdn.status_hint.${selectedVpc.value.status}`) === `sdn.status_hint.${selectedVpc.value.status}`
    ? t('sdn.status_hint.unknown')
    : t(`sdn.status_hint.${selectedVpc.value.status}`)
})

const guideSections = computed(() => [
  {
    title: t('sdn.guide_new_vpc_title'),
    steps: [
      t('sdn.guide_new_vpc_1'),
      t('sdn.guide_new_vpc_2'),
      t('sdn.guide_new_vpc_3'),
      t('sdn.guide_new_vpc_4'),
      t('sdn.guide_new_vpc_5'),
    ],
  },
  {
    title: t('sdn.guide_expand_title'),
    steps: [
      t('sdn.guide_expand_1'),
      t('sdn.guide_expand_2'),
      t('sdn.guide_expand_3'),
      t('sdn.guide_expand_4'),
    ],
  },
  {
    title: t('sdn.guide_troubleshoot_title'),
    steps: [
      t('sdn.guide_troubleshoot_1'),
      t('sdn.guide_troubleshoot_2'),
      t('sdn.guide_troubleshoot_3'),
    ],
  },
])

function isSdnFabricMember(device) {
  return String(device.sdn_role || '').toLowerCase() === 'evpn_leaf'
}

function statusClass(status) {
  if (['active', 'success', 'online'].includes(status)) return 'chip-good'
  if (['degraded', 'failed', 'offline'].includes(status)) return 'chip-bad'
  if (['deploying', 'withdrawing', 'expanding', 'pending', 'planned', 'withdraw_planned'].includes(status)) return 'chip-warn'
  return 'chip-mute'
}

function deviceName(id) {
  const d = devices.value.find((item) => item.id === id)
  return d ? `${d.name} (${d.host})` : `#${id}`
}

function ifaceName(binding) {
  return binding.interface_name || `if_index ${binding.if_index}`
}

function selectedDeviceIds() {
  return selectedDeviceId.value ? [selectedDeviceId.value] : []
}

function ensureSelectedSdnDevice() {
  if (sdnDevices.value.some((device) => device.id === selectedDeviceId.value)) return
  selectedDeviceId.value = sdnDevices.value[0]?.id || null
}

function clearNotice() {
  error.value = ''
  message.value = ''
}

function handleResult(result, successText) {
  if (!result.success) {
    error.value = result.error || t('sdn.msg_failed')
    return false
  }
  message.value = successText
  return true
}

async function loadAll(resetNotice = true) {
  loading.value = true
  if (resetNotice) clearNotice()
  const [tenantRes, vpcRes, deviceRes, bindingRes, deploymentRes] = await Promise.all([
    sdnApi.listTenants(),
    sdnApi.listVpcs(),
    deviceApi.list(),
    sdnApi.listPortBindings(),
    sdnApi.listDeployments(),
  ])

  loading.value = false
  if (!tenantRes.success || !vpcRes.success || !deviceRes.success || !bindingRes.success || !deploymentRes.success) {
    error.value = tenantRes.error || vpcRes.error || deviceRes.error || bindingRes.error || deploymentRes.error || t('sdn.load_failed')
    return
  }

  tenants.value = tenantRes.data?.tenants || []
  vpcs.value = vpcRes.data?.vpcs || []
  devices.value = deviceRes.data || []
  bindings.value = bindingRes.data?.port_bindings || []
  deployments.value = deploymentRes.data?.deployments || []

  if (!selectedVpcId.value && vpcs.value.length > 0) selectedVpcId.value = vpcs.value[0].id
  ensureSelectedSdnDevice()
  if (!vpcForm.value.tenant_id && tenants.value.length > 0) vpcForm.value.tenant_id = tenants.value[0].id
}

async function loadVpcRelated() {
  if (!selectedVpcId.value) return
  const [bindingRes, deploymentRes] = await Promise.all([
    sdnApi.listPortBindings({ vpc_id: selectedVpcId.value }),
    sdnApi.listDeployments({ vpc_id: selectedVpcId.value }),
  ])
  if (bindingRes.success) bindings.value = mergeById(bindings.value, bindingRes.data?.port_bindings || [])
  if (deploymentRes.success) deployments.value = mergeById(deployments.value, deploymentRes.data?.deployments || [])
}

function mergeById(oldList, newList) {
  const map = new Map(oldList.map((item) => [item.id, item]))
  for (const item of newList) map.set(item.id, item)
  return Array.from(map.values()).sort((a, b) => b.id - a.id)
}

async function loadInterfaces() {
  interfaces.value = []
  if (!selectedDeviceId.value) return
  const result = await interfaceApi.list(selectedDeviceId.value)
  if (result.success) interfaces.value = result.data || []
}

async function createTenant() {
  if (!tenantForm.value.name.trim()) return
  busy.value = 'tenant'
  clearNotice()
  const result = await sdnApi.createTenant({
    name: tenantForm.value.name.trim(),
    description: tenantForm.value.description.trim() || null,
  })
  busy.value = ''
  if (handleResult(result, t('sdn.tenant_created'))) {
    tenantForm.value = { name: '', description: '' }
    await loadAll(false)
  }
}

async function createVpc() {
  if (!vpcForm.value.name.trim() || !vpcForm.value.tenant_id || !vpcForm.value.cidr.trim()) return
  busy.value = 'vpc'
  clearNotice()
  const result = await sdnApi.createVpc({
    name: vpcForm.value.name.trim(),
    tenant_id: Number(vpcForm.value.tenant_id),
    cidr: vpcForm.value.cidr.trim(),
    description: vpcForm.value.description.trim() || null,
  })
  busy.value = ''
  if (handleResult(result, t('sdn.vpc_created'))) {
    selectedVpcId.value = result.data?.id || selectedVpcId.value
    vpcForm.value.name = ''
    vpcForm.value.description = ''
    await loadAll(false)
  }
}

async function deployVpc() {
  if (!selectedVpc.value) return
  busy.value = 'deploy'
  clearNotice()
  const result = await sdnApi.deployVpc(selectedVpc.value.id, {
    device_ids: selectedDeviceIds(),
    auto_apply: autoApply.value,
    include_port_bindings: true,
  })
  busy.value = ''
  if (handleResult(result, autoApply.value ? t('sdn.deploy_submitted') : t('sdn.deploy_planned'))) await loadAll(false)
}

async function withdrawVpc() {
  if (!selectedVpc.value) return
  busy.value = 'withdraw'
  clearNotice()
  const result = await sdnApi.withdrawVpc(selectedVpc.value.id, {
    device_ids: selectedDeviceIds(),
    auto_apply: autoApply.value,
    include_port_bindings: true,
  })
  busy.value = ''
  if (handleResult(result, autoApply.value ? t('sdn.withdraw_submitted') : t('sdn.withdraw_planned'))) await loadAll(false)
}

async function createBinding() {
  if (!selectedVpc.value || !selectedDeviceId.value || !bindForm.value.if_index || !bindForm.value.interface_name.trim()) return
  busy.value = 'binding'
  clearNotice()
  const result = await sdnApi.createPortBinding({
    vpc_id: selectedVpc.value.id,
    device_id: Number(selectedDeviceId.value),
    if_index: Number(bindForm.value.if_index),
    interface_name: bindForm.value.interface_name.trim(),
    service_instance: bindForm.value.service_instance ? Number(bindForm.value.service_instance) : null,
  })
  busy.value = ''
  if (handleResult(result, t('sdn.binding_created'))) {
    bindForm.value = { if_index: '', interface_name: '', service_instance: '', expected_host_ip: '' }
    await loadVpcRelated()
  }
}

async function startExpansion() {
  if (!selectedVpc.value || !selectedDeviceId.value || !bindForm.value.if_index || !bindForm.value.interface_name.trim()) return
  busy.value = 'expansion'
  clearNotice()
  const result = await sdnApi.startExpansion(selectedVpc.value.id, {
    device_id: Number(selectedDeviceId.value),
    if_index: Number(bindForm.value.if_index),
    interface_name: bindForm.value.interface_name.trim(),
    service_instance: bindForm.value.service_instance ? Number(bindForm.value.service_instance) : null,
    expected_host_ip: bindForm.value.expected_host_ip.trim() || null,
    auto_apply: autoApply.value,
  })
  busy.value = ''
  if (handleResult(result, t('sdn.expansion_started'))) {
    await loadAll(false)
  }
}

async function completeExpansion() {
  if (!selectedVpc.value || !latestExpansionBinding.value) return
  busy.value = 'complete'
  clearNotice()
  const result = await sdnApi.completeExpansion(selectedVpc.value.id, latestExpansionBinding.value.id, {
    expected_host_ip: bindForm.value.expected_host_ip.trim() || null,
    force_validation: true,
  })
  busy.value = ''
  if (handleResult(result, result.data?.success ? t('sdn.expansion_success') : t('sdn.expansion_degraded'))) {
    validation.value = result.data?.validation || validation.value
    await loadAll(false)
  }
}

async function syncValidation(force = true) {
  if (!selectedVpc.value || !selectedDeviceId.value) return
  busy.value = 'validation'
  clearNotice()
  const result = await sdnApi.syncValidation(selectedVpc.value.id, selectedDeviceId.value, force)
  busy.value = ''
  if (handleResult(result, t('sdn.validation_synced'))) validation.value = result.data
}

async function loadLatestValidation() {
  validation.value = null
  if (!selectedVpc.value || !selectedDeviceId.value) return
  const result = await sdnApi.latestValidation(selectedVpc.value.id, selectedDeviceId.value)
  if (result.success) validation.value = result.data
}

function onInterfaceChange() {
  const iface = interfaces.value.find((item) => Number(item.if_index) === Number(bindForm.value.if_index))
  if (!iface) return
  bindForm.value.interface_name = iface.name || bindForm.value.interface_name
}

watch(selectedVpcId, async () => {
  await loadVpcRelated()
  await loadLatestValidation()
})

watch(selectedDeviceId, async () => {
  await loadInterfaces()
  await loadLatestValidation()
})

onMounted(async () => {
  await loadAll()
  await loadInterfaces()
  await loadLatestValidation()
})
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('common.loading') }}</div>
  <template v-else>
    <PageHeader :title="t('sdn.title')" :subtitle="t('sdn.subtitle')" badge="v3.4">
      <template #actions>
        <button class="btn-outline" @click="guideOpen = true">{{ t('sdn.best_practice') }}</button>
        <button class="btn-outline" @click="loadAll">{{ t('sdn.refresh') }}</button>
        <button class="btn-primary" :disabled="busy === 'validation' || !selectedVpc || !selectedDeviceId" @click="syncValidation(true)">
          {{ busy === 'validation' ? t('sdn.syncing') : t('sdn.sync_validation') }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1440px] mx-auto px-4 md:px-6 xl:px-8 pb-16 space-y-4">
      <div v-if="error" class="rounded-xl border border-bad/30 bg-bad/5 px-4 py-3 text-sm text-bad">{{ error }}</div>
      <div v-if="message" class="rounded-xl border border-good/30 bg-good/5 px-4 py-3 text-sm text-good">{{ message }}</div>

      <div class="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div class="panel p-4" v-for="item in [
          { label: t('sdn.kpi_tenants'), value: stats.tenants },
          { label: t('sdn.kpi_vpcs'), value: stats.vpcs },
          { label: t('sdn.kpi_active'), value: stats.active },
          { label: t('sdn.kpi_planned'), value: stats.planned },
          { label: t('sdn.kpi_degraded'), value: stats.degraded },
          { label: t('sdn.kpi_bindings'), value: stats.bindings },
        ]" :key="item.label">
          <div class="text-[10px] uppercase tracking-wider text-ink-500">{{ item.label }}</div>
          <div class="kpi-num mt-1">{{ item.value }}</div>
        </div>
      </div>

      <div class="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
        <aside class="panel p-4 space-y-4">
          <div class="flex items-center justify-between">
            <div class="text-sm font-semibold text-ink-900">{{ t('sdn.vpc_inventory') }}</div>
            <span class="chip-mute">{{ vpcs.length }}</span>
          </div>

          <div class="space-y-2 max-h-[420px] overflow-auto pr-1">
            <button
              v-for="vpc in vpcs"
              :key="vpc.id"
              type="button"
              :class="['w-full text-left rounded-xl p-3 ring-1 transition', selectedVpcId === vpc.id ? 'bg-accent/8 ring-accent/25' : 'bg-canvas-100 ring-canvas-300 hover:bg-canvas-200']"
              @click="selectedVpcId = vpc.id"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="font-semibold text-sm text-ink-900 truncate">{{ vpc.name }}</span>
                <span :class="['chip', statusClass(vpc.status)]">{{ vpc.status }}</span>
              </div>
              <div class="mt-1 text-xs text-ink-500 font-mono break-all">{{ vpc.cidr }} · VNI {{ vpc.vni }}</div>
            </button>
            <div v-if="vpcs.length === 0" class="text-sm text-ink-500 py-8 text-center">{{ t('sdn.no_vpcs') }}</div>
          </div>
        </aside>

        <main class="space-y-4">
          <section class="panel p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="text-lg font-semibold text-ink-900">{{ selectedVpc?.name || t('sdn.no_selected_vpc') }}</div>
                <div v-if="selectedVpc" class="text-xs text-ink-500 mt-1 font-mono break-all">
                  {{ selectedVpc.cidr }} · {{ selectedVpc.vsi_name }} · Vsi-interface{{ selectedVpc.vsi_interface }}
                </div>
              </div>
              <span v-if="selectedVpc" :class="['chip', statusClass(selectedVpc.status)]">{{ selectedVpc.status }}</span>
            </div>

            <div v-if="selectedVpc" class="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
              <div class="rounded-xl bg-canvas-100 p-3" v-for="item in [
                { label: 'Tenant', value: selectedVpc.tenant_name },
                { label: 'Gateway', value: selectedVpc.gateway_ip },
                { label: 'Gateway MAC', value: selectedVpc.gateway_mac },
                { label: 'VLAN', value: selectedVpc.vlan_id },
                { label: 'VNI', value: selectedVpc.vni },
                { label: 'VSI', value: selectedVpc.vsi_name },
                { label: 'VSI IF', value: selectedVpc.vsi_interface },
                { label: 'Bindings', value: selectedBindings.length },
              ]" :key="item.label">
                <div class="text-[10px] uppercase tracking-wider text-ink-500">{{ item.label }}</div>
                <div class="mt-1 text-sm font-mono text-ink-900 break-all">{{ item.value ?? '-' }}</div>
              </div>
            </div>

            <div v-if="selectedVpc" class="mt-4 rounded-xl bg-canvas-100 ring-1 ring-canvas-300 px-4 py-3">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div class="text-xs font-semibold text-ink-900">{{ t('sdn.status_explain_title') }}</div>
                  <div class="text-xs text-ink-600 mt-1">{{ selectedStatusHint }}</div>
                </div>
                <button class="text-xs font-medium text-accent hover:underline" @click="guideOpen = true">{{ t('sdn.view_best_practice') }}</button>
              </div>
            </div>
          </section>

          <section class="panel p-5">
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <div class="text-sm font-semibold text-ink-900">{{ t('sdn.fabric_actions') }}</div>
                <div class="text-xs text-ink-500 mt-0.5">{{ t('sdn.fabric_actions_hint') }}</div>
              </div>
              <label class="inline-flex items-center gap-2 text-xs text-ink-700">
                <input v-model="autoApply" name="sdn_auto_apply" type="checkbox" class="size-4 rounded border-canvas-400 text-accent focus:ring-accent/30" />
                <span>{{ t('sdn.auto_apply') }}</span>
              </label>
            </div>
            <div v-if="selectedVpc" class="mb-3 rounded-xl bg-accent/8 ring-1 ring-accent/20 px-3 py-2 text-xs text-ink-700">
              {{ t('sdn.fabric_current_vpc', { name: selectedVpc.name, cidr: selectedVpc.cidr }) }}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-end">
              <label>
                <span class="text-xs font-medium text-ink-600">{{ t('sdn.target_leaf') }}</span>
                <select v-model="selectedDeviceId" name="sdn_target_device" class="input mt-1.5">
                  <option v-if="hasSdnTargets" :value="null">{{ t('sdn.all_leafs') }}</option>
                  <option v-else :value="null">{{ t('sdn.no_evpn_targets_short') }}</option>
                  <option v-for="d in sdnDevices" :key="d.id" :value="d.id">{{ d.name }} · {{ d.host }}</option>
                </select>
              </label>
              <button class="btn-outline" :disabled="busy === 'deploy' || !selectedVpc || !hasSdnTargets" @click="deployVpc">{{ t('sdn.deploy_plan') }}</button>
              <button class="btn-outline text-bad" :disabled="busy === 'withdraw' || !selectedVpc || !hasSdnTargets" @click="withdrawVpc">{{ t('sdn.withdraw_plan') }}</button>
            </div>
            <div v-if="!hasSdnTargets" class="mt-3 rounded-xl bg-warn/8 ring-1 ring-warn/25 px-3 py-2 text-xs text-ink-700">
              <span>{{ t('sdn.no_evpn_targets') }}</span>
              <RouterLink :to="{ name: 'devices' }" class="ml-2 font-medium text-accent hover:underline">{{ t('sdn.go_mark_device') }}</RouterLink>
            </div>
          </section>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <section class="panel p-5">
              <div class="mb-4">
                <div class="text-sm font-semibold text-ink-900">{{ t('sdn.create_section') }}</div>
                <div class="text-xs text-ink-500 mt-0.5">{{ t('sdn.create_section_hint') }}</div>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input v-model="tenantForm.name" name="sdn_tenant_name" class="input" :placeholder="t('sdn.tenant_name')" />
                <input v-model="tenantForm.description" name="sdn_tenant_description" class="input" :placeholder="t('sdn.description')" />
                <button class="btn-outline md:col-span-2" :disabled="busy === 'tenant'" @click="createTenant">{{ t('sdn.create_tenant') }}</button>
                <div class="md:col-span-2 h-px bg-canvas-300"></div>
                <input v-model="vpcForm.name" name="sdn_vpc_name" class="input" :placeholder="t('sdn.vpc_name')" />
                <select v-model="vpcForm.tenant_id" name="sdn_vpc_tenant" class="input">
                  <option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option>
                </select>
                <input v-model="vpcForm.cidr" name="sdn_vpc_cidr" class="input font-mono md:col-span-2" placeholder="192.168.10.0/24" />
                <input v-model="vpcForm.description" name="sdn_vpc_description" class="input md:col-span-2" :placeholder="t('sdn.description')" />
                <button class="btn-primary md:col-span-2" :disabled="busy === 'vpc'" @click="createVpc">{{ t('sdn.create_vpc') }}</button>
              </div>
            </section>

            <section class="panel p-5">
              <div class="mb-4">
                <div class="text-sm font-semibold text-ink-900">{{ t('sdn.access_section') }}</div>
                <div class="text-xs text-ink-500 mt-0.5">{{ t('sdn.access_section_hint') }}</div>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.target_leaf') }}</span>
                  <select v-model="selectedDeviceId" name="sdn_access_target_device" class="input mt-1.5" :disabled="!hasSdnTargets">
                    <option v-if="hasSdnTargets" :value="null">{{ t('sdn.select_evpn_target') }}</option>
                    <option v-else :value="null">{{ t('sdn.no_evpn_targets_short') }}</option>
                    <option v-for="d in sdnDevices" :key="d.id" :value="d.id">{{ d.name }} · {{ d.host }}</option>
                  </select>
                </label>
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.interface') }}</span>
                  <select v-model="bindForm.if_index" name="sdn_access_interface" class="input mt-1.5" :disabled="!selectedDeviceId || interfaces.length === 0" @change="onInterfaceChange">
                    <option value="">{{ interfaces.length === 0 ? t('sdn.no_interfaces_loaded') : t('sdn.select_interface') }}</option>
                    <option v-for="iface in interfaces" :key="iface.if_index" :value="iface.if_index">{{ iface.name }} · #{{ iface.if_index }}</option>
                  </select>
                </label>
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.if_index') }}</span>
                  <input v-model="bindForm.if_index" name="sdn_access_if_index" class="input mt-1.5 font-mono" inputmode="numeric" placeholder="3" :disabled="!selectedDeviceId" />
                </label>
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.interface_name') }}</span>
                  <input v-model="bindForm.interface_name" name="sdn_access_interface_name" class="input mt-1.5 font-mono" placeholder="GigabitEthernet1/0/3" :disabled="!selectedDeviceId" />
                </label>
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.service_instance') }}</span>
                  <input v-model="bindForm.service_instance" name="sdn_access_service_instance" class="input mt-1.5 font-mono" placeholder="3100" :disabled="!selectedDeviceId" />
                </label>
                <label>
                  <span class="text-xs font-medium text-ink-600">{{ t('sdn.expected_host') }}</span>
                  <input v-model="bindForm.expected_host_ip" name="sdn_access_expected_host" class="input mt-1.5 font-mono" placeholder="192.168.1.3" :disabled="!selectedDeviceId" />
                </label>
              </div>
              <div class="mt-3 text-[11px] text-ink-500">{{ t('sdn.interface_manual_hint') }}</div>
              <div class="mt-4 flex flex-wrap gap-2">
                <button class="btn-outline" :disabled="busy === 'binding' || !selectedVpc || !selectedDeviceId" @click="createBinding">{{ t('sdn.create_binding') }}</button>
                <button class="btn-primary" :disabled="busy === 'expansion' || !selectedVpc || !selectedDeviceId" @click="startExpansion">{{ t('sdn.start_expansion') }}</button>
                <button class="btn-outline" :disabled="busy === 'complete' || !latestExpansionBinding" @click="completeExpansion">{{ t('sdn.complete_expansion') }}</button>
              </div>
            </section>
          </div>

          <section class="panel p-5">
            <div class="text-sm font-semibold text-ink-900 mb-4">{{ t('sdn.overview_section') }}</div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div>
                <div class="text-xs font-semibold text-ink-700 mb-3">{{ t('sdn.port_bindings') }}</div>
                <div class="space-y-2 max-h-[260px] overflow-auto pr-1">
                  <div v-for="b in selectedBindings" :key="b.id" class="rounded-xl bg-canvas-100 p-3">
                    <div class="flex items-center justify-between gap-2">
                      <span class="text-sm font-semibold text-ink-900 break-all">{{ ifaceName(b) }}</span>
                      <span :class="['chip', statusClass(b.status)]">{{ b.status }}</span>
                    </div>
                    <div class="mt-1 text-xs text-ink-500 font-mono break-all">{{ deviceName(b.device_id) }} · SI {{ b.service_instance || '-' }} · VLAN {{ b.access_vlan || '-' }}</div>
                  </div>
                  <div v-if="selectedBindings.length === 0" class="text-sm text-ink-500 py-6 text-center">{{ t('sdn.no_bindings') }}</div>
                </div>
              </div>

              <div>
                <div class="text-xs font-semibold text-ink-700 mb-3">{{ t('sdn.deployments') }}</div>
                <div class="space-y-2 max-h-[260px] overflow-auto pr-1">
                  <div v-for="d in selectedDeployments" :key="d.id" class="rounded-xl bg-canvas-100 p-3">
                    <div class="flex items-center justify-between gap-2">
                      <span class="text-sm font-semibold text-ink-900">#{{ d.id }} · {{ d.action }}</span>
                      <span :class="['chip', statusClass(d.status)]">{{ d.status }}</span>
                    </div>
                    <div class="mt-1 text-xs text-ink-500 font-mono break-all">{{ deviceName(d.device_id) }} · {{ d.unit }}</div>
                  </div>
                  <div v-if="selectedDeployments.length === 0" class="text-sm text-ink-500 py-6 text-center">{{ t('sdn.no_deployments') }}</div>
                </div>
              </div>

              <div>
                <div class="text-xs font-semibold text-ink-700 mb-3">{{ t('sdn.validation') }}</div>
                <div v-if="validation" class="space-y-3">
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-xs text-ink-500">{{ t('sdn.validation_result') }}</span>
                    <span :class="['chip', statusClass(validation.validation_result)]">{{ validation.validation_result }}</span>
                  </div>
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-xs text-ink-500">{{ t('sdn.cached') }}</span>
                    <span class="text-xs font-mono text-ink-900">{{ validation.cached ? 'true' : 'false' }}</span>
                  </div>
                  <div class="rounded-xl bg-canvas-100 p-3 text-[11px] text-ink-600 font-mono max-h-[180px] overflow-auto whitespace-pre-wrap break-all">{{ JSON.stringify(validation.validation_details || validation.snapshot_data || validation, null, 2) }}</div>
                </div>
                <div v-else class="text-sm text-ink-500 py-6 text-center">{{ t('sdn.no_validation') }}</div>
              </div>
            </div>
          </section>

          <section class="panel p-5">
            <div class="text-sm font-semibold text-ink-900 mb-4">{{ t('sdn.light_topology') }}</div>
            <div class="relative h-[280px] rounded-2xl bg-canvas-100 ring-1 ring-canvas-300 overflow-hidden">
              <div class="absolute inset-0 opacity-[0.08]" style="background-image: linear-gradient(rgba(0,0,0,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.5) 1px, transparent 1px); background-size: 28px 28px;"></div>
              <div class="absolute top-5 left-1/2 -translate-x-1/2 rounded-xl bg-white px-4 py-2 shadow-sm ring-1 ring-canvas-300 text-center">
                <div class="text-xs font-semibold text-ink-900">{{ selectedVpc?.name || 'VPC' }}</div>
                <div class="text-[10px] text-ink-500 font-mono">VNI {{ selectedVpc?.vni || '-' }}</div>
              </div>
              <div class="absolute bottom-5 left-4 right-4 grid grid-cols-2 gap-2">
                <div v-for="d in sdnDevices.slice(0, 4)" :key="d.id" class="rounded-xl bg-white p-2 shadow-sm ring-1 ring-canvas-300">
                  <div class="text-[11px] font-semibold text-ink-900 truncate">{{ d.name }}</div>
                  <div class="text-[10px] text-ink-500 font-mono break-all">{{ d.host }}</div>
                  <div class="mt-1 h-1 rounded-full bg-accent/30"></div>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="guideOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/40 backdrop-blur-sm" @click.self="guideOpen = false">
          <div class="panel w-full max-w-4xl p-6 max-h-[86vh] overflow-auto">
            <div class="flex items-start justify-between gap-4 mb-5">
              <div>
                <div class="text-lg font-semibold text-ink-900">{{ t('sdn.best_practice_title') }}</div>
                <div class="text-sm text-ink-600 mt-1">{{ t('sdn.best_practice_desc') }}</div>
              </div>
              <button class="btn-soft !px-2 !py-1" @click="guideOpen = false">{{ t('common.close') }}</button>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <section v-for="section in guideSections" :key="section.title" class="rounded-xl bg-canvas-100 ring-1 ring-canvas-300 p-4">
                <div class="text-sm font-semibold text-ink-900">{{ section.title }}</div>
                <ol class="mt-3 space-y-3">
                  <li v-for="(step, index) in section.steps" :key="step" class="flex gap-3 text-sm text-ink-700">
                    <span class="size-6 shrink-0 rounded-full bg-white ring-1 ring-canvas-300 flex items-center justify-center text-[11px] font-mono text-accent">{{ index + 1 }}</span>
                    <span>{{ step }}</span>
                  </li>
                </ol>
              </section>
            </div>

            <div class="mt-4 rounded-xl bg-accent/8 ring-1 ring-accent/20 p-4 text-sm text-ink-700">
              <div class="font-semibold text-ink-900 mb-1">{{ t('sdn.guide_rule_title') }}</div>
              <div>{{ t('sdn.guide_rule_body') }}</div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </template>
</template>
