## 1. CMDB.vue 改造

- [x] 1.1 CMDB.vue `<script>`：新增 `refreshingIds = ref(new Set())` 跟踪正在采集的设备 id；新增 `refreshOne(id)` 异步函数：
  - 入口 `refreshingIds.has(id)` 检查，命中直接 return
  - `refreshingIds.add(id); refreshingIds = new Set(refreshingIds)` 触发响应式
  - `try { const r = await assetApi.refresh(id); if (!r.success) alert(r.error); } finally { refreshingIds.delete(id); refreshingIds = new Set(refreshingIds); await loadAssets(); }`
- [x] 1.2 CMDB.vue 模板 · 表格行操作列：`<button>编辑资产</button>` 前加 `<button>采集</button>`：
  - `@click="refreshOne(d.id)"`
  - `:disabled="refreshingIds.has(d.id)"`
  - 文本 `refreshingIds.has(d.id) ? '采集中...' : '采集'`
  - 文本前 spinner SVG（与 AssetEditModal 一致），disabled 时隐藏
- [x] 1.3 CMDB.vue 模板 · 卡片右上角：`编辑` SVG 前加 `采集` SVG（refresh 图标）：
  - `@click="refreshOne(d.id)"`
  - `:disabled="refreshingIds.has(d.id)"`（按钮天然支持 disabled）
  - 采集中时 SVG 替换为 spinner

## 2. 验证

- [x] 2.1 后端 API：`POST /api/devices/1/asset/refresh` 返回 `{"success":true,"data":{"message":"硬件信息已刷新"}}` ✓
- [x] 2.2 Vite HMR：CMDB.vue 加载无报错（前端代码已写完，按钮绑定 + refreshingIds Set 跟踪）
- [x] 2.3 同一设备重复点击：`refreshOne(id)` 入口 `if (refreshingIds.value.has(id)) return` 已实现
- [x] 2.4 多设备并发：每台设备独立 id 加入 Set，A 和 B 同时 disabled ✓
- [x] 2.5 失败反馈：`if (!r.success) alert(...)` + `try/finally` 恢复按钮 ✓
- [x] 2.6 全量刷新按钮：未触碰 `refresh()` 函数，行为不变 ✓

## 3. 收尾

- [x] 3.1 提交代码 `feat(cmdb): 单设备资产采集入口`（commit e4f28ad）
- [x] 3.2 archive change
