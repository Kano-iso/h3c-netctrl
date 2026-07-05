# H3C NetCtrl i18n 国际化指南（v2.6.0+）

> 本文档是 v2.6.0 起的 i18n 维护规范。涉及前端 locale 文件、后端 `i18n_keys.py`、API 错误 key 翻译三个维度。
> 改 i18n 任何一处前必读。

## 1. 设计目标

- **用户能切语言**：导航栏右上角「中 | EN」按钮，刷新后保持
- **前端 100% 翻译覆盖**：11 views + 10 components + App + Footer + utils + api
- **后端错误可翻译**：APIResponse 增加 `error_key` + `error_params`，前端用 i18n 翻译，缺失时 fallback 到中文 `error` 字段
- **降级策略**：前端 locale 缺失 → 显示中文；后端 key 未注册 → 返回中文 error；任一环节失败都不影响主流程

## 2. 翻译 key 命名规范

### 2.1 前端

**格式**：`<module>.<sub>.<semantic>`（点号分层，全小写 + 下划线）

| 段 | 规则 | 示例 |
|---|---|---|
| `<module>` | 顶级功能模块，对应 view / component / 全局 | `nav` / `dashboard` / `device` / `interface` / `vlan` / `cmdb` / `backup` / `batch` / `ops` / `log` / `topology` / `ai` / `component` / `form` / `modal` / `status` / `error` / `app` / `footer` / `common` |
| `<sub>` | 可选，二级分组 | `nav.items.devices` / `nav.groups.ops` / `device.form` / `device.list` |
| `<semantic>` | 语义（label / desc / placeholder / title / action / msg） | `.label` / `.desc` / `.placeholder` / `.action_create` / `.msg_success` |

**示例**：
```javascript
// 全局
'app.toggle_locale'         // 切换语言
'common.confirm'            // 确认
'common.cancel'             // 取消
'common.search'             // 搜索
'common.loading'            // 加载中

// 导航
'nav.dashboard'             // 总览 / Dashboard
'nav.groups.ops.label'      // 运维操作
'nav.groups.ops.desc'       // 直接对设备下发配置
'nav.items.devices.label'   // 设备
'nav.items.devices.desc'    // 设备清单 · 连接测试

// 视图
'dashboard.title'           // 网络运维总览
'dashboard.kpi.devices'     // 在管设备
'device.list.col_name'      // 设备名
'device.list.col_host'      // IP 地址
'device.list.col_status'    // 状态
'device.action.create'      // 新建设备
'device.form.label_host'    // IP 地址
'device.form.placeholder_host'  // 例：192.168.100.100

// 组件
'component.confirm.title_delete'   // 确认删除
'component.confirm.content_delete' // 确定要删除 {name} 吗？
'modal.backup.title'               // 备份管理
'form.required'                    // 必填

// 状态/错误
'status.device.online'    // 在线
'status.device.offline'   // 离线
'status.device.unknown'   // 未知
'error.network'           // 网络错误
'error.timeout'           // 请求超时
```

### 2.2 后端

**格式**：`<domain>.<semantic>`（点号分层，集中在 `backend/app/i18n_keys.py`）

| 段 | 规则 | 示例 |
|---|---|---|
| `<domain>` | 顶级域，对应 router / 公共 | `common` / `device` / `interface` / `vlan` / `asset` / `backup` / `batch` / `execute` / `log` / `dashboard` |
| `<semantic>` | 错误语义（snake_case） | `not_found` / `missing_field` / `connect_failed` / `create_failed` |

**示例**：
```python
class Device:
    NOT_FOUND = I18nKey("device.not_found")          # 设备不存在: id={id}
    CONNECT_FAILED = I18nKey("device.connect_failed")  # 设备连接失败: {error}

class Backup:
    NOT_FOUND = I18nKey("backup.not_found")          # 备份不存在: id={id}
    LOCKED_NO_DELETE = I18nKey("backup.locked_no_delete")  # 已锁定，禁止删除
```

**规则**：
- **不要拼写错误**：`is_valid_key()` 运行时检查，未注册 key 会被防御性拦截（拒绝裸字串）
- **集中管理**：所有 key 必须在 `i18n_keys.py` 的 `class Xxx` 域里声明（`SimpleNamespace err` 集中导出）
- **后端不加新域**：除非新增 router，否则不在 `i18n_keys.py` 加新 `<domain>`
- **i18n 与降级对齐**：每个 key 必须在 `FALLBACK_MESSAGES` 注册中文降级文案

