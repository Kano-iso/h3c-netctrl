import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import DeviceList from '../views/DeviceList.vue'
import DeviceDetail from '../views/DeviceDetail.vue'
import OpsTerminal from '../views/OpsTerminal.vue'
import CMDB from '../views/CMDB.vue'
import LogViewer from '../views/LogViewer.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: Dashboard },
  { path: '/devices', name: 'devices', component: DeviceList },
  { path: '/devices/:id', name: 'device-detail', component: DeviceDetail },
  { path: '/terminal', name: 'terminal', component: OpsTerminal },
  { path: '/cmdb', name: 'cmdb', component: CMDB },
  { path: '/logs', name: 'logs', component: LogViewer },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
