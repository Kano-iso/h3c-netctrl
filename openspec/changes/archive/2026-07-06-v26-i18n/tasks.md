# v2.6.0 i18n（中英切换）

## Why

v2.5.0 P1 工程化收口后 3 容器架构稳定，但 UI 与后端错误仍为中文单语。需求：导航栏右上角加中英切换按钮，扫遍全项目（前端 11 views + 10 components + App + Footer + 后端 routers error + 测试断言），做好中英切换，别漏了点。

详见 [proposal.md](proposal.md) / [design.md](design.md) / [specs/](specs/)。

---

## 任务分解

### 1. vue-i18n-integration 骨架

- [x] 1.1 装 `vue-i18n@^9.x`，`package.json` 加依赖
- [x] 1.2 `frontend/src/i18n/` 目录创建（index.js + zh-CN.js + en-US.js）
- [x] 1.3 `main.js` 注入 `app.use(i18n)`，locale 默认 `zh-CN`
- [x] 1.4 `frontend/src/__tests__/Smoke.spec.js` 加 1 个 i18n smoke test（实例创建 + 切换响应式）

**Commit**: `b9a7b8c chore(frontend): vue-i18n v9 集成骨架 + 4 smoke test`
**Spec**: [specs/vue-i18n-integration/spec.md](specs/vue-i18n-integration/spec.md)
**验证**: ✅ qa-frontend vitest 33+1=34 case / 0 failed / qa-backend 265 baseline 不变

### 2. locale 切换 UI + 持久化

- [x] 2.1 `frontend/src/stores/locale.js`（pinia store，useI18n 桥接）
- [x] 2.2 App.vue 顶导右侧工具栏加 `中 | EN` 切换按钮（K 用户头像前）
- [x] 2.3 main.js 启动时从 localStorage 还原 locale
- [x] 2.4 locale 变化时自动持久化到 localStorage

**Commit**: `c0d6902 feat(frontend): 顶导加中英切换按钮 + localStorage 持久化 (v26-i18n)`
**Spec**: [specs/vue-i18n-integration/spec.md](specs/vue-i18n-integration/spec.md)
**验证**: ✅ 浏览器实测点 EN 切英文，刷新保持 / vitest 34+2=36 case

### 3. App.vue + AppFooter.vue i18n

- [x] 3.1 App.vue 三大功能组 label + desc + 顶导 `总览` / 右侧工具栏 aria-label
- [x] 3.2 AppFooter.vue 4 列链接 + 版权行 + 介绍
- [x] 3.3 locales 加 `app.*` / `nav.*` / `footer.*` key

**Commit**: `b88b8fa refactor(frontend): App.vue 顶导三大组 + AppFooter.vue i18n 化 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ grep 验证 0 硬编码中文（除注释）/ vitest 36 / playwright 37

### 4. utils/status.js + api/index.js

- [x] 4.1 `utils/status.js` 重构：状态文案改用 `$t()`
- [x] 4.2 `api/index.js` axios 错误处理：用 `error_key` 查 i18n，fallback 到 `error`
- [x] 4.3 locales 加 `status.*` + `error.*` key（覆盖后端返的 error_key）

**Commit**: `7badae8 feat(frontend): utils/status.js + api/index.js i18n 化 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ 切换英文后状态显示英文 / 错误 toast 显示英文

### 5. Dashboard + Devices + Interfaces 核心 view

- [x] 5.1 Dashboard.vue：标题 / KPI 标签 / 卡片 / 快速入口 / 最近操作
- [x] 5.2 Devices.vue：列表表头 / 操作按钮 / Modal 触发 / 搜索占位
- [x] 5.3 Interfaces.vue：列表 / VLAN 标签 / L2/L3 状态 / 操作按钮
- [x] 5.4 locales 加 `dashboard.*` / `device.*` / `interface.*` key

**Commit**: `ea19ee7 refactor(frontend): Dashboard + Devices + Interfaces i18n 化 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ 切换英文后 3 个 view 全部英文 / qa-frontend 全过

### 6. CMDB + Backup + VLAN 业务 view

- [x] 6.1 CMDB.vue：资产列表 / 标签 / 操作 / 编辑 modal 触发
- [x] 6.2 Backup.vue：备份列表 / 状态 / 操作 / 锁定
- [x] 6.3 VLAN 部分（在 Interfaces.vue 内 modal + 工具栏）
- [x] 6.4 locales 加 `cmdb.*` / `backup.*` / `vlan.*` key

**Commit**: `1c219c3 refactor(frontend): CMDB + Backup i18n 化 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ 切换英文后 3 个 view 全部英文

### 7. Batch + OpsTerminal + Logs + Topology + AIAssistant 次要 view

- [x] 7.1 Batch.vue：批量执行表单 / 结果展示
- [x] 7.2 OpsTerminal.vue：终端 / 命令历史 / 多命令
- [x] 7.3 Logs.vue：日志列表 / 筛选 / 详情
- [x] 7.4 Topology.vue：拓扑视图（占位）
- [x] 7.5 AIAssistant.vue：AI 助手（占位）
- [x] 7.6 locales 加 `batch.*` / `ops.*` / `log.*` / `topology.*` / `ai.*` key