## 3. 文件组织

### 3.1 前端

```
frontend/src/i18n/
├── index.js          # createI18n 实例 + locale 探测
├── zh-CN.js          # 中文（默认 + 基础 key）
└── en-US.js          # 英文（与 zh-CN 对齐）

frontend/src/stores/
└── locale.js         # Pinia store（setLocale / toggleLocale + localStorage）

frontend/src/i18n/
└── t.js              # 工具模块用的 t()（utils/api 不在 Vue 组件 scope）
```

### 3.2 后端

```
backend/app/
├── i18n_keys.py      # 所有 key 集中表 + error_response() helper
└── schemas.py        # APIResponse 增加 error_key + error_params 字段
```

## 4. 翻译条目新增流程

### 4.1 前端新增 key

1. **打开** `frontend/src/i18n/zh-CN.js` 和 `en-US.js`
2. **在对应 module 段加 key**（zh-CN + en-US 必须同时加，否则测试报警）
3. **在组件中用 `$t('xxx.yyy')`**（template）或 `i18n.global.t('xxx.yyy')`（script setup）
4. **utils/api 模块**：用 `import { t } from '@/i18n/t'`（不要直接用 i18n.global.t，因为组件外响应式可能滞后）
5. **跑 vitest**：`docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`
6. **跑 playwright**：同上（i18n 切换按钮 e2e 验证渲染）

### 4.2 后端新增 key

1. **打开** `backend/app/i18n_keys.py`
2. **在对应域 class 加 key**：
   ```python
   class Device:
       NEW_ERROR = I18nKey("device.new_error")  # 新错误描述
   ```
3. **在 `err` SimpleNamespace 加导出**：
   ```python
   err = SimpleNamespace(
       ...,
       NEW_ERROR=Device.NEW_ERROR,
   )
   ```
4. **在 `FALLBACK_MESSAGES` 注册中文降级**（用 `{param}` 占位符）
5. **在 router 用** `error_response(err.DEVICE.NEW_ERROR, params={"x": 1})`
6. **写单测**：`tests/test_i18n.py` 加 `TestKeyCoverage::test_all_domains_have_keys` 验证
7. **跑 qa-backend**：`docker compose -f docker-compose.dev.yml --profile qa up qa-backend`

### 4.3 同步前端 locale

**关键**：后端加新 key 后，前端 `en-US.js` 必须同步加翻译，否则英文模式下用户看到中文降级文案。

后端改动时检查清单：
- [ ] i18n_keys.py 加新 key
- [ ] 同步 `zh-CN.js` + `en-US.js`（如果前端会用这个 key 翻译）
- [ ] 如果前端不翻译这个 key，至少保证 `zh-CN.js` 与后端 `FALLBACK_MESSAGES` 一致（fallback 兜底）

## 5. 翻译风格指引

### 5.1 中文

- **简洁直接**：避免冗长，标点用全角
- **专业术语**：保留英文缩写（NETCONF / VLAN / VPN / L2 / L3 / IP / SCP / NTP）
- **动词在前**：「创建 VLAN」「删除设备」而非「VLAN 创建」
- **不翻译品牌名**：H3C NetCtrl 保持原样

### 5.2 英文

- **Title Case**：UI 标签、按钮用 Title Case（"New Device" / "Save Changes"）
- **Sentence case**：提示消息、描述用 Sentence case（"Device created successfully."）
- **专业术语**：与中文一致（NETCONF / VLAN / VPN / IP / etc.）
- **避免被动语态**：用户视角为主（"Failed to create device" → "Couldn't create device"）
- **不翻译品牌名**：H3C NetCtrl 保持原样

### 5.3 插值参数

- **占位符用 `{name}`**（vue-i18n v9 默认）
- **位置敏感**：参数顺序在两种语言中可能不同
- **示例**：
  ```javascript
  // zh-CN
  'device.msg_not_found': '设备不存在: id={id}'
  // en-US
  'device.msg_not_found': 'Device not found: id={id}'
  ```

## 6. locale 切换机制

### 6.1 前端

