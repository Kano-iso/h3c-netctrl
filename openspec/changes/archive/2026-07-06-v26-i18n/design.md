## Context

v2.5.0 P1 工程化收口后，3 容器架构（ctrl/config/data）+ 测试体系（vitest 33 + playwright 37）已稳定。但 UI 文案和后端错误信息仍为中文单语，影响：
- 国际化社区沟通（GitHub Issue / 截图）
- 排错时与英文文档对照
- 项目未来开源 / 投稿准备

用户原话："导航栏右上角加中英切换按钮"，"扫一遍全部项目的地方"，"别漏了点"。

**干系人**：
- 开发者：日常开发切到英文可与英文文档对照
- 运维：英文用户能直接看懂界面（减少培训成本）
- 国际化贡献者：能直接读懂项目

**前置依赖**：
- v2.5.0 split 模式已稳定（265 单元 baseline） ✅
- vitest + playwright 自动化测试已就位 ✅
- App.vue 顶导有右侧工具栏，可加切换按钮 ✅

## Goals / Non-Goals

**Goals:**

- vue-i18n v9 集成（中英 2 语言，足够个人项目）
- 导航栏右上角 `中 | EN` 切换按钮（位置用户已定）
- 11 views + 10 components + App + AppFooter 全量 i18n（用户要求"别漏了点"）
- localStorage 持久化（用户切换后刷新保持）
- 默认中文（不影响现有用户体验）
- 后端 APIResponse.error 改 i18n key（前端统一翻译）
- vitest + playwright 断言同步更新（保证测试继续保护）
- 全量测试 baseline 通过：qa-backend 275+ / vitest 38+ / playwright 42+

**Non-Goals:**

- 不做 3+ 语言（个人项目，2 语言够用）
- 不做 Accept-Language 头自动判断（仅 localStorage 持久化）
- 不做 i18n key 提取自动化工具（grep 人工扫）
- 不做 RTL / 阿拉伯语（无需求）
- 不动 ops-toolkit 脚本（CLI 无 i18n 需求）
- 不动 README / docs 文档（保持中文，OpenSpec 一致）
- 不重写 APIResponse schema（仅 error 字段值类型变化）

## Decisions

### 决策 1: vue-i18n v9 集成模式 — Composition API + reactive locale

**方案**：
- 装 `vue-i18n@^9.x`
- `main.js` 用 `createI18n({ legacy: false, locale: 'zh-CN', fallbackLocale: 'zh-CN', messages: { 'zh-CN': {...}, 'en-US': {...} } })`
- 组合式 API：`const { t, locale } = useI18n()`
- 模板中：`{{ $t('key.path') }}` 或 `:placeholder="$t('key.path')"`

**替代方案**：
- Options API（`legacy: true`）：Vue 3 项目不推荐
- 自己写轻量 i18n：5 个文件 + 1 store，300 行内可完成，但 vue-i18n 已是事实标准
- i18next：通用方案，但 Vue 3 集成不如 vue-i18n 原生

**理由**：vue-i18n v9 是 Vue 3 官方推荐，与现有 Vue 3 + Vite + Pinia 生态一致；社区成熟文档多。

### 决策 2: 持久化策略 — localStorage + 启动时还原

**方案**：
- 用户切换语言时 `localStorage.setItem('locale', 'en-US')`
- `main.js` 启动时 `const stored = localStorage.getItem('locale'); locale.value = stored || 'zh-CN'`
- 监听 locale 变化自动持久化（pinia store 或 watch）

**替代方案**：
- sessionStorage：刷新页面后丢失
- Cookie：需后端配合，3 容器架构不必要
- 仅内存：刷新页面回到默认中文（差体验）

**理由**：localStorage 是浏览器最通用的持久化方案，无依赖，刷新即保持。

### 决策 3: 切换按钮位置与样式 — 顶导右侧工具栏

**方案**：
- 位置：App.vue line 156-166 `<!-- 右侧工具 -->` 区块，在 K 用户头像前
- 样式：胶囊式 toggle（`中 | EN`），当前语言高亮（accent 色）
- 切换：点击立即切换（无确认弹窗）

**替代方案**：
- 侧边栏底部：用户原话"右上角"，不符合
- 下拉选择器（3 选项）：v2.6 仅 2 语言，下拉过重
- 顶导最右侧全局图标：i18n 习惯位置是 header，但需图标认知

**理由**：用户原话"导航栏右上角"，明确位置；胶囊 toggle 是最直观的 2 语言切换控件。

### 决策 4: i18n key 命名规范 — 分层 dot 命名

**方案**：
- 格式：`模块.子模块.具体含义`，如 `device.list.title`、`common.confirm`、`error.device_not_found`
- 模块前缀：`common.*` / `device.*` / `interface.*` / `vlan.*` / `cmdb.*` / `backup.*` / `batch.*` / `ops.*` / `log.*` / `topology.*` / `ai.*` / `nav.*` / `footer.*` / `error.*` / `app.*`
- 状态类：`*_status.online` / `*_status.offline` / `*_status.error`
- 全部小写 + snake_case（与 Python 后端风格一致）

**替代方案**：
- 嵌套 JSON（`device.list.title` → `{device: {list: {title: ...}}}`）：vue-i18n 两种都支持，扁平更直观
- 大写开头（`Device.List.Title`）：不一致
- 路径式（`device/list/title`）：JSON 嵌套路径也行，但 dot 更通用

**理由**：dot 命名是 vue-i18n 官方推荐，与 JavaScript 对象访问一致，可读性高。

### 决策 5: 后端 APIResponse.error 改 i18n key — 结构化 key + 透传参数

