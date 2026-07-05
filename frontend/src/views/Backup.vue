<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import BackupListModal from '../components/BackupListModal.vue'
import { deviceApi, backupApi } from '../api/index.js'
import { useTaskStore } from '../stores/task.js'

const { t } = useI18n()

// v24-feat-async-backup-status: feature flag
const ASYNC_MODE = import.meta.env.VITE_ASYNC_BACKUP === 'true'
const taskStore = useTaskStore()

const loading = ref(true)
const errMsg = ref('')
const devices = ref([])
const backupsByDevice = ref({})  // { device_id: [backup, ...] }

// 筛选
const filterDeviceId = ref('all')
const filterLock = ref('all')  // 'all' | 'locked' | 'unlocked'

// 全量备份
const fullBackingUp = ref(false)
const fullBackupType = ref('all')  // 'all' | 'startup' | 'running'
const fullResult = ref(null)  // { success: [], failed: [] }

// 全量备份结果 Modal
const fullResultOpen = ref(false)

// 单设备 Modal
const deviceModalOpen = ref(false)
const deviceModalInfo = ref({ id: null, name: '' })

// 二次确认
const confirm = ref({
  open: false,
  title: '',
  message: '',
  confirmText: '',
  variant: 'default',
  busy: false,
  action: null,
  target: null,
})

// 工具
function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function shortHash(h) {
  if (!h) return '-'
  return h.slice(0, 8)
}

// 加载所有数据
async function loadAll() {
  loading.value = true
  errMsg.value = ''
  const r = await deviceApi.list()
  if (!r.success) {
    errMsg.value = r.error || t('backup.load_failed_devices')
    loading.value = false
    return
  }
  devices.value = r.data || []

  // 并发拉每个设备的备份
  const results = await Promise.allSettled(
    devices.value.map((d) => backupApi.list(d.id))
  )
  const map = {}
  devices.value.forEach((d, i) => {
    const r2 = results[i]
    if (r2.status === 'fulfilled' && r2.value.success) {
      // v2.2 修复：后端返回 {device_id, total, backups: [...]} 嵌套结构
      // 兼容直接返回数组的旧行为（防御性写法）
      const data = r2.value.data
      map[d.id] = (data && Array.isArray(data.backups) ? data.backups : data) || []
    } else {
      map[d.id] = []  // 设备不可达 → 空列表
    }
  })
  backupsByDevice.value = map
  loading.value = false
}

// 计算：所有备份摊平（用于 KPI）
const allBackups = computed(() => {
  const out = []
  for (const id in backupsByDevice.value) {
    for (const b of backupsByDevice.value[id]) out.push(b)
  }
  return out
})

const kpiTotal = computed(() => allBackups.value.length)
const kpiLocked = computed(() => allBackups.value.filter((b) => b.locked).length)
const kpiSize = computed(() => {
  const total = allBackups.value.reduce((sum, b) => sum + (b.size || 0), 0)
  return formatSize(total)
})
const kpiToday = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return allBackups.value.filter((b) => b.created_at && b.created_at.startsWith(today)).length
})

// 过滤
const visibleDevices = computed(() => {
  if (filterDeviceId.value === 'all') return devices.value
  return devices.value.filter((d) => d.id === Number(filterDeviceId.value))
})

function visibleBackupsFor(deviceId) {
  const list = backupsByDevice.value[deviceId] || []
  if (filterLock.value === 'locked') return list.filter((b) => b.locked)
  if (filterLock.value === 'unlocked') return list.filter((b) => !b.locked)
  return list
}

// 全量备份
async function handleFullBackup() {
  if (fullBackingUp.value) return

  // v24-fix-batch-async-backup: ASYNC 模式循环提交，不阻塞
  if (ASYNC_MODE) {
    const types = fullBackupType.value === 'all' ? ['startup', 'running'] : [fullBackupType.value]
    const results = await taskStore.submitBatchBackup(
      devices.value,
      types,
      (d) => `${t('backup.running_full', { })} ${d.name}`,
    )
    const failed = results.filter((r) => !r.success)
    if (failed.length) {
      errMsg.value = t('backup.submit_failed', {
        n: failed.length,
        error: failed[0].error || t('backup.load_failed_devices').replace('Failed to load device list', 'Unknown error'),
      })
    }
    return // 不弹结果 Modal，BackgroundTaskPanel 显示每任务
  }

  // 同步模式（v2.3 行为不变）
  fullBackingUp.value = true
  fullResult.value = null
  // v2.3 新增：根据 type 选择备份类型
  const types = fullBackupType.value === 'all' ? ['startup', 'running'] : [fullBackupType.value]
  const r = await backupApi.createAll({ types })
  fullBackingUp.value = false
  if (!r.success) {
    errMsg.value = r.error || t('backup.full_backup_failed')
    return
  }
  fullResult.value = r.data || { success: [], failed: [] }
  fullResultOpen.value = true
  // 刷新数据
  await loadAll()
}

