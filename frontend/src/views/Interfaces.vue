<script setup>
// v2.6 i18n: 所有硬编码中文 → t()（iface.* keys）
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md

import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import Select from '../components/Select.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import VpnInstanceBindModal from '../components/VpnInstanceBindModal.vue'
import Ipv4AddressEditModal from '../components/Ipv4AddressEditModal.vue'
import { deviceApi, interfaceApi, vpnApi } from '../api/index.js'
import { getIfaceStatusLabel } from '../utils/status.js'

const { t } = useI18n()

// 常用 VLAN 列表（V2.1 前端内置，后续可改为后端拉取）
const vlans = [
  { id: 1,   desc: '默认 VLAN' },
  { id: 10,  desc: '办公网' },
  { id: 20,  desc: '研发网' },
  { id: 30,  desc: '监控网' },
  { id: 100, desc: '业务 A' },
  { id: 200, desc: '业务 B' },
  { id: 300, desc: '业务 C' },
  { id: 400, desc: '业务 D' },
  { id: 500, desc: '业务 E' },
  { id: 1000, desc: '管理 VLAN' },
]

const loading = ref(true)
const error = ref('')
const devices = ref([])
const ifaces = ref([])
const selectedDeviceId = ref(null)
const search = ref('')
const filterMode = ref('all')
const showModal = ref(false)
const editingIface = ref(null)
const form = ref({ if_index: 0, mode: 'access', access_vlan: 100, allowed_vlans: [], pvid: 1, force: false })
const submitting = ref(false)
const submitMsg = ref('')

async function loadDevices() {
  loading.value = true
  error.value = ''
  const r = await deviceApi.list()
  if (!r.success) {
    error.value = r.error || t('iface.load_failed_devices')
    loading.value = false
    return
  }
  devices.value = r.data || []
  if (devices.value.length > 0) selectedDeviceId.value = devices.value[0].id
  loading.value = false
}

async function loadInterfaces() {
  if (!selectedDeviceId.value) {
    ifaces.value = []
    return
  }
  loading.value = true
  error.value = ''
  const r = await interfaceApi.list(selectedDeviceId.value)
  if (!r.success) {
    error.value = r.error || t('iface.load_failed_ifaces')
    ifaces.value = []
    loading.value = false
    return
  }
  ifaces.value = r.data || []
  loading.value = false
}

onMounted(loadDevices)

watch(selectedDeviceId, () => {
  loadInterfaces()
})

const selectedDevice = computed(() => devices.value.find(d => d.id === selectedDeviceId.value) || {})

const filtered = computed(() => {
  let list = ifaces.value
  if (filterMode.value !== 'all') list = list.filter(i => i.mode === filterMode.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(i => (i.name || '').toLowerCase().includes(q))
  }
  return list
})

const openConfig = (iface) => {
  editingIface.value = iface
  form.value = {
    if_index: iface.if_index,
    mode: iface.mode || 'access',
    access_vlan: iface.access_vlan || iface.pvid || 100,
    allowed_vlans: Array.isArray(iface.allowed_vlans) ? [...iface.allowed_vlans] : [],
    pvid: iface.pvid || 1,
    force: false
  }
  submitMsg.value = ''
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  submitMsg.value = ''
}

const submit = async () => {
  if (!editingIface.value || !selectedDeviceId.value) return
  submitting.value = true
  submitMsg.value = ''
  const payload = {
    if_index: form.value.if_index,
    mode: form.value.mode,
    access_vlan: form.value.mode === 'access' ? form.value.access_vlan : undefined,
    pvid: form.value.mode === 'trunk' ? form.value.pvid : undefined,
    allowed_vlans: form.value.mode === 'trunk' ? form.value.allowed_vlans : undefined,
    force: form.value.force
  }
  const r = await interfaceApi.applyConfig(selectedDeviceId.value, payload)
  submitting.value = false
  if (r.success) {
    submitMsg.value = r.data?.message || t('iface.applied')
    alert(submitMsg.value)
    showModal.value = false
    submitMsg.value = ''
    await loadInterfaces()
  } else {
    submitMsg.value = r.error || t('iface.apply_failed')
  }
}

const refresh = () => loadInterfaces()

