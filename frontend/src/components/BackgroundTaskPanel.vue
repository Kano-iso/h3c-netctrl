<script setup>
// 后台任务面板（v24-feat-async-backup-status）
// 右下角浮动卡片，显示运行中任务 + 最近历史，支持取消/清除
// v2.6: 全部状态/类型/按钮文案走 i18n
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '../stores/task.js'

const { t } = useI18n()
const taskStore = useTaskStore()

const expanded = ref(false)

// v2.6.2 fix-backup-restore-support Task 5: 失败任务高亮
const recent = computed(() => taskStore.recentTasks)
const hasRunning = computed(() => taskStore.hasRunning)
const runningCount = computed(() => taskStore.runningCount)
const failedCount = computed(() =>
  taskStore.recentTasks.filter(t => t.status === 'failed').length
)
const hasFailed = computed(() => failedCount.value > 0)

// 任务状态 → 显示样式
function statusMeta(status) {
  const label = t(`component.bg_task.task_status.${status}`, status)
  switch (status) {
    case 'pending':   return { label, color: 'text-ink-500',   bg: 'bg-canvas-200',   spin: false }
    case 'running':   return { label, color: 'text-accent',    bg: 'bg-accent/10',    spin: true  }
    case 'success':   return { label, color: 'text-good',      bg: 'bg-good/10',      spin: false }
    case 'failed':    return { label, color: 'text-bad',       bg: 'bg-bad/10',       spin: false }
    case 'cancelled': return { label, color: 'text-ink-500',  bg: 'bg-canvas-200',   spin: false }
    default:          return { label, color: 'text-ink-500',   bg: 'bg-canvas-200',   spin: false }
  }
}

function typeLabel(type) {
  return type === 'backup' ? t('component.bg_task.task_type_backup')
       : type === 'restore' ? t('component.bg_task.task_type_restore')
       : type
}

async function onCancel(taskId) {
  await taskStore.cancelTask(taskId)
}

function onRemove(taskId) {
  taskStore.removeTask(taskId)
}

