# fix-asset-backup-state-sync — Tasks

> OpenSpec Apply 阶段拆细。每个 Task 对应一次 commit + 可自测可运行。
> 格式：`- [ ] X.Y task description`（OpenSpec CLI 解析 checkbox 跟踪进度）。

## 1. 后端：asset 校验 + force 参数

- [x] 1.1 新增 `backend/app/utils/asset_guard.py`，实现 `check_asset_online(device_id, force=False)`
- [x] 1.2 `backend/app/routers/backup.py` 同步端点（POST /api/devices/{id}/backup）集成校验
- [x] 1.3 `backend/app/routers/backup.py` 异步端点（POST /api/devices/{id}/backup-async）集成校验
- [x] 1.4 force=true 路径加日志（force_backup device_id=... user=...）（已在 check_asset_online 内部实现）
- [x] 1.5 i18n key 加 `error.backup.device_offline`（中英文）（后端 key + FALLBACK_MESSAGES 兜底）
- [~] 1.6 qa-backend pytest 通过 + 4 个 unit case（online/offline × force=True/False） — **PENDING：4 个新 case 已写完，qa-backend 完量回归待 T4.1 补跑；历史 14 个测试问题（asset 离线场景相关）位置见 commit msg**
- [x] 1.7 补全量端点 force 支持：BackupAllRequest 加 `force: bool = False` + POST /api/backups 同步 + POST /api/backups-async 异步 + _async_backup_all_fn(force) 透传到 BackupManager.create_backup(forced=force)（task md 漏写，CMDB.vue 3.4 需要）

## 2. 数据库：backups 表加 forced 列

- [x] 2.1 新增 alembic 迁移 `backend/alembic/versions/006_add_forced_to_backups.py`
- [x] 2.2 迁移 upgrade 路径：`op.add_column("backups", sa.Column("forced", sa.Boolean, nullable=False, server_default="0"))`
- [x] 2.3 迁移 downgrade 路径：`op.drop_column("backups", "forced")`
- [x] 2.4 更新 `backend/app/models.py` Backup 模型加 `forced: Mapped[bool] = mapped_column(default=False)`
- [x] 2.5 端点集成：force=True 时 `backup.forced = True` 后 commit
- [x] 2.6 DB 迁移 up + down 双向通过（SQLite 容器内验证）

## 3. 前端：按钮 + force 勾选框 + 二次确认 + i18n

- [x] 3.1 Devices.vue 行内"备份"按钮 `:disabled="needsForce(d) && !forceChecked.has(d.id)"` + tooltip
- [x] 3.2 Devices.vue 行内加 force 勾选框（仅 offline/never_collected 显示，双向绑定 `forceChecked` Set）
- [x] 3.3 Devices.vue 强制备份二次确认弹窗（ConfirmModal variant=warning，确认后 `backupApi.create(id, force=true)`）
- [x] 3.4 CMDB.vue 全量备份按钮 + force 勾选（全量 force 透传到 backupApi.createAll({force}) + taskApi.backupAsync(force) + taskStore.submitBatchBackup(options.force)）
- [x] 3.5 i18n key（10 个，最终列表）：`button.disabled.asset_offline` / `backup.force_label` / `backup.force_confirm_title` / `backup.force_confirm_msg` / `backup.force_confirm_btn` / `backup.force_success` / `backup.force_failed` / `cmdb.full_backup_force` / `cmdb.full_backup_force_hint` （tasks.md 3.5 漏 4 个补全：`force_success` / `force_failed` / `cmdb.full_backup_force` / `cmdb.full_backup_force_hint`；`error.backup.device_offline` 仅后端 key）
- [x] 3.6 i18n 中英文翻译（zh-CN.js + en-US.js 同步加 10 个 key）
- [x] 3.7 qa-frontend lint + build + 53/53 vitest + 42/42 e2e 通过（4.7m）

## 4. 测试 + 真机集成 — **PENDING：所有交换机关机中（2026-07-06 用户停机），等设备恢复后追验**

- [~] 4.1 qa-backend 全量测试通过（baseline 309 → 313+ passed） — **PENDING：qa 容器**
- [~] 4.2 qa-frontend 全量通过（已完成，标 [x]） — **lint + type-check + build + 53/53 vitest + 42/42 e2e 全过**
- [~] 4.3 真机 .177（asset online）备份成功，force 流程不触发 — **PENDING：交换机 .177 关机**
- [~] 4.4 真机 .5（asset offline）备份按钮 disabled + tooltip 正确 — **PENDING：交换机 .5 关机**
- [~] 4.5 真机 .5（asset offline）+ 勾选 force + 二次确认 → 备份成功 + DB `backups.forced=1` — **PENDING：交换机 .5 关机**
- [~] 4.6 MCP 浏览器验证中英文切换：10 个 key 全部正常翻译 — **PENDING：需设备恢复后走 e2e**

## 5. Archive + A 类文档同步

- [ ] 5.1 写 `RELEASE-NOTES-v2.6.1.md`（commit 序列 + 测试统计 + 真机示例）
- [ ] 5.2 同步 `README.md` 顶部版本表 + 当前架构表（加 forced 字段）
- [ ] 5.3 同步 `VERSION-ROADMAP.md` §1 全景表加 1 行 + §2.6.1 详细章节
- [ ] 5.4 同步 `openspec/specs/`（delta spec 合并到 main spec 或新建 `asset-backup-state-sync`）
- [ ] 5.5 `git mv openspec/changes/fix-asset-backup-state-sync/ → openspec/changes/archive/2026-07-06-fix-asset-backup-state-sync/`
- [ ] 5.6 `git status` 干净 + 通知用户 review + **等用户确认 push**

---

## 阻塞依赖

- 1 → 2 串行（Task 2 依赖 Task 1 的 code path 引用 forced 字段）
- 1-2 → 3（Task 3 依赖后端 API 已支持 force）
- 1-3 → 4（测试验证完整链路）
- 4 → 5（archive 前所有测试通过）

## 风险点

- Task 1.6 后端测试 fixture 准备：需要 mock `assets` 表的 device_id → status 映射
- Task 3.3 二次确认弹窗时序：勾选 force → 点击 → ConfirmModal → 确认 → 提交（不能跳过确认）
- Task 2.2 alembic 迁移：生产 DB 跑前 `make backup`（v2.4.2 起强制）
