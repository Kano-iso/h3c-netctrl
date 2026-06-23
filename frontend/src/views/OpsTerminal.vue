<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { deviceApi, executeApi } from '../api/index.js'

const loading = ref(true)
const error = ref('')
const devices = ref([])
const selectedDeviceId = ref(null)
const command = ref('display version')
const running = ref(false)
const output = ref([])
const history = ref([])
const container = ref(null)

async function loadDevices() {
  loading.value = true
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

onMounted(loadDevices)

// 切换设备时清空终端输出（避免不同设备的输出混在一起）
watch(selectedDeviceId, () => {
  output.value = []
})

const selectedDevice = () => devices.value.find(d => d.id === selectedDeviceId.value) || {}

const execute = async () => {
  if (!command.value.trim() || running.value || !selectedDeviceId.value) return
  running.value = true
  output.value.push({ type: 'cmd', text: `[${selectedDevice().name}] ${command.value}` })

  const r = await executeApi.run(selectedDeviceId.value, command.value.trim())
  if (r.success && r.data) {
    output.value.push({ type: 'output', text: r.data.output || '(无输出)' })
  } else {
    output.value.push({ type: 'output', text: `[错误] ${r.error || '命令执行失败'}` })
  }

  history.value.unshift({
    cmd: command.value,
    device: selectedDevice().name,
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  })
  command.value = ''
  running.value = false
  nextTick(() => { container.value && (container.value.scrollTop = container.value.scrollHeight) })
}

const clearOutput = () => { output.value = [] }
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
    <PageHeader title="运维终端" subtitle="命令派发式执行 · 实时回显 · 操作自动入日志">
      <template #actions>
        <Select
          v-model="selectedDeviceId"
          :options="devices"
          :custom-label="(d) => d.name"
          :sub-label="(d) => d.host"
          width="w-60"
        />
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16">
      <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <!-- History -->
        <div class="panel p-4 lg:col-span-1">
          <div class="flex items-center justify-between mb-3">
            <div class="text-sm font-semibold text-ink-900">历史命令</div>
            <span class="text-[10px] text-ink-500 font-mono">{{ history.length }} 条</span>
          </div>
          <div v-if="history.length === 0" class="text-xs text-ink-500 py-4 text-center">暂无历史</div>
          <div v-else class="space-y-1">
            <button v-for="(h, i) in history" :key="i" @click="command = h.cmd" class="w-full text-left px-3 py-2 rounded-lg hover:bg-canvas-200 transition">
              <div class="flex items-center justify-between">
                <div class="text-xs font-mono text-ink-900 truncate flex-1">{{ h.cmd }}</div>
                <div class="text-[10px] text-ink-500 ml-2">{{ h.time }}</div>
              </div>
              <div class="text-[10px] text-ink-500 mt-0.5">{{ h.device }}</div>
            </button>
          </div>
        </div>

        <!-- Terminal -->
        <div class="panel lg:col-span-3 flex flex-col h-[calc(100vh-220px)] overflow-hidden">
          <!-- 顶部状态栏 -->
          <div class="flex items-center justify-between px-4 py-2.5 border-b border-canvas-300">
            <div class="flex items-center gap-2">
              <span :class="['size-2 rounded-full', running ? 'bg-warn animate-pulse' : 'bg-good']"></span>
              <span class="text-xs font-mono text-ink-900">{{ selectedDevice().name }}@{{ selectedDevice().host }}</span>
              <span class="text-[10px] text-ink-500">NETCONF · port 830</span>
            </div>
            <button class="btn-soft !text-xs !px-3 !py-1" @click="clearOutput">清屏</button>
          </div>

          <!-- 命令输入区（放在终端输出上方） -->
          <div class="border-b border-canvas-300 p-3 flex items-center gap-2 bg-canvas-50">
            <span class="text-accent font-mono text-sm">$</span>
            <input
              v-model="command"
              @keyup.enter="execute"
              :disabled="running"
              placeholder="输入命令，如 display version"
              class="flex-1 bg-white border border-canvas-300 rounded-lg px-3 py-1.5 text-sm font-mono text-ink-900 placeholder:text-ink-500 focus:outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/15"
              style="font-family: 'Menlo', 'Consolas', 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace;"
            />
            <kbd class="hidden md:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-canvas-200 text-[10px] text-ink-700 font-mono">Enter</kbd>
            <button @click="execute" :disabled="running || !command.trim()" class="btn-primary !text-xs !py-1.5">
              <svg v-if="running" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <span v-else>执行</span>
            </button>
          </div>

          <!-- 终端输出区 -->
          <div ref="container" class="flex-1 overflow-y-auto p-4 bg-ink-950 font-mono text-[13px] leading-relaxed text-green-400" style="font-family: 'Menlo', 'Consolas', 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace; font-weight: 500;">
            <div v-for="(line, i) in output" :key="i" class="whitespace-pre-wrap">
              <div v-if="line.type === 'cmd'" class="text-cyan-400 font-semibold mt-2">{{ line.text }}</div>
              <div v-else>{{ line.text }}</div>
            </div>
            <div v-if="output.length === 0" class="text-ink-500">// 执行命令后输出会显示在这里…</div>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
