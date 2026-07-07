// 全局 toast 通知 store（v2.6.2 fix-backup-restore-support Task 4）
//
// 4 种类型：success / error / warning / info
// 右上角浮动显示，自动消失（5s，error 8s），可手动关闭
//
// 用法：
//   import { useToastStore } from '../stores/toast.js'
//   const toast = useToastStore()
//   toast.error('备份失败: ...')
//
import { defineStore } from 'pinia'
import { ref } from 'vue'

const DEFAULT_DURATION = 5000
const ERROR_DURATION = 8000

let _id = 0

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])

  function push(type, message, duration) {
    const id = ++_id
    const finalDuration = duration ?? (type === 'error' ? ERROR_DURATION : DEFAULT_DURATION)
    toasts.value.push({ id, type, message, duration: finalDuration })
    if (finalDuration > 0) {
      setTimeout(() => remove(id), finalDuration)
    }
    return id
  }

  function success(msg, duration) { return push('success', msg, duration) }
  function error(msg, duration) { return push('error', msg, duration) }
  function warning(msg, duration) { return push('warning', msg, duration) }
  function info(msg, duration) { return push('info', msg, duration) }

  function remove(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function clear() {
    toasts.value = []
  }

  return { toasts, success, error, warning, info, remove, clear }
})