const statusChip = (s) => s === 'up' ? 'chip-good' : s === 'down' ? 'chip-bad' : 'chip-mute'
const statusText = (s) => getIfaceStatusLabel(s)

// ============ v2.2 VPN instance 联动配置 ============

const vpnInstances = ref([])
const vpnLoading = ref(false)
const showVpnModal = ref(false)
const vpnTargetIface = ref(null)  // 当前操作的接口
const vpnModalMode = ref('create')  // 'create' | 'bind' | 'unbind'

async function loadVpnInstances() {
  if (!selectedDeviceId.value) {
    vpnInstances.value = []
    return
  }
  vpnLoading.value = true
  const r = await vpnApi.list(selectedDeviceId.value)
  vpnLoading.value = false
  if (r.success) {
    vpnInstances.value = r.data?.vpn_instances || []
  } else {
    vpnInstances.value = []
  }
}

watch(selectedDeviceId, () => {
  loadVpnInstances()
})

async function openCreateVpn(iface) {
  vpnTargetIface.value = iface
  vpnModalMode.value = 'create'
  // v2.2.1 fix-vpn-and-l2l3-ux-bugs: 打开 modal 前确保 VPN 列表已加载
  // 否则用户切完设备立刻点 + VPN，existingVpns 可能是空
  await loadVpnInstances()
  showVpnModal.value = true
}

async function openBindVpn(iface) {
  vpnTargetIface.value = iface
  vpnModalMode.value = 'bind'
  // v2.2.1 fix-vpn-and-l2l3-ux-bugs: 同上，bind 模式也需先加载列表
  await loadVpnInstances()
  showVpnModal.value = true
}

async function onVpnModalConfirm(_payload) {
  showVpnModal.value = false
  await loadInterfaces()
  await loadVpnInstances()
}

function closeVpnModal() {
  showVpnModal.value = false
  vpnTargetIface.value = null
}

// 解绑流程：先弹 ConfirmModal 二次确认
const showUnbindConfirm = ref(false)
const unbindTarget = ref(null)
function requestUnbind(iface) {
  unbindTarget.value = iface
  showUnbindConfirm.value = true
}
async function confirmUnbind() {
  const iface = unbindTarget.value
  if (!iface || !selectedDeviceId.value) return
  showUnbindConfirm.value = false
  const r = await vpnApi.unbindInterface(selectedDeviceId.value, iface.if_index)
  if (r.success) {
    await loadInterfaces()
    await loadVpnInstances()
  } else {
    alert(r.error || t('iface.vpn_unbind_failed'))
  }
}
function cancelUnbind() {
  showUnbindConfirm.value = false
  unbindTarget.value = null
}

const layerChip = (l) => l === 'L3' ? 'chip-info' : 'chip-mute'

// v24-feat-bridge-button: 判断是否物理口（与后端 _looks_like_physical_port 正则一致）
// 用途：L3 物理口（GE/TE 被切到 route）显示"改二层"按钮，L3 虚接口不显示
// 后端护栏兜底（_looks_like_physical_port + L3_NAME_PATTERN 双重拦）
function isPhysicalPort(name) {
  if (!name) return false
  return /^(GigabitEthernet|TenGigabit|Twenty-FiveGigE|FortyGigE|HundredGigE|GE|TE|FGE|HGE|XGigabitEthernet|Eth|Bridge-Aggregation|Route-Aggregation|M-GigabitEthernet|MP|XGigabit)/i.test(name)
}

// ============ v2.2.2 patch (fix-vpn-edit-capabilities) ============
// 改 link type (mode)：弹 ConfirmModal 二次确认
const showLinkTypeConfirm = ref(false)
const linkTypeChange = ref({ iface: null, newMode: '', force: false })
const linkTypeSubmitting = ref(false)
const linkTypeErr = ref('')

// 改 IP：弹 Ipv4AddressEditModal
const showIpModal = ref(false)
const ipTargetIface = ref(null)

function requestChangeLinkType(iface, newMode) {
  // 预校验：当前 mode == newMode 直接跳过二次确认
  if ((iface.mode || 'access') === newMode) {
    alert(t('iface.same_mode_alert', { name: iface.name, mode: newMode }))
    return
  }
  linkTypeChange.value = { iface, newMode, force: !!iface.protected }
  linkTypeErr.value = ''
  showLinkTypeConfirm.value = true
}

