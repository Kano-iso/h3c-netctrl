# Capability: content-width-control

## Goal

统一所有 view 的内容区宽度为 `max-w-[1200px]`，让大屏用户视觉聚焦，避免内容"摊开"导致松散感。

## Scope

### In Scope
- 统一应用 `max-w-[1200px] mx-auto px-8` 容器
- 应用范围：
  - `src/App.vue`（顶 nav 容器）
  - `src/components/PageHeader.vue`（页面标题）
  - `src/components/AppFooter.vue`（Footer 容器）
  - 9 个 view（Dashboard / Devices / OpsTerminal / Interfaces / Batch / CMDB / Logs / Backup / Topology / AI）
- 移除旧 `max-w-7xl` (1280px) 和 `max-w-[1440px]` (1440px)

### Out of Scope
- 内容区内 component 自身的 max-w（KPI 卡片 / 表格按需调整）
- 移动端断点（PC 优先）
- 用户自定义宽度

## API Changes

无后端 API 变更。

## Implementation

### 文件改动
- 全部 12 个文件批量替换 `max-w-7xl` → `max-w-[1200px]`，`max-w-[1440px]` → `max-w-[1200px]`
- 同步调整 `px-6` → `px-8`（如未设置）

### 验收标准
- 任何 view 滚动时左右两侧留白一致
- 1920px / 1440px / 1280px 三种屏幕宽度下内容区都在 1200px 内居中
- Dashboard 4 个 KPI 卡片在 1200px 内显示完整、不溢出
- build 通过
