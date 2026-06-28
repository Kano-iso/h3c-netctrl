<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import Select from '../components/Select.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import VpnInstanceBindModal from '../components/VpnInstanceBindModal.vue'
import { deviceApi, interfaceApi, vpnApi } from '../api/index.js'

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
    error.value = r.error || '加载失败'
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
    error.value = r.error || '加载接口失败'
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
    submitMsg.value = r.data?.message || '接口配置已下发'
    alert(submitMsg.value)
    showModal.value = false
    submitMsg.value = ''
    await loadInterfaces()
  } else {
    submitMsg.value = r.error || '应用失败'
  }
}

const refresh = () => loadInterfaces()

const statusChip = (s) => s === 'up' ? 'chip-good' : s === 'down' ? 'chip-bad' : 'chip-mute'
const statusText = (s) => s === 'up' ? 'UP' : s === 'down' ? 'DOWN' : '—'

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

function openCreateVpn(iface) {
  vpnTargetIface.value = iface
  vpnModalMode.value = 'create'
  showVpnModal.value = true
}

function openBindVpn(iface) {
  vpnTargetIface.value = iface
  vpnModalMode.value = 'bind'
  showVpnModal.value = true
}

async function onVpnModalConfirm(payload) {
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
    alert(r.error || '解绑失败')
  }
}
function cancelUnbind() {
  showUnbindConfirm.value = false
  unbindTarget.value = null
}

const layerChip = (l) => l === 'L3' ? 'chip-info' : 'chip-mute'
</script>

