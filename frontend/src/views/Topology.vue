<script setup>
import PageHeader from '../components/PageHeader.vue'

// V2.1 阶段：拓扑视图尚未对接后端，预览版留作后续
const topology = { nodes: [], links: [] }
</script>

<template>
  <PageHeader title="拓扑视图" subtitle="LLDP 自动发现 · 网络拓扑可视化" badge="未来 · 预览">
    <template #actions>
      <span class="chip-info">PoC 演示</span>
    </template>
  </PageHeader>

  <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
    <div class="panel p-6">
      <div class="text-base font-semibold text-ink-900 mb-1">未来规划</div>
      <div class="text-xs text-ink-500 mb-5">通过 LLDP 协议自动发现邻居关系，渲染为可交互的网络拓扑图</div>

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
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-accent"></span><span class="text-ink-700">Spine 核心</span></div>
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-info"></span><span class="text-ink-700">Leaf 汇聚</span></div>
          <div class="flex items-center gap-2"><span class="size-1.5 rounded-full bg-ink-500"></span><span class="text-ink-700">Access 接入</span></div>
          <div class="flex items-center gap-2 pt-1.5 border-t border-canvas-300">
            <span class="size-1.5 rounded-full bg-good"></span><span class="text-ink-700">UP</span>
            <span class="size-1.5 rounded-full bg-bad ml-2"></span><span class="text-ink-700">DOWN</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">阶段 1</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">LLDP 自动发现</div>
        <div class="text-xs text-ink-700">通过 `display lldp neighbor` 定期探测，建立邻接表</div>
      </div>
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">阶段 2</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">拓扑渲染</div>
        <div class="text-xs text-ink-700">D3 / Cytoscape 渲染，支持拖拽、缩放、聚焦</div>
      </div>
      <div class="panel p-5">
        <div class="text-[10px] uppercase tracking-wider text-ink-500 mb-1.5 font-medium">阶段 3</div>
        <div class="text-sm font-semibold text-ink-900 mb-1">链路监控</div>
        <div class="text-xs text-ink-700">实时高亮告警链路，hover 显示端口流量</div>
      </div>
    </div>
  </div>
</template>
