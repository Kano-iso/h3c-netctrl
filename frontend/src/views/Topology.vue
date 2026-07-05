<script setup>
import { useI18n } from 'vue-i18n'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()

// V2.1 阶段：拓扑视图尚未对接后端，预览版留作后续
const topology = { nodes: [], links: [] }
</script>

<template>
  <PageHeader :title="t('topology.title')" :subtitle="t('topology.subtitle')" :badge="t('topology.badge')">
    <template #actions>
      <span class="chip-info">{{ t('topology.chip_poc') }}</span>
    </template>
  </PageHeader>

  <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
    <div class="panel p-6">
      <div class="text-base font-semibold text-ink-900 mb-1">{{ t('topology.plan_title') }}</div>
      <div class="text-xs text-ink-500 mb-5">{{ t('topology.plan_desc') }}</div>

      <div class="relative w-full h-[480px] rounded-2xl bg-canvas-200 ring-1 ring-canvas-300 overflow-hidden">
        <div class="absolute inset-0 opacity-[0.06]" style="background-image: linear-gradient(rgba(0,0,0,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.5) 1px, transparent 1px); background-size: 32px 32px;"></div>

        <div
          v-for="n in topology.nodes"
          :key="n.id"
          :style="{ left: `calc(50% + ${n.x}px - 70px)`, top: `calc(50% + ${n.y}px - 36px)` }"
          class="absolute w-[140px] h-[72px] panel p-2 flex flex-col items-center justify-center text-center cursor-pointer panel-hover"
        >
          <div :class="['size-1.5 rounded-full mb-1.5',
            n.role === 'spine' ? 'bg-accent' : n.role === 'leaf' ? 'bg-info' : 'bg-ink-500']" />
          <div class="text-xs font-semibold text-ink-900">{{ n.name }}</div>
          <div class="text-[9px] text-ink-500 uppercase tracking-wider">{{ n.role }}</div>
        </div>

        <svg class="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 800 480" preserveAspectRatio="none">
          <g v-for="(l, i) in topology.links" :key="i">
            <line
              :x1="400 + (topology.nodes.find(n => n.id === l.from)?.x || 0)"
              :y1="240 + (topology.nodes.find(n => n.id === l.from)?.y || 0)"
              :x2="400 + (topology.nodes.find(n => n.id === l.to)?.x || 0)"
              :y2="240 + (topology.nodes.find(n => n.id === l.to)?.y || 0)"
              :stroke="l.status === 'up' ? 'rgba(48,164,108,0.7)' : 'rgba(229,72,77,0.7)'"
              stroke-width="1.5"
              stroke-dasharray="4 4"
            />
          </g>
        </svg>

        <div class="absolute top-4 right-4 panel !p-3 text-[11px] space-y-1.5 !shadow-elevated">
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-accent"></span><span class="text-ink-700">{{ t('topology.legend_spine') }}</span></div>
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-info"></span><span class="text-ink-700">{{ t('topology.legend_leaf') }}</span></div>
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-ink-500"></span><span class="text-ink-700">{{ t('topology.legend_access') }}</span></div>
          <div class="flex items-center gap-2 pt-1.5 border-t border-canvas-300">
            <span class="size-1.5 rounded-full bg-good"></span><span class="text-ink-700">{{ t('topology.legend_up') }}</span>
            <span class="size-1.5 rounded-full bg-bad ml-2"></span><span class="text-ink-700">{{ t('topology.legend_down') }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">{{ t('topology.stage_1') }}</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">{{ t('topology.stage_1_title') }}</div>
        <div class="text-xs text-ink-700">{{ t('topology.stage_1_desc') }}</div>
      </div>
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">{{ t('topology.stage_2') }}</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">{{ t('topology.stage_2_title') }}</div>
        <div class="text-xs text-ink-700">{{ t('topology.stage_2_desc') }}</div>
      </div>
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">{{ t('topology.stage_3') }}</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">{{ t('topology.stage_3_title') }}</div>
        <div class="text-xs text-ink-700">{{ t('topology.stage_3_desc') }}</div>
      </div>
    </div>
  </div>
</template>
