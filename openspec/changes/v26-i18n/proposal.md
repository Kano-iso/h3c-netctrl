## Why

v2.5.0 P1 工程化收口已完成（265 单元测试 + 33 vitest + 37 playwright + 9 ops-toolkit 脚本），但整套 UI / 后端错误信息仍是中文单语。需求侧提到"想给项目加英文 UI 切换"——核心动机：

- 排错场景下，国际化社区（GitHub Issue / Stack Overflow）能直接看到英文截图/报错
- 个人项目未来可能开源 / 投稿，纯中文门槛高
- H3C 设备命令、log 关键词本身是英文，统一后对照方便

用户原话："在导航栏右上角加中英切换按钮"，"扫一遍全部项目的地方，做好中英的切换"，"也别漏了点"。

**驱动选择**：vue-i18n v9（Vue 3 官方推荐，集成最稳，社区成熟）+ 前端翻译 key 模式（后端返 i18n key，前端查表翻译，避免 3 容器跨语言协调）。

## What Changes

- **vue-i18n v9 集成**：装包 + main.js 注入 + createI18n + 持久化（localStorage）+ locale 切换响应式
- **导航栏右上角语言切换按钮**：App.vue 右侧工具栏加 `中 | EN` 切换器
- **全量前端 i18n 改造**：
  - 11 views（Dashboard / Devices / Interfaces / VLAN / CMDB / Backup / Batch / OpsTerminal / Logs / Topology / AIAssistant）
  - 10 components（ConfirmModal / DeviceFormModal / AssetEditModal / Ipv4AddressEditModal / VpnInstanceBindModal / BackupListModal / PageHeader / AppFooter / BackgroundTaskPanel / Select）
  - App.vue（侧边栏 groups + 顶导）
  - utils/status.js（在线/离线/告警状态文案）
  - api/index.js（axios 错误 toast 消息）
- **后端 APIResponse.error 改 i18n key**：routers/* 中所有 `error="设备不存在: id=..."` 改为 `error="device.not_found"` 等结构化 key
- **后端 i18n key 表**：`backend/app/i18n_keys.py` 集中维护 key → 描述映射（避免 router 内散落）
- **测试断言更新**：
  - vitest 33 case（5 组件 × 6 + 3 smoke）断言改为 i18n key 或英文 fallback
  - playwright 37 case 同步
  - 新增 i18n 切换测试（持久化 / 默认值 / 响应式）

## Capabilities

### New Capabilities

- `vue-i18n-integration`: vue-i18n v9 集成 + 持久化 + 切换 UI
- `backend-i18n-key`: 后端 APIResponse.error 改结构化 i18n key
- `frontend-i18n-migration`: 前端 11 views + 10 components + App + Footer 全量 i18n key 化

### Modified Capabilities

- 无（i18n 是纯增量能力，不修改现有 capability 语义）

## Impact

- **代码（新增 / 改造）**：
  - `frontend/src/i18n/`（新建，locale 文件目录）
  - `frontend/src/main.js`（注入 i18n）
  - `frontend/src/App.vue`（加切换按钮 + groups label/desc 改造）
  - `frontend/src/components/AppFooter.vue` + 其他 9 组件（中文 → $t()）
  - `frontend/src/views/*.vue` × 11（中文 → $t()）
  - `frontend/src/utils/status.js`（状态文案 $t()）
  - `frontend/src/api/index.js`（axios 错误 toast $t()）
  - `backend/app/i18n_keys.py`（新建，key 集中表）
  - `backend/app/routers/*.py` × 9（APIResponse.error 改 key）
  - `frontend/src/__tests__/*.spec.js`（vitest 断言）
  - `frontend/tests/e2e/*.spec.js`（playwright 断言）
  - `frontend/package.json`（加 vue-i18n 依赖）
  - `frontend/src/stores/locale.js`（新建，locale pinia store）
- **API**：APIResponse.error 字段值类型变化（中文 → i18n key 字符串），**BREAKING**（前端 toast 显示 + 后端日志阅读需适配）
- **依赖**：新增 `vue-i18n@^9.x`
- **文档**：
  - `docs/i18n-guide.md`（新建，翻译 key 命名规范 / 新增条目流程）
  - `VERSION-ROADMAP.md` §v2.6 章节
  - `README.md`（技术栈 + 功能概览 + 访问入口 同步）
  - `RELEASE-NOTES-v2.6.0.md`（新建，BREAKING 标注 APIResponse.error 字段类型变化）
- **测试 baseline**：
  - vitest 33 → 38+ case（+ 5 i18n 切换测试：默认 / 切换 / 持久化 / 响应式 / 边界）
  - playwright 37 → 42+ case（+ 5 i18n e2e：切换按钮可见 / 切换后文案变 / localStorage 持久化 / 后端 key 翻译 / fallback）
  - qa-backend 265 → 275+ passed（+ 10 后端 i18n key 映射测试）
- **用户体验**：
  - 中文用户：默认中文，无感（无变化）
  - 英文用户：右上角一键切英文，所有 UI + 后端错误自动变英文
  - 持久化：用户选择记 localStorage，刷新页面保持

## Non-Goals

- 不做多语言（仅中英 2 语言，3+ 语言留 v2.7+ 评估）
- 不做 i18n 异步加载（locale 文件 < 10KB 没必要 code-split）
- 不做基于 Accept-Language 头自动判断（仅 localStorage 持久化）
- 不做 RTL / 阿拉伯语（个人项目无需求）
- 不做 i18n key 提取自动化（用 grep 人工扫，工具后续评估）
- 不动 ops-toolkit 脚本（CLI 不需要 i18n）
- 不动 README / docs（文档保持中文，OpenSpec 流程文档一致）
