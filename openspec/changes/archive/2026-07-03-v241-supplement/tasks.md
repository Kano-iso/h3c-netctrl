# v241-supplement Tasks

## 任务清单

### 1. Proposal 阶段（已完成）

- [x] 1.1 起草 proposal.md（Why / What / Acceptance / QA）
- [x] 1.2 起草 design.md（决策 / 文件清单 / 升级回退）
- [x] 1.3 起草 tasks.md（本文件）
- [x] 1.4 起草 spec delta（MODIFIED requirements）

### 2. Task 4.2：cleanup 端点 + device.py 内部 API

- [x] 2.1 `backend/app/routers/data_internal.py` 新增 `DELETE /internal/devices/{id}/cleanup` 端点
  - 删 assets 表对应行（return count）
  - 删 backups 表对应行 + 删除本地备份文件（return count）
  - 备份文件已丢失不抛异常，继续清元数据 + 记录 warning
  - 中文错误处理："清理失败: 内部 API 调用失败 / 文件删除失败"
- [x] 2.2 `backend/app/routers/device.py` `delete_device` 改造
  - monolith 模式：SQLAlchemy cascade 自动级联，不调内部 API
  - split 模式：db.delete + commit 成功 → 调 `data_internal.cleanup_device(id)`
  - 内部 API 失败：log warning + 继续返回 success（设备已删事实）
  - 前端响应：成功 → success:true + data；部分失败 → success:true + warning
- [x] 2.3 单测：`backend/tests/test_data_internal.py` 加 3 case
  - 正常路径（设备有 1 asset + 2 backups）
  - 设备无关联数据（return 0, 0）
  - 备份文件已丢失（return 0, 1，warning 日志）
- [x] 2.4 qa-backend 跑通（214 passed, 0 failed）
- [x] 2.5 commit: `feat(cleanup): split 模式删设备时调 data 容器清理关联 asset/backup`

### 3. Task 8.4：全量备份异步 + MCP 浏览器 e2e

- [x] 3.1 `backend/app/routers/backup.py` 新增 `POST /api/backups-async`
  - 复用 `_async_backup_fn`（已存在）
  - 内部 for 循环改为 task_manager.submit
  - 立即返回 `{task_id, status_url: "/api/tasks/{id}"}`
- [x] 3.2 `frontend/src/components/BackupListModal.vue` 改调 `/api/backups-async`
  - 复用已有 BackgroundTaskPanel + Pinia task store
- [x] 3.3 qa-backend 跑通
- [x] 3.4 qa-frontend build 通过
- [x] 3.5 MCP 浏览器 e2e 验证（split 模式）
  - 起 3 容器
  - integrated_browser 跑全量备份异步流程
  - 截图 + 断言 task_id + status=success
  - 清理 e2e 期间产生的备份文件
- [x] 3.6 commit: `feat(async-backup): 全量备份改异步模式，复用 _async_backup_fn`

### 4. Task 8.5：split 模式集成测试 8 场景

- [x] 4.1 `backend/tests/conftest.py` 加 `split_mode_client` fixture
  - 起 3 容器 test 模式（如未起则用环境变量判断）
  - 内部 API 走真实 HTTP（不 mock）
  - 设备不通时 skip（pytest.mark.integration）
- [x] 4.2 `backend/tests/test_split_integration.py` 写 8 case
  - 1. 设备列表（GET /api/devices，split 模式走 ctrl）
  - 2. 接口列表 + status 正确（GET /api/devices/{id}/interfaces，config 容器 NETCONF 真机）
  - 3. running 备份成功（POST /api/devices/{id}/backup，data 容器）
  - 4. 全量异步备份（POST /api/backups-async，split 端到端）
  - 5. 设备删除清理（DELETE /api/devices/{id} + 验 data 容器 cleanup 调用）
  - 6. Dashboard 聚合（GET /api/dashboard，ctrl 跨容器调 data 降级容错）
  - 7. 故障注入 data 容器 down → config 仍工作
  - 8. 故障注入 ctrl 容器 down → 返回明确中文错误
- [x] 4.3 每个 case 必须 `restore_original_state`（n → n+1 → n）
- [x] 4.4 真机跑：`docker compose --profile qa run --rm --entrypoint "pytest tests/test_split_integration.py -m integration -v" qa-backend`
- [x] 4.5 8 场景全 PASS（设备不通时 skip）
- [x] 4.6 commit: `test(split): split 模式集成测试 4 设备 8 场景`

### 5. 文档收尾

- [x] 5.1 `RELEASE-NOTES-v2.4.1.md` 写清 3 个补全内容 + 真机 e2e 截图
- [x] 5.2 `VERSION-ROADMAP.md` v2.4.1 状态"实施中"→"已发版"
- [x] 5.3 `docs/CONTAINER-DECOUPLING.md` "已知遗留"章节更新（4.2/8.4/8.5 全部完成）
- [x] 5.4 commit: `docs(v2.4.1): 补全说明 + ROADMAP 状态更新`

### 6. 收尾

- [x] 6.1 全量回归：qa-backend + qa-frontend + 真机 e2e
- [x] 6.2 重做 v2.4.1 tag（删除原 v2.4.1，commit 完重打）
- [x] 6.3 `openspec archive v241-supplement` 成功
- [x] 6.4 验证 main spec 已同步（container-decoupling-preparedness）
- [x] 6.5 commit: `chore(v2.4.1): archive v241-supplement + 重做 tag`

---

## 总工作量预估

- Task 4.2: 1-2 小时
- Task 8.4: 30 分钟代码 + 10-15 分钟 MCP e2e
- Task 8.5: 3-4 小时（含真机跑）
- 文档 + 收尾: 1 小时

**合计**：6-8 小时（按 OpenSpec 流程，1 天可完成）

## 完成标准

- [x] 3 个 pending task 全部完成 + commit
- [x] 214 passed, 0 failed（qa-backend）
- [x] 8 场景 split 集成测试全 PASS
- [x] MCP 浏览器 e2e 全量备份流程通过
- [x] RELEASE-NOTES-v2.4.1.md 写清
- [x] v2.4.1 tag 重做
- [x] openspec archive v241-supplement 成功
