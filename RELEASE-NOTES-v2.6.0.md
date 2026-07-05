# RELEASE-NOTES-v2.6.0

**版本**: v2.6.0
**日期**: 2026-07-06
**主题**: 中英双语 i18n（vue-i18n v9 + 400+ 翻译 key + 后端 error_key schema 扩展）
**前序**: v2.5.0 (2026-07-05)

> ⚠️ **BREAKING SCHEMA** — `APIResponse` 新增 `error_key: Optional[str]` + `error_params: Optional[dict]` 两个字段。
> 老客户端（只用 `success` / `data` / `error`）兼容性不变；新客户端可选用 `error_key` 走 i18n 翻译。

---

## 1. 主题

v2.6.0 = **i18n（国际化）**。v2.5.0 P1 工程化收口后，3 容器 + split 默认 + 测试体系（vitest + playwright）全部稳定。
但 UI 与后端错误仍为中文单语，无法对外演示/英文用户使用。v3.0 VPC 起步面向多语用户（容器 + 监控），前端双语能力是基础设施前置。

需求：**导航栏右上角加中英切换按钮，扫遍全项目（前端 11 views + 10 components + App + Footer + 后端 9 router error + 测试断言），做好中英切换，别漏了点**。

v2.6.0 包含 **1 个 change + 14 个 commit**：

| change | 主题 | 状态 |
|---|---|---|
| v26-i18n | vue-i18n v9 集成 + locale 切换 UI + 400+ 翻译 key + 后端 error_key 扩展 + 9 router 改造 + 26 后端单测 + 25 前端测试 | ✅ archive |

---

## 2. BREAKING SCHEMA：APIResponse 新增 i18n 字段

### 2.1 变更内容

`backend/app/schemas.py` 中 `APIResponse` 类：

```python
class APIResponse(BaseModel):
    success: bool
    data: Optional[object] = None
    error: Optional[str] = None
    # v2.6 i18n: error_key 给前端用 vue-i18n 查翻译；error_params 是 i18n 插值参数
    # 兼容策略：error 必填（中文降级），error_key 可选；前端优先用 error_key 翻译，找不到再 fallback 到 error
    error_key: Optional[str] = None        # ← 新增
    error_params: Optional[dict] = None    # ← 新增
```

### 2.2 兼容性

- **老客户端（v2.5 之前）**：只用 `success` / `data` / `error` 三个字段，**完全不受影响**（新字段均为 Optional，新增字段向后兼容）
- **新客户端（v2.6+）**：可选消费 `error_key` + `error_params` 走 i18n 翻译；找不到 key 时 fallback 到 `error` 字段
- **后端降级**：每个 i18n key 在 `FALLBACK_MESSAGES` 注册中文降级文案，前端无翻译时仍能显示中文

### 2.3 升级步骤

```bash
# 1. 拉代码
git pull origin main

# 2. 重新构建 + 启动（split 3 容器，默认模式不变）
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d

# 3. 验证 API 响应 schema 升级
curl -s http://localhost:8001/api/devices/99999 | python -m json.tool
# 应该看到: success=false, error="设备不存在: id=99999", error_key="device.not_found", error_params={"id": 99999}

# 4. 验证前端切换按钮
# 访问 http://localhost:5173/，右上角「中 | EN」可点
```

---

## 3. 包含的 Changes（1 个）

### Change：v26-i18n（i18n 完整闭环）

#### 3.1 Task 1：vue-i18n 集成骨架

**问题**：前端无 i18n 框架，硬编码中文遍布 11 views + 10 components。

**解决**：
- 装 `vue-i18n@^9.x`（Vue 3 官方库，`legacy: false` composition API）
- `frontend/src/i18n/` 建 `index.js`（createI18n 实例 + locale 探测）+ `zh-CN.js`（默认 + 基础 key）+ `en-US.js`
- `main.js` 注入 `app.use(i18n)`，locale 默认 `zh-CN`
- `__tests__/Smoke.spec.js` 加 1 个 i18n 实例创建 smoke test

**Commit**：`b9a7b8c` chore(frontend): vue-i18n v9 集成骨架 + 4 smoke test (v26-i18n Task 1)

#### 3.2 Task 2：locale 切换 UI + 持久化

**问题**：用户无法在浏览器中切换语言，刷新后又回中文。

**解决**：
- `frontend/src/stores/locale.js` — Pinia store（`setLocale` / `toggleLocale` + `i18n.global.locale.value` 同步）
- App.vue 顶导右上角加「中 | EN」切换按钮（K 用户头像前，`data-testid="locale-toggle"`）
- `localStorage.setItem('locale', 'en-US')` 持久化
- `i18n/index.js` 启动时从 localStorage 还原

