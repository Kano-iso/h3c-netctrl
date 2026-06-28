# v2.3-roadmap

## Why

v2.2.0 发版后留下 3 类遗留项需要在 v2.3 收尾：

1. **运维效率** —— 当前 troubleshooting 缺乏统一容器（每次人工手敲 ping / nc / ssh 命令，环境差异大）
2. **能力补齐** —— v2.2.2 patch 实现了"配置 link type + IP 编辑"，但**没实现 link mode 切换**（L2↔L3 bridge/route），NETCONF 不支持必须走 SSH CLI
3. **质量保障** —— v2.2 收尾时 6.3-6.8/6.10/6.11 UI 端到端未逐一验证，依赖人肉点；引入自动化测试可显著降低回归成本
4. **架构演进** —— `docs/CONTAINER-DECOUPLING.md` 蓝图 v2.1.x 已预留，v2.3 拆 `asset` 容器（cmdb + 备份）

**用户原话**（2026-06-29 v2.2.0 收尾时）：

- "我们应该有一个专门的容器吧，每一次我们限错命令有点蠢...有的时候还有会有一个环境问题"（→ ops-toolkit）
- "我没看到有一个功能，就是接口的二层转三层的功能，或者三层转2"（→ link mode 切换）
- "就是这种就是除把除了在点击这一步之外的所有步骤，你不能去模拟吗？"（→ 自动化测试）

## What Changes

- **新增 ops-toolkit 容器**（profile: ops，按需启动）：预装 ping / nc / SSH client / ncclient + 一组预制脚本（check-host.sh / check-netconf.sh / ssh-test.sh / capture-config.sh），后端无侵入，仅作为排错工具
- **新增 link mode 切换能力**：后端 PATCH `/api/devices/{id}/interfaces/{if_index}/link-mode`（mode=bridge|route, force=bool），走 SSH CLI（NETCONF 不支持 link-mode 变更），UI 加"改层级"按钮，受保护护栏+二次确认+设备验证
- **引入自动化测试架构**（**轻量化：复用 `qa-backend` 容器 + `backend/tests/`，0 装包**）：
  - API 层：FastAPI TestClient + pytest（无设备）
  - 设备集成层：pytest + paramiko + ncclient（192.168.100.4 / .5）
  - 覆盖 backup-frontend 6.x + 新增 link mode 切换 + v2.2.0 漏的 14 个新 API
  - **不引入 Playwright**（个人项目 ROI 低，模拟点击是 over-engineering）
- **QA 规范化（强制）**：
  - 每个 change 的 `proposal.md` 必含 "QA 验证计划" 段（按 [QA-TEMPLATE.md](../QA-TEMPLATE.md) 模板）
  - Apply 阶段必跑 `docker compose --profile qa up qa-backend`（单元 + smoke）
  - Archive 阶段必跑 `docker compose --profile qa up qa-frontend`（验编译）
  - 真机集成可推迟（设备不通时 skip），但单元 / smoke 不能少
  - v2.2.0 漏的 14 个新 API + 备份 / VPN 真机集成测试：单独立 [v2.2.1-followup-v22-qa-repair](../v2.2.1-followup-v22-qa-repair/proposal.md) 补
  - **QA 容器使用文档**：[docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)（SOP / 流程 / checklist / 跑法），防止将来忘记 QA 流程
- **QA 前端规范化（v2.3 引入 vitest）**：
  - 引入 `vitest` + `@vue/test-utils` 跑组件测试（Modal / 表单 / 状态机）
  - qa-frontend 容器从"只验编译"升级到"编译 + 组件测试"
  - 装包：vitest + @vue/test-utils + jsdom ~10MB
  - 跑法：`npm run test` 在 qa-frontend 容器里跑
- **新模块 API 增量加入 QA**（长期）：
  - 每次新加 API（v2.3 / v2.3.x / v2.4...）→ 必加 smoke + 错误码 test
  - 流程：实现 API → 加 test → 跑 qa-backend → 写 6.x 浏览器验证项（如有 UI）→ archive
- **拆 asset 容器**（可选 / 评估中）：cmdb + 备份从 monolith 拆出到独立 `asset` 容器（v2.1.x 蓝图 [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)）
- **架构**：保留 OpenSpec 单 change 模式，每个 sub-change 独立起 + archive

## Capabilities

### New Capabilities

