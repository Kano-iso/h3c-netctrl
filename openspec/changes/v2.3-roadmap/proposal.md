# v2.3-roadmap

## Why

**v2.3 定位**：**修 bug + 健壮性补全**小版本（不是新功能大版本）。

v2.2.0（2026-06-29 发版，tag v2.2.0）= 新功能大版本（备份前端 / VPN / link type+IP）。发版时跳过了 qa 容器跑 QA，commit 19 个没跑过 1 次 qa-backend / qa-frontend，14 个新 API 0 覆盖，4 收尾 bug 全靠用户实测抓。

v2.3 把"v2.2.0 漏的 + 长期遗留 + 健壮性补全"集中发版：

| 类别 | 来源 | 收尾内容 |
|---|---|---|
| **v2.2.0 漏的 QA** | v2.2.0 发版时跳过了 qa-backend / qa-frontend | 14 个新 API smoke + 错误码 + 真机集成 |
| **运维效率** | 用户提："每一次我们限错命令有点蠢" | ops-toolkit 容器（ping / nc / SSH / ncclient + 5 预制脚本） |
| **能力补齐** | 用户提："接口的二层转三层的功能没看到" | link mode 切换（L2↔L3 bridge/route，NETCONF 不支持走 SSH CLI） |
| **质量保障** | 用户提："这种就是除点击外所有步骤你不能模拟吗" | 自动化测试架构（轻量：复用 qa-backend，0 装包） |
| **QA 规范化** | v2.2.0 教训：4 bug 全靠用户实测 | 强制 PRD QA 模板 + qa 容器使用文档 + vitest 前端组件测试 |
| **架构演进（评估）** | v2.1.x 蓝图 [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md) | 拆 asset 容器（cmdb + 备份独立，可选） |

**用户原话**（2026-06-29 v2.2.0 收尾时）：
- "我们应该有一个专门的容器吧，每一次我们限错命令有点蠢...有的时候还有会有一个环境问题"（→ ops-toolkit）
- "我没看到有一个功能，就是接口的二层转三层的功能，或者三层转2"（→ link mode 切换）
- "就是这种就是除把除了在点击这一步之外的所有步骤，你不能去模拟吗？"（→ 自动化测试）
- "我们在 2.2 发版的时候根本就没用 qa 跑过容器吧...这 QA 容器白做了呀"（→ QA 规范化 + 补漏）

## What Changes

v2.3 = **7 类工作全打包**（不分大小版本），一起发版：

### 1. 容器：ops-toolkit（运维排错工具包）

- docker-compose.dev.yml 加 `ops-toolkit` service（profile: ops，按需启动）
- 预装：ping / nc / SSH client / ncclient / netmiko / python3
- 5 个预制脚本：check-host.sh / check-netconf.sh / ssh-test.sh / capture-config.sh / reboot-wait.sh
- 后端无侵入，仅作为排错工具
- 装包：~50MB

### 2. 能力：link mode 切换（L2↔L3）

- 后端 `PATCH /api/devices/{id}/interfaces/{if_index}/link-mode`（mode=bridge|route, force=bool）
- SSH CLI 走 `port link-mode { bridge | route }`（NETCONF 不支持 link-mode 变更）
- 受保护护栏 + 二次确认 + 设备验证
- 前端 `LinkModeSwitchModal.vue` + Interfaces.vue "改层级"按钮
- 装包：0

### 3. v2.2.0 QA 漏项补齐（**P0**）

- 14 个新 API smoke + 错误码（FastAPI TestClient）：
  - backup 7 API（POST / GET / GET download / DELETE / POST lock / POST restore / POST /backups）
  - VPN 4 API（POST vpn-instances / GET / POST vpn-bind / POST vpn-unbind）
  - link-type 1 PATCH + ipv4 2 API（POST / DELETE）
- 备份 / VPN 真机集成（pytest + paramiko + ncclient）：
  - 192.168.100.4 backup 端到端（含 reboot 60-120s verify + restore_original_state）
  - 192.168.100.5 VPN + link type + IP 真机集成
- 装包：0（复用 qa-backend + paramiko + pytest）
- 集成测试约束：`restore_original_state` (n→n+1→n) / reboot sleep+retry 90s

### 4. backup-frontend UI 验证补

- 6.3-6.8 / 6.10 / 6.11 浏览器 UI 端到端（用户实测，6.9 已 PASS）
- 装包：0

