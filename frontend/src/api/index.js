// V2.1 后端 API 客户端 —— 对接 V2.0 后端 7 个 API
// 统一响应格式：{ success: true, data: {...} } / { success: false, error: "..." }
//
// v2.6 i18n：所有 catch 分支 + 后端 error 兜底走 t() helper（key 在 errors.*）
// utils 层（非组件）用 i18n/t.js 的 t()，组件内仍用 useI18n() 的 t()
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md 决策 3

import { t } from '../i18n/t.js'

const API_BASE = '/api'

export async function apiCall(path, options = {}) {
  const url = API_BASE + path
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  }
  try {
    const response = await fetch(url, config)
    const data = await response.json()
    return data
  } catch (error) {
    return { success: false, error: t('errors.network_failed') }
  }
}

// Dashboard
export const dashboardApi = {
  get: () => apiCall('/dashboard'),
}

// 设备
export const deviceApi = {
  list: () => apiCall('/devices'),
  get: (id) => apiCall(`/devices/${id}`),
  create: (data) => apiCall('/devices', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => apiCall(`/devices/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiCall(`/devices/${id}`, { method: 'DELETE' }),
  test: (id) => apiCall(`/devices/${id}/test`, { method: 'POST' }),
}

// 运维终端 —— 在设备上执行命令
// run(deviceId, payload) 接受：
//   - { command: "display version" }                单命令（向后兼容）
//   - { commands: ["cmd1", "cmd2"], delay_ms: 1000 } 多命令顺序执行
export const executeApi = {
  run: (deviceId, payload) =>
    apiCall(`/devices/${deviceId}/execute`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

// 接口管理 —— NETCONF 接口查询与配置下发
export const interfaceApi = {
  list: (deviceId) => apiCall(`/devices/${deviceId}/interfaces`),
  applyConfig: (deviceId, payload) =>
    apiCall(`/devices/${deviceId}/interfaces/config`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // v2.2.2 patch (fix-vpn-edit-capabilities): 调整 link type
  changeLinkType: (deviceId, ifIndex, mode, force = false) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/link-type`, {
      method: 'PATCH',
      body: JSON.stringify({ mode, force }),
    }),

  // v2.3: 切换 L2/L3 层级（bridge/route）
  setLinkMode: (deviceId, ifIndex, mode, force = false) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/link-mode`, {
      method: 'PATCH',
      body: JSON.stringify({ mode, force }),
    }),

  // v2.2.2 patch (fix-vpn-edit-capabilities): 给 L3 接口设置/替换 IPv4
  setIpv4Address: (deviceId, ifIndex, ip, mask) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/ipv4-address`, {
      method: 'POST',
      body: JSON.stringify({ ip, mask }),
    }),

  // v2.2.2 patch (fix-vpn-edit-capabilities): 清空 L3 接口所有 IPv4
  clearIpv4Address: (deviceId, ifIndex) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/ipv4-address`, {
      method: 'DELETE',
    }),
}

// VPN instance + 接口绑 VPN（v2.2）
export const vpnApi = {
  list: (deviceId) => apiCall(`/devices/${deviceId}/vpn-instances`),
  create: (deviceId, payload) =>
    apiCall(`/devices/${deviceId}/vpn-instances`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  delete: (deviceId, name) =>
    apiCall(`/devices/${deviceId}/vpn-instances/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),
  bindInterface: (deviceId, ifIndex, name) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/vpn-instance`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  unbindInterface: (deviceId, ifIndex) =>
    apiCall(`/devices/${deviceId}/interfaces/${ifIndex}/vpn-instance`, {
      method: 'DELETE',
    }),
}

// 批量操作
export const batchApi = {
  execute: (deviceIds, command) =>
    apiCall('/batch/execute', {
      method: 'POST',
      body: JSON.stringify({ device_ids: deviceIds, command }),
    }),
}

// 资产 CMDB
// v2.6.1 fix-asset-collect-failure: path 从 /devices/{id}/asset/* 改 /assets/device/{id}/*
// 匹配 vite proxy /api/assets → data:8000 规则
export const assetApi = {
  get: (deviceId) => apiCall(`/assets/device/${deviceId}`),
  update: (deviceId, payload) =>
    apiCall(`/assets/device/${deviceId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  refresh: (deviceId) =>
    apiCall(`/assets/device/${deviceId}/refresh`, { method: 'POST' }),
}

// 操作日志
export const logApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiCall(`/logs${qs ? '?' + qs : ''}`)
  },
}