| change-id | 主题 | 关键能力 |
|---|---|---|
| `add-ops-toolkit-container` | 容器化运维工具 | docker-compose 新增 ops-toolkit service，profile: ops，5 个预制脚本 |
| `add-interface-l2-l3-switch` | link mode 切换（L2↔L3） | SSH CLI 走 `port link-mode { bridge \| route }` + 二次确认护栏 |
| `add-backup-e2e-and-integration-tests` (轻量：复用 `qa-backend` 容器 + `backend/tests/`) | 自动化测试 | FastAPI TestClient (API) + pytest + paramiko (设备集成) |
| `v2.2.1-followup-v22-qa-repair` (P0，单独起项) | v2.2.0 QA 漏项补齐 | 14 个新 API smoke + 错误码 + 192.168.100.4 backup 集成 + 192.168.100.5 VPN 集成 |
| `v2.2.1-followup-backup-frontend-ui-tests` | backup-frontend UI 验证补 | 6.3-6.8/6.10/6.11 浏览器 UI 端到端 |
| `qa-template-mandatory` | QA 模板强制 | proposal.md 必含 "QA 验证计划" 段 ([QA-TEMPLATE.md](../QA-TEMPLATE.md)) |
| `add-qa-guide` | QA 容器使用文档 | [docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)（SOP / 流程 / checklist / 跑法） |
| `add-vitest-component-tests` (v2.3 引入) | QA 前端规范化 | vitest + @vue/test-utils 跑组件测试（Modal / 表单 / 状态机） |
| `interface-linked-config` | 接口联动配置（其他维度） | 需求待具体化 |
| `v2.3-container-decoupling-asset`（可选） | 拆 asset 容器 | cmdb + 备份独立容器 |

### Modified Capabilities

无（v2.3 是新增，不修改已有能力）

## Impact

- **新增容器**：`docker-compose.dev.yml` 加 `ops-toolkit` service（profile: ops），按需启动不污染日常
- **新增后端**：`backend/app/routers/interface.py` 加 `PATCH /link-mode`；`backend/app/utils/ssh_executor.py` 可能加 link-mode 专用方法
- **新增前端**：`frontend/src/views/Interfaces.vue` 加"改层级"按钮 + `LinkModeSwitchModal.vue` 二次确认弹窗
- **新增测试**：`backend/tests/test_backup_api.py` + `test_backup_integration.py` + `test_vpn_integration.py`（**复用 `qa-backend` 容器 + `requirements.txt` 已含 pytest + paramiko，0 装包消耗**）
- **CI**：`.github/workflows/qa.yml` 加 `docker compose --profile qa up qa-backend --abort-on-container-exit` 一行 + `docker compose --profile qa up qa-frontend --abort-on-container-exit` 一行
- **不破坏**：v2.2.0 backup-frontend / interface-vpn-instance-and-l2-l3 / fix-vpn-edit-capabilities 端点
- **可回退**：每个 sub-change 独立 revert

## 顺序与依赖

```
add-ops-toolkit-container             (独立, P0)
        ↓
v2.2.1-followup-backup-frontend-ui-tests  (独立, P0)
        ↓
add-interface-l2-l3-switch            (独立, P0)
        ↓
add-backup-e2e-and-integration-tests   (P1, 依赖 Playwright + paramiko 装好)
        ↓
v2.3-container-decoupling-asset       (P2, 评估中)
```

**关键依赖说明**：
- ops-toolkit 独立，无前置依赖
- backup-frontend UI 验证补 = 把 v2.2.0 收尾时的 follow-up 单起一个 change（不阻塞 v2.3 发版）
- link mode 切换 = v2.2.2 patch 的"补漏"，能力维度独立
- 自动化测试 = 装框架 + 写用例，对 link mode + backup-frontend 都覆盖
- asset 容器拆 = 架构演进，可推迟到 v2.3.1

## 真机验证

- **设备**：192.168.100.4 (Leaf-03) / 192.168.100.5 (Leaf-04)
- **ops-toolkit**：本地起容器 → 执行 `check-host.sh 192.168.100.4` / `check-netconf.sh 192.168.100.4` → 验证输出符合预期
- **link mode 切换**：先在 Leaf-04 找一个 access 接口 → 改 bridge（force=False 路径，必须先清配置）→ 改回 access → 改 route 路径 → 验证 running-config 已变更
- **backup-frontend UI 验证**：在浏览器跑 6.3-6.8/6.10/6.11 → 同时启动 Playwright 把流程录成 E2E 用例
- **回归**：v2.2.0 已 archive 的 4 changes 不能破坏

## 收尾 / 发版

每个 sub-change 独立 archive + release notes 合并进 v2.3.0 发版文档。`RELEASE-NOTES-v2.3.0.md` 沿用 v2.2.0 模板（统一发版文档流程）。

## Out of Scope

- 不引入 v3.0 VPC + etcd（v3.0 单独）
- 不重写 monolith 整体架构（asset 容器拆可独立评估）
- 不引入 CI/CD 完整流水线（仅 Playwright runner）
- 不做"备份版本对比 UI"（diff 留 follow-up 到 v2.3.1+）

## 关联

- 蓝图：[docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)
- 上版：[v2.2.0 release notes](../../RELEASE-NOTES-v2.2.0.md)
- 路线图：[VERSION-ROADMAP.md § 7](../../VERSION-ROADMAP.md)
