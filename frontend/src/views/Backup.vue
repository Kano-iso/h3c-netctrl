<script setup>
import { ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'

const showDiff = ref(false)

// V2.1 阶段：配置备份 / 回滚尚未对接后端，预览版留作后续
const backupHistory = []
</script>

<template>
  <PageHeader title="配置备份 / 回滚" subtitle="定时备份 · Diff 对比 · 一键回滚" badge="未来 · 预览">
    <template #actions>
      <button class="btn-primary">
        <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 14l-7 7-7-7M12 21V3"/></svg>
        立即备份全部
      </button>
    </template>
  </PageHeader>

  <div class="max-w-[1200px] mx-auto px-8 pb-16 space-y-4">
    <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
      <div class="panel p-5">
        <div class="section-title">备份总数</div>
        <div class="kpi-num mt-2">{{ backupHistory.length }}</div>
      </div>
      <div class="panel p-5">
        <div class="section-title">今日备份</div>
        <div class="kpi-num mt-2">4</div>
      </div>
      <div class="panel p-5">
        <div class="section-title">占用空间</div>
        <div class="kpi-num mt-2">23 KB</div>
      </div>
      <div class="panel p-5">
        <div class="section-title">下次定时</div>
        <div class="kpi-num mt-2">02:00</div>
      </div>
    </div>

    <div class="panel">
      <div class="px-5 py-3 border-b border-canvas-300 flex items-center justify-between">
        <div class="text-sm font-semibold text-ink-900">备份历史</div>
        <div class="text-xs text-ink-500">最近 6 条</div>
      </div>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-[11px] text-ink-500 uppercase tracking-wider border-b border-canvas-300">
            <th class="px-4 py-2.5 text-left font-medium">设备</th>
            <th class="px-4 py-2.5 text-left font-medium">备份时间</th>
            <th class="px-4 py-2.5 text-left font-medium">大小</th>
            <th class="px-4 py-2.5 text-left font-medium">备注</th>
            <th class="px-4 py-2.5 text-right font-medium w-44">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-canvas-300">
          <tr v-for="b in backupHistory" :key="b.id" class="hover:bg-canvas-100 transition">
            <td class="px-4 py-3 text-sm text-ink-900">{{ b.device }}</td>
            <td class="px-4 py-3 text-xs font-mono text-ink-700">{{ b.time }}</td>
            <td class="px-4 py-3 text-xs font-mono text-ink-700">{{ b.size }}</td>
            <td class="px-4 py-3 text-xs text-ink-700">{{ b.note }}</td>
            <td class="px-4 py-3 text-right">
              <button @click="showDiff = true" class="btn-soft !text-xs !px-3 !py-1">查看</button>
              <button @click="showDiff = true" class="btn-soft !text-xs !px-3 !py-1">Diff</button>
              <button class="btn-soft !text-xs !px-3 !py-1 text-bad">回滚</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="panel p-6">
        <div class="text-base font-semibold text-ink-900 mb-3">实现思路</div>
        <ul class="text-xs text-ink-700 space-y-2">
          <li class="flex gap-2"><span class="text-accent">▸</span> 定时执行 `display current-configuration` 保存</li>
          <li class="flex gap-2"><span class="text-accent">▸</span> SQLite 存索引，文件存原始配置</li>
          <li class="flex gap-2"><span class="text-accent">▸</span> 变更前自动备份到 `pre-change-{timestamp}`</li>
          <li class="flex gap-2"><span class="text-accent">▸</span> diff 算法用 `diff-match-patch` 库</li>
        </ul>
      </div>
      <div class="panel p-6">
        <div class="text-base font-semibold text-ink-900 mb-3">安全机制</div>
        <ul class="text-xs text-ink-700 space-y-2">
          <li class="flex gap-2"><span class="text-good">●</span> 回滚操作必须二次确认</li>
          <li class="flex gap-2"><span class="text-good">●</span> 受保护设备回滚需 force=true</li>
          <li class="flex gap-2"><span class="text-good">●</span> 回滚失败自动尝试回滚自身</li>
          <li class="flex gap-2"><span class="text-good">●</span> 所有回滚操作记入审计日志</li>
        </ul>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <Transition name="modal">
      <div v-if="showDiff" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/40 backdrop-blur-sm" @click.self="showDiff = false">
        <div class="panel w-full max-w-5xl p-6 max-h-[85vh] flex flex-col">
          <div class="flex items-center justify-between mb-4">
            <div>
              <div class="text-base font-semibold text-ink-900">配置 Diff</div>
              <div class="text-xs text-ink-500 font-mono">Spine-01 · 2026-06-21 16:42:11 vs 当前</div>
            </div>
            <button @click="showDiff = false" class="btn-soft !p-1.5">✕</button>
          </div>

          <div class="grid grid-cols-2 gap-3 flex-1 overflow-hidden">
            <div class="flex flex-col rounded-xl bg-canvas-200 ring-1 ring-canvas-300 overflow-hidden">
              <div class="px-3 py-2 text-[10px] text-ink-500 uppercase tracking-wider border-b border-canvas-300 font-medium">备份版本</div>
              <pre class="flex-1 overflow-auto p-4 text-[11px] font-mono text-ink-900 whitespace-pre">interface GigabitEthernet1/0/1
  port link-mode bridge
  port link-type trunk
  port trunk permit vlan 1 10 20 30 100 200</pre>
            </div>
            <div class="flex flex-col rounded-xl bg-canvas-200 ring-1 ring-canvas-300 overflow-hidden">
              <div class="px-3 py-2 text-[10px] text-ink-500 uppercase tracking-wider border-b border-canvas-300 font-medium">当前配置</div>
              <pre class="flex-1 overflow-auto p-4 text-[11px] font-mono whitespace-pre text-ink-900">interface GigabitEthernet1/0/1
  port link-mode bridge
  port link-type trunk
<span class="text-good">+ port trunk permit vlan 1 10 20 30 100 200 300</span>
<span class="text-good">+</span>
<span class="text-good">+interface GigabitEthernet1/0/12</span>
<span class="text-good">+ port link-mode bridge</span>
<span class="text-good">+ port link-type access</span>
<span class="text-good">+ port access vlan 200</span></pre>
            </div>
          </div>

          <div class="flex justify-end gap-2 mt-5">
            <button @click="showDiff = false" class="btn-ghost">关闭</button>
            <button class="btn-primary !bg-bad hover:!bg-red-600">回滚到该备份</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.modal-enter-active, .modal-leave-active { transition: opacity .2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
