# H3C NetCtrl

基于 NETCONF + SSH 的 H3C 交换机轻量网控平台。

> **下一代产品蓝图草案**：[PRD-VNEXT.md](PRD-VNEXT.md) 定义业务视角与底层分析、分阶段演进、前端主导 / 后端协作，以及文末的一期接入闭环范围。Draft，待用户评审，不代表新版本已立项或相关能力已交付。

## 版本路线图

> **统一的版本管理文档：[VERSION-ROADMAP.md](VERSION-ROADMAP.md)**
>
> 任何关于"当前到哪一版 / 之前完成啥 / 接下来做啥"的问题，以该文档为准。

| 版本 | 状态 | 主题 | 详情 |
|---|---|---|---|
| v1.0 MVP | ✅ 2026-06-13 | 基础 CRUD + NETCONF VLAN/接口 | [archive/2026-06-13-v1-mvp-foundation](openspec/changes/archive/2026-06-13-v1-mvp-foundation/) |
| v2.0 平台化 | ✅ 2026-06-22 | 8 项：NETCONF 重构 / QA 测试套件 / bugfix 轮次 / Schemas v2 | [archive 目录](openspec/changes/archive/) |
| v2.1 前端重构 | ✅ 2026-06-23 | 7 项：多命令终端 / 设备 CRUD UI / 资产编辑 / 单设备采集 / 状态判定修复 | [archive 目录](openspec/changes/archive/) |
| v2.1.x patch 灰度 | ✅ 2026-06-29 并入 v2.2.0 | 手动备份后端能力（前端在 v2.2 backup-frontend 补齐） | [v21x-patch-backup-backend](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/) |
| **v2.2.0 网控增强** | ✅ **2026-06-29 (tag: v2.2.0)** | 备份前端 / 接口 VPN / 接口 L2-L3 + link type + IP / 联动配置 / 4 收尾 bug fix | [**RELEASE-NOTES-v2.2.0.md**](RELEASE-NOTES-v2.2.0.md) · [archive 目录](openspec/changes/archive/2026-06-28-*) |
| **v2.3.0 修 bug + 健壮性补全** | ✅ **2026-06-29 (tag: v2.3.0)** | 修 link-mode 4 bug / 备份 UI type / ops-toolkit 容器 / 真机集成测试 / 容器解耦蓝图 / vitest BLOCKED | [archive/2026-07-01-v2.3-roadmap](openspec/changes/archive/2026-07-01-v2.3-roadmap/) + 6 archived changes |
| **v2.3.1 真机回归 patch** | ✅ **2026-07-01 (tag: v2.3.1)** | 修 v2.3.0 漏测：Loopback/Vsi IP 配 / 备份轮转 7→5 份 / 集成测试选口加固 | [RELEASE-NOTES-v2.3.1.md](RELEASE-NOTES-v2.3.1.md) · 3 archived changes |
| **v2.4.0 优化 + 工程化加固** | ✅ **2026-07-02 (tag: v2.4.0)** | 修 v2.3.0 漏测接口显示 / status 映射 / link-mode 双向 / 异步备份 / ops-toolkit UX / 容器清理 / 3 容器蓝图定稿 | [RELEASE-NOTES-v2.4.0.md](RELEASE-NOTES-v2.4.0.md) · 4 bugfix + 2 feat + 1 roadmap |
| **v2.4.1 拆 3 容器实施** | ✅ **2026-07-03 (tag: v2.4.1)** | ctrl + config + data 3 容器拆分 + 故障注入 + 双模式共存 + cleanup 端点 + 全量异步 + split 集成测试 | [RELEASE-NOTES-v2.4.1.md](RELEASE-NOTES-v2.4.1.md) · [v241-container-split](openspec/changes/archive/2026-07-03-v241-container-split/) + [v241-supplement](openspec/changes/archive/2026-07-03-v241-supplement/) |
| **v2.4.2 QA 工程化 + 压测 + review** | ✅ **2026-07-04 (tag: v2.4.2)** | ESLint 进 qa + ops-toolkit 默认 .177 + 压测 .177 max-session + split 真机 e2e + 3 容器 review 报告 + P0 vue-tsc | [RELEASE-NOTES-v2.4.2.md](RELEASE-NOTES-v2.4.2.md) · [REVIEW-v242-3container-maturity.md](docs/REVIEW-v242-3container-maturity.md) |
| **v2.4.2.1 ops-toolkit 第 7 脚本** | ✅ **2026-07-04 (tag: v2.4.2.1)** | paramiko-batch-exec.sh 单设备 SSH 批命令（复用 backend SSHExecutor + 4 级凭据 + Fernet 密文 + JSON 输出 + 11 单元 + 3 真机） | [RELEASE-NOTES-v2.4.2.1.md](RELEASE-NOTES-v2.4.2.1.md) · [v242-paramiko-tool](openspec/changes/archive/2026-07-04-v242-paramiko-tool/) |
| **v2.5.0 P1 工程化收口** | ✅ **2026-07-05 (tag: v2.5.0)** | **split 模式为默认（BREAKING）** + internal-api 5s TTL 缓存 + vitest 30 单元 + Playwright 37 e2e + ops-toolkit 第 8/9 脚本（interface-config + task-monitor） | [RELEASE-NOTES-v2.5.0.md](RELEASE-NOTES-v2.5.0.md) · [v25-roadmap](openspec/changes/archive/2026-07-05-v25-roadmap/) |
| **v2.6.0 i18n 中英双语** | ✅ **2026-07-06 (tag: v2.6.0)** | vue-i18n v9 + 顶导「中 \| EN」切换 + localStorage 持久化 + **400+ 翻译 key（zh-CN + en-US）** + 后端 `APIResponse.error_key` schema 扩展（**BREAKING**，向后兼容） + 9 router 改造 + 26 后端单测 + 25 前端测试 | [RELEASE-NOTES-v2.6.0.md](RELEASE-NOTES-v2.6.0.md) · [v26-i18n](openspec/changes/archive/2026-07-06-v26-i18n/) · [docs/i18n-guide.md](docs/i18n-guide.md) |
| **v2.6.1 bug 修复轮次** | ✅ **2026-07-07 (tag: v2.6.1)** | 6 个子 change：资产陈旧自动降级 / 采集失败可读化 / split 密码解密修 / vite proxy 精确分发 / **备份数据完整性**（下载 404 + 启动自检 + commit refresh + expire_on_commit + dump_db 工具） / **资产备份状态同步**（offline 设备按钮 disabled + force 逃生 + `backups.forced` 审计字段） / 备份回滚 SFTP 根因定位 + 1 个 review 反思 | [**RELEASE-NOTES-v2.6.1.md**](RELEASE-NOTES-v2.6.1.md) · [REVIEW-v261-bugfix-round.md](docs/REVIEW-v261-bugfix-round.md) |
| **v2.6.2 回滚预检 + 失败 UX** | ⏳ 2026-07-08 (待 tag v2.6.2) | 1 个 change：H3C V7 S6850 回滚无反应修复（probe + 端点 422 + paramiko 详细日志 + 前端 toast + 面板失败高亮 + `device.status.restore_unsupported` 字段）+ 1 review 反思 | [RELEASE-NOTES-v2.6.2.md](RELEASE-NOTES-v2.6.2.md) · [REVIEW-v262-bugfix-round-real-device-validation.md](docs/REVIEW-v262-bugfix-round-real-device-validation.md) |
| **v3.0 VPC 骨架** | ✅ **2026-07-18 (tag: v3.0.0)** | SDN 业务下发通道（按 device.platform 路由）+ 双套 payload 模板（5 unit × 4 字段）+ 跨平台 .5/.26 真机验证 + 73 SDN 单测 + 42 commits push。**v3.0 PRD 7 个子能力按规划拆到 v3.1.1 / v3.2 / v3.3 / v3.4**（详见 [PRD-V3.0.md](PRD-V3.0.md) 补充说明）| [**RELEASE-NOTES-v3.0.0.md**](RELEASE-NOTES-v3.0.0.md) · [archive/2026-07-16-sdn-vpc-netconf-schema-xml](openspec/changes/archive/2026-07-16-sdn-vpc-netconf-schema-xml/) |
| **v3.1.0 ZTP 调研** | ✅ **2026-07-18 (tag: v3.1.0)** | H3C V7 ZTP 可行性调研 + 决策 B（精简 ZTP）+ 独立 ztp-server 容器（alpine + dnsmasq 二合一）+ autocfg.cfg 模板（T7064P15 验证通过）。**后续 v3.1.1 落地 / v3.1.2 联动纳管** | [**RELEASE-NOTES-v3.1.0.md**](RELEASE-NOTES-v3.1.0.md) · [archive/2026-07-18-v31-ztp-research](openspec/changes/archive/2026-07-18-v31-ztp-research/) |
| **v3.1.1 ZTP 落地** | ✅ **2026-07-18 (tag: v3.1.1)** | ztp-server jinja2 多平台模板 + DHCP 临时池 `.151-.190` + `ZTP_MGMT_IP` static OOB 写入 + `.177/.26` 真机完整 ZTP 验证 + ops-toolkit reboot/capture 加固 | [**RELEASE-NOTES-v3.1.1.md**](RELEASE-NOTES-v3.1.1.md) · [archive/2026-07-18-v311-ztp-landing](openspec/changes/archive/2026-07-18-v311-ztp-landing/) |
| **v3.1.2 ZTP 联动纳管** | ✅ **2026-07-18 (tag: v3.1.2)** | ztp-server watcher 确认 static 管理地址 SSH 22 + NETCONF 830 上线后回调后端；后端幂等纳管入库、资产采集/partial 降级、Devices/CMDB/Dashboard 现有接口可见 | [**RELEASE-NOTES-v3.1.2.md**](RELEASE-NOTES-v3.1.2.md) · [archive/2026-07-18-v312-ztp-onboard-and-asset-sync](openspec/changes/archive/2026-07-18-v312-ztp-onboard-and-asset-sync/) |
| **v3.1.3 ZTP 恢复上线** | ✅ **2026-07-18 (tag: v3.1.3)** | 运营管理新增 ZTP 恢复页面；后端写入一次性 recovery override；ztp-server 运行时重渲染 autocfg.cfg；OOB 口补齐 `mgt` VRF；备份回滚 future 标记移除 | [**RELEASE-NOTES-v3.1.3.md**](RELEASE-NOTES-v3.1.3.md) · [archive/2026-07-18-v313-ztp-recovery-override](openspec/changes/archive/2026-07-18-v313-ztp-recovery-override/) |
| **v3.2 平台迁移待办** | 🧊 **2026-07-19 (暂缓)** | 新平台迁移与能力评级转为未来待办：HCL/177 无法升级官方 S6850 镜像，EVE/V9850 二层广播行为不可信；当前不阻塞 VPC/SDN 后续推进 | [PRD-V3.2.md](PRD-V3.2.md) |
| **v3.3.0 VPC/EVPN 配置闭环** | ✅ **2026-07-19 (tag: v3.3.0)** | VPC 按 Leaf 下发/撤回、端口绑定/解绑、网关局部撤回/加回、已有 VPC 接入口扩容、display 状态手动同步 + 600s 缓存；`.5` 真机完成本地下联与 EVPN Type-2/Type-3 验证 | [**RELEASE-NOTES-v3.3.0.md**](RELEASE-NOTES-v3.3.0.md) · [PRD-V3.3.md](PRD-V3.3.md) |
| **v3.4.0 SDN/VPC 工作台** | ✅ **2026-09-06 (tag: v3.4.0)** | 前端运营管理新增 SDN/VPC 工作台：VPC 清单/详情、当前 VPC 设备落地、创建 VPC、接入口扩容、deployment/validation 展示、最佳实践；SDN 目标准入改为显式 `sdn_role=evpn_leaf` | [**RELEASE-NOTES-v3.4.0.md**](RELEASE-NOTES-v3.4.0.md) · [PRD-V3.4.md](PRD-V3.4.md) |

