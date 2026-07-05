// frontend/src/i18n/index.js
// v2.6 i18n 集成（vue-i18n v9）
// 命名规范: 模块.子模块.具体含义
// 详见: openspec/changes/v26-i18n/design.md 决策 4

import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN.js'
import enUS from './en-US.js'

// SSR 防御：SPA 项目中 localStorage 始终存在，但写防御代码无害
const stored = typeof localStorage !== 'undefined'
  ? localStorage.getItem('locale')
  : null

export const i18n = createI18n({
  legacy: false,                        // Composition API 模式
  locale: stored || 'zh-CN',            // 默认中文
  fallbackLocale: 'zh-CN',              // 找不到 fallback 中文
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})
