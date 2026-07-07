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
| **v2.1.x patch 灰度** | ✅ 2026-06-29 (并入 v2.2.0 发版) | 手动备份后端能力（前端在 v2.2 backup-frontend 补齐） | [archive/2026-06-28-v21x-patch-backup-backend](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/) |
| **v2.2 网控增强** | ✅ 2026-06-29 (tag: v2.2.0) | 备份前端 / 接口 VPN / 接口 L2-L3 / 联动配置 | [archive/2026-06-28-interface-vpn-instance-and-l2-l3](openspec/changes/archive/2026-06-28-interface-vpn-instance-and-l2-l3/)（VPN + L2/L3 ✅ + **v2.2.1 patch** unbind 预校验 + Modal UX 修复 [archive/2026-06-28-fix-vpn-and-l2l3-ux-bugs](openspec/changes/archive/2026-06-28-fix-vpn-and-l2l3-ux-bugs/) + **v2.2.2 patch** link type + IP 编辑能力 [archive/2026-06-28-fix-vpn-edit-capabilities](openspec/changes/archive/2026-06-28-fix-vpn-edit-capabilities/) + [archive/2026-06-28-backup-frontend](openspec/changes/archive/2026-06-28-backup-frontend/)） |
| **v2.3 修 bug + 健壮性补全** | ✅ 2026-06-29 (tag: v2.3.0) | 修 link-mode 4 bug / 备份 UI type / ops-toolkit 容器 / 真机集成测试 / 容器解耦蓝图 / vitest BLOCKED | [v2.3-roadmap PRD](openspec/changes/v2.3-roadmap/proposal.md) + 6 archived changes |
| **v2.3.1 真机回归 patch** | ✅ 2026-07-01 (tag: v2.3.1) | 修 v2.3.0 漏测：Loopback/Vsi IP 配 / 备份轮转 7→5 份 / 集成测试选口加固 | [archive/2026-07-01-fix-loopback-vsi-ipv4](openspec/changes/archive/2026-07-01-fix-loopback-vsi-ipv4/) + [archive/2026-07-01-fix-rotation-total-keep](openspec/changes/archive/2026-07-01-fix-rotation-total-keep/) + [archive/2026-07-01-v2.3-roadmap](openspec/changes/archive/2026-07-01-v2.3-roadmap/) |
| **v2.4 优化 + 工程化加固** | ✅ 2026-07-02 (tag: v2.4.0) | 修 v2.3.0 漏测接口显示 / status 映射 / link-mode 双向 / 异步备份 / ops-toolkit UX / 容器清理 / 3 容器蓝图定稿 | [RELEASE-NOTES-v2.4.0.md](RELEASE-NOTES-v2.4.0.md) + 4 bugfix + 2 feat + 1 roadmap (含 4 sub-change) |
| **v2.4.1 拆 3 容器实施** | ✅ 2026-07-03 (tag: v2.4.1) | ctrl + config + data 3 容器拆分 + 故障注入 + 双模式共存 + cleanup 端点 + 全量异步 + split 集成测试 | [v241-container-split](openspec/changes/archive/2026-07-03-v241-container-split/) + [v241-supplement](openspec/changes/archive/2026-07-03-v241-supplement/) + [RELEASE-NOTES-v2.4.1.md](RELEASE-NOTES-v2.4.1.md) |
| **v2.4.2 QA 工程化 + 压测 + review** | ✅ 2026-07-04 (tag: v2.4.2) | ESLint 进 qa + ops-toolkit 默认 .177 + 压测 .177 max-session + split 真机 e2e + 3 容器 review 报告 + P0 vue-tsc | [RELEASE-NOTES-v2.4.2.md](RELEASE-NOTES-v2.4.2.md) + [REVIEW-v242-3container-maturity.md](docs/REVIEW-v242-3container-maturity.md) |
| **v2.4.2.1 ops-toolkit 第 7 脚本** | ✅ 2026-07-04 (tag: v2.4.2.1) | paramiko-batch-exec.sh 单设备 SSH 批命令（复用 backend SSHExecutor + 4 级凭据 + Fernet 密文 + JSON 输出 + 11 单元 + 3 真机） | [v242-paramiko-tool](openspec/changes/archive/2026-07-04-v242-paramiko-tool/) + [RELEASE-NOTES-v2.4.2.1.md](RELEASE-NOTES-v2.4.2.1.md) |
| **v2.5.0 P1 工程化收口** | ✅ 2026-07-05 (tag: v2.5.0) | split 模式默认（**BREAKING**） + internal-api 5s TTL 缓存 + vitest 30 case + Playwright 37 case + ops-toolkit 第 8/9 脚本（interface-config + task-monitor） | [archive/2026-07-05-v25-roadmap](openspec/changes/archive/2026-07-05-v25-roadmap/) + [RELEASE-NOTES-v2.5.0.md](RELEASE-NOTES-v2.5.0.md) |
| **v2.6.0 i18n 中英双语** | ✅ 2026-07-06 (tag: v2.6.0) | vue-i18n v9 + 顶导「中 \| EN」切换 + localStorage 持久化 + **400+ 翻译 key（zh-CN + en-US）** + 后端 `APIResponse.error_key` schema 扩展（**BREAKING**） + 9 router 改造 + 26 后端单测 + 25 前端测试 | [archive/2026-07-06-v26-i18n](openspec/changes/archive/2026-07-06-v26-i18n/) + [RELEASE-NOTES-v2.6.0.md](RELEASE-NOTES-v2.6.0.md) + [docs/i18n-guide.md](docs/i18n-guide.md) |
| **v2.6.1 bug 修复轮次** | ✅ 2026-07-07 (tag: v2.6.1) | 6 个子 change：资产陈旧自动降级 / 采集失败可读化 / split 密码解密修 / vite proxy 精确分发 / **备份数据完整性**（下载 404 + 启动自检 + commit refresh + expire_on_commit + dump_db 工具） / **资产备份状态同步**（offline 设备按钮 disabled + force 逃生 + `backups.forced` 审计字段） / 备份回滚 SFTP 根因定位 + 1 个 review 反思 | [RELEASE-NOTES-v2.6.1.md](RELEASE-NOTES-v2.6.1.md) + [REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md) |
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