// 单设备 Modal
function openDeviceModal(d) {
  deviceModalInfo.value = { id: d.id, name: d.name }
  deviceModalOpen.value = true
}

async function onDeviceModalChanged() {
  await loadAll()
}

// 单行操作
function askDelete(d, b) {
  confirm.value = {
    open: true,
    title: t('backup.confirm_delete_title'),
    message: t('backup.confirm_delete_msg', { name: d.name, filename: b.filename }),
    confirmText: t('backup.confirm_delete_btn'),
    variant: 'danger',
    busy: false,
    action: 'delete',
    target: { d, b },
  }
}

function askToggleLock(d, b) {
  const willLock = !b.locked
  confirm.value = {
    open: true,
    title: willLock ? t('backup.confirm_lock_title') : t('backup.confirm_unlock_title'),
    message: willLock
      ? t('backup.confirm_lock_msg', { name: d.name, filename: b.filename })
      : t('backup.confirm_unlock_msg', { name: d.name, filename: b.filename }),
    confirmText: t('backup.confirm_toggle_btn'),
    variant: 'default',
    busy: false,
    action: willLock ? 'lock' : 'unlock',
    target: { d, b },
  }
}

function askRestore(d, b) {
  confirm.value = {
    open: true,
    title: t('backup.confirm_restore_title'),
    message: t('backup.confirm_restore_msg', {
      name: d.name,
      filename: b.filename,
      time: formatTime(b.created_at),
      size: formatSize(b.size),
      hash: shortHash(b.content_hash),
    }),
    confirmText: t('backup.confirm_restore_btn'),
    variant: 'danger',
    busy: false,
    action: 'restore',
    target: { d, b },
  }
}

async function onConfirmAction() {
  const { action, target } = confirm.value
  if (!action) return
  confirm.value.busy = true

  // v24-feat-async-backup-status: 回滚异步模式
  if (ASYNC_MODE && action === 'restore') {
    const r = await taskStore.submitRestore(
      target.d.id,
      target.b.id,
      true,  // with_reboot=true
      `${t('backup.btn_restore')} ${target.d.name} → ${target.b.filename}`,
    )
    confirm.value.busy = false
    if (!r.success) {
      confirm.value.message = t('backup.submit_restore_failed', { error: r.error || t('backup.unknown_error') }) + '\n\n' + confirm.value.message
      return
    }
    confirm.value.open = false
    return
  }

  let r
  if (action === 'delete') {
    r = await backupApi.remove(target.d.id, target.b.id)
  } else if (action === 'lock' || action === 'unlock') {
    r = await backupApi.toggleLock(target.d.id, target.b.id, action === 'lock')
  } else if (action === 'restore') {
    r = await backupApi.restore(target.d.id, target.b.id)
  }

  confirm.value.busy = false

  if (!r.success) {
    confirm.value.message = t('backup.op_failed', { error: r.error || t('backup.load_failed_devices').replace('Failed to load device list', 'Unknown error') }) + '\n\n' + confirm.value.message
    return
  }

  confirm.value.open = false
  await loadAll()
}

function closeConfirm() {
  if (confirm.value.busy) return
  confirm.value.open = false
}

