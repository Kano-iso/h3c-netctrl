# H3C NetCtrl 版本路线图

> **这是大版本管理的统一入口。** 任何版本相关的问题（当前到哪、之前完成啥、接下来要做什么）以本文档为准。
>
> 单个 change 的细节见 [openspec/changes/](openspec/changes/) 与 [openspec/changes/archive/](openspec/changes/archive/)。
> 单个版本的开发节奏见 `openspec/changes/<change-id>/tasks.md`。

---

## 1. 版本全景

| 版本 | 状态 | 主题（一句话） | 关联 OpenSpec change |
|---|---|---|---|
| **v1.0 MVP** | ✅ 2026-06-13 | 单设备 + NETCONF VLAN + 操作日志，能跑 | [archive/2026-06-13-v1-mvp-foundation](openspec/changes/archive/2026-06-13-v1-mvp-foundation/) |
| **v1.1 UI 增强** | ⚠️ 弃用 | Vue 3 重构 + 多设备 UI（被 v2.1 替代） | [archive/2026-06-23-v11-ui-enhancement-deprecated](openspec/changes/archive/2026-06-23-v11-ui-enhancement-deprecated/) |
| **v2.0 平台化** | ✅ 2026-06-22 | 8 项：NETCONF 重构 / QA / bugfix 轮 / Schemas v2 / CMDB / 终端 / 批量 / 侧边栏 | archive 目录下 `2026-06-21-v20-platform-evolution` / `2026-06-22-v20-*` |
| **v2.1 前端重构** | ✅ 2026-06-23 | 7 项：多命令终端 / 设备 CRUD UI / 资产编辑 / 单设备采集 / 状态判定修复 / 容器解耦预留 | archive 目录下 `2026-06-23-v21-frontend-refactor` / `2026-06-23-*` / `2026-06-28-container-decoupling` |
| **v2.1.x patch 灰度** | 🚧 进行中 | 手动备份后端能力（前端延后到 v2.2） | [archive/2026-06-28-v21x-patch-backup-backend](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/) |
| **v2.2 网控增强** | 🚧 进行中（1/3） | 备份前端 / 接口 VPN / 接口 L2-L3 / 联动配置 | [archive/2026-06-28-interface-vpn-instance-and-l2-l3](openspec/changes/archive/2026-06-28-interface-vpn-instance-and-l2-l3/)（VPN + L2/L3 ✅，备份前端待开） |
| **v3.0 VPC** | ⏳ 规划 | VPC + etcd（SDN 起步） | 暂未起 spec |
| **monitor** | ⏳ 远期 | 监控 / 告警 / dashboard 独立化 | 暂未起 spec |

---

## 2. 核心约束（任何版本都遵守）

### 2.1 架构约束

- **NETCONF 优先**：H3C V7 设备能 NETCONF 的能力走 NETCONF，NETCONF 不支持的（trunk allowed VLANs）显式走 SSH CLI。
  - 例外：`port trunk permit vlan`（NETCONF 配置 trunk 允许 VLAN 在 V7 上不工作，必须 SSH CLI）。
- **SSH 端口 = 22，NETCONF 端口 = 830**：备份走 SFTP（SSH 22），与现有 `ssh_executor.py` 复用连接参数。
- **设备密码 Fernet 加密**：`ENCRYPTION_KEY` 环境变量注入，`.env` 加入 `.gitignore`。
- **数据库迁移 Alembic 强制**：`backend/migrations/versions/`，`alembic upgrade head` 自动跑。
- **容器化开发**：所有运行在 Docker 容器内，宿主机不装业务依赖。

### 2.2 流程约束

- **所有改动走 OpenSpec**：Propose → Apply（按 Task 逐步）→ Archive 闭环。
- **Task 粒度 = 一次 commit**：不攒多个 Task 一次性提交。
- **每个 Spec 必含**：目标 / 范围 / 设计决策 / 验收标准。
- **卡壳 3 次立即停手**：回 Spec 对齐，必要时重新 Propose。

### 2.3 风险约束

- **设备删除不可逆**：用户明确不接受兜底恢复（accepted 现状）。
- **多 Tab 设备删除不自动刷新**：其他 Tab 不联动刷新（accepted 现状）。
- **SSH 初次连接失败必须抛 `ConnectionError`**：让设备状态被正确设为离线，不允许"假在线"。
- **NETCONF trunk allowed VLANs 在 H3C V7 不工作**：走 SSH CLI `port trunk permit vlan`，不接受 NETCONF 尝试。

---

## 3. 详细版本史

### v1.0 MVP（✅ 2026-06-13）