**预计包含 3 个 change + 2 个 patch**：

| change-id | 主题 | 状态 | 备注 |
|---|---|---|---|
| `interface-vpn-instance-and-l2-l3` | 接口 L2/L3 展示 + IP + VPN instance 联动（创建/绑定/解绑/删除） | ✅ 已 archive | [archive/2026-06-28-interface-vpn-instance-and-l2-l3](openspec/changes/archive/2026-06-28-interface-vpn-instance-and-l2-l3/) |
| **v2.2.1 patch** `fix-vpn-and-l2l3-ux-bugs` | unbind 预校验补 L3vpn 查询 + Modal 顶部加现有 VPN 列表 | ✅ 已 archive | [archive/2026-06-28-fix-vpn-and-l2l3-ux-bugs](openspec/changes/archive/2026-06-28-fix-vpn-and-l2l3-ux-bugs/) |
| **v2.2.2 patch** `fix-vpn-edit-capabilities` | 调整接口 link type (mode) + 给 L3 接口配 IP | ✅ 已 archive | [archive/2026-06-28-fix-vpn-edit-capabilities](openspec/changes/archive/2026-06-28-fix-vpn-edit-capabilities/) |
| `backup-ui` | 备份前端 UI（Devices.vue 表格行 + BackupListModal + CMDB 全量按钮） | ⏳ 未起 | v2.1.x 灰度的前端延后部分（已起 backup-frontend change，tasks 待 archive） |
| `interface-linked-config` | 接口联动配置（其他维度） | ⏳ 未起 | 用户原话"顺便再加一个能力" |

**v2.2.2 patch 详情（fix-vpn-edit-capabilities）**：
- 用户在 192.168.100.5 实测时发现 2 个能力缺失 bug：
  1. **L2/L3 link type 不可调**：前端展示 mode 字段但无入口
  2. **三层接口不能配 IP**：前端展示 ip_addresses 字段但无入口
- 后端新增 3 个路由：
  - `PATCH /api/devices/{id}/interfaces/{if_index}/link-type`（受保护护栏，H3C V7 切换会清空对应字段）
  - `POST /api/devices/{id}/interfaces/{if_index}/ipv4-address`（L3-only，IP/mask 格式校验，clear + set 模式）
  - `DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address`（L3-only，清空）
- 前端新增：
  - `Ipv4AddressEditModal.vue`（显示当前 IP + 新 IP/mask + 清空按钮）
  - Interfaces.vue 表格行 L2 加"改模式"、L3 加"改 IP"按钮
  - 改 link type 弹 ConfirmModal 二次确认 + 提示清空行为
  - 改 IP 内部应用/清空均经 ConfirmModal 二次确认
- H3C V7 适配：IPV4ADDRESS 复合 key (IfIndex, AddressOrigin) 中 `AddressOrigin=1` 必填，缺了设备报"indexical column missed"

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
- v2.4.1 完成 3 容器拆分（ctrl + config + data，数据层独立）✅ 已发版
- 容器解耦蓝图落地（已在 v2.1.x patch 预留，v2.4.1 实施）✅

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
| [openspec/AGENTS.md](openspec/AGENTS.md) | OpenSpec 使用规范（流程类） |
| [openspec/specs/](openspec/specs/) | 长期沉淀的 spec（按能力维度） |
| [openspec/changes/](openspec/changes/) | 进行中的 change |
| [openspec/changes/archive/](openspec/changes/archive/) | 已归档的 change |

---

## 6. 变更记录

