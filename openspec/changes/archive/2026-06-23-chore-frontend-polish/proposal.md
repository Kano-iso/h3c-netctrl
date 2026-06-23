## Why

发布前小 bug 修复未走 OpenSpec 流程（历史遗留），现在补建 change 归档，规范追溯链路。本次涉及 6 个前端文件、3 类问题：

1. **运维终端下拉菜单被遮挡**（PageHeader overflow-hidden 裁剪问题）
2. **设备下拉三段式显示拥挤**（Select.vue 触发器 / 选项布局优化）
3. **字体栈不完整**（style.css 缺少 monospace 兜底，与运维终端风格不一致）

此外还有 3 个 view 文件同步引入 `utils/status.js` 的 `getStatusLabel` / `getStatusChip` 辅助函数，统一状态显示。

## What Changes

- `frontend/src/components/PageHeader.vue`：去掉 `overflow-hidden`、装饰渐变改 `-z-0` 放底层、内容容器 `z-10`、actions 区域 `z-20`，让 Select 绝对定位下拉菜单可正常溢出
- `frontend/src/components/Select.vue`：触发器内边距微调（`px-3.5` → `pl-3 pr-2`），三项元素独立 `truncate min-w-0`、状态 chip `ml-auto` 右推、加入 `h-5 w-px bg-canvas-300` 竖线分隔
- `frontend/src/style.css`：font-family 栈前置加入 `"Menlo" / "Consolas" / "Cascadia Code" / "JetBrains Mono" / "Fira Code"` monospace 兜底，末尾 `sans-serif` → `monospace`（IP / 等宽数字走 mono 栈）
- `frontend/src/views/Dashboard.vue`：import `getStatusLabel`，新增 `statusLabel` 包装
- `frontend/src/views/Devices.vue`：import `getStatusChip` / `getStatusLabel`，移除本地 `statusChip` 内联函数
- `frontend/src/views/OpsTerminal.vue`：import `Select` 组件

## Capabilities

### New Capabilities
（无新增能力，纯样式 / 布局调整，不引入新功能）

### Modified Capabilities
（无现有 spec 修改；状态显示统一已经在 `feat(frontend): 字体统一 + 自定义 Select 组件 + 状态显示中文化`（commit 4532232）中实现，本 change 只是补全 view 层的引用）

## Impact

- **代码**：6 个前端文件，CSS/Tailwind 类名微调、import 调整
- **行为**：纯视觉调整，无业务逻辑变化
- **API**：无变化
- **数据库**：无
- **依赖**：无新增
- **回归**：原 commit 4532232 已通过发布前自测（用户在浏览器确认字体、Select、状态显示均正确）
