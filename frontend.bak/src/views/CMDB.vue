<template>
  <div>
    <h4 class="mb-4"><i class="bi bi-database me-2"></i>CMDB 资产管理</h4>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-danger alert-dismissible fade show">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- 设备资产表格 -->
    <div class="card border-0 shadow-sm">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-5">
          <div class="spinner-border text-primary" role="status"></div>
        </div>
        <table v-else class="table table-hover mb-0">
          <thead class="table-light">
            <tr>
              <th>设备名称</th>
              <th>IP 地址</th>
              <th>型号</th>
              <th>SN</th>
              <th>固件版本</th>
              <th>软件包</th>
              <th>位置</th>
              <th>标签</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in assets" :key="item.device_id">
              <td>{{ item.device_name }}</td>
              <td>{{ item.host }}</td>
              <td>{{ item.model || '-' }}</td>
              <td>{{ item.serial_number || '-' }}</td>
              <td>{{ item.firmware_version || '-' }}</td>
              <td>{{ item.software_package || '-' }}</td>
              <td>{{ item.location || '-' }}</td>
              <td>
                <span v-for="tag in (item.tags || '').split(',').filter(Boolean)" :key="tag" class="badge bg-info me-1">{{ tag }}</span>
                <span v-if="!item.tags">-</span>
              </td>
              <td>
                <span :class="statusClass(item.status)" class="badge">{{ statusLabel(item.status) }}</span>
              </td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="refreshAsset(item.device_id)" :disabled="item.refreshing">
                  <span v-if="item.refreshing" class="spinner-border spinner-border-sm"></span>
                  刷新
                </button>
                <button class="btn btn-outline-secondary btn-sm" @click="openEditAsset(item)">编辑</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="assets.length === 0 && !loading" class="text-center py-4 text-muted">暂无资产数据</div>
      </div>
    </div>

    <!-- 编辑资产弹窗 -->
    <div v-if="editTarget" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">编辑资产信息 - {{ editTarget.device_name }}</h5>
            <button type="button" class="btn-close" @click="editTarget = null"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">物理位置</label>
              <input type="text" class="form-control" v-model="editForm.location" placeholder="机房A-机架03-U15">
            </div>
            <div class="mb-3">
              <label class="form-label">业务标签（逗号分隔）</label>
              <input type="text" class="form-control" v-model="editForm.tags" placeholder="核心,数据中心">
            </div>
            <div class="mb-3">
              <label class="form-label">管理状态</label>
              <select class="form-select" v-model="editForm.status">
                <option value="online">在线</option>
                <option value="offline">离线</option>
                <option value="maintenance">维护中</option>
                <option value="decommissioned">已下线</option>
                <option value="unknown">未知</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="editTarget = null">取消</button>
            <button class="btn btn-primary" @click="saveAsset" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { deviceApi, apiCall } from '../api'

const assets = ref([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const editTarget = ref(null)
const editForm = ref({ location: '', tags: '', status: 'unknown' })

function statusClass(status) {
  const map = { online: 'bg-success', offline: 'bg-secondary', maintenance: 'bg-warning', decommissioned: 'bg-danger', unknown: 'bg-secondary' }
  return map[status] || 'bg-secondary'
}

function statusLabel(status) {
  const map = { online: '在线', offline: '离线', maintenance: '维护中', decommissioned: '已下线', unknown: '未知' }
  return map[status] || status
}

async function loadAssets() {
  loading.value = true
  const devRes = await deviceApi.list()
  if (!devRes.success) {
    error.value = devRes.error
    loading.value = false
    return
  }
  const devices = devRes.data || []
  // 并行获取每个设备的资产信息
  const results = await Promise.all(
    devices.map(async (d) => {
      const res = await apiCall(`/devices/${d.id}/asset`)
      return {
        device_id: d.id,
        device_name: d.name,
        host: d.host,
        ...(res.success ? res.data : {}),
        refreshing: false,
      }
    })
  )
  assets.value = results
  loading.value = false
}

async function refreshAsset(deviceId) {
  const item = assets.value.find(a => a.device_id === deviceId)
  if (item) item.refreshing = true
  const res = await apiCall(`/devices/${deviceId}/asset/refresh`, { method: 'POST' })
  if (res.success) {
    await loadAssets()
  } else {
    error.value = res.error || '刷新失败'
    if (item) item.refreshing = false
  }
}

function openEditAsset(item) {
  editTarget.value = item
  editForm.value = { location: item.location || '', tags: item.tags || '', status: item.status || 'unknown' }
}

async function saveAsset() {
  saving.value = true
  const res = await apiCall(`/devices/${editTarget.value.device_id}/asset`, {
    method: 'PUT',
    body: JSON.stringify(editForm.value),
  })
  if (res.success) {
    editTarget.value = null
    await loadAssets()
  } else {
    error.value = res.error || '保存失败'
  }
  saving.value = false
}

onMounted(loadAssets)
</script>