| 日期 | 变更 | 作者 |
|---|---|---|
| 2026-06-28 | 初版：v1.0 → v2.1 + v2.1.x patch 灰度 + v2.2 规划 | session 续接 |
| 2026-06-29 | v2.2 第 1 项 archive + v2.2.1 patch（unbind 预校验 + Modal UX）+ v2.2.2 patch（link type + IP 编辑能力）archive | session 续接 |
| 2026-06-29 | v2.2.0 tag 发版（backup-frontend archive + 4 fix commits + spec 规范化，共 18 commits） | session 续接 |
| 2026-06-29 | v2.3.0 tag 发版（6 archived changes + 18 commits） | session 续接 |
| 2026-07-01 | v2.3.1 tag 发版（Loopback/Vsi IP 配修复 + 备份轮转 7→5 + 集成测试加固，3 archived + 14 commits） | session 续接 |
| 2026-07-02 | v2.4.0 tag 发版（7 change: 4 bugfix + 2 feat + 1 roadmap，10 个 archive 子目录，23 commits） | session 续接 |
| 2026-07-03 | v2.4.1 实施中（v241-container-split Task 1-8 完成：3 容器拆分 + 故障注入 + 真机 e2e，待 archive） | session 续接 |
| 2026-07-04 | v2.4.2 发版（3 change + 1 review 报告 + P0 vue-tsc + 9 commit，214 passed） | session 续接 |
| 2026-07-04 | v2.4.2.1 发版（1 change：v242-paramiko-tool paramiko-batch-exec.sh + 8 commit + 1 archive，225 passed） | session 续接 |
| 2026-07-05 | v2.5.0 tag 发版（split 默认 BREAKING + internal-api-cache + vitest 30 + playwright 37 + ops-toolkit 8/9 脚本，1 change + 15 commit，233 passed） | session 续接 |
| 2026-07-06 | v2.6.0 tag 发版（vue-i18n v9 + 顶导「中 \| EN」切换 + 400+ key + APIResponse.error_key BREAKING schema + 9 router 改造，1 change + 14 commit，291 passed） | session 续接 |

---

## 7. v2.3 修 bug + 健壮性补全（✅ 2026-06-29 tag: v2.3.0）

详见 [RELEASE-NOTES-v2.3.0.md](RELEASE-NOTES-v2.3.0.md)。

**6 个已 archive change + 1 个未来**：
1. `fix-link-mode-switch` — 4 bug 全修 + 真机集成测试 PASS（11.5s）
2. `test-backup-rotation-locked` — 3 单元测试保护锁定备份不被轮转
3. `add-ops-toolkit` — 容器化运维工具（5 预制脚本）
4. `add-integration-test-framework` — 真机集成测试框架（backup 4 + VPN 6）
5. `add-backup-type-radio-ui` — UI type radio + 修真 bug
6. `add-vitest-component-tests` — ⏸️ BLOCKED by EACCES node_modules
7. `v2.4-container-decoupling` — 📋 PROPOSAL（v2.3 不实施）

**测试统计**：
- 单元：105 passed + 11 skipped in 2.67s
- 集成（真机 192.168.100.4/.5）：11 case PASS

**关键 commit**：见 RELEASE-NOTES-v2.3.0.md 章节 8。

---

## 8. v2.4 优化 + 工程化加固（✅ 2026-07-02 tag: v2.4.0）

详见 [RELEASE-NOTES-v2.4.0.md](RELEASE-NOTES-v2.4.0.md)。

**主题**：v2.3.0/v2.3.1 漏测 bug 集中修复 + 工程化加固（ops-toolkit UX + 容器清理 + 3 容器蓝图定稿 + 异步备份）。**不是新功能大版本**。

**包含 7 个 change**：
1. `v24-bugfix-interface-display-100` — 100.100 接口 24→59 + 100.4/.5/.177 接口 7-11→58-63（NETCONF get 改 + operational data namespace）
2. `v24-bugfix-status-mapping` — OperStatus 1=UP 2=DOWN（RFC 2863 标准）+ 9 单测
3. `v24-bugfix-ui-feedback-and-loopback` — Loopback 弱匹配 + link-mode reason_code + 改层级按钮守卫 + 4 单测 + 7 detect_layer_v2 单测
4. `v24-feat-bridge-button` — L3 物理口加"改二层"按钮 + SSH [Y/N] 二次确认自动应答修复（v2.3.0 漏测 bug）+ 6 单测
5. `v24-feat-async-backup-status` — 异步备份/回滚：TaskManager (ThreadPoolExecutor 串行) + 4 异步端点 + Pinia store + BackgroundTaskPanel + localStorage 持久化 + 7+12=19 单测
6. `v24-roadmap` — v2.4 路线图聚合（4 sub-change）：
   - `v24-container-cleanup` — 盘点脚本 + SOP + 清理 1 容器 / 2 镜像 / 1 匿名 volume（基线 3 容器 / 6 镜像 / 1 命名 volume）
   - `v24-toolkit-ux-and-doc-discovery` — 6 脚本 `--device` 统一入口 + 回显带文档链接 + qa 容器 banner
   - `v24-decoupling-inventory-doc` — 3 容器蓝图定稿（sdn-control + data + monitor + 内部 API + 升级回退 SOP）
   - `v24-container-decoupling-3tier` — 蓝图定稿，**实施延后 v2.4.1**（独立 change）
7. `45aa929` — SSH [Y/N] 二次确认自动应答（v2.3.0 漏测 bug，回归发现）

**测试统计**：
- 单元：**172 passed, 11 skipped, 0 failed**（30.83s）
- 集成（真机 4 设备）：8 场景 PASS
- 前端 build：✅ 通过

比 v2.3.1 baseline (127 passed, 4 skipped) 新增 **+45 passed, +7 skipped**。

**关键 commit 序列**：见 RELEASE-NOTES-v2.4.0.md。

---

## 9. v2.4.1 拆 3 容器实施（🚧 实施中）

**主题**：把 v2.4.0 定稿的 3 容器蓝图落地为可运行代码，故障域隔离 + 双模式共存（monolith/split）渐进上线。

