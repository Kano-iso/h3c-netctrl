<script setup>
// v2.6 i18n: 所有硬编码中文 → t()（device.* keys）
// 状态/状态标签走 utils/status.js（已 i18n 化）
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import DeviceFormModal from '../components/DeviceFormModal.vue'
import AssetEditModal from '../components/AssetEditModal.vue'
import BackupListModal from '../components/BackupListModal.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import { deviceApi, assetApi, backupApi } from '../api/index.js'
import { getStatusChip, getStatusLabel } from '../utils/status.js'

const { t } = useI18n()

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

// 备份 Modal
const backupModalOpen = ref(false)
const backupModalInfo = ref({ id: null, name: '' })
function openBackupModal(d) {
  backupModalInfo.value = { id: d.id, name: d.name }
  backupModalOpen.value = true
}

// v2.6.1 fix-asset-backup-state-sync Task 3.1-3.3: 强制备份
// - forceChecked: 每设备 force 勾选（仅 offline/never_collected 显示）
// - forceConfirmOpen: 强制备份二次确认弹窗
// - forceConfirmBusy: 弹窗 confirm 按钮 busy 状态
const forceChecked = ref(new Set())  // deviceId set
const forceConfirmOpen = ref(false)
const forceConfirmInfo = ref({ id: null, name: '', status: null })
const forceConfirmBusy = ref(false)

// 设备是否需要 force 才能备份（offline / never_collected / null）
function needsForce(d) {
  return d.status !== 'online'
}

