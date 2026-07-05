# vue-i18n-integration（vue-i18n v9 集成 + 切换 UI）

## 目标

集成 vue-i18n v9 到现有 Vue 3 项目，建立中英 2 语言切换机制，导航栏右上角加 `中 | EN` 切换按钮，localStorage 持久化用户选择。

## 范围

**包含**：
- 装 `vue-i18n@^9.x` 依赖
- `frontend/src/i18n/` 目录新建（index.js + zh-CN.js + en-US.js）
- `main.js` 注入 createI18n（legacy: false + Composition API）
- 切换按钮组件（嵌入 App.vue 顶导右侧工具栏，K 用户头像前）
- `frontend/src/stores/locale.js`（pinia store + localStorage 同步）
- 1 个 smoke test（i18n 实例创建 + locale 切换响应式）

**不包含**：
- 视图文案改造（→ frontend-i18n-migration spec）
- 后端 error key 改造（→ backend-i18n-key spec）
- 3+ 语言支持
- Accept-Language 头判断
- 异步加载 locale

## 设计决策

### 决策 1: i18n 实例配置

```js
// frontend/src/i18n/index.js
import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN.js'
import enUS from './en-US.js'

const stored = typeof localStorage !== 'undefined'
  ? localStorage.getItem('locale')
  : null

export const i18n = createI18n({
  legacy: false,           // Composition API
  locale: stored || 'zh-CN',
  fallbackLocale: 'zh-CN', // 找不到 fallback 到中文
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})
```

### 决策 2: pinia store 监听 locale 变化

```js
// frontend/src/stores/locale.js
import { defineStore } from 'pinia'
import { useI18n } from 'vue-i18n'

export const useLocaleStore = defineStore('locale', () => {
  const { locale } = useI18n()
  
  function setLocale(newLocale) {
    locale.value = newLocale
    localStorage.setItem('locale', newLocale)
  }
  
  return { locale, setLocale }
})
```

### 决策 3: 切换按钮 UI

```vue
<!-- App.vue 顶导右侧工具栏（line 156-166 之间） -->
<div class="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-canvas-200/60 text-[11px] font-medium ml-1">
  <button @click="setLocale('zh-CN')" 
    :class="['px-1.5 py-0.5 rounded-full transition', 
      currentLocale === 'zh-CN' ? 'bg-white text-accent shadow-sm' : 'text-ink-500 hover:text-ink-700']">
    中
  </button>
  <span class="text-ink-300">|</span>
  <button @click="setLocale('en-US')" 
    :class="['px-1.5 py-0.5 rounded-full transition', 
      currentLocale === 'en-US' ? 'bg-white text-accent shadow-sm' : 'text-ink-500 hover:text-ink-700']">
    EN
  </button>
</div>
```

样式参考：用户原话"中英切换"，胶囊 toggle 是最直观的 2 语言控件；当前语言高亮（accent 色 + 阴影）。

### 决策 4: 启动时还原 locale

- main.js 注入 i18n 时，从 localStorage 读取（决定 1）
- 监听 locale 变化自动持久化（pinia store + watch）
- SSR 兼容：`typeof localStorage !== 'undefined'` 检查（虽然本项目是 SPA，但写防御代码无害）

## 验收标准

1. ✅ 装 `vue-i18n@^9.x`，`package.json` 出现依赖
2. ✅ `main.js` 注入 `app.use(i18n)`，无控制台报错
3. ✅ `frontend/src/i18n/index.js` 创建 i18n 实例，默认 locale = `zh-CN`
4. ✅ `frontend/src/i18n/zh-CN.js` + `en-US.js` 至少包含 `app.title` / `nav.dashboard` / `common.confirm` / `common.cancel` 4 个基础 key（占位 + 占位翻译）
5. ✅ 切换按钮渲染在 App.vue 顶导右侧（K 用户头像前）
6. ✅ 点击 `EN` → 全局所有 `$t('nav.dashboard')` 显示 "Dashboard"
7. ✅ 点击 `中` → 全局所有 `$t('nav.dashboard')` 显示 "总览"
8. ✅ 切换后刷新页面，locale 保持
9. ✅ vitest 1 个 smoke test 验证 i18n 实例创建 + locale 切换响应式
10. ✅ qa-frontend 全过（lint + build + vitest 33 + playwright 37 baseline）
11. ✅ qa-backend 265 passed baseline 不变

## 风险

- vue-i18n 9.x 与 Vue 3.5+ 兼容：官方支持
- bundle 增大：~30KB
- SSR 不支持：本项目 SPA 无影响