详细进度、约束、决策记录见 [VERSION-ROADMAP.md](VERSION-ROADMAP.md)。
已归档 change 见 [openspec/changes/archive/](openspec/changes/archive/)。
主规格沉淀见 [openspec/specs/](openspec/specs/)。
V3.0 产品蓝图见 [PRD-V3.0.md](PRD-V3.0.md)，当前 VPC/EVPN 后端闭环见 [PRD-V3.3.md](PRD-V3.3.md)，前端工作台见 [PRD-V3.4.md](PRD-V3.4.md)。

## 当前架构（v3.4）

> 详见 [VERSION-ROADMAP.md](VERSION-ROADMAP.md)。v3.4 在 v3.3 VPC/EVPN 后端闭环上，补齐用户可操作的 SDN/VPC 工作台：创建 VPC、选择 EVPN Leaf、生成下发/撤回变更单、接入口扩容、查看 deployment/validation 状态。当前继续接受 **NETCONF/XML + CLI over SSH 混合下发**，不再等待 v3.2 平台迁移。

| 容器 | 职责 | 实施 | 状态 |
|---|---|---|---|
| **ctrl** | 设备身份中心（CMDB / 资产 / 设备 CRUD） | v2.4.1 实施 | ✅ 默认 split 模式 |
| **config** | 设备配置（NETCONF 配置下发 / 接口 / VLAN / VPN） + 逻辑拓扑 | v2.4.1 实施 | ✅ 默认 split 模式 |
| **data** | 采集 / 存储 / 聚合（备份 / 操作日志 / 资产采集） | v2.4.1 实施 | ✅ 默认 split 模式 |
| **backend (monolith)** | ctrl + config + data 合并 | v2.4.1 双模式共存 | ✅ 兼容老调用，profile: core |
| **qa-backend / qa-frontend** | pytest / lint / build / vitest / playwright | v2.4.2 加 lint+build 必跑 / v2.5 加 vitest+playwright 必跑 | ✅ Archive 必跑 |
| **ops-toolkit** | **7 个排错脚本**（check-host / check-netconf / capture-config / reboot-wait / paramiko-batch-exec / **interface-config** / **task-monitor**） | v2.4.1 + v2.4.2.1 + v2.5.0 + v3.1.1 reboot/capture 加固 | ✅ 按需启动 |
| **sdn (v3.4)** | VPC/EVPN 编排 + 前端工作台：租户/VPC/端口绑定/deployment/validation；显式 `sdn_role=evpn_leaf` 准入；按平台路由下发；支持局部撤回与补回 | v3.0.0 骨架 + v3.3 生命周期闭环 + v3.4 前端工作台 | ✅ 后端 `.5` 真机验证；前端 SDN/VPC 工作台 QA + 浏览器验证通过；远端同 VNI 互通等待环境补齐后验证 |
| **ztp-server (v3.1.3)** | DHCP + TFTP + autocfg.cfg 渲染 + static 管理地址上线确认回调 + recovery override | v3.1.0 基建 + v3.1.1 落地 + v3.1.2 联动纳管 + v3.1.3 恢复上线 | ✅ `.177` LSTN 与 `.26` RSTN 完整 ZTP 通过；支持前端临时指定已有设备 OOB 地址恢复上线 |
| **monitor (未来)** | 实时指标 / 告警 / dashboard | 远期 | ⏳ v3.0+ 评估 |

