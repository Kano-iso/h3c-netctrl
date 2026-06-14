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
    return { success: false, error: '网络请求失败，请检查服务是否运行' }
  }
}

// 设备 API
export const deviceApi = {
  list: () => apiCall('/devices'),
  get: (id) => apiCall(`/devices/${id}`),
  create: (data) => apiCall('/devices', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => apiCall(`/devices/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => apiCall(`/devices/${id}`, { method: 'DELETE' }),
  test: (id) => apiCall(`/devices/${id}/test`, { method: 'POST' }),
}

// VLAN API
export const vlanApi = {
  list: (deviceId) => apiCall(`/devices/${deviceId}/vlans`),
  create: (deviceId, data) => apiCall(`/devices/${deviceId}/vlans`, { method: 'POST', body: JSON.stringify(data) }),
  update: (deviceId, vlanId, data) => apiCall(`/devices/${deviceId}/vlans/${vlanId}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (deviceId, vlanId) => apiCall(`/devices/${deviceId}/vlans/${vlanId}`, { method: 'DELETE' }),
}