async function confirmChangeLinkType() {
  const { iface, newMode, force } = linkTypeChange.value
  if (!iface || !selectedDeviceId.value) return
  linkTypeSubmitting.value = true
  linkTypeErr.value = ''
  const r = await interfaceApi.changeLinkType(
    selectedDeviceId.value, iface.if_index, newMode, force
  )
  linkTypeSubmitting.value = false
  if (!r.success) {
    linkTypeErr.value = r.error || t('iface.linktype_failed')
    return
  }
  showLinkTypeConfirm.value = false
  await loadInterfaces()
}

function cancelChangeLinkType() {
  if (linkTypeSubmitting.value) return
  showLinkTypeConfirm.value = false
  linkTypeChange.value = { iface: null, newMode: '', force: false }
  linkTypeErr.value = ''
}

// ============ v2.3: 切换 L2/L3 层级（bridge/route） ============
const showLinkModeConfirm = ref(false)
const linkModeChange = ref({ iface: null, mode: '', message: '', force: false, reason_code: null, suggested_action: null })
const linkModeSubmitting = ref(false)
const linkModeErr = ref('')
// v24-bugfix: 护栏拒时显示 reason_code + suggested_action
const linkModeGuardInfo = ref(null)  // { reason_code, suggested_action, error }

async function requestSwitchLinkMode(iface, targetMode = 'route') {
  // v24-feat-bridge-button: targetMode 'route'=改三层 | 'bridge'=改二层
  // 前端预检（兜底，按钮 v-if 已挡）
  // - 改三层：L3 接口不能再改三层
  // - 改二层：L3 虚接口（LoopBack/Vsi/Vlan）不支持 link-mode
  if (targetMode === 'route' && iface.layer === 'L3') {
    linkModeGuardInfo.value = {
      reason_code: 'L3_INTERFACE',
      suggested_action: '此接口已是 L3，无法再改三层。如需配置 IP，请用"改 IP"按钮。',
      error: `${iface.name} 已经是 L3 接口`,
    }
    return
  }
  if (targetMode === 'bridge' && !isPhysicalPort(iface.name)) {
    linkModeGuardInfo.value = {
      reason_code: 'PHYSICAL_ONLY',
      suggested_action: '此接口不是物理接口（可能是 LoopBack / Vsi / Vlan / NULL0 等虚接口），不支持切换 L2/L3 层级。',
      error: `${iface.name} 不是物理接口，不支持切层级`,
    }
    return
  }

  linkModeErr.value = ''
  linkModeGuardInfo.value = null
  linkModeSubmitting.value = true

  // 先调用 force=false 获取确认消息
  const r = await interfaceApi.setLinkMode(selectedDeviceId.value, iface.if_index, targetMode, false)
  linkModeSubmitting.value = false

  if (!r.success) {
    // v24-bugfix: 优先用 reason_code + suggested_action
    const data = r.data
    if (data && data.reason_code) {
      linkModeGuardInfo.value = {
        reason_code: data.reason_code,
        suggested_action: data.suggested_action || '请检查接口状态后重试',
        error: r.error || t('iface.linkmode_failed'),
      }
    } else {
      linkModeErr.value = r.error || t('iface.linkmode_failed')
    }
    return
  }

  const data = r.data
  if (data && data.confirmed === false) {
    // 后端返回确认提示，弹 ConfirmModal
    const targetLayerText = targetMode === 'route' ? t('iface.linkmode_layer_l3') : t('iface.linkmode_layer_l2')
    linkModeChange.value = {
      iface,
      mode: targetMode,
      message: data.message || t('iface.linkmode_default_msg', { name: iface.name, layer: targetLayerText }),
      force: true,
      reason_code: null,
      suggested_action: null,
    }
    showLinkModeConfirm.value = true
  } else {
    // 直接成功（force=true 路径）
    await loadInterfaces()
  }
}

