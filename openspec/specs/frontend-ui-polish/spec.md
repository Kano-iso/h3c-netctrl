# frontend-ui-polish Specification

## Purpose
TBD - created by archiving change chore-frontend-polish. Update Purpose after archive.
## Requirements
### Requirement: PageHeader 下拉菜单可溢出显示

PageHeader 组件 MUST 不使用 `overflow-hidden` 裁剪子元素，且 slot="actions" 区域 MUST 位于 z-index 20 层，确保任何内部 Select 组件的绝对定位下拉菜单可正常溢出显示，不被装饰渐变或相邻容器遮挡。

装饰渐变元素 MUST 位于 z-index 0 以下（`-z-0`），主内容容器 MUST 位于 z-index 10 层。

#### Scenario: 运维终端下拉菜单在 PageHeader 中正常显示
- **WHEN** 用户在窄窗口（< 800px）打开 OpsTerminal 页面并点击设备下拉菜单
- **THEN** 下拉菜单完整显示在 PageHeader 之外（向下方溢出），不被装饰渐变或相邻 DOM 节点遮挡

### Requirement: Select 触发器三段式显示布局

Select 组件触发器 MUST 支持三段式显示（label / sub / status chip），各项 MUST 可独立截断，状态 chip MUST 通过 `ml-auto` 推至最右。当 sub 字段超长时 MUST 截断且不挤压其他元素。

#### Scenario: 长 IP 设备名 + 状态 chip 同时显示
- **WHEN** Select 触发器显示 "Spine-01@192.168.100.100" + sub "192.168.100.100" + status "在线"
- **THEN** label 优先截断，sub 截断至 `max-w-[8rem]`，status chip 通过 `ml-auto` 推至最右；触发器右侧下拉箭头 + 装饰竖线完整可见

### Requirement: 跨平台 monospace 字体栈

`style.css` body 的 `font-family` MUST 在中文栈之前优先使用 monospace 栈（Menlo / Consolas / Cascadia Code / JetBrains Mono / Fira Code），保证英文 / 数字 / IP 在所有平台（macOS / Windows / Linux）渲染风格与运维终端一致。

#### Scenario: Linux 容器内 IP 渲染一致
- **WHEN** 用户在 Linux 浏览器访问任意含 IP 的下拉项（如 "Spine-01@192.168.100.100"）
- **THEN** IP 字符走 monospace 栈（DejaVu Sans Mono / Liberation Mono 兜底），与运维终端默认命令同款字体

### Requirement: view 层统一调用 utils/status.js

Dashboard / Devices 视图 MUST 直接 import `utils/status.js` 的 `getStatusLabel` / `getStatusChip` 辅助函数，删除内联的 `statusChip` 箭头函数，状态显示逻辑 MUST 集中维护。

#### Scenario: Devices 视图状态 chip 与 label 一致
- **WHEN** Devices 视图加载设备列表，设备 status="online" / "offline" / "maintenance"
- **THEN** chip class 由 `getStatusChip` 返回（与 CMDB / Dashboard / OpsTerminal 一致），label 由 `getStatusLabel` 返回中文（"在线" / "离线" / "维护中"）

