<template>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container">
      <router-link class="navbar-brand" to="/">H3C NetCtrl</router-link>
      <div class="navbar-nav">
        <router-link class="nav-link" to="/" :class="{ active: $route.path === '/' }">设备管理</router-link>
        <router-link class="nav-link" to="/logs" :class="{ active: $route.path === '/logs' }">操作日志</router-link>
      </div>
    </div>
  </nav>
</template>
