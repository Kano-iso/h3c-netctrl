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
| **v2.6.2 回滚预检 + 失败 UX** | ⏳ 2026-07-08 (待 tag v2.6.2) | 1 个 change：H3C V7 S6850 回滚无反应修复（probe + 端点 422 + paramiko 详细日志 + 前端 toast + 面板失败高亮 + `device.status.restore_unsupported` 字段）+ 1 review 反思 | [RELEASE-NOTES-v2.6.2.md](RELEASE-NOTES-v2.6.2.md) + [REVIEW-v262-bugfix-round-real-device-validation.md](docs/REVIEW-v262-bugfix-round-real-device-validation.md) |
| **v3.0 VPC 骨架** | ✅ 2026-07-18 (tag: v3.0.0) | SDN 业务下发通道（按 device.platform 路由 LSTN→SSH / RSTN→NETCONF）+ 双套 payload 模板（5 unit × 4 字段）+ 跨平台 .5/.26 真机验证。**v3.0 PRD 7 个子能力按新规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4**（详见 [PRD-V3.0.md](PRD-V3.0.md) 补充说明）| [PRD-V3.0.md](PRD-V3.0.md) + [RELEASE-NOTES-v3.0.0.md](RELEASE-NOTES-v3.0.0.md) + [archive/2026-07-16-sdn-vpc-netconf-schema-xml](openspec/changes/archive/2026-07-16-sdn-vpc-netconf-schema-xml/) |
| **v3.1.0 ZTP 调研** | ✅ 2026-07-18 (tag: v3.1.0) | H3C V7 ZTP 可行性调研 + 决策 B（精简 ZTP）+ 独立 ztp-server 容器（alpine + dnsmasq 二合一）+ autocfg.cfg 模板（T7064P15 验证通过）| [RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md) + [archive/2026-07-18-v31-ztp-research](openspec/changes/archive/2026-07-18-v31-ztp-research/) |
| **v3.1.1 ZTP 落地** | ✅ 2026-07-18 (tag: v3.1.1) | ztp-server jinja2 多平台模板 + DHCP 临时池 `.151-.190` + `ZTP_MGMT_IP` static OOB 写入 + `.177/.26` 真机完整 ZTP 验证 + ops-toolkit reboot/capture 加固 | [RELEASE-NOTES-v3.1.1.md](RELEASE-NOTES-v3.1.1.md) + [archive/2026-07-18-v311-ztp-landing](openspec/changes/archive/2026-07-18-v311-ztp-landing/) |
| **v3.1.2 ZTP 联动纳管** | ✅ 2026-07-18 (tag: v3.1.2) | ztp-server watcher 确认 static 管理地址 SSH 22 + NETCONF 830 上线后回调后端；后端幂等纳管入库 + 资产采集/partial 降级 + Devices/CMDB/Dashboard 现有接口可见；不走 DHCP lease 监听 | [RELEASE-NOTES-v3.1.2.md](RELEASE-NOTES-v3.1.2.md) + [archive/2026-07-18-v312-ztp-onboard-and-asset-sync](openspec/changes/archive/2026-07-18-v312-ztp-onboard-and-asset-sync/) |
| **v3.1.3 ZTP 恢复上线** | ✅ 2026-07-18 (tag: v3.1.3) | 前端 ZTP 恢复页面 + recovery override API + ztp-server runtime 渲染 + OOB `mgt` VRF 标准配置；不联动备份回滚 | [RELEASE-NOTES-v3.1.3.md](RELEASE-NOTES-v3.1.3.md) + [archive/2026-07-18-v313-ztp-recovery-override](openspec/changes/archive/2026-07-18-v313-ztp-recovery-override/) |
| **v3.2 平台迁移待办** | 🧊 2026-07-19 (暂缓) | 原计划新平台切换 + 能力评级；因 HCL/177 不能升级官方 S6850 镜像、EVE/V9850 二层广播不可信，当前转为未来迁移方案沉淀，不阻塞 v3.3 | [PRD-V3.2.md](PRD-V3.2.md) |
| **v3.3.0 VPC/EVPN 配置闭环** | ✅ 2026-07-19 (tag: v3.3.0) | VPC 按 Leaf 下发/撤回、端口绑定/解绑、网关局部撤回/加回、已有 VPC 接入口扩容、display 状态手动同步 + 600s 缓存；`.5` 真机完成本地下联与 EVPN Type-2/Type-3 验证 | [RELEASE-NOTES-v3.3.0.md](RELEASE-NOTES-v3.3.0.md) + [PRD-V3.3.md](PRD-V3.3.md) |
| **v3.4 前端大屏 + UX** | ⏳ 2026-07-18 (待启动) | VPC 详情页 + 端口矩阵 + 网络拓扑 + UX 打磨（5 步 VPC 向导 / 批量操作 / 错误处理）+ ops-toolkit-probes（3 个脚本）| [PRD-V3.4.md](PRD-V3.4.md) |
| **v3.5 etcd 协调** | ⏳ 远期 | 可选单节点 etcd / 轻量协调方案评估 | 暂未起 spec |
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

