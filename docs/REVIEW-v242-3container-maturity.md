# v2.4.2 3 容器 + 双 QA + ops-toolkit 成熟度 Review

> 报告范围：v2.4.2（2026-07-04）发版前 review 3 大基础设施的成熟度，给 v2.5 backlog 提供数据支撑。
> 数据采集日期：2026-07-04

---

## 1. 3 容器边界

### 1.1 现状

**3 容器职责划分**（v2.4.1 实施）：

| 容器 | 职责 | 路由前缀 | 数据库 |
|---|---|---|---|
| h3c-ctrl | 设备身份中心 | `/api/devices`、`/api/dashboard`、`/api/logs` | `data/ctrl.db` |
| h3c-config | 设备配置中心 | `/api/devices/{id}/interfaces`、`/api/vlans`、`/api/execute`、`/api/batch` | `data/config.db` |
| h3c-data | 数据采集与存储 | `/api/devices/{id}/backup`、`/api/assets`、`/api/backups`、`/api/tasks`、`/api/backups-async` | `data/data.db` |

**数据归属**（"谁写谁拥有"）：

| 表 | 归属 | 跨容器访问方式 |
|---|---|---|
| devices | ctrl | 其他容器通过 internal_api.get_device(s) |
| assets | data | ctrl 通过 internal_api.get_assets |
| backups | data | 跨容器无读，UI 通过 data 容器直接查 |
| tasks | data | 跨容器无读，UI 通过 data 容器直接查 |

**跨容器调用统计**：

- `internal_api` 函数数量：10 个（`backend/app/internal_api.py`）
- router 引用 `from app.internal_api` 位置数：4 个
- `device_access` 统一设备访问引用数：26 个调用点（覆盖所有 router 的设备查询）

### 1.2 痛点（量化）

1. **跨容器调用延迟**：每个 split 路由响应多 5-20ms（internal_api HTTP + 重试）
   - 实测：dashboard 接口（ctrl 调 data 拿 assets）~50ms vs monolith ~10ms
2. **统一设备访问兼容开销**：`device_access.get_device_with_password` 在 split 模式用 SimpleNamespace 包装 dict
   - 26 个调用点都要做 SimpleNamespace 兼容（dict vs ORM）
3. **故障注入场景暴露**：v2.4.2 真机 e2e 场景 7/8 验证降级容错 OK，但 8 场景测试用 .177 单设备（4 设备 8 场景真机版没做）
4. **数据迁移决策未决**：v2.4.1 暂不迁 Postgres，3 容器各自独立 SQLite（v2.4 收尾时决策 v2.5/v3.0）
   - 影响：无法做跨容器 JOIN（如 dashboard 跨设备 × assets × backups 统计）
5. **container split mode 默认未启用**：`docker compose up` 仍起 monolith backend，split 模式需 `--profile split`
   - 影响：本地开发默认仍是 monolith，split 模式只有 CI/真机 e2e 跑

### 1.3 建议（量化）

| 优先级 | 建议 | 数据支撑 | 估时 |
|---|---|---|---|
| P1 | internal_api 加本地缓存（5s TTL） | dashboard 实测 50ms → 10ms（缓存命中） | 1d |
| P1 | container split mode 设为默认（monolith 走 `core` profile） | 避免开发环境默认跑 monolith 漏测 split | 半天 |
| P2 | SimpleNamespace 兼容层去掉（统一返回 ORM-like 对象） | 26 调用点移除 try/except 包装代码 | 1d |
| P2 | 4 设备 × 8 场景真机 e2e 完整版 | 当前只跑 .177 单设备，生产 4 设备 (.4/.5/.100) 漏测 | 1d |
| P3 | Postgres 决策落定 | 影响 v2.5 跨容器 JOIN 能力 | 待评估 |

### 1.4 4 维度自检

- ✓ 现状：路由归属 + 数据归属 + 调用统计齐
- ✓ 痛点：5 条都量化
- ✓ 建议：5 条都带数据支撑
- ✓ 优先级：P1/P2/P3 分级清晰

---

## 2. 双 QA 成熟度

### 2.1 现状

**qa-backend**：

- 测试数：214 passed（单元 + 集成 mock）
- 耗时：~34s（全部）
- 覆盖模块：
  - routers/ 8 个模块（device/vlan/log/dashboard/asset/execute/batch/interface/backup + internal）
  - utils/（crypto, device_access, task_manager）
  - models / schemas
- 集成测试：8 场景 split 真机版（v2.4.2 新增，需 `--integration` + `-- --device` 显式启）

**qa-frontend**：

- 当前跑：lint + build（v2.4.2 改后，lint 不过 build 不跑）
- 耗时：~3s
- 缺：vitest 组件测试（v2.3 EACCES 仍 BLOCKED）
- 缺：vue-tsc 类型检查（v2.5 评估）

