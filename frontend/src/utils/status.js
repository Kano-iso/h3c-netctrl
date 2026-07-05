// 设备状态显示工具
// v2.6 i18n：label 走 t() helper（显式 messages lookup，与 locale 切换可靠同步）
// chipClass / dot class 保持 css 静态（与 locale 无关）
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md 决策 2/3

import { t } from '../i18n/t.js'

// 设备状态键集合
const DEVICE_KEYS = ['online', 'warning', 'maintenance', 'offline', 'unknown']

// dot color（与 locale 无关，纯 css class）
const DOT_CLASS = {
  online: 'bg-good',
  warning: 'bg-warn',
  maintenance: 'bg-warn',
  offline: 'bg-bad',
  unknown: 'bg-ink-400',
}

// chip background（与 locale 无关，纯 css class）
const CHIP_CLASS = {
  online: 'chip-good',
  warning: 'chip-warn',
  maintenance: 'chip-warn',
  offline: 'chip-bad',
  unknown: 'chip-mute',
}

function _normalizeDeviceKey(s) {
  return s && DEVICE_KEYS.includes(s) ? s : 'unknown'
}

export function getStatusLabel(s) {
  return t(`status.device.${_normalizeDeviceKey(s)}`)
}

export function getStatusDot(s) {
  return DOT_CLASS[_normalizeDeviceKey(s)]
}

export function getStatusChip(s) {
  return CHIP_CLASS[_normalizeDeviceKey(s)]
}

// 后向兼容：返回 { label, chipClass } 复合对象
// 已有调用方（v2.5 之前的组件）仍按原 API 使用
export function getStatusInfo(s) {
  return { label: getStatusLabel(s), chipClass: getStatusChip(s) }
}

// 端口/接口 status 映射（接口 up/down/administrarive）
// i18n 化：label 走 t() helper
const IFACE_KEYS = ['up', 'down', 'testing', 'unknown', 'administratively_down']

export function getIfaceStatusLabel(s) {
  if (!s) return t('status.iface.unknown')
  return IFACE_KEYS.includes(s) ? t(`status.iface.${s}`) : t('status.iface.unknown')
}
