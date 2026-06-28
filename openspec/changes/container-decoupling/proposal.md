## Why

当前后端是一个**大单体**（`h3c-netctrl-backend` 容器内含 11 个 router + 3 个工具类 + 3 张表 + 业务逻辑），前端是单 SPA。这种架构在 v2.1 之前规模下尚可，但 v2.2 引入备份模块、v3.0 计划上 SDN/VPC 之后，**单容器会成为瓶颈**：

- **资源争抢**：NETCONF 同步操作 vs 备份 I/O vs 监控 polling → 同一进程相互阻塞
- **故障域过大**：一个 router 崩了整个后端挂
- **不可扩展**：将来 SDN 容器（高频控制面）和资产容器（低频批处理）资源需求差异巨大
- **数据库归属不明**：当前 SQLite / Postgres 跟业务混在一起，将来拆容器时数据迁移路径不清晰

### 用户原话（v2.2 规划）

> "其实我这里说你自己考虑吧，就是我觉得就是有一部分功能该是不是需要解耦啊？我们现在的整个后端容器是整个一个大全部后端放在一个容器里，这有点怪异啊。就是我觉得将来，比如说一些sdn相关的是一个容器，然后一个资产cmdb啊，然后包括一些管一些那种。呃监控啊，这些方面是一个，就是我觉得这是两回事吧。这个到时候看一看吧，我觉得解耦一点吧，到时候全放那个放全放在一个容器里怪怪的，做的所以尽量做的微服务一些"

> "我觉得这里说的拆容器这个方面啊，就是做好预，一是做好预留啊。2呢就是呃像cmdb这种的就是我虽然说cmdb的备份啊啥都属于资产的，也就是说不要cmdb叫资产吧，就是说。嗯这么一个类似的容器吧，里面有一些这种嗯。以及你的数据库现在不就是在嗯你的数据库不就是在这个，我觉得数据库这种东西也算资产。数据库统一放在这个资产容器里也行，或者是你自己挑一个容器吧，挑一个就任务少的容器，你去挑一个这个东西，我觉得将来监控一定是个大东西吧，我觉得监控可以自己有自己有一个东西，然后。呃像这种资产我觉得它的任务少一点吧，它就可以有一个数据库把它放在那，然后那个sdn的去连它的数据库，将来那个类似于一些etcd，我觉得sdn将来需要etedcd吧这个东西我觉得也可以让他在这里保存一下。"

### 关键设计约束（user feedback）

- **本次只做"预留"**（架构骨架 + docker-compose 注释 + 服务命名空间），**不真正拆容器**
- **资产容器**：包含 cmdb + 备份 + 数据库（轻负载，统一一个 Postgres）
- **SDN 容器**：未来 v3.0 + etcd 集成
- **监控容器**：未来独立（用户预期是大模块）
- **资产容器的数据库**：也承载 SDN 容器的元数据（device / asset 表），不重复存储

## What Changes

### 本次 change 范围（仅预留，不拆）

| 改动 | 行为 |
|---|---|
| `docker-compose.dev.yml` 注释 | 加 4 个未来服务名（`asset` / `sdn` / `monitor` / `core`），明确职责 |
| `docker-compose.dev.yml` 当前 `backend` 服务 | 重命名或保留 + 加注释"当前 monolith，预留拆分点" |
| `backend/app/main.py` 加 `SERVICE_NAME = "core"` env 变量 | 未来按 SERVICE_NAME 启动时挂载不同 router 子集 |
| `backend/app/routers/__init__.py` 注释分组 | 按"core / asset / sdn / monitor"标注未来归属 |
| 新增 `docs/CONTAINER-DECOUPLING.md` | 拆分蓝图（本次写"预留"章节，"实施"章节留空指向 v3.0） |
| `README.md` 加"未来架构"小节 | 简图描述 4 个容器的职责 |

### 不做（明确）

- **不真拆** 4 个容器
- **不改**业务代码逻辑
- **不重写** 现有 router
- **不创建** 任何 v3.0 代码

## Capabilities

### New Capabilities
- `container-decoupling-preparedness`：架构预留，标记未来拆容器边界

### Modified Capabilities
- （无现有 spec 修改，仅 docker-compose + 注释）

## Impact

- **代码**：
  - 改 `docker-compose.dev.yml`（加注释，**不改容器名/端口**）
  - 改 `backend/app/main.py`（+ 1 行 env 读取 + log 打印）
  - 改 `backend/app/routers/__init__.py`（仅注释分组）
  - 新增 `docs/CONTAINER-DECOUPLING.md`（架构蓝图）
  - 改 `README.md`（+ "未来架构" 章节）
- **API 兼容性**：100% 不变
- **数据库**：无迁移
- **依赖**：无新增
- **回归**：零（仅注释 + env 读取）
- **回退**：git revert 即可
- **测试**：仅验证服务启动 + log 输出 SERVICE_NAME=core

## 4 个未来容器职责（蓝图）

| 容器 | 职责 | 资源特征 | 数据库 |
|---|---|---|---|
| **core** | NETCONF 配置下发 + 运维终端 + 操作日志 + 设备 CRUD | 高频 NETCONF，CPU 中 | 写 device / log / interface_config |
| **asset** | cmdb + 备份 + 资产采集 + 数据库统一 | 低频批处理，I/O 重（备份），轻 CPU | **统一数据库**（device / asset / backup） |
| **sdn** (v3.0) | VPC + 控制器对接 + etcd 协调 | 高频控制面 | 读 device / asset |
| **monitor** (未来) | 实时指标采集 + 告警 + dashboard | 高频 polling | 写 metric / alert |

### 拆分时序（v2.2 后）

1. v2.3 拆 `asset`（最小、最容易，备份 I/O 隔离）
2. v3.0 上 `sdn`
3. 未来 `monitor`

## Open Questions

- **数据库归属**：用户允许"资产容器承载数据库"或"挑一个任务少的容器"。本次预留中"asset"容器承载 Postgres 实例。**风险**：如果将来 core 容器需要事务，跨容器事务复杂 → **缓解**：拆分时用"事件驱动"代替强事务
- **跨容器通信**：gRPC vs HTTP/REST？**预留**：本次不决定，v2.3 时再选
- **etcd 归属**：用户说"也可以让他在这里保存一下"（指资产容器），但 SDN 容器未来要写 etcd → **预留**：本次不部署 etcd，仅在蓝图标注
