import { createRouter, createWebHistory } from 'vue-router'
import DeviceList from '../views/DeviceList.vue'
import DeviceDetail from '../views/DeviceDetail.vue'
import LogViewer from '../views/LogViewer.vue'

const routes = [
  { path: '/', name: 'devices', component: DeviceList },
  { path: '/devices/:id', name: 'device-detail', component: DeviceDetail },
  { path: '/logs', name: 'logs', component: LogViewer },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
