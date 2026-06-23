<script setup>
import { ref, onMounted } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { dashboardApi, assetApi, deviceApi } from '../api/index.js'

const loading = ref(true)
const error = ref('')
const stats = ref([
  { key: 'devices', label: '在管设备', value: '—', sub: '加载中…', trend: '', color: 'info' },
  { key: 'online', label: '在线设备', value: '—', sub: '加载中…', trend: '', color: 'good' },
  { key: 'interfaces', label: '管理接口', value: '—', sub: '加载中…', trend: '', color: 'accent' },
  { key: 'ops', label: '今日操作', value: '—', sub: '加载中…', trend: '', color: 'warn' },
])
const recentLogs = ref([])
const recentFailures = ref([])
const devicesOverview = ref([])

// 设备总览：拉取设备列表 + 每台设备的 asset，拼装成首页展示卡
async function loadDevicesOverview() {
  const dr = await deviceApi.list()
  if (!dr.success) {
    devicesOverview.value = []
    return
  }
  const list = dr.data || []
  // 并发拉每台设备的 asset
  const enriched = await Promise.all(
    list.map(async (d) => {
      const ar = await assetApi.get(d.id)
      const a = ar.success ? ar.data : {}
      return {
        id: d.id,
        name: d.name,
        host: d.host,
        model: a.model || '—',
        software: a.software_package || '—',
        ports: a.ports || 0,
        location: a.location || '',
        status: a.status || 'unknown',
        tags: a.tags ? a.tags.split(',').map(s => s.trim()).filter(Boolean) : [],
        role: 'device',
        protected: d.protected_interfaces || [],
      }
    })
  )
  devicesOverview.value = enriched
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  const r = await dashboardApi.get()
  if (!r.success) {
    error.value = r.error || '加载失败'
    loading.value = false
    return
  }
  const data = r.data || {}
  const ds = data.device_stats || {}
  stats.value = [
    { key: 'devices', label: '在管设备', value: String(ds.total ?? 0), sub: `共 ${ds.total ?? 0} 台`, trend: '', color: 'info' },
    { key: 'online', label: '在线设备', value: String(ds.online ?? 0), sub: `${ds.offline ?? 0} 离线`, trend: '', color: 'good' },
    { key: 'interfaces', label: '管理接口', value: '—', sub: '需接口数据', trend: '', color: 'accent' },
    { key: 'ops', label: '今日操作', value: String((data.recent_logs || []).length), sub: `${(data.recent_failures || []).length} 失败`, trend: '', color: 'warn' },
  ]
  recentLogs.value = (data.recent_logs || []).map((l) => ({
    id: l.id,
    time: l.created_at ? l.created_at.substring(11, 19) : '',
    device: l.device_name,
    action: l.action,
    detail: l.detail,
    status: l.status,
  }))
  recentFailures.value = data.recent_failures || []
  await loadDevicesOverview()
  loading.value = false
}

onMounted(loadDashboard)