### v3.0 VPC 骨架（✅ 2026-07-18 tag: v3.0.0）

**目标**：SDN 起步，搭建**业务下发通道 + 双套 payload 模板 + 跨平台真机验证**骨架。本版本仅交付骨架能力，**v3.0 PRD 7 个子能力按新规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4**（详见 [PRD-V3.0.md](PRD-V3.0.md) 补充说明 + [VERSION-ROADMAP.md §1 全景表](VERSION-ROADMAP.md)）。

**PRD**：[PRD-V3.0.md](PRD-V3.0.md)

**前置依赖**：
- v2.4.1 完成 3 容器拆分（ctrl + config + data，数据层独立）✅ 已发版
- 容器解耦蓝图落地（已在 v2.1.x patch 预留，v2.4.1 实施）✅

**已闭环 change**：

| change-id | 状态 | 主题 | 关键产出 |
|---|---|---|---|
| `sdn-vpc-netconf-schema-xml` | ✅ 2026-07-16（42 commits push） | 业务下发通道选型 + 双套 payload 模板 + .5/.26 跨平台真机验证 | [archive](openspec/changes/archive/2026-07-16-sdn-vpc-netconf-schema-xml/) |

**已闭环 change 详情（sdn-vpc-netconf-schema-xml）**：

**业务下发通道最终定稿**（T1.13a-g 多轮探针，3 维证据链证实）：
- **L3vpn/VRF/RD/RT** → schema 化 NETCONF XML（所有 H3C V7 设备）
- **L2vpn/VSI/VXLAN/EVPN** → **按 device.platform 路由**：
  - LSTN 老平台（.5/.177 S6850）→ **SSH 22 + paramiko 跑 system-view CLI**（T1.13g 推翻 CLI-over-NETCONF，因 ncclient 同步 reply 不可靠）
  - RSTN 新平台（.26 V9850）→ schema 化 NETCONF XML
- **SSH 22 CLI** → fallback（同时是 LSTN 主通道）
- **RESTful / gRPC / Ansible** → 不投入（.5 设备业务 API 缺失 / gRPC 平台无 enable）

**双套 payload 模板架构**（5 unit × 4 字段）：
- `cli_commands`（LSTN 通道） + `xml_payloads`（RSTN 通道） + `undo_cli` + `undo_xml`
- `vpc_create` 5 unit: VSI-L2 / EVPN / L3VPN / VSI-L3 / Global
- `port_bind` 1 unit: service-instance + xconnect vsi（含 `encapsulation default` 跨平台兼容，T9 真机验证）

**A 方案修复**（T8, 2026-07-16）：
- RD 唯一性：1:{vni} 避免 VPC 间 RD 冲突
- `vsi-l3` unit 用 `quit` 不用 `return`（避免退出 system-view 后续命令 Unrecognized）
- MAC 地址用 H-H-H 格式（设备内部归一化）
- SSH error_indicators 增强：识别 "The RD is used by another EVPN instance."（不带 `%` 前缀的业务级错误）
- 内部 API platform 字段透传
- Asset PUT/i18n error code 修复

**跨平台真机验证**（.5 LSTN/SSH + .26 RSTN/NETCONF, 2026-07-16）：
- vpc0001 业务命令 union 一致（vsi / vxlan 20000 / evpn encapsulation vxlan / RD 1:20000）
- port_bind service-instance 1001 业务命令 union 一致（GE1/0/4 + HGE1/0/8）
- **配置面 100% 一致**（数据面 .26 受限暂不验证，符合 user 指示"只管配置面"）

