## Context

v2.4.2.1 发版后 3 容器架构（ctrl/config/data）稳定运行，225 单元测试 baseline + 真机 e2e 全过。但 [REVIEW-v242-3container-maturity.md](../../../docs/REVIEW-v242-3container-maturity.md) §4 暴露 6 项 P1 工程化遗留项，分布在 3 个维度：

- **性能**：internal_api 跨容器调用延迟（dashboard 50ms vs monolith 10ms）
- **体验**：split mode 默认未启用 + vitest BLOCKED（v2.3 遗留） + Playwright 缺失
- **工具**：interface-config.sh 和 task-monitor.sh 缺失（高频操作无脚本）

**干系人**：
- 开发者：split mode 默认 + vitest + Playwright 影响日常开发体验
- 运维：2 个新脚本影响 ops-toolkit 工作流
- v3.0 VPC：依赖 3 容器架构稳定，缓存层是 VPC etcd 协调的前置模式

## Goals / Non-Goals

**Goals:**

- dashboard 跨容器调用 50ms → 10ms（缓存命中）
- split mode 设为默认（避免开发环境漏测 split）
- vitest 0 → 30+ case（解 EACCES）
- Playwright 0 → 8+ e2e 场景（CI 可跑）
- ops-toolkit 7 → 9 脚本（加 interface-config.sh + task-monitor.sh）

**Non-Goals:**

- 不做 Postgres 迁移（P3，v2.6+ 评估）
- 不做 SimpleNamespace 兼容层去掉（P2，下个版本）
- 不做 4 设备真机 e2e 完整版（P2）
- 不引入新业务能力（VPC 留 v3.0）

## Decisions

### 决策 1: internal_api 缓存策略 — TTL 5s + per-process dict

**方案**：在 `backend/app/internal_api.py` 加 process-local dict 缓存，key = (url, params, headers)，value = (timestamp, data)，TTL = 5s。仅缓存 GET 请求，POST/PUT/DELETE 透明不缓存。

**替代方案**：
- Redis：引入新依赖，ROI 低（5s 缓存命中即可）
- functools.lru_cache：不支持 TTL，参数不可哈希时失效
- HTTP Cache-Control：需要 ctrl/config/data 容器协同改造，工作量大

**理由**：dashboard 等接口对实时性要求不高（5s 内数据变化可接受），process-local 避免新依赖，TTL 5s 平衡命中率和新鲜度。

### 决策 2: split mode 设为默认 — profile 翻转

**方案**：
- `ctrl`/`config`/`data` 移除 `profiles: ["split"]` 限制（默认起）
- `backend` 加 `profiles: ["core"]`（仅显式 `--profile core` 时起 monolith）
- frontend `depends_on` 改为 `ctrl`（split 模式下 backend 不起）

**替代方案**：
- 保持现状 + 文档强调：开发者仍会忘记
- 加 CI 强制 split：治标不治本

**理由**：默认值翻转是最强约束，符合 12-factor "默认值即正确值" 原则。

**BREAKING**：已有脚本 `docker compose up -d` 行为变化（默认起 3 容器而非 monolith），需更新文档 + RELEASE-NOTES 显式标注。

### 决策 3: vitest EACCES 排障 — chown + npm ci

**方案**：
- `frontend/Dockerfile.qa` 中 `RUN chown -R node:node /app` 解决 EACCES
- 用 `npm ci` 替代 `npm install`（CI 友好，遵守 package-lock.json）
- vitest 配置：`vite.config.js` 加 `test:` 块 + `environment: 'happy-dom'`
- 30 case 覆盖：Devices / Interfaces / Backup / CMDB / Dashboard 5 个核心组件各 6 case

**替代方案**：
- 换 pnpm：引入新工具链，ROI 低
- 用 jest：与 vite 生态不一致

**理由**：v2.3 EACCES 是容器内权限问题，chown 是最直接解法；npm ci 是 CI 标准实践。

### 决策 4: Playwright — 独立 tests/e2e/ + qa-frontend 集成

