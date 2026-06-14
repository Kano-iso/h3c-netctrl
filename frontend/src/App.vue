<template>
  <div>
    <NavBar />
    <div class="container py-4">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import NavBar from './components/NavBar.vue'
</script>
