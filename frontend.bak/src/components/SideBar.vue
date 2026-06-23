<template>
  <div class="sidebar bg-dark text-white">
    <div class="sidebar-brand p-3 border-bottom border-secondary">
      <h5 class="mb-0"><i class="bi bi-hdd-network me-2"></i>H3C NetCtrl</h5>
    </div>
    <nav class="sidebar-nav py-2">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-link px-3 py-2 d-flex align-items-center"
        :class="{ active: isActive(item.path) }"
      >
        <i :class="item.icon" class="me-2"></i>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { path: '/dashboard', label: '仪表盘', icon: 'bi bi-speedometer2' },
  { path: '/devices', label: '设备管理', icon: 'bi bi-hdd-stack' },
  { path: '/terminal', label: '网络运维', icon: 'bi bi-terminal' },
  { path: '/cmdb', label: 'CMDB', icon: 'bi bi-database' },
  { path: '/logs', label: '操作日志', icon: 'bi bi-journal-text' },
]

function isActive(path) {
  if (path === '/devices') {
    return route.path === '/devices' || route.path.startsWith('/devices/')
  }
  return route.path === path
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  min-height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 1000;
}
.sidebar-brand h5 {
  font-size: 1.1rem;
  font-weight: 600;
}
.sidebar-nav .nav-link {
  color: rgba(255, 255, 255, 0.7);
  transition: all 0.2s;
  font-size: 0.9rem;
  border-radius: 0;
}
.sidebar-nav .nav-link:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}
.sidebar-nav .nav-link.active {
  color: #fff;
  background: rgba(255, 255, 255, 0.15);
  border-left: 3px solid #0d6efd;
}
</style>
