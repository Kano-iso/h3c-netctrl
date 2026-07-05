// frontend/src/i18n/t.js
// utils 层（非组件）i18n helper —— 显式 lookup messages
//
// 原因：vue-i18n v9 legacy:false 模式下，i18n.global.t 在模块作用域时对
//   locale 切换反应不稳定（实测：setTimeout 内 locale 改了但 t() 仍返回旧值）
//   显式从 messages lookup 100% 可靠，且不依赖 vue-i18n 内部行为
// 组件内仍用 useI18n() 的 t()，因为有 composer scope
//
// 用法：
//   import { t } from '../i18n/t'
//   t('errors.network_failed')
//   t('errors.download_failed_http', { status: 500 })
//
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md 决策 3

import { i18n } from './index.js'

/**
 * 根据 key 在当前 locale 的 messages 中查找翻译
 * 支持点号路径（a.b.c）和简单 {name} 插值
 * @param {string} key dot-separated key
 * @param {Object} [params] 插值参数，例如 { status: 500 }
 * @returns {string} 翻译结果；找不到则返回 key 本身
 */
export function t(key, params) {
  const locale = i18n.global.locale.value
  const messages = i18n.global.messages.value
  const root = messages[locale]
  if (!root) return key

  const keys = key.split('.')
  let v = root
  for (const k of keys) {
    if (v == null || typeof v !== 'object') return key
    v = v[k]
  }
  if (typeof v !== 'string') return key

  if (params) {
    return v.replace(/\{(\w+)\}/g, (_, name) => {
      return params[name] != null ? String(params[name]) : `{${name}}`
    })
  }
  return v
}