const statusChip = (s) => s === 'online' ? 'chip-good' : s === 'warning' || s === 'maintenance' ? 'chip-warn' : s === 'offline' ? 'chip-bad' : 'chip-mute'
const roleChip = () => 'chip-mute'
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">加载中…</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">仪表盘加载失败</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDashboard">重试</button>
    </div>
  </div>
  <template v-else>
    <PageHeader
      title="网络运维总览"
      :subtitle="`${stats[0].value} 台设备 · ${stats[1].value} 在线 · ${stats[2].value} 接口待采集`"
    >
      <template #actions>
        <button class="btn-outline" @click="loadDashboard">刷新</button>
        <RouterLink :to="{ name: 'batch' }" class="btn-primary">新建任务</RouterLink>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-5">
      <!-- KPI 卡片 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div v-for="s in stats" :key="s.key" class="panel panel-hover p-6">
          <div class="flex items-center justify-between">
            <div class="section-title">{{ s.label }}</div>
          </div>
          <div class="mt-3 kpi-num">{{ s.value }}</div>
          <div class="text-xs text-ink-500 mt-1.5">{{ s.sub }}</div>
        </div>
      </div>

      <!-- 设备总览和快速入口 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <!-- 设备总览 -->
        <div class="panel p-6 lg:col-span-2">
          <div class="flex items-center justify-between mb-5">
            <div class="text-base font-semibold text-ink-900 leading-tight">设备总览</div>
            <RouterLink :to="{ name: 'devices' }" class="link-pill">查看全部
              <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </RouterLink>
          </div>
          <div v-if="devicesOverview.length === 0" class="text-sm text-ink-500 py-8 text-center">暂无设备</div>
          <div v-else class="divide-y divide-canvas-300">
            <div v-for="d in devicesOverview" :key="d.id" class="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <div :class="['size-2 rounded-full shrink-0',
                d.status === 'online' ? 'bg-good' : d.status === 'warning' || d.status === 'maintenance' ? 'bg-warn' : d.status === 'offline' ? 'bg-bad' : 'bg-ink-400']" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-semibold text-ink-900">{{ d.name }}</span>
                  <span :class="roleChip()">{{ d.role }}</span>
                  <span v-for="t in d.tags" :key="t" class="chip-mute !text-[10px]">{{ t }}</span>
                </div>
                <div class="text-[12px] mt-1 flex items-center gap-1.5">
                  <span class="num-mono text-ink-700">{{ d.host }}</span>
                  <span class="text-ink-300">·</span>
                  <span class="text-ink-600">{{ d.model }}</span>
                </div>
              </div>
              <div class="text-right">
                <div class="text-[13px]">
                  <span :class="statusChip(d.status)">{{ d.status }}</span>
                </div>
                <div v-if="d.location" class="text-[10px] text-ink-500 mt-0.5">{{ d.location.split('·')[0].trim() }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 快速入口 -->
        <div class="panel p-6">
          <div class="text-base font-semibold text-ink-900 leading-tight mb-5">快速入口</div>
          <div class="grid grid-cols-2 gap-2.5">
            <RouterLink :to="{ name: 'ops' }" class="p-3.5 rounded-2xl bg-canvas-100 hover:bg-white ring-1 ring-transparent hover:ring-canvas-300 hover:shadow-soft transition-all">
              <div class="text-[13px] font-medium text-ink-900">运维终端</div>
              <div class="text-[10px] text-ink-500 mt-0.5">执行命令</div>
            </RouterLink>
            <RouterLink :to="{ name: 'interfaces' }" class="p-3.5 rounded-2xl bg-canvas-100 hover:bg-white ring-1 ring-transparent hover:ring-canvas-300 hover:shadow-soft transition-all">
              <div class="text-[13px] font-medium text-ink-900">接口管理</div>
              <div class="text-[10px] text-ink-500 mt-0.5">配置 vlan</div>
            </RouterLink>
            <RouterLink :to="{ name: 'batch' }" class="p-3.5 rounded-2xl bg-canvas-100 hover:bg-white ring-1 ring-transparent hover:ring-canvas-300 hover:shadow-soft transition-all">
              <div class="text-[13px] font-medium text-ink-900">批量操作</div>
              <div class="text-[10px] text-ink-500 mt-0.5">多设备</div>
            </RouterLink>
            <RouterLink :to="{ name: 'cmdb' }" class="p-3.5 rounded-2xl bg-canvas-100 hover:bg-white ring-1 ring-transparent hover:ring-canvas-300 hover:shadow-soft transition-all">
              <div class="text-[13px] font-medium text-ink-900">CMDB</div>
              <div class="text-[10px] text-ink-500 mt-0.5">资产盘点</div>
            </RouterLink>
          </div>
        </div>
      </div>

      <!-- 最近操作 -->
      <div class="panel p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="text-base font-semibold text-ink-900 leading-tight">最近操作</div>
          <RouterLink :to="{ name: 'logs' }" class="link-pill">查看全部
            <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M5 12h14M12 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </RouterLink>
        </div>
        <div v-if="recentLogs.length === 0" class="text-sm text-ink-500 py-6 text-center">暂无操作记录</div>
        <div v-else class="divide-y divide-canvas-300">
          <div v-for="log in recentLogs" :key="log.id" class="py-2.5 flex items-center gap-3 text-sm">
            <span class="text-xs text-ink-500 font-mono w-16">{{ log.time }}</span>
            <span class="chip-mute !text-[10px]">{{ log.action }}</span>
            <span class="text-ink-900 flex-1 truncate">{{ log.device }} · {{ log.detail }}</span>
            <span :class="log.status === 'success' ? 'chip-good' : log.status === 'warning' ? 'chip-warn' : 'chip-bad'">
              {{ log.status === 'success' ? '成功' : log.status === 'warning' ? '告警' : '失败' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