async function confirmSwitchLinkMode() {
  const { iface, mode } = linkModeChange.value
  if (!iface || !selectedDeviceId.value) return
  linkModeSubmitting.value = true
  linkModeErr.value = ''
  linkModeGuardInfo.value = null

  const r = await interfaceApi.setLinkMode(selectedDeviceId.value, iface.if_index, mode, true)
  linkModeSubmitting.value = false

  if (!r.success) {
    // v24-bugfix: 强制执行失败也走 reason_code
    const data = r.data
    if (data && data.reason_code) {
      linkModeGuardInfo.value = {
        reason_code: data.reason_code,
        suggested_action: data.suggested_action || '请检查接口状态后重试',
        error: r.error || t('iface.linkmode_failed'),
      }
      showLinkModeConfirm.value = false
    } else {
      linkModeErr.value = r.error || t('iface.linkmode_failed')
    }
    return
  }
  showLinkModeConfirm.value = false
  linkModeChange.value = { iface: null, mode: '', message: '', force: false, reason_code: null, suggested_action: null }
  await loadInterfaces()
}

function cancelSwitchLinkMode() {
  if (linkModeSubmitting.value) return
  showLinkModeConfirm.value = false
  linkModeChange.value = { iface: null, mode: '', message: '', force: false, reason_code: null, suggested_action: null }
  linkModeErr.value = ''
}

function dismissLinkModeGuard() {
  linkModeGuardInfo.value = null
  linkModeErr.value = ''
}

function openIpModal(iface) {
  ipTargetIface.value = iface
  showIpModal.value = true
}

async function onIpModalConfirm() {
  showIpModal.value = false
  await loadInterfaces()
}

// 改 link type / link mode confirm message 组装
const linkTypeMessage = computed(() => {
  const errPart = linkTypeErr.value ? linkTypeErr.value + '\n\n' : ''
  const iface = linkTypeChange.value.iface
  const newMode = linkTypeChange.value.newMode
  if (!iface) return ''
  return errPart +
    t('iface.linktype_iface_info', { name: iface.name, idx: iface.if_index }) + '\n' +
    t('iface.linktype_message_current', { mode: iface.mode || 'access' }) + '\n' +
    t('iface.linktype_message_target', { mode: newMode }) + '\n\n' +
    t('iface.linktype_warn') + '\n' +
    (newMode === 'trunk' ? t('iface.linktype_warn_a2t') + '\n' : t('iface.linktype_warn_t2a') + '\n') +
    (linkTypeChange.value.force ? '\n' + t('iface.linktype_force_warn') + '\n' : '\n') +
    '\n' + t('iface.linktype_irreversible')
})

const linkModeMessage = computed(() => {
  const errPart = linkModeErr.value ? linkModeErr.value + '\n\n' : ''
  const iface = linkModeChange.value.iface
  const mode = linkModeChange.value.mode
  if (!iface) return ''
  const targetLayerText = mode === 'bridge' ? t('iface.linkmode_layer_l2') : t('iface.linkmode_layer_l3')
  return errPart +
    `${linkModeChange.value.message || ''}\n\n` +
    t('iface.linkmode_iface_info', { name: iface.name, idx: iface.if_index }) + '\n' +
    t('iface.linkmode_message_current', { layer: iface.layer || 'L2' }) + '\n' +
    t('iface.linkmode_message_target', { layer: targetLayerText }) + '\n\n' +
    t('iface.linkmode_warn') + '\n' +
    (mode === 'route' ? t('iface.linkmode_warn_b2r') + '\n' : t('iface.linkmode_warn_r2b') + '\n') +
    '\n' + t('iface.linkmode_irreversible')
})
</script>

