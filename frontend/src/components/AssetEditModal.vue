<script setup>
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Select from './Select.vue'
import { assetApi } from '../api/index.js'

const { t } = useI18n()

const props = defineProps({
  open: { type: Boolean, default: false },
  deviceId: { type: Number, default: null },
  deviceName: { type: String, default: '' },
  asset: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:open', 'updated'])

// v2.6: 状态选项走 i18n
const STATUS_OPTIONS = computed(() => [
  { value: 'online',          label: t('form.asset.status_options.online') },
  { value: 'offline',         label: t('form.asset.status_options.offline') },
  { value: 'maintenance',     label: t('form.asset.status_options.maintenance') },
  { value: 'decommissioned',  label: t('form.asset.status_options.decommissioned') },
  { value: 'unknown',         label: t('form.asset.status_options.unknown') },
])

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
    error.value = t('form.asset.missing_id')
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
    error.value = r.error || t('form.asset.save_failed')
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
            <h3 class="text-base font-semibold text-ink-900">{{ t('form.asset.edit_title', { name: deviceName }) }}</h3>
            <button class="text-ink-500 hover:text-ink-900" :disabled="busy" @click="close">✕</button>
          </div>
          <div class="px-5 py-4 space-y-3">
            <div v-if="error" class="px-3 py-2 rounded-lg border border-bad/30 bg-bad/5 text-xs text-bad">{{ error }}</div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">{{ t('form.asset.location_label') }}</label>
              <input v-model="form.location" :disabled="busy" class="input" :placeholder="t('form.asset.location_ph')" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">{{ t('form.asset.tags_label') }}</label>
              <input v-model="form.tags" :disabled="busy" class="input font-mono" :placeholder="t('form.asset.tags_ph')" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">{{ t('form.asset.status_label') }}</label>
              <Select
                v-model="form.status"
                :options="STATUS_OPTIONS"
                :custom-label="(o) => o.label"
                width="w-full"
              />
              <div class="text-[10px] text-ink-500 mt-1">{{ t('form.asset.hardware_note') }}</div>
            </div>
          </div>
          <div class="px-5 py-3 border-t border-canvas-300 flex justify-end gap-2">
            <button class="btn-soft !text-xs" :disabled="busy" @click="close">{{ t('form.asset.cancel') }}</button>
            <button class="btn-primary !text-xs" :disabled="busy" @click="save">
              <svg v-if="busy" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <span>{{ busy ? t('form.asset.saving') : t('form.asset.save') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
