# container-decoupling-preparedness Specification

## Purpose
TBD - created by archiving change container-decoupling. Update Purpose after archive.
## Requirements
### Requirement: 未来 4 容器职责划分蓝图

`docs/CONTAINER-DECOUPLING.md` MUST 文档化 3 容器职责划分（ctrl / config / data），替换原 v2.1.x patch 的 4 容器蓝图（core/asset/sdn/monitor）：

| 容器 | 职责 | 资源特征 | 数据库表 | 外部端口 |
|---|---|---|---|---|
| **ctrl** | 设备身份中心：device CRUD / 操作日志 / dashboard 聚合 / 认证 | 高频读写，CPU 中 | `devices` / `logs` / `alembic_version` | 8001 |
| **config** | 设备配置中心：interface / vlan / execute / batch（SSH/NETCONF 下发） | 高频 NETCONF，CPU 重 | 无业务表（设备查询走 internal_api 调 ctrl） | 8002 |
| **data** | 数据采集存储：asset / backup / task | 低频批处理，I/O 重 | `assets` / `backups` / `tasks` / `alembic_version` | 8003 |

monitor 容器 v2.4.1 暂不立（v3.0 VPC 落地时再评估）。

#### Scenario: 文档反映 3 容器方案

- **WHEN** 团队成员查看 `docs/CONTAINER-DECOUPLING.md`
- **THEN** MUST 看到 ctrl / config / data 3 容器的职责 + 资源特征 + 数据库归属 + 外部端口
- **AND** MUST 看到与 v2.4.0 蓝图（sdn-control/data/monitor）的关键变化对比表

#### Scenario: monolith/split 双模式共存

- **WHEN** 团队成员查看 `docker-compose.dev.yml`
- **THEN** MUST 看到默认 `backend` service（monolith 模式）+ `profile: split` 下的 `ctrl` / `config` / `data` 3 service
- **AND** 切换方式文档化：`docker compose --profile split up -d ctrl config data`

### Requirement: SERVICE_NAME env 注入

`backend/app/main.py` MUST 读取 `SERVICE_NAME` 环境变量，3 容器模式下分别注入 `ctrl` / `config` / `data`。

#### Scenario: ctrl 容器启动

- **WHEN** ctrl 容器启动（`SERVICE_NAME=ctrl`）
- **THEN** 后端 MUST log `service_name=ctrl`，加载 device + log + dashboard + auth + health router

#### Scenario: config 容器启动

- **WHEN** config 容器启动（`SERVICE_NAME=config`）
- **THEN** 后端 MUST log `service_name=config`，加载 interface + vlan + execute + batch router

#### Scenario: data 容器启动

- **WHEN** data 容器启动（`SERVICE_NAME=data`）
- **THEN** 后端 MUST log `service_name=data`，加载 asset + backup + task router

### Requirement: docker-compose 蓝图注释

`docker-compose.dev.yml` MUST 在当前 `backend` 服务上方加注释块，列出 4 个未来服务名 + 职责（不实际新增 service，仅注释）。

#### Scenario: 查看 docker-compose
- **WHEN** 团队成员打开 `docker-compose.dev.yml`
- **THEN** MUST 看到注释明确标注"当前 monolith，未来拆 core/asset/sdn/monitor 4 容器"

### Requirement: Router 注释分组

`backend/app/routers/__init__.py` MUST 在顶部加注释表格，标注每个 router 未来归属（core / asset / sdn / monitor），**不实际移动文件**。

#### Scenario: 路由归属可读
- **WHEN** 团队成员查看 `routers/__init__.py`
- **THEN** MUST 看到每个 router 注释 `# future: core | asset | sdn | monitor`

### Requirement: README 未来架构章节

`README.md` MUST 新增"未来架构"章节，包含 4 容器职责简图。

#### Scenario: README 完整
- **WHEN** 查看 `README.md`
- **THEN** MUST 在"版本状态"之后看到"未来架构"小节，描述 core/asset/sdn/monitor 4 个未来容器

### Requirement: 实施标记

`docs/CONTAINER-DECOUPLING.md` MUST 明确标注"本次 change 仅做预留，未实际拆容器"，并指向 v2.4.1 拆 ctrl/config/data 的入口。

#### Scenario: 防止误读
- **WHEN** 团队成员阅读蓝图
- **THEN** MUST 看到 "本次 change 仅做预留" + 实施时序（v2.3 / v3.0 / 未来）

### Requirement: 内部 API 客户端 + 鉴权中间件

3 容器间跨容器通信 MUST 通过 HTTP REST + `X-Internal-Token` 头鉴权，禁止裸 HTTP 调用。

