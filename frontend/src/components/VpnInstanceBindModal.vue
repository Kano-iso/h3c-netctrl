<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { vpnApi } from '../api/index.js'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  deviceId: { type: Number, required: true },
  mode: { type: String, default: 'bind' },  // 'create' | 'bind'
  targetIface: { type: Object, default: null },
  existingVpns: { type: Array, default: () => [] },
})

const emit = defineEmits(['confirm', 'cancel'])

// 'create' 模式的折叠区：默认收起，提示用户优先选已有
const showCreateForm = ref(false)
const newVpnName = ref('')
const newVpnRd = ref('auto')

const selectedVpnName = ref('')
const submitting = ref(false)
const errMsg = ref('')

const filteredVpns = computed(() => props.existingVpns || [])
const canCreate = computed(() => /^[A-Za-z0-9_-]+$/.test(newVpnName.value))
const canBind = computed(() => !!selectedVpnName.value)
const isCreateMode = computed(() => props.mode === 'create')

watch(() => props.visible, (v) => {
  if (v) {
    // create 模式：列表优先，折叠区默认收起
    // bind 模式：纯列表
    showCreateForm.value = props.mode === 'create' ? filteredVpns.value.length > 0 : false
    newVpnName.value = ''
    newVpnRd.value = 'auto'
    selectedVpnName.value = ''
    errMsg.value = ''
  }
})

function close() {
  if (submitting.value) return
  emit('cancel')
}

async function handleCreateAndBind() {
  if (!canCreate.value) {
    errMsg.value = t('form.vpn.name_invalid')
    return
  }
  submitting.value = true
  errMsg.value = ''
  const r = await vpnApi.create(props.deviceId, {
    name: newVpnName.value,
    rd: newVpnRd.value,
  })
  if (!r.success) {
    submitting.value = false
    errMsg.value = r.error || t('form.vpn.create_failed')
    return
  }
  // 创建成功，绑定到目标接口
  const r2 = await vpnApi.bindInterface(props.deviceId, props.targetIface.if_index, newVpnName.value)
  submitting.value = false
  if (!r2.success) {
    errMsg.value = t('form.vpn.bind_after_create_failed', {
      name: newVpnName.value,
      iface: props.targetIface.name,
      error: r2.error || t('form.vpn.unknown_error'),
    })
    return
  }
  emit('confirm', { action: 'create_bind', name: newVpnName.value })
}

async function handleBindOnly() {
  if (!canBind.value) {
    errMsg.value = t('form.vpn.no_selection')
    return
  }
  submitting.value = true
  errMsg.value = ''
  const r = await vpnApi.bindInterface(props.deviceId, props.targetIface.if_index, selectedVpnName.value)
  submitting.value = false
  if (!r.success) {
    errMsg.value = r.error || t('form.vpn.bind_failed')
    return
  }
  emit('confirm', { action: 'bind', name: selectedVpnName.value })
}

