# H3C NetCtrl

基于 NETCONF + SSH 的 H3C 交换机轻量网控平台。

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
| v3.0 VPC | ⏳ PRD 初稿 | VPC 能力（SDN）+ 端口随接随入 + 分布式网关状态闭环 | [PRD-V3.0.md](PRD-V3.0.md) |

详细进度、约束、决策记录见 [VERSION-ROADMAP.md](VERSION-ROADMAP.md)。
已归档 change 见 [openspec/changes/archive/](openspec/changes/archive/)。
主规格沉淀见 [openspec/specs/](openspec/specs/)。
V3.0 产品蓝图见 [PRD-V3.0.md](PRD-V3.0.md)。

## 当前架构（v2.6.2）

> 详见 [VERSION-ROADMAP.md §v2.6.2 回滚预检 + 失败 UX](VERSION-ROADMAP.md)。v2.5 split 模式为默认，v2.6.0 i18n 上线，v2.6.1 修 6 类 bug，v2.6.2 集中修回滚链路 + 提升失败任务 UX。

| 容器 | 职责 | 实施 | 状态 |
|---|---|---|---|
| **ctrl** | 设备身份中心（CMDB / 资产 / 设备 CRUD） | v2.4.1 实施 | ✅ 默认 split 模式 |
| **config** | 设备配置（NETCONF 配置下发 / 接口 / VLAN / VPN） + 逻辑拓扑 | v2.4.1 实施 | ✅ 默认 split 模式 |
| **data** | 采集 / 存储 / 聚合（备份 / 操作日志 / 资产采集） | v2.4.1 实施 | ✅ 默认 split 模式 |
| **backend (monolith)** | ctrl + config + data 合并 | v2.4.1 双模式共存 | ✅ 兼容老调用，profile: core |
| **qa-backend / qa-frontend** | pytest / lint / build / vitest / playwright | v2.4.2 加 lint+build 必跑 / v2.5 加 vitest+playwright 必跑 | ✅ Archive 必跑 |
| **ops-toolkit** | **9 个排错脚本**（check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch / paramiko-batch-exec / **interface-config** / **task-monitor**） | v2.4.1 + v2.4.2.1 + v2.5.0 + **v2.6.2 文档**（S6850 SCP 限制） | ✅ 按需启动 |
| **sdn (v3.0)** | VPC + etcd 协调 | 规划 | ⏳ v3.0 |
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
│   │   │   └── interface.py     # 接口管理
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

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| ENCRYPTION_KEY | 是 | - | Fernet 加密密钥 |
| DB_PATH | 否 | ./data/dev.db | SQLite 数据库路径 |
| LOG_LEVEL | 否 | INFO | 日志级别（INFO/DEBUG） |
| BACKEND_PORT | 否 | 8000 | 后端服务端口 |

## 运维排查工具（ops-toolkit）

v2.3 起提供独立运维容器，**按需启动**，不依赖后端：

```bash
# 构建镜像
docker compose -f docker-compose.dev.yml --profile ops build ops-toolkit

# 主机连通性检查（ping + SSH 22 + NETCONF 830）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-host.sh 192.168.100.4

# NETCONF 连接测试（ncclient hello + 能力集）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/check-netconf.sh 192.168.100.4 admin password

# SSH 交互测试（登录 + 执行命令）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit /scripts/ssh-test.sh 192.168.100.4 admin password "display version"

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
**9 个预制脚本**：check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch / paramiko-batch-exec / **interface-config（v2.5.0 新增）** / **task-monitor（v2.5.0 新增）**。详细用法见 [docs/ops-toolkit.md](docs/ops-toolkit.md)。

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
