<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h2>设备管理</h2>
      <button class="btn btn-primary" @click="showAddModal = true">添加设备</button>
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
        <div class="card h-100">
          <div class="card-body">
            <h5 class="card-title">{{ device.name }}</h5>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { deviceApi } from '../api'

const devices = ref([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const showAddModal = ref(false)
const deleteTarget = ref(null)

const form = ref({ name: '', host: '', port: 830, username: '', password: '' })

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