**Commit**：`c0d6902` feat(frontend): 顶导加中英切换按钮 + localStorage 持久化 (v26-i18n Task 2)

#### 3.3 Task 3：App.vue + AppFooter.vue i18n

**解决**：
- App.vue 三大功能组（运维操作 / 运营管理 / 排查诊断）label + desc 全 i18n
- 顶导「总览」/ 切换按钮 aria-label 全 i18n
- AppFooter.vue 4 列链接 + 介绍 + 版权行全 i18n
- locales 加 `app.*` / `nav.*` / `footer.*` key（~30 条）

**Commit**：`b88b8fa` refactor(frontend): App.vue 顶导三大组 + AppFooter.vue i18n 化 (v26-i18n Task 3)

#### 3.4 Task 4：utils/status.js + api/index.js

**解决**：
- `utils/status.js` — 状态文案改用 `$t('status.device.online')` 等
- `api/index.js` — axios 错误处理：优先 `error_key` 查 i18n → fallback `error` 字段
- `frontend/src/i18n/t.js`（新建）— 工具模块的 t() helper，确保 utils/api 也能响应式翻译
- locales 加 `status.*`（在线/离线/未知/启用/禁用等）+ `error.*`（网络错误/超时等）key

**Commit**：`7badae8` feat(frontend): utils/status.js + api/index.js i18n 化 (v26-i18n Task 4)

#### 3.5 Task 5：Dashboard + Devices + Interfaces 核心 view

**解决**：3 个核心 view 全 i18n：
- Dashboard.vue：标题 / KPI 标签 / 卡片 / 快速入口 / 最近操作
- Devices.vue：列表表头 / 操作按钮 / Modal 触发 / 搜索占位
- Interfaces.vue：列表 / VLAN 标签 / L2/L3 状态 / 操作按钮
- locales 加 `dashboard.*` / `device.*` / `interface.*` key（~120 条）

**Commit**：`ea19ee7` refactor(frontend): Dashboard + Devices + Interfaces i18n 化 (v26-i18n Task 5)

#### 3.6 Task 6：CMDB + Backup + VLAN 业务 view

**解决**：3 个业务 view 全 i18n：
- CMDB.vue：资产列表 / 标签 / 操作 / 编辑 modal
- Backup.vue：备份列表 / 状态 / 操作 / 锁定
- VLAN（Interfaces.vue 内 modal + 工具栏）
- locales 加 `cmdb.*` / `backup.*` / `vlan.*` key（~80 条）

**Commit**：`1c219c3` refactor(frontend): CMDB + Backup i18n 化 (v26-i18n Task 6)

#### 3.7 Task 7：5 个次要 view

**解决**：5 个次要 view 全 i18n：
- Batch.vue：批量执行表单 / 结果展示
- OpsTerminal.vue：终端 / 命令历史 / 多命令
- Logs.vue：日志列表 / 筛选 / 详情
- Topology.vue：拓扑视图（占位）
- AIAssistant.vue：AI 助手（占位）
- locales 加 `batch.*` / `ops.*` / `log.*` / `topology.*` / `ai.*` key（~60 条）

**Commit**：`951f882` refactor(frontend): Batch + OpsTerminal + Logs + Topology + AIAssistant i18n 化 (v26-i18n Task 7)

#### 3.8 Task 8：10 个核心 components i18n

**解决**：
- ConfirmModal / PageHeader / Select（基础组件）
- DeviceFormModal / AssetEditModal / Ipv4AddressEditModal / VpnInstanceBindModal（表单 modal）
- BackupListModal / BackgroundTaskPanel（业务 modal）
- locales 补全 `component.*` / `form.*` / `modal.*` key（~80 条）
- **修复回归**：6 处 i18n 迁移后的中文 fallback 回归（恢复原始中文 + 翻译 key 并存）

**Commit**：`5944e2c` refactor(frontend): 10 components i18n 化 + locales 全量翻译 (v26-i18n Task 8)

#### 3.9 Task 9：后端 i18n_key + APIResponse 扩展（**BREAKING SCHEMA**）

**解决**：
- `backend/app/schemas.py` — `APIResponse` 加 `error_key` + `error_params` 字段
- `backend/app/i18n_keys.py`（新建）— 84 个 key 集中表 + `is_valid_key()` + `error_response()` helper
- 9 个 router 改造（device / interface / vlan / asset / backup / batch / execute / log / dashboard）
- 全部 error 场景走 `error_response(err.X.Y, params={...})` 统一返回
- 中文降级：每个 key 在 `FALLBACK_MESSAGES` 注册降级文案

