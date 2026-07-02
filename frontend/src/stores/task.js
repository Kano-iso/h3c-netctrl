// 异步任务管理 Pinia store（v24-feat-async-backup-status）
//
// 维护后台备份/回滚任务状态，前端轮询 + localStorage 持久化。
// 切页面/刷新浏览器后，未完成任务可从 localStorage 恢复并继续轮询。
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskApi } from '../api/index.js'

const STORAGE_KEY = 'h3c-netctrl-tasks'
const POLL_INTERVAL = 2000  // 2s 轮询
const PERSIST_INTERVAL = 5000  // 5s 持久化
const MAX_HISTORY = 20  // 最多保留历史任务数

export const useTaskStore = defineStore('task', () => {
  // state: { [taskId]: { task_id, task_type, device_id, status, progress, result, error, created_at, updated_at, _label } }
  const tasks = ref({})
  const _timers = {}  // taskId -> intervalId（非响应式）
  let _persistTimer = null

  // computed
  const runningTasks = computed(() =>
    Object.values(tasks.value).filter(t => t.status === 'pending' || t.status === 'running')
  )
  const recentTasks = computed(() =>
    Object.values(tasks.value)
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
      .slice(0, MAX_HISTORY)
  )
  const hasRunning = computed(() => runningTasks.value.length > 0)
  const runningCount = computed(() => runningTasks.value.length)

  // 提交异步备份
  async function submitBackup(deviceId, types, label) {
    const r = await taskApi.backupAsync(deviceId, types)
    if (!r.success) {
      return { success: false, error: r.error }
    }
    const taskId = r.data.task_id
    tasks.value[taskId] = {
      task_id: taskId,
      task_type: 'backup',
      device_id: deviceId,
      status: r.data.status,
      progress: 0,
      _label: label || `备份 #${deviceId}`,
    }
    _startPolling(taskId)
    _persist()
    return { success: true, task_id: taskId }
  }

  // 提交异步回滚
  async function submitRestore(deviceId, backupId, withReboot, label) {
    const r = await taskApi.restoreAsync(deviceId, backupId, withReboot)
    if (!r.success) {
      return { success: false, error: r.error }
    }
    const taskId = r.data.task_id
    tasks.value[taskId] = {
      task_id: taskId,
      task_type: 'restore',
      device_id: deviceId,
      status: r.data.status,
      progress: 0,
      _label: label || `回滚 #${deviceId}`,
    }
    _startPolling(taskId)
    _persist()
    return { success: true, task_id: taskId }
  }

  // 批量提交异步备份（全量备份用）
  // 串行提交，避免瞬间 N 个 HTTP 请求；后台 TaskManager max_workers=1 保证串行执行
  async function submitBatchBackup(devices, types, labelFn) {
    const results = []
    for (const d of devices) {
      const label = labelFn ? labelFn(d) : `全量备份 ${d.name || '#' + d.id}`
      const r = await submitBackup(d.id, types, label)
      results.push({ device_id: d.id, device_name: d.name, ...r })
    }
    return results
  }

  // 取消任务
  async function cancelTask(taskId) {
    const r = await taskApi.cancel(taskId)
    if (r.success && r.data.cancelled) {
      const t = tasks.value[taskId]
      if (t && (t.status === 'pending' || t.status === 'running')) {
        t.status = 'cancelled'
      }
      _stopPolling(taskId)
      _persist()
      return true
    }
    return false
  }

  // 轮询一次
  async function _pollOnce(taskId) {
    const r = await taskApi.get(taskId)
    if (!r.success) {
      // 任务不存在（可能 DB 被清理），停止轮询并标记
      const t = tasks.value[taskId]
      if (t && (t.status === 'pending' || t.status === 'running')) {
        t.status = 'failed'
        t.error = r.error || '任务不存在'
      }
      _stopPolling(taskId)
      _persist()
      return
    }
    const data = r.data
    const old = tasks.value[taskId]
    tasks.value[taskId] = { ...old, ...data, _label: old?._label }
    if (['success', 'failed', 'cancelled'].includes(data.status)) {
      _stopPolling(taskId)
    }
    _persist()
  }

  function _startPolling(taskId) {
    if (_timers[taskId]) return
    // 立即轮询一次，然后定时
    _pollOnce(taskId)
    _timers[taskId] = setInterval(() => _pollOnce(taskId), POLL_INTERVAL)
  }

  function _stopPolling(taskId) {
    const id = _timers[taskId]
    if (id) {
      clearInterval(id)
      delete _timers[taskId]
    }
  }

  function _persist() {
    try {
      const arr = Object.values(tasks.value)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(arr))
    } catch (e) {
      console.warn('任务状态持久化失败:', e)
    }
  }

  // 启动时恢复未完成任务
  function restoreFromLocalStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        // 启动定期持久化
        _ensurePersistTimer()
        return
      }
      const arr = JSON.parse(raw)
      const newMap = {}
      for (const t of arr) {
        newMap[t.task_id] = t
        // 未完成的任务恢复轮询（可能是上次刷新前提交的）
        if (t.status === 'pending' || t.status === 'running') {
          _startPolling(t.task_id)
        }
      }
      tasks.value = newMap
    } catch (e) {
      console.warn('恢复任务状态失败:', e)
    }
    _ensurePersistTimer()
  }

  function _ensurePersistTimer() {
    if (_persistTimer) return
    _persistTimer = setInterval(_persist, PERSIST_INTERVAL)
  }

  // 清理已完成的任务历史
  function clearHistory() {
    const keep = {}
    for (const t of Object.values(tasks.value)) {
      // 保留 running/pending
      if (!['success', 'failed', 'cancelled'].includes(t.status)) {
        keep[t.task_id] = t
      }
    }
    tasks.value = keep
    _persist()
  }

  // 移除单个任务记录（仅终态可移除）
  function removeTask(taskId) {
    const t = tasks.value[taskId]
    if (!t) return
    if (!['success', 'failed', 'cancelled'].includes(t.status)) return
    delete tasks.value[taskId]
    _persist()
  }

  return {
    tasks,
    runningTasks,
    recentTasks,
    hasRunning,
    runningCount,
    submitBackup,
    submitBatchBackup,
    submitRestore,
    cancelTask,
    restoreFromLocalStorage,
    clearHistory,
    removeTask,
  }
})
