# Container Inventory

> 自动生成 by `scripts/container-inventory.sh`
> 时间: 2026-07-02 12:04:22 +0800
> 项目: h3c-netctrl (v2.4)

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

## 基线清单（v2.4 必须保留）

| 容器 | 镜像 | 用途 | 来源 |
|---|---|---|---|
| h3c-netctrl-backend | h3c-netctrl-backend | 后端 API (monolith, v2.4 将拆 3 容器) | docker-compose.dev.yml
| h3c-netctrl-frontend | h3c-netctrl-frontend | 前端 Vue.js | docker-compose.dev.yml
| h3c-netctrl-qa-backend | h3c-netctrl-qa-backend | QA 后端测试 (profile: qa) | docker-compose.dev.yml
| h3c-netctrl-qa-frontend | h3c-netctrl-qa-frontend | QA 前端 build 检查 (profile: qa) | docker-compose.dev.yml
| h3c-netctrl-ops-toolkit | h3c-netctrl-ops-toolkit | 运维排错工具 (profile: ops, 按需启动) | docker-compose.dev.yml

## 清理建议

- **stop 残留容器**: `docker ps -a --filter status=exited` 列出的容器，如非必须可 `docker rm` 删除（需要时 `docker compose up` 重建）
- **dangling 镜像**: `docker image prune -f` 清理
- **未用 volume**: `docker volume prune -f` 清理（**注意**: 会删除匿名 volume，命名 volume 保留）
- **未用镜像**: 当前无容器引用的镜像可 `docker rmi` 删除（需要时重新 pull/build）

清理 SOP 详见 [docs/CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)

---

Last updated: 2026-07-02 12:04:22 +0800