## v2.6.2 增量能力

- **回滚预检链路**（fix-backup-restore-support）：
  - 后端 `BackupManager.check_restore_support()` probe（H3C V7 S6850 默认禁 SCP subsystem → 推 1 字节 dummy 立即失败）
  - `POST /api/devices/{id}/backup/{bid}/restore-async` 启动前 probe → 不支持直接 422 + `error_key=backup.restore_not_supported`
  - `_restore_via_scp` 失败日志含 device_model / host / backup_id / error_type / error_message（v2.6.1 复盘"无反应"调试困难问题修复）
- **失败任务 UX**（fix-backup-restore-support Task 4-5）：
  - 全局 toast 系统（taskStore 检测 `pending/running → failed` 跃迁自动弹）
  - `BackgroundTaskPanel` 失败高亮（折叠态红点 + 头部 failed chip + ring 描边）
- **设备状态字段**（fix-backup-restore-support Task 6）：
  - `device.status.restore_unsupported: Optional[bool]` 5s TTL 缓存
  - 前端可基于此字段禁用"回滚"按钮 + 显示提示

## v3.0 增量能力（sdn-vpc-netconf-schema-xml change 已闭环）

- **业务下发通道按 device.platform 路由**（最终定稿，2026-07-15 推翻 T1.13f 决策）：
  - L3vpn/VRF/RD/RT → schema 化 NETCONF XML（所有 H3C V7 设备）
  - L2vpn/VSI/VXLAN/EVPN → **按 device.platform 路由**：
    - LSTN 老平台（.5/.177 S6850）→ **SSH 22 + paramiko 跑 system-view CLI**（T1.13g 推翻 CLI-over-NETCONF，因 ncclient 同步 reply 不可靠）
    - RSTN 新平台（.26 V9850）→ schema 化 NETCONF XML
  - SSH 22 CLI → fallback
  - RESTful / gRPC / Ansible → 不投入（.5 设备业务 API 缺失，gRPC 平台无 enable）
