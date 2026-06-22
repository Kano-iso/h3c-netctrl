## Context

v20-bugfix-interface-safety-guard 变更在 DeviceDetail.vue 加了：

```js
const isIfaceProtected = computed(() => {...})
```

但 script 顶部 import 只有 `ref, onMounted`，**漏了 computed**。

虽然 computed 用在 `v-if="isIfaceProtected"` 的弹窗内部（弹窗 v-if 控制），但 setup 阶段顶层表达式仍会执行 `computed()` 调用，触发 ReferenceError，导致 Vue 渲染挂掉。

## Goals / Non-Goals

**Goals:**
- 增加 computed import，修复白屏

**Non-Goals:**
- 不改其他逻辑

## Decisions

### D1: 仅加 import

**选择**：`import { ref, computed, onMounted } from 'vue'`

**理由**：最小改动，只补 import。

## Risks

- 后续新增 computed 还可能忘记 import — 建议加 ESLint 规则
