# v241-container-split Tasks

## 1. 基础设施：内部 API 客户端 + 鉴权中间件

- [ ] 1.1 新建 `backend/app/internal_api.py`（httpx 客户端 + 重试 + 超时 + X-Internal-Token）
- [ ] 1.2 新建 `backend/app/middleware.py`（`verify_internal_token` 中间件，仅拦截 `/internal/*` 路径）
- [ ] 1.3 单测 `test_internal_api.py`（mock httpx，验证重试 3 次 + 超时 5s + 鉴权 403）
- [ ] 1.4 单测 `test_middleware.py`（加/不加 token 的 401 vs 200）

## 2. 容器入口：3 个 main.py + 3 个 Dockerfile

- [ ] 2.1 新建 `backend/ctrl/main.py`（加载 device + log + dashboard router + 内部路由）
- [ ] 2.2 新建 `backend/config/main.py`（加载 interface + vlan + execute + batch router）
- [ ] 2.3 新建 `backend/data/main.py`（加载 asset + backup + task router + 内部路由）
- [ ] 2.4 新建 `backend/ctrl/Dockerfile`（基于 `backend/Dockerfile.dev`，CMD 启动 ctrl/main.py）
- [ ] 2.5 新建 `backend/config/Dockerfile`（同上，CMD 启动 config/main.py）
- [ ] 2.6 新建 `backend/data/Dockerfile`（同上，CMD 启动 data/main.py）

## 3. 内部端点：跨容器 API

- [ ] 3.1 新建 `backend/app/routers/ctrl_internal.py`（`GET /internal/devices` + `GET /internal/devices/{id}` + `POST /internal/logs`）
- [ ] 3.2 新建 `backend/app/routers/data_internal.py`（`POST /internal/backup` + `GET /internal/backups/{device_id}`）
- [ ] 3.3 单测 `test_ctrl_internal.py`（3 个端点正常/异常路径）
- [ ] 3.4 单测 `test_data_internal.py`（2 个端点正常/异常路径）

## 4. 业务改造：跨容器调用

- [ ] 4.1 `dashboard.py`：聚合查询改为走内部 API 调 data 容器（`GET /internal/assets`）
- [ ] 4.2 `device.py`：删除设备时通知 data 清理关联 asset/backup（`DELETE /internal/devices/{id}/cleanup`）
- [ ] 4.3 `interface.py`：改配置后 POST /internal/logs（调 ctrl）+ POST /internal/backup（调 data）
- [ ] 4.4 `config/main.py`：启动时调 ctrl `GET /internal/devices` 拉 device 列表缓存到本地
- [ ] 4.5 单测更新（mock 内部 API 调用，确保业务逻辑不受影响）
- [ ] 4.6 全量回归 172 passed, 0 failed

## 5. docker-compose + 前端适配

- [ ] 5.1 `docker-compose.dev.yml`：拆 backend → ctrl + config + data 3 service
- [ ] 5.2 更新 volumes 归属（backups volume 仅挂 data）
- [ ] 5.3 更新 env 注入（INTERNAL_CTRL_URL / INTERNAL_CONFIG_URL / INTERNAL_DATA_URL / INTERNAL_API_TOKEN）
- [ ] 5.4 `.env.example` 加新环境变量
- [ ] 5.5 `frontend/vite.config.js`：proxy 规则按路径分发到 3 后端
- [ ] 5.6 启动 3 容器 + `docker compose ps` 全部 running
- [ ] 5.7 前端无感验证：所有页面正常加载

## 6. 数据库迁移

- [ ] 6.1 新建 `scripts/migrate-v241-split-db.py`：从 monolith `dev.db` 拆出 `ctrl.db` + `data.db`
- [ ] 6.2 新建 `scripts/rollback-v241-split-db.py`：合并回 `dev.db`
- [ ] 6.3 验证：迁移后数据不丢失（device count / asset count / backup count 一致）

## 7. 故障注入验证

- [ ] 7.1 `docker stop data` → config 改端口仍成功 + 中文错误提示
- [ ] 7.2 `docker stop ctrl` → config 用本地缓存继续工作
- [ ] 7.3 `docker stop config` → data 备份不受影响
- [ ] 7.4 恢复 3 容器 → 全量回归 172 passed

## 8. 真机 e2e 验证

- [ ] 8.1 3 容器模式下设备管理正常（增删改查）
- [ ] 8.2 3 容器模式下接口配置下发正常
- [ ] 8.3 3 容器模式下备份/回滚正常
- [ ] 8.4 3 容器模式下全量备份正常（异步模式）
- [ ] 8.5 集成测试 `--integration` 4 设备 8 场景 PASS

## 9. 文档更新

- [ ] 9.1 `docs/CONTAINER-DECOUPLING.md` 更新为最终方案（ctrl/config/data 三分）
- [ ] 9.2 `VERSION-ROADMAP.md` 加 v2.4.1 版本条目
- [ ] 9.3 `CONTAINER-INVENTORY.md` 更新（3 容器清单）

## 10. 收尾

- [ ] 10.1 commit（按 task 粒度，每个 task 一个 commit）
- [ ] 10.2 archive
- [ ] 10.3 评估 v2.5/v3.0 是否迁 Postgres（决策点）