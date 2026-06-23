<template>
  <footer class="mt-16 border-t border-canvas-300/70 bg-canvas-50/60 backdrop-blur-sm">
    <div class="max-w-[1200px] mx-auto px-8 py-14">
      <!-- 上：4 列 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-10 mb-10">
        <!-- 1. Logo + 介绍 -->
        <div class="col-span-2 md:col-span-1">
          <div class="flex items-center gap-2 mb-3">
            <div class="size-7 rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 flex items-center justify-center">
              <svg class="size-3.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M4 6h16M4 12h16M4 18h10" stroke-linecap="round"/>
                <circle cx="20" cy="18" r="1.5" fill="currentColor"/>
              </svg>
            </div>
            <span class="text-sm font-semibold tracking-tight text-ink-900">H3C NetCtrl</span>
          </div>
          <p class="text-xs text-ink-500 leading-relaxed max-w-xs">
            基于 NETCONF 的轻量 H3C 交换机 Web 管控平台。命令派发、接口联动、资产盘点、批量操作，一个界面完成日常网络运维。
          </p>
          <!-- 社交图标 -->
          <div class="flex items-center gap-2 mt-4">
            <a href="https://github.com/" target="_blank" rel="noopener" class="size-8 rounded-full bg-canvas-200 hover:bg-canvas-300 flex items-center justify-center text-ink-700 transition" aria-label="GitHub">
              <svg class="size-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .3a12 12 0 0 0-3.79 23.4c.6.1.82-.26.82-.58v-2.16c-3.34.72-4.04-1.42-4.04-1.42-.55-1.39-1.34-1.76-1.34-1.76-1.09-.74.08-.73.08-.73 1.2.09 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .1-.78.42-1.31.76-1.61-2.66-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.11-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.65 1.66.24 2.88.12 3.18a4.65 4.65 0 0 1 1.23 3.22c0 4.61-2.81 5.62-5.48 5.92.43.37.81 1.1.81 2.22v3.29c0 .32.22.69.83.57A12 12 0 0 0 12 .3"/></svg>
            </a>
            <a href="#" class="size-8 rounded-full bg-canvas-200 hover:bg-canvas-300 flex items-center justify-center text-ink-700 transition" aria-label="文档">
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>
            </a>
            <a href="#" class="size-8 rounded-full bg-canvas-200 hover:bg-canvas-300 flex items-center justify-center text-ink-700 transition" aria-label="邮件">
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/></svg>
            </a>
          </div>
        </div>

        <!-- 2. 产品 -->
        <div>
          <div class="text-[11px] font-semibold text-ink-900 uppercase tracking-wider mb-3">产品</div>
          <ul class="space-y-2 text-xs text-ink-600">
            <li><a class="hover:text-accent transition" href="#/devices">设备管理</a></li>
            <li><a class="hover:text-accent transition" href="#/ops">运维终端</a></li>
            <li><a class="hover:text-accent transition" href="#/interfaces">接口配置</a></li>
            <li><a class="hover:text-accent transition" href="#/batch">批量操作</a></li>
            <li><a class="hover:text-accent transition" href="#/cmdb">CMDB 资产</a></li>
          </ul>
        </div>

        <!-- 3. 资源 -->
        <div>
          <div class="text-[11px] font-semibold text-ink-900 uppercase tracking-wider mb-3">资源</div>
          <ul class="space-y-2 text-xs text-ink-600">
            <li><a class="hover:text-accent transition" href="#/logs">操作日志</a></li>
            <li><a class="hover:text-accent transition" href="#/backup">备份 / 回滚</a></li>
            <li><a class="hover:text-accent transition" href="#/topology">拓扑视图</a></li>
            <li><a class="hover:text-accent transition" href="#">技术文档</a></li>
            <li><a class="hover:text-accent transition" href="#">Changelog</a></li>
          </ul>
        </div>

        <!-- 4. 关于 -->
        <div>
          <div class="text-[11px] font-semibold text-ink-900 uppercase tracking-wider mb-3">关于</div>
          <ul class="space-y-2 text-xs text-ink-600">
            <li><a class="hover:text-accent transition" href="#">项目简介</a></li>
            <li><a class="hover:text-accent transition" href="#">技术栈</a></li>
            <li><a class="hover:text-accent transition" href="#">开发规范</a></li>
            <li><a class="hover:text-accent transition" href="#">MIT License</a></li>
            <li><a class="hover:text-accent transition" href="#">联系作者</a></li>
          </ul>
        </div>
      </div>

      <!-- 下：版权行 -->
      <div class="pt-6 border-t border-canvas-300/70 flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-500">
        <div>© 2026 H3C NetCtrl · 个人学习项目</div>
        <div class="flex items-center gap-4">
          <span class="flex items-center gap-1.5">
            <span class="size-1.5 rounded-full bg-good animate-pulse"></span>
            <span class="num-mono">v2.0.0</span>
          </span>
          <span>Built with Vue 3 · FastAPI · NETCONF</span>
        </div>
      </div>
    </div>
  </footer>
</template>
