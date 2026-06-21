<template>
  <div>
    <!-- 错误提示 -->
    <div v-if="error" class="alert alert-danger alert-dismissible fade show">
      {{ error }}
      <button type="button" class="btn-close" @click="error = ''"></button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
    </div>

    <template v-else-if="device">
      <!-- 返回导航 -->
      <router-link to="/devices" class="text-decoration-none">&larr; 返回设备列表</router-link>

      <!-- 设备信息卡片 -->
      <div class="card mt-3 mb-4">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0">{{ device.name }}</h5>
          <div>
            <button class="btn btn-outline-primary btn-sm me-2" @click="testConnection" :disabled="testing">
              <span v-if="testing" class="spinner-border spinner-border-sm me-1"></span>
              {{ testing ? '测试中...' : '测试连接' }}
            </button>
            <button class="btn btn-outline-secondary btn-sm" @click="showEditModal = true">编辑</button>
          </div>
        </div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-3"><strong>IP 地址:</strong> {{ device.host }}</div>
            <div class="col-md-3"><strong>端口:</strong> {{ device.port }}</div>
            <div class="col-md-3"><strong>用户名:</strong> {{ device.username }}</div>
            <div class="col-md-3"><strong>更新时间:</strong> {{ device.updated_at }}</div>
          </div>
        </div>
      </div>

      <!-- VLAN 管理区 -->
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0">VLAN 管理</h5>
          <div>
            <button class="btn btn-outline-secondary btn-sm me-2" @click="loadVlans">刷新</button>
            <button class="btn btn-primary btn-sm" @click="openAddVlan">新增 VLAN</button>
          </div>
        </div>
        <div class="card-body">
          <div v-if="vlanLoading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
            <span class="ms-2">加载中...</span>
          </div>
          <table v-else-if="vlans.length > 0" class="table table-striped table-hover">
            <thead>
              <tr><th>VLAN ID</th><th>VLAN 名称</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="vlan in vlans" :key="vlan.vlan_id">
                <td>{{ vlan.vlan_id }}</td>
                <td>{{ vlan.name }}</td>
                <td>
                  <button class="btn btn-outline-primary btn-sm me-1" @click="openEditVlan(vlan)">编辑</button>
                  <button class="btn btn-outline-danger btn-sm" @click="confirmDeleteVlan(vlan)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-muted text-center">暂无VLAN数据</p>
        </div>
      </div>

      <!-- 资产信息 -->
      <div class="card mt-3">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0"><i class="bi bi-database me-1"></i>资产信息</h5>
          <div>
            <button class="btn btn-outline-primary btn-sm me-2" @click="refreshAssetInfo" :disabled="assetRefreshing">
              <span v-if="assetRefreshing" class="spinner-border spinner-border-sm me-1"></span>
              刷新硬件信息
            </button>
            <button class="btn btn-outline-secondary btn-sm" @click="showAssetEdit = true">编辑</button>
          </div>
        </div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-3"><strong>型号:</strong> {{ assetInfo.model || '-' }}</div>
            <div class="col-md-3"><strong>SN:</strong> {{ assetInfo.serial_number || '-' }}</div>
            <div class="col-md-3"><strong>固件:</strong> {{ assetInfo.firmware_version || '-' }}</div>
            <div class="col-md-3"><strong>状态:</strong>
              <span :class="assetInfo.status === 'online' ? 'text-success' : 'text-secondary'">
                {{ assetInfo.status === 'online' ? '在线' : assetInfo.status === 'offline' ? '离线' : '未知' }}
              </span>
            </div>
          </div>
          <div class="row mt-2">
            <div class="col-md-3"><strong>CPU:</strong> {{ assetInfo.cpu_usage || '-' }}</div>
            <div class="col-md-3"><strong>内存:</strong> {{ assetInfo.memory_usage || '-' }}</div>
            <div class="col-md-3"><strong>位置:</strong> {{ assetInfo.location || '-' }}</div>
            <div class="col-md-3"><strong>标签:</strong> {{ assetInfo.tags || '-' }}</div>
          </div>
        </div>
      </div>

      <!-- 接口管理 -->
      <div class="card mt-3">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0"><i class="bi bi-ethernet me-1"></i>接口管理</h5>
          <button class="btn btn-outline-secondary btn-sm" @click="loadInterfaces">刷新</button>
        </div>
        <div class="card-body">
          <div v-if="ifaceLoading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
            <span class="ms-2">加载中...</span>
          </div>
          <table v-else-if="interfaces.length > 0" class="table table-striped table-hover">
            <thead>
              <tr><th>接口名</th><th>状态</th><th>模式</th><th>VLAN</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="iface in interfaces" :key="iface.name">
                <td>{{ iface.name }}</td>
                <td>{{ iface.status }}</td>
                <td>{{ iface.mode }}</td>
                <td>{{ iface.access_vlan || (iface.allowed_vlans && iface.allowed_vlans.join(',')) || '-' }}</td>
                <td><button class="btn btn-outline-primary btn-sm" @click="openIfaceConfig(iface)">配置</button></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-muted text-center">暂无接口数据</p>
        </div>
      </div>

      <!-- 接口配置弹窗 -->
      <div v-if="showIfaceConfig" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">配置接口 - {{ ifaceConfigTarget.name }}</h5>
              <button type="button" class="btn-close" @click="showIfaceConfig = false"></button>
            </div>
            <div class="modal-body">
              <div class="mb-3">
                <label class="form-label">接口模式</label>
                <select class="form-select" v-model="ifaceConfigForm.mode">
                  <option value="access">Access</option>
                  <option value="trunk">Trunk</option>
                </select>
              </div>
              <div v-if="ifaceConfigForm.mode === 'access'" class="mb-3">
                <label class="form-label">Access VLAN</label>
                <input type="number" class="form-control" v-model.number="ifaceConfigForm.access_vlan" min="1" max="4094">
              </div>
              <template v-if="ifaceConfigForm.mode === 'trunk'">
                <div class="mb-3">
                  <label class="form-label">允许 VLAN（逗号分隔）</label>
                  <input type="text" class="form-control" v-model="ifaceConfigForm.allowed_vlans_str" placeholder="10,20,30">
                </div>
                <div class="mb-3">
                  <label class="form-label">PVID</label>
                  <input type="number" class="form-control" v-model.number="ifaceConfigForm.pvid" min="1" max="4094">
                </div>
              </template>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showIfaceConfig = false">取消</button>
              <button class="btn btn-primary" @click="saveIfaceConfig" :disabled="saving">
                {{ saving ? '下发中...' : '下发配置' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 资产编辑弹窗 -->
      <div v-if="showAssetEdit" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">编辑资产信息</h5>
              <button type="button" class="btn-close" @click="showAssetEdit = false"></button>
            </div>
            <div class="modal-body">
              <div class="mb-3">
                <label class="form-label">物理位置</label>
                <input type="text" class="form-control" v-model="assetEditForm.location">
              </div>
              <div class="mb-3">
                <label class="form-label">业务标签</label>
                <input type="text" class="form-control" v-model="assetEditForm.tags">
              </div>
              <div class="mb-3">
                <label class="form-label">管理状态</label>
                <select class="form-select" v-model="assetEditForm.status">
                  <option value="online">在线</option>
                  <option value="offline">离线</option>
                  <option value="maintenance">维护中</option>
                  <option value="unknown">未知</option>
                </select>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showAssetEdit = false">取消</button>
              <button class="btn btn-primary" @click="saveAssetEdit" :disabled="saving">保存</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 编辑设备弹窗 -->
      <div v-if="showEditModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">编辑设备</h5>
              <button type="button" class="btn-close" @click="showEditModal = false"></button>
            </div>
            <div class="modal-body">
              <form>
                <div class="mb-3">
                  <label class="form-label">设备名称</label>
                  <input type="text" class="form-control" v-model="editForm.name">
                </div>
                <div class="mb-3">
                  <label class="form-label">IP 地址</label>
                  <input type="text" class="form-control" v-model="editForm.host">
                </div>
                <div class="mb-3">
                  <label class="form-label">端口</label>
                  <input type="number" class="form-control" v-model.number="editForm.port">
                </div>
                <div class="mb-3">
                  <label class="form-label">用户名</label>
                  <input type="text" class="form-control" v-model="editForm.username">
                </div>
                <div class="mb-3">
                  <label class="form-label">密码（留空不修改）</label>
                  <input type="password" class="form-control" v-model="editForm.password">
                </div>
              </form>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showEditModal = false">取消</button>
              <button class="btn btn-primary" @click="updateDevice" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- VLAN 新增/编辑弹窗 -->
      <div v-if="showVlanModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">{{ vlanEditId ? '编辑 VLAN' : '新增 VLAN' }}</h5>
              <button type="button" class="btn-close" @click="showVlanModal = false"></button>
            </div>
            <div class="modal-body">
              <form @submit.prevent="saveVlan">
                <div class="mb-3" v-if="!vlanEditId">
                  <label class="form-label">VLAN ID</label>
                  <input type="number" class="form-control" v-model.number="vlanForm.vlan_id" min="1" max="4094" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">VLAN 名称</label>
                  <input type="text" class="form-control" v-model="vlanForm.name" required>
                </div>
              </form>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showVlanModal = false">取消</button>
              <button class="btn btn-primary" @click="saveVlan" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- VLAN 删除确认弹窗 -->
      <div v-if="deleteVlanTarget" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">确认删除</h5>
              <button type="button" class="btn-close" @click="deleteVlanTarget = null"></button>
            </div>
            <div class="modal-body">
              <p>确定要删除 VLAN <strong>{{ deleteVlanTarget.vlan_id }}</strong>（{{ deleteVlanTarget.name }}）吗？</p>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="deleteVlanTarget = null">取消</button>
              <button class="btn btn-danger" @click="doDeleteVlan" :disabled="saving">确认删除</button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { deviceApi, vlanApi, apiCall } from '../api'

const route = useRoute()
const deviceId = route.params.id

const device = ref(null)
const vlans = ref([])
const loading = ref(true)
const vlanLoading = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref('')

// 编辑设备
const showEditModal = ref(false)
const editForm = ref({ name: '', host: '', port: 830, username: '', password: '' })

// VLAN 弹窗
const showVlanModal = ref(false)
const vlanEditId = ref(null)
const vlanForm = ref({ vlan_id: 1, name: '' })
const deleteVlanTarget = ref(null)

// 资产信息
const assetInfo = ref({})
const assetRefreshing = ref(false)
const showAssetEdit = ref(false)
const assetEditForm = ref({ location: '', tags: '', status: 'unknown' })

// 接口管理
const interfaces = ref([])
const ifaceLoading = ref(false)
const showIfaceConfig = ref(false)
const ifaceConfigTarget = ref({})
const ifaceConfigForm = ref({ mode: 'access', access_vlan: 1, allowed_vlans_str: '', pvid: 1 })

async function loadDevice() {
  loading.value = true
  const res = await deviceApi.get(deviceId)
  if (res.success) {
    device.value = res.data
    editForm.value = { name: res.data.name, host: res.data.host, port: res.data.port, username: res.data.username, password: '' }
  } else {
    error.value = res.error || '加载设备信息失败'
  }
  loading.value = false
}

async function loadVlans() {
  vlanLoading.value = true
  const res = await vlanApi.list(deviceId)
  if (res.success) {
    vlans.value = res.data || []
  } else {
    error.value = res.error || '加载VLAN失败'
  }
  vlanLoading.value = false
}

async function testConnection() {
  testing.value = true
  error.value = ''
  const res = await deviceApi.test(deviceId)
  if (res.success) {
    alert('连接成功！')
  } else {
    error.value = res.error || '连接测试失败'
  }
  testing.value = false
}

async function updateDevice() {
  saving.value = true
  error.value = ''
  const body = { ...editForm.value }
  if (!body.password) delete body.password
  const res = await deviceApi.update(deviceId, body)
  if (res.success) {
    device.value = res.data
    showEditModal.value = false
  } else {
    error.value = res.error || '更新设备失败'
  }
  saving.value = false
}

function openAddVlan() {
  vlanEditId.value = null
  vlanForm.value = { vlan_id: 1, name: '' }
  showVlanModal.value = true
}

function openEditVlan(vlan) {
  vlanEditId.value = vlan.vlan_id
  vlanForm.value = { vlan_id: vlan.vlan_id, name: vlan.name }
  showVlanModal.value = true
}

async function saveVlan() {
  saving.value = true
  error.value = ''
  let res
  if (vlanEditId.value) {
    res = await vlanApi.update(deviceId, vlanEditId.value, { name: vlanForm.value.name })
  } else {
    res = await vlanApi.create(deviceId, vlanForm.value)
  }
  if (res.success) {
    showVlanModal.value = false
    await loadVlans()
  } else {
    error.value = res.error || '保存VLAN失败'
  }
  saving.value = false
}

function confirmDeleteVlan(vlan) {
  deleteVlanTarget.value = vlan
}

async function doDeleteVlan() {
  saving.value = true
  const res = await vlanApi.delete(deviceId, deleteVlanTarget.value.vlan_id)
  if (res.success) {
    deleteVlanTarget.value = null
    await loadVlans()
  } else {
    error.value = res.error || '删除VLAN失败'
    deleteVlanTarget.value = null
  }
  saving.value = false
}

// 资产信息
async function loadAssetInfo() {
  const res = await apiCall(`/devices/${deviceId}/asset`)
  if (res.success) {
    assetInfo.value = res.data
    assetEditForm.value = { location: res.data.location || '', tags: res.data.tags || '', status: res.data.status || 'unknown' }
  }
}

async function refreshAssetInfo() {
  assetRefreshing.value = true
  const res = await apiCall(`/devices/${deviceId}/asset/refresh`, { method: 'POST' })
  if (res.success) {
    await loadAssetInfo()
  } else {
    error.value = res.error || '刷新失败'
  }
  assetRefreshing.value = false
}

async function saveAssetEdit() {
  saving.value = true
  const res = await apiCall(`/devices/${deviceId}/asset`, {
    method: 'PUT',
    body: JSON.stringify(assetEditForm.value),
  })
  if (res.success) {
    showAssetEdit.value = false
    await loadAssetInfo()
  } else {
    error.value = res.error || '保存失败'
  }
  saving.value = false
}

// 接口管理
async function loadInterfaces() {
  ifaceLoading.value = true
  const res = await apiCall(`/devices/${deviceId}/interfaces`)
  if (res.success) {
    interfaces.value = res.data || []
  } else {
    error.value = res.error || '加载接口失败'
  }
  ifaceLoading.value = false
}

function openIfaceConfig(iface) {
  ifaceConfigTarget.value = iface
  ifaceConfigForm.value = { mode: iface.mode === 'trunk' ? 'trunk' : 'access', access_vlan: iface.access_vlan || 1, allowed_vlans_str: (iface.allowed_vlans || []).join(','), pvid: iface.pvid || 1 }
  showIfaceConfig.value = true
}

async function saveIfaceConfig() {
  saving.value = true
  error.value = ''
  const body = { mode: ifaceConfigForm.value.mode }
  if (body.mode === 'access') {
    body.access_vlan = ifaceConfigForm.value.access_vlan
  } else {
    body.allowed_vlans = ifaceConfigForm.value.allowed_vlans_str.split(',').map(Number).filter(n => n > 0)
    body.pvid = ifaceConfigForm.value.pvid
  }
  const res = await apiCall(`/devices/${deviceId}/interfaces/${encodeURIComponent(ifaceConfigTarget.value.name)}/config`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  if (res.success) {
    showIfaceConfig.value = false
    await loadInterfaces()
  } else {
    error.value = res.error || '配置下发失败'
  }
  saving.value = false
}

onMounted(async () => {
  await loadDevice()
  await loadVlans()
  await loadAssetInfo()
  await loadInterfaces()
})
</script>