### 5. 自动化测试架构

- API 层：FastAPI TestClient + pytest（无设备）
- 设备集成层：pytest + paramiko + ncclient（192.168.100.4 / .5）
- 覆盖 backup-frontend 6.x + 新增 link mode 切换 + v2.2.0 漏的 14 个新 API
- **不引入 Playwright**（个人项目 ROI 低，模拟点击是 over-engineering）
- 装包：0

### 6. QA 规范化（强制 + 长期）

- **每个 change 的 `proposal.md` 必含 "QA 验证计划" 段**（按 [QA-TEMPLATE.md](../QA-TEMPLATE.md) 模板）
- Apply 阶段必跑 `docker compose --profile qa up qa-backend`（单元 + smoke）
- Archive 阶段必跑 `docker compose --profile qa up qa-frontend`（验编译）
- 真机集成可推迟（设备不通时 skip），但单元 / smoke 不能少
- **QA 容器使用文档**：[docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)（SOP / 流程 / checklist / 跑法）
- **新模块 API 增量加入 QA**（长期）：每次新加 API 必加 smoke + 错误码 test
- 装包：0

### 7. QA 前端规范化（vitest）

- 引入 `vitest` + `@vue/test-utils` 跑组件测试（Modal / 表单 / 状态机）
- qa-frontend 容器从"只验编译"升级到"编译 + 组件测试"
- 装包：vitest + @vue/test-utils + jsdom ~10MB

### 8. 拆 asset 容器（**评估中**，可能推迟 v2.3.1）

- 评估拆 asset 容器的 ROI（开发成本 vs 收益）
- 如决定拆：cmdb + 备份从 monolith 拆出到独立 `asset` 容器
- 如不拆：标记"评估结论：暂不拆，v3.0 VPC 时再统一拆"

### 9. interface-linked-config（**待需求具体化**）

- 用户提过"顺便再加一个能力"
- 跟用户确认具体能力范围
- 评估能力范围 + 选 NETCONF / SSH CLI 实现路径

## Capabilities

### New Capabilities

| sub-change | 主题 | 关键能力 | 装包 |
|---|---|---|---|
| `add-ops-toolkit-container` | 容器化运维工具 | docker-compose 新增 ops-toolkit service，profile: ops，5 个预制脚本 | +50MB |
| `add-interface-l2-l3-switch` | link mode 切换（L2↔L3） | SSH CLI 走 `port link-mode { bridge \| route }` + 二次确认护栏 | 0 |
| `add-v22-qa-repair`（**P0**） | v2.2.0 QA 漏项补齐 | 14 个新 API smoke + 错误码 + 192.168.100.4 backup 集成 + 192.168.100.5 VPN 集成 | 0 |
| `add-v22-backup-frontend-ui-tests` | backup-frontend UI 验证补 | 6.3-6.8/6.10/6.11 浏览器 UI 端到端 | 0 |
| `add-backup-e2e-and-integration-tests` | 自动化测试架构（轻量） | FastAPI TestClient (API) + pytest + paramiko (设备集成) | 0 |
| `qa-template-mandatory` | QA 模板强制 | proposal.md 必含 "QA 验证计划" 段 ([QA-TEMPLATE.md](../QA-TEMPLATE.md)) | 0 |
| `add-qa-guide` | QA 容器使用文档 | [docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)（SOP / 流程 / checklist / 跑法） | 0 |
| `add-vitest-component-tests` | QA 前端规范化 | vitest + @vue/test-utils 跑组件测试 | +10MB |
| `v2.3-container-decoupling-asset`（**评估中**） | 拆 asset 容器 | cmdb + 备份独立容器 | - |
| `interface-linked-config`（**待具体化**） | 接口联动配置（其他维度） | 需求待用户确认 | - |

### Modified Capabilities

- v2.2.0 backup-frontend / interface-vpn-instance-and-l2-l3 / fix-vpn-edit-capabilities 端点
  - 加 14 个新 API test（v2.2.0 漏的）
  - 加 backup / VPN 集成测试

## Impact