**数据模型扩展**：
- `Device.platform: Optional[str]` 字段（alembic 009 迁移幂等）
- `SdnDeployment.unit: str` + `parent_deployment_id: Optional[int]` 字段（alembic 008 迁移幂等）

**回归**：
- 73 SDN 单测全过
- 全量 432 PASS / 3 pre-existing FAIL（async_backup + split_integration, 与本 change 无关）
- 42 commits push to origin/main（e5b2e61..5690d60）

**待推进 change**：

| change-id | 主题 | 状态 |
|---|---|---|
| `sdn-vpc-prd-and-model` | 数据模型、术语、PRD/Spec 定稿 | **v3.2**（VPC 全能力验证时一起做）|
| `sdn-vpc-foundation` | 租户/VPC CRUD、Alembic、配置计划生成 | **v3.2**（VPC 全能力验证时做）|
| `sdn-l3vni-validation` | L3VNI、RD/RT、EVPN route、ARP/MAC 状态采集与校验 | **v3.2**（VPC 全能力验证时做）|
| `sdn-port-binding` | 端口随接随入与端口状态可视化 | **v3.2**（VPC 全能力验证时做）|
| `sdn-gateway-fallback` | 单设备单 VPC 集中式网关降级/恢复与排障校验 | **v3.3**（剩余 VPC 能力）|
| `sdn-visual-overview` | 前端大屏、端口矩阵、VPC 详情 | **v3.4**（前端集中做）|
| `sdn-ops-toolkit-probes` | ops-toolkit 增加 VPC/EVPN 专用探测 | **v3.4**（工具随前端）|
| `sdn-etcd-coordination` | 可选单节点 etcd / 轻量协调方案评估（不作为 P0 前置依赖） | **v3.5 远期** |

**v3.0.0 骨架发版**：

- ✅ **业务下发通道**（T1.13a-g 多轮探针，3 维证据链证实）：
  - L3vpn/VRF/RD/RT → schema 化 NETCONF XML（所有 H3C V7 设备）
  - L2vpn/VSI/VXLAN/EVPN → **按 device.platform 路由**（LSTN→SSH 22 / RSTN→schema 化 NETCONF）
  - RESTful / gRPC / Ansible → 不投入
- ✅ **双套 payload 模板**（5 unit × 4 字段）：`cli_commands` + `xml_payloads` + `undo_cli` + `undo_xml`
  - `vpc_create` 5 unit: VSI-L2 / EVPN / L3VPN / VSI-L3 / Global
  - `port_bind` 1 unit: service-instance + xconnect vsi（含 `encapsulation default` 跨平台兼容）
- ✅ **跨平台真机验证**（.5 LSTN/SSH + .26 RSTN/NETCONF, 2026-07-16）
  - vpc0001 业务命令 union 一致（vsi / vxlan 20000 / evpn encapsulation vxlan / RD 1:20000）
  - port_bind service-instance 1001 业务命令 union 一致（GE1/0/4 + HGE1/0/8）
- ✅ **数据模型扩展**：`Device.platform` / `SdnDeployment.unit` / `SdnDeployment.parent_deployment_id`（Alembic 008/009 迁移幂等）
- ✅ **测试统计**：73 SDN 单测全过 + 全量 432 PASS / 3 pre-existing FAIL
- ✅ **42 commits push to origin/main**（e5b2e61..5690d60）

---

### monitor（⏳ 远期）

**目标**：独立监控 / 告警 / dashboard 容器，对接 Prometheus + Grafana。

**前置依赖**：
- v3.0 VPC 稳定
- 监控需求明确（目前用户未提出）

**注意**：目前监控诉求弱（用户原话："监控将来一定是个大东西"），暂不主动起 change。

---

### v3.1 ZTP 调研（✅ 2026-07-18 tag: v3.1.0）

**主题**：H3C V7 设备 ZTP（Zero Touch Provisioning）调研 + 基建容器。本 change **无新功能落地**，仅完成可行性评估 + 决策 + 基建。

**调研结论**：

