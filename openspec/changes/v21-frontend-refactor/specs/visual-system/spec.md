# Capability: visual-system

## Goal

建立 V2.1 米白风格视觉系统：色板、阴影、圆角、字体、背景光晕、组件基础类。所有页面共享同一套视觉语言。

## Scope

### In Scope
- 三层色板：`canvas`（米白底，5 阶）/ `ink`（文字，5 阶）/ `accent`（主色，蓝色 5 阶）
- 状态色板：`good` / `warn` / `bad` / `info`
- 阴影层级：`shadow-card`（1px 近场 + 12px 中场 + 32px 远场）/ `shadow-elevated` / `shadow-floating`
- 圆角规范：`rounded-xl` (18px) / `rounded-2xl` (24px) / `rounded-3xl` (28px)
- 字体栈：苹方优先（macOS 灵动字形 + ss01 变体），回退到 Noto Sans CJK / 微软雅黑 / system-ui
- 数字精致化：`num-mono` 工具类启用 `tnum` 等宽 + `slashed-zero` + `lining-nums`
- 背景光晕：3 个超大柔光晕（85-100% 宽度，alpha 0.04-0.06，transparent 75%），scroll attachment 跟文档走
- 基础组件类：`panel` / `btn-primary` / `btn-outline` / `btn-ghost` / `btn-soft` / `chip-good` / `chip-warn` / `chip-bad` / `chip-info` / `chip-mute` / `link-pill` / `input` / `select`

### Out of Scope
- 暗色主题切换（保持纯白）
- 自定义主题（颜色由 spec 锁定）
- 动画时长定制（统一 150-200ms cubic-bezier）
- 国际化（保持中文 UI）

## API Changes

无后端 API 变更。

## Implementation

### 文件改动
- `tailwind.config.js`：扩展 theme.colors / theme.boxShadow / theme.borderRadius
- `src/style.css`：@layer base（body 字体 + 背景光晕） + @layer components（基础类） + @layer utilities（kpi-num / num-mono / link-pill）

### 验收标准
- 所有页面背景 = `#fbfbfd` + 3 段柔光晕
- 所有 panel = 白色 + 圆角 2xl + 三层阴影
- 所有按钮 = 圆角 + 渐变或纯色
- 所有数字 = 等宽 + slashed-zero（如果字体支持）
- 滚动时光晕跟着文档流（不是 fixed）
- build 通过，无 Tailwind class 警告
