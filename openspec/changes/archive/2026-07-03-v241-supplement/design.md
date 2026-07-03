# v241-supplement Design

## 决策记录

### D1: Task 4.2 内部 API 失败不阻塞主流程

**决策**：device.py `delete_device` 内部 API 失败不抛异常，仅记录警告 + 返回中文错误给前端。

**理由**：
- 设备在 ctrl 容器已 `db.delete + db.commit`（事实已发生）
- data 容器 cleanup 失败只意味着产生孤儿数据（asset/backup 残留），**不影响核心业务**
- 用户在 UI 上看到的：success=true + 警告信息（"设备已删除，但部分关联数据清理失败，请联系管理员"）
- 兜底：data 容器有定时任务（v2.5+ 评估）扫孤儿数据兜底

**风险**：孤儿数据短期残留（无备份文件丢失风险，因为 SCP 备份文件在 data 容器本地，cleanup 时一并删）

### D2: Task 8.4 全量备份异步 vs 同步双端点

**决策**：`POST /api/backups`（同步）保留 + `POST /api/backups-async`（异步）新增。

**理由**：
- 同步端点保留向后兼容（CLI / 脚本可能调）
- 前端默认改调异步端点
- 异步实现复用 `_async_backup_fn`（已存在），改 for 循环为 task_manager.submit wrapper

**前端切换**：
- `BackupListModal.vue` / `CMDB.vue` 改 fetch URL：`/api/backups` → `/api/backups-async`
- 复用已有 `BackgroundTaskPanel` + Pinia store（v2.4.0 已实现）

### D3: Task 8.5 split 模式集成测试 fixture 设计

**决策**：复用 monolith 模式 integration test + 新增 `split_mode_client` fixture。

**理由**：
- 13 个现有 integration test 跑 monolith 真机 PASS（v2.4.0 / v2.4.1 验证过）
- split 模式集成测试 = 同一批 case 但跑在 split 容器下
- fixture 设计：起 3 容器 + 内部 API 走真实 HTTP（不 mock，因为 split 模式本身就是测跨容器调用）
- 设备不通时 skip（integration marker 已实现，详见 [backend/tests/conftest.py:14-34](../../../../backend/tests/conftest.py#L14-L34)）

**与 13 个现有 integration test 关系**：
- 现有：跑 monolith 模式（所有 router 在同一进程）
- 新增：跑 split 模式（router 分 3 容器，跨容器 HTTP 通信）
- 8 场景 = 13 case 的核心 8 个子集（按 ROI 选最重要的 8 个）

### D4: MCP 浏览器选型

**决策**：优先 `integrated_browser`（Trae 内置），备选 `Chrome DevTools MCP`。

**理由**：
- `integrated_browser` 用法简单（browser_navigate / browser_click / browser_snapshot），Trae 用户原话"谷歌 mcp 那个形式"很可能指这个
- `Chrome DevTools MCP` 功能更全（lighthouse_audit / performance_analyze），但用法更复杂
- v2.4.1 MVP 用 integrated_browser，复杂场景（性能分析）再切 Chrome DevTools

**e2e 步骤**：
1. browser_navigate http://localhost:5173
2. browser_snapshot → 找登录按钮
3. browser_type 用户名/密码
4. browser_click 登录
5. browser_snapshot → 找 "全量备份" 按钮
6. browser_click 触发
7. browser_wait_for BackgroundTaskPanel 出现
8. browser_snapshot 验证 task_id + status=running
9. 轮询 task status 直至 success
10. 截图保存 + 清理备份文件

### D5: 三个 task 优先级

| Task | 业务影响 | 工作量 | 优先级 |
|---|---|---|---|
| **4.2 cleanup 端点** | split 模式孤儿数据 | 1-2 小时 | P0 |
| **8.4 全量异步** | 业务缺失 | 30 分钟代码 + MCP e2e 验证 | P0 |
| **8.5 split 集成测试** | 测试覆盖 | 3-4 小时 + 真机跑 | P0 |

**实施顺序**：4.2 → 8.4 → 8.5（4.2 最简单先做，8.5 最复杂最后做）

---

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|---|---|
| `backend/tests/test_split_integration.py` | split 模式集成测试 8 场景 |
| `backend/tests/test_data_internal.py` | data_internal cleanup 端点单测（如未存在） |
| `docs/RELEASE-NOTES-v2.4.1.md` | v2.4.1 发版说明 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `backend/app/routers/data_internal.py` | 新增 `DELETE /internal/devices/{id}/cleanup` 端点 |
| `backend/app/routers/device.py` | `delete_device` 调内部 API（split 模式） |
| `backend/app/routers/backup.py` | 新增 `POST /api/backups-async`（复用 _async_backup_fn） |
| `frontend/src/components/BackupListModal.vue` / `CMDB.vue` | 改调 `/api/backups-async` |
| `backend/tests/conftest.py` | 加 `split_mode_client` fixture（如需要） |
| `VERSION-ROADMAP.md` | v2.4.1 状态从"实施中"→"已发版" + 详细章节更新 |
| `docs/CONTAINER-DECOUPLING.md` | "已知遗留"章节更新（4.2/8.4/8.5 全部完成） |
| `RELEASE-NOTES-v2.4.1.md` | 新增 |

### 不变文件

- `backend/app/internal_api.py`：现有 `get_device` / `write_log` 等已够用
- `backend/app/middleware.py`：不变
- 数据库：不变（v2.4.1 收尾决策 v2.5 不迁 Postgres）
- monolith 模式：完全不动（向后兼容）

---

## 升级步骤

```bash
# 1. 强制备份
make backup

# 2. 拉取新代码 + 重做 v2.4.1 tag
git pull
git checkout v2.4.1

# 3. 数据库无变更（schema 兼容）

# 4. 启动 3 容器（split 模式）
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data frontend

# 5. 端到端验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
# 8 场景 split 集成测试 + MCP 浏览器 e2e
```

## 回退步骤

```bash
# 1. 停 split 容器
docker compose -f docker-compose.dev.yml --profile split down

# 2. 切回 monolith（v2.4.1 monolith 模式仍可用）
docker compose -f docker-compose.dev.yml up -d backend frontend

# 3. 验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 预期：194+ passed（monolith 行为不变）
```

**最坏情况**：回退到 v2.4.0 monolith tag，零数据损失。
