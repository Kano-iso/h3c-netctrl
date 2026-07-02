import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Dashboard from './views/Dashboard.vue'
import Devices from './views/Devices.vue'
import OpsTerminal from './views/OpsTerminal.vue'
import Interfaces from './views/Interfaces.vue'
import CMDB from './views/CMDB.vue'
import Logs from './views/Logs.vue'
import Batch from './views/Batch.vue'
import Topology from './views/Topology.vue'
import Backup from './views/Backup.vue'
import AIAssistant from './views/AIAssistant.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Dashboard, name: 'dashboard' },
    { path: '/devices', component: Devices, name: 'devices' },
    { path: '/ops', component: OpsTerminal, name: 'ops' },
    { path: '/interfaces', component: Interfaces, name: 'interfaces' },
    { path: '/cmdb', component: CMDB, name: 'cmdb' },
    { path: '/logs', component: Logs, name: 'logs' },
    { path: '/batch', component: Batch, name: 'batch' },
    { path: '/topology', component: Topology, name: 'topology', meta: { future: true } },
    { path: '/backup', component: Backup, name: 'backup', meta: { future: true } },
    { path: '/ai', component: AIAssistant, name: 'ai', meta: { future: true } }
  ]
})

createApp(App).use(createPinia()).use(router).mount('#app')