// 配置备份 / 回滚（v2.2）
// 7 个方法对应后端 routers/backup.py：
//   list / create / createAll / download / remove / toggleLock / restore
// 错误处理：apiCall 已统一 try/catch 返回 { success:false, error: "..." }，中文透传
export const backupApi = {
  // 列表
  list: (deviceId) => apiCall(`/devices/${deviceId}/backup`),

  // 单设备备份（POST 空 body，后端 BackupCreateRequest 必填 body 否则 422）
  // 不能用 apiCall 默认 options —— 没 body 字段时 fetch 会发空 body + Content-Type: application/json
  // → FastAPI 422 "Field required: body" → 前端 r.success undefined → 显示"备份失败"
  // v2.6.1 fix-asset-backup-state-sync Task 3: force=true 走 ?force=true query param
  // （后端 asset offline/never_collected 校验跳过 + 标记 backup.forced=1）
  create: (deviceId, force = false) =>
    apiCall(`/devices/${deviceId}/backup${force ? '?force=true' : ''}`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  // 全量备份同步（POST /api/backups，串行对所有设备，结果聚合）— 向后兼容
  // v2.6.1 Task 3: body 支持 force 字段，全量强制备份（offline 设备也执行）
  createAll: (body) => apiCall('/backups', { method: 'POST', body: body || {} }),

  // 全量备份异步（POST /api/backups-async，立即返回 task_id）— v241-supplement Task 8.4
  // 前端默认走异步，避免 7 设备 × 2 type 阻塞 2-4 分钟
  // v2.6.1 Task 3: body 支持 force 字段
  createAllAsync: (body) => apiCall('/backups-async', { method: 'POST', body: body || {} }),

  // 下载（返回 Blob，不走 apiCall 因为它走 .json()）
  download: async (deviceId, backupId) => {
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/backup/${backupId}`)
      if (!res.ok) {
        // 尝试读 error body（如果后端返回 JSON 错误）
        try {
          const data = await res.json()
          return { success: false, error: data.error || t('errors.download_failed_http', { status: res.status }) }
        } catch {
          return { success: false, error: t('errors.download_failed_http', { status: res.status }) }
        }
      }
      const blob = await res.blob()
      // 从 Content-Disposition 取文件名（后端已设 attachment; filename=...）
      const cd = res.headers.get('Content-Disposition') || ''
      const m = cd.match(/filename\*?=(?:UTF-8'')?["']?([^;"']+)/i)
      const filename = m ? decodeURIComponent(m[1]) : `backup-${backupId}.cfg`
      return { success: true, data: { blob, filename } }
    } catch (e) {
      return { success: false, error: t('errors.download_failed_network') }
    }
  },

  // 删除（锁定 → 后端返回 403 + error）
  remove: (deviceId, backupId) =>
    apiCall(`/devices/${deviceId}/backup/${backupId}`, { method: 'DELETE' }),

  // 锁切换（body: { locked: true | false }）
  toggleLock: (deviceId, backupId, locked) =>
    apiCall(`/devices/${deviceId}/backup/${backupId}/lock`, {
      method: 'POST',
      body: JSON.stringify({ locked }),
    }),

  // 回滚：默认 with_reboot=true 走端到端（推 + set as startup + reboot + retry SSH + verify）
  // v2.2 用户场景是"页面点一下就完成回滚"，不 reboot 设备 running-config 不变
  // → 用户看到"没效果"（实测反馈，见 backup-frontend 任务 6）
  // with_reboot=false 仍可显式传，但 UI 默认按钮走 true
  restore: (deviceId, backupId, with_reboot = true) =>
    apiCall(`/devices/${deviceId}/backup/${backupId}/restore`, {
      method: 'POST',
      body: JSON.stringify({ with_reboot }),
    }),
}

// 异步任务管理（v24-feat-async-backup-status）
// 提交耗时操作（备份/回滚）后台执行，前端轮询 GET /api/tasks/{id} 获取进度
export const taskApi = {
  // 异步备份（立即返回 task_id，后台执行）
  // v2.6.1 fix-asset-backup-state-sync Task 3.4: force=true 走 ?force=true query param
  backupAsync: (deviceId, types, force = false) =>
    apiCall(`/devices/${deviceId}/backup-async${force ? '?force=true' : ''}`, {
      method: 'POST',
      body: JSON.stringify({ types: types || ['startup', 'running'] }),
    }),

  // 异步回滚（立即返回 task_id，后台执行）
  restoreAsync: (deviceId, backupId, with_reboot = true) =>
    apiCall(`/devices/${deviceId}/backup/${backupId}/restore-async`, {
      method: 'POST',
      body: JSON.stringify({ with_reboot }),
    }),

  // 查询任务状态（轮询用，每 2s 一次）
  get: (taskId) => apiCall(`/tasks/${taskId}`),

  // 取消任务（协作式取消，任务在下一个检查点退出）
  cancel: (taskId) =>
    apiCall(`/tasks/${taskId}/cancel`, { method: 'POST' }),
}
