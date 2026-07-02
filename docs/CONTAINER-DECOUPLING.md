# 容器拆分蓝图（v2.4 实施）

**状态**：v2.4 实施中（替换 v2.3 早期 2 容器 core/asset 评估）
**关联 change**: `openspec/changes/v24-roadmap/`
**实施时序**: v2.4.0 拆 3 容器 + v2.4.1 性能压测 + v2.4.2 灰度上线

---

## v2.3 → v2.4 关键变化

| 维度 | v2.3 评估 | v2.4 决策 | 理由 |
|---|---|---|---|
| 容器数 | 2（core + asset） | **3（sdn-control + data + monitor）** | 故障域清晰 + v3.0 VPC 落地更顺 |
| 数据归属 | 统一 Postgres | **3 容器各自独立 SQLite** | v2.4 不迁 Postgres（决策点 v2.5/v3.0） |
| 内部通信 | 未设计 | **Docker internal network + HTTP REST + X-Internal-Token** | 简单可控，复杂度 ROI 低于 gRPC |
| asset 概念 | 独立容器 | **并入 data 容器** | asset + CMDB + 备份都是 I/O 重低频业务 |

---

## 3 容器职责

| 容器 | 职责 | 资源特征 | 数据库 | v3.0 扩展 |
|---|---|---|---|---|
| **sdn-control** | NETCONF / SSH 改端口 / VPN / 设备 CRUD / 操作日志 | 高频 NETCONF，CPU 中 | SQLite: device / log / interface_config | VPC 联动落地 |
| **data** | CMDB / 资产采集 / 配置备份 / 异步任务管理 | 低频批处理，I/O 重 | SQLite: cmdb / asset / backup / tasks | 长保留历史 |
| **monitor**（v2.4 基础） | 指标采集 / 自愈钩子（v2.4 框架，v3.0+ 完善） | 高频 polling | SQLite: metric | AI 抓包 / troubleshooting |

---

## 拓扑图

```
                          前端 (Vue.js 5173)
                               │
                               ▼
   ┌────────────────────────────────────────────────┐
   │       API 网关 (nginx/Traefik - 后续)          │
   │       当前: 前端直接连 3 后端 (load balance)   │
   └────────┬───────────────┬──────────────┬────────┘
            │               │              │
            ▼               ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ sdn-control  │ │     data     │ │   monitor    │
    │   :8001      │ │    :8002     │ │    :8003     │
    │              │ │              │ │              │
    │  device      │ │  cmdb        │ │  metrics     │
    │  interface   │ │  asset       │ │  self_heal   │
    │  vpn         │ │  backup      │ │  (v2.4 空)   │
    │  log         │ │  task        │ │              │
    │              │ │              │ │              │
    │ SQLite       │ │ SQLite       │ │ SQLite       │
    │  /data/dev.db│ │  /data/cmdb.db│ │ /data/mon.db│
    │              │ │  /data/asset.db│ │             │
    │              │ │  /data/backup.db│ │             │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┴────────────────┘
                            │
                内部通信: X-Internal-Token
                (Docker internal network h3c-net)
```

---

## API 路由归属表（拆分参考）

| router | 当前 (monolith) | 未来归属 (v2.4) | 备注 |
|---|---|---|---|
| `device.py` | monolith | **sdn-control** | 设备 CRUD / 详情 |
| `vlan.py` | monolith | **sdn-control** | VLAN 配置 |
| `interface.py` | monolith | **sdn-control** | 接口配置 + VPN instance |
| `vpn.py` | monolith | **sdn-control** | VPN instance |
| `execute.py` | monolith | **sdn-control** | SSH 终端 + 异步执行 |
| `log.py` | monolith | **sdn-control** | 操作日志（高频写） |
| `auth.py` | monolith | **sdn-control** | 认证授权（sdn-control 入口） |
| `health.py` | monolith | **sdn-control**（+ 各容器自检） | 基础 health 路由 |
| `dashboard.py` | monolith | **sdn-control**（汇总） | 仪表盘聚合查询 |
| `batch.py` | monolith | **sdn-control** | 批处理任务 |
| `cmdb.py` | monolith | **data** | CMDB 资产 |
| `asset.py` | monolith | **data** | 资产采集 |
| `backup.py` | monolith | **data** | 备份 + 异步任务管理 |
| `metrics.py`（v2.4 新增） | — | **monitor** | 指标暴露 |
| `self_heal.py`（v2.4 框架） | — | **monitor** | 自愈钩子（v2.4 基础） |
| `task.py`（v2.4 新增） | monolith | **data** | 异步任务管理（与 backup 一起） |

