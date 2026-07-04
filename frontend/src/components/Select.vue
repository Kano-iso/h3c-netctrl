<script setup>
// 自定义下拉组件 —— 绕开原生 <option> 字体不可控的问题
// 用法：
//   <Select v-model="selected" :options="devices" label-key="name" value-key="id" placeholder="选择设备" />
//   <Select v-model="..." :options="..." :custom-label="(d) => `${d.name} · ${d.host}`" />

import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, null], default: null },
  options: { type: Array, required: true },
  valueKey: { type: String, default: 'id' },
  labelKey: { type: String, default: 'name' },
  // 自定义 label 渲染：传入 (option) => string 返回要显示的文本
  customLabel: { type: Function, default: null },
  // 自定义 sub：传入 (option) => string 返回副标题
  subLabel: { type: Function, default: null },
  // 状态 chip：传入 (option) => string 返回 chip class
  statusClass: { type: Function, default: null },
  // 状态文本：传入 (option) => string 返回状态文字
  statusText: { type: Function, default: null },
  placeholder: { type: String, default: '请选择…' },
  disabled: { type: Boolean, default: false },
  width: { type: String, default: 'w-56' },  // 触发器宽度
  align: { type: String, default: 'left' },  // 下拉弹出方向：left | right
})

const emit = defineEmits(['update:modelValue', 'change'])

const open = ref(false)
const triggerRef = ref(null)
const menuRef = ref(null)

const getValue = (opt) => (props.valueKey ? opt[props.valueKey] : opt)
const getLabel = (opt) => {
  if (props.customLabel) return props.customLabel(opt)
  return opt[props.labelKey]
}
const getSub = (opt) => props.subLabel ? props.subLabel(opt) : ''

const selected = computed(() =>
  props.options.find(opt => getValue(opt) === props.modelValue) || null
)

const choose = (opt) => {
  emit('update:modelValue', getValue(opt))
  emit('change', opt)
  open.value = false
}

const toggle = () => {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) nextTick()
}

const close = () => { open.value = false }

const onDocClick = (e) => {
  if (!open.value) return
  if (triggerRef.value && !triggerRef.value.contains(e.target) &&
      menuRef.value && !menuRef.value.contains(e.target)) {
    close()
  }
}

onMounted(() => { document.addEventListener('mousedown', onDocClick) })
onBeforeUnmount(() => { document.removeEventListener('mousedown', onDocClick) })
</script>

<template>
  <div class="relative" :class="width">
    <!-- 触发器 -->
    <button
      ref="triggerRef"
      type="button"
      :disabled="disabled"
      @click="toggle"
      class="w-full h-9 pl-3 pr-2 text-sm text-left rounded-xl bg-white ring-1 ring-canvas-400
             text-ink-900 transition flex items-center gap-2
             hover:ring-ink-400 focus:outline-none focus:ring-2 focus:ring-accent/40
             disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <span v-if="selected" class="flex-1 min-w-0 flex items-center gap-2">
        <span class="truncate min-w-0">{{ getLabel(selected) }}</span>
        <span v-if="getSub(selected)" class="text-ink-500 text-[10px] num-mono truncate max-w-[8rem] shrink">{{ getSub(selected) }}</span>
        <span v-if="statusText" :class="['chip text-[9px] !px-1.5 !py-0 shrink-0 ml-auto', statusClass(selected)]">
          {{ statusText(selected) }}
        </span>
      </span>
      <span v-else class="flex-1 text-ink-500 truncate">{{ placeholder }}</span>
      <span class="h-5 w-px bg-canvas-300 shrink-0"></span>
      <svg class="size-3.5 text-ink-500 shrink-0 transition-transform" :class="{ 'rotate-180': open }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <!-- 下拉菜单 -->
    <transition name="dropdown">
      <div
        v-if="open"
        ref="menuRef"
        class="absolute z-50 mt-1.5 max-h-80 overflow-y-auto rounded-xl bg-white shadow-lg ring-1 ring-canvas-400
               focus:outline-none"
        :class="align === 'right' ? 'right-0' : 'left-0'"
        style="min-width: 100%;"
      >
        <div v-if="options.length === 0" class="px-4 py-3 text-xs text-ink-500 text-center">无选项</div>
        <button
          v-for="opt in options"
          :key="getValue(opt)"
          type="button"
          @click="choose(opt)"
          class="w-full text-left pl-3 pr-2 py-2 text-sm flex items-center gap-2 transition
                 hover:bg-canvas-100"
          :class="modelValue === getValue(opt) ? 'bg-accent/5 text-accent' : 'text-ink-900'"
        >
          <span class="flex-1 min-w-0 flex items-center gap-2">
            <span class="truncate min-w-0">{{ getLabel(opt) }}</span>
            <span v-if="getSub(opt)" class="text-ink-500 text-[10px] num-mono truncate max-w-[8rem] shrink">{{ getSub(opt) }}</span>
          </span>
          <span v-if="statusText" :class="['chip text-[9px] !px-1.5 !py-0 shrink-0', statusClass(opt)]">
            {{ statusText(opt) }}
          </span>
          <svg v-if="modelValue === getValue(opt)" class="size-3.5 text-accent shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M5 12l5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </transition>
  </div>
</template>