function toggleForce(id) {
  const next = new Set(forceChecked.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  forceChecked.value = next
}

function onBackupClick(d) {
  // online → 直接打开 backup list modal（正常流程）
  if (d.status === 'online') {
    openBackupModal(d)
    return
  }
  // offline + 已勾选 force → 二次确认
  if (forceChecked.value.has(d.id)) {
    forceConfirmInfo.value = { id: d.id, name: d.name, status: d.status }
    forceConfirmOpen.value = true
  } else {
    // offline + 未勾选 force → tooltip 提示，无法点击（按钮 disabled）
  }
}

async function onForceConfirm() {
  if (!forceConfirmInfo.value.id) return
  forceConfirmBusy.value = true
  const r = await backupApi.create(forceConfirmInfo.value.id, true)
  forceConfirmBusy.value = false
  forceConfirmOpen.value = false
  if (r.success) {
    // 成功提示 + 刷新 backup list modal（如果开着）
    alert(t('backup.force_success', { name: forceConfirmInfo.value.name }))
    if (backupModalOpen.value && backupModalInfo.value.id === forceConfirmInfo.value.id) {
      // 触发 BackupListModal 刷新（通过 backupApi.list）
    }
  } else {
    alert(t('backup.force_failed', { name: forceConfirmInfo.value.name, error: r.error || t('cmdb.unknown_error') }))
  }
  forceConfirmInfo.value = { id: null, name: '', status: null }
}

async function loadDevices() {
  loading.value = true
  error.value = ''
  const r = await deviceApi.list()
  if (!r.success) {
    error.value = r.error || t('device.load_failed')
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
    alert(t('device.test_success', { id }))
  } else {
    alert(t('device.test_failed', { id, error: r.error || t('device.test_failed_unknown') || '未知错误' }))
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
    alert(t('device.delete_failed', { error: r.error || t('device.test_failed_unknown') || '未知错误' }))
  }
}

// 编辑资产
const onEditAsset = (d) => {
  editingAsset.value = { deviceId: d.id, deviceName: d.name, asset: d.asset || {} }
  assetEditOpen.value = true
}
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('dashboard.kpi_loading') }}</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">{{ t('device.load_failed') }}</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDevices">{{ t('device.retry') }}</button>
    </div>
  </div>
  <template v-else>
    <PageHeader
      :title="t('device.title')"
      :subtitle="t('device.subtitle', { n: devices.length })"
    >
      <template #actions>
        <button v-if="selected.size > 0" class="btn-outline" @click="$router.push({ name: 'batch' })">{{ t('device.batch_execute', { n: selected.size }) }}</button>
        <button class="btn-primary" @click="onCreate">
          <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('device.new_device') }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <input v-model="search" :placeholder="t('device.search_placeholder')" class="input pl-9" />
        </div>
        <div class="h-5 w-px bg-canvas-400" />
        <div class="flex items-center gap-1">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'all'">{{ t('device.filter_all') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'online' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'online'">{{ t('device.filter_online') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'maintenance' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'maintenance'">{{ t('device.filter_maintenance') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
            filterStatus === 'offline' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'offline'">{{ t('device.filter_offline') }}</button>
        </div>
      </div>

      <div class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 w-10 text-left">
                <input type="checkbox" :checked="allSelected" @change="toggleAll" class="rounded border-canvas-400 text-accent focus:ring-accent/40" />
              </th>
              <th class="px-4 py-3 text-left font-medium">{{ t('device.col_device') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('device.col_ip_location') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('device.col_model_software') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('device.col_status') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('device.col_protected') }}</th>
              <th class="px-4 py-3 text-right font-medium w-72">{{ t('device.col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-if="filtered.length === 0">
              <td colspan="7" class="px-4 py-12 text-center text-ink-500 text-sm">
                {{ t('device.no_devices') }} <button class="text-accent hover:underline" @click="onCreate">{{ t('device.add_device') }}</button>
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
                  <span v-for="tag in d.tags" :key="tag" class="text-[10px] text-ink-500">#{{ tag }}</span>
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
                    {{ testing.has(d.id) ? t('device.btn_testing') : t('device.btn_test') }}
                  </button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEditAsset(d)">{{ t('device.btn_asset') }}</button>
                  <!-- v2.6.1 fix-asset-backup-state-sync Task 3.1-3.3: 备份按钮 disabled + tooltip + force 勾选 -->
                  <label v-if="needsForce(d)" class="inline-flex items-center gap-1 text-[10px] text-ink-500 select-none cursor-pointer" :title="t('backup.force_label')">
                    <input
                      type="checkbox"
                      :checked="forceChecked.has(d.id)"
                      class="rounded border-canvas-400 text-warn focus:ring-warn/40"
                      @change="toggleForce(d.id)"
                    />
                    <span>{{ t('backup.force_label') }}</span>
                  </label>
                  <button
                    class="btn-soft !text-[11px] !px-2 !py-1"
                    :disabled="needsForce(d) && !forceChecked.has(d.id)"
                    :title="needsForce(d) && !forceChecked.has(d.id) ? t('button.disabled.asset_offline') : ''"
                    @click="onBackupClick(d)"
                  >
                    {{ t('device.btn_backup') }}
                  </button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEdit(d)">{{ t('device.btn_edit') }}</button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1 hover:!text-bad" @click="onDeleteClick(d)">{{ t('device.btn_delete') }}</button>
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
      :title="t('device.btn_delete')"
      :message="deletingDevice ? t('device.delete_confirm_message', { name: deletingDevice.name, host: deletingDevice.host }) : ''"
      :confirm-text="t('device.delete_confirm_btn')"
      :cancel-text="t('iface.btn_cancel')"
      variant="danger"
      :busy="deleteBusy"
      @confirm="onDeleteConfirm"
    />
    <BackupListModal
      v-if="backupModalOpen && backupModalInfo.id"
      v-model:visible="backupModalOpen"
      :device-id="backupModalInfo.id"
      :device-name="backupModalInfo.name"
    />

    <!-- v2.6.1 fix-asset-backup-state-sync Task 3.3: 强制备份二次确认弹窗 -->
    <ConfirmModal
      v-model:open="forceConfirmOpen"
      :title="t('backup.force_confirm_title')"
      :message="forceConfirmInfo.id ? t('backup.force_confirm_msg', { name: forceConfirmInfo.name, status: forceConfirmInfo.status || t('cmdb.unknown_error') }) : ''"
      :confirm-text="t('backup.force_confirm_btn')"
      :cancel-text="t('iface.btn_cancel')"
      variant="warning"
      :busy="forceConfirmBusy"
      @confirm="onForceConfirm"
    />
  </template>
</template>
