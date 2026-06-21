<template>
  <div>
    <h4 class="mb-4"><i class="bi bi-speedometer2 me-2"></i>仪表盘</h4>

    <!-- 设备统计卡片 -->
    <div class="row mb-4">
      <div class="col-md-4">
        <div class="card border-0 shadow-sm">
          <div class="card-body text-center">
            <i class="bi bi-hdd-stack fs-1 text-primary"></i>
            <h3 class="mt-2 mb-0">{{ stats.total }}</h3>
            <small class="text-muted">设备总数</small>
          </div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card border-0 shadow-sm">
          <div class="card-body text-center">
            <i class="bi bi-check-circle fs-1 text-success"></i>
            <h3 class="mt-2 mb-0">{{ stats.online }}</h3>
            <small class="text-muted">在线设备</small>
          </div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card border-0 shadow-sm">
          <div class="card-body text-center">
            <i class="bi bi-x-circle fs-1 text-danger"></i>
            <h3 class="mt-2 mb-0">{{ stats.offline }}</h3>
            <small class="text-muted">离线设备</small>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <!-- 最近操作 -->
      <div class="col-md-6 mb-4">
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-transparent d-flex justify-content-between align-items-center">
            <h6 class="mb-0"><i class="bi bi-clock-history me-1"></i>最近操作</h6>
            <router-link to="/logs" class="btn btn-sm btn-outline-primary">查看全部</router-link>
          </div>
          <div class="card-body p-0">
            <div v-if="recentLogs.length === 0" class="text-center py-4 text-muted">暂无操作记录</div>
            <div v-else class="list-group list-group-flush">
              <div v-for="log in recentLogs" :key="log.id" class="list-group-item px-3 py-2">
                <div class="d-flex justify-content-between align-items-center">
                  <span>
                    <span :class="log.status === 'success' ? 'text-success' : 'text-danger'">
                      <i :class="log.status === 'success' ? 'bi bi-check-circle' : 'bi bi-x-circle'"></i>
                    </span>
                    <span class="ms-1">{{ log.device_name }}</span>
                    <span class="badge bg-secondary ms-1">{{ actionLabel(log.action) }}</span>
                  </span>
                  <small class="text-muted">{{ formatTime(log.created_at) }}</small>
                </div>
                <small class="text-muted">{{ log.detail }}</small>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近告警 -->
      <div class="col-md-6 mb-4">
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-transparent">
            <h6 class="mb-0"><i class="bi bi-exclamation-triangle me-1 text-warning"></i>最近失败操作</h6>
          </div>
          <div class="card-body p-0">
            <div v-if="recentFailures.length === 0" class="text-center py-4 text-muted">暂无失败记录</div>
            <div v-else class="list-group list-group-flush">
              <div v-for="log in recentFailures" :key="log.id" class="list-group-item px-3 py-2">
                <div class="d-flex justify-content-between align-items-center">
                  <span>
                    <span class="text-danger"><i class="bi bi-x-circle"></i></span>
                    <span class="ms-1">{{ log.device_name }}</span>
                    <span class="badge bg-danger ms-1">{{ actionLabel(log.action) }}</span>
                  </span>
                  <small class="text-muted">{{ formatTime(log.created_at) }}</small>
                </div>
                <small class="text-muted">{{ log.detail }}</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiCall } from '../api'

const stats = ref({ total: 0, online: 0, offline: 0 })
const recentLogs = ref([])
const recentFailures = ref([])

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
  return dt.replace('T', ' ').substring(0, 19)
}

async function loadDashboard() {
  const res = await apiCall('/dashboard')
  if (res.success) {
    stats.value = res.data.device_stats || { total: 0, online: 0, offline: 0 }
    recentLogs.value = res.data.recent_logs || []
    recentFailures.value = res.data.recent_failures || []
  }
}

onMounted(loadDashboard)
</script>
