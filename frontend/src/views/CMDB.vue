<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import AssetEditModal from '../components/AssetEditModal.vue'
import { deviceApi, assetApi, backupApi } from '../api/index.js'
import { useTaskStore } from '../stores/task.js'
import { getStatusInfo } from '../utils/status.js'

const { t } = useI18n()

// v24-fix-batch-async-backup: feature flag
const ASYNC_MODE = import.meta.env.VITE_ASYNC_BACKUP === 'true'
const taskStore = useTaskStore()

const loading = ref(true)
const error = ref('')
const items = ref([])
const search = ref('')
const view = ref('table')
const refreshing = ref(false)
const refreshMsg = ref('')
const refreshingIds = ref(new Set())  // 单设备采集中跟踪

// Modal state
const assetEditOpen = ref(false)
const editingAsset = ref({ deviceId: null, deviceName: '', asset: {} })

// 全量备份
const fullBackingUp = ref(false)
const fullResult = ref(null)
const fullResultOpen = ref(false)
// v2.6.1 fix-asset-backup-state-sync Task 3.4: 全量强制备份勾选
const fullBackupForce = ref(false)

async function loadAssets() {
  loading.value = true
  error.value = ''
  const dr = await deviceApi.list()
  if (!dr.success) {
    error.value = dr.error || t('cmdb.load_failed_devices')
    loading.value = false
    return
  }
  const list = dr.data || []
  const enriched = await Promise.all(
    list.map(async (d) => {
      const ar = await assetApi.get(d.id)
      const a = ar.success ? (ar.data || {}) : {}
      return {
        id: d.id,
        name: d.name,
        host: d.host,
        model: a.model || t('common.dash'),
        software: a.software_package || t('common.dash'),
        location: a.location || '',
        tags: a.tags ? a.tags.split(',').map(s => s.trim()).filter(Boolean) : [],
        status: a.status || null,  // null → utils 兜底为"未采集"
        asset: a,
      }
    })
  )
  items.value = enriched
  loading.value = false
}

onMounted(loadAssets)

const refresh = async () => {
  if (refreshing.value) return
  refreshing.value = true
  refreshMsg.value = ''
  const dr = await deviceApi.list()
  if (!dr.success) {
    refreshMsg.value = dr.error || t('cmdb.load_failed_devices')
    refreshing.value = false
    return
  }
  const ids = (dr.data || []).map(d => d.id)
  // 并发触发 SSH 采集（忽略单台结果）
  await Promise.all(ids.map(id => assetApi.refresh(id).catch(() => null)))
  // 重新拉取资产详情
  await loadAssets()
  refreshing.value = false
  refreshMsg.value = t('cmdb.refresh_done')
  setTimeout(() => { refreshMsg.value = '' }, 2000)
}

// 单设备采集（独立于全量刷新，支持多设备并发）
const refreshOne = async (id) => {
  if (refreshingIds.value.has(id)) return
  const next = new Set(refreshingIds.value)
  next.add(id)
  refreshingIds.value = next
  try {
    const r = await assetApi.refresh(id)
    if (!r.success) {
      alert(t('cmdb.collect_failed', { error: r.error || t('cmdb.unknown_error') }))
    }
  } catch (e) {
    alert(t('cmdb.collect_exception', { error: e.message || e }))
  } finally {
    const done = new Set(refreshingIds.value)
    done.delete(id)
    refreshingIds.value = done
    await loadAssets()
  }
}

const filtered = computed(() => {
  if (!search.value) return items.value
  const q = search.value.toLowerCase()
  return items.value.filter(d => `${d.name} ${d.host} ${d.model} ${d.software} ${d.location}`.toLowerCase().includes(q))
})

const groupBy = (key) => {
  const groups = {}
  for (const d of filtered.value) {
    const k = d[key] || null
    if (!groups[k]) groups[k] = []
    groups[k].push(d)
  }
  return groups
}

const byStatus = computed(() => groupBy('status'))

