# RELEASE-NOTES-v2.4.2

**版本**: v2.4.2
**日期**: 2026-07-04
**主题**: 3 容器 + 双 qa + ops-toolkit 成熟度 review（QA 工程化 / 压测 / 报告）
**前序**: v2.4.1 (2026-07-03)

---

## 1. 主题

v2.4.2 = **v2.4.1 3 容器拆分实施 1 周后的成熟度 review + QA 工程化加固**。**不开 v2.5**，因为 review 报告结论是"v2.4.2 可发版，P0（vue-tsc）必须做"。

v2.4.2 包含 **3 个 change + 1 个 review 报告产出物**：

| change | 主题 | 状态 |
|---|---|---|
| v242-qa-and-tooling | ESLint 进 qa 容器 + ops-toolkit 默认 test 设备 + qa 规范改写 | ✅ archive |
| v242-perf-and-e2e | locust 压测 .177 + split 模式真机 e2e 8 场景 + MCP 浏览器 e2e | ✅ archive |
| v242-3container-review | 3 容器 + 双 qa + ops-toolkit 成熟度 review 报告 + P0 vue-tsc 实施 | ✅ archive |
| **产出物** | `docs/REVIEW-v242-3container-maturity.md` | ✅ |

---

## 2. 包含的 Changes（3 个 + 1 报告）

### Change 1：v242-qa-and-tooling（QA 工具完善）

#### 主线 1：前端 ESLint 进 qa 容器

**问题**：qa-frontend 容器只跑 `npm run build`，lint 错被 build 掩盖，存量代码无 lint 规范。

**实现**：
- `frontend/package.json`：加 `eslint@^8.57.0` + `eslint-plugin-vue@^9.33.0` + `lint: "eslint --ext .js,.vue src --max-warnings 0"`
- `frontend/.eslintrc.cjs`：extends `plugin:vue/vue3-essential` + 个人规则（v-for key / PascalCase / no-unused-vars）
- `frontend/.eslintignore`：dist / node_modules / *.config.js
- `frontend/Dockerfile.qa`：CMD 改 `lint && type-check && build`（v2.4.2 P0 加 type-check）

**验证**：
- 存量代码 0 error / 0 warning
- 故意加 unused import → lint 失败 → build 不跑
- 故意加错误类型 → type-check 失败 → build 不跑

#### 主线 2：ops-toolkit 默认 test 设备

**问题**：v2.3 vlan 100 教训：qa 工具"反复跑"特性，误连生产导致配置污染。

**实现**：
- `ops-toolkit/scripts/_lib.sh`：加 `_resolve_alias()` 设备名→IP 映射（test/leaf-03/leaf-04/spine-01 等）+ `DEFAULT_DEVICE=test` + `_print_device_banner()` 提示
- 6 脚本（check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch）入口加 `--device` 解析
- 显式生产 IP（.4/.5/.100）→ ⚠️ warn 日志，不阻止

**验证**：
- `check-host.sh`（不带参数）→ 指向 .177
- `--device test` → 指向 .177
- `--device leaf-04` → 解析为 .5
- `--device 192.168.100.5` → 显式生产 + warn

#### 主线 3：qa 规范.md 重写

**实现**：`.trae/rules/qa规范.md` 改写：
- §工具边界：lint（ESLint）+ type-check（vue-tsc）+ build（vite）分离
- §默认设备：强制 .177 / 禁止生产
- §MCP 浏览器：定位"小测试 / 单功能验证 / 排错"，不进 qa 容器

**关联文档**：`docs/ops-toolkit.md` + `docs/QA-GUIDE.md` 同步

---

### Change 2：v242-perf-and-e2e（压测 + 真机 e2e）

#### 主线 1：locust 压测 .177

**问题**：未量化 NETCONF / SSH 设备容量上限，并发高了盲猜易踩雷。

**实现**：
- `backend/tests/perf/locustfile.py`：定义 2 个 User 类
  - `NetconfConfigUser`：GET /api/devices/{id}/interfaces
  - `SshBackupUser`：POST /api/devices/{id}/backup
- `backend/tests/perf/scenarios/`：2 个并发压测脚本（100_concurrent_interfaces.sh / 50_concurrent_backup.sh）
- `backend/tests/perf/README.md`：压测 SOP + 阈值表 + 监控命令

**多档实测结果**（.177 单设备）：

