<template>
  <div>
    <h4 class="mb-4"><i class="bi bi-terminal me-2"></i>网络运维终端</h4>

    <!-- 设备选择 + 命令输入 -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-md-4">
            <label class="form-label">目标设备</label>
            <select class="form-select" v-model="selectedDeviceId">
              <option value="">请选择设备</option>
              <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }} ({{ d.host }})</option>
            </select>
          </div>
          <div class="col-md-6">
            <label class="form-label">命令</label>
            <div class="input-group">
              <input type="text" class="form-control" v-model="command" placeholder="输入命令，如 display version" @keyup.enter="executeCommand">
              <button class="btn btn-primary" @click="executeCommand" :disabled="executing || !selectedDeviceId || !command">
                <span v-if="executing" class="spinner-border spinner-border-sm me-1"></span>
                执行
              </button>
            </div>
            <div v-if="longRunningTip" class="text-muted small mt-1">
              <i class="bi bi-info-circle me-1"></i>命令执行中，您可以切换到其他页面
            </div>
          </div>
          <div class="col-md-2">
            <label class="form-label">历史</label>
            <select class="form-select form-select-sm" v-model="command" v-if="commandHistory.length > 0">
              <option value="">选择历史命令</option>
              <option v-for="cmd in commandHistory" :key="cmd" :value="cmd">{{ cmd }}</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-danger alert-dismissible fade show">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- 输出展示区 -->
    <div class="card border-0 shadow-sm">
      <div class="card-header bg-transparent d-flex justify-content-between align-items-center">
        <h6 class="mb-0">输出</h6>
        <span v-if="lastExecutionTime" class="text-muted small">执行耗时: {{ lastExecutionTime }}s</span>
      </div>
      <div class="card-body">
        <div v-if="!output && !error" class="text-center py-5 text-muted">
          <i class="bi bi-terminal fs-1"></i>
          <p class="mt-2">选择设备并输入命令开始</p>
        </div>
        <pre v-else class="bg-dark text-light p-3 rounded mb-0" style="max-height: 500px; overflow-y: auto; font-size: 0.85rem; white-space: pre-wrap;">{{ output }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { deviceApi, apiCall } from '../api'

const devices = ref([])
const selectedDeviceId = ref('')
const command = ref('')
const output = ref('')
const executing = ref(false)
const error = ref('')
const lastExecutionTime = ref(null)
const commandHistory = ref([])
const longRunningTip = ref(false)
let longRunningTimer = null

async function loadDevices() {
  const res = await deviceApi.list()
  if (res.success) {
    devices.value = res.data || []
  }
}

async function executeCommand() {
  if (!selectedDeviceId.value || !command.value) return
  executing.value = true
  error.value = ''
  output.value = ''
  longRunningTip.value = false
  longRunningTimer = setTimeout(() => { longRunningTip.value = true }, 5000)

  const res = await apiCall(`/devices/${selectedDeviceId.value}/execute`, {
    method: 'POST',
    body: JSON.stringify({ command: command.value }),
  })

  clearTimeout(longRunningTimer)
  longRunningTip.value = false

  if (res.success) {
    output.value = res.data.output
    lastExecutionTime.value = res.data.execution_time
    // 添加到历史
    const cmd = command.value.trim()
    if (!commandHistory.value.includes(cmd)) {
      commandHistory.value.unshift(cmd)
      if (commandHistory.value.length > 20) commandHistory.value.pop()
      localStorage.setItem('cmdHistory', JSON.stringify(commandHistory.value))
    }
  } else {
    error.value = res.error || '命令执行失败'
  }
  executing.value = false
}

onMounted(() => {
  loadDevices()
  const saved = localStorage.getItem('cmdHistory')
  if (saved) {
    try { commandHistory.value = JSON.parse(saved) } catch {}
  }
})
</script>
