<script setup>
import { ref, computed, onMounted } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { deviceApi, assetApi } from '../api/index.js'

const loading = ref(true)
const error = ref('')
const items = ref([])
const search = ref('')
const view = ref('table')
const refreshing = ref(false)
const refreshMsg = ref('')

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
        status: a.status || 'unknown',
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

const filtered = computed(() => {
  if (!search.value) return items.value
  const q = search.value.toLowerCase()
  return items.value.filter(d => `${d.name} ${d.host} ${d.model} ${d.software} ${d.location}`.toLowerCase().includes(q))
})

const groupBy = (key) => {
  const groups = {}
  for (const d of filtered.value) {
    const k = d[key] || 'unknown'
    if (!groups[k]) groups[k] = []
    groups[k].push(d)
  }
  return groups
}

const byStatus = computed(() => groupBy('status'))

const statusChip = (s) => s === 'online' ? 'chip-good' : s === 'warning' || s === 'maintenance' ? 'chip-warn' : s === 'offline' ? 'chip-bad' : 'chip-mute'
const statusText = (s) => s === 'online' ? '在线' : s === 'warning' ? '告警' : s === 'maintenance' ? '维护' : s === 'offline' ? '离线' : '未知'
const statusLabel = (s) => ({
  online: '在线',
  warning: '告警',
  maintenance: '维护',
  offline: '离线',
  unknown: '未知',
})[s] || s || '未知'
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
                <span :class="statusChip(d.status)">{{ statusText(d.status) }}</span>
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
                <span :class="statusChip(d.status)">{{ statusText(d.status) }}</span>
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
  </template>
</template>