**方案**：
- APIResponse.error 字段从 `"设备不存在: id=123"` 改为 `"device.not_found"`，参数用占位符传递（如 `error_params: {id: 123}`）
- 或保留单字符串格式：APIResponse 加可选字段 `error_key: "device.not_found"` + `error_params: {id: 123}` + 原 `error` 字段保留为已翻译文案（兼容）
- **采用第二种**（兼容性最好）：原 `error` 字段保留中文（运维日志友好），新加 `error_key` 字段供前端 i18n 翻译

**替代方案**：
- 直接改 `error` 字段值类型（中文 → key）：**BREAKING**，破坏日志和现有前端
- Accept-Language 头翻译：3 容器架构复杂
- 不改后端：仅前端 UI 翻译，错误仍中文（用户切到英文看到混合）

**理由**：加 `error_key` + `error_params` 字段是非破坏性扩展，原 `error` 字段保留兼容；前端用 `error_key` 查 i18n 表，没找到 fallback 到 `error`。

### 决策 6: 翻译条目集中维护 — i18n 目录结构

**方案**：
```
frontend/src/i18n/
├── index.js           # i18n 实例 + locale store 绑定
├── zh-CN.js           # 中文（默认 + 全量）
└── en-US.js           # 英文（次要 + 全量）
```

- 中文文件作为基础（与现有中文 UI 一一对应）
- 英文文件从中文翻译，要求语义一致（不创造新文案）
- 启动时校验：zh-CN 和 en-US key 数量一致（CI 校验）

**替代方案**：
- 单文件混编（`messages.js` 包含所有语言）：大文件难维护
- 按模块拆（device/zh-CN.js + device/en-US.js）：过度拆分
- JSON 文件：vue-i18n 支持，但 JS 导出更灵活

**理由**：2 语言 × 单一入口最简单，文件大小可控（预计 zh-CN ~30KB, en-US ~25KB）。

### 决策 7: 测试断言更新策略 — i18n key 断言 + 英文 fallback

**方案**：
- vitest：组件渲染后断言 `wrapper.text()` 包含 i18n key 翻译后的中文（默认 locale）或英文（mock locale）
- playwright：默认 locale 测中文，切到英文后断言英文文本出现
- 新增 i18n 切换专项测试：5 case × 2（vitest + playwright）
- 不动现有 e2e 用例结构（`expect(page.getByText('设备')).toBeVisible()` → 改成 `expect(page.getByText('设备')).toBeVisible()` 即可，默认中文不变）

**替代方案**：
- 全部改英文断言：默认 locale 测英文不直观
- 用 data-testid 替代文本断言：现有测试没 data-testid，全改成本高
- 跳过 i18n 测试：失去切换正确性保护

**理由**：默认 locale 不变（中文），现有断言基本无需改；只需新增 i18n 切换专项测试 + 后端 key 翻译测试。

## Risks / Trade-offs

- **后端 error 字段不变，前端必须用 error_key**：依赖前端接入，新增组件忘了用 key → 用户看到混合。缓解：qa-frontend 加 lint 规则（error 必须配合 error_key）
- **vue-i18n 增加 ~30KB bundle**：可接受
- **全量翻译工作量大（11 views + 10 components）**：用户已确认范围，分 8-10 个 task 逐步推进，每 task 1 commit
- **英文翻译质量**：个人项目非专业翻译，语义准确即可；写 i18n-guide.md 标注风格（不创造新文案）
- **后端 error_key 未覆盖场景**：fallback 到原 error 中文，UI 看到混合 → 加全局 fallback 提示
- **vitest + playwright 同步更新测试**：必须保证 i18n 切换后旧断言仍能工作 → 默认中文不变，新加英文断言即可

## Migration Plan

按 task 粒度 = 1 commit 分阶段：

1. **Task 1 (vue-i18n-integration 骨架)**：装包 + main.js 注入 + i18n/index.js + locales 占位文件 + 1 个 smoke test
2. **Task 2 (locale 切换 UI)**：App.vue 顶导右侧加 `中 | EN` 切换按钮 + pinia store + localStorage 持久化
3. **Task 3 (App.vue + AppFooter i18n)**：groups label/desc + 顶导 + footer 4 列链接全量 $t()
4. **Task 4 (utils/status.js + api/index.js)**：状态文案 + axios 错误 toast $t()
5. **Task 5 (Dashboard + Devices + Interfaces i18n)**：3 个核心 view
6. **Task 6 (VLAN + CMDB + Backup i18n)**：3 个业务 view
7. **Task 7 (Batch + OpsTerminal + Logs + Topology + AIAssistant i18n)**：5 个次要 view
8. **Task 8 (10 components i18n)**：所有 component
9. **Task 9 (后端 i18n_key + APIResponse 扩展)**：backend/app/i18n_keys.py + routers/* 改 error_key + 后端 10 单测
10. **Task 10 (vitest 断言更新 + 5 i18n 测试)**：33 → 38+ case
11. **Task 11 (playwright 断言更新 + 5 i18n e2e)**：37 → 42+ case
12. **Task 12 (发版闭环)**：archive + RELEASE-NOTES + VERSION-ROADMAP §v2.6 + README 同步

**回退策略**：
- 每个 task 独立 commit，可单独 revert
- vue-i18n 集成失败：删除 main.js 注入 + 切换按钮，UI 回到原中文
- 后端 error_key 失败：APIResponse 兼容原 error 字段，前端 fallback 到 error 字符串

## Open Questions

- i18n key 是否需要 CI 校验（zh-CN 和 en-US 数量一致）？建议加 lint 脚本（package.json + lint step）
- 后端 i18n key 表是 1 个 dict 还是按模块拆？建议 1 个 dict（< 200 key）
- 错误消息中的占位符（如 `id={device_id}`）如何在 i18n 中处理？建议用 vue-i18n 的命名占位符 `{id}`