- **双套 payload 模板架构**（5 unit × 4 字段）：
  - `cli_commands`（LSTN 通道） + `xml_payloads`（RSTN 通道） + `undo_cli` + `undo_xml`
  - `vpc_create` 5 unit: VSI-L2 / EVPN / L3VPN / VSI-L3 / Global
  - `port_bind` 1 unit: service-instance + xconnect vsi（含 `encapsulation default` 跨平台兼容）
- **A 方案修复**（T8, 2026-07-16）：
  - RD 唯一性：1:{vni} 避免 VPC 间 RD 冲突
  - `vsi-l3` unit 用 `quit` 不用 `return`（避免退出 system-view 后续命令 Unrecognized）
  - MAC 地址用 H-H-H 格式（设备内部归一化）
  - SSH error_indicators 增强：识别 "The RD is used by another EVPN instance."（不带 `%` 前缀的业务级错误）
  - 内部 API platform 字段透传
- **跨平台真机验证**（.5 LSTN/SSH + .26 RSTN/NETCONF, 2026-07-16）：
  - vpc0001 业务命令 union 一致（vsi / vxlan 20000 / evpn encapsulation vxlan / RD 1:20000）
  - port_bind service-instance 1001 业务命令 union 一致（GE1/0/4 + HGE1/0/8）
  - **配置面 100% 一致**（数据面 .26 受限暂不验证，符合 user 指示"只管配置面"）
