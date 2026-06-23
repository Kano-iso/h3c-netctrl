// 设备状态显示工具
// 后端可能返回 null / undefined / '' / 'unknown' / 'online' / 'warning' / 'maintenance' / 'offline'
// 统一映射到 UI 显示

const STATUS_MAP = {
  online:      { label: '在线', chipClass: 'chip-good' },
  warning:     { label: '告警', chipClass: 'chip-warn' },
  maintenance: { label: '维护', chipClass: 'chip-warn' },
  offline:     { label: '离线', chipClass: 'chip-bad' },
  unknown:     { label: '未采集', chipClass: 'chip-mute' },
}

const DOT_CLASS = {
  online: 'bg-good',
  warning: 'bg-warn',
  maintenance: 'bg-warn',
  offline: 'bg-bad',
  unknown: 'bg-ink-400',
}

export function getStatusInfo(s) {
  if (!s || s === 'unknown') return STATUS_MAP.unknown
  return STATUS_MAP[s] || STATUS_MAP.unknown
}

export function getStatusDot(s) {
  if (!s || s === 'unknown') return DOT_CLASS.unknown
  return DOT_CLASS[s] || DOT_CLASS.unknown
}

export function getStatusLabel(s) {
  return getStatusInfo(s).label
}

export function getStatusChip(s) {
  return getStatusInfo(s).chipClass
}

// 端口/接口 status 映射（接口 up/down/administrarive）
const IFACE_STATUS_MAP = {
  up: 'UP',
  down: 'DOWN',
  testing: '测试中',
  unknown: '—',
  administratively_down: '禁用',
}

export function getIfaceStatusLabel(s) {
  if (!s) return '—'
  return IFACE_STATUS_MAP[s] || IFACE_STATUS_MAP.unknown
}