async function handleDownload(d, b) {
  const r = await backupApi.download(d.id, b.id)
  if (!r.success) {
    errMsg.value = r.error || t('backup.download_failed')
    return
  }
  const url = URL.createObjectURL(r.data.blob)
  const a = document.createElement('a')
  a.href = url
  a.download = r.data.filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

onMounted(loadAll)
</script>

<template>
  <PageHeader
    :title="t('backup.title')"
    :subtitle="t('backup.subtitle')"
  >
    <template #actions>
      <div class="flex items-center gap-2 mr-2">
        <span class="text-xs text-ink-500">{{ t('backup.type_label') }}</span>
        <div class="flex items-center gap-1 text-xs">
          <button :class="['px-2.5 py-1 rounded-full transition', fullBackupType === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="fullBackupType = 'all'">{{ t('backup.type_all') }}</button>
          <button :class="['px-2.5 py-1 rounded-full transition', fullBackupType === 'startup' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="fullBackupType = 'startup'">{{ t('backup.type_startup') }}</button>
          <button :class="['px-2.5 py-1 rounded-full transition', fullBackupType === 'running' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="fullBackupType = 'running'">{{ t('backup.type_running') }}</button>
        </div>
      </div>
      <button class="btn-primary" :disabled="fullBackingUp" @click="handleFullBackup">
        <svg v-if="fullBackingUp" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
        {{ fullBackingUp ? t('backup.running_full') : t('backup.run_full') }}
      </button>
    </template>
  </PageHeader>

  <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
    <!-- KPI -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="panel px-4 py-3">
        <div class="text-[11px] text-ink-500 uppercase tracking-wider">{{ t('backup.kpi_total') }}</div>
        <div class="text-2xl font-mono text-ink-900 mt-1">{{ kpiTotal }}</div>
      </div>
      <div class="panel px-4 py-3">
        <div class="text-[11px] text-ink-500 uppercase tracking-wider">{{ t('backup.kpi_locked') }}</div>
        <div class="text-2xl font-mono text-warn mt-1">{{ kpiLocked }}</div>
      </div>
      <div class="panel px-4 py-3">
        <div class="text-[11px] text-ink-500 uppercase tracking-wider">{{ t('backup.kpi_size') }}</div>
        <div class="text-2xl font-mono text-ink-900 mt-1">{{ kpiSize }}</div>
      </div>
      <div class="panel px-4 py-3">
        <div class="text-[11px] text-ink-500 uppercase tracking-wider">{{ t('backup.kpi_today') }}</div>
        <div class="text-2xl font-mono text-accent mt-1">{{ kpiToday }}</div>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
      <div class="text-xs text-ink-500">{{ t('backup.filter_device') }}</div>
      <select v-model="filterDeviceId" class="input !w-auto !text-xs">
        <option value="all">{{ t('backup.filter_all', { n: devices.length }) }}</option>
        <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }} ({{ d.host }})</option>
      </select>
      <div class="h-5 w-px bg-canvas-400" />
      <div class="flex items-center gap-1">
        <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
          filterLock === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterLock = 'all'">{{ t('backup.filter_all_short') }}</button>
        <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
          filterLock === 'locked' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterLock = 'locked'">{{ t('backup.filter_locked') }}</button>
        <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition',
          filterLock === 'unlocked' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterLock = 'unlocked'">{{ t('backup.filter_unlocked') }}</button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="errMsg" class="panel px-4 py-2.5 bg-bad/8 border-bad/30 text-sm text-bad">
      {{ errMsg }}
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="panel px-4 py-12 text-center text-sm text-ink-500">{{ t('common.loading') }}</div>

    <!-- 按设备分组 -->
    <div v-else-if="visibleDevices.length === 0" class="panel px-4 py-12 text-center text-sm text-ink-500">{{ t('backup.no_devices') }}</div>
    <div v-else class="space-y-3">
      <div v-for="d in visibleDevices" :key="d.id" class="panel overflow-hidden">
        <div class="px-4 py-2.5 border-b border-canvas-300 flex items-center justify-between bg-canvas-50">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-ink-900">{{ d.name }}</span>
            <span class="text-[10px] text-ink-500 font-mono">{{ d.host }}:{{ d.port }}</span>
            <span class="text-[10px] text-ink-400">·</span>
            <span class="text-[10px] text-ink-500">{{ t('backup.count_per_device', { n: (backupsByDevice[d.id] || []).length }) }}</span>
          </div>
          <button class="btn-soft !text-[11px] !px-2 !py-1" @click="openDeviceModal(d)">
            {{ t('backup.backup_here') }}
          </button>
        </div>
        <div v-if="(backupsByDevice[d.id] || []).length === 0" class="px-4 py-6 text-center text-xs text-ink-500">
          {{ t('backup.no_backups') }}
        </div>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-[10px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-3 py-2 text-left font-medium">{{ t('backup.col_filename') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('backup.col_time') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('backup.col_type') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('backup.col_size') }}</th>
              <th class="px-3 py-2 text-left font-medium">{{ t('backup.col_hash') }}</th>
              <th class="px-3 py-2 text-center font-medium w-16">{{ t('backup.col_status') }}</th>
              <th class="px-3 py-2 text-right font-medium w-48">{{ t('backup.col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-for="b in visibleBackupsFor(d.id)" :key="b.id" class="hover:bg-canvas-50">
              <td class="px-3 py-2 font-mono text-[11px] text-ink-900">{{ b.filename }}</td>
              <td class="px-3 py-2 text-[11px] font-mono text-ink-700">{{ formatTime(b.created_at) }}</td>
              <td class="px-3 py-2 text-[11px] text-ink-700">{{ b.type || b.backup_type }}</td>
              <td class="px-3 py-2 text-[11px] font-mono text-ink-700 text-right">{{ formatSize(b.size) }}</td>
              <td class="px-3 py-2 text-[11px] font-mono text-ink-500">{{ shortHash(b.content_hash) }}</td>
              <td class="px-3 py-2 text-center">
                <span v-if="b.locked" class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-warn/10 text-warn" :title="t('backup.title_locked')">{{ t('backup.status_locked') }}</span>
                <span v-else class="text-[10px] text-ink-400">{{ t('backup.status_unlocked_chip') }}</span>
              </td>
              <td class="px-3 py-2 text-right">
                <div class="inline-flex items-center gap-1">
                  <button class="text-[11px] text-accent hover:underline" @click="handleDownload(d, b)">{{ t('backup.btn_download') }}</button>
                  <span class="text-canvas-300">{{ t('common.or') }}</span>
                  <button :class="['text-[11px] hover:underline', b.locked ? 'text-warn' : 'text-ink-700']" @click="askToggleLock(d, b)">{{ b.locked ? t('backup.btn_unlock') : t('backup.btn_lock') }}</button>
                  <span class="text-canvas-300">{{ t('common.or') }}</span>
                  <button :class="['text-[11px] hover:underline', b.locked ? 'text-canvas-300 cursor-not-allowed' : 'text-bad']" :disabled="b.locked" :title="b.locked ? t('backup.title_locked_no_delete') : t('backup.title_delete')" @click="askDelete(d, b)">{{ t('backup.btn_delete') }}</button>
                  <span class="text-canvas-300">{{ t('common.or') }}</span>
                  <button class="text-[11px] text-bad hover:underline" @click="askRestore(d, b)">{{ t('backup.btn_restore') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 全量备份结果 Modal -->
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="fullResultOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="fullResultOpen = false"></div>
        <div class="relative panel w-full max-w-lg shadow-2xl">
          <div class="px-5 py-4 border-b border-canvas-300 flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink-900">{{ t('cmdb.result_title') }}</h3>
            <button class="btn-soft !text-xs" @click="fullResultOpen = false">{{ t('common.close') }}</button>
          </div>
          <div class="px-5 py-4 space-y-3">
            <div v-if="fullResult" class="text-sm space-y-2">
              <div class="flex items-center gap-2 text-good">
                <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 13l4 4L19 7"/></svg>
                <span>{{ t('cmdb.result_success', { n: fullResult.success.length }) }}</span>
              </div>
              <div v-if="fullResult.failed.length > 0" class="flex items-start gap-2 text-bad">
                <svg class="size-4 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                <div>
                  <div>{{ t('cmdb.result_failed', { n: fullResult.failed.length }) }}</div>
                  <ul class="mt-1 ml-4 text-[11px] space-y-0.5 list-disc">
                    <li v-for="(f, i) in fullResult.failed" :key="i">
                      {{ t('cmdb.result_failed_item', { id: f.device_id, error: f.error }) }}
                    </li>
                  </ul>
                </div>
              </div>
              <div v-if="fullResult.success.length > 0" class="text-[11px] text-ink-500">
                {{ t('cmdb.result_stored', { n: fullResult.success.length }) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 二次确认 Modal -->
  <ConfirmModal
    :open="confirm.open"
    :title="confirm.title"
    :message="confirm.message"
    :confirm-text="confirm.confirmText"
    :variant="confirm.variant"
    :busy="confirm.busy"
    @update:open="(v) => v || closeConfirm()"
    @confirm="onConfirmAction"
    @cancel="closeConfirm"
  />

  <!-- 单设备详细 Modal -->
  <BackupListModal
    v-if="deviceModalOpen && deviceModalInfo.id"
    v-model:visible="deviceModalOpen"
    :device-id="deviceModalInfo.id"
    :device-name="deviceModalInfo.name"
    @changed="onDeviceModalChanged"
  />
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
