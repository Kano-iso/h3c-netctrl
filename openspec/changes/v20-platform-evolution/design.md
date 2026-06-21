## Context

V1.x 已完成设备管理、VLAN CRUD、操作日志、Vue 3 前端框架。当前状态：
- 后端：FastAPI + ncclient + paramiko，SQLite 数据库，7 个 API 端点
- 前端：Vue 3 + Vite + Vue Router，3 个页面（设备列表、设备详情、日志）
- 部署：Docker Compose 双容器（后端 320MB + 前端 Vite dev server）
- 数据库：devices 表 + logs 表，无迁移管理（create_all 自动建表）

V2.0 要在此基础上扩展 6 个新能力模块，同时保持 NETCONF XML 交互层不变。

## Goals / Non-Goals

**Goals:**
- 命令派发式运维终端（非交互式）
- 接口列表查看 + Access/Trunk 联动配置
- CMDB 资产台账 + 硬件信息自动采集
- 多设备批量命令执行 + 结果汇总
- 前端从功能页面演进为平台级体验（侧边栏 + Dashboard + 视觉升级）
- Alembic 数据库迁移管理
- GitHub Actions 基础 CI 保障

**Non-Goals:**
- 真正交互式终端（xterm.js + WebSocket）
- 配置备份/对比/回滚
- 拓扑发现/可视化
- AI 辅助
- 用户认证/权限
- EVPN/VXLAN/路由配置
- CI/CD 自动部署/镜像仓库

## Decisions

### D1: 命令执行方式——paramiko SSH exec_command

**选择**：命令派发式，通过 paramiko SSH 连接执行命令，返回文本输出。

**理由**：
- 项目已有 paramiko 依赖（NETCONF 连接用），无需新增依赖
- 每次请求独立执行，无状态管理，简单可靠
- 不需要 WebSocket，前端用普通 HTTP 请求即可

**替代方案**：
- xterm.js + WebSocket + paramiko channel：体验好但工作量大（3-5天），中文输入/特殊按键/分页输出都是坑
- NETCONF rpc 命令：H3C 不支持标准 `<rpc>` 执行任意命令

### D2: 接口信息获取——SSH 命令优先，NETCONF 辅助

**选择**：先用 SSH `display interface brief` 命令获取接口列表和状态，接口配置下发用 NETCONF edit-config。

**理由**：
- H3C 接口的 NETCONF XML 结构未知，需要实际探测（和 VLAN 一样会踩坑）
- SSH 命令输出格式稳定，解析简单
- 配置下发仍用 NETCONF（原子性、可回滚）
- 后续可逐步 NETCONF 化接口查询

### D3: CMDB 硬件信息采集——SSH 命令组合

**选择**：通过 SSH 执行多条命令采集硬件信息：
- `display device` → 型号、SN
- `display version` → 固件版本
- `display cpu-usage` / `display memory` → CPU/内存

**理由**：
- NETCONF 获取硬件信息的 XML 结构不确定
- SSH 命令输出更直观，解析更可控
- 一键刷新 = 并行执行多条命令 + 解析 + 写入 assets 表

### D4: 数据库迁移——引入 Alembic

**选择**：引入 Alembic 管理数据库迁移，从现有表结构生成初始 migration。

**理由**：
- V2.0 新增 assets 表，后续还可能有更多表
- `create_all` 无法处理表结构变更（加列、改类型）
- Alembic 是 SQLAlchemy 生态标准，切换到 PostgreSQL 只需改连接字符串

### D5: 前端导航——侧边栏替代顶部导航

**选择**：左侧固定侧边栏导航，包含：仪表盘、设备管理、网络运维、接口管理、CMDB、操作日志。

**理由**：
- 页面数量从 3 个增加到 7+，顶部导航放不下
- 侧边栏是运维平台的标准布局（Grafana/Zabbix/Ansible AWX 都是侧边栏）
- 支持分组和图标，信息层次更清晰

### D6: Dashboard 数据——轻量聚合查询

**选择**：Dashboard 展示设备总数/在线/离线、最近操作日志、最近失败操作，数据从现有 API 聚合。

**理由**：
- 不需要新的数据源，现有 devices 表和 logs 表即可
- 一个新的 API 端点 `/api/dashboard` 返回聚合数据
- 轻量实现，不做图表库引入（保持项目简洁）

### D7: GitHub Actions CI——阶段1 仅测试+构建验证

**选择**：仅配置推送后自动跑后端测试 + 前端构建验证，不做镜像推送和自动部署。

**理由**：
- 项目体量小，不需要镜像仓库
- 国内网络访问 Docker Hub/GHCR 不稳定
- 核心价值是"推送后自动验证代码没坏"，不是自动部署

## Risks / Trade-offs

| 风险 | 影响 | 应对 |
|------|------|------|
| H3C 接口 NETCONF XML 结构未知 | 接口查询可能踩坑 | 先用 SSH 命令，后续 NETCONF 化 |
| Trunk/Access 联动配置需多条命令原子下发 | 部分成功部分失败导致配置不一致 | 用 NETCONF edit-config 单次下发，失败自动不生效 |
| SSH 命令输出解析依赖设备型号 | 不同型号输出格式可能不同 | 优先适配当前 HCL 模拟器，后续按需扩展 |
| Alembic 首次引入 | 需要从现有表生成初始 migration | 先 `alembic stamp head` 标记当前状态，再生成新 migration |
| 前端页面数量翻倍 | 开发和测试工作量增加 | 按优先级逐步实现，每个页面独立可测 |
