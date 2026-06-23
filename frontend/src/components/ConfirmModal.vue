<script setup>
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '确认' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  variant: { type: String, default: 'default' }, // 'default' | 'danger'
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['update:open', 'confirm', 'cancel'])

const close = () => { if (!props.busy) emit('update:open', false) }
const onCancel = () => { if (!props.busy) { emit('cancel'); emit('update:open', false) } }
const onConfirm = () => { if (!props.busy) emit('confirm') }
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="close">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-md shadow-2xl" role="dialog">
          <div class="px-5 py-4 border-b border-canvas-300">
            <h3 class="text-base font-semibold text-ink-900">{{ title }}</h3>
          </div>
          <div class="px-5 py-4 text-sm text-ink-700 whitespace-pre-line">{{ message }}</div>
          <div class="px-5 py-3 border-t border-canvas-300 flex justify-end gap-2">
            <button class="btn-soft !text-xs" :disabled="busy" @click="onCancel">{{ cancelText }}</button>
            <button
              :class="[variant === 'danger' ? 'bg-bad hover:bg-bad/90 text-white' : 'btn-primary', 'inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium transition']"
              :disabled="busy"
              @click="onConfirm"
            >
              <svg v-if="busy" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <span>{{ confirmText }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
