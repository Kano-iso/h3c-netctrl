# frontend-i18n-migration（前端全量 i18n 改造）

## 目标

把前端所有面向用户的中文文案改造为 i18n key 引用，确保用户切换到英文时所有 UI、按钮、提示、状态文案、错误 toast 均显示英文。

## 范围

**包含**：
- 11 views（Dashboard / Devices / Interfaces / VLAN / CMDB / Backup / Batch / OpsTerminal / Logs / Topology / AIAssistant）全量中文 → `$t()`
- 10 components（ConfirmModal / DeviceFormModal / AssetEditModal / Ipv4AddressEditModal / VpnInstanceBindModal / BackupListModal / PageHeader / AppFooter / BackgroundTaskPanel / Select）全量中文 → `$t()`
- App.vue（顶导 groups label/desc、用户头像 menu）→ `$t()`
- `frontend/src/utils/status.js`（设备状态文案：在线 / 离线 / 告警 等）→ `$t()`
- `frontend/src/api/index.js`（axios 错误 toast、APIResponse.error 显示）→ 用 `error_key` 查 i18n
- 中文 locale 文件 + 英文 locale 文件 同步扩充（按实际用到的 key）
- 后端 APIResponse.error_key → i18n 表（前端 key → 文案映射）

**不包含**：
- HTML 注释、JS 注释、console.log（不影响用户体验）
- ops-toolkit 脚本（CLI 无 i18n 需求）
- 文档（README、docs、OpenSpec 流程文档保持中文）
- 第三方库默认文案（bootstrap、vue 等）

## 设计决策

### 决策 1: locale 文件结构（单一入口 + 按视图分组）

```js
// frontend/src/i18n/zh-CN.js
export default {
  app: {
    title: 'H3C NetCtrl',
    loading: '加载中...',
    error: '出错了',
  },
  nav: {
    dashboard: '总览',
    devices: '设备',
    ops: '运维终端',
    interfaces: '接口',
    batch: '批量操作',
    cmdb: 'CMDB',
    backup: '备份回滚',
    logs: '操作日志',
    topology: '拓扑视图',
    ai: 'AI 助手',
    overview: '运维操作',
    ops_desc: '直接对设备下发配置',
    management: '运营管理',
    management_desc: '资产盘点 · 配置存档',
    diagnosis: '排查诊断',
    diagnosis_desc: '日志 · 拓扑 · AI 辅助',
  },
  common: {
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    delete: '删除',
    edit: '编辑',
    add: '新增',
    search: '搜索',
    refresh: '刷新',
    loading: '加载中...',
    success: '成功',
    failed: '失败',
    retry: '重试',
    yes: '是',
    no: '否',
  },
  device: {
    list: {
      title: '设备清单',
      empty: '暂无设备',
      add: '新增设备',
      edit: '编辑设备',
      delete_confirm: '确认删除设备 {name}?',
    },
    form: {
      name: '设备名称',
      host: 'IP 地址',
      port: '端口',
      username: '用户名',
      password: '密码',
    },
  },
  status: {
    online: '在线',
    offline: '离线',
    warning: '告警',
    error: '错误',
    unknown: '未知',
  },
  // ... 11 views × 完整中文
}
```

- 按模块分组（`nav.*` / `common.*` / `device.*` / `interface.*` / ...）
- 嵌套结构 vs 扁平 key：vue-i18n 两种都支持，扁平更直观（参考 design.md 决策 4）
- 中文为主，英文次要，key 数量一致（CI 校验）

### 决策 2: 状态文案 i18n 化

```js
// frontend/src/utils/status.js 改造
import { useI18n } from 'vue-i18n'

export function getStatusText(status) {
  const { t } = useI18n()  // Composition API
  const map = {
    online: t('status.online'),
    offline: t('status.offline'),
    warning: t('status.warning'),
    error: t('status.error'),
    unknown: t('status.unknown'),
  }
  return map[status] || map.unknown
}
```

- `useI18n()` 在 setup 外调用：用 `getCurrentInstance()` 或导出纯函数 + 外部传入 `t`

### 决策 3: axios 错误处理 i18n 化

```js
// frontend/src/api/index.js 错误处理
import { useI18n } from 'vue-i18n'

function showError(error) {
  const { t } = useI18n()
  const errorKey = error.response?.data?.error_key
  const errorParams = error.response?.data?.error_params || {}
  
  let message
  if (errorKey) {
    // 后端返了 i18n key，前端查表
    message = t(`error.${errorKey}`, errorParams)
    if (message === `error.${errorKey}`) {
      // fallback：i18n 表里没找到，用后端原 error
      message = error.response?.data?.error || t('common.error')
    }
  } else {
    // 后端没返 error_key，用原 error（可能中文）
    message = error.response?.data?.error || error.message || t('common.error')
  }
  
  // toast.show(message)  // 假设有 toast 系统
  console.error(message)
}
```

- 兼容策略：后端有 `error_key` → 用 i18n；没有 → fallback 到原 `error`（中文）

### 决策 4: 视图改造顺序（按用户使用频率）

按 task 粒度分阶段（design.md 决策 4 命名规范）：

1. App.vue（groups 顶导）
2. AppFooter.vue
3. utils/status.js
4. api/index.js
5. Dashboard.vue
6. Devices.vue
7. Interfaces.vue
8. VLAN（Interfaces.vue 内的 modal 部分）
9. CMDB.vue
10. Backup.vue
11. Batch.vue
12. OpsTerminal.vue
13. Logs.vue
14. Topology.vue
15. AIAssistant.vue
16. PageHeader.vue
17. Select.vue
18. ConfirmModal.vue
19. DeviceFormModal.vue
20. AssetEditModal.vue
21. Ipv4AddressEditModal.vue
22. VpnInstanceBindModal.vue
23. BackupListModal.vue
24. BackgroundTaskPanel.vue

每视图/组件 = 1 task = 1 commit。

## 验收标准

1. ✅ 11 views 全部使用 `$t()` 替代硬编码中文（grep 验证：`grep -r "[\u4e00-\u9fff]" frontend/src/views/ | grep -v "// " | grep -v "<!--"` 应为 0 行）
2. ✅ 10 components 全部使用 `$t()` 替代硬编码中文（同上验证 components/）
3. ✅ App.vue + AppFooter.vue 全部使用 `$t()`
4. ✅ `utils/status.js` 全部使用 `$t()`
5. ✅ `api/index.js` 错误处理使用 `error_key` 查 i18n
6. ✅ `frontend/src/i18n/zh-CN.js` 与 `frontend/src/i18n/en-US.js` key 数量一致（CI 校验）
7. ✅ 默认 locale (zh-CN) 下，UI 显示与 v2.5.0 完全一致（无视觉变化）
8. ✅ 切换到 en-US 后，所有 UI 文字变英文（包括顶导 groups 描述、按钮、提示、错误 toast、状态文案）
9. ✅ 切换后刷新页面保持
10. ✅ qa-frontend 全过（lint + build + vitest 38+ + playwright 42+）
11. ✅ qa-backend 265 passed baseline 不变

## 风险

- **翻译条目遗漏**：用户原话"别漏了点" → 风险高 → 用 grep 脚本自动验证
- **翻译质量**：非专业翻译，语义准确即可
- **后端 error_key 字段未覆盖**：fallback 到原 error（中文）→ UI 看到混合 → 加 console.warn 提示 + 用户报告后补
- **测试断言需要更新**：默认 locale 是中文，断言基本不变；新增英文断言即可
- **i18n key 命名冲突**：模块前缀避免（参考 design.md 决策 4）
