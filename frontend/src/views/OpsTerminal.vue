<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import Select from '../components/Select.vue'
import { deviceApi, executeApi } from '../api/index.js'

const { t, locale } = useI18n()

const loading = ref(true)
const error = ref('')
const devices = ref([])
const selectedDeviceId = ref(null)
const command = ref('display version')
const delayMs = ref(1000)
const running = ref(false)
const output = ref([])
const history = ref([])
const container = ref(null)

async function loadDevices() {
  loading.value = true
  const r = await deviceApi.list()
  if (!r.success) {
    error.value = r.error || t('errors.network_failed')
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

// 解析 textarea 内容为命令列表（按 \n 拆分，trim 空白，跳过空行）
const parseCommands = (text) => {
  return text.split('\n').map(s => s.trim()).filter(Boolean)
}

// 数字 input 兜底（< 0 或非数字 → 0）
const safeDelay = () => {
  const v = parseInt(delayMs.value, 10)
  if (isNaN(v) || v < 0) return 0
  return v
}

const onTextareaKeydown = (event) => {
  // Enter（无 shift）→ 提交；Shift+Enter → 插入换行（默认行为）
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    execute()
  }
}

const formatTime = () => new Date().toLocaleTimeString(locale.value === 'en-US' ? 'en-US' : 'zh-CN', { hour: '2-digit', minute: '2-digit' })

const execute = async () => {
  const cmds = parseCommands(command.value)
  if (cmds.length === 0 || running.value || !selectedDeviceId.value) return

  running.value = true
  const total = cmds.length
  const isMulti = total > 1
  const dms = safeDelay() || 1000

  // 显示每条命令
  cmds.forEach((cmd, i) => {
    output.value.push({
      type: 'cmd-multi',
      text: isMulti
        ? t('ops.cmd_prefix_multi', { i: i + 1, n: total, cmd })
        : t('ops.cmd_prefix_single', { device: selectedDevice().name, cmd }),
    })
  })

  let r
  if (isMulti) {
    r = await executeApi.run(selectedDeviceId.value, { commands: cmds, delay_ms: dms })
    if (r.success && r.data && Array.isArray(r.data.results)) {
      r.data.results.forEach((res, _i) => {
        output.value.push({
          type: 'output',
          text: res.output || t('batch.no_output'),
        })
        if (!res.success) {
          output.value.push({
            type: 'fail',
            text: t('ops.fail_prefix', { error: res.error || t('batch.cmd_failed') }),
          })
        }
      })
      // 末尾失败 banner
      if (r.data.failed_count > 0) {
        output.value.push({
          type: 'banner',
          text: t('ops.summary_multi', { n: r.data.total, failed: r.data.failed_count }),
        })
      }
    } else {
      output.value.push({ type: 'output', text: t('ops.error_prefix', { error: r.error || t('batch.cmd_failed') }) })
    }
  } else {
    // 单命令走旧路径，保持向后兼容
    r = await executeApi.run(selectedDeviceId.value, { command: cmds[0] })
    if (r.success && r.data) {
      output.value.push({ type: 'output', text: r.data.output || t('batch.no_output') })
    } else {
      output.value.push({ type: 'output', text: t('ops.error_prefix', { error: r.error || t('batch.cmd_failed') }) })
    }
  }

  // 历史命令存多命令模板（join 后的字符串）
  history.value.unshift({
    cmd: cmds.join('\n'),
    device: selectedDevice().name,
    time: formatTime(),
    isMulti: isMulti,
  })
  command.value = ''
  running.value = false
  nextTick(() => { container.value && (container.value.scrollTop = container.value.scrollHeight) })
}

const clearOutput = () => { output.value = [] }
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('common.loading') }}</div>
  <div v-else-if="error" class="max-w-[1200px] mx-auto px-8 py-16">
    <div class="panel p-6 border border-bad/30 bg-bad/5">
      <div class="text-bad font-medium">{{ t('ops.load_failed') }}</div>
      <div class="text-sm text-ink-700 mt-1">{{ error }}</div>
      <button class="btn-outline mt-3" @click="loadDevices">{{ t('common.retry') }}</button>
    </div>
  </div>
  <template v-else>
    <PageHeader :title="t('ops.title')" :subtitle="t('ops.subtitle')">
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
            <div class="text-sm font-semibold text-ink-900">{{ t('ops.history') }}</div>
            <span class="text-[10px] text-ink-500 font-mono">{{ t('ops.count_entries', { n: history.length }) }}</span>
          </div>
          <div v-if="history.length === 0" class="text-xs text-ink-500 py-4 text-center">{{ t('ops.no_history') }}</div>
          <div v-else class="space-y-1">
            <button v-for="(h, i) in history" :key="i" @click="command = h.cmd" class="w-full text-left px-3 py-2 rounded-lg hover:bg-canvas-200 transition">
              <div class="flex items-center justify-between gap-2">
                <div class="text-xs font-mono text-ink-900 truncate flex-1" :class="{ 'whitespace-pre-wrap': h.isMulti }">{{ h.isMulti ? t('ops.count_cmds', { n: h.cmd.split('\n').length }) : h.cmd }}</div>
                <div class="text-[10px] text-ink-500 shrink-0">{{ h.time }}</div>
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
              <span class="text-[10px] text-ink-500">{{ t('ops.netconf_label') }}</span>
            </div>
            <button class="btn-soft !text-xs !px-3 !py-1" @click="clearOutput">{{ t('ops.clear') }}</button>
          </div>

          <!-- 命令输入区（textarea + 延迟设置） -->
          <div class="border-b border-canvas-300 p-3 bg-canvas-50">
            <div class="flex items-start gap-2">
              <span class="text-accent font-mono text-sm pt-2">$</span>
              <textarea
                v-model="command"
                @keydown="onTextareaKeydown"
                :disabled="running"
                rows="4"
                :placeholder="t('ops.terminal_placeholder')"
                class="flex-1 bg-white border border-canvas-300 rounded-lg px-3 py-2 text-[13px] font-mono text-ink-900 placeholder:text-ink-500 focus:outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/15 resize-y min-h-[6rem]"
                style="font-family: 'Menlo', 'Consolas', 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace;"
              ></textarea>
            </div>
            <div class="flex items-center justify-between mt-2 gap-2">
              <div class="flex items-center gap-2 text-xs text-ink-600">
                <label class="flex items-center gap-1.5">
                  <span>{{ t('ops.delay_label') }}</span>
                  <input
                    v-model.number="delayMs"
                    type="number"
                    :disabled="running"
                    min="0"
                    step="100"
                    class="w-20 bg-white border border-canvas-300 rounded-md px-2 py-1 text-xs font-mono text-ink-900 focus:outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/15"
                  />
                  <span class="text-[10px] text-ink-500">{{ t('ops.delay_unit') }}</span>
                </label>
                <span v-if="command.split('\n').filter(s => s.trim()).length > 1" class="text-accent font-mono">
                  {{ t('ops.will_send', { n: command.split('\n').filter(s => s.trim()).length }) }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <kbd class="hidden md:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-canvas-200 text-[10px] text-ink-700 font-mono">{{ t('ops.enter_key') }}</kbd>
                <kbd class="hidden md:inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-canvas-200 text-[10px] text-ink-700 font-mono">{{ t('ops.shift_enter') }}</kbd>
                <button @click="execute" :disabled="running || !command.trim()" class="btn-primary !text-xs !py-1.5">
                  <svg v-if="running" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                  <span v-else>{{ t('ops.run') }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 终端输出区 -->
          <div ref="container" class="flex-1 overflow-y-auto p-4 bg-ink-950 font-mono text-[13px] leading-relaxed text-green-400" style="font-family: 'Menlo', 'Consolas', 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace; font-weight: 500;">
            <div v-for="(line, i) in output" :key="i" class="whitespace-pre-wrap">
              <div v-if="line.type === 'cmd' || line.type === 'cmd-multi'" class="text-cyan-400 font-semibold mt-2">{{ line.text }}</div>
              <div v-else-if="line.type === 'fail'" class="text-red-400 font-semibold">{{ line.text }}</div>
              <div v-else-if="line.type === 'banner'" class="text-yellow-400 font-semibold mt-2 border-t border-yellow-400/30 pt-2">{{ line.text }}</div>
              <div v-else>{{ line.text }}</div>
            </div>
            <div v-if="output.length === 0" class="text-ink-500">{{ t('ops.output_placeholder') }}</div>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
