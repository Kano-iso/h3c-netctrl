# 未来容器解耦蓝图

**状态**：预留（v2.1.x patch，未实际拆容器）
**关联 change**: `openspec/changes/container-decoupling/`
**实施时序**: v2.3 拆 asset / v3.0 加 sdn / 未来 monitor

---

## 背景

当前后端是单一 FastAPI 进程（uvicorn 1 worker），11 个 router 加载到同一进程：
- 高频 NETCONF（vlan / interface / device）
- 同步 SSH（execute）
- I/O 重（备份 v2.2 引入）
- 批处理（asset / dashboard / batch）

随着 v2.2 备份模块 + v3.0 SDN 上线，**单容器架构将不适用**：
- 资源争抢：NETCONF 同步 vs 备份 I/O 相互阻塞
- 故障域过大：一个 router 崩整个后端挂
- 数据库归属不明：拆分时数据迁移路径不清晰

## 4 个未来容器职责

| 容器 | 职责 | 资源特征 | 数据库 | 实施时序 |
|---|---|---|---|---|
| **core** | NETCONF 配置下发 / 运维终端 / 操作日志 / 设备 CRUD | 高频 NETCONF，CPU 中 | 写 device / log / interface_config | 当前 monolith |
| **asset** | cmdb / 备份 / 资产采集 / **统一数据库** | 低频批处理，I/O 重 | **统一 Postgres**（device / asset / backup） | v2.3 拆分 |
| **sdn** (v3.0) | VPC + 控制器对接 + etcd 协调 | 高频控制面 | 读 device / asset | v3.0 引入 |
| **monitor** (未来) | 实时指标采集 / 告警 / dashboard | 高频 polling | 写 metric / alert | 未来 |

## 数据库归属：asset 容器

统一 Postgres 实例**部署在 asset 容器**，core / sdn / monitor 远程连接。

**理由**：
- asset 任务最少，最稳定
- 避免每个容器都跑一份 DB（运维噩梦）
- 设备元数据 / 资产 / 备份 强一致性，单一 DB 简化事务

**未来风险**：
- 跨服务事务复杂 → 拆分时用"事件驱动 + 最终一致性"代替强事务
- 数据库单点 → v2.3 实施前重新评估主从 / 读写分离

## Router 归属（拆分参考）

| router | 当前 | 未来归属 |
|---|---|---|
| `device.py` | core | core |
| `vlan.py` | core | core |
| `interface.py` | core | core |
| `execute.py` | core | core |
| `log.py` | core | core |
| `auth.py` | core | core |
| `health.py` | core | core |
| `dashboard.py` | core | core |
| `batch.py` | core | core |
| `asset.py` | asset | asset |
| `backup.py`（v2.2 新增） | core（monolith） | asset（v2.3 拆） |
| `sdn.py`（v3.0 新增） | — | sdn |
| `monitor.py`（未来新增） | — | monitor |

## 拆分时序

### 阶段 1（v2.3）：拆 asset 容器

最小、最容易（备份 I/O 隔离，资源特征明显）：
1. 创建 `h3c-netctrl-asset` 容器
2. 移入 `asset.py` / `backup.py` router + `BackupManager` 工具
3. Postgres 容器化（`h3c-netctrl-postgres`，独立容器）
4. core 容器远程连接 Postgres
5. 跨服务鉴权：共享 `INTERNAL_TOKEN` env

### 阶段 2（v3.0）：加 sdn 容器

- 上线 `sdn.py` + etcd 集成
- sdn 容器连接 asset 的 Postgres 读 device
- SDN 控制面与业务面物理隔离

### 阶段 3（未来）：加 monitor 容器

- 独立采集链路
- Prometheus / OpenTelemetry 集成
- 不影响业务面

## 技术挑战（拆时再处理）

| 挑战 | 当前应对 | 拆分时应对 |
|---|---|---|
| 跨服务事务 | 单一 DB 事务 | 事件驱动 + 最终一致性 |
| 跨服务鉴权 | 无（单进程） | `INTERNAL_TOKEN` 共享密钥 |
| 跨服务日志 | 文件 + DB | ELK / Loki 集中 |
| 跨服务监控 | 无 | Prometheus + Grafana |
| 数据库迁移 | 无 | 增量迁移工具（alembic + 跨容器） |

## 本次 change 范围

**仅做预留**（已 commit）：
- `backend/app/main.py` 加 `SERVICE_NAME` env 读取（默认 `core`）+ log 输出
- `backend/app/routers/__init__.py` 顶部注释分组表
- `docker-compose.dev.yml` 在 `backend` 服务上方加蓝图注释
- `docs/CONTAINER-DECOUPLING.md`（本文件）
- `README.md` 新增"未来架构"章节

**不真拆**：当前 monolith 单服务运行，行为零变化。

## 拆分实施入口

v2.3 开工前需：
1. 在 `openspec/changes/` 新建 `split-asset-container/` change
2. 更新本文件，将"阶段 1"从"实施时序"移入新 change 的 proposal.md
3. 评估本文件"数据库归属"是否仍适用
4. 提交 PR review