- **客户端**：`backend/app/internal_api.py`（httpx + 3 次指数退避重试 + 5s 超时）
- **中间件**：`backend/app/middleware.py`（`verify_internal_token` 仅拦截 `/internal/*` 路径）
- **寻址**：环境变量注入（`INTERNAL_CTRL_URL` / `INTERNAL_CONFIG_URL` / `INTERNAL_DATA_URL`）+ Docker DNS 容器名解析，禁止硬编码 IP:Port

#### Scenario: 内部 API 鉴权失败

- **WHEN** 跨容器请求未带 `X-Internal-Token` 头或 token 不匹配
- **THEN** 被调容器 MUST 返回 401，调用方记录中文错误"内部 API 鉴权失败"

#### Scenario: 内部 API 重试机制

- **WHEN** 跨容器请求超时或被调容器不可达
- **THEN** 客户端 MUST 重试 3 次，指数退避（1s / 2s / 4s）
- **AND** 全部失败后返回中文错误（不暴露技术异常）

### Requirement: 统一设备访问模式

config 和 data 容器无 `devices` 表，查询 device 凭据 MUST 通过 `backend/app/utils/device_access.py` 统一封装：

- **monolith 模式**：本地 `db.query(Device)` 优先（性能最优，无网络开销）
- **split 模式**：本地表查询抛 OperationalError → 走 `internal_api.get_device()` 兜底
- **设备真不存在**（本地查到 None）→ 直接返回错误，不走 internal_api（避免无谓网络调用）
- **SimpleNamespace 包装**：内部 API 返回的 dict 用 SimpleNamespace 包装，兼容 ORM 属性访问（`device.host` / `device.id`）

#### Scenario: monolith 模式本地查

- **WHEN** monolith 模式调用 `get_device_with_password(db, device_id)`
- **AND** 设备存在
- **THEN** MUST 返回 ORM Device 对象 + 解密密码，不走 internal_api

#### Scenario: split 模式走 internal_api

- **WHEN** split 模式（config/data 容器无 devices 表）调用 `get_device_with_password(db, device_id)`
- **THEN** 本地查询抛异常后 MUST 走 `internal_api.get_device(device_id)`
- **AND** 返回 SimpleNamespace 包装的对象 + 已解密密码

#### Scenario: 设备真不存在

- **WHEN** monolith 模式本地查到 `device=None`（表可用但记录不存在）
- **THEN** MUST 直接返回 `APIResponse(success=False, error="设备不存在: id=...")`
- **AND** 不走 internal_api（避免无谓网络调用）

### Requirement: 日志内部 API 兜底

config/data 容器写操作日志 MUST 通过 `backend/app/utils/log_recorder.py` 统一封装：

- **monolith 模式**：本地 `db.add(Log)` + `db.commit()`
- **split 模式**：本地写失败 → 走 `internal_api.write_log()` 调 ctrl 容器 `POST /internal/logs`

#### Scenario: split 模式日志走 ctrl

- **WHEN** config 容器改配置后记录日志
- **AND** 本地 logs 表不可用（split 模式）
- **THEN** MUST 走 `internal_api.write_log()` 调 ctrl 容器
- **AND** ctrl 容器收到 `POST /internal/logs` 后写入本地 logs 表

### Requirement: 数据库拆分/回滚脚本

v2.4.1 MUST 提供数据库迁移脚本，支持 monolith `dev.db` ↔ split `ctrl.db` + `data.db` 双向迁移：

- **拆分**：`scripts/migrate-v241-split-db.py`（拷贝 dev.db → 3 份 → 各自 DROP 不属于的表 → VACUUM）
- **回滚**：`scripts/rollback-v241-split-db.py`（优先从 dev.db.bak 恢复 / 无 .bak 时从 3 分库合并）
- **库表归属**：ctrl = devices + logs + alembic_version；data = assets + backups + tasks + alembic_version；config 无业务表

#### Scenario: 拆分后数据量一致

- **WHEN** 运行 `python scripts/migrate-v241-split-db.py`
- **THEN** ctrl.db MUST 包含原 dev.db 的全部 devices + logs 记录
- **AND** data.db MUST 包含原 dev.db 的全部 assets + backups + tasks 记录
- **AND** 数据量双向验证一致（如 7 devices + 586 logs + 7 assets + 35 backups + 27 tasks）

#### Scenario: 回滚优先从 .bak 恢复

- **WHEN** 运行 `python scripts/rollback-v241-split-db.py`
- **AND** dev.db.bak 存在
- **THEN** MUST 优先从 dev.db.bak 恢复（最可靠路径）
- **AND** 无 .bak 时从 ctrl.db + data.db 合并建表 + 拷贝数据

### Requirement: 故障注入容错

3 容器拆分后 MUST 通过故障注入验证，单容器故障不影响其他容器核心功能：

