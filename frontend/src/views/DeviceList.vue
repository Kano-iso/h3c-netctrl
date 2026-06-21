<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h4><i class="bi bi-hdd-stack me-2"></i>设备管理</h4>
      <div>
        <button v-if="selectedDevices.length > 0" class="btn btn-warning btn-sm me-2" @click="showBatchModal = true">
          <i class="bi bi-lightning me-1"></i>批量操作 ({{ selectedDevices.length }})
        </button>
        <button class="btn btn-primary btn-sm" @click="showAddModal = true">
          <i class="bi bi-plus-lg me-1"></i>添加设备
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-danger alert-dismissible fade show">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
      <p class="mt-2 text-muted">加载设备列表...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="devices.length === 0" class="text-center py-5">
      <p class="text-muted">暂无设备，点击"添加设备"开始</p>
    </div>

    <!-- 设备卡片列表 -->
    <div v-else class="row">
      <div v-for="device in devices" :key="device.id" class="col-md-6 col-lg-4 mb-3">
        <div class="card h-100 border-0 shadow-sm" :class="{ 'border-primary': isSelected(device.id) }">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start">
              <h5 class="card-title mb-2">
                <span class="status-dot" :class="device._status === 'online' ? 'status-online' : 'status-offline'"></span>
                {{ device.name }}
              </h5>
              <input type="checkbox" class="form-check-input" :checked="isSelected(device.id)" @change="toggleSelect(device.id)">
            </div>
            <p class="card-text mb-1"><small class="text-muted">IP:</small> {{ device.host }}:{{ device.port }}</p>
            <p class="card-text mb-1"><small class="text-muted">用户:</small> {{ device.username }}</p>
          </div>
          <div class="card-footer bg-transparent d-flex justify-content-between">
            <router-link :to="`/devices/${device.id}`" class="btn btn-outline-primary btn-sm">查看详情</router-link>
            <button class="btn btn-outline-danger btn-sm" @click="confirmDelete(device)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加设备弹窗 -->
    <div v-if="showAddModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">添加设备</h5>
            <button type="button" class="btn-close" @click="showAddModal = false"></button>
          </div>
          <div class="modal-body">
            <form @submit.prevent="addDevice">
              <div class="mb-3">
                <label class="form-label">设备名称</label>
                <input type="text" class="form-control" v-model="form.name" required>
              </div>
              <div class="mb-3">
                <label class="form-label">IP 地址</label>
                <input type="text" class="form-control" v-model="form.host" required placeholder="192.168.1.1">
              </div>
              <div class="mb-3">
                <label class="form-label">端口</label>
                <input type="number" class="form-control" v-model.number="form.port" required>
              </div>
              <div class="mb-3">
                <label class="form-label">用户名</label>
                <input type="text" class="form-control" v-model="form.username" required>
              </div>
              <div class="mb-3">
                <label class="form-label">密码</label>
                <input type="password" class="form-control" v-model="form.password" required>
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showAddModal = false">取消</button>
            <button class="btn btn-primary" @click="addDevice" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">确认删除</h5>
            <button type="button" class="btn-close" @click="deleteTarget = null"></button>
          </div>
          <div class="modal-body">
            <p>确定要删除设备 <strong>{{ deleteTarget.name }}</strong>（{{ deleteTarget.host }}）吗？</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="deleteTarget = null">取消</button>
            <button class="btn btn-danger" @click="doDelete" :disabled="saving">
              {{ saving ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量操作弹窗 -->
    <div v-if="showBatchModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="bi bi-lightning me-1"></i>批量执行命令</h5>
            <button type="button" class="btn-close" @click="showBatchModal = false"></button>
          </div>
          <div class="modal-body">
            <p class="text-muted">已选择 {{ selectedDevices.length }} 台设备</p>
            <div class="mb-3">
              <label class="form-label">命令</label>
              <input type="text" class="form-control" v-model="batchCommand" placeholder="display version" @keyup.enter="executeBatch">
            </div>
            <!-- 批量执行结果 -->
            <div v-if="batchResults.length > 0">
              <h6>执行结果</h6>
              <table class="table table-sm table-bordered">
                <thead><tr><th>设备</th><th>状态</th><th>输出/错误</th></tr></thead>
                <tbody>
                  <tr v-for="r in batchResults" :key="r.device_id">
                    <td>{{ r.device_name }}</td>
                    <td>
                      <span v-if="r.success" class="badge bg-success">成功</span>
                      <span v-else class="badge bg-danger">失败</span>
                    </td>
                    <td><pre class="mb-0 small" style="max-height:100px;overflow-y:auto;">{{ r.output || r.error }}</pre></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showBatchModal = false; batchResults = []">关闭</button>
            <button class="btn btn-warning" @click="executeBatch" :disabled="batchExecuting || !batchCommand">
              <span v-if="batchExecuting" class="spinner-border spinner-border-sm me-1"></span>
              {{ batchExecuting ? '执行中...' : '执行' }}
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

const devices = ref([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const showAddModal = ref(false)
const deleteTarget = ref(null)
const form = ref({ name: '', host: '', port: 830, username: '', password: '' })

// 批量操作
const selectedDevices = ref([])
const showBatchModal = ref(false)
const batchCommand = ref('')
const batchExecuting = ref(false)
const batchResults = ref([])

function isSelected(id) {
  return selectedDevices.value.includes(id)
}

function toggleSelect(id) {
  const idx = selectedDevices.value.indexOf(id)
  if (idx >= 0) {
    selectedDevices.value.splice(idx, 1)
  } else {
    selectedDevices.value.push(id)
  }
}

async function executeBatch() {
  batchExecuting.value = true
  batchResults.value = []
  const res = await apiCall('/batch/execute', {
    method: 'POST',
    body: JSON.stringify({ device_ids: selectedDevices.value, command: batchCommand.value }),
  })
  if (res.success) {
    batchResults.value = res.data.results || []
  } else {
    error.value = res.error || '批量执行失败'
  }
  batchExecuting.value = false
}

async function loadDevices() {
  loading.value = true
  error.value = ''
  const res = await deviceApi.list()
  if (res.success) {
    devices.value = res.data || []
  } else {
    error.value = res.error || '加载设备列表失败'
  }
  loading.value = false
}

async function addDevice() {
  saving.value = true
  error.value = ''
  const res = await deviceApi.create(form.value)
  if (res.success) {
    showAddModal.value = false
    form.value = { name: '', host: '', port: 830, username: '', password: '' }
    await loadDevices()
  } else {
    error.value = res.error || '添加设备失败'
  }
  saving.value = false
}

function confirmDelete(device) {
  deleteTarget.value = device
}

async function doDelete() {
  saving.value = true
  const res = await deviceApi.delete(deleteTarget.value.id)
  if (res.success) {
    deleteTarget.value = null
    await loadDevices()
  } else {
    error.value = res.error || '删除设备失败'
    deleteTarget.value = null
  }
  saving.value = false
}

onMounted(loadDevices)
</script>

<style scoped>
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
.status-online { background-color: #198754; }
.status-offline { background-color: #6c757d; }
</style>