**Commit**: `951f882 refactor(frontend): Batch + OpsTerminal + Logs + Topology + AIAssistant i18n 化 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ 切换英文后 5 个 view 全部英文

### 8. 10 components i18n

- [x] 8.1 ConfirmModal / PageHeader / Select（基础组件）
- [x] 8.2 DeviceFormModal / AssetEditModal / Ipv4AddressEditModal / VpnInstanceBindModal（表单 modal）
- [x] 8.3 BackupListModal / BackgroundTaskPanel（业务 modal）
- [x] 8.4 locales 补全 `component.*` / `form.*` / `modal.*` key

**Commit**: `5944e2c refactor(frontend): 10 components i18n 化 + locales 全量翻译 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: ✅ 所有 modal 切换英文后内容/按钮全部英文

### 9. 后端 i18n_key + APIResponse 扩展

- [x] 9.1 `backend/app/schemas.py` APIResponse 加 `error_key` + `error_params` 字段
- [x] 9.2 `backend/app/i18n_keys.py`（新建）：≥ 80 key 集中表 + `is_valid_key()` + `error_response()` helper
- [x] 9.3 `backend/app/routers/device.py` 改造：所有 error 加 error_key
- [x] 9.4 `backend/app/routers/interface.py` 改造
- [x] 9.5 `backend/app/routers/vlan.py` 改造
- [x] 9.6 `backend/app/routers/asset.py` 改造（CMDB）
- [x] 9.7 `backend/app/routers/backup.py` 改造
- [x] 9.8 `backend/app/routers/batch.py` 改造
- [x] 9.9 `backend/app/routers/execute.py` 改造
- [x] 9.10 `backend/app/routers/log.py` 改造
- [x] 9.11 `backend/app/routers/dashboard.py` 改造（如有）
- [x] 9.12 后端 10 个单测：key 集中表完整性 / error_response helper / 各 router 错误场景带 key

**Commit**: `f2b47fa feat(backend): APIResponse error_key 扩展 + 9 router 改造 (v26-i18n Task 9, BREAKING schema)`
**Spec**: [specs/backend-i18n-key/spec.md](specs/backend-i18n-key/spec.md)
**验证**: ✅ qa-backend 265 → 291+ passed / 0 failed

### 10. vitest 断言更新 + 5 i18n 测试

- [ ] 10.1 `Smoke.spec.js` + 1 个 i18n 切换测试
- [ ] 10.2 `Dashboard.spec.js` 6 case 断言同步（默认中文不变）+ 1 i18n 测试
- [ ] 10.3 `Devices.spec.js` 6 case + 1 i18n 测试
- [ ] 10.4 `Interfaces.spec.js` 6 case + 1 i18n 测试
- [ ] 10.5 `Backup.spec.js` 6 case + 1 i18n 测试
- [ ] 10.6 `CMDB.spec.js` 6 case + 1 i18n 测试
- [ ] 10.7 1 个 i18n 专项测试：localStorage 持久化 + 响应式 + fallback + 默认值

**Commit**: `test(frontend): vitest 33 → 38+ case 含 5 i18n 切换测试 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: qa-frontend vitest 38+ case / 0 failed

### 11. playwright 断言更新 + 5 i18n e2e

- [ ] 11.1 8 个 e2e 文件：默认 locale 中文断言不变 + 切英文后断言英文
- [ ] 11.2 新增 `i18n-switch.spec.js`：5 case（切换按钮可见 / 切换后文案变 / localStorage 持久化 / 后端 key 翻译 / fallback）

**Commit**: `test(frontend): playwright 37 → 42+ e2e 含 5 i18n 切换测试 (v26-i18n)`
**Spec**: [specs/frontend-i18n-migration/spec.md](specs/frontend-i18n-migration/spec.md)
**验证**: qa-frontend playwright 42+ case / 0 failed

### 12. v2.6.0 发版闭环

- [ ] 12.1 qa-backend 全量回归（275+ passed / 0 failed）
- [ ] 12.2 qa-frontend 完整流程（lint → build → vitest 38+ → playwright 42+）
- [ ] 12.3 真机 .177 集成：切英文后 UI 显示英文（手动 MCP 浏览器验证）
- [ ] 12.4 `docs/i18n-guide.md`（新建，翻译 key 命名规范 + 新增条目流程 + 中英文风格指引）
- [ ] 12.5 `RELEASE-NOTES-v2.6.0.md`（顶部 BREAKING 标注 APIResponse.error_key 字段类型）
- [ ] 12.6 `VERSION-ROADMAP.md` §v2.6 章节 + §1 全景表加 1 行
- [ ] 12.7 `README.md` 顶部版本表 + 当前架构 + 技术栈 vue-i18n
- [ ] 12.8 change archive（`git mv openspec/changes/v26-i18n/ → archive/2026-07-XX-v26-i18n/`）
- [ ] 12.9 git tag v2.6.0 + push（**需用户确认**）

---

## 测试 baseline 目标

| 维度 | v2.5.0 baseline | v2.6.0 目标 |
|---|---|---|
| qa-backend pytest | 265 passed | **275+ passed**（+ 10 i18n key） |
| qa-frontend vitest | 33 case | **38+ case**（+ 5 i18n 切换） |
| qa-frontend playwright | 37 case | **42+ case**（+ 5 i18n e2e） |
| 前端 i18n 覆盖率 | 0% | **100%**（11 views + 10 components + App + Footer + utils + api） |
| 后端 error_key 覆盖率 | 0% | **100%**（9 router 全部 error 场景） |
| 中英翻译条目 | 0 | **~400-500 key**（zh-CN + en-US 对齐） |