| 阶段 | 状态 | 结论 |
|---|---|---|
| T1 文档调研 | ✅ | H3C 官方 VCF ZTP 仅 S6805/S6825/S6850/V9850/S9820 + R6607+ 支持；本项目 3 设备多数不满足 |
| T2 真机探针 | ✅ | 3 设备 `ztp enable` / `display ztp status` / `display ztp history` 全部 Unrecognized |
| T1 后期新发现 | ✅ | H3C V7 还有"自动配置"功能（autocfg.cfg），不依赖 VCF ZTP 命令，理论上所有 V7 支持 |
| T3 基建 | ✅ | 独立 `ztp-server` 容器（alpine + dnsmasq 二合一，`network_mode: host`）|
| T4 真机验证 | ✅ | .177 T7064P15 attempt 2 完整链路通：DHCP → TFTP → 执行 → "successfully completed" |
| T5 决策 | ✅ | **决策 B（精简 ZTP）**：保留 ztp-server 容器 + autocfg.cfg 模板精简 |

**autocfg.cfg 模板精简**（T7064P15 验证通过）：

```h3c
sysname ztp-device
ssh server enable
local-user admin class manage
 password simple admin
 service-type ssh terminal
 authorization-attribute user-role network-admin
 authorization-attribute user-role level-15
quit
user-interface vty 0 15
 authentication-mode scheme
 protocol inbound ssh
quit
netconf ssh server enable
password-control login-password-change disable
save force
```

**T4 实证关键发现**：
- ✅ autocfg 机制**完全工作**：attempt 2 链路通（DHCP → TFTP → 执行 → "successfully completed"）
- ✅ autocfg.cfg 模板**大部分生效**：sysname / local-user / ssh / netconf / save force
- ⚠️ **唯一不生效**：Vlan1 IP 配置行（`ip gateway` T7064P15 Unrecognized + Vlan1 因无物理接口 up 而 down）
- ⚠️ **副作用**：H3C V7 默认首次 SSH 登录强制改密（autocfg.cfg 模板加 `password-control login-password-change disable` 关改密）
- ✅ **autocfg 机制自动处理 OOB 口 + DHCP client**：attempt 2 自动 enable M-GE 0/0/0 + DHCP 拿 IP

**变更清单**：
- `docker/ztp-stack/`：新独立容器（alpine + dnsmasq 二合一）
- `docker/ztp-stack/tftp/autocfg.cfg.template`：精简版（删 IP 配置 + 加关改密）
- `docker/ztp-stack/entrypoint.sh`：模板渲染（env vars → dnsmasq.conf + autocfg.cfg）
- `docker-compose.dev.yml`：新增 ztp-server 服务（`profiles: ["ops"]` + `network_mode: host`）
- `.env.example`：ZTP_* 变量定义
- `docs/ztp-stack.md`：容器使用文档 + 真机验证 SOP

**后续 change 计划**（**未启动，等 user 决策**）：

| Change | 范围 | 状态 |
|---|---|---|
| v3.1.1 ztp-landing | autocfg.cfg 模板适配多平台 + `.177/.26` 完整 ZTP 真机验证 + ops-toolkit reboot/capture 加固 | ✅ 已完成 |
| v3.1.2 ztp-onboard-and-asset-sync | ztp-server watcher 确认 static 管理地址上线后回调后端，完成纳管入库 + 资产采集 + 前端现有页面可见 | ✅ 已完成 |
| v3.1.3 ztp-recovery-override | 已有设备清空配置后的 ZTP 恢复上线旁路能力，前端可临时指定 OOB 地址 | ✅ 已完成 |

**用户愿景**（2026-07-17 02:13 + 2026-07-18）：
> "ZTP 阶段只做基础配置（SSH 22 + 带外 IP + NETCONF 830 + 凭据），不做业务配置（VPC / 端口绑定 / 路由协议 / 业务 VLAN），不做配置联动（ZTP 完成后由 controller 推业务配置）"
>
> "白屏用户能不用做任何的操作，就能看他上线（自动上线）" —— v3.1.2 实现基础联动；专门 ZTP 产品页面后续单独起。

**回退**：v3.1.1 真机验证失败（多平台不兼容）→ 决策 C 重新评估。

---

### v3.1.1 ZTP 落地（✅ 2026-07-18 tag: v3.1.1）

**目标**：解决 v3.1.0 留下的 2 个未解决问题：① 设备管理 IP 不持久 ② 多平台 autocfg 模板未适配。

**OpenSpec**：[archive/2026-07-18-v311-ztp-landing](openspec/changes/archive/2026-07-18-v311-ztp-landing/)
**Release Notes**：[RELEASE-NOTES-v3.1.1.md](RELEASE-NOTES-v3.1.1.md)