- **数据模型扩展**：
  - `Device.platform: Optional[str]` 字段（alembic 009 迁移幂等）
  - `SdnDeployment.unit: str` + `parent_deployment_id: Optional[int]` 字段（alembic 008 迁移幂等）
  - 73 SDN 单测全过 / 全量 432 PASS / 3 pre-existing FAIL（与本 change 无关）
- **42 commits 已 push**（origin/main e5b2e61..5690d60，含 T0-T9 全部 task）

## v3.3 增量能力（VPC/EVPN 配置闭环）

- **VPC 级编排入口**：
  - 支持按用户选择的 Leaf 设备下发或撤回 VPC；
  - 未显式选择设备时，后端按 Leaf 候选选择目标设备；
  - deployment 记录保留 unit、设备、状态、错误信息，用于审计和排障。
- **细粒度动作**：
  - 端口绑定 / 端口解绑；
  - 单设备 VPC 撤回 / 补回；
  - 单设备三层网关撤回 / 加回；
  - 已有 VPC 接入口扩容，支持填写期望主机 IP 并在完成时由网关发起 ping 校验。
- **状态采集闭环**：
  - `POST /api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/sync` 手动同步 display 状态；
  - `GET /api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/latest` 读取最近快照；
  - 默认 600 秒缓存，避免频繁 SSH 打设备。
- **真机验证结果**：
  - `.5 / Leaf-04 / 192.168.100.5` 已验证本地 Vsi-interface、VSI、AC、ARP、MAC、Type-2、Type-3 链路；
  - `192.168.2.254 -> 192.168.2.2` 网关源地址 ping 5/5 成功；
  - `GigabitEthernet1/0/3 + 192.168.1.3` 扩容演示配置当前保留，用于后续前端联调；
  - 远端同 VNI 主机互通暂受实验环境限制，不作为 v3.3 当前收口阻塞项。

## 功能概览

