// locale 切换 Pinia store（v2.6 i18n）
//
// 桥接 vue-i18n 与 localStorage：
// - store.current 与 i18n.global.locale.value 始终同步
// - setLocale() 是唯一修改入口（同步 i18n + 写 localStorage）
// - 启动时由 i18n/index.js 从 localStorage 还原（见 main.js 注入顺序）
//
// 详见: openspec/changes/v26-i18n/design.md 决策 1-2
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { i18n } from '../i18n'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']
export const LOCALE_STORAGE_KEY = 'locale'

export const useLocaleStore = defineStore('locale', () => {
  // 单一来源 = vue-i18n 的 locale ref
  // 启动时 i18n/index.js 已从 localStorage 还原
  const current = ref(i18n.global.locale.value)

  // 同步到 vue-i18n（保证模板 $t() 响应式更新）
  function _syncI18n(locale) {
    if (i18n.global.locale.value !== locale) {
      i18n.global.locale.value = locale
    }
  }

  // 切换到指定 locale
  function setLocale(locale) {
    if (!SUPPORTED_LOCALES.includes(locale)) {
      console.warn(`[locale] 不支持的 locale: ${locale}，已忽略`)
      return
    }
    current.value = locale
    _syncI18n(locale)
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale)
    } catch (e) {
      console.warn('[locale] 持久化失败:', e)
    }
  }

  // 中英切换（用于顶导 toggle 按钮）
  function toggleLocale() {
    const next = current.value === 'zh-CN' ? 'en-US' : 'zh-CN'
    setLocale(next)
  }

  return {
    current,
    setLocale,
    toggleLocale,
  }
})