**Commit**：`f2b47fa` feat(backend): APIResponse error_key 扩展 + 9 router 改造 (v26-i18n Task 9, BREAKING schema)

#### 3.10 Task 10-11：vitest + playwright i18n 测试

**vitest（53 case）**：
- 5 核心组件 + 1 i18n 专项 = 33 + 20 case
- i18n 切换响应式 / localStorage 持久化 / fallback / 默认 locale

**playwright（42 e2e）**：
- `i18n-switch.spec.js` 5 case：切换按钮可见 / 切英文后文案变 / localStorage 持久化 / 切回中文恢复 / 后端 error_key 翻译
- 8 个 e2e 文件默认中文断言不变（向后兼容）

**Commit**：
- `c6c309a` test(frontend): vitest 33→53 case 含 5 组件 i18n 切换测试 (v26-i18n Task 10)
- `6c6f030` test(frontend): playwright 37→42 e2e 含 5 i18n 切换测试 (v26-i18n Task 11)

#### 3.11 Task 12.1：conftest 修复（回归发现）

**问题**：v2.5 测试 291 passed，v2.6 加 `import app.models` 后 132 failed（58 + 74 errors）。

**根因**：conftest 写 `from app.main import app` 后又写 `import app.models`，后者是 binding statement（PEP 328），把局部 namespace 的 `app` 重新绑定到 `app` package module，覆盖 `app.main.app` 的 FastAPI 实例。TestClient 收到 module 报 `'module' object is not callable`。

**修复**：调换 import 顺序——先 `import app.models`（注册 Base 子类到 metadata），再 `from app.main import app`，最后一次绑定胜出。

**Commit**：
- `7ebfcca` fix(backend): conftest 显式 import app.models 修复 test_task_manager 'no such table: tasks' (v26-i18n Task 12.1)
- `28faec3` fix(backend): conftest import 顺序修复 TestClient 'module is not callable'

---

## 4. 关键设计决策

| 决策 | 方案 | 理由 |
|---|---|---|
| i18n 库 | vue-i18n v9（legacy: false） | Vue 3 官方库，composition API 友好 |
| 状态管理 | Pinia store（locale.js） | 响应式 + 模块化 |
| 持久化 | localStorage（key: `locale'`） | 简单够用，无需后端参与 |
| 切换按钮位置 | 顶导右上角 K 用户头像前 | 用户视线第一落点 |
| 默认 locale | zh-CN | 项目当前用户群 |
| 后端 i18n 路径 | APIResponse 加 error_key + error_params | 与现有 success/data/error 兼容 |
| 后端降级策略 | FALLBACK_MESSAGES 字典 | 旧客户端拿到 error 字段仍可显示中文 |
| 集中管理 key | `i18n_keys.py` class + SimpleNamespace | 防止拼写错误 + IDE 自动补全 |
| 工具模块翻译 | 自建 `i18n/t.js`（非 i18n.global.t） | 避免 component scope 外响应式滞后 |
| conftest import 顺序 | 先 `import app.models` 再 `from app.main import app` | PEP 328 binding statement 不覆盖 |

---

## 5. 关联

