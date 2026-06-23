<template>
  <div class="d-flex">
    <SideBar />
    <div class="main-content flex-grow-1" style="margin-left: 220px;">
      <div class="container-fluid p-4">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import SideBar from './components/SideBar.vue'
</script>
