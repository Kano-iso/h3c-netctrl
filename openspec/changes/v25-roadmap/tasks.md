## 1. internal-api-cache（缓存层）

- [x] 1.1 在 `backend/app/internal_api.py` 加 process-local dict 缓存（key=url+params+headers，value=timestamp+data，TTL=5s，仅 GET）
- [x] 1.2 加 `clear_cache()` 函数 + 单元测试（缓存命中 / 过期回源 / 写操作不缓存 / 不同 params 隔离 / clear 生效）
- [x] 1.3 pytest fixture 调用 `clear_cache()` 避免测试间污染

**Commit**: `db9799f` feat(internal-api): GET 请求 5s TTL 本地缓存 + 8 单元测试
**测试**: qa-backend 233 passed (225 baseline + 8 new) / 23 skipped / 0 failed

## 2. split-default-mode（profile 翻转，BREAKING）

- [ ] 2.1 `docker-compose.dev.yml` 翻转 profile：ctrl/config/data 移除 `profiles: ["split"]`，backend 加 `profiles: ["core"]`
- [ ] 2.2 frontend `depends_on` 改为 ctrl + `frontend/vite.config.js` 加双模式 proxy（`VITE_API_MODE=split|core`）
- [ ] 2.3 `README.md` 快速启动章节更新 + `.env.example` 加 `VITE_API_MODE=split`

## 3. vitest EACCES 排障 + 框架配置

- [ ] 3.1 `frontend/Dockerfile.qa` 加 `RUN chown -R node:node /app` 解决 EACCES
- [ ] 3.2 装 `vitest` / `@vue/test-utils` / `happy-dom` + `vite.config.js` 加 `test:` 块 + `package.json` 加 `test:unit` script
- [ ] 3.3 qa-frontend 入口加 `test:unit` step（lint → build → vitest，build 不过 vitest 不跑）+ 1 个 smoke test 验证

## 4. vitest 30 case 覆盖 5 核心组件

- [ ] 4.1 `src/__tests__/Devices.spec.js`（6 case：列表加载 / 创建 / 编辑 / 删除 / 连接测试 / 搜索过滤）
- [ ] 4.2 `src/__tests__/Interfaces.spec.js`（6 case：列表加载 / L2-L3 切换 / IP 编辑 / VPN 绑定 / 解绑 / 分页）
- [ ] 4.3 `src/__tests__/Backup.spec.js`（6 case：列表加载 / 创建 / 锁定 / 解锁 / 回滚 / 下载）
- [ ] 4.4 `src/__tests__/CMDB.spec.js`（6 case：列表加载 / 单设备采集 / 编辑资产 / 状态筛选 / 位置更新 / 标签管理）
- [ ] 4.5 `src/__tests__/Dashboard.spec.js`（6 case：统计加载 / 最近操作 / 最近告警 / 图表渲染 / 跳转 / 刷新）

## 5. Playwright 配置 + qa-frontend 集成

- [ ] 5.1 装 `playwright` + Chromium 二进制 + `frontend/playwright.config.js`（webServer 自动起 vite + baseURL）
- [ ] 5.2 `frontend/Dockerfile.qa` 加 playwright 安装 + entrypoint 加 `test:e2e` step（lint → build → vitest → e2e）
- [ ] 5.3 `frontend/tests/e2e/mocks/` 公共 mock 框架（route interception，与 Pydantic schema 对齐）

## 6. Playwright 8 e2e 场景

- [ ] 6.1 `tests/e2e/devices-crud.spec.js`（设备 CRUD 全流程）
- [ ] 6.2 `tests/e2e/interfaces-list.spec.js`（接口列表 + L2/L3 状态展示）
- [ ] 6.3 `tests/e2e/vlan-create-delete.spec.js`（VLAN 创建 + 删除）
- [ ] 6.4 `tests/e2e/backup-list-create.spec.js`（备份列表 + 单设备创建）
- [ ] 6.5 `tests/e2e/cmdb-asset-refresh.spec.js`（CMDB 资产采集）
- [ ] 6.6 `tests/e2e/dashboard-load.spec.js`（仪表盘加载 + 统计展示）
- [ ] 6.7 `tests/e2e/login-flow.spec.js`（登录流程，如有 auth）
- [ ] 6.8 `tests/e2e/backup-restore.spec.js`（备份回滚流程）

## 7. interface-config.sh（ops-toolkit 第 8 脚本）

- [ ] 7.1 `ops-toolkit/scripts/interface-config.sh`（子命令：`vlan add/del` / `access set` / `trunk allow`，复用 backend API）
- [ ] 7.2 凭据从 .env 注入（`DEVICE_USERNAME` / `DEVICE_PASSWORD`），禁止 admin fallback，API 不可达降级提示
- [ ] 7.3 单元测试（mock backend API）+ 真机集成测试（.177 创建/删除 VLAN）
- [ ] 7.4 `docs/ops-toolkit.md` §4.8 章节回写（用途 / 示例 / 参数 / schema / pytest 覆盖 / 限制）

## 8. task-monitor.sh（ops-toolkit 第 9 脚本）

- [ ] 8.1 `ops-toolkit/scripts/task-monitor.sh`（轮询 `GET /api/tasks/{task_id}`，间隔 2s，超时 300s，`--follow` 模式）
- [ ] 8.2 单元测试 + 真机集成测试（异步备份任务监控，验证终态退出 + 超时退出 + follow 输出）
- [ ] 8.3 `docs/ops-toolkit.md` §4.9 章节回写

## 9. v2.5.0 发版闭环

- [ ] 9.1 `qa-backend` 全量回归（225 → 预计 255+ passed，baseline 对比 0 failed）
- [ ] 9.2 `qa-frontend` 完整流程（lint → build → vitest → playwright 全过）
- [ ] 9.3 真机集成（.177 跑 `interface-config.sh` + `task-monitor.sh`）
- [ ] 9.4 `RELEASE-NOTES-v2.5.0.md`（顶部 **BREAKING** 标注 split 默认 + commit 序列 + 测试统计 + 真机示例）
- [ ] 9.5 `VERSION-ROADMAP.md` 加 §v2.5 章节 + §1 全景表加 1 行
- [ ] 9.6 `README.md` 顶部版本表 + 当前架构表 + QA 章节（split 默认 / vitest / playwright）同步
- [ ] 9.7 change archive（`git mv openspec/changes/v25-roadmap/ → archive/2026-07-XX-v25-roadmap/`）
- [ ] 9.8 git tag v2.5.0 + push（**需用户确认**）
