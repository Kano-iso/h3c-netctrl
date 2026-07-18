<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'
import { ztpApi } from '../api/index.js'

const { t } = useI18n()

const loading = ref(true)
const saving = ref(false)
const clearing = ref(false)
const error = ref('')
const message = ref('')
const status = ref({ active: false, override: null })

const form = ref({
  host: '192.168.100.2',
  name: '',
  platform: 'lstn',
  hcl_t7064p15: false,
  username: 'python',
  password: 'Admin123!@#',
})

const activeOverride = computed(() => status.value?.override || null)

function loadOverrideToForm(data) {
  if (!data) return
  form.value.host = data.host || data.mgmt_ip || form.value.host
  form.value.name = data.sysname || ''
  form.value.platform = data.platform || 'lstn'
  form.value.hcl_t7064p15 = !!data.hcl_t7064p15
  form.value.username = data.username || 'python'
  form.value.password = data.password || 'Admin123!@#'
}

async function loadStatus() {
  loading.value = true
  error.value = ''
  const r = await ztpApi.getRecoveryOverride()
  loading.value = false
  if (!r.success) {
    error.value = r.error || t('ztp.load_failed')
    return
  }
  status.value = r.data || { active: false, override: null }
  loadOverrideToForm(status.value.override)
}

function payload() {
  return {
    host: String(form.value.host || '').trim(),
    name: String(form.value.name || '').trim() || null,
    platform: form.value.platform,
    hcl_t7064p15: !!form.value.hcl_t7064p15,
    username: String(form.value.username || '').trim(),
    password: form.value.password,
    netconf_port: 830,
    collect_asset: false,
  }
}

async function saveOverride() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  const r = await ztpApi.setRecoveryOverride(payload())
  saving.value = false
  if (!r.success) {
    error.value = r.error || t('ztp.save_failed')
    return
  }
  status.value = r.data || { active: true, override: null }
  message.value = t('ztp.save_success')
}

async function clearOverride() {
  if (clearing.value) return
  clearing.value = true
  error.value = ''
  message.value = ''
  const r = await ztpApi.clearRecoveryOverride()
  clearing.value = false
  if (!r.success) {
    error.value = r.error || t('ztp.clear_failed')
    return
  }
  status.value = r.data || { active: false, override: null }
  message.value = t('ztp.clear_success')
}

onMounted(loadStatus)
</script>