**目标**：从零跑通"单台 H3C 设备 + NETCONF VLAN + 日志"的最小闭环。

**包含**：
- 设备 CRUD（单设备硬编码）
- NETCONF VLAN 增删改查
- 操作日志（写入数据库）
- Vue 3 前端骨架

**OpenSpec**：[archive/2026-06-13-v1-mvp-foundation](openspec/changes/archive/2026-06-13-v1-mvp-foundation/)

---

### v2.0 平台化（✅ 2026-06-22）

**目标**：从 MVP 升级到"多设备 + 平台 UI + 完整生命周期"。

**包含**（共 8 项 change）：
1. **2026-06-21-v20-platform-evolution** — 平台能力（Dashboard / CMDB / 终端 / 批量 / 接口 / 设备 / 日志 / 工程基础设施）
2. **2026-06-21-v20-bugfix-ssh-pagination** — SSH 分页 bug
3. **2026-06-22-v20-netconf-refactor** — NETCONF 重构
4. **2026-06-22-v20-bugfix-ifmgr-parse** — 接口 XML 解析
5. **2026-06-22-v20-bugfix-connection-resilience** — 连接弹性
6. **2026-06-22-v20-bugfix-interface-safety-guard** — 接口安全护栏
7. **2026-06-22-v20-bugfix-schemas-pydantic-v2** — Schemas v2
8. **2026-06-22-v20-bugfix-device-detail-computed-import** — 设备详情 computed
9. **2026-06-22-v20-qa-test-suite** — QA 测试套件
10. **2026-06-22-v20-bugfix-round2** — bugfix 轮次 2

**OpenSpec**：[archive/](openspec/changes/archive/)（2026-06-21 / 2026-06-22 子目录）

---

### v2.1 前端重构（✅ 2026-06-23）

**目标**：把 v1.1 弃用的旧 UI 翻新为"完整多设备管理 + 真实状态判定"。

**包含**（共 7 项 change）：
1. **2026-06-23-v21-frontend-refactor** — 前端重构 7 子能力（视觉系统 / 顶导 / 页脚 / 内容宽度控制 / 平台 UI / 后端集成）
2. **2026-06-23-device-asset-crud-ui** — 设备 / 资产 CRUD UI（Devices.vue / CMDB.vue + Modal 组件）
3. **2026-06-23-cmdb-single-asset-refresh** — CMDB 单设备采集按钮
4. **2026-06-23-fix-asset-status-and-cmdb-layout** — 资产状态判定修复（1.1.1.1 误判在线）+ CMDB 操作列宽度
5. **2026-06-23-fix-interface-trunk-deploy** — Trunk 部署 NETCONF 限制修复（用 SSH CLI fallback）
6. **2026-06-23-ops-terminal-multi-cmd** — 多命令终端
7. **2026-06-23-chore-frontend-polish** — 前端细节打磨（字体 / 端口 / 状态 / Select / CMDB / PageHeader）
8. **2026-06-28-container-decoupling** — 容器解耦预留（蓝图文档化，不实际拆）

**OpenSpec**：[archive/](openspec/changes/archive/)（2026-06-23 / 2026-06-28 子目录）

---

### v2.1.x patch 灰度（🚧 当前）

**目标**：v2.2 中"手动备份"功能的后端能力先落地，前端延后。**本次不发 v2.2 版，仅作为 v2.1.x patch 灰度发布。**

**正在进行的 change**：
- **[backup-manual-with-rollback](openspec/changes/backup-manual-with-rollback/)** — 手动备份 + 锁定 + 轮转 + 回滚
  - 后端：Backup 模型 / BackupManager / 7 个 API 端点 / Alembic 迁移
  - 前端：延后到 v2.2（**本 change 不在本次发版**）
  - 真实设备验证目标：192.168.100.4 (Leaf-03)
  - 决策记录：用户明确"不写前端不发 v2.2 版"，符合灰度发布原则

**archive 时机**：后端能力完成后，先 archive 此 change（标注"灰度，未发版"），等 v2.2 前端完成时再起新 change 合并进 v2.2。

---

### v2.2 网控增强（🚧 进行中）

**目标**：把 v2.1.x 灰度的备份前端补齐，新增接口 VPN 联动 + L2/L3 状态展示。

**预计包含 3 个 change**：