**方案**：
- 新建 `frontend/tests/e2e/` 目录
- Playwright 配置 `webServer` 自动起 vite dev server + `baseURL`
- qa-frontend 容器加 `playwright` 包 + 浏览器二进制（`npx playwright install --with-deps chromium`）
- 8 个核心场景：设备 CRUD / 接口列表 / VLAN 创建 / 备份列表 / 备份创建 / CMDB 采集 / 仪表盘 / 登录
- qa-frontend 入口加 `test:e2e` step（lint → build → vitest → playwright）

**替代方案**：
- Cypress：生态类似但 Playwright 更现代 + 多浏览器
- puppeteer：低层 API，工作量大

**理由**：Playwright 是 2024+ 主流 e2e 框架，CI 友好，与 vite 集成成熟。

### 决策 5: interface-config.sh — 复用 backend API

**方案**：
- 调用 `POST /api/devices/{id}/vlans`（创建 VLAN）+ `PUT /api/devices/{id}/interfaces/{name}/config`（接口配置）
- 凭据从 .env 注入（同 paramiko-batch-exec.sh 模式）
- 支持 `--device test` 别名（默认 .177）
- 子命令：`vlan add/del`、`access set`、`trunk allow`

**替代方案**：
- 裸 SSH CLI：违反 qa规范（不裸写 SSH）
- 直接 NETCONF：复杂度高，复用 backend 已有逻辑

**理由**：复用 backend API 保证业务逻辑一致（trunk allowed VLANs SSH fallback 等），符合 ops-toolkit paramiko-batch-exec.sh 的"复用 backend"模式。

### 决策 6: task-monitor.sh — 轮询 + 终态退出

**方案**：
- 调用 `GET /api/tasks/{task_id}` 轮询 status
- 默认间隔 2s，超时 300s
- 终态（success/failed/cancelled）退出 + 返回最终结果 JSON
- 支持 `--follow` 持续输出进度

**替代方案**：
- WebSocket：引入新协议，ROI 低
- SSE：同上

**理由**：轮询简单可靠，符合 ops-toolkit "shell 工具" 定位。

## Risks / Trade-offs

- **缓存 5s 内数据陈旧** → dashboard 等非关键路径可接受；写操作不缓存（POST/PUT/DELETE 透明）
- **split mode 默认翻转破坏现有脚本** → RELEASE-NOTES 显式标注 BREAKING，提供 `--profile core` 回退路径
- **vitest chown 增加镜像构建时间** → 预估 +5s，可接受
- **Playwright 浏览器二进制增大 qa-frontend 镜像** → 预估 +300MB，可接受（CI 镜像）
- **interface-config.sh 复用 API 依赖 backend 在线** → 文档标注，离线场景用 paramiko-batch-exec.sh 兜底

## Migration Plan

1. **Task 1-2 (internal-api-cache)**：缓存层 + 单测 → 不影响现有行为（缓存透明）
2. **Task 3 (split-default-mode)**：profile 翻转 + 文档更新 → BREAKING，需通知用户
3. **Task 4-5 (vitest)**：Dockerfile.qa chown + 30 case → 不影响现有测试
4. **Task 6-7 (playwright)**：配置 + 8 场景 → 不影响现有测试
5. **Task 8 (interface-config.sh)**：新脚本 + 文档 → 独立新增
6. **Task 9 (task-monitor.sh)**：新脚本 + 文档 → 独立新增
7. **Task 10**：archive + RELEASE-NOTES + VERSION-ROADMAP §v2.5 + README 同步

**回退策略**：每个 Task 独立 commit，可单独 revert；split mode 翻转可通过 `--profile core` 回退。

## Open Questions

- Playwright 是否需要单独容器（qa-e2e）还是合并到 qa-frontend？倾向合并（共用 vite 构建）
- vitest 30 case 覆盖哪些组件？建议：Devices / Interfaces / Backup / CMDB / Dashboard 5 个核心组件各 6 case