function onClearHistory() {
  taskStore.clearHistory()
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

onMounted(() => {
  // 启动时恢复 localStorage 中的未完成任务
  taskStore.restoreFromLocalStorage()
})
</script>

<template>
  <!-- 右下角浮动面板 -->
  <Teleport to="body">
    <div class="fixed bottom-4 right-4 z-40 print:hidden">
      <!-- 折叠态：v2.6.2 Task 5: 有失败任务时即使无 running 也显示 -->
      <Transition name="panel-fade">
        <div v-if="hasRunning || expanded || hasFailed" :class="['panel w-[360px] shadow-elevated overflow-hidden', hasFailed && !hasRunning && 'ring-2 ring-bad/40']">
          <!-- 头部 -->
          <div
            class="px-4 py-2.5 flex items-center justify-between cursor-pointer select-none border-b border-canvas-300/70"
            @click="expanded = !expanded"
          >
            <div class="flex items-center gap-2">
              <svg v-if="hasRunning" class="size-3.5 animate-spin text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M21 12a9 9 0 11-6.219-8.56" stroke-linecap="round"/>
              </svg>
              <!-- v2.6.2 Task 5: 无 running 但有 failed 时显示红色警示图标 -->
              <svg v-else-if="hasFailed" class="size-3.5 text-bad" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 8v4M12 16h.01"/>
              </svg>
              <span class="text-[13px] font-medium text-ink-900">{{ t('component.bg_task.title') }}</span>
              <span v-if="hasRunning" class="chip bg-accent/10 text-accent !text-[10px] !px-1.5 !py-0">
                {{ t('component.bg_task.running_count', { n: runningCount }) }}
              </span>
              <!-- v2.6.2 Task 5: 失败计数 chip -->
              <span v-else-if="hasFailed" class="chip bg-bad/10 text-bad !text-[10px] !px-1.5 !py-0">
                {{ t('component.bg_task.failed_badge', { n: failedCount }) }}
              </span>
              <span v-else class="text-[11px] text-ink-500">{{ t('component.bg_task.none_running') }}</span>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="!hasRunning && recent.length > 0"
                class="text-[11px] text-ink-500 hover:text-ink-900 transition"
                @click.stop="onClearHistory"
              >清空历史</button>
              <svg
                :class="['size-3.5 text-ink-500 transition-transform', expanded && 'rotate-180']"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              ><path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
          </div>

          <!-- 展开态：任务列表 -->
          <Transition name="expand">
            <div v-if="expanded" class="max-h-[320px] overflow-y-auto divide-y divide-canvas-200">
              <div v-if="recent.length === 0" class="px-4 py-6 text-center text-xs text-ink-500">
                {{ t('component.bg_task.empty') }}
              </div>
              <div
                v-for="task in recent"
                :key="task.task_id"
                class="px-4 py-2.5 hover:bg-canvas-50/60 transition"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-2 min-w-0">
                    <span :class="['chip !text-[10px] !px-1.5 !py-0', statusMeta(task.status).bg, statusMeta(task.status).color]">
                      <svg v-if="statusMeta(task.status).spin" class="size-2.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21 12a9 9 0 11-6.219-8.56" stroke-linecap="round"/></svg>
                      {{ statusMeta(task.status).label }}
                    </span>
                    <span class="text-[11px] text-ink-500 font-mono">{{ typeLabel(task.task_type) }}</span>
                    <span class="text-[12px] text-ink-900 truncate">{{ task._label || `#${task.task_id}` }}</span>
                  </div>
                  <div class="flex items-center gap-1 shrink-0">
                    <span class="text-[10px] text-ink-400 font-mono">{{ formatTime(task.updated_at) }}</span>
                    <button
                      v-if="['success','failed','cancelled'].includes(task.status)"
                      class="size-5 rounded-full hover:bg-canvas-200 flex items-center justify-center text-ink-400 hover:text-ink-700 transition"
                      @click="onRemove(task.task_id)"
                      :title="t('component.bg_task.remove_title')"
                    >
                      <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round"/></svg>
                    </button>
                  </div>
                </div>

                <!-- 进度条（running/pending） -->
                <div v-if="task.status === 'running' || task.status === 'pending'" class="mt-1.5">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1 rounded-full bg-canvas-200 overflow-hidden">
                      <div
                        class="h-full bg-accent transition-all duration-300"
                        :style="{ width: `${task.progress || 0}%` }"
                      ></div>
                    </div>
                    <span class="text-[10px] text-ink-500 font-mono w-8 text-right">{{ task.progress || 0 }}%</span>
                  </div>
                </div>

                <!-- 错误信息（failed） -->
                <div v-else-if="task.status === 'failed' && task.error" class="mt-1 text-[11px] text-bad break-all line-clamp-2">
                  {{ task.error }}
                </div>

                <!-- 成功结果摘要 -->
                <div v-else-if="task.status === 'success' && task.result" class="mt-1 text-[11px] text-ink-500">
                  <template v-if="task.task_type === 'backup' && task.result.backups">
                    {{ t('component.bg_task.result_new_backups', { n: task.result.backups.length }) }}
                  </template>
                  <template v-else-if="task.task_type === 'restore'">
                    {{ task.result.message || t('component.bg_task.result_restore_done') }}
                  </template>
                  <template v-else>{{ t('component.bg_task.result_done') }}</template>
                </div>

                <!-- 取消按钮（running） -->
                <div v-if="task.status === 'running' || task.status === 'pending'" class="mt-1.5">
                  <button
                    class="text-[10px] text-bad hover:underline"
                    @click="onCancel(task.task_id)"
                  >{{ t('component.bg_task.cancel') }}</button>
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </Transition>
    </div>
  </Teleport>
</template>

<style scoped>
.panel-fade-enter-active, .panel-fade-leave-active { transition: opacity .2s, transform .2s; }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; transform: translateY(8px); }

.expand-enter-active, .expand-leave-active { transition: max-height .2s ease, opacity .15s ease; }
.expand-enter-from, .expand-leave-to { opacity: 0; }

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