**完成范围**：
- **DHCP 临时池 + static OOB 写入**：DHCP 池 `.151-.190` 只用于首启拉配置；设备最终管理地址由 `ZTP_MGMT_IP` 渲染进 autocfg.cfg 并写入 physical OOB 口。
- **autocfg.cfg 多平台适配**：1 份 `autocfg.cfg.j2`，按 `ZTP_PLATFORM=lstn|rstn` 生成 LSTN/S6850 与 RSTN/V9850 配置；HCL T7064P15 通过 `ZTP_HCL_T7064P15=true` 打开独有改密规避命令。
- **sysname 动态派生**：`ZTP_SYSNAME` 留空或保持旧默认 `ztp-device` 时，按 `ZTP_MGMT_IP` 生成 `ztp-switch-101` / `ztp-switch-102`。
- **ops-toolkit 加固**：`reboot-wait.sh` 支持 reset saved-configuration + reboot + 等待目标 IP；`capture-config.sh` 补齐 H3C V7 低版本 RSA/SCP 兼容参数。

**真机验证**：

| 设备 | 平台 | 结果 |
|---|---|---|
| `.177` | S6850 / T7064P15-hcl / LSTN | 完整 ZTP 链路通过，最终 static `.101`，SSH 22 + NETCONF 830 通，二次 reboot 持久 |
| `.26` | V9850-256H / R7643P02 / RSTN | 完整 ZTP 链路通过，最终 static `.102`，sysname `ztp-switch-102`，SSH 22 + NETCONF 830 通，二次 reboot 持久 |
| `.5` | S6850 / T7064P15-prod / LSTN | 不跑完整 ZTP，仅保留 OOB/static 命令探针佐证 |

**关键边界**：
- v3.1.1 不做 controller 自动纳管、不入库、不前端可见；这些进入 v3.1.2。
- v3.1.1 不从 dnsmasq lease 自动计算 static IP；当前由 `ZTP_MGMT_IP` 指定，v3.1.2 基于该 static 管理地址做纳管联动，不走 DHCP lease 监听。
- ZTP 阶段只写基础配置：SSH 22、NETCONF 830、项目统一账号、physical OOB static IP，不写 VPC/业务 VLAN/路由协议。

**关键 commit 序列**：
- `8551310 test(ztp): T7 容器层 CI 验证`
- `8a7aa03 chore(ztp): T8 qa-backend 回归 N/A`
- `0bc0592 docs(ztp): sync v3.1.1 handoff scope`
- `40257b7 test(ztp): T9 .177 ZTP链路验证与RSTN模板纠偏`
- `bd80e79 fix(ztp): 按管理IP派生sysname并收紧RSTN模板`
- `4472e35 test(ztp): T10 .26 RSTN完整ZTP链路验证`

**已知注意点**：当前环境重建 ztp-server 镜像时曾遇到外部 alpine 镜像代理 401；真机验证使用已有镜像并挂载当前模板/entrypoint 完成。修复镜像源后可重新 build。

---

### v3.1.2 ZTP 联动纳管（✅ 2026-07-18 tag: v3.1.2）

**目标**：设备 ZTP 完成后，平台基于 static 管理地址完成纳管入库、资产采集和前端可见。原 v3.1.2“自动纳管”和 v3.1.3“资产可见”合并到本版本。

**OpenSpec**：[archive/2026-07-18-v312-ztp-onboard-and-asset-sync](openspec/changes/archive/2026-07-18-v312-ztp-onboard-and-asset-sync/)
**Release Notes**：[RELEASE-NOTES-v3.1.2.md](RELEASE-NOTES-v3.1.2.md)

**范围**：
- **不走 DHCP lease 监听**：当前 dnsmasq/autocfg 链路无法稳定承担“从租约自动发现最终 static IP”的职责。
- **ZTP watcher 触发**：ztp-server 在 `ZTP_ONBOARD_ENABLED=true` 时后台等待 `ZTP_MGMT_IP` 的 SSH 22 与 NETCONF 830 均开放，再 POST `/api/ztp/onboard`。
- **后端纳管联动**：`/api/ztp/onboard` 做二次 SSH/NETCONF 探测，创建或更新设备记录，同 host 重复触发幂等更新。
- **资产采集联动**：纳管成功后触发资产采集，刷新 model / serial / software / mgmt IP / vendor 等 CMDB 字段；资产采集失败返回 `partial` 并把 asset 标记为 offline。
- **前端可见**：Devices / CMDB / Dashboard 复用现有接口和刷新逻辑即可看到新增设备与统计变化。
- **后续产品化页面**：上线设备、下线设备、ZTP 生命周期管理单独起前端页面，不塞进本版本。