- **新增容器**：1 个（`ops-toolkit`，profile: ops）
- **新增后端 API**：1 个（`PATCH /api/devices/{id}/interfaces/{if_index}/link-mode`）
- **新增后端测试文件**：5 个
  - `backend/tests/test_smoke.py` 加 14 个 existence smoke
  - `backend/tests/test_backup_api.py`（7 backup API）
  - `backend/tests/test_vpn_api.py`（4 VPN API）
  - `backend/tests/test_interface_edit_api.py`（3 link-type / ipv4 API）
  - `backend/tests/test_backup_integration.py`（192.168.100.4）
  - `backend/tests/test_vpn_integration.py`（192.168.100.5）
- **修改 conftest.py**：加 `--integration` marker
- **新增前端组件**：1 个（`LinkModeSwitchModal.vue`）
- **修改前端**：Interfaces.vue 加"改层级"按钮
- **新增前端测试**：vitest + @vue/test-utils 框架 + 组件测试用例（v2.3 评估覆盖范围）
- **CI**：`.github/workflows/qa.yml` 加 2 行（qa-backend + qa-frontend）
- **不破坏**：v2.2.0 backup-frontend / interface-vpn-instance-and-l2-l3 / fix-vpn-edit-capabilities 端点
- **可回退**：每个 sub-change 独立 revert

## 顺序与依赖

```
add-v22-qa-repair                    (P0, v2.2.0 补漏, 优先)
        ↓
qa-template-mandatory                (P0, 强制规范)
        ↓
add-qa-guide                         (P0, QA 容器使用文档)
        ↓
add-v22-backup-frontend-ui-tests     (P0, 浏览器验证补)
        ↓
add-ops-toolkit-container            (P0, 独立)
        ↓
add-interface-l2-l3-switch           (P0, 独立)
        ↓
add-backup-e2e-and-integration-tests (P1, 依赖 qa-repair + link mode)
        ↓
add-vitest-component-tests           (P1, QA 前端规范化)
        ↓
v2.3-container-decoupling-asset     (P2, 评估中, 可能推迟 v2.3.1)
        ↓
interface-linked-config              (P2, 待用户具体化)
```

**关键依赖说明**：
- `add-v22-qa-repair` P0 优先：v2.2.0 漏的测试必须先补，否则后面 change 的"QA 模板强制"前提不成立
- ops-toolkit / link mode 独立，无前置依赖
- 自动化测试 = 在 QA 补漏 + link mode 基础上增量加用例
- vitest 独立，依赖前端框架（v2.3 评估覆盖率）
- asset 容器拆 + interface-linked-config 可推迟

## 真机验证

- **设备**：192.168.100.4 (Leaf-03) / 192.168.100.5 (Leaf-04)
- **ops-toolkit**：`docker compose --profile ops run --rm ops-toolkit check-host.sh 192.168.100.4` → 验证输出
- **link mode 切换**：192.168.100.5 找 access 接口 → 改 bridge（force=False 路径先清配置）→ 改回 access → 改 route → 验证 running-config
- **backup 集成**：192.168.100.4 backup startup + running → restore with_reboot=true → reboot + verify → restore_original_state
- **VPN 集成**：192.168.100.5 创建测试 VPN → 绑定到测试接口 → 解绑 → 删除 → restore_original_state
- **回归**：v2.2.0 已 archive 的 4 changes 不能破坏（qa-backend 跑 42+ tests 全 PASS）

## 收尾 / 发版

- 每个 sub-change 独立 archive
- `RELEASE-NOTES-v2.3.0.md` 沿用 v2.2.0 模板（统一发版文档）
- 合并所有 sub-change release notes 到 v2.3.0
- `VERSION-ROADMAP.md` v2.3 状态：进行中 → 已发版
- `README.md` 版本路线图 / 功能概览 / API 端点 / 版本历史 更新
- push 全部 commits + `git tag v2.3.0`

## Out of Scope

- 不引入 v3.0 VPC + etcd（v3.0 单独）
- 不重写 monolith 整体架构（asset 容器拆独立评估）
- 不做"备份版本对比 UI"（diff 留 follow-up 到 v2.3.1+）
- 不引入新测试框架（vitest 是新增，因为 v2.2.0 没组件测试）

## 关联

- 蓝图：[docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)
- 上版：[v2.2.0 release notes](../../../RELEASE-NOTES-v2.2.0.md)
- 路线图：[VERSION-ROADMAP.md § v2.3 backlog](../../../VERSION-ROADMAP.md)
- QA 模板：[openspec/changes/QA-TEMPLATE.md](../QA-TEMPLATE.md)
- QA 容器使用：[docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)
