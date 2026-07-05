## Why

v2.4.2.1 发版后 3 容器架构已稳定运行（225 单元测试 baseline + 真机 e2e 全过），但 [REVIEW-v242-3container-maturity.md](../../../docs/REVIEW-v242-3container-maturity.md) §4 暴露 6 项 P1 工程化遗留项，影响 split 模式性能、开发体验和测试覆盖率。v3.0 VPC 起步依赖 3 容器架构稳定，现在不收口后续会随 VPC 复杂度放大；故起 v2.5 集中收尾 P1，作为 v3.0 起步前置。

## What Changes

- **internal_api 加 5s TTL 本地缓存**：dashboard 跨容器调用 50ms → 10ms（缓存命中），降低 split 模式延迟开销
- **container split mode 设为默认**：`docker compose up` 默认起 3 容器（ctrl/config/data），monolith 走 `core` profile，避免开发环境漏测 split
- **vitest 组件测试 EACCES 排障 + 启用**：解决 v2.3 BLOCKED 的 EACCES 问题，目标 30+ case 覆盖关键 Vue 组件（Devices / Interfaces / Backup / CMDB）
- **Playwright 端到端 e2e**：替代手动 MCP 浏览器流程，CI 可跑，关键用户流程自动化覆盖（设备 CRUD / 接口配置 / 备份回滚）
- **ops-toolkit 新增 interface-config.sh**：vlan / access / trunk CLI 一键下发（高频操作无脚本，回退到 backend API 麻烦）
- **ops-toolkit 新增 task-monitor.sh**：task_id 轮询 status 直至终态（调试异步备份任务常用）

## Capabilities

### New Capabilities

- `internal-api-cache`: internal_api 本地缓存层（5s TTL，命中跳过 HTTP，降 split 模式延迟）
- `split-default-mode`: docker compose 默认起 3 容器 split 模式，monolith 走 `core` profile
- `playwright-e2e`: Playwright 端到端测试框架（替代手动 MCP 浏览器，CI 可跑）

### Modified Capabilities

- `add-vitest-component-tests`: v2.3 BLOCKED EACCES 排障 + 启用 vitest 组件测试（0 → 30+ case）
- `add-ops-toolkit`: 新增 interface-config.sh 和 task-monitor.sh 两个脚本（ops-toolkit 7 → 9 脚本）

## Impact

- **代码**：
  - `backend/app/internal_api.py`（缓存层注入）
  - `docker-compose.dev.yml`（profile 默认值翻转：backend 加 `core` profile，ctrl/config/data 移除 `split` profile 限制）
  - `frontend/package.json` + `frontend/src/__tests__/`（vitest 配置 + 测试文件）
  - `frontend/tests/e2e/`（Playwright 新建）
  - `ops-toolkit/scripts/interface-config.sh` + `ops-toolkit/scripts/task-monitor.sh`
- **API**：无破坏性变更（缓存透明，TTL 失效自动回源）
- **依赖**：新增 `playwright` 包（@vue/test-utils 已装但未跑）
- **文档**：
  - `docs/ops-toolkit.md` §4.8 interface-config.sh + §4.9 task-monitor.sh
  - `docs/QA-GUIDE.md` vitest 章节 + Playwright 章节
  - `VERSION-ROADMAP.md` §v2.5 章节
- **测试 baseline**：225 → 预计 255+（+30 vitest case）；E2E 0 → 8+ Playwright 场景