| 场景 | 并发 | 60s 内 reqs | 失败率 | P99 | 结论 |
|---|---|---|---|---|---|
| NETCONF 接口查询 | 5 | 45 | 0% | 1.9s | ✅ 达标 |
| NETCONF 接口查询 | 10 | 80 | 5% | 8s | ⚠️ 临界 |
| NETCONF 接口查询 | 20 | 150 | 25% | 20s | ❌ |
| NETCONF 接口查询 | 100 | 88 | 60% | 45s | ❌（设备 max-session ~ 8） |
| SSH 备份 | 5 | 15 | 0% | 5s | ✅ |
| SSH 备份 | 10 | 31 | 0% | 9.6s | ✅ 达标 |
| SSH 备份 | 20 | 91 | 9% | 9.9s | ❌（设备 max-session ~ 16-20） |

**暴露 1 个 v2.4.1 bug**：monolith 模式 100 并发时 `sqlite lock` 错误走 internal_api 兜底。已记录进 v242-3container-review backlog。

#### 主线 2：split 模式真机 e2e 8 场景

**问题**：v2.4.1 13 个 integration test 跑 monolith 模式，split 模式 0 覆盖。

**实现**：`backend/tests/test_split_e2e_real.py`（@pytest.mark.integration）
- fixture 注入 3 容器 URL（E2E_CTRL_URL / E2E_CONFIG_URL / E2E_DATA_URL 环境变量 > 默认容器名）
- 8 场景（.177 单设备）：
  1. 设备列表（ctrl）
  2. 接口列表（config NETCONF get）
  3. running 备份（data SSH）
  4. 全量异步备份（split 端到端）
  5. 设备删除清理（split 调 data cleanup）
  6. Dashboard 聚合（ctrl 跨容器调 data 降级）
  7. 故障注入 data down → config 仍成功（用 Python docker SDK + /var/run/docker.sock 挂载）
  8. 故障注入 ctrl down → config 返明确错误
- **结果**：8 场景全 PASS，81.32s
- **缩到 .177 单设备**：4 设备真机版（.4/.5/.100）留 v2.5 backlog（review 报告 P2）

#### 主线 3：MCP 浏览器 split 模式 e2e

**实现**：MCP 浏览器手测 split 模式 UI 流程
- 起 3 容器 + frontend（VITE_SPLIT_MODE=true）
- 打开 `http://localhost:5173/#/cmdb` → 7 设备显示
- 点"全量备份" → 触发 taskStore.submitBatchBackup 串行提交 7 设备
- localStorage 验 task 创建（task 35-41 / 42-48）
- 等 status=success → 14/14 任务 success
- 截图存 `docs/screenshots/v2.4.2-mcp-e2e/`

---

### Change 3：v242-3container-review（成熟度 review + P0 vue-tsc）

**特殊**：本 change **只产出 review 报告 + 实施 P0**，**不写新业务代码**。

**产出物**：`docs/REVIEW-v242-3container-maturity.md`

**4 大块**：
1. **3 容器边界 review**：路由归属 / 数据归属 / 跨容器调用统计（10 internal_api 函数 / 4 router 引用 / 26 device_access 调用点）
2. **双 qa 成熟度 review**：qa-backend 214 passed / 34s / 覆盖模块；qa-frontend lint+type-check+build / 缺 vitest
3. **ops-toolkit 成熟度 review**：6 脚本频率 / 默认 test 设备 / 文档发现
4. **v2.5 候选 backlog**：P0 1 项 / P1 6 项 / P2 6 项 / P3 3 项

**总体评分**：
- 3 容器：**A-**（边界清晰、跨容器容错已验真机，缓存层 + 默认值还有优化空间）
- 双 qa：**B+**（qa-backend 稳定，qa-frontend 缺 vitest + vue-tsc）
- ops-toolkit：**A-**（6 脚本覆盖主要场景，默认 test 设备避免误连生产）

**P0 项实施**（review 报告阻塞 v2.4.2 发版）：
- **qa-frontend 加 vue-tsc 类型检查**（commit 37fac09）
  - `frontend/package.json`：vue-tsc@^2 + typescript@^5 devDeps + `type-check` 脚本
  - `frontend/tsconfig.json`：minimal 配置（allowJs=true, checkJs=false）
  - `frontend/Dockerfile.qa`：CMD 改 `lint && type-check && build`
  - 存量 0 type errors；故意加 .ts 错类型 → type-check 失败 → build 不跑（exit 2）

**新 spec**：`openspec/specs/review-report-process/spec.md` — 后续每个版本发版前都要出 review 报告。

---

## 3. 关联

- 前序 change: [v241-container-split](openspec/changes/archive/2026-07-03-v241-container-split/) + [v241-supplement](openspec/changes/archive/2026-07-03-v241-supplement/)
- 本次 3 个 change（v2.4.2）：
  - [v242-qa-and-tooling](openspec/changes/archive/2026-07-04-v242-qa-and-tooling/)
  - [v242-perf-and-e2e](openspec/changes/archive/2026-07-04-v242-perf-and-e2e/)
  - [v242-3container-review](openspec/changes/archive/2026-07-04-v242-3container-review/)
