<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import Select from '../components/Select.vue'
import { deviceApi, logApi } from '../api/index.js'

const { t } = useI18n()

const loading = ref(true)
const error = ref('')
const logs = ref([])
const total = ref(0)
const devices = ref([])

// 过滤状态
const filterStatus = ref('all')  // all / success / warning / failed
const filterAction = ref('all')
const filterDeviceId = ref(null)  // null = 全部
const search = ref('')
const expanded = ref(new Set())

// 全部 action 枚举（从 i18n key 派生）
const ACTION_VALUES = [
  'all', 'execute', 'connect', 'interface_config', 'asset_refresh',
  'batch_execute', 'backup_create', 'backup_create_all',
  'backup_delete', 'backup_lock', 'backup_restore',
]
const actionOptions = computed(() =>
  ACTION_VALUES.map(v => ({ value: v, label: t(`logs.actions.${v}`) }))
)

// "全部" 显式作为第一项（placeholder 也可，但放第一项更明确）
const deviceOptions = computed(() => [
  { id: null, label: t('logs.filter_device_all') },
  ...devices.value.map(d => ({ id: d.id, label: d.name })),
])

async function loadDevices() {
  const r = await deviceApi.list()
  if (r.success) devices.value = r.data || []
}

async function loadLogs() {
  loading.value = true
  error.value = ''
  const params = { page: 1, page_size: 50 }
  if (filterDeviceId.value) params.device_id = filterDeviceId.value
  if (filterAction.value && filterAction.value !== 'all') params.action = filterAction.value
  const r = await logApi.list(params)
  if (!r.success) {
    error.value = r.error || t('errors.network_failed')
    logs.value = []
    loading.value = false
    return
  }
  const data = r.data || {}
  logs.value = data.items || []
  total.value = data.total ?? logs.value.length
  loading.value = false
}

onMounted(async () => {
  await loadDevices()
  await loadLogs()
})

watch([filterDeviceId, filterAction], () => {
  loadLogs()
})

const filtered = computed(() => {
  let list = logs.value
  if (filterStatus.value !== 'all') list = list.filter(l => l.status === filterStatus.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(l => `${l.device_name || ''} ${l.detail || ''} ${l.action || ''}`.toLowerCase().includes(q))
  }
  return list
})

const toggle = (id) => {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
  expanded.value = new Set(expanded.value)
}

const timeOf = (iso) => {
  if (!iso) return ''
  // 形如 2026-06-23T14:32:08，截取 HH:MM:SS
  const tIdx = iso.indexOf('T')
  if (tIdx >= 0) {
    const t = iso.substring(tIdx + 1)
    return t.length >= 8 ? t.substring(0, 8) : t
  }
  // 退路：空格分隔
  const parts = iso.split(' ')
  return parts[1] ? parts[1].substring(0, 8) : ''
}

const statusChip = (s) => s === 'success' ? 'chip-good' : s === 'warning' ? 'chip-warn' : 'chip-bad'
const statusText = (s) => t(`status.log.${s}`, t('common.dash'))
</script>

<template>
  <div v-if="loading && logs.length === 0" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">{{ t('logs.load_failed') }}</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadLogs">{{ t('common.retry') }}</button>
    </div>
  </div>
  <template v-else>
    <PageHeader :title="t('logs.title')" :subtitle="t('logs.subtitle', { n: total })">
      <template #actions>
        <button class="btn-outline" @click="alert(t('logs.export_csv_wip'))">
          <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          {{ t('logs.export_csv') }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="search" :placeholder="t('logs.search_placeholder')" class="input pl-9" />
        </div>

        <Select
          v-model="filterDeviceId"
          :options="deviceOptions"
          :custom-label="(d) => d.label"
          value-key="id"
          width="w-44"
        />

        <Select
          v-model="filterAction"
          :options="actionOptions"
          :custom-label="(a) => a.label"
          value-key="value"
          width="w-44"
        />

        <div class="flex items-center gap-1">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterStatus === 'all' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'all'">{{ t('logs.filter_status_all') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterStatus === 'success' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'success'">{{ t('logs.filter_status_success') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterStatus === 'warning' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'warning'">{{ t('logs.filter_status_warning') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', filterStatus === 'failed' ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-canvas-200']" @click="filterStatus = 'failed'">{{ t('logs.filter_status_failed') }}</button>
        </div>
      </div>

      <div v-if="filtered.length === 0" class="panel p-12 text-center text-sm text-ink-500">{{ t('logs.no_records') }}</div>

      <div v-else class="panel overflow-hidden">
        <div v-for="log in filtered" :key="log.id" class="border-b border-canvas-300 last:border-0">
          <button @click="toggle(log.id)" class="w-full px-4 py-3 flex items-center gap-3 hover:bg-canvas-100 transition text-left">
            <svg :class="['size-4 text-ink-500 transition-transform shrink-0', expanded.has(log.id) && 'rotate-90']" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
            <span class="text-xs text-ink-500 font-mono w-16 shrink-0">{{ timeOf(log.created_at) }}</span>
            <span class="chip-mute !text-[10px] w-32 text-center shrink-0">{{ log.action }}</span>
            <span class="text-sm text-ink-900 flex-1 truncate">{{ log.device_name || t('logs.device_id', { id: log.device_id }) }} · {{ log.detail }}</span>
            <span :class="statusChip(log.status)">
              {{ statusText(log.status) }}
            </span>
          </button>
          <Transition name="expand">
            <div v-if="expanded.has(log.id)" class="px-4 pb-4 pt-1 ml-8">
              <div class="rounded-xl bg-canvas-100 p-4 space-y-2 text-xs font-mono">
                <div class="grid grid-cols-2 md:grid-cols-3 gap-3 text-ink-700">
                  <div><span class="text-ink-500">{{ t('logs.label_device') }}</span> <span class="text-ink-900">{{ log.device_name || t('logs.device_id', { id: log.device_id }) }}</span></div>
                  <div><span class="text-ink-500">{{ t('logs.label_action') }}</span> <span class="text-ink-900">{{ log.action }}</span></div>
                  <div><span class="text-ink-500">{{ t('logs.label_time') }}</span> <span class="text-ink-900">{{ log.created_at }}</span></div>
                </div>
                <div class="text-ink-700">
                  <span class="text-ink-500">{{ t('logs.label_detail') }}</span> <span class="text-ink-900 break-all">{{ log.detail || t('logs.detail_empty') }}</span>
                </div>
                <div v-if="log.status === 'failed' && log.error_message" class="mt-2 p-3 rounded-lg bg-bad/8 border border-bad/30">
                  <div class="text-bad font-semibold mb-1">{{ t('logs.error_detail') }}</div>
                  <div class="text-bad/80 break-all whitespace-pre-wrap">{{ log.error_message }}</div>
                </div>
                <div v-else-if="log.status === 'success'" class="text-ink-500">{{ t('logs.success_no_error') }}</div>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </template>
</template>

<style>
.expand-enter-active, .expand-leave-active { transition: all .2s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { max-height: 0; opacity: 0; }
.expand-enter-to, .expand-leave-from { max-height: 400px; opacity: 1; }
</style>