- `docker stop data` → ctrl dashboard 降级（assets/backups 表不可用显示 0,0），config 改端口仍成功
- `docker stop ctrl` → config 返回明确错误"设备查询失败: 内部 API 调用失败..."，data 备份失败明确提示
- `docker stop config` → ctrl / data 不受影响
- 恢复 3 容器 → 全量回归通过

#### Scenario: data 容器故障 ctrl 降级

- **WHEN** `docker stop data`
- **AND** 访问 ctrl 的 `/api/dashboard`
- **THEN** ctrl MUST 降级返回（assets_count=0, backups_count=0），不抛 500
- **AND** config 改端口配置仍成功（不依赖 data）

#### Scenario: ctrl 容器故障 config 明确报错

- **WHEN** `docker stop ctrl`
- **AND** 访问 config 的接口配置端点
- **THEN** config MUST 返回明确中文错误"设备查询失败: 内部 API 调用失败..."
- **AND** 不暴露技术异常（如 ConnectionRefusedError）

### Requirement: 前端 Vite proxy 按路径分发

split 模式下前端 Vite dev server proxy MUST 按路径前缀分发到 3 后端，前端业务代码不变：

- `/api/devices` / `/api/logs` / `/api/dashboard` → ctrl:8000
- `/api/interfaces` / `/api/vlans` / `/api/execute` / `/api/batch` → config:8000
- `/api/assets` / `/api/backups` / `/api/tasks` → data:8000
- 切换由 `VITE_SPLIT_MODE` 环境变量控制（true=split / 未设=monolith）

#### Scenario: split 模式 API 路径分发

- **WHEN** `VITE_SPLIT_MODE=true`
- **AND** 前端请求 `GET /api/devices`
- **THEN** Vite proxy MUST 转发到 `http://ctrl:8000`
- **AND** 前端请求 `GET /api/interfaces/...` MUST 转发到 `http://config:8000`

#### Scenario: monolith 模式全转 backend

- **WHEN** `VITE_SPLIT_MODE` 未设或 false
- **THEN** Vite proxy MUST 全部转发到 `http://backend:8000`（向后兼容）

### Requirement: 设备删除时 data 容器清理关联数据

split 模式下，ctrl 容器删除 device 时 MUST 通过 `data_internal.cleanup_device()` 调 data 容器清理关联 asset / backup 数据 + 本地备份文件：

- **新增端点**：`DELETE /internal/devices/{id}/cleanup`（data 容器）
  - 删 `assets` 表对应行（return `deleted_assets` count）
  - 删 `backups` 表对应行（return `deleted_backups` count）
  - 删本地备份文件（`os.remove`，文件不存在不抛异常）
- **修改**：`backend/app/routers/device.py` `delete_device` 路由
  - **monolith 模式**：SQLAlchemy `cascade="all, delete-orphan"` 自动级联清理，**不调**内部 API
  - **split 模式**：本地 `db.delete + commit` 成功后调 `data_internal.cleanup_device(id)`（httpx + 内部 token）
  - **失败容忍**：内部 API 失败仅 log warning + 返回成功（设备已删事实优先），前端响应带 `warning` 字段
- **数据完整性**：备份文件由 data 容器本地存储（volume 挂载），cleanup 端点必须删文件 + 元数据双管齐下

#### Scenario: split 模式删设备触发 cleanup

- **WHEN** split 模式下 `DELETE /api/devices/{id}` 在 ctrl 容器执行
- **AND** 该设备有 2 个 asset + 3 个 backup
- **THEN** ctrl MUST 调 data 容器 `DELETE /internal/devices/{id}/cleanup`
- **AND** data 容器 MUST 返回 `{success: true, data: {deleted_assets: 2, deleted_backups: 3}}`
- **AND** 本地备份文件 MUST 全部删除（`os.path.exists(backup.file_path) == False`）

#### Scenario: monolith 模式不调内部 API

- **WHEN** monolith 模式 `DELETE /api/devices/{id}` 执行
- **THEN** SQLAlchemy cascade 自动清理关联 asset + backup 行
- **AND** MUST 不调 `data_internal.cleanup_device()`（避免重复删）

#### Scenario: 设备无关联数据

- **WHEN** split 模式删设备时无 asset / backup
- **THEN** cleanup 端点 MUST 返回 `{success: true, data: {deleted_assets: 0, deleted_backups: 0}}`

#### Scenario: 备份文件已丢失不阻塞

- **WHEN** backup 元数据存在但本地文件已丢失
- **THEN** cleanup 端点 MUST 继续删元数据 + log warning，不抛 500

#### Scenario: 内部 API 失败容忍

- **WHEN** split 模式调 `data_internal.cleanup_device()` 超时或返错
- **THEN** ctrl MUST log warning
- **AND** 返回 `APIResponse(success=True, data={warning: "关联数据清理失败: ..."})`
- **AND** 不抛 500 / 不阻塞设备已删的事实

