## ADDED Requirements

### Requirement: 后端拆分为 3 个独立 service
v2.3.1 monolith `backend` service 必须拆分为 3 个独立 service：
- `sdn-control`：改端口、VPN、SDN 联动（v3.0 VPC 在此容器）
- `data`：数据库、CMDB、备份（含 `h3c-netctrl-backups` volume 挂载）
- `monitor`：监控指标、自愈记录（v2.4 基础 metrics，v3.0+ AI troubleshooting 在此）

每个 service 有独立 Dockerfile / 独立 SQLite / 独立进程（端口可不同）。

#### Scenario: docker-compose 包含 3 个 service
- **WHEN** 用户执行 `docker compose -f docker-compose.dev.yml config --services`
- **THEN** 输出包含 `sdn-control` + `data` + `monitor` + `frontend` + `qa-*` + `ops-toolkit`（不再有 `backend`）

#### Scenario: 3 service 各自有独立 Dockerfile
- **WHEN** 用户查看 `backend/Dockerfile.sdn-control.dev` / `backend/Dockerfile.data.dev` / `backend/Dockerfile.monitor.dev`
- **THEN** 3 个 Dockerfile 都存在且各自包含对应 service 的依赖（如 sdn-control 包含 paramiko + ncclient，data 包含 sqlalchemy，monitor 包含 prometheus_client）

### Requirement: 容器间通过 HTTP REST 通信
3 service 之间的内部 API 调用必须通过 Docker internal network + HTTP REST：
- sdn-control 暴露 `:8000`（默认端口）
- data 暴露 `:8001`
- monitor 暴露 `:8002`
- 内部 API 走 `http://<service-name>:<port>/api/...`
- 内部 API 必须有 `X-Internal-Token` 头验证（从环境变量 `INTERNAL_API_TOKEN` 读取）

#### Scenario: data 容器调用 sdn-control 拿 device 列表
- **WHEN** data 容器在备份任务中执行 `httpx.get(f"{SDN_API_URL}/api/devices", headers={"X-Internal-Token": TOKEN})`
- **THEN** sdn-control 容器返回 device 列表，data 容器继续备份流程

#### Scenario: 内部 API 缺 token 时拒绝
- **WHEN** data 容器调用 sdn-control 时漏 `X-Internal-Token` 头
- **THEN** sdn-control 返回 401 + 中文错误 "内部 API 缺少认证 token"

### Requirement: 故障注入测试
拆容器后必须跑故障注入测试，验证故障域隔离：
- 故障 1：docker stop data → sdn-control 改端口仍成功（不阻塞）
- 故障 2：docker stop sdn-control → monitor metrics 仍采集（但不更新）
- 故障 3：docker stop monitor → sdn-control / data 不受影响

故障时返回中文错误，不暴露技术异常。

#### Scenario: data 容器挂时 sdn-control 改端口仍成功
- **WHEN** docker stop data 容器后，用户调 `sdn-control API PATCH /api/devices/1/interfaces/2/link-mode`
- **THEN** 接口配置成功（设备改端口不依赖 data 容器），日志记录"CMDB 暂不可用，已记录本地日志"

#### Scenario: sdn-control 容器挂时返回中文错误
- **WHEN** data 容器尝试调用 sdn-control 但 sdn-control 已停
- **THEN** data 容器返回中文错误 "SDN 控制服务不可用，请稍后重试"，不抛技术异常到前端

### Requirement: 路由归属明确
每个 API 路由必须明确归属 3 service 之一（前缀标注），路由文件顶部加注释：

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

前端 API 路径不变（OpenAPI 客户端透明路由）。

#### Scenario: 路由文件顶部有归属标注
- **WHEN** 用户查看 `backend/app/routers/interface.py` / `backup.py` / `monitor.py`
- **THEN** 每个文件顶部有 `# Service: sdn-control` 或 `# Service: data` 或 `# Service: monitor` 注释

### Requirement: 数据迁移可回退
v2.4 拆容器 + 数据迁移必须有 backup 兜底：
- 实施前 `make backup` 强制走一遍（沿用 v2.1.x 决策）
- 每个 sub-change 独立 revert，monolith 仍在 git history
- 灰度：先单机后多机

#### Scenario: 实施前自动 backup
- **WHEN** 用户执行 `make v24-decouple`
- **THEN** 脚本第一步自动跑 `make backup`，备份存在 `data/backups/pre-v24-decouple-<timestamp>/` 才继续

#### Scenario: 拆容器后回退
- **WHEN** 拆容器后出现严重问题需要回退
- **THEN** `git revert` 对应 commit + `docker compose down && docker compose -f docker-compose.monolith.yml up` 即可回退到 monolith
