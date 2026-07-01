## ADDED Requirements

### Requirement: 容器拆分布局图（3 容器）
`docs/CONTAINER-DECOUPLING.md` 必须更新，含 v2.4 拆 3 容器的**最终布局图**：
- `sdn-control`：sdn-control.db + 改端口 / VPN / SDN 联动 API
- `data`：data.db + CMDB / 备份 + 持久化 volume
- `monitor`：monitor.db + metrics / 自愈记录
- 3 容器间通过 Docker internal network 通信
- 故障域：sdn-control 改端口不依赖 data / monitor

#### Scenario: 文档含 ASCII 布局图
- **WHEN** 用户查看 `docs/CONTAINER-DECOUPLING.md`
- **THEN** 文档含 3 容器拓扑的 ASCII 图（或 mermaid），标出端口 / 共享 volume / 内部 API

#### Scenario: 文档标 v2.4 决策点
- **WHEN** 用户查看 `docs/CONTAINER-DECOUPLING.md` 第 1 节
- **THEN** 明确标 "v2.4 实施：3 容器"（与 v2.3 评估的"2 容器"对比）

### Requirement: 容器 API 路由归属表
`docs/CONTAINER-DECOUPLING.md` 必须含 API 路由归属表（与 proposal 一致）：

| 路由 | 归属 |
|---|---|
| `POST /api/devices` | sdn-control |
| `PATCH /api/devices/{id}/interfaces/{if_index}/link-mode` | sdn-control |
| `POST /api/devices/{id}/vpn-instances` | sdn-control |
| `GET /api/devices/{id}/backup` | data |
| `POST /api/devices/{id}/backup` | data |
| `GET /api/assets` | data |
| `POST /api/assets/refresh` | data |
| `GET /api/monitor/metrics` | monitor |
| `GET /api/monitor/self-heal` | monitor |

#### Scenario: 路由表完整
- **WHEN** 用户查看 `docs/CONTAINER-DECOUPLING.md` 第 2 节
- **THEN** 表含 9 个核心路由（含 method + 路径 + 归属）

### Requirement: 升级 + 回退步骤
`docs/CONTAINER-DECOUPLING.md` 必须含 v2.4 升级 + 回退步骤：
- 升级：`make backup` → `git pull` → `docker compose pull` → `docker compose up -d` → 端到端验证
- 回退：`docker compose down` → `git revert <commit>` → `docker compose -f docker-compose.monolith.yml up`

#### Scenario: 升级步骤可执行
- **WHEN** 用户按文档升级步骤操作
- **THEN** 拆容器成功，端到端（sdn-control 改端口 → data 备份 → monitor metrics）正常

#### Scenario: 回退步骤可执行
- **WHEN** 拆容器后出现问题，用户按文档回退步骤操作
- **THEN** 回退到 monolith，设备配置 / 备份 / 监控全部正常
