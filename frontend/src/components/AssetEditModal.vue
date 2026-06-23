<script setup>
import { ref, watch } from 'vue'
import Select from './Select.vue'
import { assetApi } from '../api/index.js'
import { getStatusLabel } from '../utils/status.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  deviceId: { type: Number, default: null },
  deviceName: { type: String, default: '' },
  asset: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:open', 'updated'])

const STATUS_OPTIONS = [
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
  { value: 'maintenance', label: '维护中' },
  { value: 'decommissioned', label: '已下线' },
  { value: 'unknown', label: '未采集' },
]

const form = ref({ location: '', tags: '', status: 'unknown' })
const error = ref('')
const busy = ref(false)

watch(() => [props.open, props.asset], ([open, a]) => {
  if (!open) return
  error.value = ''
  form.value = {
    location: a?.location || '',
    tags: a?.tags || '',
    status: a?.status || 'unknown',
  }
}, { immediate: true })

const close = () => { if (!busy.value) emit('update:open', false) }

const save = async () => {
  if (!props.deviceId) {
    error.value = '缺少 deviceId'
    return
  }
  busy.value = true
  error.value = ''
  const payload = {
    location: form.value.location,
    tags: form.value.tags,
    status: form.value.status,
  }
  const r = await assetApi.update(props.deviceId, payload)
  busy.value = false
  if (r.success) {
    emit('updated', { ...form.value })
    emit('update:open', false)
  } else {
    error.value = r.error || '保存失败'
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="close">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-md shadow-2xl" role="dialog">
          <div class="px-5 py-4 border-b border-canvas-300 flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink-900">编辑资产 · {{ deviceName }}</h3>
            <button class="text-ink-500 hover:text-ink-900" :disabled="busy" @click="close">✕</button>
          </div>
          <div class="px-5 py-4 space-y-3">
            <div v-if="error" class="px-3 py-2 rounded-lg border border-bad/30 bg-bad/5 text-xs text-bad">{{ error }}</div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">位置</label>
              <input v-model="form.location" :disabled="busy" class="input" placeholder="如 上海 IDC 3-A" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">标签（多个用逗号分隔）</label>
              <input v-model="form.tags" :disabled="busy" class="input font-mono" placeholder="如 核心,生产,核心交换机" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">状态</label>
              <Select
                v-model="form.status"
                :options="STATUS_OPTIONS"
                :custom-label="(o) => o.label"
                width="w-full"
              />
              <div class="text-[10px] text-ink-500 mt-1">硬件字段（型号 / 固件）由"全量刷新"SSH 采集覆盖，本 Modal 仅管理位置 / 标签 / 状态</div>
            </div>
          </div>
          <div class="px-5 py-3 border-t border-canvas-300 flex justify-end gap-2">
            <button class="btn-soft !text-xs" :disabled="busy" @click="close">取消</button>
            <button class="btn-primary !text-xs" :disabled="busy" @click="save">
              <svg v-if="busy" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <span>{{ busy ? '保存中…' : '保存' }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