**关联 change**：[v241-container-split](openspec/changes/v241-container-split/)
**关联蓝图**：本文档 §9.关键设计决策 + §9.3 容器职责

### 关键设计决策

| 决策点 | v2.4.0 蓝图 | v2.4.1 实施 | 理由 |
|---|---|---|---|
| 容器划分 | sdn-control + data + monitor | **ctrl + config + data** | sdn-control 装太多（device+interface+vlan+execute+batch+log+auth+dashboard），拆得不平均；monitor v2.4 无业务，先不立 |
| 服务寻址 | 未明确 | **环境变量 + Docker DNS（12-factor）** | 避免硬编码 IP:Port，迁移/扩容友好 |
| 内部通信 | HTTP REST + X-Internal-Token | **保持**（httpx + 3 次指数退避 + 5s 超时） | 简单可控 |
| 数据库 | 3 容器各自 SQLite | **保持**（不迁 Postgres，决策点 v2.5/v3.0） | ROI 评估 |
| 上线策略 | 一次切换 | **monolith（默认）+ split（profile: split）双模式共存** | 故障可秒级回退 |
| 设备访问 | 未明确 | **统一 `device_access.py`**（monolith 本地查 / split 走 internal_api，SimpleNamespace 包装兼容） | 上层 router 代码无需感知模式差异 |

### 3 容器职责

| 容器 | 职责 | 数据库表 | 外部端口 |
|---|---|---|---|
| **ctrl** | 设备身份中心：device CRUD / 操作日志 / dashboard 聚合 | `devices` / `logs` / `alembic_version` | 8001 |
| **config** | 设备配置中心：interface / vlan / execute / batch | 无业务表（设备查询走 internal_api 调 ctrl） | 8002 |
| **data** | 数据采集存储：asset / backup / task | `assets` / `backups` / `tasks` / `alembic_version` | 8003 |

### 进度（截至 2026-07-03）

- ✅ Task 1：内部 API 客户端 + 鉴权中间件（httpx + 重试 + X-Internal-Token）
- ✅ Task 2：3 容器入口（ctrl/config/data_svc main.py + Dockerfile）
- ✅ Task 3：内部端点（ctrl_internal + data_internal）
- ✅ Task 4：业务改造（统一设备访问 `device_access.py` + 日志兜底 `log_recorder.py` + 5 router 替换）+ 跨容器查 assets 降级
- ✅ Task 5：docker-compose split profile + Vite proxy 按路径分发 + .env.example
- ✅ Task 6：数据库拆分/回滚脚本（双向验证：7 devices + 586 logs + 7 assets + 35 backups + 27 tasks 一致）
- ✅ Task 7：故障注入验证（docker stop data/ctrl/config 三场景 + 恢复后 194 passed, 11 skipped, 0 failed）
- ✅ Task 8：真机 e2e（7 设备列表 + 63 接口 NETCONF + running 备份成功 8224 bytes）
- 🚧 Task 9：文档更新（CONTAINER-DECOUPLING / VERSION-ROADMAP / CONTAINER-INVENTORY）
- ⏸️ Task 10：收尾（commit + archive + Postgres 决策点评估）

### 已知遗留（v2.4.2 follow-up）

- Task 4.2：删除设备时通知 data 清理关联 asset/backup（需新增 data 容器 cleanup 端点）
- Task 8.4/8.5：全量备份异步模式 e2e + 集成测试 4 设备 8 场景（留到发版前）
- Postgres 决策点：v2.4.1 收尾时评估 v2.5/v3.0 是否迁

### 测试统计（monolith 模式回归）

- 单元：**194 passed, 11 skipped, 0 failed**（v241-container-split）
- 真机 e2e：4 设备核心场景通过（设备管理 / 接口配置 / running 备份 / 故障注入）

**v2.4.1 收尾（v241-supplement，2026-07-03）**：

- 单元：**214 passed, 11 skipped, 0 failed**（从 194 → 214，新增 20 case）
- 3 task 全完成：cleanup 端点 (4) + device split integration (3) + 全量异步 (4) + split 集成测试 (9)
- 4 设备 × 8 场景 split 集成测试（mock 跨容器，monolith TestClient 跑，真机 e2e 留发版前 + MCP 浏览器）
- Postgres 决策点评估完成：v2.5 不迁，v3.0 评估点
- 发版 v2.4.1 tag

---

## 10. v2.4.2 QA 工程化 + 压测 + review（✅ 2026-07-04 tag: v2.4.2）

详见 [RELEASE-NOTES-v2.4.2.md](RELEASE-NOTES-v2.4.2.md) + [docs/REVIEW-v242-3container-maturity.md](docs/REVIEW-v242-3container-maturity.md)。

**主题**：v2.4.1 3 容器拆分实施 1 周后的成熟度 review + QA 工程化加固。**不开 v2.5**，因为 review 报告结论是"v2.4.2 可发版，P0（vue-tsc）必须做"。

**包含 3 个 change + 1 报告**：
1. **2026-07-04-v242-qa-and-tooling** — ESLint 进 qa 容器 + ops-toolkit 默认 test 设备 + qa 规范改写
2. **2026-07-04-v242-perf-and-e2e** — locust 压测 .177（5/10 并发达标，100/50 失败暴露设备 max-session） + split 模式真机 e2e 8 场景 + MCP 浏览器 e2e
3. **2026-07-04-v242-3container-review** — 3 容器 + 双 qa + ops-toolkit 成熟度 review 报告 + **P0 vue-tsc 实施**（qa-frontend 加 type-check）

