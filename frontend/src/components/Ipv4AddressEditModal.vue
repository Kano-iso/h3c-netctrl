<script setup>
import { ref, computed, watch } from 'vue'
import ConfirmModal from './ConfirmModal.vue'
import { interfaceApi } from '../api/index.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  deviceId: { type: Number, required: true },
  iface: { type: Object, required: true },  // 接口完整对象（含 ip_addresses / protected / layer）
})

const emit = defineEmits(['confirm', 'cancel'])

const newIp = ref('')
const newMask = ref('255.255.255.0')
const submitting = ref(false)
const errMsg = ref('')
const showSetConfirm = ref(false)     // 替换 IP 前二次确认
const showClearConfirm = ref(false)   // 清空 IP 前二次确认

const currentIps = computed(() => props.iface?.ip_addresses || [])
const isProtected = computed(() => !!props.iface?.protected)
const hasCurrentIp = computed(() => currentIps.value.length > 0)

// 校验：IPv4 格式（前端 quick check，后端再校验）
const ipValid = computed(() => /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(newIp.value))
const maskValid = computed(() => /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(newMask.value))
const canApply = computed(() => ipValid.value && maskValid.value && !isProtected.value)

watch(() => props.visible, (v) => {
  if (v) {
    newIp.value = ''
    newMask.value = '255.255.255.0'
    errMsg.value = ''
    showSetConfirm.value = false
    showClearConfirm.value = false
  }
})

function close() {
  if (submitting.value) return
  emit('cancel')
}

// 1) 用户点"应用" → 先弹 ConfirmModal 二次确认 → 真正调 API
function requestApply() {
  if (!canApply.value) {
    if (isProtected.value) {
      errMsg.value = '该接口是受保护口，禁止配置 IP'
    } else if (!ipValid.value) {
      errMsg.value = 'IP 格式不合法（如 192.168.1.1）'
    } else if (!maskValid.value) {
      errMsg.value = 'mask 格式不合法（如 255.255.255.0）'
    }
    return
  }
  errMsg.value = ''
  showSetConfirm.value = true
}

async function confirmApply() {
  showSetConfirm.value = false
  submitting.value = true
  errMsg.value = ''
  const r = await interfaceApi.setIpv4Address(
    props.deviceId, props.iface.if_index, newIp.value, newMask.value
  )
  submitting.value = false
  if (!r.success) {
    errMsg.value = r.error || '配 IP 失败'
    return
  }
  emit('confirm', { action: 'set', ip: newIp.value, mask: newMask.value })
}

function cancelApplyConfirm() {
  showSetConfirm.value = false
}

// 2) 用户点"清空所有 IP" → 二次确认 → 真正调 API
function requestClear() {
  if (isProtected.value) {
    errMsg.value = '该接口是受保护口，禁止清空 IP'
    return
  }
  if (!hasCurrentIp.value) {
    errMsg.value = '该接口当前没有 IP'
    return
  }
  errMsg.value = ''
  showClearConfirm.value = true
}

async function confirmClear() {
  showClearConfirm.value = false
  submitting.value = true
  errMsg.value = ''
  const r = await interfaceApi.clearIpv4Address(props.deviceId, props.iface.if_index)
  submitting.value = false
  if (!r.success) {
    errMsg.value = r.error || '清空 IP 失败'
    return
  }
  emit('confirm', { action: 'clear' })
}