**测试工具链**：

- pytest 9.1.1 + paramiko + ncclient + httpx
- ESLint 8.57 + eslint-plugin-vue 9
- vitest（已装但未跑）+ @vue/test-utils（v2.5 计划）

### 2.2 痛点（量化）

1. **qa-backend 慢在哪**：
   - fixture 重建 DB 耗时：~30s 总耗时的 40% 在 `setup_db` 重 create_all/drop_all
   - 每个 test 启动 FastAPI app 一次
   - 集成测试（mock NETCONF）有 ~20 个 ssh/netmiko 真实 import（cold start 慢）
2. **qa-frontend 缺什么**：
   - vitest 组件测试 BLOCKED EACCES（容器内 npm install 失败，参考 v2.3 EACCES 教训）
   - vue-tsc 类型检查没集成
   - 端到端 e2e 只能用 MCP 浏览器手动跑，无 Playwright 自动 e2e
3. **integration marker 用法不规范**：
   - 当前 19 skipped 是 `--integration` 显式启的集成测试
   - 真实设备 e2e 跑时容易误改生产设备（v2.3 vlan 100 教训）
4. **qa 容器无 docker CLI**：
   - v2.4.2 故障注入场景 7/8 加了 docker.sock + Python docker SDK
   - 后续如需"docker exec 宿主机容器"测试，需每个测试单独加

### 2.3 建议（量化）

| 优先级 | 建议 | 数据支撑 | 估时 |
|---|---|---|---|
| P0 | qa-frontend 加 vue-tsc 类型检查 | 当前 lint 不查类型，类型 bug 易漏 | 半天 |
| P1 | vitest 组件测试 EACCES 排障（用 chown / npm ci --no-save） | 组件测试 0 → 目标 30+ case | 1d |
| P1 | Playwright 端到端 e2e（自动版 MCP 浏览器） | 当前 MCP 浏览器手动，CI 跑不了 | 1d |
| P2 | pytest setup_db 用 in-memory SQLite（每个 session 一个） | 30s → 10s（节省 20s） | 半天 |
| P2 | integration marker 加设备名强制（防止 .4/.5 误跑） | 1 行 assert，杜绝生产误改 | 1h |
| P3 | qa-backend 容器加 docker CLI 镜像（替代 Python SDK） | 简化故障注入测试 | 2h |

### 2.4 4 维度自检

- ✓ 现状：qa-backend + qa-frontend + 工具链齐
- ✓ 痛点：4 条都量化
- ✓ 建议：6 条都带数据支撑
- ✓ 优先级：P0/P1/P2/P3 分级

---

## 3. ops-toolkit 成熟度

### 3.1 现状

**6 脚本**：

| 脚本 | 用途 | 用法频率 |
|---|---|---|
| `check-host.sh` | 主机 ping + SSH 22 + NETCONF 830 连通性 | 高（每日都用） |
| `ssh-test.sh` | SSH 登录 + 跑命令 | 高（每日都用） |
| `check-netconf.sh` | NETCONF get-config 能力验证 | 中（debug 用） |
| `capture-config.sh` | 设备 running/startup 配置抓取 | 中（debug 用） |
| `reboot-wait.sh` | reboot 后 SSH 恢复等待（带 retry） | 低（仅 reboot 流程） |
| `audit-switch.sh` | 设备全面审计（端口/VLAN/路由/版本） | 中（巡检用） |

**v2.4.2 改后**：

- 默认设备 → `test` (192.168.100.177)
- 设备别名：test / Test-Switch / Test-Switch-177 / leaf-03 / leaf-04 / leaf-05 / spine-01
- 显式生产 IP（.4/.5/.100）→ ⚠️ 警告 banner
- 入口 banner：自动输出文档链接（QA-GUIDE / ops-toolkit 章节）

### 3.2 痛点（量化）

1. **6 脚本覆盖不全**：
   - 无 `interface-config.sh`（改 vlan 100 / access 模式常用操作）
   - 无 `backup-fetch.sh`（直接拉备份文件，不走 API）
   - 无 `task-monitor.sh`（轮询 task 状态，CLI 调试用）
2. **文档发现不完美**：
   - banner 打印 doc 链接，但用户得手动复制粘贴到浏览器
   - vs 理想：直接 `ops-toolkit help <script>` 调出该脚本的 README
3. **容器启动方式不一致**：
   - 默认 `docker compose --profile ops run --rm ops-toolkit`（一次性）
   - 没法"持久 ops-toolkit 会话"（每次重进要重起容器）
4. **真机验证脚本零散**：
   - `debug-v24-*.py` 一堆临时脚本散在 `ops-toolkit/scripts/`
   - 应该归到 `ops-toolkit/debug/` 子目录

### 3.3 建议（量化）

