## Why

v20-bugfix-interface-safety-guard 变更中给 DeviceDetail.vue 增加了 `isIfaceProtected` 计算属性，但**漏了 import computed**。

Vue setup 阶段执行 `computed(() => ...)` 时，`computed` 未定义，运行时抛 `ReferenceError`，导致整个页面白屏。

## What Changes

- DeviceDetail.vue 增加 `computed` 的 import
- 验证：设备详情页能正常加载（不白屏）

## Impact

- 前端：DeviceDetail.vue

## 教训

- 每次改 Vue 组件 script 段，必须**真的打开页面**测一遍（不能只看 API 200）
- 改 vue 文件时 ESLint/lint 工具能发现 undefined 引用