| change-id | 主题 | 状态 | 备注 |
|---|---|---|---|
| `interface-vpn-instance-and-l2-l3` | 接口 L2/L3 展示 + IP + VPN instance 联动（创建/绑定/解绑/删除） | 🚧 后端+前端已就位，等真机验证 | [openspec/changes/interface-vpn-instance-and-l2-l3](openspec/changes/interface-vpn-instance-and-l2-l3/) |
| `backup-ui` | 备份前端 UI（Devices.vue 表格行 + BackupListModal + CMDB 全量按钮） | ⏳ 未起 | v2.1.x 灰度的前端延后部分 |
| `interface-linked-config` | 接口联动配置（其他维度） | ⏳ 未起 | 用户原话"顺便再加一个能力" |

**功能边界**（用户已确认）：
- ✅ 手动备份（单设备 + 全量）
- ✅ 备份锁定 / 轮转（5 份未锁 + 锁定永久）
- ✅ 回滚（NETCONF load-config 优先，SSH 推送 fallback）
- ✅ 备份文件按设备 ID 目录隔离
- ✅ Docker volume 持久化
- ❌ **不**做定时备份（cron / scheduler）
- ❌ **不**做"今日份"快查界面
- ❌ **不**另起 FTP/SCP server
- ❌ **不**做"auto 备份"

---

### v3.0 VPC（⏳ 规划）

**目标**：SDN 起步，引入 VPC 能力 + etcd 协调。

**前置依赖**：
- v2.3 完成 asset 容器拆分（数据层独立）
- 容器解耦蓝图落地（已在 v2.1.x patch 预留）

**预计 change**：
- `sdn-vpc-foundation` — VPC 基础能力（创建 / 删除 / 绑定到交换机）
- `sdn-etcd-coordination` — etcd 集群协调

---

### monitor（⏳ 远期）

**目标**：独立监控 / 告警 / dashboard 容器，对接 Prometheus + Grafana。

**前置依赖**：
- v3.0 VPC 稳定
- 监控需求明确（目前用户未提出）

**注意**：目前监控诉求弱（用户原话："监控将来一定是个大东西"），暂不主动起 change。

---

## 4. 当前正在做（v2.1.x patch 灰度）

### 4.1 实时进度

详见 [openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/tasks.md](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/tasks.md)。

**已完成**：
- ✅ 数据库：Backup 模型 + Alembic 迁移（`d201cd0389d1_add_backups_table.py`）
- ✅ 后端：BackupManager（SFTP 拉取 / 轮转 / 锁定 / 回滚）
- ✅ 后端：7 个 API 端点（`/api/devices/{id}/backup` 全家桶 + `/api/backups` 全量）
- ✅ 配置：BACKUP_DIR / BACKUP_KEEP 环境变量
- ✅ 路由注册：`main.py` 已 include_router（修复 import 缺 `backup` 的 NameError）
- ✅ 部署：docker-compose.dev.yml volume 挂载完成
- ✅ 验证：5 个 backup 路径在 OpenAPI 中可见，边界场景"设备不存在"返回正确 APIResponse

**未完成 / 留作 v2.2 follow-up**：
- ⏸️ 真实设备验证：192.168.100.4 (Leaf-03) 需要用户现场配合
- ⏸️ 前端：明确延后到 v2.2（task 4.1 / 5.1 / 6.1-6.3 / 7.x）

### 4.2 下一步

1. ~~补全部署配置（volume + env）~~ ✅ 已完成
2. ~~验证后端能正常启动~~ ✅ 已完成
3. ~~archive 此 change（标注"灰度未发版"）~~ ✅ 已 archive 到 `2026-06-28-v21x-patch-backup-backend/`
4. **转入 v2.2 计划**：起 3 个新 change（`backup-ui` / `interface-vpn-instance-and-l2-l3` / `interface-linked-config`）

---

## 5. 关联文档

| 文档 | 用途 |
|---|---|
| [README.md](README.md) | 项目入口 / 快速启动 / 技术栈 |
| [VERSION-ROADMAP.md](VERSION-ROADMAP.md) | **大版本路线图（本文档）** |
| [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md) | 容器解耦蓝图（v2.1.x patch 已 archive） |
| [docs/tutorial.md](docs/tutorial.md) | 教程 |
| [docs/implementation.md](docs/implementation.md) | 实施说明 |
| [openspec/AGENTS.md](openspec/AGENTS.md) | OpenSpec 使用规范（流程类） |
| [openspec/specs/](openspec/specs/) | 长期沉淀的 spec（按能力维度） |
| [openspec/changes/](openspec/changes/) | 进行中的 change |
| [openspec/changes/archive/](openspec/changes/archive/) | 已归档的 change |

---

## 6. 变更记录

| 日期 | 变更 | 作者 |
|---|---|---|
| 2026-06-28 | 初版：v1.0 → v2.1 + v2.1.x patch 灰度 + v2.2 规划 | session 续接 |
| | | |

---

**最后更新**：2026-06-28