| 模块 | 说明 |
|------|------|
| 仪表盘 | 设备统计、最近操作、最近告警 |
| 设备管理 | 多设备 CRUD、连接测试、密码加密存储 |
| VLAN 管理 | 通过 NETCONF 协议增删改查 VLAN |
| 网络运维 | 命令派发式终端（SSH 执行，返回输出，支持多命令） |
| 接口管理 | 接口列表查看、Access/Trunk 联动配置下发、trunk 允许 VLAN 列表显式拒绝、L2/L3 link type 调整、L3 接口配 IPv4 address |
| CMDB | 设备资产台账、硬件信息自动采集（SSH）、位置/标签/状态手动编辑、单设备采集 |
| 批量操作 | 多设备勾选、批量执行命令、结果汇总 |
| 操作日志 | 全操作自动记录、按类型/状态筛选 |
| **备份 / 回滚**（v2.2 新增 / **v2.6.1 增强**） | **3 个入口**（全局 Backup 页 / 设备行 / CMDB 顶部）+ **1 个 Modal**，拉取 startup.cfg + running-config（SCP + SSH CLI），回滚（全文本 + SCP 文件级替换 + reboot + verify），每设备保留最新 5 份非锁定备份，**离线/未采集设备备份按钮 disabled + force 逃生 + `backups.forced` 审计字段** |
| **ZTP 上线 / 恢复**（v3.1） | ztp-server 提供 DHCP + TFTP + autocfg.cfg 渲染；新设备上线后自动回调后端纳管；恢复模式支持一次性指定已有设备 OOB 地址，帮助清空配置后的设备重新接入平台 |
| **SDN / VPC**（v3.0 / **v3.4 增强**） | VPC/EVPN 混合通道下发（LSTN→SSH CLI，RSTN→NETCONF XML）；支持 VPC 下发/撤回、端口绑定/解绑、网关局部撤回/补回、扩容完成校验、display 快照；运营管理提供 SDN/VPC 工作台与最佳实践引导 |

## 快速启动

> **v2.5 BREAKING**：默认模式从 monolith 翻转为 3 容器 split。
> 如需 monolith，用 `docker compose -f docker-compose.dev.yml --profile core up -d`。

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 ENCRYPTION_KEY（生成命令见 .env.example 注释）

# 2. 启动服务（默认 3 容器 split 模式：ctrl / config / data）
docker compose -f docker-compose.dev.yml up -d
# 如需 monolith 模式（仅起 backend + frontend，不起 split 3 容器）：
docker compose -f docker-compose.dev.yml --profile core up -d backend frontend

