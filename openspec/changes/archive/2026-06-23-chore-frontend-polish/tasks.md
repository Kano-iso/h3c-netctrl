## 1. 确认改动落地

本 change 实际改动已在前序工作中完成（commit 4532232 之后追加，发布前自测通过），本节仅做落盘确认。

- [x] 1.1 PageHeader.vue 去掉 `overflow-hidden`，装饰渐变 `-z-0`，内容 `z-10`，actions `z-20`
- [x] 1.2 Select.vue 触发器内边距 `pl-3 pr-2`、sub `truncate max-w-[8rem]`、status `ml-auto`、加竖线分隔
- [x] 1.3 style.css font-family 前置 mono 栈（Menlo / Consolas / Cascadia Code / JetBrains Mono / Fira Code），末尾 `monospace` 兜底
- [x] 1.4 Dashboard.vue / Devices.vue import `utils/status.js` 的 `getStatusLabel` / `getStatusChip`，删除内联函数
- [x] 1.5 OpsTerminal.vue import `Select` 组件

## 2. 验证

- [x] 2.1 浏览器确认窄窗口下 PageHeader 内 Select 下拉菜单正常溢出显示
- [x] 2.2 浏览器确认 Select 触发器长设备名 + 状态 chip 三段式不挤压
- [x] 2.3 浏览器确认 Dashboard / Devices / OpsTerminal 状态显示中文化（"在线"/"离线"/"维护中"）
- [x] 2.4 浏览器确认 Linux 容器内 IP 字符走 monospace 栈（与运维终端同款）
- [x] 2.5 确认无新增 vite 报错、无控制台 warning

## 3. 收尾

- [ ] 3.1 提交代码 `chore(frontend): 下拉菜单溢出 + Select 布局 + monospace 字体栈`
- [ ] 3.2 archive change
