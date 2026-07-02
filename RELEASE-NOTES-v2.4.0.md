# RELEASE-NOTES-v2.4.0

**版本**: v2.4.0
**日期**: 2026-07-02
**主题**: 优化大版本（拆 3 容器蓝图 + 工具完善化 + bugfix + 异步备份）
**前序**: v2.3.1 (`f8b63cb`, 2026-07-01)

---

## 1. 主题

v2.4 = **优化 + 工程化加固**小版本（不是新功能大版本）。
v3.0 才是新功能（VPC 联动）大版本。

用户原话（2026-07-01 v2.3.1 收尾时）：
> "3.0 版本才是上功能的时候，现在我们还是在做一些优化呀，拆容器这些都是优化"
> "你像我们说 vpc 功能的都是 3.0 的事情，但是拆容器都是 2.2.4 的事情"

---

## 2. 包含的 Changes（10 个）

### Bugfix（4 个）
- `v24-bugfix-interface-display-100` — 100.100 接口全 + 其他设备 7-11 个特例（NETCONF get 改 + operational data namespace）
- `v24-bugfix-status-mapping` — OperStatus 映射 1=UP 2=DOWN（RFC 2863 标准）+ 9 单测
- `v24-bugfix-ui-feedback-and-loopback` — Loopback 弱匹配 + link-mode reason_code + 改层级按钮守卫
- `45aa929` — SSH [Y/N] 二次确认自动应答（v2.3.0 漏测 bug，回归发现）

### Feat（2 个）
- `v24-feat-bridge-button` — L3 物理口加"改二层"按钮，补全 link-mode 双向切换
- `v24-feat-async-backup-status` — 异步备份/回滚任务管理（Pinia + BackgroundTaskPanel + 4 异步端点 + 19 单测）

### Roadmap（1 个大 change，4 个 sub-change）
- `v24-roadmap` — v2.4 路线图聚合
  - ✅ `v24-container-cleanup` — 盘点脚本 + SOP + 清理 1 容器/2 镜像/1 volume
  - ✅ `v24-toolkit-ux-and-doc-discovery` — 6 脚本封装 + 回显带文档链接 + qa 容器 banner
  - ✅ `v24-decoupling-inventory-doc` — 3 容器蓝图定稿
  - ⏸️ `v24-container-decoupling-3tier` — 蓝图已定稿，**实施延后到 v2.4.1**

### Archive（4 个）
- 上述 bugfix/feat/roadmap 的归档

---

## 3. v2.4.0 关键能力

### 3.1 接口显示修复（v2.3.0 漏测 bug）
- 100.100 设备从 24 接口 → 59 接口（其他 100.4/.5/.177 从 7-11 接口 → 58-63 接口）
- 根因：NETCONF `get_config` 拿 operational data 不全 → 改用 `get` + data namespace
- 端口状态：1=UP 2=DOWN（RFC 2863 标准），修复前全反

### 3.2 link-mode 双向切换
- 物理口可"改三层"（bridge → route）或"改二层"（route → bridge）
- L3 虚接口（Loopback / Vsi / Vlan）无切换按钮（reason_code=L3_INTERFACE）
- 护栏二次确认 + 受保护接口拦截

### 3.3 异步备份 / 回滚
- 后端：TaskManager (ThreadPoolExecutor 串行) + 4 异步端点 (POST /backup-async + /restore-async + GET /tasks/{id} + POST /cancel)
- 前端：Pinia store + BackgroundTaskPanel 右下角浮动卡片 + localStorage 持久化
- 弹窗立即关闭，任务后台跑，进度条实时显示

### 3.4 ops-toolkit 工具完善化
- 6 脚本：check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch
- 支持 `--device <name|ip>` 统一入口（从后端 API 查 IP+凭据）
- 兼容 v2.3 位置参数 `<ip> <user> <pass>`
- 脚本末尾强制打印 📖 文档链接段（[ops-toolkit.md](docs/ops-toolkit.md) / [CONTAINER-CLEANUP-SOP.md](docs/CONTAINER-CLEANUP-SOP.md) / 凭据来源）
- qa-backend / qa-frontend 容器启动时打印 QA-GUIDE 链接 banner

### 3.5 容器清理
- `make container-inventory` 盘点脚本
- [docs/CONTAINER-INVENTORY.md](docs/CONTAINER-INVENTORY.md) 自动基线
- [docs/CONTAINER-CLEANUP-SOP.md](docs/CONTAINER-CLEANUP-SOP.md) 清理 SOP
- 清理执行：删 1 exited 容器 + 2 未用镜像 + 1 stale 匿名 volume
- 当前基线：3 容器（全 running）/ 6 镜像 / 1 命名 volume