**依赖**：v3.1.1（静态 IP 持久化）

**QA**：
- `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest -q tests/test_ztp_onboard.py tests/test_data_internal.py` → 12 passed

### v3.1.3 ZTP 恢复上线（✅ 2026-07-18 tag: v3.1.3）

**目标**：为已有设备提供一个旁路恢复能力。设备配置丢失后，用户在前端临时指定原管理地址，ztp-server 将 `autocfg.cfg` 渲染为该地址，使设备先恢复 OOB、SSH、NETCONF 与统一账号。完整配置恢复仍由备份回滚页面负责。

**OpenSpec**：[archive/2026-07-18-v313-ztp-recovery-override](openspec/changes/archive/2026-07-18-v313-ztp-recovery-override/)
**Release Notes**：[RELEASE-NOTES-v3.1.3.md](RELEASE-NOTES-v3.1.3.md)

**完成范围**：
- 新增 `/api/ztp/recovery-override` GET / POST / DELETE。
- 后端写入共享文件 `data/ztp/recovery_override.json`，不修改 `.env`。
- ztp-server 挂载 `./data/ztp:/ztp-state`，运行时监控 override 并重渲染 `autocfg.cfg`。
- `autocfg.cfg` 标准模板补齐 `ip vpn-instance mgt` 与 OOB 口 `ip binding vpn-instance mgt`。
- 前端运营管理新增“ZTP 恢复”页面。
- 备份回滚移除“未来”标记；拓扑 / AI 继续保留“未来”标记。

**边界**：
- 不自动触发配置回滚。
- 不做 MAC 绑定、DHCP lease 监听、自动识别具体设备。
- 清除 recovery override 后恢复默认 ZTP 序列。

**QA**：
- `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest -q tests/test_ztp_recovery.py tests/test_ztp_onboard.py tests/test_device_api.py` → 16 passed
- `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend npm run test:unit -- src/__tests__/ZtpRecovery.spec.js src/__tests__/Smoke.spec.js` → 20 passed
- `docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend npm run build` → passed

---

### v3.2 平台迁移待办（🧊 2026-07-19 暂缓）

**目标**：v3.2 原计划分两步完成新平台迁移与能力评级，当前已转为未来迁移方案沉淀，不作为 v3.3 阻塞项：

**PRD**：[PRD-V3.2.md](PRD-V3.2.md)

**范围**：
- **v3.2.1 新平台割接迁移**：用户逐台通过 ZTP 上线新平台设备，人工确认“新 OOB 地址 ↔ 旧设备身份”映射；旧平台 OOB 地址迁入备份地址段，新平台恢复关键业务配置。
- **v3.2.2 新平台能力评级**：在新平台上验证管理面、ZTP、备份/回滚、现有前端、SDN/VPC 下发/回收/校验能力，形成 A/B/C/D 能力评级和后续缺口清单。
- **VPC 全能力验证**：v3.0 PRD 4 个子能力在新平台验证（prd-and-model / foundation / port-binding / l3vni-validation）。

**走法**：
1. 新平台设备 ZTP 上线，确认 SSH/SCP/NETCONF 可达。
2. 用户提供新旧设备映射，例如 `.103 -> 原 .2`、`.104 -> 原 .3`、`.105 -> 原 .100`。
3. 维护窗口内调整旧平台 OOB 地址到备份段，避免管理地址冲突。
4. 对照旧配置与新平台配置，迁移平台无关配置，适配物理接口/OOB/平台差异配置。
5. 在新平台做管理面、备份回滚、ZTP、SDN/VPC 能力评级。
6. 发版收尾（未来真正迁移时再生成 RELEASE-NOTES + tag + push）。

**依赖**：v3.0 骨架 + v3.1 ZTP 全部完成

**用户原话**：
> "v3.2 加固切换，配合 ztp 的能力，做架构切换，切换到 eveng 平台"
> "v3.2 把所有的 qa 做了，就是包括 sdn 的后端现在已有能力"

