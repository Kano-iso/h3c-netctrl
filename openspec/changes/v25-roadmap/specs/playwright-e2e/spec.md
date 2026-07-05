## ADDED Requirements

### Requirement: qa-frontend 容器 SHALL 集成 Playwright

`frontend/Dockerfile.qa` MUST 安装 `playwright` 包 + Chromium 浏览器二进制（`npx playwright install --with-deps chromium`）。qa-frontend 入口 MUST 在 lint + build + vitest 之后增加 `test:e2e` step（lint 不过 build 不跑，build 不过 e2e 不跑）。

#### Scenario: qa-frontend 完整流程

- **WHEN** 执行 `docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`
- **THEN** 依次执行 lint → build → vitest → playwright e2e，任一步失败后续不跑

#### Scenario: Playwright 镜像构建

- **WHEN** 构建 qa-frontend 镜像
- **THEN** 镜像内包含 `playwright` 包 + Chromium 二进制，`npx playwright --version` 可正常输出

### Requirement: Playwright 配置 SHALL 自动起 vite dev server

`frontend/playwright.config.js` MUST 配置 `webServer` 块，自动启动 `vite dev` 并等待 `http://localhost:5173` 就绪。测试运行结束后 MUST 自动关闭 dev server。

#### Scenario: 自动起服务

- **WHEN** 执行 `npx playwright test`
- **THEN** 系统自动启动 vite dev server，等待就绪后跑测试，结束后关闭

#### Scenario: 端口冲突失败

- **WHEN** 5173 端口被占用且 webServer 启动超时
- **THEN** Playwright 报错退出，不进入测试步骤

### Requirement: SHALL 覆盖 8 个核心 e2e 场景

`frontend/tests/e2e/` 目录 MUST 包含至少 8 个测试文件，覆盖核心用户流程：

1. 设备 CRUD（创建 / 查询 / 更新 / 删除）
2. 接口列表查看
3. VLAN 创建 / 删除
4. 备份列表查看
5. 备份创建（单设备）
6. CMDB 资产采集
7. 仪表盘加载
8. 登录流程（如有）

#### Scenario: 设备 CRUD e2e

- **WHEN** Playwright 模拟用户打开设备管理页 → 创建设备 → 查询列表 → 更新设备 → 删除设备
- **THEN** 全流程无报错，UI 状态正确反映每步操作结果

#### Scenario: VLAN 创建 e2e

- **WHEN** Playwright 模拟用户选择设备 → 进入 VLAN 管理 → 创建 VLAN → 删除 VLAN
- **THEN** 全流程无报错，VLAN 列表正确更新

### Requirement: Playwright 测试 MUST 与后端 mock 解耦

e2e 测试 SHALL 使用 `frontend/tests/e2e/mocks/` 下的 HTTP mock（如 Playwright route interception），不依赖真实后端容器。mock 数据 MUST 覆盖所有被测场景的 API 响应。

#### Scenario: 无后端跑 e2e

- **WHEN** 仅启动 frontend dev server（不启动 ctrl/config/data 容器）
- **THEN** Playwright 通过 route interception mock 所有 `/api/*` 请求，e2e 测试全过

#### Scenario: mock 数据真实

- **WHEN** e2e 测试访问设备列表
- **THEN** mock 返回的设备数据结构与真实 `/api/devices` 响应一致（Pydantic schema 对齐）