### 3.6 3 容器蓝图（v2.4.0 定稿，v2.4.1 实施）
- [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md) 重写
- 拓扑：sdn-control (NETCONF/SSH) + data (CMDB/备份/任务) + monitor (指标/自愈)
- 通信：HTTP REST + Docker internal network + X-Internal-Token
- 数据库：3 容器各自独立 SQLite（v2.4 不迁 Postgres，决策点 v2.5/v3.0）
- 升级 + 回退步骤 + 故障注入 4 场景设计

---

## 4. 真机验证

**设备**: 192.168.100.5（生产 Leaf-04）/ 192.168.100.100（Spine-01）/ 192.168.100.4（Leaf-03）/ 192.168.100.177（Test-Switch）

| 场景 | 结果 |
|---|---|
| 100.4/.5/.100/.177 接口数 | 58 / 63 / 59 / 58（修前 7-11/7-11/24/7-11） |
| GE1/0/1 状态 100.5 + 100.100 | OperStatus=1 → status="up" ✓ |
| GE1/0/2 状态 100.5 | OperStatus=2 → status="down" ✓ |
| 100.5 Loopback / Vsi / Vlan L3 判断 | 9 个 L3 接口全对 ✓ |
| 100.5 异步备份 9s 完成 | task_id=1, success, 备份 id=68 |
| 100.5 异步备份刷新恢复 | localStorage 保留 success 状态 ✓ |
| 100.100 link-mode route 改回 bridge | 7s + force=true + 改回 + 验证 vlan 100 配回 ✓ |
| 100.100 L3 物理口改二层 | 100.100 GE1/0/5 bridge → route → bridge 真机验证 ✓ |

---

## 5. QA 验证

| 套件 | 结果 |
|---|---|
| 后端 pytest (`make qa-backend`) | **172 passed, 11 skipped, 0 failed** (30.83s) |
| 前端 build (`make qa-frontend`) | ✅ 通过 |
| 真机 e2e | 4 设备 / 8 场景全 PASS |

比 v2.3.1 baseline (127 passed, 4 skipped) 新增 **+45 passed, +7 skipped**。

新增单测来源：
- link_mode_reason: 4 (v24-bugfix-ui-feedback-and-loopback)
- detect_layer_v2: 7 (4 弱匹配回归 + 3 新 case)
- status_mapping: 9 (v24-bugfix-status-mapping)
- ssh_yn_prompt: 6 (v2.3.0 漏测 bug 修复 + 回归)
- task_manager: 7 (v24-feat-async-backup-status)
- async_backup: 12 (v24-feat-async-backup-status)

---

## 6. 设备最终状态

- 192.168.100.4: 接口数据修正，无配置变更
- 192.168.100.5: 接口数据修正 + Loopback 弱匹配，无配置变更
- 192.168.100.100: 接口数据修正 + link-mode route → bridge 改回 + vlan 100 配回（恢复基线）
- 192.168.100.177: 接口数据修正，无配置变更

---

## 7. v2.4.1 路线图（已规划）

> 拆 3 容器 + 性能压测 + 故障注入 + 灰度上线
>
> 决策点：v2.4 收尾时决定 v2.5 / v3.0 是否迁 Postgres
>
> 决策点：v2.4 收尾时决定 monitor 容器是否加 AI troubleshooting

详见 [openspec/changes/v24-roadmap/tasks.md § 4-5](openspec/changes/v24-roadmap/tasks.md)。

---

## 8. 关联

- 路线图: [VERSION-ROADMAP.md § v2.4](VERSION-ROADMAP.md)
- 上版: [RELEASE-NOTES-v2.3.1.md](RELEASE-NOTES-v2.3.1.md)
- 上版: [RELEASE-NOTES-v2.3.0.md](RELEASE-NOTES-v2.3.0.md)
- 蓝图: [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)
- 容器基线: [docs/CONTAINER-INVENTORY.md](docs/CONTAINER-INVENTORY.md)
- 清理 SOP: [docs/CONTAINER-CLEANUP-SOP.md](docs/CONTAINER-CLEANUP-SOP.md)
- ops-toolkit 手册: [docs/ops-toolkit.md](docs/ops-toolkit.md)
- QA 指南: [docs/QA-GUIDE.md](docs/QA-GUIDE.md)
- v2.4-roadmap change: [openspec/changes/v24-roadmap/proposal.md](openspec/changes/v24-roadmap/proposal.md)