<template>
  <div v-if="loading && devices.length === 0" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">加载中…</div>
  <div v-else-if="error && devices.length === 0" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">设备列表加载失败</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDevices">重试</button>
    </div>
  </div>
  <template v-else>
    <PageHeader title="接口管理" :subtitle="`${devices.length} 台设备 · Access / Trunk 联动配置 · 受保护接口需 force=true`">
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
          刷新
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="search" placeholder="搜索接口…" class="input pl-9" />
        </div>
        <div class="flex items-center gap-1">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'all'">全部</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'access' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'access'">Access</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterMode === 'trunk' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterMode = 'trunk'">Trunk</button>
        </div>
        <div class="text-[10px] text-ink-500 ml-auto font-mono">设备：{{ selectedDevice.name || '—' }} · 共 {{ filtered.length }} 个接口</div>
      </div>

      <div v-if="error" class="panel p-6 border border-bad/30 bg-bad/5">
        <div class="text-bad font-medium">接口加载失败</div>
        <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
        <button class="btn-outline mt-3" @click="loadInterfaces">重试</button>
      </div>

      <div v-else-if="filtered.length === 0 && !loading" class="panel p-12 text-center text-sm text-ink-500">该设备暂无接口数据</div>

      <div v-else class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 text-left font-medium">接口</th>
              <th class="px-4 py-3 text-left font-medium">层级</th>
              <th class="px-4 py-3 text-left font-medium">模式</th>
              <th class="px-4 py-3 text-left font-medium">IP / VPN</th>
              <th class="px-4 py-3 text-left font-medium">PVID / 允许 VLAN</th>
              <th class="px-4 py-3 text-left font-medium">状态</th>
              <th class="px-4 py-3 text-left font-medium">保护</th>
              <th class="px-4 py-3 text-right font-medium w-48">操作</th>
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
                <div v-else-if="i.layer === 'L3'" class="text-ink-500 mt-0.5">无 VPN</div>
              </td>
              <td class="px-4 py-3 font-mono text-xs">
                <span class="text-ink-900">PVID {{ i.pvid }}</span>
                <span v-if="i.mode === 'trunk' && i.allowed_vlans && i.allowed_vlans.length" class="text-ink-500 ml-2">[{{ i.allowed_vlans.join(', ') }}]</span>
              </td>
              <td class="px-4 py-3">
                <span :class="statusChip(i.status)">
                  <span :class="['size-1.5 rounded-full', i.status === 'up' ? 'bg-good' : i.status === 'down' ? 'bg-bad' : 'bg-ink-400']"></span>
                  {{ statusText(i.status) }}
                </span>
              </td>
              <td class="px-4 py-3">
                <span v-if="i.protected" class="chip-bad !text-[10px]">🛡 受保护</span>
                <span v-else class="text-[10px] text-ink-500">—</span>
              </td>
              <td class="px-4 py-3 text-right space-x-1">
                <button @click="openConfig(i)" class="btn-soft !text-xs !px-2.5 !py-1">配置</button>
                <button v-if="i.vpn_instance" @click="requestUnbind(i)" class="btn-soft !text-xs !px-2.5 !py-1">解绑 VPN</button>
                <button v-else-if="i.layer === 'L3'" @click="openBindVpn(i)" class="btn-soft !text-xs !px-2.5 !py-1">绑 VPN</button>
                <button v-if="i.layer === 'L3' && !i.vpn_instance" @click="openCreateVpn(i)" class="btn-soft !text-xs !px-2.5 !py-1">+ VPN</button>
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
                <div class="text-base font-semibold text-ink-900">配置接口</div>
                <div class="text-xs text-ink-500 font-mono mt-0.5">{{ editingIface?.name }} · if_index {{ editingIface?.if_index }}</div>
              </div>
              <button @click="closeModal" class="btn-soft !p-1.5">✕</button>
            </div>

            <div v-if="editingIface?.protected" class="mb-4 p-3 rounded-xl bg-bad/8 border border-bad/30 flex gap-2.5">
              <span class="text-bad text-base">🛡</span>
              <div class="text-xs text-bad flex-1">
                <div class="font-semibold">该接口已被标记为受保护</div>
                <div class="text-bad/80 mt-0.5">保护口通常是上行/管理口，误改可能导致设备失联。需勾选 force 才能继续。</div>
              </div>
            </div>

            <div v-if="submitMsg" class="mb-4 p-3 rounded-xl bg-bad/8 border border-bad/30 text-xs text-bad">
              {{ submitMsg }}
            </div>

            <div class="space-y-4">
              <div>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">模式</label>
                <div class="grid grid-cols-2 gap-1.5">
                  <button :class="['btn-ghost', form.mode === 'access' && 'ring-2 ring-accent']" @click="form.mode = 'access'">Access</button>
                  <button :class="['btn-ghost', form.mode === 'trunk' && 'ring-2 ring-accent']" @click="form.mode = 'trunk'">Trunk</button>
                </div>
              </div>

              <div v-if="form.mode === 'access'">
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">Access VLAN</label>
                <select v-model.number="form.access_vlan" class="input">
                  <option v-for="v in vlans" :key="v.id" :value="v.id">VLAN {{ v.id }} · {{ v.desc }}</option>
                </select>
              </div>

              <div v-else>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">Trunk PVID</label>
                <select v-model.number="form.pvid" class="input mb-3">
                  <option v-for="v in vlans" :key="v.id" :value="v.id">VLAN {{ v.id }}</option>
                </select>
                <label class="text-xs font-medium text-ink-700 mb-1.5 block">允许 VLAN</label>
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
                <span class="text-sm text-ink-900">Force (强制覆盖保护)</span>
              </label>
            </div>

            <div class="flex justify-end gap-2 mt-6">
              <button @click="closeModal" class="btn-ghost">取消</button>
              <button @click="submit" :disabled="submitting || (editingIface?.protected && !form.force)" class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed">
                {{ submitting ? '下发中…' : '应用' }}
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
      title="解绑 VPN instance"
      :message="`确认要解绑接口 ${unbindTarget?.name} 的 VPN instance ${unbindTarget?.vpn_instance} 吗？`"
      confirm-text="确认解绑"
      variant="danger"
      @confirm="confirmUnbind"
      @cancel="cancelUnbind"
    />
  </template>
</template>

<style>
.modal-enter-active, .modal-leave-active { transition: opacity .2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
