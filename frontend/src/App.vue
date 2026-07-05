<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppFooter from './components/AppFooter.vue'
import BackgroundTaskPanel from './components/BackgroundTaskPanel.vue'

const route = useRoute()
const { t } = useI18n()

// 三大功能组（i18n 化在 Task 3 完成，此处保留硬编码作为占位）
const groups = [
  {
    key: 'ops',
    label: '运维操作',
    desc: '直接对设备下发配置',
    items: [
      { name: 'devices',    label: '设备',     desc: '设备清单 · 连接测试',     icon: 'devices' },
      { name: 'ops',        label: '运维终端', desc: '命令派发式执行',          icon: 'terminal' },
      { name: 'interfaces', label: '接口',     desc: 'Access / Trunk 配置',     icon: 'interface' },
      { name: 'batch',      label: '批量操作', desc: '多设备并行执行',          icon: 'batch' }
    ]
  },
  {
    key: 'ops-mgmt',
    label: '运营管理',
    desc: '资产盘点 · 配置存档',
    items: [
      { name: 'cmdb',       label: 'CMDB', desc: '资产台账', icon: 'cmdb' },
      { name: 'backup',     label: '备份回滚', desc: '定时备份 · 一键回滚', icon: 'backup', future: true }
    ]
  },
  {
    key: 'debug',
    label: '排查诊断',
    desc: '日志 · 拓扑 · AI 辅助',
    items: [
      { name: 'logs',       label: '操作日志', desc: '执行历史 · 错误定位',     icon: 'logs' },
      { name: 'topology',   label: '拓扑视图', desc: 'LLDP 邻居可视化',         icon: 'topology', future: true },
      { name: 'ai',         label: 'AI 助手', desc: '自然语言排错',            icon: 'ai', future: true }
    ]
  }
]

const openGroup = ref(null)
const currentName = computed(() => route.name)

// 当前路由所属组（用于高亮组 tab）
const activeGroup = computed(() => {
  for (const g of groups) {
    if (g.items.some(it => it.name === currentName.value)) return g.key
  }
  return null
})

const open = (key) => { openGroup.value = key }
const close = () => { openGroup.value = null }
const toggle = (key) => { openGroup.value = openGroup.value === key ? null : key }