**前端无感**：API 路径不变，前端通过反向代理 / load balancer 路由到对应容器。

---

## 容器间通信

### 协议
- **HTTP REST**（不用 gRPC，复杂度 ROI 低）
- **Docker internal network** `h3c-net`（容器间无外部网络暴露）

### 鉴权
- **X-Internal-Token** 头：所有跨容器请求必须带
- `INTERNAL_API_TOKEN` 环境变量：3 容器共享同一密钥（docker secret 或 env 注入）
- `verify_internal_token` 中间件：sdn-control / data / monitor 各自实现

### 超时与重试
- 超时 5s
- 重试 3 次，指数退避（1s / 2s / 4s）
- 失败记录中文错误（不暴露技术异常）

### 典型通信场景

| 调用方 | 被调方 | 接口 | 场景 |
|---|---|---|---|
| sdn-control | data | `POST /internal/devices/{id}/asset-refresh` | 改端口后刷新 CMDB |
| sdn-control | data | `POST /internal/backup` | 改配置后自动备份 |
| monitor | sdn-control | `GET /internal/devices` | 拉设备列表采集指标 |
| monitor | data | `GET /internal/backups` | 备份状态采集 |
| data | sdn-control | `GET /internal/interfaces/{id}` | 备份前拉接口配置 |

---

## 数据库策略

**v2.4 决策**：3 容器各自独立 SQLite（不迁 Postgres）

**理由**：
- v2.4 重点是故障域隔离，I/O 隔离已通过容器拆分实现
- 迁 Postgres 工作量大（迁移工具 / 主从 / 备份策略），v2.4 ROI 低
- 评估点：v2.4 收尾时决策 v2.5 / v3.0 是否迁

**共享数据**（device 列表 / interface 配置）：
- **缓存模式**：data 容器启动时通过内部 API 拉 device 列表缓存到本地 SQLite
- **失效模式**：sdn-control 改 device 时通过内部 API 通知 data 失效
- **读写分离**：data 主要读，sdn-control 写

**备份数据**（v2.2 引入）：
- 仅 data 容器拥有
- 共享 `h3c-netctrl-backups` volume 挂到 data 容器
- sdn-control 触发备份时通过内部 API 调用 data 的 `/internal/backup` 端点

---

## 升级步骤

```bash
# 1. 备份（强制）
make backup

# 2. 拉取新代码 + 新镜像
git pull
docker compose -f docker-compose.dev.yml pull

# 3. 启动 3 容器（顺序：data → sdn-control → monitor）
docker compose -f docker-compose.dev.yml up -d data
docker compose -f docker-compose.dev.yml up -d sdn-control
docker compose -f docker-compose.dev.yml up -d monitor

# 4. 端到端验证
make qa
# 预期: 183 passed（拆 3 容器后端到端测试）
```

## 回退步骤

```bash
# 1. 停止 3 容器
docker compose -f docker-compose.dev.yml down

# 2. 回退到 monolith 版本
git revert <commit>
docker compose -f docker-compose.dev.yml up -d backend

# 3. 验证
make qa
# 预期: 183 passed（monolith 行为不变）
```

**最坏情况**：回退到 v2.3.1 monolith docker-compose，数据零损失（SQLite 文件不变）。

---

## 故障注入测试场景（v2.4.1）

| 故障 | 预期行为 | 验证 |
|---|---|---|
| `docker stop data` | sdn-control 改端口仍成功 + 中文错误"CMDB 不可用，已记录本地日志" | sdn-control 接口返 success:true + 业务降级 |
| `docker stop sdn-control` | monitor 仍采集（但不更新 device 列表缓存） | monitor metrics 持续输出 |
| `docker stop monitor` | sdn-control / data 不受影响 | 改端口 / 备份正常 |
| `docker stop data` 同时触发备份 | 备份任务暂存到 sdn-control 内存，data 恢复后自动重放 | 任务管理器持久化 |

---

## 关联

- 路线图: [openspec/changes/v24-roadmap/proposal.md](../openspec/changes/v24-roadmap/proposal.md)
- 基线清单: [CONTAINER-INVENTORY.md](CONTAINER-INVENTORY.md)
- 清理 SOP: [CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)
- ops-toolkit: [ops-toolkit.md](ops-toolkit.md)
- QA: [QA-GUIDE.md](QA-GUIDE.md)
- 上版蓝图（v2.3 2 容器评估）: [archive/2026-07-02-v2.4-container-decoupling/](../openspec/changes/archive/2026-07-02-v2.4-container-decoupling/proposal.md)
