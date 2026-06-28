## Context

当前后端是单一 FastAPI 进程（uvicorn 1 worker），11 个 router 加载到同一进程。用户规划 v2.2 引入备份（I/O 重）+ v3.0 引入 SDN（控制面高频）+ 未来监控（polling 高频），**单容器架构将不适用**。

本次 change **只做"预留"**，不真正拆容器。目的是：
- 标记未来拆分边界（业务模块 → 未来容器）
- 准备 `SERVICE_NAME` env（让同一个 monolith 二进制将来能按 service 加载 router 子集）
- 写架构蓝图（`docs/CONTAINER-DECOUPLING.md`），避免未来拆容器时无文档

## Goals / Non-Goals

**Goals:**
- 4 个未来容器职责清晰（core / asset / sdn / monitor）
- 当前 router 按未来归属分组注释
- `SERVICE_NAME` env 注入 + log 输出
- 写架构蓝图（重点是"为什么这样拆"+"何时拆"）
- README 加"未来架构"章节

**Non-Goals:**
- **不真拆**容器（保持当前 `backend` 单服务）
- **不改**业务逻辑（router 行为 0 变化）
- **不部署** etcd / 第二数据库
- **不实现**跨容器通信（gRPC/HTTP 留给 v2.3）
- **不引入**新依赖

## Decisions

### 1. 拆分粒度：4 个容器

- **选择**：core / asset / sdn / monitor
- **理由**：
  - **core**：NETCONF 同步操作 + 设备 CRUD + 运维终端 + 操作日志（高频 CPU）
  - **asset**：cmdb + 备份 + 资产采集 + 统一数据库（I/O 重，低频）
  - **sdn**：v3.0 VPC + etcd 协调（控制面高频）
  - **monitor**：未来独立（用户原话"监控一定是个大东西"）
- **替代**：
  - 只拆 2 个（core + everything else）→ 粒度粗，sdn 上线时还得再拆
  - 拆 5+ 个（按 router 拆）→ 过度设计，跨服务事务复杂

### 2. 数据库归属：asset 容器

- **选择**：统一 Postgres 实例**部署在 asset 容器**，core / sdn / monitor 远程连接
- **理由**：
  - asset 任务最少，最稳定
  - 避免每个容器都跑一份 DB（运维噩梦）
  - 用户原话"我觉得资产任务少一点，它就可以有一个数据库把它放在那，然后那个sdn的去连它的数据库"
- **替代**：
  - core 容器部署 DB（高频 NETCONF 干扰 DB 性能）→ 不推荐
  - 每个容器独立 DB（device 同步爆炸）→ 复杂
  - 外部 DB 容器（postgres 独立）→ 用户没要求，且增加运维

### 3. `SERVICE_NAME` env

- **选择**：新增 `SERVICE_NAME` env，默认 `core`，`main.py` 启动时 log 打印
- **理由**：
  - 当前 monolith 一份代码将来拆容器时，可按 `SERVICE_NAME` 加载不同 router 子集
  - 不立即生效，仅做"准备开关"
  - 加 log 输出让运维一眼能识别当前实例的角色
- **替代**：
  - 直接拆 4 个 git branch → 维护噩梦
  - 用 monorepo 多服务 → 当前规模 over-engineering

### 4. docker-compose 改动：仅注释

- **选择**：在 `docker-compose.dev.yml` 当前 `backend` 服务加注释，列出 4 个未来服务名 + 职责
- **理由**：
  - 不影响当前运行（容器名/端口/mount 全不变）
  - 提供"未来扩展示例"，新成员看 compose 就懂拆分蓝图
- **替代**：
  - 直接加 4 个 `*-future` 注释服务 → 视觉污染但不影响运行；选这个方案也行

### 5. 蓝图文档：`docs/CONTAINER-DECOUPLING.md`

- **选择**：新增该文档，写：
  - 当前 monolith 痛点
  - 4 个未来容器职责 + 资源特征 + 数据库
  - 拆分时序（v2.3 拆 asset / v3.0 加 sdn / 未来 monitor）
  - 拆分时技术挑战（跨服务事务、事件驱动替代）
- **理由**：拆分是长线工作，必须有文档沉淀共识
- **替代**：
  - 写在 README → 主页太杂
  - 写在 OpenSpec proposal → change archive 后会消失
  - 不写 → 未来拆时无参考

### 6. Router 注释分组

- **选择**：`backend/app/routers/__init__.py` 不实际分组，仅顶部加注释表格（每个 router 标注未来归属 core / asset / sdn / monitor）
- **理由**：
  - 当前代码 import 结构不动（避免 11 个 import 链调整）
  - 但 reviewer 扫一眼就知道未来边界
- **替代**：
  - 物理分组（创建 `app/routers/core/` 等子包）→ 当前规模 over-engineering

## Risks / Trade-offs

- **[风险] 蓝图与未来实施脱节** → **缓解**：proposal 中明确"本次不实施"，v2.3 / v3.0 开工前必须 update proposal 重新对齐
- **[风险] 误以为本次拆了容器** → **缓解**：commit message + README 双重强调"本次仅预留，未真拆"
- **[风险] `SERVICE_NAME` env 加了但未使用** → **缓解**：log 中打印但不影响功能（"准备开关"模式）
- **[风险] 数据库"放 asset"假设未来变** → **缓解**：蓝图文档中标注为"假设 v2.3 实施前重新评估"
- **[回归] 业务代码** → **零回归**（仅注释 + 1 行 env 读取）

## Migration Plan

- **部署**：纯注释 + 1 行 env 读取，**后端容器无需重启**（uvicorn --reload 自动 HMR）
- **回退**：git revert 即可
- **数据**：零迁移
- **测试**：
  1. 启动后端容器，log 看到 `service_name=core`
  2. curl `/health` 返回 200
  3. 现有所有 API 行为不变