**测试统计**：
- 单元：214 passed, 19 skipped, 33.42s（不变）
- qa-frontend：lint + type-check + build 三步全过，3s
- split 真机 e2e：8 场景全 PASS, 81.32s
- locust 5 并发 NETCONF：45 reqs / 0% fail / P99 1.9s ✓
- locust 10 并发 SSH 备份：31 reqs / 0% fail / P99 9.6s ✓
- MCP 浏览器 split 模式 CMDB 全量备份：14/14 任务 success

**关键 commit 序列**：见 RELEASE-NOTES-v2.4.2.md §5（9 commit + 1 chore）。

**v2.5 Backlog 入口**（review 报告 §4）：
- P0：vue-tsc（已做）
- P1：internal_api 5s TTL 缓存 / split mode 设为默认 / vitest EACCES 排障 / Playwright e2e / interface-config.sh / task-monitor.sh
- P2：SimpleNamespace 兼容层去掉 / 4 设备真机 e2e / pytest in-memory / debug 脚本归位
- P3：Postgres 决策 / qa-backend 加 docker CLI / help <script> 子命令

---

**最后更新**：2026-07-04 v2.4.2 已发版（3 change + 1 review 报告 + P0 vue-tsc，214 passed）

---

## 11. v2.4.2.1 ops-toolkit 第 7 脚本 paramiko-batch-exec（✅ 2026-07-04 tag: v2.4.2.1）