- 路线图: [VERSION-ROADMAP.md v2.4.2](VERSION-ROADMAP.md)
- Review 报告: [docs/REVIEW-v242-3container-maturity.md](docs/REVIEW-v242-3container-maturity.md)
- 压测报告: [docs/PERF-RESULTS-v2.4.2.md](docs/PERF-RESULTS-v2.4.2.md)

---

## 4. 测试 / 验证

### qa-backend（回归）

```
214 passed, 19 skipped, 10 warnings in 33.42s
```

**v2.4.1 → v2.4.2**：测试数不变（仍 214 passed），但 skip 数 11 → 19（integration test marker 调整）。

### qa-frontend（lint + type-check + build）

```
> eslint --ext .js,.vue src --max-warnings 0     # 0 error
> vue-tsc --noEmit                                # 0 type errors
> vite build                                       # ✓ built in 2.6s
```

### ops-toolkit（6 脚本默认行为）

- `check-host.sh`（不带参数）→ 192.168.100.177 ✓
- `check-host.sh --device test` → 192.168.100.177 ✓
- `check-host.sh --device leaf-04` → 192.168.100.5 ✓
- `check-host.sh --device 192.168.100.5` → 显式生产 + warn ✓

### split 模式真机 e2e（.177 单设备）

```
8 passed in 81.32s
```

### 压测（locust .177）

- 5 并发 NETCONF 接口：45 reqs / 0% fail / P99 1.9s ✓
- 10 并发 SSH 备份：31 reqs / 0% fail / P99 9.6s ✓

### MCP 浏览器 split 模式 e2e

- CMDB 全量备份流程：14/14 任务 success
- 截图存 `docs/screenshots/v2.4.2-mcp-e2e/`

---

## 5. 关键 commit 序列（9 个）

| commit | 说明 |
|---|---|
| `2ad6678` | feat(frontend-lint): qa-frontend 容器跑 lint + build (ESLint 8 + vue plugin) |
| `ff3c986` | feat(qa-tooling): 默认 test 设备 .177 + 设备名→IP 别名映射 |
| `be8d485` | docs(qa-spec): qa 规范重写 (lint+build / 默认 test 设备 / MCP 边界) |
| `c76ff47` | feat(perf): locust 压测 .177 NETCONF/SSH 多档并发 + 暴露设备容量上限 |
| `b2c002e` | test(split-e2e): split 模式真机 e2e 8 场景 .177 (含故障注入真机版) |
| `f71b22b` | docs(perf): MCP 浏览器 split 模式 CMDB 全量备份 e2e 截图 |
| `37fac09` | feat(frontend-typecheck): qa-frontend 加 vue-tsc 类型检查 (v242-3container-review P0) |
| `9ca314b` | chore(v2.4.2): review 报告 + 3 个 change proposal/design/specs (v2.4.2 收尾前) |
| 待 commit | chore(v2.4.2): archive 闭环 + RELEASE-NOTES + VERSION-ROADMAP |

---

## 6. 升级 / 回退

### 升级

```bash
git pull
docker compose -f docker-compose.dev.yml build qa-frontend qa-backend ops-toolkit
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend
# 预期：lint + type-check + build 三步全过
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest
# 预期：214 passed, 19 skipped
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit check-host.sh
# 预期：默认连 192.168.100.177
```

### 回退

```bash
git revert <v2.4.2 commits>
docker compose -f docker-compose.dev.yml build qa-frontend qa-backend ops-toolkit
# 行为恢复 v2.4.1（lint + build / ops-toolkit 无默认设备 / 无数 vue-tsc）
```

---

## 7. v2.5 Backlog 入口

review 报告 §4 列出 v2.5 候选 backlog，本节只列 P0/P1 摘要：

| 优先级 | 项 | 估时 |
|---|---|---|
| （已做） | qa-frontend 加 vue-tsc | — |
| P1 | internal_api 加本地缓存（5s TTL，dashboard 50ms → 10ms） | 1d |
| P1 | container split mode 设为默认（monolith 走 `core` profile） | 半天 |
| P1 | vitest 组件测试 EACCES 排障（用 chown / npm ci --no-save） | 1d |
| P1 | Playwright 端到端 e2e（自动版 MCP 浏览器） | 1d |
| P1 | 加 `interface-config.sh`（vlan/access/trunk CLI 一键下发） | 半天 |
| P1 | 加 `task-monitor.sh`（task_id → 轮询 status 直至终态） | 2h |

详见 [docs/REVIEW-v242-3container-maturity.md §4](docs/REVIEW-v242-3container-maturity.md#4-v25-候选-backlog)。
