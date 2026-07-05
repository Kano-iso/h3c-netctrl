## MODIFIED Requirements

### Requirement: vitest 组件测试 SHALL 在 qa-frontend 容器内运行

`frontend/Dockerfile.qa` MUST 通过 `RUN chown -R node:node /app` 解决 v2.3 BLOCKED 的 EACCES 权限问题。`package.json` MUST 包含 `test:unit` script 调用 `vitest run`。`vite.config.js` MUST 配置 `test:` 块（`environment: 'happy-dom'` + `include: ['src/**/__tests__/**/*.spec.js']`）。

#### Scenario: EACCES 排障后 vitest 可跑

- **WHEN** qa-frontend 容器内执行 `npm run test:unit`
- **THEN** vitest 正常启动，无 EACCES 错误，所有 .spec.js 文件被执行

#### Scenario: vitest 集成 qa 流程

- **WHEN** 执行 `docker compose -f docker-compose.dev.yml --profile qa up qa-frontend`
- **THEN** 流程为 lint → build → vitest，lint 不过 build 不跑，build 不过 vitest 不跑

#### Scenario: happy-dom 环境生效

- **WHEN** vitest 跑涉及 DOM API 的组件测试（如 mount + findComponent）
- **THEN** happy-dom 提供 document/window API，测试不报 "document is not defined"

### Requirement: SHALL 覆盖 5 个核心组件各 6 case

`frontend/src/__tests__/` 目录 MUST 包含至少 30 个测试 case，覆盖 5 个核心组件：

1. `Devices.spec.js`（6 case：列表加载 / 创建 / 编辑 / 删除 / 连接测试 / 搜索过滤）
2. `Interfaces.spec.js`（6 case：列表加载 / L2-L3 切换 / IP 编辑 / VPN 绑定 / 解绑 / 分页）
3. `Backup.spec.js`（6 case：列表加载 / 创建 / 锁定 / 解锁 / 回滚 / 下载）
4. `CMDB.spec.js`（6 case：列表加载 / 单设备采集 / 编辑资产 / 状态筛选 / 位置更新 / 标签管理）
5. `Dashboard.spec.js`（6 case：统计加载 / 最近操作 / 最近告警 / 图表渲染 / 跳转 / 刷新）

#### Scenario: Devices 组件列表加载

- **WHEN** mount Devices 组件并 mock API 返回设备列表
- **THEN** 组件渲染设备表格，行数等于 mock 数据数量

#### Scenario: Backup 组件创建备份

- **WHEN** mount Backup 组件并模拟用户点击"创建备份"按钮
- **THEN** 组件调用 `/api/devices/{id}/backup` POST，UI 显示创建中状态

### Requirement: vitest 测试 SHALL 与 e2e 解耦

vitest 测试 MUST 仅覆盖组件级逻辑（mount + props + events），不依赖真实后端或路由跳转。HTTP 请求 MUST 通过 `vi.mock` 或 `axios-mock-adapter` mock。

#### Scenario: 组件测试无网络依赖

- **WHEN** vitest 跑组件测试
- **THEN** 不发起任何真实 HTTP 请求，所有 API 通过 mock 返回

#### Scenario: 测试间隔离

- **WHEN** 多个 vitest 测试文件并行运行
- **THEN** 测试间无状态污染，每个 test 独立 mount/destroy 组件

## 解锁条件（v2.3 遗留，v2.5 解决）

v2.3 的 EACCES 问题由 `frontend/Dockerfile.qa` 中 `chown -R node:node /app` 解决，不再依赖宿主机手动 `sudo chown`。

## 关联 change

- v2.3 遗留：`openspec/changes/archive/2026-06-29-add-vitest-component-tests/`
- v2.5 实施：`openspec/changes/v25-roadmap/`
