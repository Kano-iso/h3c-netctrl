<script setup>
import { ref, computed, onMounted } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import DeviceFormModal from '../components/DeviceFormModal.vue'
import AssetEditModal from '../components/AssetEditModal.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import { deviceApi, assetApi } from '../api/index.js'
import { getStatusChip, getStatusLabel } from '../utils/status.js'

const loading = ref(true)
const error = ref('')
const devices = ref([])

const search = ref('')
const filterStatus = ref('all')
const filterRole = ref('all')
const selected = ref(new Set())
const testing = ref(new Set())

// Modal state
const deviceFormOpen = ref(false)
const deviceFormMode = ref('create') // 'create' | 'edit'
const editingDevice = ref(null)

const deleteConfirmOpen = ref(false)
const deletingDevice = ref(null)
const deleteBusy = ref(false)

const assetEditOpen = ref(false)
const editingAsset = ref({ deviceId: null, deviceName: '', asset: {} })

async function loadDevices() {
  loading.value = true
  error.value = ''
  const r = await deviceApi.list()
  if (!r.success) {
    error.value = r.error || '加载失败'
    loading.value = false
    return
  }
  const list = r.data || []
  const enriched = await Promise.all(
    list.map(async (d) => {
      const ar = await assetApi.get(d.id)
      const a = ar.success ? ar.data : {}
      return {
        id: d.id,
        name: d.name,
        host: d.host,
        port: d.port,
        model: a.model || '—',
        software: a.software_package || '—',
        status: a.status || null,
        location: a.location || '',
        tags: a.tags ? a.tags.split(',').map(s => s.trim()).filter(Boolean) : [],
        protected: d.protected_interfaces || [],
        asset: a,
      }
    })
  )
  devices.value = enriched
  loading.value = false
}

onMounted(loadDevices)

const filtered = computed(() => {
  return devices.value.filter(d => {
    if (filterStatus.value !== 'all' && d.status !== filterStatus.value) return false
    if (filterRole.value !== 'all' && filterRole.value === 'spine' && d.tags.includes('核心') === false) return false
    if (search.value && !`${d.name} ${d.host} ${d.model}`.toLowerCase().includes(search.value.toLowerCase())) return false
    return true
  })
})

const toggle = (id) => {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
  selected.value = new Set(selected.value)
}
const allSelected = computed(() => selected.value.size === filtered.value.length && filtered.value.length > 0)
const toggleAll = () => {
  if (allSelected.value) selected.value = new Set()
  else selected.value = new Set(filtered.value.map(d => d.id))
}

async function testConnection(id) {
  if (testing.value.has(id)) return
  testing.value.add(id)
  testing.value = new Set(testing.value)
  const r = await deviceApi.test(id)
  testing.value.delete(id)
  testing.value = new Set(testing.value)
  if (r.success) {
    alert(`设备 ${id} 连接成功`)
  } else {
    alert(`设备 ${id} 连接失败：${r.error || '未知错误'}`)
  }
  await loadDevices()
}

const statusChip = (s) => getStatusChip(s)
const statusLabel = (s) => getStatusLabel(s)

// 新增设备
const onCreate = () => {
  deviceFormMode.value = 'create'
  editingDevice.value = null
  deviceFormOpen.value = true
}

// 编辑设备
const onEdit = (d) => {
  deviceFormMode.value = 'edit'
  editingDevice.value = d
  deviceFormOpen.value = true
}

// 删除设备
const onDeleteClick = (d) => {
  deletingDevice.value = d
  deleteConfirmOpen.value = true
}
const onDeleteConfirm = async () => {
  if (!deletingDevice.value) return
  deleteBusy.value = true
  const r = await deviceApi.delete(deletingDevice.value.id)
  deleteBusy.value = false
  if (r.success) {
    deleteConfirmOpen.value = false
    deletingDevice.value = null
    await loadDevices()
  } else {
    alert(`删除失败：${r.error || '未知错误'}`)
  }
}