### Requirement: 全量备份异步模式 + MCP 浏览器 e2e

`POST /api/backups-async` MUST 提供全量备份异步执行能力，复用 `_async_backup_fn` + `task_manager.submit`：

- **新增端点**：`POST /api/backups-async`（data 容器）
  - 接收 `{types: ["startup", "running"]}`（默认两者都拉）
  - 内部循环用 `task_manager.submit` 提交异步任务
  - 立即返回 `{task_id, status_url: "/api/tasks/{id}"}`
- **前端切换**：`BackupListModal.vue` / `CMDB.vue` 改调 `/api/backups-async`
  - 复用已有 `BackgroundTaskPanel` + Pinia `useTaskStore`（v2.4.0 已实现）
- **向后兼容**：`POST /api/backups`（同步）保留，CLI / 脚本可继续用
- **真机 e2e**：v2.4.1 发版前必跑 MCP 浏览器（integrated_browser / Chrome DevTools MCP）
  - 起 3 容器 split 模式
  - 浏览器打开 `http://localhost:5173`
  - 登录 → 切 split 模式 → 打开 CMDB → 点"全量备份"按钮
  - 验 BackgroundTaskPanel 出现 + task_id + status=running → success
  - 截图保存 + 清理 e2e 期间产生的备份文件

#### Scenario: 异步提交立即返回

- **WHEN** `POST /api/backups-async` 调入（4 设备）
- **THEN** MUST 在 100ms 内返回 `{task_id, status_url}`
- **AND** 不阻塞等待所有设备备份完成

#### Scenario: 前端 BackgroundTaskPanel 显示

- **WHEN** 前端 `BackupListModal.vue` 调 `/api/backups-async`
- **THEN** BackgroundTaskPanel MUST 出现 task
- **AND** 轮询 `GET /api/tasks/{id}` 显示进度（10% → 90% → success）
- **AND** 完成后显示成功 + 备份数

#### Scenario: MCP 浏览器 e2e 全量备份

- **WHEN** MCP 浏览器（integrated_browser）在 split 模式跑全量备份
- **THEN** 浏览器 MUST 完成：登录 → CMDB → 点"全量备份" → 验 task 出现 → 验完成
- **AND** 关键步骤截图保存
- **AND** 清理 e2e 期间产生的备份文件（恢复 n+1 → n 状态）

### Requirement: split 模式集成测试 4 设备 8 场景

`backend/tests/test_split_integration.py` MUST 跑 4 设备 × 8 场景 split 模式端到端测试：

- **测试设备**：
  - 192.168.100.4 (Leaf-03)
  - 192.168.100.5 (生产)
  - 192.168.100.100
  - 192.168.100.177
- **8 场景**：
  1. 设备列表（`GET /api/devices`，split 模式走 ctrl）
  2. 接口列表 + status 正确（`GET /api/devices/{id}/interfaces`，config 容器 NETCONF 真机）
  3. running 备份成功（`POST /api/devices/{id}/backup`，data 容器）
  4. 全量异步备份（`POST /api/backups-async`，split 端到端）
  5. 设备删除清理（`DELETE /api/devices/{id}` + 验 data 容器 cleanup 调用）
  6. Dashboard 聚合（`GET /api/dashboard`，ctrl 跨容器调 data 降级容错）
  7. 故障注入 data 容器 down → config 仍工作
  8. 故障注入 ctrl 容器 down → 返回明确中文错误
- **fixture 设计**：`backend/tests/conftest.py` 加 `split_mode_client`（起 3 容器 + 内部 API 走真实 HTTP）
- **状态恢复**：每个 case 必须 `restore_original_state`（n → n+1 → n），备份类操作必须显式清理

#### Scenario: split 模式 4 设备 8 场景全 PASS

- **WHEN** 跑 `docker compose --profile qa run --rm --entrypoint "pytest tests/test_split_integration.py -m integration -v" qa-backend`
- **AND** 4 设备全部可达
- **THEN** 8 场景 MUST 全 PASS
- **AND** 备份文件 / device 列表恢复到测试前状态

#### Scenario: 设备不通时 skip

- **WHEN** 1+ 设备不可达（SSH / NETCONF 失败）
- **THEN** 该 case MUST `pytest.skip("设备不可达")`，不阻塞其他 case

#### Scenario: 故障注入容错

- **WHEN** 跑场景 7：`docker stop data` 后调 config 接口
- **THEN** config MUST 仍返回 200（不依赖 data）
- **AND** 跑场景 8：`docker stop ctrl` 后调 config 接口
- **THEN** config MUST 返回明确中文错误"设备查询失败: 内部 API 调用失败..."
- **AND** 故障恢复后 8 场景再跑仍全 PASS