// 状态显示统一用 utils 兜底
const statusChip = (s) => getStatusInfo(s).chipClass
const statusLabel = (s) => getStatusInfo(s).label

// 全量备份
const handleFullBackup = async () => {
  if (fullBackingUp.value) return

  // v2.6.1 fix-asset-backup-state-sync Task 3.4: 全量 force 时传 body.force
  const body = { types: ['startup', 'running'], force: fullBackupForce.value }

  // v24-fix-batch-async-backup: ASYNC 模式循环提交，不阻塞
  if (ASYNC_MODE) {
    const results = await taskStore.submitBatchBackup(
      items.value,
      ['startup', 'running'],
      (d) => `${t('cmdb.full_backup')} ${d.name}`,
      { force: fullBackupForce.value },  // v2.6.1 Task 3.4
    )
    const failed = results.filter((r) => !r.success)
    if (failed.length) {
      error.value = t('cmdb.submit_failed', {
        n: failed.length,
        error: failed[0].error || t('cmdb.unknown_error'),
      })
    }
    return
  }

  // 同步模式（v2.3 行为不变）
  fullBackingUp.value = true
  fullResult.value = null
  const r = await backupApi.createAll(body)
  fullBackingUp.value = false
  if (!r.success) {
    error.value = r.error || t('cmdb.full_backup_failed')
    return
  }
  fullResult.value = r.data || { success: [], failed: [] }
  fullResultOpen.value = true
}

