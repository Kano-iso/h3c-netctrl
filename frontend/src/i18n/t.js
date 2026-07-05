// frontend/src/i18n/t.js
// utils 层（非组件）i18n helper
//
// 原因：vue-i18n v9 legacy:false 模式下，i18n.global.t 在模块作用域时对
//   locale 切换反应不稳定（实测：setTimeout 内 locale 改了但 t() 仍返回旧值）
//   → 改用：先从 messages 显式 lookup（locale 同步），找不到再 fallback 到
//   i18n.global.t（兼容嵌套 key / 数字格式化等高级功能）
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
 * 简单 {name} 插值
 */
function _interpolate(template, params) {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, name) => {
    return params[name] != null ? String(params[name]) : `{${name}}`
  })
}

/**
 * 在当前 locale 的 messages 中按点号路径查找翻译
 * 找不到返回 null（不返回 key，让调用方决定 fallback）
 */
function _lookup(key) {
  const messages = i18n.global.messages?.value
  if (!messages) return null
  const locale = i18n.global.locale.value
  const root = messages[locale] || messages[i18n.global.fallbackLocale?.value || 'zh-CN']
  if (!root || typeof root !== 'object') return null
  const keys = key.split('.')
  let v = root
  for (const k of keys) {
    if (v == null || typeof v !== 'object') return null
    v = v[k]
  }
  return typeof v === 'string' ? v : null
}

/**
 * 根据 key 翻译
 * 1. 先走显式 messages lookup（locale 同步、测试环境可靠）
 * 2. 找不到 fallback 到 i18n.global.t（处理嵌套/高级 key）
 * 3. 都不行返回 key
 */
export function t(key, params) {
  const hit = _lookup(key)
  if (hit != null) return _interpolate(hit, params)
  // fallback: 让 vue-i18n 处理（数字、命名空间、复数等）
  try {
    const fallback = i18n.global.t(key, params)
    if (fallback && fallback !== key) return fallback
  } catch {
    // ignore
  }
  return key
}
