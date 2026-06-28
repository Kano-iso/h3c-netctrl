# v2.3-roadmap Design

> v2.3-roadmap 是聚合 PRD，详细设计在每个 sub-change 的 `design.md` 中。
> 本文件只描述 v2.3 整体架构 + sub-change 间的关系。

## 1. 整体架构

```
v2.3 整体
├── ops-toolkit 容器 (profile: ops)
│   ├── 工具：ping / nc / SSH client / ncclient / netmiko
│   ├── 预制脚本：check-host / check-netconf / ssh-test / capture-config
│   └── 入口：docker compose --profile ops run --rm ops-toolkit <script>
│
├── backup-frontend UI 验证补 (v2.2.1 follow-up, 无新代码)
│
├── link mode 切换 (add-interface-l2-l3-switch)
│   ├── 后端：PATCH /api/devices/{id}/interfaces/{if_index}/link-mode
│   │   body: { mode: "bridge"|"route", force: bool }
│   │   实现：SSH CLI 走 `port link-mode { bridge | route }` + 二次确认护栏
│   ├── 前端：LinkModeSwitchModal.vue + Interfaces.vue "改层级" 按钮
│   └── 真机验证：192.168.100.5
│
├── 自动化测试双层 (add-backup-e2e-and-integration-tests)
│   ├── tests/e2e/ (Playwright)
│   │   ├── backup.spec.js  (跑 backup-frontend 6.1-6.11)
│   │   ├── interface-vpn.spec.js
│   │   └── interface-link-mode.spec.js  (v2.3 新增)
│   └── tests/integration/ (pytest + paramiko)
│       ├── test_backup_real_device.py
│       ├── test_vpn_real_device.py
│       └── test_link_mode_real_device.py  (v2.3 新增)
│
└── container-decoupling-asset (可选 / 评估)
    ├── asset service (cmdb + 备份)
    ├── 独立数据库
    └── 与 core 通过 REST + message queue 通信
```

## 2. sub-change 间的关系

### 2.1 独立无依赖

- `add-ops-toolkit-container`：纯容器工具，不依赖任何代码改动
- `v2.2.1-followup-backup-frontend-ui-tests`：纯真机验证补，不改代码

### 2.2 弱依赖（自动化测试覆盖新功能）

- `add-interface-l2-l3-switch` 完成后，`add-backup-e2e-and-integration-tests` 可新增 `interface-link-mode.spec.js` + `test_link_mode_real_device.py` 覆盖
- 时序：link mode 切换先 apply → 自动化测试 add link mode 用例

### 2.3 强依赖（拆容器前置）

- `v2.3-container-decoupling-asset` 需先有 v2.2.0 备份后端稳定运行（已满足）
- 数据库 schema 无变更（只是容器边界）

## 3. 关键技术决策

### 3.1 ops-toolkit 容器为什么用 `profile: ops`

- 日常 dev 不启动（避免污染环境）
- 排错时 `docker compose --profile ops run --rm ops-toolkit <script>` 临时启动
- 与日常 dev/prod 环境完全隔离（不会影响其他容器）

### 3.2 link mode 切换为什么走 SSH CLI

- H3C V7 NETCONF YANG 模型（[H3C-COMMON-IFNET-MIB](https://www.h3c.com/cn/Products___Technology/Technical_Support/Technical_Documents/Switches/Catalog/S12500/S12500-X/Command/Command_Manual/H3C_S12500-X_CG-R7583P04-6W100/04/202004/1286459_30005_0.htm)）的 `Ifmgr/Interfaces/Interface/LinkType` 只读，**不支持 link-mode 变更**
- 业界标准：H3C 官方 CLI 走 `interface { name }` → `port link-mode { bridge | route }`
- SSH CLI 是 v2.2.2 patch 的"link type 调整"无法覆盖的场景，必须走 SSH

### 3.3 自动化测试为什么双层

| 层 | 框架 | 跑什么 | 是否需设备 |
|---|---|---|---|
| E2E | Playwright | 前端 UI 路径 | ❌ |
| Integration | pytest + paramiko + ncclient | 真实 SSH / NETCONF / 备份文件 | ✅ 192.168.100.4 / .5 |

- E2E 跑得勤（PR 每次），验证 UI 流程
- Integration 跑得少（每天 / 每周），验证设备交互
- 双层覆盖：UI bug 不漏（E2E）+ 设备协议变更不漏（Integration）

### 3.4 拆 asset 容器为什么"评估中"

- **收益**：cmdb + 备份独立扩缩容、独立发布、不影响 core
- **成本**：跨容器通信、数据库拆分、状态同步、CI 复杂度
- **评估点**：v2.3 是否带来明显的运维负担（不是）
- **结论**：v2.3 不拆，v3.0 VPC 时和 sdn 容器一起拆

## 4. 数据流（link mode 切换）

```
用户 UI 点"改层级" 
  ↓
Interfaces.vue 弹 LinkModeSwitchModal
  ↓ (选择 mode=bridge|route + force bool)
PATCH /api/devices/{id}/interfaces/{if_index}/link-mode
  body: { mode, force }
  ↓
后端 routers/interface.py::set_link_mode
  ↓ (force=False + 现 L3 配置 → 422 拒绝)
  ↓ (force=True → 走 SSH CLI)
SSHExecutor.set_link_mode(if_index, mode)
  ↓
paramiko invoke_shell
  ↓
H3C CLI: system-view → interface {if} → port link-mode {mode} → quit
  ↓ (验证 running-config)
  ↓
NETCONF get-config Ifmgr/Interfaces/Interface/LinkType
  ↓
返回 success + 新 mode
  ↓
UI 弹"修改成功" + 刷新接口表
```

## 5. 失败回退

每个 sub-change 独立 revert：

- `add-ops-toolkit-container` revert：删 docker-compose service + 删脚本
- `add-interface-l2-l3-switch` revert：删 PATCH /link-mode + 删前端 modal
- `add-backup-e2e-and-integration-tests` revert：删 tests/ + 删 CI workflow
- `v2.2.1-followup-backup-frontend-ui-tests` revert：仅删 tasks.md 6.x 标记

## 6. 关联

- 蓝图：[docs/CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)
- 上版：[v2.2.0 release notes](../../../RELEASE-NOTES-v2.2.0.md)
- 路线图：[VERSION-ROADMAP.md § 7](../../../VERSION-ROADMAP.md)
- 父 PRD 模板：参考 [archive/2026-06-21-v20-platform-evolution/proposal.md](../archive/2026-06-21-v20-platform-evolution/proposal.md)
