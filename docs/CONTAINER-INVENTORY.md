# Container Inventory

> 自动生成 by `scripts/container-inventory.sh`
> 时间: 2026-07-02 12:04:22 +0800（v2.4.0 baseline）
> 项目: h3c-netctrl (v2.4.1)
>
> **v2.4.1 新增**：split 模式（profile: split）下的 3 容器清单见下方"基线清单（v2.4.1 split 模式）"章节。
> 如需重新生成本文件，运行：`bash scripts/container-inventory.sh > docs/CONTAINER-INVENTORY.md`

## 容器 (docker ps -a)

| 名称 | 镜像 | 状态 | 端口 |
|---|---|---|---|
| h3c-netctrl-frontend | h3c-netctrl-frontend | Up 8 hours | 0.0.0.0:5173->5173/tcp, [::]:5173->5173/tcp |
| h3c-netctrl-ops-toolkit | h3c-netctrl-ops-toolkit | Up 38 hours | - |
| h3c-netctrl-backend | h3c-netctrl-backend | Up 11 hours | 0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp |

## 镜像 (docker images)

| 仓库 | 标签 | 大小 | 创建时间 |
|---|---|---|---|
| h3c-netctrl-frontend | latest | 303MB | 8 hours ago |
| h3c-netctrl-ops-toolkit | latest | 294MB | 2 days ago |
| h3c-netctrl-qa-frontend | latest | 295MB | 3 days ago |
| h3c-netctrl-qa-backend | latest | 343MB | 3 days ago |
| h3c-netctrl-backend | latest | 342MB | 3 days ago |
| python | 3.10-slim | 185MB | 3 weeks ago |

## Dangling 镜像

- 无 dangling 镜像

## Volumes (docker volume ls)

| Driver | Name |
|---|---|
| local | h3c-netctrl_h3c-netctrl-backups |

## 网络 (docker network ls)

| Network ID | Name | Driver | Scope |
|---|---|---|---|
| 441a728ff9f6 | bridge | bridge | local |
| a216ecba0f1e | h3c-netctrl_h3c-net | bridge | local |
| 2fe4969320d0 | host | host | local |
| 401f436e2716 | none | null | local |

## 基线清单（v2.4.1 monolith 模式，默认）

| 容器 | 镜像 | 用途 | 来源 |
|---|---|---|---|
| h3c-netctrl-backend | h3c-netctrl-backend | 后端 API（monolith 全量，v2.4.1 split 模式下停用） | docker-compose.dev.yml `backend` service |
| h3c-netctrl-frontend | h3c-netctrl-frontend | 前端 Vue.js（Vite proxy 按 VITE_SPLIT_MODE 分发） | docker-compose.dev.yml `frontend` service |
| h3c-netctrl-qa-backend | h3c-netctrl-qa-backend | QA 后端测试（profile: qa） | docker-compose.dev.yml `qa-backend` service |
| h3c-netctrl-qa-frontend | h3c-netctrl-qa-frontend | QA 前端 build 检查（profile: qa） | docker-compose.dev.yml `qa-frontend` service |
| h3c-netctrl-ops-toolkit | h3c-netctrl-ops-toolkit | 运维排错工具（profile: ops，按需启动） | docker-compose.dev.yml `ops-toolkit` service |

## 基线清单（v2.4.1 split 模式，profile: split）

> 启动方式：`docker compose --profile split up -d ctrl config data frontend`
> 停用 monolith backend，3 容器各自独立 SQLite（ctrl.db / config.db 无业务表 / data.db）

| 容器 | 镜像 | 用途 | 端口 | 数据库 |
|---|---|---|---|---|
| h3c-ctrl | h3c-netctrl-ctrl（构建自 backend/ctrl/Dockerfile） | 设备身份中心：device + log + dashboard + auth + health | 8001 → 8000 | `./data/ctrl.db`（devices / logs / alembic_version） |
| h3c-config | h3c-netctrl-config（构建自 backend/config/Dockerfile） | 设备配置中心：interface + vlan + execute + batch | 8002 → 8000 | 无业务表（设备查询走 internal_api 调 ctrl） |
| h3c-data | h3c-netctrl-data（构建自 backend/data_svc/Dockerfile） | 数据采集存储：asset + backup + task + data_internal | 8003 → 8000 | `./data/data.db`（assets / backups / tasks / alembic_version） |
| h3c-netctrl-frontend | h3c-netctrl-frontend | 前端（VITE_SPLIT_MODE=true 时按路径分发到 3 容器） | 5173 → 5173 | — |
| h3c-netctrl-qa-backend | h3c-netctrl-qa-backend | QA 后端测试（profile: qa，与 split 模式无关） | — | — |
| h3c-netctrl-qa-frontend | h3c-netctrl-qa-frontend | QA 前端 build 检查（profile: qa） | — | — |
| h3c-netctrl-ops-toolkit | h3c-netctrl-ops-toolkit | 运维排错工具（profile: ops，按需启动） | — | — |

**Volume 归属**：
- `h3c-netctrl-backups` volume 仅挂到 data 容器（split 模式）或 backend（monolith 模式）

**内部网络通信**：
- 容器间走 Docker DNS（`http://ctrl:8000` / `http://config:8000` / `http://data:8000`）
- X-Internal-Token 头鉴权（`INTERNAL_API_TOKEN` 环境变量注入）
- httpx 客户端 + 3 次指数退避 + 5s 超时

## 清理建议

- **stop 残留容器**: `docker ps -a --filter status=exited` 列出的容器，如非必须可 `docker rm` 删除（需要时 `docker compose up` 重建）
- **dangling 镜像**: `docker image prune -f` 清理
- **未用 volume**: `docker volume prune -f` 清理（**注意**: 会删除匿名 volume，命名 volume 保留）
- **未用镜像**: 当前无容器引用的镜像可 `docker rmi` 删除（需要时重新 pull/build）
- **split 模式切换残留**：从 split 切回 monolith 后，3 个 split 镜像（h3c-netctrl-ctrl / -config / -data）可保留（下次切换直接复用）或 `docker rmi` 清理（需要时重新 build）

清理 SOP 详见 [docs/CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)
容器拆分蓝图详见 [docs/CONTAINER-DECOUPLING.md](CONTAINER-DECOUPLING.md)

---

Last updated: 2026-07-03 v2.4.1（在 v2.4.0 自动生成清单基础上补 split 模式基线清单）