- 前序: v2.5.0 (2026-07-05) — P1 工程化收口
- 路线图: [VERSION-ROADMAP.md §v2.6](VERSION-ROADMAP.md#v26)
- 翻译规范: [docs/i18n-guide.md](docs/i18n-guide.md)
- 工具容器: 不变（ops-toolkit / qa-backend / qa-frontend 9 脚本）
- Change archive: [openspec/changes/archive/2026-07-06-v26-i18n/](openspec/changes/archive/)

---

## 6. 测试 / 验证

### qa-backend 单元测试（265 baseline + 26 i18n = 291 passed）

新增 26 case 在 `backend/tests/test_i18n.py`：
- `TestIsValidKey`：5 case（注册 key 通过 / 未注册拒绝 / 防御性错误）
- `TestErrorResponse`：4 case（基础字段填充 / 中文降级 / 无参数保模板 / 未知 key 防御）
- `TestFallbackMessagesConsistency`：3 case（所有 key 有 fallback / 无孤儿条目 / 跨域一致）
- `TestKeyCoverage`：1 case（全 domain 有 key）
- `TestDeviceRouterI18n` / `TestInterfaceRouterI18n` / `TestVlanRouterI18n` / `TestAssetRouterI18n` / `TestBackupRouterI18n` / `TestBatchRouterI18n` / `TestExecuteRouterI18n`：各 router 错误场景带 key

**回归**：265 + 26 = **291 passed**, 23 skipped（**未破坏 v2.5.0 全部测试**）

### qa-frontend 自动化测试

- **lint** + **type-check** + **build**: 全过（vue-i18n v9 类型正确）
- **vitest**: 33 baseline + 20 i18n = **53 case** 全过
- **playwright**: 37 baseline + 5 i18n-switch = **42 e2e** 全过

### 真机集成测试（.177 Test-Switch-177）

手动 MCP 浏览器验证（`localhost:5173`）：

```text
# 1. 默认中文（localStorage 空）
访问 http://localhost:5173/ → "总览 / 运维操作 / 运营管理 / 排查诊断" + 切换按钮"中 | EN"
"网络运维总览 / 7 台设备 · 7 在线 · — 接口待采集 / 在管设备 / 在线设备 / 今日操作 / 刷新 / 新建任务"

# 2. 点击切换按钮 → 切到英文
"Dashboard / Operations / Management / Troubleshooting" + 切换按钮"中 | EN"（EN 高亮）
"Network Operations Overview / 7 devices · 7 online · — interfaces pending / Managed Devices / Online Devices / Today's Operations / Refresh / New Task"

# 3. 刷新页面 → 英文保持
localStorage: {"locale": "en-US"} 保留 → 重新渲染英文
```

---

## 7. 关键 commit 序列（14 个）

| # | commit | 主题 |
|---|---|---|
| 1 | `b9a7b8c` | chore(frontend): vue-i18n v9 集成骨架 + 4 smoke test (Task 1) |
| 2 | `c0d6902` | feat(frontend): 顶导加中英切换按钮 + localStorage 持久化 (Task 2) |
| 3 | `b88b8fa` | refactor(frontend): App.vue 顶导三大组 + AppFooter.vue i18n 化 (Task 3) |
| 4 | `7badae8` | feat(frontend): utils/status.js + api/index.js i18n 化 (Task 4) |
| 5 | `ea19ee7` | refactor(frontend): Dashboard + Devices + Interfaces i18n 化 (Task 5) |
| 6 | `1c219c3` | refactor(frontend): CMDB + Backup i18n 化 (Task 6) |
| 7 | `951f882` | refactor(frontend): Batch + OpsTerminal + Logs + Topology + AIAssistant i18n 化 (Task 7) |
| 8 | `5944e2c` | refactor(frontend): 10 components i18n 化 + locales 全量翻译 (Task 8) |
| 9 | `f2b47fa` | feat(backend): APIResponse error_key 扩展 + 9 router 改造 (**Task 9, BREAKING schema**) |
| 10 | `69ab045` | chore(openspec): v26-i18n tasks 1-9 标记 [x] 验证通过 |
| 11 | `c6c309a` | test(frontend): vitest 33→53 case 含 5 组件 i18n 切换测试 (Task 10) |
| 12 | `6c6f030` | test(frontend): playwright 37→42 e2e 含 5 i18n 切换测试 (Task 11) |
| 13 | `7ebfcca` | fix(backend): conftest 显式 import app.models 修复 test_task_manager (Task 12.1) |
| 14 | `28faec3` | fix(backend): conftest import 顺序修复 TestClient 'module is not callable' |

合计 14 个 commit。

---

## 8. 升级检查清单

- [ ] 拉取最新代码：`git pull origin main`
- [ ] 重新构建镜像：`docker compose -f docker-compose.dev.yml build`
- [ ] 启动 split 3 容器（默认模式）：`docker compose -f docker-compose.dev.yml up -d`
- [ ] 验证 3 容器运行：`docker compose -f docker-compose.dev.yml ps`
- [ ] 访问前端 `http://localhost:5173`，看到右上角「中 | EN」按钮
- [ ] 点击切换，验证文案变英文 / 刷新保持英文
- [ ] 跑 qa-backend：`docker compose -f docker-compose.dev.yml --profile qa up qa-backend`（应过 291 passed）
- [ ] 跑 qa-frontend：`docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`（应过 lint + build + 53 vitest + 42 playwright）
- [ ] （可选）真机 e2e：MCP 浏览器验证切换按钮

---

## 9. 已知问题

无（v2.6.0 review 通过）

---

## 10. 后续

v2.6 是 v3.0 VPC 起步的 **i18n 基础设施前置**。v3.0 起将开始 SDN + etcd 协调 + 监控容器拆解。

- 下一发版: v3.0（VPC + 监控容器 + i18n 拓展 4 语言）
- 当前 backlog: 见 [VERSION-ROADMAP.md §11 backlog](VERSION-ROADMAP.md#11-backlog)
