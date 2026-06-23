<script setup>
import { ref, watch, computed } from 'vue'
import { deviceApi } from '../api/index.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'create' }, // 'create' | 'edit'
  device: { type: Object, default: null }, // 编辑时传入
})

const emit = defineEmits(['update:open', 'saved'])

const form = ref({
  name: '',
  host: '',
  port: 830,
  username: '',
  password: '',
  protected_interfaces: '',
})
const error = ref('')
const busy = ref(false)

const isEdit = computed(() => props.mode === 'edit')

watch(() => [props.open, props.device], ([open, dev]) => {
  if (!open) return
  error.value = ''
  if (isEdit.value && dev) {
    form.value = {
      name: dev.name || '',
      host: dev.host || '',
      port: dev.port ?? 830,
      username: dev.username || '',
      password: '', // 编辑模式密码留空
      protected_interfaces: Array.isArray(dev.protected_interfaces) ? dev.protected_interfaces.join(',') : '',
    }
  } else {
    form.value = {
      name: '',
      host: '',
      port: 830,
      username: '',
      password: '',
      protected_interfaces: '',
    }
  }
}, { immediate: true })

const parseProtected = (s) => {
  if (!s) return []
  return s.split(',').map(x => parseInt(x.trim(), 10)).filter(Number.isInteger)
}

const validate = () => {
  if (!form.value.name.trim()) return '缺少必填字段: name'
  if (!isEdit.value) {
    if (!form.value.host.trim()) return '缺少必填字段: host'
    if (!form.value.username.trim()) return '缺少必填字段: username'
    if (!form.value.password) return '缺少必填字段: password'
  }
  return ''
}

const close = () => { if (!busy.value) emit('update:open', false) }

const save = async () => {
  const err = validate()
  if (err) { error.value = err; return }

  busy.value = true
  error.value = ''
  const protectedList = parseProtected(form.value.protected_interfaces)

  let payload, r
  if (isEdit.value) {
    payload = {
      name: form.value.name.trim(),
      host: form.value.host.trim() || undefined,
      port: form.value.port || undefined,
      username: form.value.username.trim() || undefined,
      protected_interfaces: protectedList,
    }
    if (form.value.password) payload.password = form.value.password
    r = await deviceApi.update(props.device.id, payload)
  } else {
    payload = {
      name: form.value.name.trim(),
      host: form.value.host.trim(),
      port: form.value.port || 830,
      username: form.value.username.trim(),
      password: form.value.password,
      protected_interfaces: protectedList,
    }
    r = await deviceApi.create(payload)
  }

  busy.value = false
  if (r.success) {
    emit('saved', r.data)
    emit('update:open', false)
  } else {
    error.value = r.error || '操作失败'
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="close">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-lg shadow-2xl" role="dialog">
          <div class="px-5 py-4 border-b border-canvas-300 flex items-center justify-between">
            <h3 class="text-base font-semibold text-ink-900">
              {{ isEdit ? `编辑设备：${device?.name || ''}` : '新增设备' }}
            </h3>
            <button class="text-ink-500 hover:text-ink-900" :disabled="busy" @click="close">✕</button>
          </div>
          <div class="px-5 py-4 space-y-3">
            <div v-if="error" class="px-3 py-2 rounded-lg border border-bad/30 bg-bad/5 text-xs text-bad">{{ error }}</div>

            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">设备名 <span v-if="!isEdit" class="text-bad">*</span></label>
              <input v-model="form.name" :disabled="busy" class="input" placeholder="如 Spine-01" />
            </div>
            <div class="grid grid-cols-3 gap-3">
              <div class="col-span-2">
                <label class="text-xs text-ink-700 font-medium block mb-1">IP <span v-if="!isEdit" class="text-bad">*</span></label>
                <input v-model="form.host" :disabled="busy" class="input font-mono" placeholder="192.168.100.100" />
              </div>
              <div>
                <label class="text-xs text-ink-700 font-medium block mb-1">NETCONF 端口</label>
                <input v-model.number="form.port" :disabled="busy" type="number" class="input font-mono" />
              </div>
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">用户名 <span v-if="!isEdit" class="text-bad">*</span></label>
              <input v-model="form.username" :disabled="busy" class="input" placeholder="admin" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">
                密码 <span v-if="!isEdit" class="text-bad">*</span>
                <span v-if="isEdit" class="text-[10px] text-ink-500 ml-1">（留空表示不修改）</span>
              </label>
              <input v-model="form.password" :disabled="busy" type="password" class="input font-mono" :placeholder="isEdit ? '留空表示不修改' : '设备登录密码'" />
            </div>
            <div>
              <label class="text-xs text-ink-700 font-medium block mb-1">保护口（if_index）</label>
              <input v-model="form.protected_interfaces" :disabled="busy" class="input font-mono" placeholder="逗号分隔，如 1,5,22" />
              <div class="text-[10px] text-ink-500 mt-1">填入的接口在配置下发时会被拦截保护，需 force=true 强制通过</div>
            </div>
          </div>
          <div class="px-5 py-3 border-t border-canvas-300 flex justify-end gap-2">
            <button class="btn-soft !text-xs" :disabled="busy" @click="close">取消</button>
            <button class="btn-primary !text-xs" :disabled="busy" @click="save">
              <svg v-if="busy" class="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
              <span>{{ busy ? (isEdit ? '保存中…' : '创建中…') : (isEdit ? '保存' : '新增') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