// 编辑资产
const onEditAsset = (d) => {
  editingAsset.value = { deviceId: d.id, deviceName: d.name, asset: d.asset || {} }
  assetEditOpen.value = true
}
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">加载中…</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">设备列表加载失败</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDevices">重试</button>
    </div>
  </div>
  <template v-else>
    <PageHeader
      title="设备"
      :subtitle="`${devices.length} 台 H3C 设备`"
    >
      <template #actions>
        <button v-if="selected.size > 0" class="btn-outline" @click="$router.push({ name: 'batch' })">批量执行 ({{ selected.size }})</button>
        <button class="btn-primary" @click="onCreate">
          <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新增设备
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <input v-model="search" placeholder="搜索设备名 / IP / 型号…" class="input pl-9" />
        </div>
        <div class="h-5 w-px bg-canvas-400" />
        <div class="flex items-center gap-1">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'all'">全部</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'online' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'online'">在线</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'maintenance' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'maintenance'">维护</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'offline' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'offline'">离线</button>
        </div>
      </div>

      <div class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 w-10 text-left">
                <input type="checkbox" :checked="allSelected" @change="toggleAll" class="rounded border-canvas-400 text-accent focus:ring-accent/40" />
              </th>
              <th class="px-4 py-3 text-left font-medium">设备</th>
              <th class="px-4 py-3 text-left font-medium">IP / 位置</th>
              <th class="px-4 py-3 text-left font-medium">型号 / 软件</th>
              <th class="px-4 py-3 text-left font-medium">状态</th>
              <th class="px-4 py-3 text-left font-medium">保护口</th>
              <th class="px-4 py-3 text-right font-medium w-72">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-if="filtered.length === 0">
              <td colspan="7" class="px-4 py-12 text-center text-ink-500 text-sm">
                暂无设备，请先 <button class="text-accent hover:underline" @click="onCreate">添加设备</button>
              </td>
            </tr>
            <tr v-for="d in filtered" :key="d.id" class="hover:bg-canvas-100 transition">
              <td class="px-4 py-3">
                <input type="checkbox" :checked="selected.has(d.id)" @change="toggle(d.id)" class="rounded border-canvas-400 text-accent focus:ring-accent/40" />
              </td>
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-ink-900">{{ d.name }}</span>
                </div>
                <div v-if="d.tags.length" class="flex gap-1 mt-0.5">
                  <span v-for="t in d.tags" :key="t" class="text-[10px] text-ink-500">#{{ t }}</span>
                </div>
              </td>
              <td class="px-4 py-3">
                <div class="text-ink-900 font-mono text-xs">{{ d.host }}:{{ d.port }}</div>
                <div class="text-[10px] text-ink-500">{{ d.location || '—' }}</div>
              </td>
              <td class="px-4 py-3">
                <div class="text-ink-900 text-xs">{{ d.model }}</div>
                <div class="text-[10px] text-ink-500 font-mono">{{ d.software }}</div>
              </td>
              <td class="px-4 py-3">
                <span :class="statusChip(d.status)">{{ statusLabel(d.status) }}</span>
              </td>
              <td class="px-4 py-3">
                <span v-if="d.protected.length" class="chip-bad !text-[10px]">🛡 {{ d.protected.length }}</span>
                <span v-else class="text-[10px] text-ink-500">—</span>
              </td>
              <td class="px-4 py-3 text-right">
                <div class="inline-flex items-center gap-1.5">
                  <button class="btn-soft !text-[11px] !px-2 !py-1" :disabled="testing.has(d.id)" @click="testConnection(d.id)">
                    {{ testing.has(d.id) ? '测试中…' : '连接测试' }}
                  </button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEditAsset(d)">资产</button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEdit(d)">编辑</button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1 hover:!text-bad" @click="onDeleteClick(d)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modals -->
    <DeviceFormModal
      v-model:open="deviceFormOpen"
      :mode="deviceFormMode"
      :device="editingDevice"
      @saved="loadDevices"
    />
    <AssetEditModal
      v-model:open="assetEditOpen"
      :device-id="editingAsset.deviceId"
      :device-name="editingAsset.deviceName"
      :asset="editingAsset.asset"
      @updated="loadDevices"
    />
    <ConfirmModal
      v-model:open="deleteConfirmOpen"
      title="删除设备"
      :message="deletingDevice ? `确定要删除设备 ${deletingDevice.name}（${deletingDevice.host}）吗？\n该操作不可恢复，关联的资产信息将一并删除。` : ''"
      confirm-text="确定删除"
      cancel-text="取消"
      variant="danger"
      :busy="deleteBusy"
      @confirm="onDeleteConfirm"
    />
  </template>
</template>
