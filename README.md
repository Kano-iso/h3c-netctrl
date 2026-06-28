# H3C NetCtrl

基于 NETCONF + SSH 的 H3C 交换机轻量网控平台。

## 版本状态

| 版本 | 状态 | 主题 | 详情 |
|---|---|---|---|
| v1.0 MVP | ✅ 2026-06-13 | 基础 CRUD + NETCONF VLAN/接口 | [archive/2026-06-13-v1-mvp-foundation](openspec/changes/archive/) |
| v2.0 平台化 | ✅ 2026-06-22 | 8 项：NETCONF 重构 / QA 测试套件 / bugfix 轮次 / Schemas v2 | [archive 目录](openspec/changes/archive/) |
| v2.1 前端重构 | ✅ 2026-06-23 | 7 项：多命令终端 / 设备 CRUD UI / 资产编辑 / 单设备采集 / 状态判定修复 | [archive 目录](openspec/changes/archive/) |
| **v2.2 网控增强** | 🚧 进行中 | 手动备份+回滚 / 接口 VPN 能力 / 容器解耦预留 | 本次会话目标 |
| v3.0 VPC | ⏳ 规划 | VPC 能力（SDN） | 延后 |

详细进度与归档 change 见 [openspec/changes/archive/](openspec/changes/archive/)。
主规格沉淀见 [openspec/specs/](openspec/specs/)。

## 未来架构

详见 [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)（v2.1.x patch 已预留蓝图，未实际拆）。

| 容器 | 职责 | 实施 |
|---|---|---|
| **core** | NETCONF 配置 / 运维终端 / 设备 CRUD / 操作日志 | 当前 monolith |
| **asset** | cmdb / 备份 / 资产采集 / 统一数据库 | v2.3 拆分 |
| **sdn** (v3.0) | VPC + etcd 协调 | v3.0 引入 |
| **monitor** (未来) | 实时指标 / 告警 / dashboard | 未来 |

## 功能概览

| 模块 | 说明 |
|------|------|
| 仪表盘 | 设备统计、最近操作、最近告警 |
| 设备管理 | 多设备 CRUD、连接测试、密码加密存储 |
| VLAN 管理 | 通过 NETCONF 协议增删改查 VLAN |
| 网络运维 | 命令派发式终端（SSH 执行，返回输出，支持多命令） |
| 接口管理 | 接口列表查看、Access/Trunk 联动配置下发、trunk 允许 VLAN 列表显式拒绝 |
| CMDB | 设备资产台账、硬件信息自动采集（SSH）、位置/标签/状态手动编辑、单设备采集 |
| 批量操作 | 多设备勾选、批量执行命令、结果汇总 |
| 操作日志 | 全操作自动记录、按类型/状态筛选 |

## 快速启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 ENCRYPTION_KEY（生成命令见 .env.example 注释）

# 2. 启动服务
docker compose -f docker-compose.dev.yml up -d

# 3. 访问
# 前端：http://localhost:5173
# 后端 API 文档：http://localhost:8000/docs
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
| 前端 | Vue 3 + Vite + Vue Router + Bootstrap 5 |
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

## 版本历史

| 版本 | 主要功能 |
|------|---------|
| V1.0 | 设备管理、VLAN CRUD、NETCONF 交互、操作日志 |
| V1.1 | Vue 3 前端重构、多设备管理、日志查看页面 |
| V2.0 | 侧边栏导航、Dashboard、运维终端、接口管理、CMDB、批量操作、Alembic 迁移、GitHub Actions CI |
