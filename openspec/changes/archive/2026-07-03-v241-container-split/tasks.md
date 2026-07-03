# v241-container-split Tasks

## 1. 基础设施：内部 API 客户端 + 鉴权中间件

- [x] 1.1 新建 `backend/app/internal_api.py`（httpx 客户端 + 重试 + 超时 + X-Internal-Token）
- [x] 1.2 新建 `backend/app/middleware.py`（`verify_internal_token` 中间件，仅拦截 `/internal/*` 路径）
- [x] 1.3 单测 `test_internal_api.py`（mock httpx，验证重试 3 次 + 超时 5s + 鉴权 403）
- [x] 1.4 单测 `test_middleware.py`（加/不加 token 的 401 vs 200）

## 2. 容器入口：3 个 main.py + 3 个 Dockerfile

- [x] 2.1 新建 `backend/ctrl/main.py`（加载 device + log + dashboard router + 内部路由）
- [x] 2.2 新建 `backend/config/main.py`（加载 interface + vlan + execute + batch router）
- [x] 2.3 新建 `backend/data_svc/main.py`（加载 asset + backup + task router + 内部路由）
- [x] 2.4 新建 `backend/ctrl/Dockerfile`（基于 `backend/Dockerfile.dev`，CMD 启动 ctrl/main.py）
- [x] 2.5 新建 `backend/config/Dockerfile`（同上，CMD 启动 config/main.py）
- [x] 2.6 新建 `backend/data_svc/Dockerfile`（同上，CMD 启动 data_svc/main.py）

## 3. 内部端点：跨容器 API

- [x] 3.1 新建 `backend/app/routers/ctrl_internal.py`（`GET /internal/devices` + `GET /internal/devices/{id}` + `POST /internal/logs`）
- [x] 3.2 新建 `backend/app/routers/data_internal.py`（`POST /internal/backup` + `GET /internal/backups/{device_id}`）
- [x] 3.3 单测 `test_ctrl_internal.py`（3 个端点正常/异常路径）
- [x] 3.4 单测 `test_data_internal.py`（2 个端点正常/异常路径）

## 4. 业务改造：跨容器调用

- [x] 4.1 `dashboard.py`：聚合查询改为走内部 API 调 data 容器（`GET /internal/assets`）✅ commit c72f8a2
- [ ] 4.2 `device.py`：删除设备时通知 data 清理关联 asset/backup（`DELETE /internal/devices/{id}/cleanup`）⏸️ 延后 v2.4.2（涉及新增 data 容器 cleanup 端点）
- [x] 4.3 `interface.py` / `vlan.py` / `execute.py` / `batch.py` / `asset.py` / `backup.py`：改用统一设备访问 `device_access.py`（monolith 本地查 / split 走 internal_api）+ 日志内部 API 兜底（`log_recorder.py`）✅ commit 353b4f0
- [x] 4.4 `backend/app/utils/device_access.py` 统一设备访问工具（SimpleNamespace 包装 dict 兼容 ORM 属性访问）✅ commit 353b4f0
- [x] 4.5 单测更新（mock 内部 API 调用，确保业务逻辑不受影响）
- [x] 4.6 全量回归 194 passed, 11 skipped, 0 failed（monolith 模式不破坏）

## 5. docker-compose + 前端适配

- [x] 5.1 `docker-compose.dev.yml`：默认 monolith（backend service）+ profile: split 模式（ctrl + config + data 3 service）✅ commit a3870d8
- [x] 5.2 更新 volumes 归属（backups volume 仅挂 data 容器）
- [x] 5.3 更新 env 注入（INTERNAL_CTRL_URL / INTERNAL_CONFIG_URL / INTERNAL_DATA_URL / INTERNAL_API_TOKEN）
- [x] 5.4 `.env.example` 加新环境变量
- [x] 5.5 `frontend/vite.config.js`：proxy 规则按路径分发到 3 后端（VITE_SPLIT_MODE 控制 target）
- [x] 5.6 启动 3 容器 + `docker compose ps` 全部 running
- [x] 5.7 前端无感验证：所有页面正常加载

## 6. 数据库迁移

- [x] 6.1 新建 `scripts/migrate-v241-split-db.py`：从 monolith `dev.db` 拆出 `ctrl.db` + `data.db`（DROP 不属于该容器的表 + VACUUM）✅ commit e8dfdd4
- [x] 6.2 新建 `scripts/rollback-v241-split-db.py`：合并回 `dev.db`（优先从 .bak 恢复 / 无 .bak 时从 3 分库合并）
- [x] 6.3 验证：迁移后数据不丢失（7 devices + 586 logs + 7 assets + 35 backups + 27 tasks 双向一致）

## 7. 故障注入验证

- [x] 7.1 `docker stop data` → ctrl dashboard 降级到 0,0（assets/backups 表不可用）✅ commit ed88b62
- [x] 7.2 `docker stop ctrl` → config 返回明确错误"设备查询失败: 内部 API 调用失败..."
- [x] 7.3 `docker stop config` → data backup/asset 正常
- [x] 7.4 恢复 3 容器 → 全量回归 194 passed, 11 skipped, 0 failed

## 8. 真机 e2e 验证

- [x] 8.1 3 容器模式下设备管理正常（7 台设备列表）
- [x] 8.2 3 容器模式下接口配置下发正常（63 个接口，NETCONF 真机）
- [x] 8.3 3 容器模式下备份/回滚正常（running 备份成功 id=102 8224 bytes；startup 失败是真机 SCP 问题，与 split 模式无关）
- [ ] 8.4 3 容器模式下全量备份正常（异步模式）⏸️ 留到发版前
- [ ] 8.5 集成测试 `--integration` 4 设备 8 场景 PASS ⏸️ 留到发版前

## 9. 文档更新

- [x] 9.1 `docs/CONTAINER-DECOUPLING.md` 更新为最终方案（ctrl/config/data 三分）
- [x] 9.2 `VERSION-ROADMAP.md` 加 v2.4.1 版本条目
- [x] 9.3 `CONTAINER-INVENTORY.md` 更新（3 容器清单）

## 10. 收尾

- [ ] 10.1 commit（按 task 粒度，每个 task 一个 commit）
- [ ] 10.2 archive
- [ ] 10.3 评估 v2.5/v3.0 是否迁 Postgres（决策点）