// 点击外部关闭
const navRef = ref(null)
const onDocClick = (e) => {
  if (navRef.value && !navRef.value.contains(e.target)) close()
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

// SVG icon 渲染
const Icons = {
  devices: 'M9 17l3-3 3 3 5-5M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z',
  terminal: 'M4 17l6-6-6-6M12 19h8',
  interface: 'M9 2v6M15 2v6M5 8h14v3a7 7 0 01-14 0zM12 18v4',
  batch:    'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  cmdb:     'M4 7h16M4 12h16M4 17h10',
  backup:   'M19 14l-7 7-7-7M12 21V3M5 7l7-4 7 4',
  logs:     'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
  topology: 'M12 2v6m0 8v6M2 12h6m8 0h6M5 5l4 4m6 6l4 4M5 19l4-4m6-6l4-4',
  ai:       'M12 2a4 4 0 014 4v2a4 4 0 01-8 0V6a4 4 0 014-4zM5 12h14M12 12v10M8 22h8'
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <!-- 顶部 nav：分类下拉 -->
    <header class="sticky top-0 z-40 backdrop-blur-2xl bg-canvas/70 border-b border-canvas-300/70" ref="navRef">
      <div class="max-w-[1200px] mx-auto px-8 h-[52px] flex items-center gap-2">
        <!-- Logo -->
        <RouterLink :to="{ name: 'dashboard' }" class="flex items-center gap-2.5 shrink-0 mr-4">
          <div class="size-7 rounded-[10px] bg-gradient-to-br from-accent-400 via-accent-500 to-accent-700 flex items-center justify-center shadow-sm">
            <svg class="size-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M4 6h16M4 12h16M4 18h10" stroke-linecap="round"/>
              <circle cx="20" cy="18" r="1.5" fill="currentColor"/>
            </svg>
          </div>
          <div class="text-[13px] font-semibold tracking-tight text-ink-900">H3C NetCtrl</div>
        </RouterLink>

        <!-- 总览（独立 tab） -->
        <RouterLink :to="{ name: 'dashboard' }"
          :class="['nav-item', currentName === 'dashboard' ? 'active' : '']">
          {{ t('nav.dashboard') }}
        </RouterLink>

        <!-- 三大分组（下拉） -->
        <div
          v-for="g in groups" :key="g.key"
          class="relative"
          @mouseenter="open(g.key)"
          @mouseleave="close"
        >
          <button
            @click="toggle(g.key)"
            :class="['nav-item gap-1', activeGroup === g.key || openGroup === g.key ? 'active' : '']">
            <span>{{ g.label }}</span>
            <svg :class="['size-3 transition-transform', openGroup === g.key && 'rotate-180']"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>

          <!-- 下拉面板 -->
          <Transition name="dropdown">
            <div v-if="openGroup === g.key"
              class="absolute left-0 top-[calc(100%+6px)] w-[360px] panel !p-2 shadow-elevated !ring-black/[0.08]">
              <div class="px-3 pt-2 pb-2.5">
                <div class="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-500">{{ g.label }}</div>
                <div class="text-[12px] text-ink-500 mt-0.5">{{ g.desc }}</div>
              </div>
              <div class="border-t border-canvas-300/70 my-1"></div>
              <div class="space-y-0.5 p-1">
                <RouterLink
                  v-for="it in g.items" :key="it.name"
                  :to="{ name: it.name }"
                  @click="close"
                  :class="['flex items-start gap-3 p-2.5 rounded-2xl transition',
                    currentName === it.name ? 'bg-accent/8 ring-1 ring-accent/20' : 'hover:bg-canvas-100']">
                  <div :class="['size-9 shrink-0 rounded-xl flex items-center justify-center',
                    currentName === it.name ? 'bg-gradient-to-br from-accent-400 to-accent-600 text-white shadow-sm' : 'bg-canvas-200 text-ink-700']">
                    <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                      <path :d="Icons[it.icon]" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <span :class="['text-[13px] font-medium', currentName === it.name ? 'text-accent' : 'text-ink-900']">{{ it.label }}</span>
                      <span v-if="it.future" class="text-[9px] font-medium px-1.5 py-[1px] rounded-full bg-canvas-200 text-ink-500 leading-none">未来</span>
                    </div>
                    <div class="text-[11px] text-ink-500 mt-0.5 truncate">{{ it.desc }}</div>
                  </div>
                </RouterLink>
              </div>
            </div>
          </Transition>
        </div>

        <div class="flex-1"></div>

        <!-- 右侧工具 -->
        <div class="flex items-center gap-1.5">
          <button class="size-8 rounded-full hover:bg-canvas-200/80 flex items-center justify-center text-ink-700 transition">
            <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          </button>
          <button class="size-8 rounded-full hover:bg-canvas-200/80 flex items-center justify-center text-ink-700 transition relative">
            <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
            <span class="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-bad ring-2 ring-canvas"></span>
          </button>
          <div class="size-8 rounded-full bg-gradient-to-br from-accent-300 via-accent-500 to-accent-700 flex items-center justify-center text-[11px] font-semibold text-white shadow-sm ml-1">K</div>
        </div>
      </div>
    </header>

    <!-- Main -->
    <main class="flex-1 relative">
      <RouterView v-slot="{ Component, route: r }">
        <component :is="Component" :key="r.fullPath" />
      </RouterView>
    </main>

    <!-- 官网式 Footer -->
    <AppFooter />

    <!-- 后台任务面板（v24-feat-async-backup-status） -->
    <BackgroundTaskPanel />
  </div>
</template>

<style>
/* 页面切换淡入淡出（快速、避免卡顿） */
.fade-enter-active, .fade-leave-active { transition: opacity .12s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.dropdown-enter-active, .dropdown-leave-active { transition: opacity .15s ease, transform .18s cubic-bezier(.2,.8,.2,1); }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
