<script setup>
// 全局 toast 容器（v2.6.2 fix-backup-restore-support Task 4）
// 右上角浮动，4 种类型：success / error / warning / info
// 自动消失（5s，error 8s），可手动关闭
import { useToastStore } from '../stores/toast.js'

const toastStore = useToastStore()

// 类型 → 颜色 / 图标
const TYPE_META = {
  success: { bg: 'bg-good/10 ring-good/30',   text: 'text-good',  icon: 'check' },
  error:   { bg: 'bg-bad/10  ring-bad/30',    text: 'text-bad',   icon: 'cross' },
  warning: { bg: 'bg-warn/10 ring-warn/30',   text: 'text-warn',  icon: 'warn' },
  info:    { bg: 'bg-accent/10 ring-accent/30', text: 'text-accent', icon: 'info' },
}

// SVG path
const ICONS = {
  check: 'M5 13l4 4L19 7',
  cross: 'M6 6l12 12M18 6L6 18',
  warn:  'M12 9v4m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4a2 2 0 00-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z',
  info:  'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-50 print:hidden flex flex-col gap-2 max-w-[400px]">
      <TransitionGroup name="toast">
        <div
          v-for="t in toastStore.toasts"
          :key="t.id"
          :class="['toast-item flex items-start gap-2.5 px-3.5 py-2.5 rounded-xl shadow-elevated ring-1 backdrop-blur-sm',
                   TYPE_META[t.type].bg, TYPE_META[t.type].text]"
        >
          <svg class="size-4 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path :d="ICONS[TYPE_META[t.type].icon]" />
          </svg>
          <div class="flex-1 min-w-0 text-[12px] leading-[1.5] break-words">
            {{ t.message }}
          </div>
          <button
            class="size-5 -m-1 rounded-full hover:bg-canvas-200/60 flex items-center justify-center text-ink-500 hover:text-ink-900 transition shrink-0"
            @click="toastStore.remove(t.id)"
            :aria-label="'close'"
          >
            <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-item {
  /* 默认背景色（避免某些 type 没匹配时透明） */
  background-color: var(--canvas, #fff);
}

.toast-enter-active, .toast-leave-active {
  transition: opacity .2s ease, transform .2s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
