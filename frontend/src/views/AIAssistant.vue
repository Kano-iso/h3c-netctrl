<script setup>
import { ref, nextTick, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'

const { t, locale } = useI18n()

// 预设问题 key（responses 也按此 key 取）
const PRESET_KEYS = ['spine_down', 'leaf_trunk', 'cpu_usage', 'netconf_fail']

const presets = computed(() => PRESET_KEYS.map(k => ({ key: k, text: t(`ai.presets.${k}`) })))

// key → userText（用于 send 时的反查）
const presetTexts = computed(() => {
  const m = {}
  presets.value.forEach(p => { m[p.text] = p.key })
  return m
})

// 初始欢迎消息（响应 locale 变化）
const messages = ref([{ role: 'assistant', text: '' }])
watch(locale, () => {
  messages.value[0].text = t('ai.welcome')
}, { immediate: true })
const input = ref('')
const thinking = ref(false)

const send = async (text) => {
  if (!text.trim() || thinking.value) return
  const userText = text.trim()
  messages.value.push({ role: 'user', text: userText })
  input.value = ''
  thinking.value = true
  await new Promise(r => setTimeout(r, 1200))
  // 命中预设 → 查对应 response key；未命中 → fallback
  const matchedKey = presetTexts.value[userText]
  const reply = matchedKey ? t(`ai.responses.${matchedKey}`) : t('ai.fallback')
  messages.value.push({ role: 'assistant', text: reply })
  thinking.value = false
  nextTick(() => { container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' }) })
}

const container = ref(null)
</script>

<template>
  <PageHeader :title="t('ai.title')" :subtitle="t('ai.subtitle')" :badge="t('ai.badge')">
    <template #actions>
      <span class="chip-info">{{ t('ai.chip_poc') }}</span>
    </template>
  </PageHeader>

  <div class="max-w-4xl mx-auto px-6 pb-16">
    <div class="panel flex flex-col h-[calc(100vh-220px)] overflow-hidden">
      <div class="px-5 py-3 border-b border-canvas-300 flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="size-8 rounded-lg bg-gradient-to-br from-accent-400 to-info flex items-center justify-center">
            <svg class="size-4 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.5 5L18 8.5 13.5 10 12 15l-1.5-5L6 8.5 10.5 7z"/></svg>
          </div>
          <div>
            <div class="text-sm font-semibold text-ink-900">{{ t('ai.brand') }}</div>
            <div class="text-[10px] text-ink-500">{{ t('ai.brand_subtitle') }}</div>
          </div>
        </div>
        <button class="btn-soft !text-xs">{{ t('ai.new_chat') }}</button>
      </div>

      <div ref="container" class="flex-1 overflow-y-auto p-5 space-y-4 bg-canvas-100">
        <div v-for="(m, i) in messages" :key="i" :class="['flex gap-3', m.role === 'user' ? 'flex-row-reverse' : '']">
          <div :class="['size-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0',
            m.role === 'user' ? 'bg-accent text-white' : 'bg-gradient-to-br from-accent-400 to-accent-700 text-white']">
            {{ m.role === 'user' ? t('ai.user_avatar') : t('ai.assistant_avatar') }}
          </div>
          <div :class="['rounded-2xl px-4 py-2.5 text-sm leading-relaxed max-w-[80%] whitespace-pre-wrap',
            m.role === 'user' ? 'bg-accent text-white' : 'bg-white ring-1 ring-canvas-300 text-ink-900']">
            {{ m.text }}
          </div>
        </div>
        <div v-if="thinking" class="flex gap-3">
          <div class="size-7 rounded-full bg-gradient-to-br from-accent-400 to-accent-700 flex items-center justify-center text-xs font-semibold shrink-0 text-white">{{ t('ai.assistant_avatar') }}</div>
          <div class="rounded-2xl bg-white ring-1 ring-canvas-300 px-4 py-3 text-sm text-ink-700 flex items-center gap-1.5">
            <span class="size-1.5 rounded-full bg-accent animate-pulse" />
            <span class="size-1.5 rounded-full bg-accent animate-pulse" style="animation-delay: .15s" />
            <span class="size-1.5 rounded-full bg-accent animate-pulse" style="animation-delay: .3s" />
            <span class="ml-2 text-[10px] text-ink-500">{{ t('ai.thinking') }}</span>
          </div>
        </div>
      </div>

      <div class="border-t border-canvas-300 p-4">
        <div class="flex flex-wrap gap-1.5 mb-3">
          <button v-for="p in presets" :key="p.key" @click="send(p.text)" class="chip-mute hover:bg-canvas-300 !text-[10px]">{{ p.text }}</button>
        </div>
        <div class="flex items-end gap-2">
          <textarea
            v-model="input"
            @keyup.enter.exact.prevent="send(input)"
            rows="2"
            :placeholder="t('ai.input_placeholder')"
            class="input flex-1 resize-none"
          />
          <button @click="send(input)" :disabled="!input.trim() || thinking" class="btn-primary disabled:opacity-50">
            <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            {{ t('ai.send') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