<template>
  <div v-if="loading" class="max-w-[1200px] mx-auto px-8 py-16 text-center text-ink-500">{{ t('common.loading') }}</div>
  <template v-else>
    <PageHeader :title="t('ztp.title')" :subtitle="t('ztp.subtitle')">
      <template #actions>
        <button class="btn-outline" @click="loadStatus">{{ t('ztp.refresh') }}</button>
      </template>
    </PageHeader>

    <div class="max-w-[1200px] mx-auto px-8 pb-16">
      <div v-if="error" class="mb-4 rounded-xl border border-bad/30 bg-bad/5 px-4 py-3 text-sm text-bad">{{ error }}</div>
      <div v-if="message" class="mb-4 rounded-xl border border-good/30 bg-good/5 px-4 py-3 text-sm text-good">{{ message }}</div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <section class="panel p-5 lg:col-span-2">
          <div class="flex items-center justify-between gap-3 mb-5">
            <div>
              <div class="text-base font-semibold text-ink-900">{{ t('ztp.form_title') }}</div>
              <div class="text-xs text-ink-500 mt-1">{{ t('ztp.form_meta') }}</div>
            </div>
            <span :class="['chip', status.active ? 'chip-warn' : 'chip-good']">
              {{ status.active ? t('ztp.status_active') : t('ztp.status_default') }}
            </span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label class="block">
              <span class="text-xs font-medium text-ink-600">{{ t('ztp.host') }}</span>
              <input v-model="form.host" class="input mt-1.5 font-mono" placeholder="192.168.100.2" />
            </label>
            <label class="block">
              <span class="text-xs font-medium text-ink-600">{{ t('ztp.name') }}</span>
              <input v-model="form.name" class="input mt-1.5 font-mono" placeholder="ztp-switch-2" />
            </label>

            <div class="md:col-span-2">
              <span class="text-xs font-medium text-ink-600">{{ t('ztp.platform') }}</span>
              <div class="mt-1.5 grid grid-cols-1 md:grid-cols-2 gap-2">
                <button
                  type="button"
                  :class="['text-left rounded-xl px-3 py-3 ring-1 transition', form.platform === 'lstn' ? 'bg-white shadow-sm text-ink-900 ring-accent/30' : 'bg-canvas-100 text-ink-600 ring-canvas-300 hover:bg-canvas-200']"
                  @click="form.platform = 'lstn'"
                >
                  <div class="text-sm font-semibold">{{ t('ztp.platform_lstn') }}</div>
                  <div class="text-xs text-ink-500 mt-0.5">{{ t('ztp.platform_lstn_desc') }}</div>
                </button>
                <button
                  type="button"
                  :class="['text-left rounded-xl px-3 py-3 ring-1 transition', form.platform === 'rstn' ? 'bg-white shadow-sm text-ink-900 ring-accent/30' : 'bg-canvas-100 text-ink-600 ring-canvas-300 hover:bg-canvas-200']"
                  @click="form.platform = 'rstn'"
                >
                  <div class="text-sm font-semibold">{{ t('ztp.platform_rstn') }}</div>
                  <div class="text-xs text-ink-500 mt-0.5">{{ t('ztp.platform_rstn_desc') }}</div>
                </button>
              </div>
            </div>

            <label class="block">
              <span class="text-xs font-medium text-ink-600">{{ t('ztp.username') }}</span>
              <input v-model="form.username" class="input mt-1.5 font-mono" />
            </label>
            <label class="block">
              <span class="text-xs font-medium text-ink-600">{{ t('ztp.password') }}</span>
              <input v-model="form.password" type="password" class="input mt-1.5 font-mono" />
            </label>
          </div>

          <div class="mt-5 flex flex-wrap items-center gap-4">
            <label class="inline-flex items-center gap-2 text-sm text-ink-700">
              <input v-model="form.hcl_t7064p15" type="checkbox" class="size-4 rounded border-canvas-400 text-accent focus:ring-accent/30" />
              <span>{{ t('ztp.hcl') }}</span>
            </label>
          </div>

          <div class="mt-6 flex items-center gap-2">
            <button class="btn-primary" :disabled="saving" @click="saveOverride">
              {{ saving ? t('ztp.saving') : t('ztp.apply') }}
            </button>
            <button class="btn-outline" :disabled="clearing" @click="clearOverride">
              {{ clearing ? t('ztp.clearing') : t('ztp.clear') }}
            </button>
          </div>
        </section>

        <aside class="panel p-5">
          <div class="text-base font-semibold text-ink-900">{{ t('ztp.current_title') }}</div>
          <div class="mt-4 space-y-3 text-sm">
            <div class="flex items-center justify-between gap-3">
              <span class="text-ink-500">{{ t('ztp.current_mode') }}</span>
              <span class="font-medium text-ink-900">{{ status.active ? t('ztp.mode_recovery') : t('ztp.mode_default') }}</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-ink-500">{{ t('ztp.host') }}</span>
              <span class="font-mono text-ink-900">{{ activeOverride?.host || '-' }}</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-ink-500">{{ t('ztp.platform') }}</span>
              <span class="font-mono text-ink-900 uppercase">{{ activeOverride?.platform || '-' }}</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-ink-500">{{ t('ztp.name') }}</span>
              <span class="font-mono text-ink-900 truncate max-w-[160px]">{{ activeOverride?.sysname || '-' }}</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="text-ink-500">{{ t('ztp.updated_at') }}</span>
              <span class="font-mono text-ink-900 text-xs">{{ activeOverride?.updated_at || '-' }}</span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </template>
</template>
