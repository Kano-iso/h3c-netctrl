<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmModal from './ConfirmModal.vue'
import { backupApi } from '../api/index.js'
import { useTaskStore } from '../stores/task.js'

const { t } = useI18n()

// v24-feat-async-backup-status: feature flag 控制异步模式
// VITE_ASYNC_BACKUP=true 启用，否则保持 v2.3 同步行为
const ASYNC_MODE = import.meta.env.VITE_ASYNC_BACKUP === 'true'
const taskStore = useTaskStore()

const props = defineProps({
  visible: { type: Boolean, default: false },
  deviceId: { type: Number, required: true },
  deviceName: { type: String, default: '' },
})

const emit = defineEmits(['update:visible', 'changed'])

// 状态
const backups = ref([])
const loading = ref(false)
const errMsg = ref('')
const busyId = ref(null)  // 正在操作的 backup.id（行级 busy）
const pageLoadingId = ref(null)  // 立即备份 / 列表刷新按钮级 busy

// ConfirmModal 状态
const confirm = ref({
  open: false,
  title: '',
  message: '',
  confirmText: '',
  variant: 'default',
  busy: false,
  action: null,  // 'delete' | 'lock' | 'unlock' | 'restore' | 'create'
  target: null,  // {id, filename, ...}
})

// 工具
function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(iso) {
  if (!iso) return '-'
  // 兼容 ISO 字符串，去掉时区尾巴、保留本地化
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function shortHash(h) {
  if (!h) return '-'
  return h.slice(0, 8)
}

// 列表加载
async function loadList() {
  loading.value = true
  errMsg.value = ''
  const r = await backupApi.list(props.deviceId)
  loading.value = false
  if (!r.success) {
    errMsg.value = r.error || t('backup.load_failed_devices')
    backups.value = []
    return
  }
  // v2.2 修复：后端返回 {device_id, total, backups: [...]} 嵌套结构
  // 兼容直接返回数组的旧行为（防御性写法）
  const data = r.data
  backups.value = (data && Array.isArray(data.backups) ? data.backups : data) || []
}

// 立即备份（顶部按钮）
async function handleCreate() {
  if (busyId.value !== null) return
  errMsg.value = ''

  // v24-feat-async-backup-status: 异步模式
  if (ASYNC_MODE) {
    pageLoadingId.value = 'create'
    const r = await taskStore.submitBackup(
      props.deviceId,
      ['startup', 'running'],
      t('backup.async_label', { name: props.deviceName || '#' + props.deviceId }),
    )
    pageLoadingId.value = null
    if (!r.success) {
      errMsg.value = r.error || t('backup.submit_failed')
      return
    }
    // 立即关闭弹窗，任务在后台执行，进度在右下角面板显示
    emit('changed', { action: 'create-async', task_id: r.task_id })
    emit('update:visible', false)
    return
  }

  // 同步模式（v2.3 行为）
  pageLoadingId.value = 'create'
  const r = await backupApi.create(props.deviceId)
  pageLoadingId.value = null
  if (!r.success) {
    errMsg.value = r.error || t('backup.op_failed', { error: t('common.dash') })
    return
  }
  await loadList()
  emit('changed', { action: 'create', backup: r.data })
}

// 触发操作
function askDelete(b) {
  confirm.value = {
    open: true,
    title: t('backup.confirm_delete_title'),
    message: t('backup.confirm_delete_msg', { name: props.deviceName, filename: b.filename }),
    confirmText: t('backup.confirm_delete_btn'),
    variant: 'danger',
    busy: false,
    action: 'delete',
    target: b,
  }
}

function askToggleLock(b) {
  const willLock = !b.locked
  confirm.value = {
    open: true,
    title: willLock ? t('backup.confirm_lock_title') : t('backup.confirm_unlock_title'),
    message: willLock
      ? t('backup.confirm_lock_msg', { name: props.deviceName, filename: b.filename })
      : t('backup.confirm_unlock_msg', { name: props.deviceName, filename: b.filename }),
    confirmText: t('backup.confirm_toggle_btn'),
    variant: 'default',
    busy: false,
    action: willLock ? 'lock' : 'unlock',
    target: b,
  }
}

function askRestore(b) {
  confirm.value = {
    open: true,
    title: t('backup.confirm_restore_title'),
    message: t('backup.confirm_restore_msg', {
      name: props.deviceName,
      filename: b.filename,
      time: formatTime(b.created_at),
      size: formatSize(b.size),
      hash: shortHash(b.content_hash),
    }),
    confirmText: t('backup.confirm_restore_btn'),
    variant: 'danger',
    busy: false,
    action: 'restore',
    target: b,
  }
}

// 执行确认的操作
async function onConfirmAction() {
  const { action, target } = confirm.value
  if (!action) return
  confirm.value.busy = true
  busyId.value = target.id

  // v24-feat-async-backup-status: 回滚异步模式
  if (ASYNC_MODE && action === 'restore') {
    const r = await taskStore.submitRestore(
      props.deviceId,
      target.id,
      true,  // with_reboot=true（与同步默认一致）
      t('backup.async_restore_label', { name: props.deviceName || '#' + props.deviceId, filename: target.filename }),
    )
    confirm.value.busy = false
    busyId.value = null

    if (!r.success) {
      confirm.value.message = `${t('backup.submit_restore_failed', { error: r.error || t('backup.unknown_error') })}\n\n${confirm.value.message}`
      return
    }
    // 立即关闭弹窗，任务在后台执行
    confirm.value.open = false
    emit('update:visible', false)
    emit('changed', { action: 'restore-async', task_id: r.task_id })
    return
  }

  // 同步模式（delete / lock / unlock / restore）
  let r
  if (action === 'delete') {
    r = await backupApi.remove(props.deviceId, target.id)
  } else if (action === 'lock' || action === 'unlock') {
    r = await backupApi.toggleLock(props.deviceId, target.id, action === 'lock')
  } else if (action === 'restore') {
    r = await backupApi.restore(props.deviceId, target.id)
  }

  confirm.value.busy = false
  busyId.value = null

  if (!r.success) {
    // 错误显示在 ConfirmModal 内
    confirm.value.message = `${t('backup.op_failed', { error: r.error || t('backup.unknown_error') })}\n\n${confirm.value.message}`
    return
  }

  // 成功 → 关闭 confirm → 刷新列表
  confirm.value.open = false
  await loadList()
  emit('changed', { action, backup: target, result: r.data })
}

function closeConfirm() {
  if (confirm.value.busy) return
  confirm.value.open = false
}

// 下载
async function handleDownload(b) {
  if (busyId.value !== null) return
  busyId.value = b.id
  const r = await backupApi.download(props.deviceId, b.id)
  busyId.value = null
  if (!r.success) {
    errMsg.value = r.error || t('backup.download_failed')
    return
  }
  // 触发浏览器下载
  const url = URL.createObjectURL(r.data.blob)
  const a = document.createElement('a')
  a.href = url
  a.download = r.data.filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 关闭 Modal
function close() {
  if (busyId.value !== null || pageLoadingId.value) return
  emit('update:visible', false)
}

// 响应 visible
watch(() => props.visible, async (v) => {
  if (v) {
    errMsg.value = ''
    await loadList()
  }
})

// ESC 关闭
function onKey(e) {
  if (e.key === 'Escape' && props.visible && busyId.value === null && !pageLoadingId.value) {
    close()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// 计算：空状态
const isEmpty = computed(() => !loading.value && backups.value.length === 0)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-3xl shadow-2xl flex flex-col" style="max-height: 80vh">
          <!-- 标题 -->
          <div class="px-5 py-4 border-b border-canvas-300 flex items-start justify-between gap-4">
            <div>
              <h3 class="text-base font-semibold text-ink-900">
                {{ t('form.backup_list.title', { name: deviceName }) }}
              </h3>
              <div class="text-xs text-ink-500 font-mono mt-0.5">
                {{ t('backup.subtitle') }}
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button
                class="btn-primary text-xs"
                :disabled="!!pageLoadingId"
                @click="handleCreate"
              >
                <svg v-if="pageLoadingId === 'create'" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                {{ pageLoadingId === 'create' ? t('backup.btn_backup_running', '备份中…') : t('backup.run_full') }}
              </button>
              <button class="btn-soft !text-xs" :disabled="!!busyId" @click="close">{{ t('form.backup_list.close') }}</button>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errMsg" class="px-5 py-2.5 bg-bad/8 border-b border-bad/30 text-xs text-bad">
            {{ errMsg }}
          </div>

          <!-- 内容 -->
          <div class="flex-1 overflow-y-auto">
            <div v-if="loading && backups.length === 0" class="px-5 py-12 text-center text-sm text-ink-500">
              {{ t('common.loading') }}
            </div>
            <div v-else-if="isEmpty" class="px-5 py-12 text-center text-sm text-ink-500">
              {{ t('form.backup_list.no_records') }} · {{ t('backup.run_full') }}
            </div>
            <table v-else class="w-full text-sm">
              <thead class="sticky top-0 bg-canvas-50">
                <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
                  <th class="px-4 py-2.5 text-left font-medium">{{ t('backup.col_filename') }}</th>
                  <th class="px-4 py-2.5 text-left font-medium">{{ t('backup.col_time') }}</th>
                  <th class="px-4 py-2.5 text-left font-medium">{{ t('backup.col_type') }}</th>
                  <th class="px-4 py-2.5 text-right font-medium">{{ t('backup.col_size') }}</th>
                  <th class="px-4 py-2.5 text-left font-medium">{{ t('backup.col_hash') }}</th>
                  <th class="px-4 py-2.5 text-center font-medium w-20">{{ t('backup.col_status') }}</th>
                  <th class="px-4 py-2.5 text-right font-medium w-56">{{ t('backup.col_actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-canvas-300">
                <tr v-for="b in backups" :key="b.id" class="hover:bg-canvas-50 transition">
                  <td class="px-4 py-2.5 font-mono text-xs text-ink-900">{{ b.filename }}</td>
                  <td class="px-4 py-2.5 text-xs font-mono text-ink-700">{{ formatTime(b.created_at) }}</td>
                  <td class="px-4 py-2.5 text-xs text-ink-700">{{ b.type || b.backup_type }}</td>
                  <td class="px-4 py-2.5 text-xs font-mono text-ink-700 text-right">{{ formatSize(b.size) }}</td>
                  <td class="px-4 py-2.5 text-xs font-mono text-ink-500">{{ shortHash(b.content_hash) }}</td>
                  <td class="px-4 py-2.5 text-center">
                    <span
                      v-if="b.locked"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-warn/10 text-warn"
                      :title="t('backup.title_locked')"
                    >
                      <svg class="size-2.5" viewBox="0 0 24 24" fill="currentColor"><path d="M6 10V8a6 6 0 1112 0v2h1a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2v-8a2 2 0 012-2h1zm2 0h8V8a4 4 0 10-8 0v2z"/></svg>
                      {{ t('backup.status_locked') }}
                    </span>
                    <span v-else class="text-[10px] text-ink-400">{{ t('backup.status_unlocked_chip') }}</span>
                  </td>
                  <td class="px-4 py-2.5 text-right">
                    <div class="inline-flex items-center gap-1.5">
                      <button
                        class="text-xs text-accent hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                        :disabled="busyId !== null"
                        @click="handleDownload(b)"
                      >{{ t('backup.btn_download') }}</button>
                      <span class="text-canvas-300">|</span>
                      <button
                        class="text-xs hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                        :class="b.locked ? 'text-warn' : 'text-ink-700'"
                        :disabled="busyId !== null"
                        @click="askToggleLock(b)"
                      >{{ b.locked ? t('backup.btn_unlock') : t('backup.btn_lock') }}</button>
                      <span class="text-canvas-300">|</span>
                      <button
                        class="text-xs hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                        :class="b.locked ? 'text-canvas-300 cursor-not-allowed' : 'text-bad'"
                        :disabled="busyId !== null || b.locked"
                        :title="b.locked ? t('backup.title_locked_no_delete') : t('backup.title_delete')"
                        @click="askDelete(b)"
                      >{{ t('backup.btn_delete') }}</button>
                      <span class="text-canvas-300">|</span>
                      <button
                        class="text-xs text-bad hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                        :disabled="busyId !== null"
                        @click="askRestore(b)"
                      >{{ t('backup.btn_restore') }}</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="px-5 py-2.5 border-t border-canvas-300 text-[11px] text-ink-500 flex items-center justify-between">
            <span>{{ t('backup.count_per_device', { n: backups.length }) }}</span>
            <span class="font-mono">设备 {{ deviceName || deviceId }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 二次确认 Modal -->
  <ConfirmModal
    :open="confirm.open"
    :title="confirm.title"
    :message="confirm.message"
    :confirm-text="confirm.confirmText"
    :variant="confirm.variant"
    :busy="confirm.busy"
    @update:open="(v) => v || closeConfirm()"
    @confirm="onConfirmAction"
    @cancel="closeConfirm"
  />
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
