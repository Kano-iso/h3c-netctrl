<script setup>
// 后台任务面板（v24-feat-async-backup-status）
// 右下角浮动卡片，显示运行中任务 + 最近历史，支持取消/清除
import { ref, computed, onMounted } from 'vue'
import { useTaskStore } from '../stores/task.js'

const taskStore = useTaskStore()

const expanded = ref(false)

const recent = computed(() => taskStore.recentTasks)
const hasRunning = computed(() => taskStore.hasRunning)
const runningCount = computed(() => taskStore.runningCount)

// 任务状态 → 显示样式
function statusMeta(status) {
  switch (status) {
    case 'pending':   return { label: '排队',   color: 'text-ink-500',   bg: 'bg-canvas-200',   spin: false }
    case 'running':   return { label: '执行中', color: 'text-accent',    bg: 'bg-accent/10',    spin: true  }
    case 'success':   return { label: '成功',   color: 'text-good',      bg: 'bg-good/10',      spin: false }
    case 'failed':    return { label: '失败',   color: 'text-bad',       bg: 'bg-bad/10',       spin: false }
    case 'cancelled': return { label: '已取消', color: 'text-ink-500',  bg: 'bg-canvas-200',   spin: false }
    default:          return { label: status,   color: 'text-ink-500',   bg: 'bg-canvas-200',   spin: false }
  }
}

function typeLabel(t) {
  return t === 'backup' ? '备份' : t === 'restore' ? '回滚' : t
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
      <!-- 折叠态：仅当无 running 且未展开时不显示；有 running 时显示小圆点 -->
      <Transition name="panel-fade">
        <div v-if="hasRunning || expanded" class="panel w-[360px] shadow-elevated overflow-hidden">
          <!-- 头部 -->
          <div
            class="px-4 py-2.5 flex items-center justify-between cursor-pointer select-none border-b border-canvas-300/70"
            @click="expanded = !expanded"
          >
            <div class="flex items-center gap-2">
              <svg v-if="hasRunning" class="size-3.5 animate-spin text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M21 12a9 9 0 11-6.219-8.56" stroke-linecap="round"/>
              </svg>
              <span class="text-[13px] font-medium text-ink-900">后台任务</span>
              <span v-if="hasRunning" class="chip bg-accent/10 text-accent !text-[10px] !px-1.5 !py-0">
                {{ runningCount }} 个执行中
              </span>
              <span v-else class="text-[11px] text-ink-500">无运行中</span>
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
                暂无任务记录
              </div>
              <div
                v-for="t in recent"
                :key="t.task_id"
                class="px-4 py-2.5 hover:bg-canvas-50/60 transition"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-2 min-w-0">
                    <span :class="['chip !text-[10px] !px-1.5 !py-0', statusMeta(t.status).bg, statusMeta(t.status).color]">
                      <svg v-if="statusMeta(t.status).spin" class="size-2.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21 12a9 9 0 11-6.219-8.56" stroke-linecap="round"/></svg>
                      {{ statusMeta(t.status).label }}
                    </span>
                    <span class="text-[11px] text-ink-500 font-mono">{{ typeLabel(t.task_type) }}</span>
                    <span class="text-[12px] text-ink-900 truncate">{{ t._label || `#${t.task_id}` }}</span>
                  </div>
                  <div class="flex items-center gap-1 shrink-0">
                    <span class="text-[10px] text-ink-400 font-mono">{{ formatTime(t.updated_at) }}</span>
                    <button
                      v-if="['success','failed','cancelled'].includes(t.status)"
                      class="size-5 rounded-full hover:bg-canvas-200 flex items-center justify-center text-ink-400 hover:text-ink-700 transition"
                      @click="onRemove(t.task_id)"
                      title="移除记录"
                    >
                      <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 6l12 12M18 6L6 18" stroke-linecap="round"/></svg>
                    </button>
                  </div>
                </div>

                <!-- 进度条（running/pending） -->
                <div v-if="t.status === 'running' || t.status === 'pending'" class="mt-1.5">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1 rounded-full bg-canvas-200 overflow-hidden">
                      <div
                        class="h-full bg-accent transition-all duration-300"
                        :style="{ width: `${t.progress || 0}%` }"
                      ></div>
                    </div>
                    <span class="text-[10px] text-ink-500 font-mono w-8 text-right">{{ t.progress || 0 }}%</span>
                  </div>
                </div>

                <!-- 错误信息（failed） -->
                <div v-else-if="t.status === 'failed' && t.error" class="mt-1 text-[11px] text-bad break-all line-clamp-2">
                  {{ t.error }}
                </div>

                <!-- 成功结果摘要 -->
                <div v-else-if="t.status === 'success' && t.result" class="mt-1 text-[11px] text-ink-500">
                  <template v-if="t.task_type === 'backup' && t.result.backups">
                    新增 {{ t.result.backups.length }} 份备份
                  </template>
                  <template v-else-if="t.task_type === 'restore'">
                    {{ t.result.message || '回滚完成' }}
                  </template>
                  <template v-else>完成</template>
                </div>

                <!-- 取消按钮（running） -->
                <div v-if="t.status === 'running' || t.status === 'pending'" class="mt-1.5">
                  <button
                    class="text-[10px] text-bad hover:underline"
                    @click="onCancel(t.task_id)"
                  >取消</button>
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