function toggleCreateForm() {
  showCreateForm.value = !showCreateForm.value
  errMsg.value = ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-md shadow-2xl" role="dialog">
          <div class="px-5 py-4 border-b border-canvas-300">
            <h3 class="text-base font-semibold text-ink-900">
              {{ isCreateMode ? t('form.vpn.title_create') : t('form.vpn.title_bind') }}
            </h3>
            <div class="text-xs text-ink-500 font-mono mt-0.5">
              {{ t('form.vpn.iface_label', { name: targetIface?.name, idx: targetIface?.if_index }) }}
            </div>
          </div>

          <div class="px-5 py-4 space-y-4 text-sm text-ink-700">
            <!-- 错误提示 -->
            <div v-if="errMsg" class="p-3 rounded-xl bg-bad/8 border border-bad/30 text-xs text-bad whitespace-pre-line">
              {{ errMsg }}
            </div>

            <!-- v2.2.1 fix-vpn-and-l2l3-ux-bugs: 顶部展示现有 VPN instance 列表（两种模式都显示） -->
            <div>
              <div class="text-xs font-medium text-ink-700 mb-1.5 flex items-center justify-between">
                <span>{{ t('form.vpn.existing_label', { n: filteredVpns.length }) }}</span>
                <button
                  v-if="isCreateMode"
                  type="button"
                  class="text-[10px] text-accent hover:underline"
                  @click="toggleCreateForm"
                >
                  {{ showCreateForm ? t('form.vpn.toggle_hide') : t('form.vpn.toggle_show') }}
                </button>
              </div>
              <div v-if="filteredVpns.length === 0" class="p-3 rounded-xl bg-canvas-100 text-xs text-ink-500">
                {{ t('form.vpn.empty_hint') }}
              </div>
              <div v-else class="space-y-1.5 max-h-48 overflow-y-auto border border-canvas-300 rounded-lg p-1.5">
                <label
                  v-for="vpn in filteredVpns"
                  :key="vpn.name"
                  :class="['flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition',
                           selectedVpnName === vpn.name ? 'border-accent bg-accent/5' : 'border-transparent hover:bg-canvas-100']"
                >
                  <input type="radio" :value="vpn.name" v-model="selectedVpnName" class="text-accent focus:ring-accent/40" />
                  <div class="flex-1">
                    <div class="font-mono text-ink-900 text-xs">{{ vpn.name }}</div>
                    <div class="text-[10px] text-ink-500 mt-0.5">
                      {{ t('form.vpn.rd_label', { rd: vpn.rd || t('form.vpn.rd_auto'), n: vpn.interfaces?.length || 0 }) }}
                    </div>
                  </div>
                </label>
              </div>
            </div>

            <!-- 模式 1：创建 + 绑定（仅 create 模式，且折叠区展开时） -->
            <template v-if="isCreateMode && showCreateForm">
              <div class="border-t border-canvas-300 pt-3">
                <div class="text-xs font-medium text-ink-700 mb-1.5">{{ t('form.vpn.new_label') }}</div>
                <div class="space-y-3">
                  <div>
                    <label class="text-[10px] font-medium text-ink-700 mb-1 block">{{ t('form.vpn.name_label') }}</label>
                    <input v-model="newVpnName" :placeholder="t('form.vpn.name_ph')" class="input" :disabled="submitting" />
                    <div class="text-[10px] text-ink-500 mt-1">{{ t('form.vpn.name_hint') }}</div>
                  </div>
                  <div>
                    <label class="text-[10px] font-medium text-ink-700 mb-1 block">{{ t('form.vpn.rd_field_label') }}</label>
                    <input v-model="newVpnRd" :placeholder="t('form.vpn.rd_auto')" class="input font-mono" :disabled="submitting" />
                    <div class="text-[10px] text-ink-500 mt-1">{{ t('form.vpn.rd_hint') }}</div>
                  </div>
                  <div class="p-2.5 rounded-xl bg-canvas-100 text-[10px] text-ink-700">
                    {{ t('form.vpn.auto_bind_hint', { iface: targetIface?.name }) }}
                  </div>
                </div>
              </div>
            </template>
          </div>

          <div class="px-5 py-3 border-t border-canvas-300 flex justify-end gap-2">
            <button class="btn-soft !text-xs" :disabled="submitting" @click="close">{{ t('form.vpn.cancel') }}</button>
            <!-- create 模式：分两种提交 -->
            <template v-if="isCreateMode">
              <!-- 列表里有选中：优先"绑定已有" -->
              <button
                v-if="canBind && !showCreateForm"
                :disabled="submitting"
                class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                @click="handleBindOnly"
              >
                {{ submitting ? t('form.vpn.submitting') : t('form.vpn.bind_to', { name: selectedVpnName }) }}
              </button>
              <!-- 创建区展开：用 create + bind -->
              <button
                v-else-if="showCreateForm"
                :disabled="!canCreate || submitting"
                class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                @click="handleCreateAndBind"
              >
                {{ submitting ? t('form.vpn.submitting') : t('form.vpn.submit_create_bind') }}
              </button>
              <!-- create 模式但既没选也没展开：展开创建区 -->
              <button
                v-else
                :disabled="submitting"
                class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                @click="toggleCreateForm"
              >
                {{ t('form.vpn.submit_create_only') }}
              </button>
            </template>
            <!-- bind 模式：纯绑 -->
            <button
              v-else
              :disabled="!canBind || submitting"
              class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              @click="handleBindOnly"
            >
              {{ submitting ? t('form.vpn.submitting') : t('form.vpn.submit_bind') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