---

### v3.3.0 VPC/EVPN 配置闭环（✅ 2026-07-19 tag: v3.3.0）

**目标**：在 v3.2 平台迁移暂缓后，直接基于现有平台补齐 VPC/EVPN 后端生命周期闭环。

**PRD**：[PRD-V3.3.md](PRD-V3.3.md)
**Release Notes**：[RELEASE-NOTES-v3.3.0.md](RELEASE-NOTES-v3.3.0.md)

**范围**：
- **VPC 级编排**：按 Leaf 下发 / 撤回 VPC，deployment 保留设备、unit、状态和错误信息。
- **端口生命周期**：端口绑定 / 解绑，deployment 关联 `port_binding_id`。
- **局部操作**：单设备 VPC 补回、三层网关撤回、三层网关加回。
- **已有 VPC 接入口扩容**：开始扩容进入 `expanding`，完成时做网关 ping 与 display 校验。
- **状态采集**：手动同步 + 600 秒缓存 + latest 快照，采集 BGP EVPN peer、VSI/Vsi-interface、AC、MAC、ARP、Type-2/Type-3。
- **真机验证**：`.5 / Leaf-04 / 192.168.100.5` 完成本地下联 ping、MAC/ARP、Type-2/Type-3 advertised-routes 验证。

**边界**：
- 不做前端大屏，留到 v3.4。
- 不做高频自动采集。
- 远端同 VNI 主机互通因实验环境不足转后续验证。

---

### v3.4 前端大屏 + UX（⏳ 2026-07-18 待启动）

**目标**：VPC 详情页 + 端口矩阵 + 网络拓扑 + UX 打磨 + ops-toolkit-probes。

**PRD**：[PRD-V3.4.md](PRD-V3.4.md)

**范围**：
- **VPC 详情页**：单一 VPC 全景视图（VPC / 端口 / 网关 / 路由 / 状态）
- **端口矩阵**：所有设备 × 所有端口 × VPC 归属色 + 状态指示
- **网络拓扑**：underlay + overlay 拓扑图（d3.js / vis.js / echarts 选型）
- **UX 打磨**：5 步 VPC 创建向导 + dry-run 预览 + 批量操作 + 错误处理
- **ops-toolkit-probes**：3 个脚本（`sdn-vpc-status` / `sdn-evpn-routes` / `sdn-vxlan-tunnels`）

**走法**（4 阶段）：
1. VPC 详情页（依赖 v3.2/v3.3 后端）
2. 端口矩阵 + 网络拓扑
3. UX 打磨
4. ops-toolkit-probes（3 个脚本）

**依赖**：v3.2 / v3.3 后端 + v2.6.0 i18n

**用户原话**：
> "3.4 做前端其实我觉得这个前端的逻辑也很重要啊... 考虑到用户体验"
> "当然你也不可能往十全十美，这个在后面再考虑吧"

---

### v3.5 etcd 协调（⏳ 远期）

**目标**：可选单节点 etcd / 轻量协调方案评估。

**状态**：⏳ 远期，暂未起 spec

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
- v3.0 VPC/SDN PRD 与 OpenSpec 拆分准备
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
- v3.0 VPC/SDN PRD 与 OpenSpec 拆分准备
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
- v3.0 VPC/SDN PRD 与 OpenSpec 拆分准备

---

## 15. v2.6.2 回滚预检 + 失败 UX（⏳ 2026-07-08 待 tag v2.6.2）

详见 [RELEASE-NOTES-v2.6.2.md](RELEASE-NOTES-v2.6.2.md) + [docs/REVIEW-v262-bugfix-round-real-device-validation.md](docs/REVIEW-v262-bugfix-round-real-device-validation.md) + main spec [`openspec/specs/backup-restore-support/spec.md`](openspec/specs/backup-restore-support/spec.md)。

**主题**：v2.6.1 复盘发现 H3C V7 设备"回滚无反应"根因是 S6850/S6860/S9850 系列默认禁用 SFTP/SCP subsystem，v2.6.2 落地"启动前 probe + 端点预检 + 前端可视化"3 套防线 + 1 个新 `device.status` 字段。
**无 BREAKING SCHEMA** — 纯修 bug + 加 1 个新 `DeviceResponse.restore_unsupported: Optional[bool]` 字段。

