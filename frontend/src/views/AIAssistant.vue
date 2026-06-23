<script setup>
import { ref, nextTick } from 'vue'
import PageHeader from '../components/PageHeader.vue'

const messages = ref([
  { role: 'assistant', text: '你好！我是 NetCtrl AI 助手。\n\n我可以帮你：\n• 解读设备配置（粘贴 `display current-configuration` 即可）\n• 分析接口/VLAN 状态\n• 给出故障排查建议\n• 起草配置变更命令\n\n（当前为 PoC 演示，所有回答均为模拟）' }
])
const input = ref('')
const thinking = ref(false)

const presets = [
  '为什么 Spine-01 G1/0/1 接口 down 了？',
  '帮我把 Leaf-01 的 G1/0/12 改成 trunk 允许 100 200',
  '解释一下 `display cpu-usage` 的输出',
  'Access-02 连不上 NETCONF，怎么排查？'
]

const send = async (text) => {
  if (!text.trim() || thinking.value) return
  const userText = text.trim()
  messages.value.push({ role: 'user', text: userText })
  input.value = ''
  thinking.value = true
  await new Promise(r => setTimeout(r, 1200))
  const responses = {
    '为什么 Spine-01 G1/0/1 接口 down 了？': `根据历史日志分析，Spine-01 的 G1/0/1 接口在 06-21 14:32 之后处于 down 状态。\n\n可能原因：\n1. **对端设备断电** - G1/0/1 连接到 Leaf-01 G1/0/1，请检查 Leaf-01 状态\n2. **线缆松动** - 检查物理链路指示灯\n3. **端口被关闭** - 在 Leaf-01 上执行:\n   display interface GigabitEthernet1/0/1\n   查看 link state\n\n建议先 ping Leaf-01 (192.168.100.11) 确认邻居可达。`,
    '帮我把 Leaf-01 的 G1/0/12 改成 trunk 允许 100 200': `好的，我会通过 NETCONF 下发：\n\n<config>\n  <Ifmgr>\n    <Interface>\n      <IfIndex>12</IfIndex>\n      <LinkType>trunk</LinkType>\n      <PVID>1</PVID>\n      <PermitVlanList>100,200</PermitVlanList>\n    </Interface>\n  </Ifmgr>\n</config>\n\n⚠️ 注意事项：\n- G1/0/12 当前是 access 100，切换会中断该口连接的业务\n- 建议先确认下行设备配置（trunk + 允许 100,200）\n- 是否要我也下发？回复 "确认" 即可。`,
    '解释一下 `display cpu-usage` 的输出': `这是 H3C 设备的 CPU 使用率命令：\n\nCPU utilization for five seconds: 23%; one minute: 18%; five minutes: 21%\nSystem is running well.\n\n**含义：**\n- **Five seconds** - 最近 5 秒的 CPU 平均使用率\n- **One minute** - 最近 1 分钟的平均使用率\n- **Five minutes** - 最近 5 分钟的平均使用率\n\n**判断标准：**\n- < 30% — 正常\n- 30-70% — 关注\n- > 70% — 告警`,
    'Access-02 连不上 NETCONF，怎么排查？': `排查步骤：\n\n1. **物理层**\n   ping 192.168.100.22\n\n2. **端口检查**\n   nc -zv 192.168.100.22 830\n\n3. **NETCONF 服务确认**\n   ssh admin@192.168.100.22 'display netconf service status'\n\n4. **认证**\n   - 确认用户名密码无误\n\nAccess-02 当前状态是 **offline**，建议先检查物理链路和电源。`
  }
  messages.value.push({ role: 'assistant', text: responses[userText] || '我还在学习中，可以试试上面的预设问题。' })
  thinking.value = false
  nextTick(() => { container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' }) })
}

const container = ref(null)
</script>

<template>
  <PageHeader title="AI 助手" subtitle="自然语言运维 · 智能排障 · 配置生成" badge="未来 · 预览">
    <template #actions>
      <span class="chip-info">PoC 演示</span>
    </template>
  </PageHeader>

  <div class="max-w-4xl mx-auto px-6 pb-16">
    <div class="panel flex flex-col h-[calc(100vh-220px)] overflow-hidden">
      <div class="px-5 py-3 border-b border-canvas-300 flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="size-8 rounded-lg bg-gradient-to-br from-accent-400 to-info flex items-center justify-center">
            <svg class="size-4 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.5 5L18 8.5 13.5 10 12 15l-1.5-5L6 8.5 10.5 7z"/></svg>
          </div>
          <div>
            <div class="text-sm font-semibold text-ink-900">NetCtrl AI</div>
            <div class="text-[10px] text-ink-500">基于运维知识库 · 暂未对接大模型</div>
          </div>
        </div>
        <button class="btn-soft !text-xs">新对话</button>
      </div>

      <div ref="container" class="flex-1 overflow-y-auto p-5 space-y-4 bg-canvas-100">
        <div v-for="(m, i) in messages" :key="i" :class="['flex gap-3', m.role === 'user' ? 'flex-row-reverse' : '']">
          <div :class="['size-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0',
            m.role === 'user' ? 'bg-accent text-white' : 'bg-gradient-to-br from-accent-400 to-accent-700 text-white']">
            {{ m.role === 'user' ? 'K' : 'AI' }}
          </div>
          <div :class="['rounded-2xl px-4 py-2.5 text-sm leading-relaxed max-w-[80%] whitespace-pre-wrap',
            m.role === 'user' ? 'bg-accent text-white' : 'bg-white ring-1 ring-canvas-300 text-ink-900']">
            {{ m.text }}
          </div>
        </div>
        <div v-if="thinking" class="flex gap-3">
          <div class="size-7 rounded-full bg-gradient-to-br from-accent-400 to-accent-700 flex items-center justify-center text-xs font-semibold shrink-0 text-white">AI</div>
          <div class="rounded-2xl bg-white ring-1 ring-canvas-300 px-4 py-3 text-sm text-ink-700 flex items-center gap-1.5">
            <span class="size-1.5 rounded-full bg-accent animate-pulse" />
            <span class="size-1.5 rounded-full bg-accent animate-pulse" style="animation-delay: .15s" />
            <span class="size-1.5 rounded-full bg-accent animate-pulse" style="animation-delay: .3s" />
            <span class="ml-2 text-[10px] text-ink-500">思考中</span>
          </div>
        </div>
      </div>

      <div class="border-t border-canvas-300 p-4">
        <div class="flex flex-wrap gap-1.5 mb-3">
          <button v-for="p in presets" :key="p" @click="send(p)" class="chip-mute hover:bg-canvas-300 !text-[10px]">{{ p }}</button>
        </div>
        <div class="flex items-end gap-2">
          <textarea
            v-model="input"
            @keyup.enter.exact.prevent="send(input)"
            rows="2"
            placeholder="问点什么…(Enter 发送)"
            class="input flex-1 resize-none"
          />
          <button @click="send(input)" :disabled="!input.trim() || thinking" class="btn-primary disabled:opacity-50">
            <svg class="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            发送
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