// 编辑资产
const onEditAsset = (d) => {
  editingAsset.value = { deviceId: d.id, deviceName: d.name, asset: d.asset || {} }
  assetEditOpen.value = true
}
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">{{ t('cmdb.load_failed') }}</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadAssets">{{ t('common.retry') }}</button>
    </div>
  </div>
  <template v-else>
    <PageHeader :title="t('cmdb.title')" :subtitle="t('cmdb.subtitle', { n: items.length })">
      <template #actions>
        <div class="flex items-center bg-canvas-200 rounded-full p-0.5">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', view === 'table' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-700']" @click="view = 'table'">{{ t('cmdb.view_table') }}</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', view === 'card' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-700']" @click="view = 'card'">{{ t('cmdb.view_card') }}</button>
        </div>
        <button class="btn-outline" :disabled="refreshing" @click="refresh">
          <svg :class="['size-3.5', refreshing && 'animate-spin']" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8M3 3v5h5"/></svg>
          {{ refreshing ? t('cmdb.refreshing') : t('cmdb.refresh_all') }}
        </button>
        <!-- v2.6.1 fix-asset-backup-state-sync Task 3.4: 全量强制备份勾选 -->
        <label class="inline-flex items-center gap-1.5 text-xs text-ink-700 cursor-pointer select-none" :title="t('cmdb.full_backup_force_hint')">
          <input
            type="checkbox"
            v-model="fullBackupForce"
            class="rounded border-canvas-400 text-warn focus:ring-warn/40"
          />
          <span>{{ t('cmdb.full_backup_force') }}</span>
        </label>
        <button class="btn-primary" :disabled="fullBackingUp" @click="handleFullBackup">
          <svg v-if="fullBackingUp" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
          {{ fullBackingUp ? t('cmdb.full_backup_running') : t('cmdb.full_backup') }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="search" :placeholder="t('cmdb.search_placeholder')" class="input pl-9" />
        </div>
        <div class="text-[10px] text-ink-500 font-mono">{{ t('cmdb.count_devices', { n: filtered.length }) }}</div>
      </div>

      <div v-if="refreshMsg" class="panel p-3 text-xs text-ink-700">{{ refreshMsg }}</div>

      <div v-if="filtered.length === 0" class="panel p-12 text-center text-sm text-ink-500">{{ t('cmdb.no_devices') }}</div>

      <div v-else-if="view === 'table'" class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_name') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_ip') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_model') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_software') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_location') }}</th>
              <th class="px-4 py-3 text-left font-medium">{{ t('cmdb.col_status') }}</th>
              <th class="px-4 py-3 text-right font-medium w-32">{{ t('cmdb.col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-for="d in filtered" :key="d.id" class="hover:bg-canvas-100 transition">
              <td class="px-4 py-3 text-sm font-medium text-ink-900">{{ d.name }}</td>
              <td class="px-4 py-3 font-mono text-xs text-ink-900">{{ d.host }}</td>
              <td class="px-4 py-3 text-xs text-ink-900">{{ d.model }}</td>
              <td class="px-4 py-3 font-mono text-[10px] text-ink-500">{{ d.software }}</td>
              <td class="px-4 py-3 text-xs text-ink-700">{{ d.location || t('common.dash') }}</td>
              <td class="px-4 py-3">
                <span :class="statusChip(d.status)">{{ statusLabel(d.status) }}</span>
              </td>
              <td class="px-4 py-3 text-right">
                <div class="inline-flex items-center gap-1.5 justify-end">
                  <button
                    class="btn-soft !text-[11px] !px-2 !py-1"
                    :disabled="refreshingIds.has(d.id)"
                    @click="refreshOne(d.id)"
                  >
                    <svg v-if="refreshingIds.has(d.id)" class="size-3 animate-spin inline-block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                    <span>{{ refreshingIds.has(d.id) ? t('cmdb.collecting') : t('cmdb.collect') }}</span>
                  </button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEditAsset(d)">{{ t('cmdb.edit_asset') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="space-y-6">
        <div v-for="(devs, s) in byStatus" :key="s">
          <div class="flex items-center gap-2 mb-3">
            <span :class="statusChip(s)">{{ statusLabel(s) }}</span>
            <span class="chip-mute !text-[10px]">{{ t('cmdb.count_per_group', { n: devs.length }) }}</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div v-for="d in devs" :key="d.id" class="panel panel-hover p-5">
              <div class="flex items-center justify-between mb-3">
                <div>
                  <div class="text-sm font-semibold text-ink-900">{{ d.name }}</div>
                  <div class="text-[10px] text-ink-500 font-mono">{{ d.host }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <span :class="statusChip(d.status)">{{ statusLabel(d.status) }}</span>
                  <button
                    class="text-ink-500 hover:text-accent p-1"
                    :disabled="refreshingIds.has(d.id)"
                    :title="t('cmdb.title_collect')"
                    @click="refreshOne(d.id)"
                  >
                    <svg v-if="refreshingIds.has(d.id)" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                    <svg v-else class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 12a9 9 0 11-9-9c2.5 0 4.7 1 6.4 2.6L21 8"/><path d="M21 3v5h-5"/></svg>
                  </button>
                  <button class="text-ink-500 hover:text-accent p-1" :title="t('cmdb.title_edit')" @click="onEditAsset(d)">
                    <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                  </button>
                </div>
              </div>
              <div class="space-y-1.5 text-xs">
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">{{ t('cmdb.card_model') }}</span><span class="text-ink-900 font-mono truncate">{{ d.model }}</span></div>
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">{{ t('cmdb.card_software') }}</span><span class="text-ink-900 font-mono text-[10px] truncate">{{ d.software }}</span></div>
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">{{ t('cmdb.card_location') }}</span><span class="text-ink-900 text-[10px] truncate">{{ d.location || t('common.dash') }}</span></div>
              </div>
              <div v-if="d.tags.length" class="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-canvas-300">
                <span v-for="tag in d.tags" :key="tag" class="chip-mute !text-[10px]">#{{ tag }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modals -->
    <AssetEditModal
      v-model:open="assetEditOpen"
      :device-id="editingAsset.deviceId"
      :device-name="editingAsset.deviceName"
      :asset="editingAsset.asset"
      @updated="loadAssets"
    />

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
                <div class="text-[11px] text-ink-500 pt-2 border-t border-canvas-300">
                  {{ t('cmdb.result_goto') }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </template>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