# 3. 访问
# 前端：http://localhost:5173
# ctrl API 文档（split 模式）：http://localhost:8001/docs
# backend API 文档（core 模式）：http://localhost:8000/docs
```

## 访问入口

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档（Swagger） | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Vue Router + Bootstrap 5 + **vue-i18n v9**（v2.6 i18n 切换）+ Pinia |
| 后端 | FastAPI + SQLAlchemy + ncclient + paramiko |
| 数据库 | SQLite + Alembic 迁移管理 |
| 加密 | Fernet 对称加密（密码存储） |
| 部署 | Docker Compose（开发环境热重载） |
| CI | GitHub Actions（推送自动测试+构建验证） |

## 项目结构

```
h3c-netctrl/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── models.py            # ORM 模型（Device/Log/Asset）
│   │   ├── schemas.py           # Pydantic 模型
│   │   ├── database.py          # SQLAlchemy 引擎
│   │   ├── config.py            # 配置管理
│   │   ├── routers/
│   │   │   ├── device.py        # 设备 CRUD
│   │   │   ├── vlan.py          # VLAN 管理（NETCONF）
│   │   │   ├── log.py           # 操作日志
│   │   │   ├── dashboard.py     # 仪表盘数据
│   │   │   ├── asset.py         # CMDB 资产管理
│   │   │   ├── execute.py       # 命令执行
│   │   │   ├── batch.py         # 批量操作
│   │   │   ├── interface.py     # 接口管理
│   │   │   ├── sdn.py           # SDN/VPC 编排 API
│   │   │   └── ztp.py           # ZTP 上线/恢复 API
│   │   ├── services/
│   │   │   ├── sdn_validation_collector.py # VPC display 状态采集
│   │   │   └── templates/       # H3C V7 SDN 配置模板
│   │   └── utils/
│   │       ├── crypto.py        # Fernet 加密
│   │       ├── logger.py        # 日志系统
│   │       ├── log_recorder.py  # 操作日志记录
│   │       ├── netconf_client.py# NETCONF 连接管理
│   │       └── ssh_executor.py  # SSH 命令执行器
│   ├── migrations/              # Alembic 迁移脚本
│   ├── tests/                   # 测试套件
│   └── Dockerfile.dev
├── frontend/
│   ├── src/
│   │   ├── views/               # 页面组件
│   │   ├── components/          # 公共组件（SideBar）
│   │   ├── api/                 # API 调用封装
│   │   └── router/              # 路由配置
│   └── Dockerfile.dev
├── openspec/                    # OpenSpec 变更管理
├── docs/                        # 文档
├── PRD-V2.0.md                  # V2.0 产品需求文档
├── PRD-V3.0.md                  # V3.0 VPC/SDN 产品需求文档
├── PRD-V3.2.md                  # V3.2 平台迁移待办
├── PRD-V3.3.md                  # V3.3 VPC/EVPN 配置闭环
└── docker-compose.dev.yml
```

## API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/dashboard | 仪表盘数据 |
| GET | /api/devices | 设备列表 |
| POST | /api/devices | 创建设备 |
| GET | /api/devices/{id} | 设备详情 |
| PUT | /api/devices/{id} | 更新设备 |
| DELETE | /api/devices/{id} | 删除设备 |
| POST | /api/devices/{id}/test-connection | 连接测试 |
| GET | /api/devices/{id}/vlans | VLAN 列表 |
| POST | /api/devices/{id}/vlans | 创建 VLAN |
| DELETE | /api/devices/{id}/vlans/{vlan_id} | 删除 VLAN |
| GET | /api/devices/{id}/asset | 资产信息 |
| PUT | /api/devices/{id}/asset | 更新资产 |
| POST | /api/devices/{id}/asset/refresh | 刷新硬件信息 |
| POST | /api/devices/{id}/execute | 执行命令 |
| GET | /api/devices/{id}/interfaces | 接口列表 |
| PUT | /api/devices/{id}/interfaces/{name}/config | 接口配置 |
| POST | /api/batch/execute | 批量执行命令 |
| GET | /api/logs | 操作日志 |
| POST | /api/sdn/vpcs/{vpc_id}/deploy | VPC 下发到 Leaf |
| POST | /api/sdn/vpcs/{vpc_id}/withdraw | VPC 从 Leaf 撤回 |
| POST | /api/sdn/vpcs/{vpc_id}/devices/{device_id}/gateway/withdraw | 撤回单设备 VPC 三层网关 |
| POST | /api/sdn/vpcs/{vpc_id}/devices/{device_id}/gateway/restore | 加回单设备 VPC 三层网关 |
| POST | /api/sdn/vpcs/{vpc_id}/expansions | 已有 VPC 接入口扩容 |
| POST | /api/sdn/vpcs/{vpc_id}/expansions/{binding_id}/complete | 扩容完成校验 |
| POST | /api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/sync | 手动同步 VPC display 状态 |
| GET | /api/sdn/vpcs/{vpc_id}/devices/{device_id}/validation/latest | 读取最近 VPC display 快照 |

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| ENCRYPTION_KEY | 是 | - | Fernet 加密密钥 |
| DB_PATH | 否 | ./data/dev.db | SQLite 数据库路径 |
| LOG_LEVEL | 否 | INFO | 日志级别（INFO/DEBUG） |
| BACKEND_PORT | 否 | 8000 | 后端服务端口 |
| ZTP_MGMT_IP | 否 | - | ZTP 模板渲染时指定 static OOB 管理地址 |

## 运维排查工具（ops-toolkit）

v2.3 起提供独立运维容器，**按需启动**，不依赖后端：

```bash
# 构建镜像
docker compose -f docker-compose.dev.yml --profile ops build ops-toolkit

# 主机连通性检查（ping + SSH 22 + NETCONF 830）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-host.sh 192.168.100.4

# NETCONF 连接测试（ncclient hello + 能力集）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-netconf.sh 192.168.100.4 admin password

# 快速拉取 startup.cfg
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/capture-config.sh 192.168.100.4 admin password

# 触发 reboot + 等待 SSH 恢复（最多 120s）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/reboot-wait.sh 192.168.100.4 admin password

# 单设备 SSH 批命令（v2.4.2.1，复用 backend SSHExecutor，H3C 兼容）
#   凭据默认读 .env 注入的 DEVICE_USERNAME/DEVICE_PASSWORD，不用每次 -e 传
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --command "display version"
```

预装工具：ping / nc / sshpass / ncclient / netmiko / paramiko。
**7 个预制脚本**：check-host / check-netconf / capture-config / reboot-wait / paramiko-batch-exec / **interface-config（v2.5.0 新增）** / **task-monitor（v2.5.0 新增）**。详细用法见 [docs/ops-toolkit.md](docs/ops-toolkit.md)。

## QA

每个版本发版前必跑（v2.5 起新增 vitest 组件测试 + Playwright e2e，必跑）：

```bash
# 后端 QA（unit + smoke + bugfix regression + xml builder，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-backend