function cancelClearConfirm() {
  showClearConfirm.value = false
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-ink-950/40 backdrop-blur-sm" @click="close"></div>
        <div class="relative panel w-full max-w-md shadow-2xl" role="dialog">
          <div class="px-5 py-4 border-b border-canvas-300">
            <h3 class="text-base font-semibold text-ink-900">配置 IPv4 地址</h3>
            <div class="text-xs text-ink-500 font-mono mt-0.5">
              接口 {{ iface?.name }} · if_index {{ iface?.if_index }} · L3
            </div>
          </div>

          <div class="px-5 py-4 space-y-4 text-sm text-ink-700">
            <!-- 受保护提示 -->
            <div v-if="isProtected" class="p-3 rounded-xl bg-bad/8 border border-bad/30 flex gap-2.5">
              <span class="text-bad text-base">🛡</span>
              <div class="text-xs text-bad flex-1">
                <div class="font-semibold">该接口已被标记为受保护</div>
                <div class="text-bad/80 mt-0.5">保护口通常是上行/管理口，误改可能导致设备失联，禁止配置 IP。</div>
              </div>
            </div>

            <!-- 错误提示 -->
            <div v-if="errMsg" class="p-3 rounded-xl bg-bad/8 border border-bad/30 text-xs text-bad whitespace-pre-line">
              {{ errMsg }}
            </div>

            <!-- 当前 IP 列表 -->
            <div>
              <div class="text-xs font-medium text-ink-700 mb-1.5">当前 IP（{{ currentIps.length }}）</div>
              <div v-if="currentIps.length === 0" class="p-3 rounded-xl bg-canvas-100 text-xs text-ink-500">
                该接口尚未配置 IP
              </div>
              <div v-else class="space-y-1.5">
                <div
                  v-for="(ip, idx) in currentIps"
                  :key="idx"
                  class="p-2 rounded-lg border border-canvas-300 bg-canvas-50 font-mono text-xs text-ink-900"
                >
                  {{ ip }}
                </div>
              </div>
            </div>

            <!-- 替换/新增 IP -->
            <div>
              <div class="text-xs font-medium text-ink-700 mb-1.5">
                {{ hasCurrentIp ? '替换为新 IP' : '配置新 IP' }}
              </div>
              <div class="grid grid-cols-[1fr_1fr] gap-2">
                <div>
                  <label class="text-[10px] font-medium text-ink-500 mb-1 block">IP 地址</label>
                  <input
                    v-model="newIp"
                    placeholder="192.168.1.1"
                    class="input font-mono"
                    :disabled="submitting || isProtected"
                  />
                </div>
                <div>
                  <label class="text-[10px] font-medium text-ink-500 mb-1 block">子网掩码</label>
                  <input
                    v-model="newMask"
                    placeholder="255.255.255.0"
                    class="input font-mono"
                    :disabled="submitting || isProtected"
                  />
                </div>
              </div>
              <div class="text-[10px] text-ink-500 mt-1.5">
                {{ hasCurrentIp ? '⚠️ 应用后该接口的现有 IP 将被替换' : '应用后该接口将拥有此 IP' }}
              </div>
            </div>
          </div>

          <div class="px-5 py-3 border-t border-canvas-300 flex justify-between gap-2">
            <button
              v-if="hasCurrentIp"
              class="btn-soft !text-xs !text-bad hover:!bg-bad/10"
              :disabled="submitting || isProtected"
              @click="requestClear"
            >
              清空所有 IP
            </button>
            <div v-else></div>
            <div class="flex gap-2">
              <button class="btn-soft !text-xs" :disabled="submitting" @click="close">取消</button>
              <button
                class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="!canApply || submitting"
                @click="requestApply"
              >
                {{ submitting ? '下发中…' : '应用' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 应用 IP 二次确认 -->
  <ConfirmModal
    :open="showSetConfirm"
    title="配置 IPv4 地址"
    :message="hasCurrentIp
      ? `确认要替换接口 ${iface?.name}（if_index ${iface?.if_index}）的 IP 吗？\n\n当前 IP：${currentIps.join(', ')}\n新 IP：${newIp} / ${newMask}\n\n操作不可撤销。`
      : `确认要给接口 ${iface?.name}（if_index ${iface?.if_index}）配置 IP ${newIp} / ${newMask} 吗？`"
    confirm-text="确认配置"
    variant="default"
    @confirm="confirmApply"
    @cancel="cancelApplyConfirm"
  />

  <!-- 清空 IP 二次确认 -->
  <ConfirmModal
    :open="showClearConfirm"
    title="清空 IP 地址"
    :message="`确认要清空接口 ${iface?.name}（if_index ${iface?.if_index}）的所有 IPv4 地址吗？\n\n当前 IP：${currentIps.join(', ')}\n\n清空后该接口将无 IP，依赖 IP 的路由/VPN 可能受影响。\n\n操作不可撤销。`"
    confirm-text="确认清空"
    variant="danger"
    @confirm="confirmClear"
    @cancel="cancelClearConfirm"
  />
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
