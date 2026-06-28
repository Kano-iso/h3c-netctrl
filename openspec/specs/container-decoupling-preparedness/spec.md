# container-decoupling-preparedness Specification

## Purpose
TBD - created by archiving change container-decoupling. Update Purpose after archive.
## Requirements
### Requirement: 未来 4 容器职责划分蓝图

`docs/CONTAINER-DECOUPLING.md` MUST 文档化 4 个未来容器的职责划分：

| 容器 | 职责 | 资源特征 | 数据库 |
|---|---|---|---|
| **core** | NETCONF 配置下发 / 运维终端 / 操作日志 / 设备 CRUD | 高频 NETCONF，CPU 中 | 写 device / log / interface_config |
| **asset** | cmdb / 备份 / 资产采集 / 统一数据库 | 低频批处理，I/O 重 | 统一 Postgres（device / asset / backup） |
| **sdn** (v3.0) | VPC + 控制器对接 + etcd 协调 | 高频控制面 | 读 device / asset |
| **monitor** (未来) | 实时指标采集 / 告警 / dashboard | 高频 polling | 写 metric / alert |

#### Scenario: 文档存在性
- **WHEN** 团队成员查看 `docs/CONTAINER-DECOUPLING.md`
- **THEN** MUST 看到 4 个未来容器的职责 + 资源特征 + 数据库归属

### Requirement: SERVICE_NAME env 注入

`backend/app/main.py` MUST 读取 `SERVICE_NAME` 环境变量（默认 `"core"`），并在启动日志中打印 `service_name={value}`。

#### Scenario: 默认启动
- **WHEN** 未设置 `SERVICE_NAME` env
- **THEN** 后端 MUST log `service_name=core`，业务行为不变

#### Scenario: 自定义值
- **WHEN** 设置 `SERVICE_NAME=asset`
- **THEN** 后端 MUST log `service_name=asset`，**业务行为仍不变**（准备开关，本次未使用 router 分组）

### Requirement: docker-compose 蓝图注释

`docker-compose.dev.yml` MUST 在当前 `backend` 服务上方加注释块，列出 4 个未来服务名 + 职责（不实际新增 service，仅注释）。

#### Scenario: 查看 docker-compose
- **WHEN** 团队成员打开 `docker-compose.dev.yml`
- **THEN** MUST 看到注释明确标注"当前 monolith，未来拆 core/asset/sdn/monitor 4 容器"

### Requirement: Router 注释分组

`backend/app/routers/__init__.py` MUST 在顶部加注释表格，标注每个 router 未来归属（core / asset / sdn / monitor），**不实际移动文件**。

#### Scenario: 路由归属可读
- **WHEN** 团队成员查看 `routers/__init__.py`
- **THEN** MUST 看到每个 router 注释 `# future: core | asset | sdn | monitor`

### Requirement: README 未来架构章节

`README.md` MUST 新增"未来架构"章节，包含 4 容器职责简图。

#### Scenario: README 完整
- **WHEN** 查看 `README.md`
- **THEN** MUST 在"版本状态"之后看到"未来架构"小节，描述 core/asset/sdn/monitor 4 个未来容器

### Requirement: 实施标记

`docs/CONTAINER-DECOUPLING.md` MUST 明确标注"本次 change 仅做预留，未实际拆容器"，并指向 v2.3 拆 asset 的入口。

#### Scenario: 防止误读
- **WHEN** 团队成员阅读蓝图
- **THEN** MUST 看到 "本次 change 仅做预留" + 实施时序（v2.3 / v3.0 / 未来）