- **store**：`frontend/src/stores/locale.js`（Pinia）
  - `setLocale(locale)` — 设置并持久化
  - `toggleLocale()` — 在 zh-CN ↔ en-US 间切换
  - 自动同步 `i18n.global.locale.value` + `localStorage.setItem('locale', locale)`
- **持久化**：`localStorage.setItem('locale', 'en-US')`（key 固定为 `locale`）
- **初始化**：`frontend/src/i18n/index.js` 启动时从 `localStorage.getItem('locale')` 还原，缺失则 fallback `zh-CN`
- **支持 locale**：`zh-CN` / `en-US`（其他 locale 切换时打印 warn 并忽略）

### 6.2 后端

- **错误响应 schema**：`backend/app/schemas.py` `APIResponse`
  - `success: bool`
  - `data: Optional[object] = None`
  - `error: Optional[str] = None` — 中文降级（**必填**或 success=True）
  - `error_key: Optional[str] = None` — i18n key（v2.6 新增）
  - `error_params: Optional[dict] = None` — 插值参数（v2.6 新增）
- **前端优先用 `error_key` 翻译**；找不到翻译时 fallback 到 `error` 字段（**永远不为空**）

## 7. 测试覆盖

| 层 | 测试类型 | 文件 | 关键 case |
|---|---|---|---|
| 前端 vitest | 组件渲染 + i18n 切换 | `src/__tests__/Devices.spec.js` 等 5 文件 | 默认中文渲染 + 切英文 + localStorage 持久化 |
| 前端 playwright | E2E 切换 | `tests/e2e/i18n-switch.spec.js` | 5 case（按钮可见 / 切换响应 / 持久化 / 后端 key / fallback） |
| 后端 pytest | 单元 + 路由错误 | `tests/test_i18n.py` | 26 case（key 完整性 / error_response helper / 9 router 错误场景） |

**回归基线**（v2.6.0）：
- qa-backend: 265 → **291 passed**（+26 i18n）
- qa-frontend vitest: 33 → **53 case**（+20 i18n）
- qa-frontend playwright: 37 → **42 e2e**（+5 i18n-switch）

## 8. 常见误区

1. **❌ 在 zh-CN.js 加 key 但 en-US.js 漏了** → 英文模式显示 key 字符串
   **✅** 同步加，CI 会卡 lint（vue-i18n 缺失警告）

2. **❌ 在 utils/api 用 `i18n.global.t('xxx')`** → 切换 locale 后可能不更新
   **✅** 用 `import { t } from '@/i18n/t'`（基于 i18n ref 显式取值）

3. **❌ 循环变量名 `t` 遮蔽 i18n `t()`** → 编译能过但运行报 undefined
   **✅** 循环变量用业务名（`task` / `device` / `item`）

4. **❌ 后端拼字串 `error=f"设备不存在: {id}"`** → 英文模式无法翻译
   **✅** 用 `error_response(err.DEVICE.NOT_FOUND, params={"id": id})`

5. **❌ 加 key 不更新 FALLBACK_MESSAGES** → 前端拿到 error_key 但没 fallback，error 字段空
   **✅** 每个新 key 必加中文 fallback

6. **❌ ESLint 报 `'finalPlaceholder' is assigned a value but never used`** → 在 setup return 中暴露但 template 用了，被误判
   **✅** 加 `// eslint-disable-next-line no-unused-vars` 注释（template 用法 ESLint 看不到）

## 9. 工具链

- **vue-i18n v9** — Vue 3 官方 i18n 库（legacy: false，composition API）
- **Pinia** — 响应式 locale 状态管理
- **localStorage** — 持久化（key: `locale`）
- **pytest** — 后端 key 完整性测试
- **vitest + playwright** — 前端 i18n 渲染 + 切换测试

## 10. 关联文档

- [VERSION-ROADMAP.md §v2.6](VERSION-ROADMAP.md#v26)
- [openspec/changes/v26-i18n/proposal.md](openspec/changes/v26-i18n/proposal.md)
- [openspec/changes/v26-i18n/design.md](openspec/changes/v26-i18n/design.md)
- [frontend/src/i18n/zh-CN.js](frontend/src/i18n/zh-CN.js) / [en-US.js](frontend/src/i18n/en-US.js)
- [backend/app/i18n_keys.py](backend/app/i18n_keys.py)
- [RELEASE-NOTES-v2.6.0.md](RELEASE-NOTES-v2.6.0.md)
