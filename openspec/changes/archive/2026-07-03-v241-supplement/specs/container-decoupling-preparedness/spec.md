# v241-supplement Spec Deltas

> 本 change 在 [container-decoupling-preparedness](../../specs/container-decoupling-preparedness/spec.md) 之上新增 3 个 requirement：
> - 设备删除时 data 容器 cleanup 端点
> - 全量备份异步模式 + MCP 浏览器 e2e
> - split 模式集成测试 4 设备 8 场景

---

## ADDED Requirements

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