**包含 2 个子 change + 1 review 反思 + 11 commit**：
1. **2026-07-08-fix-backup-restore-support** — H3C V7 SCP 不支持设备预检 + 422 + 前端 toast + 面板高亮 + 状态字段（9 commit + 3 mock 测试）
2. **2026-07-08-v262-roadmap** — 总入口 proposal + tasks
3. **docs/REVIEW-v262-bugfix-round-real-device-validation.md** — 真机 .177/.5 验证记录（dev 环境跳过，逻辑已 mock 覆盖）
4. **openspec/specs/backup-restore-support/spec.md** — main spec 沉淀（7 requirement + 各 task Scenario）

**关键设计决策**：
| 决策 | 方案 | 理由 |
|---|---|---|
| probe 机制 | 推 1 字节 dummy 文件 + SSH exec delete 清理 | 不依赖具体 H3C 型号；scp subsystem 禁用时立即 `Channel closed`，SSH exec 仍可用 |
| 端点预检位置 | `restore_async` 启动前 probe | 提前拦截，避免 task 提交后才发现不可用（"无反应"问题根因） |
| 设备状态字段 | `device.status.restore_unsupported: Optional[bool]` + 5s TTL 缓存 | 前端可基于此字段禁用"回滚"按钮 + 显示提示（无需等用户点回滚才知道） |
| 缓存 TTL | 5s | 与 v2.5 internal-api 5s TTL 一致；list 接口 N 设备 × probe 1s 性能可接受 |
| probe 失败兜底 | 按"支持"处理 + ERROR 日志 | 探测失败不应阻塞原 task 流程（如 SSH 偶发抖动） |
| 前端 toast | Pinia store + 全局组件 + 5s 自动消失 | 任务失败 UX 提升（v2.6.1 复盘"用户必须点进面板才看到错误"） |
| 失败 chip 视觉 | `text-bad` 颜色 + 红色 SVG + `ring-2 ring-bad/40` 描边 | 即使折叠态也醒目（v2.6.1 复盘"折叠态无反馈"） |
| `device_model` 来源 | `device.asset.model`（不在 Device ORM 上） | Device 模型只存网络身份；硬件属性在 Asset |
| 错误码 fallback | `Backup.RESTORE_NOT_SUPPORTED: "设备 {device_model} 不支持 SCP 推回，无法回滚: {reason}"` | 明确给设备型号 + 原因（v2.6.1 复盘"无反应"调试困难） |

**测试统计**：
- **backend 单元**：245+ → **317 passed**（+5：T1 probe 函数 2 个 + T7 restore_async 422/支持/probe 失败兜底 3 个）
- **backend 失败**：3（baseline 已存在，与本次改动无关：test_backups_async_success_with_2_devices + 2 split integration）
- **frontend lint + build**：全过
- **真机集成**：dev 环境 `.5/.177` 不可达（仅 `.100` Spine 可达），逻辑已通过 mock 覆盖

**真机回归（待生产环境窗口）**：
- [ ] .5 设备点回滚 → toast 弹"设备 S6850 不支持 SCP 推回，无法回滚"
- [ ] .5 设备 Backend log 含 `paramiko.ssh_exception.SSHException: Channel closed.`
- [ ] .177 设备点回滚 → toast 弹"回滚成功"或正常进度
- [ ] .177 设备 Backend log 含 `restore success`

**关键 commit 序列**：
- T1 `a40dde2` probe 函数 + device_model 参数
- T2 `c1b33bb` 端点预检 + 422（`fa140de` 修 T2 device.model bug + 加 err 注册）
- T3 `5cd3ad7` 详细 paramiko 错误日志
- T4 `9a5f26f` toast 系统 + taskStore 失败触发
- T5 `44d59be` BackgroundTaskPanel 失败高亮
- T6 `167063e` device.status restore_unsupported 字段
- T7 `fa140de` mock scp.put Channel closed 测试（合并 T2 patch）
- T8 `62511d9` 真机验证记录
- T9 `828cba2` docs/ops-toolkit.md S6850 SCP 限制
- archive `fee6d33` 2 change 闭环
- main spec `7080c46` 沉淀

**v3.0 推进**（v2.6.2 闭环后）：
- v3.0 VPC/SDN 正式进入 PRD 与 OpenSpec 拆分阶段
- 远期 vision 12.1 节按 v3.0 进展更新

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
