# v241-supplement

> **类型**：platform（v2.4.1 容器拆分补全）
> **优先级**：P0
> **目标版本**：v2.4.1（与 v241-container-split 合并发版，不开 v2.4.2）
> **前序**：[archive/2026-07-03-v241-container-split](../archive/2026-07-03-v241-container-split/)（3 容器拆分已 archive，留 3 个 pending task）

---

## Why

`v241-container-split` 已 archive，但 tasks.md 留了 3 个 pending：

| Task | 摘要 | 实际严重性 | 用户原话 |
|---|---|---|---|
| **4.2** | 删除设备时通知 data 清理关联 asset/backup | **split 模式真有孤儿数据风险**（SQLAlchemy `cascade="all, delete-orphan"` 跨容器失效） | "这么点小功能还延后吗？" |
| **8.4** | split 模式全量备份异步模式 | **业务缺失**（v2.4.0 已实现单设备异步，全量没接；用 MCP 浏览器做 e2e 即可） | "e to e 是不是可以用谷歌的 mcp 那个形式" |
| **8.5** | split 模式集成测试 4 设备 8 场景 | **测试覆盖缺失**（已有 13 个 integration test 跑 monolith，split 模式 0 覆盖） | "保留为发版前必跑" |

**用户决策**：合并到 v2.4.1 重做 tag，**不开 v2.4.2**（"就这么点小功能，又开一个版本，没意义"）。

---

## What Changes

### Task 4.2：data 容器 cleanup 端点 + device.py 调用

- **新增**：`backend/app/routers/data_internal.py` 加 `DELETE /internal/devices/{id}/cleanup`
  - 删 `assets` 表对应行
  - 删 `backups` 表对应行 + 删除本地备份文件（`os.remove`）
  - 返回 `{success: true, data: {deleted_assets: N, deleted_backups: M}}`
- **修改**：`backend/app/routers/device.py` `delete_device` 在 `db.delete(device) + db.commit()` 后调内部 API
  - monolith 模式：SQLAlchemy cascade 已自动级联清理 asset/backup，**不调**内部 API（避免重复删）
  - split 模式：本表删除成功 → 调 `data_internal.cleanup_device(id)`
  - 内部 API 调用失败不阻塞主流程（设备已删，记录警告 + 中文错误给前端）
- **新增单测**：`test_data_internal.py` 加 cleanup 端点测试（3 case：正常 / 设备无关联数据 / 部分文件已丢失）

### Task 8.4：全量备份异步 + MCP 浏览器 e2e

- **修改**：`backend/app/routers/backup.py` `create_all_backups` 改 task_manager.submit 异步实现
  - 同步实现保留作 `POST /api/backups`（向后兼容，**默认行为**）
  - 新增 `POST /api/backups-async` → 提交 task → 立即返回 `{task_id, status_url}`（**前端默认走 async**）
  - 内部循环复用 `_async_backup_fn`（已存在）
- **修改**：`frontend/src/components/BackupListModal.vue` / 类似触发点 → 默认调 `/api/backups-async`（v2.4.0 已实现单设备异步 + BackgroundTaskPanel，全量复用）
- **真机 e2e**：MCP 浏览器（integrated_browser / Chrome DevTools MCP）跑 split 模式
  - 起 3 容器 → 登录前端 → 打开 CMDB 页面 → 点"全量备份"按钮 → 验 BackgroundTaskPanel 出现 task → 轮询 task status → 验完成
  - 全程截图 + 关键步骤断言
  - **恢复到测试前状态**：清理 e2e 期间产生的备份文件

### Task 8.5：split 模式集成测试 4 设备 8 场景

- **新增**：`backend/tests/test_split_integration.py`（pytest + 真机 4 设备）
  - 4 设备：192.168.100.4 (Leaf-03) / 192.168.100.5 (生产) / 192.168.100.100 / 192.168.100.177
  - 8 场景：
    1. 设备列表（ctrl 容器）
    2. 接口列表 + status 正确（config 容器 NETCONF 真机）
    3. running 备份成功（data 容器）
    4. 全量异步备份（split 模式端到端）
    5. 设备删除清理（split 模式 + data 容器 cleanup）
    6. Dashboard 聚合查询（ctrl 跨容器调 data 降级容错）
    7. 故障注入：data 容器 down → config 仍工作
    8. 故障注入：ctrl 容器 down → 返回明确中文错误
  - 每个 case 必须 `restore_original_state`（n → n+1 → n）
  - 跑法：`docker compose --profile qa run --rm --entrypoint "pytest tests/test_split_integration.py -m integration -v" qa-backend`
- **新增 fixture**：`backend/tests/conftest.py` 加 `split_mode_client`（起 3 容器 test 模式 + mock internal_api）

### Postgres 决策点

