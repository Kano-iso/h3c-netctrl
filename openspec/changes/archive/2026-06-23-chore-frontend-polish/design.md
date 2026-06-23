## Context

发布前用户反馈 3 类前端小问题（运维终端下拉被遮挡、Select 三段式显示拥挤、字体栈不完整），已在 commit 4532232 之后追加修复但未走 OpenSpec 流程。本 change 补建归档，确立：

- PageHeader z-index 分层（装饰 -z-0、内容 z-10、actions z-20）
- Select 触发器 / 选项内边距与三段式分布微调
- style.css monospace 字体栈前置
- 3 个 view 文件 import `utils/status.js` 辅助函数

## Goals / Non-Goals

**Goals:**
- 让所有带 `slot="actions"` 的下拉菜单在 PageHeader 中可正常溢出显示
- Select 触发器在宽度有限时，三段（label / sub / status）有合理截断 + 视觉分隔
- 中英文 / IP / 数字混排时统一走运维终端同款 mono 栈
- view 层不再各自内联 status 颜色函数，统一调用 `utils/status.js`

**Non-Goals:**
- 不引入新组件 / 新依赖
- 不调整状态字段映射规则（已在 `feat(frontend): 字体统一 + 自定义 Select 组件 + 状态显示中文化` 落地）
- 不改后端 API / 数据库

## Decisions

### 1. PageHeader 用 z-index 分层替代 overflow-hidden

- **选择**：去掉 `overflow-hidden` 父容器，改用 z-index 分层
  - 装饰渐变 `-z-0`（放底层）
  - 内容容器 `z-10`（中间层）
  - actions 容器 `z-20`（最上层，让 Select 绝对定位下拉溢出可见）
- **理由**：`overflow-hidden` 会裁剪所有子元素，包括 `position: absolute` 的下拉菜单。直接去掉是最简解，但需要补 z-index 防止装饰元素压到内容
- **替代**：给 PageHeader 加 `position: relative` + `overflow: visible`（默认就是 visible，等同去掉 hidden）。但单独去 hidden 仍可能有装饰元素压内容的风险，所以同时加 z-index

### 2. Select 触发器内边距 pl-3 / pr-2

- **选择**：`px-3.5` → `pl-3 pr-2`
- **理由**：右侧要容纳下拉箭头 + 装饰条，需要更紧凑的右内边距；左侧保留 pl-3 给 label 文字呼吸空间
- **替代**：保持 px-3.5 调整其他位置。评估后改右内边距改动最小

### 3. status chip ml-auto

- **选择**：状态 chip 加 `ml-auto` 自动推到右侧
- **理由**：label / sub 默认靠左、status chip 视觉上更靠右，三段式分布更清晰
- **替代**：用 grid 3 列固定分布。改动大且收益小

### 4. monospace 字体栈前置

- **选择**：font-family 把 mono 栈（Menlo / Consolas / Cascadia Code / JetBrains Mono / Fira Code）放在中文字体**之前**
- **理由**：英文 / 数字 / IP 在 mono 栈下视觉一致，与运维终端同款；中文回退到 PingFang / 思源
- **替代**：分开 body 与 .font-mono 两套。body 是 mixed content，分不开；放 mono 在前即可让英文 / 数字走 mono，中文仍走中文栈

### 5. view 层 import status utils

- **选择**：删除内联的 `statusChip` 箭头函数，直接 import `getStatusChip` / `getStatusLabel`
- **理由**：与 `feat(frontend): 字体统一 + 自定义 Select 组件 + 状态显示中文化`（commit 4532232）保持一致，避免重复逻辑

## Risks / Trade-offs

- **风险 1**：去掉 PageHeader `overflow-hidden` 后，装饰渐变可能溢出到外部边界 → **缓解**：装饰元素已加 `-z-0` 放底层，且 `absolute` 定位不影响父容器布局
- **风险 2**：monospace 栈前置后，中文 + 数字混排的对齐可能微调 → **缓解**：浏览器的 `font-family` 栈会按字符类型自动选 fallback，中文仍走 PingFang/思源，肉眼无明显差异（用户已确认）
- **风险 3**：Select 触发器宽度变窄时 status chip `ml-auto` 可能挤压 sub label → **缓解**：sub label 已加 `truncate max-w-[8rem]`，超长会截断不挤压
