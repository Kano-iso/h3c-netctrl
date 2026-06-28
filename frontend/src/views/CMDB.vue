<script setup>
import { ref, computed, onMounted } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import AssetEditModal from '../components/AssetEditModal.vue'
import { deviceApi, assetApi, backupApi } from '../api/index.js'
import { getStatusInfo } from '../utils/status.js'

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
const fullResultConfirm = ref(false)  // 防止全量备份确认误点（暂用 false）

async function loadAssets() {
  loading.value = true
  error.value = ''
  const dr = await deviceApi.list()
  if (!dr.success) {
    error.value = dr.error || '加载失败'
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
        model: a.model || '—',
        software: a.software_package || '—',
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
    refreshMsg.value = dr.error || '获取设备列表失败'
    refreshing.value = false
    return
  }
  const ids = (dr.data || []).map(d => d.id)
  // 并发触发 SSH 采集（忽略单台结果）
  await Promise.all(ids.map(id => assetApi.refresh(id).catch(() => null)))
  // 重新拉取资产详情
  await loadAssets()
  refreshing.value = false
  refreshMsg.value = '刷新完成'
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
      alert(`采集失败：${r.error || '未知错误'}`)
    }
  } catch (e) {
    alert(`采集异常：${e.message || e}`)
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
  fullBackingUp.value = true
  fullResult.value = null
  const r = await backupApi.createAll()
  fullBackingUp.value = false
  if (!r.success) {
    error.value = r.error || '全量备份失败'
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
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">加载中…</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">资产列表加载失败</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadAssets">重试</button>
    </div>
  </div>
  <template v-else>
    <PageHeader title="CMDB" :subtitle="`${items.length} 台设备 · 型号 / 固件 / 软件包 / 物理位置`">
      <template #actions>
        <div class="flex items-center bg-canvas-200 rounded-full p-0.5">
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', view === 'table' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-700']" @click="view = 'table'">表格</button>
          <button :class="['px-3 py-1.5 text-xs font-medium rounded-full transition', view === 'card' ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-700']" @click="view = 'card'">分组</button>
        </div>
        <button class="btn-outline" :disabled="refreshing" @click="refresh">
          <svg :class="['size-3.5', refreshing && 'animate-spin']" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8M3 3v5h5"/></svg>
          {{ refreshing ? '采集中…' : '全量刷新' }}
        </button>
        <button class="btn-primary" :disabled="fullBackingUp" @click="handleFullBackup">
          <svg v-if="fullBackingUp" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
          {{ fullBackingUp ? '全量备份中…' : '全量备份' }}
        </button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="panel px-4 py-3 flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 min-w-[200px]">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="search" placeholder="搜索名称 / IP / 型号 / 位置…" class="input pl-9" />
        </div>
        <div class="text-[10px] text-ink-500 font-mono">{{ filtered.length }} 台设备</div>
      </div>

      <div v-if="refreshMsg" class="panel p-3 text-xs text-ink-700">{{ refreshMsg }}</div>

      <div v-if="filtered.length === 0" class="panel p-12 text-center text-sm text-ink-500">暂无设备</div>

      <div v-else-if="view === 'table'" class="panel overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
              <th class="px-4 py-3 text-left font-medium">名称</th>
              <th class="px-4 py-3 text-left font-medium">IP</th>
              <th class="px-4 py-3 text-left font-medium">型号</th>
              <th class="px-4 py-3 text-left font-medium">软件包</th>
              <th class="px-4 py-3 text-left font-medium">位置</th>
              <th class="px-4 py-3 text-left font-medium">状态</th>
              <th class="px-4 py-3 text-right font-medium w-32">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-canvas-300">
            <tr v-for="d in filtered" :key="d.id" class="hover:bg-canvas-100 transition">
              <td class="px-4 py-3 text-sm font-medium text-ink-900">{{ d.name }}</td>
              <td class="px-4 py-3 font-mono text-xs text-ink-900">{{ d.host }}</td>
              <td class="px-4 py-3 text-xs text-ink-900">{{ d.model }}</td>
              <td class="px-4 py-3 font-mono text-[10px] text-ink-500">{{ d.software }}</td>
              <td class="px-4 py-3 text-xs text-ink-700">{{ d.location || '—' }}</td>
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
                    <span>{{ refreshingIds.has(d.id) ? '采集中…' : '采集' }}</span>
                  </button>
                  <button class="btn-soft !text-[11px] !px-2 !py-1" @click="onEditAsset(d)">编辑资产</button>
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
            <span class="chip-mute !text-[10px]">{{ devs.length }} 台</span>
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
                    title="采集资产"
                    @click="refreshOne(d.id)"
                  >
                    <svg v-if="refreshingIds.has(d.id)" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                    <svg v-else class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 12a9 9 0 11-9-9c2.5 0 4.7 1 6.4 2.6L21 8"/><path d="M21 3v5h-5"/></svg>
                  </button>
                  <button class="text-ink-500 hover:text-accent p-1" title="编辑资产" @click="onEditAsset(d)">
                    <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                  </button>
                </div>
              </div>
              <div class="space-y-1.5 text-xs">
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">型号</span><span class="text-ink-900 font-mono truncate">{{ d.model }}</span></div>
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">软件包</span><span class="text-ink-900 font-mono text-[10px] truncate">{{ d.software }}</span></div>
                <div class="flex justify-between gap-2"><span class="text-ink-500 shrink-0">位置</span><span class="text-ink-900 text-[10px] truncate">{{ d.location || '—' }}</span></div>
              </div>
              <div v-if="d.tags.length" class="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-canvas-300">
                <span v-for="t in d.tags" :key="t" class="chip-mute !text-[10px]">#{{ t }}</span>
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
              <h3 class="text-base font-semibold text-ink-900">全量备份结果</h3>
              <button class="btn-soft !text-xs" @click="fullResultOpen = false">关闭</button>
            </div>
            <div class="px-5 py-4 space-y-3">
              <div v-if="fullResult" class="text-sm space-y-2">
                <div class="flex items-center gap-2 text-good">
                  <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 13l4 4L19 7"/></svg>
                  <span>成功 <b>{{ fullResult.success.length }}</b> 台</span>
                </div>
                <div v-if="fullResult.failed.length > 0" class="flex items-start gap-2 text-bad">
                  <svg class="size-4 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                  <div>
                    <div>失败 <b>{{ fullResult.failed.length }}</b> 台</div>
                    <ul class="mt-1 ml-4 text-[11px] space-y-0.5 list-disc">
                      <li v-for="(f, i) in fullResult.failed" :key="i">
                        设备 ID {{ f.device_id }} — {{ f.error }}
                      </li>
                    </ul>
                  </div>
                </div>
                <div v-if="fullResult.success.length > 0" class="text-[11px] text-ink-500">
                  备份详情：{{ fullResult.success.length }} 份新备份已入库
                </div>
                <div class="text-[11px] text-ink-500 pt-2 border-t border-canvas-300">
                  前往 <b>配置备份</b> 页面查看 / 下载 / 回滚
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