- v2.4.1 收尾时评估 v2.5/v3.0 是否迁 Postgres：**已完成**（详见 [docs/CONTAINER-DECOUPLING.md § Postgres 决策点评估](../../../../docs/CONTAINER-DECOUPLING.md#postgres-决策点评估v241-收尾)）
- 决策：v2.5 不迁（ROI 不足），v3.0 评估点（看 VPC 跨容器事务需求）

---

## 关联

- 前序 change：[archive/2026-07-03-v241-container-split](../archive/2026-07-03-v241-container-split/)
- 路线图：[VERSION-ROADMAP.md v2.4.1](../../../../VERSION-ROADMAP.md#9-v241-拆-3-容器实施-实施中)
- 蓝图：[docs/CONTAINER-DECOUPLING.md](../../../../docs/CONTAINER-DECOUPLING.md)
- QA 规范：[openspec/changes/QA-TEMPLATE.md](../../QA-TEMPLATE.md)

---

## Acceptance Criteria

- [ ] 3 个 pending task 全部完成 + commit + 单测全 PASS
- [ ] 194+ passed, 11 skipped, 0 failed（qa-backend 跑通）
- [ ] qa-frontend build 通过
- [ ] 真机集成测试 8 场景全 PASS（设备不通时 skip）
- [ ] MCP 浏览器 e2e 全量备份异步流程截图 + 断言
- [ ] 重做 v2.4.1 tag（覆盖 archive 状态）
- [ ] RELEASE-NOTES-v2.4.1.md 写清 3 个补全内容

---

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | `DELETE /internal/devices/{id}/cleanup` | backend/app/routers/data_internal.py |
| 后端 API | `POST /api/backups-async` | backend/app/routers/backup.py |
| 后端 API | `DELETE /api/devices/{id}` | backend/app/routers/device.py |
| 前端 UI | "全量备份"按钮改异步 | frontend/src/components/CMDB.vue / BackupListModal.vue |
| 真实设备 | 192.168.100.4/.5/.100/.177 | - |
| 浏览器 e2e | MCP 浏览器跑 split 模式全量备份 | - |

### 2. QA 验证项

#### 2.1 后端 API 单元 / 集成（qa-backend 容器跑）

- [ ] `DELETE /internal/devices/{id}/cleanup` 端点存在 + 正常路径（删 asset + backup + 文件）
- [ ] 设备无关联数据时返回 `{deleted_assets: 0, deleted_backups: 0}`
- [ ] 备份文件已丢失不抛异常（继续清元数据 + 记录警告）
- [ ] `POST /api/backups-async` 立即返回 `{task_id, status_url}`（不阻塞）
- [ ] `DELETE /api/devices/{id}` split 模式：删 device → 调 cleanup → 内部 API 失败不阻塞主流程
- [ ] device.py 单测：monolith 模式不调内部 API（cascade 已自动）
- [ ] 中文错误信息（"清理失败: 内部 API 调用失败"而非裸抛技术异常）

#### 2.2 前端 UI 验证（qa-frontend 容器跑 vite build）

- [ ] `npm run build` 编译过
- [ ] 浏览器 6.x 验证：CMDB 页面"全量备份"按钮触发异步任务，BackgroundTaskPanel 出现

#### 2.3 真机集成（pytest --integration 跑 4 设备）

- [ ] split 模式起 3 容器（docker compose --profile split up）
- [ ] 8 场景全 PASS（详见上文 Task 8.5 清单）
- [ ] **每个 case 必须 restore_original_state**
- [ ] reboot / restart 类操作 sleep + retry ≥ 90s
- [ ] **凭理论推断打 [x] 禁止**——实测 vs 推断严格区分

#### 2.4 MCP 浏览器 e2e

- [ ] integrated_browser 或 Chrome DevTools MCP 跑 split 模式
- [ ] 全量备份异步流程：登录 → 切 split 模式 → 打开 CMDB → 点全量备份 → 验 task 出现 → 验完成
- [ ] 关键步骤截图 + 断言
- [ ] 清理 e2e 期间产生的备份文件

#### 2.5 回归

- [ ] v2.4.1 既有 194+ 测试全 PASS（不破坏）
- [ ] split 模式所有 API 端点 smoke 全过
- [ ] 故障注入：data / ctrl / config 各自 stop 后业务降级符合预期
- [ ] 数据库双向迁移（monolith → split → monolith）数据不丢失

### 3. 跑法

```bash
# 单元 + smoke（CI 必跑，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 预期：194+ passed, 11 skipped, 0 failed

# 集成（按需跑，分钟级，需 SSH 通设备 + split 模式）
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data frontend
docker compose -f docker-compose.dev.yml --profile qa run --rm --entrypoint "pytest tests/test_split_integration.py -m integration -v" qa-backend
# 预期：8 场景全 PASS（设备不通时 skip）

# 前端编译（CI 必跑，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend

# MCP 浏览器 e2e（v2.4.1 发版前必跑，分钟级）
# 在 split 模式起好后，用 MCP 浏览器打开 http://localhost:5173，跑全量备份异步流程
```

### 4. 验收标准

- [ ] 单元 / smoke 全 PASS（qa-backend 跑通）
- [ ] 真机集成 8 场景全 PASS 或设备不通时 skip
- [ ] 前端编译过（qa-frontend 跑通）
- [ ] MCP 浏览器 e2e 全量备份流程通过
- [ ] 文档：RELEASE-NOTES-v2.4.1.md / VERSION-ROADMAP.md / CONTAINER-DECOUPLING.md 同步更新
- [ ] v2.4.1 tag 重做
