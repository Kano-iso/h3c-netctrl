<script setup>
import { ref, onMounted } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { deviceApi, batchApi } from '../api/index.js'

const loading = ref(true)
const error = ref('')
const devices = ref([])
const selected = ref(new Set())
const command = ref('display version')
const running = ref(false)
const results = ref(null)
const summary = ref({ total: 0, success_count: 0, failed_count: 0 })
const execError = ref('')

const quickCmds = ['display version', 'display cpu-usage', 'display vlan all', 'display interface brief']

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
  loading.value = false
}

onMounted(loadDevices)

const toggle = (id) => {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
  selected.value = new Set(selected.value)
}

const statusChip = (s) => s === 'online' ? 'chip-good !text-[10px]' : s === 'warning' || s === 'maintenance' ? 'chip-warn !text-[10px]' : s === 'offline' ? 'chip-bad !text-[10px]' : 'chip-mute !text-[10px]'
const statusText = (s) => s === 'online' ? '在线' : s === 'warning' ? '告警' : s === 'maintenance' ? '维护' : s === 'offline' ? '离线' : s || '—'

const execute = async () => {
  if (selected.value.size === 0 || running.value) return
  if (!command.value.trim()) {
    execError.value = '请输入要执行的命令'
    return
  }
  running.value = true
  results.value = null
  summary.value = { total: 0, success_count: 0, failed_count: 0 }
  execError.value = ''
  const ids = Array.from(selected.value)
  const r = await batchApi.execute(ids, command.value.trim())
  running.value = false
  if (!r.success) {
    execError.value = r.error || '执行失败'
    return
  }
  const data = r.data || {}
  results.value = data.results || []
  summary.value = {
    total: data.total ?? results.value.length,
    success_count: data.success_count ?? results.value.filter(x => x.success).length,
    failed_count: data.failed_count ?? results.value.filter(x => !x.success).length,
  }
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
    <PageHeader title="批量操作" subtitle="多设备并行执行 · 结果汇总展示">
      <template #actions>
        <span class="chip-info">已选 {{ selected.size }} 台</span>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="panel p-5 lg:col-span-1">
          <div class="text-sm font-semibold text-ink-900 mb-3">选择设备</div>
          <div v-if="devices.length === 0" class="text-sm text-ink-500 py-6 text-center">暂无设备</div>
          <div v-else class="space-y-1 max-h-[420px] overflow-y-auto">
            <label v-for="d in devices" :key="d.id" class="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-canvas-200 cursor-pointer">
              <input type="checkbox" :checked="selected.has(d.id)" @change="toggle(d.id)" class="rounded border-canvas-400 text-accent focus:ring-accent/40" />
              <div class="flex-1 min-w-0">
                <div class="text-sm text-ink-900 truncate">{{ d.name }}</div>
                <div class="text-[10px] text-ink-500 font-mono">{{ d.host }}</div>
              </div>
              <span :class="statusChip(d.status)">
                {{ statusText(d.status) }}
              </span>
            </label>
          </div>
        </div>

        <div class="panel p-5 lg:col-span-2">
          <div class="text-sm font-semibold text-ink-900 mb-3">执行命令</div>
          <div class="flex gap-2 mb-3">
            <input v-model="command" placeholder="display version" class="input flex-1 font-mono" />
            <button @click="execute" :disabled="running || selected.size === 0 || !command.trim()" class="btn-primary disabled:opacity-50">
              <svg v-if="running" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              {{ running ? '执行中…' : '执行' }}
            </button>
          </div>
          <div class="flex flex-wrap gap-1.5 mt-2">
            <span class="text-[10px] text-ink-500 py-1">快速选择：</span>
            <button v-for="c in quickCmds" :key="c" @click="command = c" class="chip-mute hover:bg-canvas-300 !text-[10px]">{{ c }}</button>
          </div>
          <div v-if="execError" class="mt-3 p-3 rounded-xl bg-bad/8 border border-bad/30 text-xs text-bad">
            {{ execError }}
          </div>
        </div>
      </div>

      <div v-if="results" class="panel">
        <div class="px-5 py-3 border-b border-canvas-300 flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-ink-900">执行结果</div>
            <div class="text-xs text-ink-500">{{ summary.total }} 台设备</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="chip-good !text-[10px]">{{ summary.success_count }} 成功</span>
            <span class="chip-bad !text-[10px]">{{ summary.failed_count }} 失败</span>
          </div>
        </div>
        <div v-if="results.length === 0" class="p-8 text-center text-sm text-ink-500">无可展示结果</div>
        <div v-else class="divide-y divide-canvas-300">
          <div v-for="(r, i) in results" :key="i" class="p-4">
            <div class="flex items-center gap-3 mb-2">
              <span :class="r.success ? 'chip-good' : 'chip-bad'">{{ r.success ? '✓ 成功' : '✗ 失败' }}</span>
              <span class="text-sm font-medium text-ink-900">{{ r.device_name || ('设备 #' + r.device_id) }}</span>
              <span class="text-[10px] text-ink-500 font-mono">#{{ r.device_id }}</span>
            </div>
            <pre v-if="r.success" class="text-[10px] font-mono text-ink-700 bg-canvas-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">{{ r.output || '(无输出)' }}</pre>
            <div v-else class="text-[10px] text-bad bg-bad/5 border border-bad/30 rounded-lg p-3 font-mono whitespace-pre-wrap">
              {{ r.error || '命令执行失败' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
