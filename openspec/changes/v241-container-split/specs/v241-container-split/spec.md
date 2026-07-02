# v241-container-split Spec

## 目标

将 monolith backend 拆分为 3 个独立容器（ctrl / config / data），实现故障域隔离、资源独立、职责清晰。

## 范围

- 后端：9 个 router 按职责分配到 3 容器
- 基础设施：内部 API 客户端 + 鉴权中间件
- 部署：docker-compose 拆 3 service
- 前端：Vite proxy 规则适配
- 数据库：从 monolith SQLite 拆到各自 SQLite

## 非范围

- 不迁 Postgres（v2.5/v3.0 决策点）
- 不加 nginx/Traefik 网关（开发环境 Vite proxy 足够）
- 不改前端业务代码（API 路径不变）
- 不加 monitor 容器（v3.0+ 的事）
- 不做 VPC 功能（v3.0）

## 验收标准

1. 3 容器独立启动，各自监听 8000 端口（外部 8001/8002/8003）
2. 前端所有页面正常（API 路径不变，Vite proxy 透明转发）
3. 内部 API 通信正常（设备列表缓存、改配置后写日志、改配置后触发备份）
4. Docker 内部 DNS 寻址正常（`http://ctrl:8000` / `http://config:8000` / `http://data:8000`）
5. 全量回归 172 passed, 0 failed
6. 数据库迁移脚本可执行且数据不丢失
7. 升级/回退步骤可执行