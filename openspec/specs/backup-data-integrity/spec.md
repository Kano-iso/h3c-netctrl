# backup-data-integrity Specification

## Purpose
TBD - created by archiving change fix-backup-data-integrity. Update Purpose after archive.

## Requirements

### Requirement: vite proxy 精确分发备份下载

`frontend/vite.config.js` MUST 加 `DOWNLOAD_PATTERN` 优先分支（`/^\/api\/devices\/\d+\/backup\/\d+\/?$/`），让 `GET /api/devices/{id}/backup/{bid}` 在 split 模式下走 data 容器，core 模式走 backend 容器。

#### Scenario: split 模式下载
- **WHEN** split 模式 + 浏览器 `fetch('/api/devices/1/backup/93')`
- **THEN** MUST 走 data 容器，返回 200（application/octet-stream）或 410（文件丢失）

#### Scenario: core 模式下载
- **WHEN** core 模式 + 浏览器 `fetch('/api/devices/1/backup/93')`
- **THEN** MUST 走 backend 容器，返回 200 或 410

#### Scenario: 优先级不破现有路由
- **WHEN** execute / interfaces / vlans / assets / tasks / backups-async 请求
- **THEN** MUST 仍走原容器（priority 顺序：DOWNLOAD → DATA → CONFIG → CTRL）

### Requirement: 启动时 backup 物理文件自检

`backend/app/utils/backup_integrity.py` MUST 提供 `check_backup_files(db)` 函数，遍历所有 Backup 行检查 `file_path` 是否物理存在。

#### Scenario: 启动时自检 warn
- **WHEN** data 容器启动
- **THEN** MUST 跑 `check_backup_files()`，有 missing 时写 `logger.warning(...)` 列出详情（前 5 条）

#### Scenario: 无 missing
- **WHEN** 所有 backup 物理文件存在
- **THEN** MUST 不打 warn（保持静默启动）

#### Scenario: 启动时自动清理幽灵行
- **WHEN** 启动时检测到 backup 行对应物理文件丢失
- **THEN** MUST 自动删除该 backup 行（避免 list 接口长期显示 410 失败项）

### Requirement: backup-async 数据一致性 4 防线

`BackupManager.create_backup` MUST 实施 4 防线确保 task 报告与 list 接口一致：
1. `DB_PATH` 绝对路径（`/app/data/data.db`），避免 cwd 变化误连 dev.db
2. commit 后 `db.refresh(backup)` 验证行真在 DB（不依赖 session cache）
3. 用真实 id 替换 flush 时分配的临时 id
4. `db.expire_on_commit = False`（长生命周期 session 跨函数避免属性过期）

#### Scenario: task 报告 id 与 list 一致
- **WHEN** 跑 backup-async → task 报告 `result.backups[0].id = X`
- **THEN** `GET /api/devices/{id}/backups` MUST 立刻能看到 id=X 的 backup 行

#### Scenario: 假成功抛 BackupError
- **WHEN** commit 后 backup 行不存在（DB 隔离 / commit 失败）
- **THEN** MUST 抛 `BackupError("commit 后 backup 行不存在: id=X, filename=Y")`，task 报告 failed

### Requirement: 环境清理工具

`tools/dump_db.py` MUST 把 SQLite DB 关键表（devices / backups / assets / tasks / logs / alembic_version）dump 成 JSON，用于人肉验证。

#### Scenario: dump dev.db
- **WHEN** `python tools/dump_db.py --db ./data/dev.db --output /tmp/dev-snapshot.json`
- **THEN** MUST 输出 JSON 文件，列出每张表的列名 + 行数

#### Scenario: 不存在的表
- **WHEN** 某张表在 DB 中不存在
- **THEN** MUST 在 JSON 中标 `null` + 控制台打"表不存在"
