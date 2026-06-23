// V2.1 后端 API 客户端 —— 对接 V2.0 后端 7 个 API
// 统一响应格式：{ success: true, data: {...} } / { success: false, error: "..." }

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
    return { success: false, error: '网络请求失败，请检查后端服务是否运行' }
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
export const assetApi = {
  get: (deviceId) => apiCall(`/devices/${deviceId}/asset`),
  update: (deviceId, payload) =>
    apiCall(`/devices/${deviceId}/asset`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  refresh: (deviceId) =>
    apiCall(`/devices/${deviceId}/asset/refresh`, { method: 'POST' }),
}

// 操作日志
export const logApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiCall(`/logs${qs ? '?' + qs : ''}`)
  },
}