<template>
  <div v-if="loading && devices.length === 0" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('dashboard.kpi_loading') }}</div>
  <div v-else-if="error && devices.length === 0" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">{{ t('iface.load_failed_devices') }}</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDevices">{{ t('iface.retry') }}</button>
    </div>
  </div>
  <template v-else>
    <PageHeader :title="t('iface.title')" :subtitle="t('iface.subtitle', { n: devices.length })">
      <template #actions>
        <Select
          v-model="selectedDeviceId"
          :options="devices"
          :custom-label="(d) => d.name"
          :sub-label="(d) => d.host"
          width="w-60"
        />
        <button class="btn-outline" @click="refresh">
          <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
          {{ t('iface.refresh') }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="search" :placeholder="t('iface.search_placeholder')" class="input pl-9" />
        </div>
        <div class="flex items-center gap-1">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'all'">{{ t('iface.filter_all') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'access' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'access'">Access</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'trunk' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'trunk'">Trunk</button>
        </div>
        <div class="text-[10px] text-ink-500 ml-auto font-mono">{{ t('iface.device_label', { name: selectedDevice.name || '—', n: filtered.length }) }}</div>
      </div>

      <!-- v24-bugfix-ui-feedback-and-loopback: 顶部说明 -->
      <!-- v24-feat-bridge-button: 更新文案，L3 物理口可改回二层 -->
      <div class="panel px-4 py-2.5 bg-canvas-100 border-canvas-300 flex items-start gap-2.5 text-xs text-ink-700">
        <span class="text-accent mt-0.5">{{ t('iface.notice_title') }}</span>
        <div class="flex-1 leading-relaxed">
          {{ t('iface.notice_body') }}
        </div>
      </div>

      <div v-if="error" class="panel p-6 border border-bad/30 bg-bad/5">
        <div class="text-bad font-medium">{{ t('iface.load_failed_ifaces') }}</div>
        <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
        <button class="btn-outline mt-3" @click="loadInterfaces">{{ t('iface.retry') }}</button>
      </div>

      <div v-else-if="filtered.length === 0 && !loading" class="panel p-12 text-center text-sm text-ink-500">{{ t('iface.no_ifaces') }}</div>

      <div v-else class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_iface') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_layer') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_mode') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_ip_vpn') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_pvid_vlan') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_status') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('iface.col_protected') }}</th>
              <th class="px-4 py-3 text-right font-medium w-64">{{ t('iface.col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-for="i in filtered" :key="i.if_index" class="hover:bg-canvas-100 transition">
              <td class="px-4 py-3 font-mono text-xs">
                <span class="text-ink-900">{{ i.name }}</span>
                <span class="text-ink-500 ml-2">#{{ i.if_index }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="layerChip(i.layer)">{{ i.layer || 'L2' }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="i.mode === 'trunk' ? 'chip-info' : 'chip-mute'">{{ i.mode }}</span>
              </td>
              <td class="px-4 py-3 font-mono text-xs">
                <div v-if="i.layer === 'L3' && i.ip_addresses && i.ip_addresses.length" class="text-ink-900">
                  {{ i.ip_addresses.join(', ') }}
                </div>
                <div v-else class="text-ink-500">—</div>
                <div v-if="i.vpn_instance" class="text-accent mt-0.5">
                  🔒 {{ i.vpn_instance }}
                </div>
                <div v-else-if="i.layer === 'L3'" class="text-ink-500 mt-0.5">{{ t('iface.no_vpn') }}</div>
              </td>
              <td class="px-4 py-3 font-mono text-xs">
                <span class="text-ink-900">{{ t('iface.pvid', { n: i.pvid }) }}</span>
                <span v-if="i.mode === 'trunk' && i.allowed_vlans && i.allowed_vlans.length" class="text-ink-500 ml-2">[{{ i.allowed_vlans.join(', ') }}]</span>
              </td>
              <td class="px-4 py-3">
                <span :class="statusChip(i.status)">
                  <span :class="['size-1.5 rounded-full', i.status === 'up' ? 'bg-good' : i.status === 'down' ? 'bg-bad' : 'bg-ink-400']"></span>
                  {{ statusText(i.status) }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="i.protected" class="chip-bad !text-[10px]">{{ t('iface.protected_chip') }}</span>
                <span v-else class="text-[10px] text-ink-500">—</span>
              </td>
              <td class="px-4 py-3 text-right space-x-1">
                <button @click="openConfig(i)" class="btn-soft !text-xs !px-2.5 !py-1">{{ t('iface.btn_config') }}</button>
                <!-- v2.2.2 patch: L2 接口才显示"改模式"按钮 -->
                <button
                  v-if="i.layer !== 'L3'"
                  @click="requestChangeLinkType(i, i.mode === 'access' ? 'trunk' : 'access')"
                  class="btn-soft !text-xs !px-2.5 !py-1"
                >
                  {{ t('iface.btn_change_mode', { mode: i.mode === 'access' ? 'Trunk' : 'Access' }) }}
                </button>
                <!-- v2.3: 切换 L2/L3 层级 -->
                <!-- v24-feat-bridge-button: L2 物理口显示"改三层"，L3 物理口显示"改二层" -->
                <button
                  v-if="i.layer !== 'L3'"
                  @click="requestSwitchLinkMode(i, 'route')"
                  class="btn-soft !text-xs !px-2.5 !py-1"
                >
                  {{ t('iface.btn_to_l3') }}
                </button>
                <button
                  v-if="i.layer === 'L3' && isPhysicalPort(i.name)"
                  @click="requestSwitchLinkMode(i, 'bridge')"
                  class="btn-soft !text-xs !px-2.5 !py-1"
                >
                  {{ t('iface.btn_to_l2') }}
                </button>
                <!-- v2.2.2 patch: L3 接口才显示"改 IP"按钮 -->
                <button
                  v-if="i.layer === 'L3'"
                  @click="openIpModal(i)"
                  class="btn-soft !text-xs !px-2.5 !py-1"
                >
                  {{ t('iface.btn_change_ip') }}
                </button>
                <button v-if="i.vpn_instance" @click="requestUnbind(i)" class="btn-soft !text-xs !px-2.5 !py-1">{{ t('iface.btn_unbind_vpn') }}</button>
                <button v-else-if="i.layer === 'L3'" @click="openBindVpn(i)" class="btn-soft !text-xs !px-2.5 !py-1">{{ t('iface.btn_bind_vpn') }}</button>
                <button v-if="i.layer === 'L3' && !i.vpn_instance" @click="openCreateVpn(i)" class="btn-soft !text-xs !px-2.5 !py-1">{{ t('iface.btn_create_vpn') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/40 backdrop-blur-sm" @click.self="closeModal">
          <div class="panel w-full max-w-md p-6">
            <div class="flex items-start justify-between mb-4">
              <div>
                <div class="text-base font-semibold text-ink-900">{{ t('iface.modal_title') }}</div>
                <div class="text-xs text-ink-500 font-mono mt-0.5">{{ editingIface ? t('iface.modal_iface_id', { name: editingIface.name, idx: editingIface.if_index }) : '' }}</div>
              </div>
              <button @click="closeModal" class="btn-soft !p-1.5">✕</button>
            </div>

            <div v-if="editingIface?.protected" class="mb-4 p-3 rounded-xl bg-bad/8 border border-bad/30 flex gap-2.5">
              <span class="text-bad text-base">🛡</span>
              <div class="text-xs text-bad flex-1">
                <div class="font-semibold">{{ t('iface.protected_warn_title') }}</div>
                <div class="text-bad/80 mt-0.5">{{ t('iface.protected_warn_desc') }}</div>
              </div>
            </div>

            <div v-if="submitMsg" class="mb-4 p-3 rounded-xl bg-bad/8 border border-bad/30 text-xs text-bad">
              {{ submitMsg }}
            </div>

            <div class="space-y-4">
              <div>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">{{ t('iface.label_mode') }}</label>
                <div class="grid grid-cols-2 gap-1.5">
                  <button :class="['btn-ghost', form.mode === 'access' && 'ring-2 ring-accent']" @click="form.mode = 'access'">Access</button>
                  <button :class="['btn-ghost', form.mode === 'trunk' && 'ring-2 ring-accent']" @click="form.mode = 'trunk'">Trunk</button>
                </div>
              </div>

              <div v-if="form.mode === 'access'">
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">{{ t('iface.label_access_vlan') }}</label>
                <select v-model.number="form.access_vlan" class="input">
                  <option v-for="v in vlans" :key="v.id" :value="v.id">VLAN {{ v.id }} · {{ v.desc }}</option>
                </select>
              </div>

              <div v-else>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">{{ t('iface.label_trunk_pvid') }}</label>
                <select v-model.number="form.pvid" class="input mb-3">
                  <option v-for="v in vlans" :key="v.id" :value="v.id">VLAN {{ v.id }}</option>
                </select>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">{{ t('iface.label_allowed_vlans') }}</label>
                <div class="flex flex-wrap gap-1.5">
                  <label v-for="v in vlans" :key="v.id" class="px-2.5 py-1 text-xs font-medium rounded-full cursor-pointer transition"
                    :class="form.allowed_vlans.includes(v.id) ? 'bg-accent text-white' : 'bg-canvas-200 text-ink-700 hover:bg-canvas-300'">
                    <input type="checkbox" :value="v.id" v-model="form.allowed_vlans" class="sr-only" />
                    {{ v.id }}
                  </label>
                </div>
              </div>

              <label class="flex items-center gap-2 cursor-pointer select-none">
                <input type="checkbox" v-model="form.force" class="rounded border-canvas-400 text-accent focus:ring-accent/40" />
                <span class="text-sm text-ink-900">{{ t('iface.label_force') }}</span>
              </label>
            </div>

            <div class="flex justify-end gap-2 mt-6">
              <button @click="closeModal" class="btn-ghost">{{ t('iface.btn_cancel') }}</button>
              <button @click="submit" :disabled="submitting || (editingIface?.protected && !form.force)" class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed">
                {{ submitting ? t('iface.btn_applying') : t('iface.btn_apply') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- v2.2 VPN instance 创建/绑定 Modal -->
    <VpnInstanceBindModal
      v-if="showVpnModal"
      :visible="showVpnModal"
      :device-id="selectedDeviceId"
      :mode="vpnModalMode"
      :target-iface="vpnTargetIface"
      :existing-vpns="vpnInstances"
      @confirm="onVpnModalConfirm"
      @cancel="closeVpnModal"
    />

    <!-- v2.2 VPN 解绑二次确认 -->
    <ConfirmModal
      v-if="showUnbindConfirm"
      :open="showUnbindConfirm"
      :title="t('iface.vpn_unbind_title')"
      :message="unbindTarget ? t('iface.vpn_unbind_message', { name: unbindTarget.name, vpn: unbindTarget.vpn_instance }) : ''"
      :confirm-text="t('iface.vpn_unbind_confirm')"
      :cancel-text="t('iface.btn_cancel')"
      variant="danger"
      @confirm="confirmUnbind"
      @cancel="cancelUnbind"
    />

    <!-- v2.2.2 patch: 改 link type 二次确认 -->
    <ConfirmModal
      v-if="showLinkTypeConfirm"
      :open="showLinkTypeConfirm"
      :title="t('iface.linktype_modal_title', { mode: linkTypeChange.newMode })"
      :message="linkTypeMessage"
      :confirm-text="linkTypeSubmitting ? t('iface.linktype_applying') : t('iface.linktype_confirm')"
      :busy="linkTypeSubmitting"
      variant="danger"
      @confirm="confirmChangeLinkType"
      @cancel="cancelChangeLinkType"
    />

    <!-- v2.3: 切换 L2/L3 层级 ConfirmModal -->
    <ConfirmModal
      v-if="showLinkModeConfirm"
      :open="showLinkModeConfirm"
      :title="t('iface.linkmode_modal_title', { layer: linkModeChange.mode === 'bridge' ? t('iface.linkmode_layer_l2') : t('iface.linkmode_layer_l3') })"
      :message="linkModeMessage"
      :confirm-text="linkModeSubmitting ? t('iface.linkmode_executing') : t('iface.linkmode_confirm')"
      :busy="linkModeSubmitting"
      variant="danger"
      @confirm="confirmSwitchLinkMode"
      @cancel="cancelSwitchLinkMode"
    />

    <!-- v24-bugfix: 切层级护栏拒时弹窗，告知 reason_code + suggested_action -->
    <ConfirmModal
      v-if="linkModeGuardInfo"
      :open="!!linkModeGuardInfo"
      :title="t('iface.linkmode_guard_title', { code: linkModeGuardInfo.reason_code })"
      :message="(linkModeGuardInfo.error || t('iface.linkmode_failed')) + '\n\n' +
        t('iface.linkmode_guard_suggestion') + '\n' +
        (linkModeGuardInfo.suggested_action || '请检查接口状态后重试')"
      :confirm-text="t('iface.linkmode_guard_ack')"
      :cancel-text="t('iface.linkmode_guard_close')"
      variant="danger"
      @confirm="dismissLinkModeGuard"
      @cancel="dismissLinkModeGuard"
    />

    <!-- v2.2.2 patch: 改 IP modal（内部自带二次确认） -->
    <Ipv4AddressEditModal
      v-if="showIpModal && ipTargetIface"
      :visible="showIpModal"
      :device-id="selectedDeviceId"
      :iface="ipTargetIface"
      @confirm="onIpModalConfirm"
      @cancel="() => { showIpModal = false }"
    />
  </template>
</template>

<style>
.modal-enter-active, .modal-leave-active { transition: opacity .2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