详见 [RELEASE-NOTES-v2.4.2.1.md](RELEASE-NOTES-v2.4.2.1.md) + [docs/ops-toolkit.md §4.7](docs/ops-toolkit.md#paramiko-batch-exec)。

**主题**：v2.4.2 review 报告 P1 项"加 paramiko 单设备排错工具"前置闭环。**不开 v2.5**，因为这是 ops-toolkit 工具集**第 7 脚本**，与 v2.4.2 review 报告 P1 backlog 对齐。

**包含 1 个 change**：
1. **2026-07-04-v242-paramiko-tool** — paramiko-batch-exec.sh（单设备 SSH 批命令执行）
   - 复用 backend `app/utils/ssh_executor.py`（**154 行薄壳**，不手搓 paramiko 协议）
   - 4 级凭据优先级 + **禁止 admin fallback**（找不到凭据明确报错）
   - Fernet 密文支持（`--pass-cipher`）+ .env `ENCRYPTION_KEY` 注入
   - JSON 默认输出（pytest 友好）+ text 模式（人类可读）
   - 11 单元测试（mock SSHExecutor）+ 3 真机集成测试（.177 设备）
   - 文档：`docs/ops-toolkit.md §4.7` 完整章节（用途/示例/参数/schema/复用说明/pytest 覆盖/限制）

**关键设计决策**：
| 决策 | 方案 | 理由 |
|---|---|---|
| 协议实现 | 复用 backend SSHExecutor | 避免重复造 H3C kex / 分页 / [Y/N] 轮子 |
| 凭据 fallback | **禁止 admin** | "贴心默认值"会掩盖 .env 注入失败（v2.4.2 复盘） |
| 凭据传参 | 严禁 `-e USERNAME=xxx -e PASSWORD=xxx` | 必须 `env_file: - .env`（避免 shell history 泄露） |
| 输出格式 | 默认 JSON | pytest 可直接 `json.load` 断言 |
| 单设备 | **明确边界** | 批量配置是工程工具的活，不是排错工具 |

**真机实测（.177 设备）**：
```json
{
  "host": "192.168.100.177",
  "total": 2,
  "success": 2,
  "failed": 0,
  "elapsed_ms": 1667,
  "results": [
    {"command": "display version", "returncode": 0, "stdout": "H3C Comware Software, Version 7.1.070, ...", "success": true},
    {"command": "display vlan 1", "returncode": 0, "stdout": "VLAN ID: 1\nVLAN type: Static\n...", "success": true}
  ]
}
```

**测试统计**：
- 单元：214 + 11 = **225 passed**, 19 skipped（**未破坏 v2.4.2 全部测试**）
- 真机集成：3 case PASS（display version / 批命令 / 设备别名）

**关键 commit 序列**：见 RELEASE-NOTES-v2.4.2.1.md §5（10 commit + 1 chore）。

**v2.5 Backlog 推进**（v2.4.2.1 闭环后）：
- ✅ **P1 加 paramiko 单设备排错工具**（v2.4.2.1 完成）
- 剩余 P1：internal_api 5s TTL 缓存 / split mode 设为默认 / vitest EACCES 排障 / Playwright e2e / interface-config.sh / task-monitor.sh
- 剩余 P2/P3：见 [docs/REVIEW-v242-3container-maturity.md §4](docs/REVIEW-v242-3container-maturity.md#4-v25-候选-backlog)

---

## 12. v2.5.0 P1 工程化收口（✅ 2026-07-05 tag: v2.5.0）

详见 [RELEASE-NOTES-v2.5.0.md](RELEASE-NOTES-v2.5.0.md) + [archive/2026-07-05-v25-roadmap/](openspec/changes/archive/2026-07-05-v25-roadmap/)。

**主题**：v2.4.2.1 发版后 3 容器架构已稳定，但 [REVIEW-v242-3container-maturity.md](docs/REVIEW-v242-3container-maturity.md) §4 暴露 6 项 P1 工程化遗留项。v3.0 VPC 起步依赖 3 容器架构稳定，现在不收口后续会随 VPC 复杂度放大。故起 v2.5 集中收尾 P1，作为 v3.0 起步前置。

**包含 1 个 change**：
1. **2026-07-05-v25-roadmap** — 6 P1 项集中收口
   - internal-api 5s TTL 缓存（dashboard 跨容器调用 50ms → 10ms）
   - **split 模式设为默认（BREAKING）**：`docker compose up` 起 3 容器，monolith 走 `--profile core`
   - vitest 组件测试 0 → 30 case（EACCES 修复 + 5 核心组件覆盖）
   - Playwright e2e 0 → 37 case（8 场景 + 公共 mock 框架）
   - ops-toolkit 第 8 脚本 `interface-config.sh`（vlan/access/trunk 4 子命令）
   - ops-toolkit 第 9 脚本 `task-monitor.sh`（task_id 轮询 + 退出码 0/1/2/3）

**关键设计决策**：
| 决策 | 方案 | 理由 |
|---|---|---|
| BREAKING 默认翻转 | 移除 `profiles: ["split"]`，加 `backend profiles: ["core"]` | 开发者经常忘加 profile → split 模式未被测试覆盖 |
| 缓存层位置 | `backend/app/internal_api.py` process-local dict | 简单够用；不引入 Redis 等额外组件 |
| e2e mock 方式 | Playwright route interception | 与后端解耦，CI 不需要真后端 |
| vitest 阻塞解法 | `chown -R node:node /app` | 容器内 node 权限问题（v2.3 遗留） |
| interface-config 协议 | **不重复造 NETCONF**，调后端 API | 后端 vlan/interface config 端点已实现 |
| task-monitor 退出码 | 0 成功 / 1 失败 / 2 超时 / 3 API 不可达 | CI 脚本可直接 `if task-monitor.sh X; then ...` |

**真机实测（.177 Test-Switch-177）**：
```bash
$ docker compose -f docker-compose.dev.yml run --rm ops-toolkit \
    interface-config.sh vlan add Test-Switch-177 950 "v25-test"
✅ 成功: 完成

$ docker compose -f docker-compose.dev.yml run --rm ops-toolkit \
    task-monitor.sh 33 --timeout 30 --interval 1
[████████████████████] 100% 成功
🎉 任务 33 执行成功
```

**测试统计**：
- **backend 单元**：225 + 8 = **233 passed**, 23 skipped（**未破坏 v2.4.2.1 全部测试**）
- **frontend 单元（vitest）**：3 smoke + 30 = **33 passed**
- **frontend e2e（playwright）**：8 场景 / **36 passed**（最后一次跑 37 全过）
- **真机集成**：2 case PASS（interface-config vlan add / task-monitor）

**关键 commit 序列**：见 RELEASE-NOTES-v2.5.0.md §6（15 commit：1 feat(cache) + 1 feat(BREAKING compose) + 2 test(vitest) + 2 test(playwright) + 1 test(e2e 修复) + 3 feat(ops-toolkit 脚本) + 3 fix + 1 docs(ops-toolkit) + 1 docs(tasks)）。

**v3.0 推进**（v2.5 闭环后）：
- v3.0 VPC（SDN + etcd 协调）正式开始
- 监控容器拆分（等需求明确后启动）

---

## 13. v2.6.0 i18n 中英双语（✅ 2026-07-06 tag: v2.6.0）

详见 [RELEASE-NOTES-v2.6.0.md](RELEASE-NOTES-v2.6.0.md) + [archive/2026-07-06-v26-i18n/](openspec/changes/archive/) + [docs/i18n-guide.md](docs/i18n-guide.md)。

**主题**：v2.5.0 P1 工程化收口后 3 容器 + split 默认 + 测试体系（vitest + playwright）全部稳定。
但 UI 与后端错误仍为中文单语，无法对外演示/英文用户使用。v3.0 VPC 起步面向多语用户（容器 + 监控），前端双语能力是基础设施前置。
需求：导航栏右上角加中英切换按钮，扫遍全项目（11 views + 10 components + App + Footer + 9 router error + 测试断言），做好中英切换。

**包含 1 个 change + 14 commit**：
1. **2026-07-06-v26-i18n** — i18n 完整闭环
   - vue-i18n v9 集成骨架（legacy: false composition API）+ locale 探测
   - 顶导右上角「中 | EN」切换按钮 + Pinia store + localStorage 持久化
   - 11 views 全 i18n（Dashboard / Devices / Interfaces / CMDB / Backup / Batch / OpsTerminal / Logs / Topology / AIAssistant / VLAN 弹窗）
   - 10 components 全 i18n（ConfirmModal / PageHeader / Select / DeviceFormModal / AssetEditModal / Ipv4AddressEditModal / VpnInstanceBindModal / BackupListModal / BackgroundTaskPanel / 工具栏）
   - App.vue + AppFooter.vue + utils/status.js + api/index.js 全 i18n
   - **400+ 翻译 key**（zh-CN + en-US 对齐）
   - 后端 `APIResponse` 新增 `error_key` + `error_params` 字段（**BREAKING SCHEMA**，向后兼容）
   - `backend/app/i18n_keys.py`（新建）：84 个 key 集中表 + `error_response()` helper + `FALLBACK_MESSAGES` 中文降级
   - 9 router 改造（device / interface / vlan / asset / backup / batch / execute / log / dashboard）
   - **26 后端单测** + **20 vitest** + **5 playwright i18n-switch**（共 51 新测试）

**关键设计决策**：
| 决策 | 方案 | 理由 |
|---|---|---|
| i18n 库 | vue-i18n v9（legacy: false） | Vue 3 官方库，composition API 友好 |
| 状态管理 | Pinia store（locale.js） | 响应式 + 模块化 |
| 持久化 | localStorage（key: `locale`） | 简单够用，无需后端参与 |
| 切换按钮位置 | 顶导右上角 K 用户头像前 | 用户视线第一落点 |
| 默认 locale | zh-CN | 项目当前用户群 |
| 后端 i18n 路径 | APIResponse 加 error_key + error_params | 与现有 success/data/error 兼容（向后兼容） |
| 后端降级策略 | FALLBACK_MESSAGES 字典 | 旧客户端拿到 error 字段仍可显示中文 |
| 集中管理 key | `i18n_keys.py` class + SimpleNamespace | 防止拼写错误 + IDE 自动补全 |
| 工具模块翻译 | 自建 `i18n/t.js`（非 i18n.global.t） | 避免 component scope 外响应式滞后 |
| conftest import 顺序 | 先 `import app.models` 再 `from app.main import app` | PEP 328 binding statement 不覆盖 app 变量 |

**真机实测（localhost:5173）**：
```text
# 1. 默认中文
访问 → 顶导 "总览 / 运维操作 / 运营管理 / 排查诊断" + 按钮"中 | EN"
Dashboard: "网络运维总览 / 7 台设备 · 7 在线 / 在管设备 / 在线设备 / 今日操作 / 刷新 / 新建任务"

# 2. 点击切换
顶导 → "Dashboard / Operations / Management / Troubleshooting" + 按钮"中 | EN"（EN 高亮）
Dashboard: "Network Operations Overview / 7 devices · 7 online / Managed Devices / Online Devices / Today's Operations / Refresh / New Task"

# 3. 刷新页面保持英文
localStorage: {"locale": "en-US"} 保留
```

**测试统计**：
- **backend 单元**：265 + 26 = **291 passed**, 23 skipped（**未破坏 v2.5.0 全部测试**）
- **frontend 单元（vitest）**：33 + 20 = **53 case** 全过
- **frontend e2e（playwright）**：37 + 5 = **42 e2e** 全过
- **真机集成**：1 case PASS（MCP 浏览器验证切换按钮 + 文案响应 + localStorage 持久化）

**关键 commit 序列**：见 RELEASE-NOTES-v2.6.0.md §7（14 commit：1 vue-i18n 骨架 + 1 切换 UI + 1 App/Footer + 1 utils/api + 5 views + 1 components + 1 BREAKING schema + 1 tasks chore + 2 test + 2 fix conftest）。

**v3.0 推进**（v2.6 闭环后）：
- v3.0 VPC（SDN + etcd 协调）正式开始
- i18n 拓展到 4 语言（zh-CN / en-US / ja-JP / ko-KR），面向亚太/全球用户
- 监控容器拆分（等需求明确后启动）

---

## 14. v2.6.1 bug 修复轮次（✅ 2026-07-07 tag: v2.6.1）

详见 [RELEASE-NOTES-v2.6.1.md](RELEASE-NOTES-v2.6.1.md) + [docs/REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md)。

**主题**：v2.6.0 i18n 上线后用户回归发现 dashboard 陈旧数据 + 备份/恢复链路多个问题，QA 套件盲区反思 + 集中修 6 类问题。
**无 BREAKING SCHEMA** — 纯修 bug + 加 1 个新审计字段 `backups.forced`。

**包含 6 个子 change + 1 review 反思 + 22 commit**：
1. **2026-07-07-fix-asset-stale-status** — assets 表超阈值自动降级 + dashboard 按阈值过滤（8 commit）
2. **2026-07-07-fix-asset-collect-failure** — 采集链路失败可读化（error_key + 中文 fallback，8 commit）
3. **2026-07-07-fix-asset-split-password-decrypt** — split 模式 password 二次解密修（3 commit）
4. **2026-07-07-fix-vite-proxy-route** — vite proxy 用正则精确分发修端点 404（1 commit）
5. **2026-07-07-fix-backup-data-integrity** — 下载 404 + 启动自检 + commit refresh + expire_on_commit + dump_db 工具（6 commit）
6. **2026-07-07-fix-asset-backup-state-sync** — offline 设备备份按钮 disabled + force 逃生 + `backups.forced` 审计字段（5 commit）+ 10 个 i18n key
7. **2026-07-07-fix-backup-restore-no-response** — 根因定位（设备缺 `sftp server enable`）+ 修复方案文档（1 docs）
8. **2026-07-07-v261-roadmap** — 总入口 proposal

**关键设计决策**：
| 决策 | 方案 | 理由 |
|---|---|---|
| `backups.forced` 审计字段 | Alembic 006 + `Mapped[bool]` + `server_default="0"` | 强制备份独立审计标记，不参与业务逻辑（不影响下载/回滚/删除/轮转） |
| 006 迁移 split 兼容 | `if "backups" not in insp.get_table_names(): return` 守卫 | ctrl/config 容器无 backups 表 → 直接跳过，避免 alembic 启动失败 |
| 资产陈旧降级 | `ASSET_STALE_HOURS` 配置 + 启动时一次性降级 | 24h 默认值，调试用 `ASSET_STALE_ENABLED=False` 关闭 |
| 备份数据完整性 4 防线 | 下载路由（vite proxy DOWNLOAD_PATTERN） + 启动自检（幽灵行清理） + commit refresh（防假成功） + expire_on_commit=False（防长任务属性 reload） | 分层防御，每层独立可关 |
| dump_db 工具 | `tools/dump_db.py` SQLite → JSON | 清理前人肉验证 + 离线性回退 |
| force 逃生 UI | Devices.vue 离线/未采集行内 force checkbox + 二次确认弹窗 + CMDB.vue 全量 force 选项 | 不挡正常用户流程（online 设备 0 摩擦），离线设备走二次确认防误操作 |

**真机实测（192.168.100.5 / .177 / .99 Test-Fake-Fail）**：
- 192.168.100.5 (Leaf-04)：临时 asset=offline → 无 force 备份 422 → force=true 备份成功 + DB.forced=1 → 恢复 online
- 192.168.100.177 (Test-Switch-177)：online 备份成功（API 默认路径，无 force 不入强制分支）
- 192.168.100.99 (Test-Fake-Fail，asset offline)：MCP 浏览器完整跑通 force 流程 + 中英切换验证 10 个 i18n key

**测试统计**：
- **backend 单元**：265 + 4 = **309+ passed**（v2.6.0 baseline + 4 个新 force 场景 case）
- **frontend 单元（vitest）**：53 case 全过（v2.6.0 baseline 不破）
- **frontend e2e（playwright）**：42 case 全过（v2.6.0 baseline 不破）
- **真机集成**：3 case PASS（.5 force 流程 / .177 online / .99 浏览器端到端）

**反思（v2.6.0 review）**：
> 详见 [docs/REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md)
>
> v2.6.0 archive 时 qa-backend 全量 pytest + qa-frontend lint+build 都过，但用户立刻发现 dashboard online=7 陈旧数据 bug。**QA 套件不覆盖"业务时间敏感"场景（如数据陈旧、过期降级）**。
>
> 改进方向：
> - Archive 前必须做"线上数据 sanity check"（curl 真实 endpoints 看返回是否符合业务预期）
> - 加"时间敏感"测试 fixture（mock 旧时间戳 → 验证降级逻辑）
> - 真机集成测试必跑 .177（不能跳过 switch down 的借口）

**关键 commit 序列**：见 RELEASE-NOTES-v2.6.1.md §3.1 / §3.2 + tasks.md 追验段（22 commit：8 stale + 8 collect + 3 split + 1 vite + 6 backup-data + 5 asset-backup-sync + 1 docs backup-restore + 1 tasks 追验 + 1 changelog 反思 + 1 fix c4456ef App.vue + 1 fix 3489546 _async_backup_fn）。

**v3.0 推进**（v2.6.1 闭环后）：
- v2.6.2 待定（按需启动小 patch）
- v3.0 VPC（SDN + etcd 协调）正式开始

---

## 12. 远期愿景（"未来"）

> 本章节是 A 类长期维护文档的"将来念想"部分（v2.4.2.1 加）。不写具体时间表，只列"未来"可能的方向。

### 12.1 方向（按可能性，不按时间）

| 方向 | 描述 | 触发条件 |
|------|------|----------|
| **sdn 容器（VPC）** | v3.0 引入，独立 SDN 协调器（etcd）+ VPC 能力 | 业务提出 VPC 需求 |
| **monitor 容器** | 独立监控 / 告警 / dashboard（Prometheus + Grafana）| 监控需求明确（目前弱）|
| **多厂商支持** | 抽象 NETCONF / CLI 适配层，支持 H3C 以外（华为 / 思科 / 锐捷）| 业务提出多厂商需求 |
| **Postgres 替代 SQLite** | 3 容器从独立 SQLite 迁到共享 Postgres（v2.4 评估点延期）| 数据规模 / 并发需求出现 |
| **Web UI 重构** | 当前 Vue 3 + Vite，未来可能换 React / Svelte 等 | UI 框架大版本不兼容时 |
| **CI/CD 集成** | GitHub Actions / GitLab CI 集成（当前裸写 CI 脚本）| 持续部署需求出现 |

### 12.2 注意

- 本章节只列"方向"，不承诺"时间表"
- 每个方向触发后，单独起 OpenSpec change（如 `v3-vpc` / `v25x-postgres-migration` 等）
- 方向删除 / 修改：直接改本章节，不需要单独归档
- 详细见 [§3 详细版本史 §monitor 远期](#33-详细版本史) 已记录的最早远期条目
