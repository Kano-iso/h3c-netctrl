<template>
  <div>
    <h2 class="mb-4">操作日志</h2>

    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-danger alert-dismissible fade show">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- 筛选区 -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-md-3">
            <label class="form-label">操作类型</label>
            <select class="form-select form-select-sm" v-model="filter.action">
              <option value="">全部</option>
              <option value="connect">连接测试</option>
              <option value="vlan_create">创建VLAN</option>
              <option value="vlan_update">修改VLAN</option>
              <option value="vlan_delete">删除VLAN</option>
              <option value="execute">命令执行</option>
              <option value="batch_execute">批量执行</option>
              <option value="asset_refresh">刷新资产</option>
              <option value="interface_config">接口配置</option>
            </select>
          </div>
          <div class="col-md-3">
            <label class="form-label">设备</label>
            <select class="form-select form-select-sm" v-model="filter.device_id">
              <option value="">全部设备</option>
              <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }} ({{ d.host }})</option>
            </select>
          </div>
          <div class="col-md-3">
            <button class="btn btn-primary btn-sm" @click="loadLogs">查询</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
    </div>

    <!-- 日志表格 -->
    <div v-else class="card">
      <div class="card-body p-0">
        <table class="table table-striped table-hover mb-0">
          <thead>
            <tr>
              <th>时间</th>
              <th>设备</th>
              <th>操作</th>
              <th>详情</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" @click="toggleLogDetail(log.id)" style="cursor: pointer;">
              <td><small>{{ formatTime(log.created_at) }}</small></td>
              <td>{{ log.device_name }}</td>
              <td><span class="badge bg-secondary">{{ actionLabel(log.action) }}</span></td>
              <td>{{ log.detail }}</td>
              <td>
                <span v-if="log.status === 'success'" class="badge bg-success">成功</span>
                <span v-else class="badge bg-danger">失败</span>
              </td>
            </tr>
            <tr v-if="expandedLogId">
              <td colspan="5">
                <div class="p-2 bg-light rounded small">
                  <strong>详细信息:</strong> {{ logs.find(l => l.id === expandedLogId)?.detail }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="logs.length === 0" class="text-center py-4 text-muted">暂无日志记录</div>
    </div>

    <!-- 分页 -->
    <nav v-if="total > pageSize" class="mt-3">
      <ul class="pagination pagination-sm justify-content-center">
        <li class="page-item" :class="{ disabled: page <= 1 }">
          <a class="page-link" href="#" @click.prevent="goPage(page - 1)">上一页</a>
        </li>
        <li class="page-item active"><a class="page-link" href="#">{{ page }}</a></li>
        <li class="page-item" :class="{ disabled: page * pageSize >= total }">
          <a class="page-link" href="#" @click.prevent="goPage(page + 1)">下一页</a>
        </li>
      </ul>
      <p class="text-center text-muted small">共 {{ total }} 条记录</p>
    </nav>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiCall, deviceApi } from '../api'

const logs = ref([])
const devices = ref([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const filter = ref({ action: '', device_id: '' })

const expandedLogId = ref(null)
function toggleLogDetail(id) {
  expandedLogId.value = expandedLogId.value === id ? null : id
}

const actionLabels = {
  connect: '连接测试',
  vlan_create: '创建VLAN',
  vlan_update: '修改VLAN',
  vlan_delete: '删除VLAN',
  execute: '命令执行',
  batch_execute: '批量执行',
  asset_refresh: '刷新资产',
  interface_config: '接口配置',
}

function actionLabel(action) {
  return actionLabels[action] || action
}

function formatTime(dt) {
  if (!dt) return ''
  return dt.replace('T', ' ')
}

async function loadDevices() {
  const res = await deviceApi.list()
  if (res.success) {
    devices.value = res.data || []
  }
}

async function loadLogs() {
  loading.value = true
  error.value = ''

  let path = `/logs?page=${page.value}&page_size=${pageSize.value}`
  if (filter.value.action) path += `&action=${filter.value.action}`
  if (filter.value.device_id) path += `&device_id=${filter.value.device_id}`

  const res = await apiCall(path)
  if (res.success) {
    logs.value = res.data?.items || []
    total.value = res.data?.total || 0
  } else {
    error.value = res.error || '加载日志失败'
  }
  loading.value = false
}

function goPage(p) {
  if (p < 1 || p * pageSize.value >= total.value + pageSize.value) return
  page.value = p
  loadLogs()
}

onMounted(async () => {
  await loadDevices()
  await loadLogs()
})
</script>