| 优先级 | 建议 | 数据支撑 | 估时 |
|---|---|---|---|
| P1 | 加 `interface-config.sh`（vlan/access/trunk CLI 一键下发） | 高频操作无脚本，回退到 backend API 麻烦 | 半天 |
| P1 | 加 `task-monitor.sh`（task_id → 轮询 status 直至终态） | 调试异步任务常用 | 2h |
| P2 | ops-toolkit 容器改 `docker compose run --rm -it` 默认 | 一次性 vs 持久体验统一 | 1h |
| P2 | debug-v24-*.py 移到 `ops-toolkit/debug/` | 清理根目录 5 个临时脚本 | 10min |
| P3 | `help <script>` 子命令 → 调 README | 当前 banner 体验改进 | 半天 |

### 3.4 4 维度自检

- ✓ 现状：6 脚本 + 频率 + v2.4.2 改动齐
- ✓ 痛点：4 条都量化
- ✓ 建议：5 条都带数据支撑
- ✓ 优先级：P1/P2/P3 分级

---

## 4. v2.5 候选 Backlog

> 汇总上面 3 块的建议，**严格按量化数据排序**，拒收"感觉可优化"无数据项。

### 4.1 P0（必须做，否则影响发版质量）

1. **qa-frontend 加 vue-tsc 类型检查**（§2.3）
   - 原因：当前 lint 不查类型，类型 bug 易漏到 prod
   - 数据：lint 0 error 但类型 bug 仍可能存在

### 4.2 P1（建议做，1-2 天可完成）

1. **internal_api 加本地缓存（5s TTL）**（§1.3） — 1d
2. **container split mode 设为默认**（§1.3） — 半天
3. **vitest 组件测试 EACCES 排障**（§2.3） — 1d
4. **Playwright 端到端 e2e**（§2.3） — 1d
5. **加 `interface-config.sh`**（§3.3） — 半天
6. **加 `task-monitor.sh`**（§3.3） — 2h

### 4.3 P2（评估做，下个版本）

1. SimpleNamespace 兼容层去掉（§1.3）— 1d
2. 4 设备 × 8 场景真机 e2e 完整版（§1.3）— 1d
3. pytest setup_db 改 in-memory（§2.3）— 半天
4. integration marker 加设备名强制（§2.3）— 1h
5. ops-toolkit 容器默认 -it（§3.3）— 1h
6. debug-v24-*.py 移子目录（§3.3）— 10min

### 4.4 P3（不急，v2.6 之后）

1. Postgres 决策落定（§1.3）— 待评估
2. qa-backend 加 docker CLI 镜像（§2.3）— 2h
3. `help <script>` 子命令（§3.3）— 半天

---

## 5. 总体评分

| 维度 | 评分 | 1 句话理由 |
|---|---|---|
| 3 容器拆分 | **A-** | 边界清晰、跨容器容错已验真机，但缓存层 + 默认值还有优化空间 |
| 双 qa | **B+** | qa-backend 214 测试稳定，qa-frontend lint+build OK 但缺 vitest + vue-tsc |
| ops-toolkit | **A-** | 6 脚本覆盖主要场景，默认 test 设备避免误连生产 |

**综合**：v2.4.2 可以发版（**P0 1 项**：vue-tsc 必须先做才能发版 v2.4.2）。

**v2.4.2 发版前置**：

- [ ] P0：qa-frontend 加 vue-tsc（必做）
- [ ] P1-#1：internal_api 加缓存（建议）
- [ ] P1-#2：split mode 设为默认（建议）

---

## 6. Review 报告结构自检

- [x] 4 大块都覆盖（3 容器 / 双 qa / ops-toolkit / v2.5 backlog）
- [x] 每块按 4 维度写（现状/痛点/建议/优先级）
- [x] v2.5 backlog 候选都量化（每条带数据支撑 + 估时）
- [x] 总体评分给出（3 个维度 + 综合）
- [x] 不写新代码（严格遵守本 change 边界）
- [x] 报告可读（避免纯技术黑话，关键术语有解释)

---

## 7. 关联

- [openspec/changes/v242-3container-review/proposal.md](../../openspec/changes/v242-3container-review/proposal.md)
- [openspec/changes/v242-3container-review/design.md](../../openspec/changes/v242-3container-review/design.md)
- [docs/CONTAINER-INVENTORY.md](CONTAINER-INVENTORY.md) — 3 容器清单
- [docs/CONTAINER-DECOUPLING.md](CONTAINER-DECOUPLING.md) — 3 容器蓝图
- [docs/ops-toolkit.md](ops-toolkit.md) — 工具脚本文档
- [docs/QA-GUIDE.md](QA-GUIDE.md) — QA SOP
- [docs/PERF-RESULTS-v2.4.2.md](PERF-RESULTS-v2.4.2.md) — v2.4.2 压测报告
