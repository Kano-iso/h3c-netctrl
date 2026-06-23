<script setup>
defineProps({
  title: String,
  subtitle: String,
  eyebrow: { type: String, default: null },
  badge: { type: String, default: null }
})
</script>

<template>
  <div class="relative">
    <!-- 装饰渐变：放在 z-0 底层，且不参与裁剪（让下拉菜单可溢出） -->
    <div class="absolute inset-0 bg-gradient-to-b from-accent-50/40 via-canvas-50/20 to-canvas pointer-events-none -z-0"></div>
    <div class="absolute -top-20 right-1/3 size-[360px] bg-accent-200/15 rounded-full blur-3xl pointer-events-none -z-0"></div>

    <div class="relative z-10 max-w-[1200px] mx-auto px-8 pt-9 pb-6">
      <div class="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div v-if="eyebrow" class="text-[12px] font-medium text-accent tracking-wide uppercase mb-1.5">{{ eyebrow }}</div>
          <div class="flex items-center gap-2.5">
            <h1 class="text-[30px] font-semibold tracking-tight text-ink-900 leading-tight">{{ title }}</h1>
            <span v-if="badge" class="text-[10px] font-medium px-2 py-0.5 rounded-full bg-canvas-200 text-ink-700">{{ badge }}</span>
          </div>
          <p v-if="subtitle" class="text-[14px] text-ink-600 mt-1 max-w-2xl">{{ subtitle }}</p>
        </div>
        <!-- actions 区域用 relative + z-20，让 Select 的绝对定位下拉菜单能正常溢出显示 -->
        <div class="relative z-20 flex items-center gap-2">
          <slot name="actions" />
        </div>
      </div>
    </div>
  </div>
</template>
