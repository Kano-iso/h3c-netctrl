# v2.4-container-decoupling-asset

> ## ⚠️ SUPERSEDED BY v24-roadmap（2026-07-02）
> 本 change 是 v2.3 评估期的早期提案（拆 2 容器 core/asset + Postgres）。
> v2.4 最终决策已变更，详见 [v24-roadmap/proposal.md](../v24-roadmap/proposal.md)：
> - **拆 3 容器**：`sdn-control` + `data` + `monitor`（不是 2 容器 core/asset）
> - **数据库**：3 容器**各自独立 SQLite**（v2.4 **不迁 Postgres**，v2.5/v3.0 再评估）
> - **内部通信**：Docker internal network + HTTP REST + `X-Internal-Token` 头（**不**用 Postgres 共享）
> - **拆容器实施 sub-change**：[v24-container-decoupling-3tier](../v24-roadmap/proposal.md)（**待创建**）
>
> 本 proposal **不再实施**。保留仅供历史追溯。
> 决策记录：[project_memory.md § v2.4 数据迁移决策](../../../.trae-cn/memory/projects/-root-workpace-h3c-netctrl/project_memory.md)

## Why（历史背景）

v2.3 备份功能上线后 monolith 性能 / 故障域问题加剧：
- 备份 I/O 阻塞 NETCONF 配置下发
- 一个 router 崩溃整个后端挂
- 数据库归属不清晰

`docs/CONTAINER-DECOUPLING.md` 已规划 4 容器蓝图，本 change 实施"v2.3 拆 asset"。

## What Changes

### 拆 asset 容器（独立后端 + 统一 Postgres）

#### 数据迁移
- 启动时 alembic upgrade head（保留现有 SQLite 数据先 export）
- `core` 容器只写 device / log / interface_config / iface_state
- `asset` 容器写 asset / backup / cmdb
- 共用 Postgres `h3cnet_asset` 数据库

#### API 路由归属
| 路由 | 新归属 | 说明 |
|---|---|---|
| `GET /api/devices` | core | device 列表（强一致） |
| `GET /api/devices/{id}/backup` | **asset** | 备份列表（v2.4 拆） |
| `POST /api/devices/{id}/backup` | **asset** | 创建备份 |
| `GET /api/assets` | **asset** | CMDB 资产 |
| `POST /api/assets/refresh` | **asset** | 资产刷新 |

#### 内部通信
- core → asset: 内部 HTTP（不暴露外网）
- 共用 ENV: `INTERNAL_API_TOKEN`

#### docker-compose
```yaml
services:
  postgres:
    image: postgres:15-alpine
    volumes:
      - h3c-postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: h3cnet_asset
      POSTGRES_USER: h3cnet
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  backend-core:
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://h3cnet:${POSTGRES_PASSWORD}@postgres/h3cnet_core
      ASSET_API_URL: http://backend-asset:8001

  backend-asset:
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://h3cnet:${POSTGRES_PASSWORD}@postgres/h3cnet_asset
      LISTEN_PORT: 8001
```

### 阶段
1. **Phase 1（v2.4.0）**：拆分实施
2. **Phase 2（v2.4.1）**：性能压测 + 故障注入测试
3. **Phase 3（v2.4.2）**：上线灰度

## 评估
- **价值**：故障隔离 + 资源争抢解决 + 数据库统一
- **代价**：
  - 工作量大（2-3 周）
  - 数据库迁移风险（SQLite → Postgres）
  - 内部 API 协议设计
  - 测试覆盖要求极高
- **风险**：
  - 数据迁移丢失
  - core/asset 通信失败
  - 备份 / 资产 / CMDB 都依赖 asset 容器

## 当前状态：📋 PROPOSAL ONLY

不在 v2.3.0 发版范围。本 change 仅 OpenSpec 提案。

## Verification (待实施)
- [ ] docker compose up postgres + 跑 alembic migration
- [ ] core/asset 容器独立启动
- [ ] 端到端：core 创建设备 → asset 备份 → core 列表显示备份
- [ ] 故障注入：asset 挂 → core 仍可创建设备（但备份失败 → 中文错误）
- [ ] 性能：核心 NETCONF 100 并发不受 backup I/O 影响

## Files Changed (待实施)
- `docker-compose.dev.yml`：拆 core/asset
- `docker-compose.prod.yml`：同上 + Postgres
- `backend/Dockerfile.{core,asset}.dev`
- `backend/app/routers/`：路由归属调整
- `backend/migrations/`：Postgres 兼容
- `frontend/src/api/`：API 路径不变（前端无感）

## 关联
- `docs/CONTAINER-DECOUPLING.md`
- v3.0 `add-sdn-controller`
- 未来 `add-monitor-service`