# 前端 QA（lint → build → vitest → playwright，秒级~分钟级）
#   v2.5 起 vitest 33 case（5 核心组件 × 6 case + 3 smoke）+ playwright 37 e2e 自动跑
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend

# 真机集成（按需，分钟级，需 SSH 通设备）
docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend
```

**测试统计（v2.5.0 baseline）**：
- qa-backend 单元测试：**233 passed**（225 baseline + 8 internal-api-cache）
- qa-frontend vitest：**33 case**（5 核心组件 × 6 case + 3 smoke）
- qa-frontend Playwright：**37 e2e case**（8 场景覆盖核心用户流程）
- 真机集成：默认 skip（不阻塞），需 `.177` 设备可达时显式跑

详细 SOP 见 [docs/QA-GUIDE.md](docs/QA-GUIDE.md)。

## 版本历史

| 版本 | 主要功能 | 发版说明 |
|------|---------|---------|
| V1.0 | 设备管理、VLAN CRUD、NETCONF 交互、操作日志 | - |
| V1.1 | Vue 3 前端重构、多设备管理、日志查看页面 | ⚠️ 弃用，被 v2.1 替代 |
| V2.0 | 侧边栏导航、Dashboard、运维终端、接口管理、CMDB、批量操作、Alembic 迁移、GitHub Actions CI | - |
| V2.1 | 多命令终端、设备 CRUD UI、资产编辑、单设备采集、状态判定修复 | - |
| V2.2.0 | **备份前端（3 入口 + 1 Modal）、接口 VPN 联动 + L2/L3 + link type + IP 编辑能力、4 收尾 bug fix** | [**RELEASE-NOTES-v2.2.0.md**](RELEASE-NOTES-v2.2.0.md) |
| V2.5.0 | **split 模式为默认（BREAKING）+ internal-api 5s TTL 缓存 + vitest 30 单元 + Playwright 37 e2e + ops-toolkit 第 8/9 脚本（interface-config + task-monitor）** | [**RELEASE-NOTES-v2.5.0.md**](RELEASE-NOTES-v2.5.0.md) |
| V2.6.0 | **vue-i18n v9 + 顶导「中 \| EN」切换 + 400+ 翻译 key（zh-CN + en-US）+ 后端 `APIResponse.error_key` BREAKING schema 扩展 + 9 router 改造** | [**RELEASE-NOTES-v2.6.0.md**](RELEASE-NOTES-v2.6.0.md) |
| V3.0.0 | **SDN/VPC 业务下发通道骨架 + LSTN/RSTN 平台路由 + 双套 payload 模板 + .5/.26 真机验证** | [**RELEASE-NOTES-v3.0.0.md**](RELEASE-NOTES-v3.0.0.md) |
| V3.1.0 | **ZTP 可行性调研 + 精简 ZTP 方案 + ztp-server 容器骨架** | [**RELEASE-NOTES-v3.1.0.md**](RELEASE-NOTES-v3.1.0.md) |
| V3.1.1 | **ZTP 多平台模板 + DHCP/TFTP 落地 + `.177/.26` 真机验证 + ops-toolkit reboot/capture 加固** | [**RELEASE-NOTES-v3.1.1.md**](RELEASE-NOTES-v3.1.1.md) |
| V3.1.2 | **ZTP static 管理地址上线确认 + 后端幂等纳管 + 资产采集 partial 降级** | [**RELEASE-NOTES-v3.1.2.md**](RELEASE-NOTES-v3.1.2.md) |
| V3.1.3 | **ZTP 恢复上线页面 + recovery override + OOB mgt VRF 标准配置** | [**RELEASE-NOTES-v3.1.3.md**](RELEASE-NOTES-v3.1.3.md) |
| V3.2 | **平台迁移待办暂缓：沉淀 HCL/EVE/镜像升级限制与未来迁移方向** | [PRD-V3.2.md](PRD-V3.2.md) |
| V3.3.0 | **VPC/EVPN 后端配置闭环：下发/撤回、绑定/解绑、网关局部操作、扩容校验、display 快照** | [**RELEASE-NOTES-v3.3.0.md**](RELEASE-NOTES-v3.3.0.md) |
