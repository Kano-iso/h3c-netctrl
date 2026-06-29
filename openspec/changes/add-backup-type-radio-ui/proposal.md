# add-backup-type-radio-ui

## Why

v2.2.0 backup-frontend 用户反馈：点"立即全量备份"一次出现 3 份备份（running + startup + 之前的 running）。
体验问题：startup/running 名称相近，UI 没区分，用户感觉是重复的。

## What Changes

### 1. 前端 type radio
- `Backup.vue` 顶部"立即全量备份"按钮左侧加 3 选项 radio：`全部` / `startup` / `running`
- 选"全部" = 2 份/设备（默认，向后兼容）
- 选"startup" = 1 份/设备（持久化配置）
- 选"running" = 1 份/设备（动态配置）

### 2. 后端接受 body
- `POST /api/backups` 加 `BackupAllRequest` (types: Optional[List[str]])
- 不传 = 默认全备
- 传 `["startup"]` = 只备 startup
- 传 `["xxx"]` = 200 + 中文错误"不支持的备份类型"

### 3. 修真 bug
**Bug A**：原代码 `create_all_backups` 路由用 `body.types` 做校验但 `mgr.create_backup(types=["startup", "running"])` 硬编码全备。
**修**：`mgr.create_backup(types=types, db=db)`（用 body 解析后的 types）

### 4. 测试
- `test_create_all_with_types_filter`：3 case（startup / running / 全部 / 错误类型）
- `test_create_all_invalid_type`：错误类型业务层 200 + 中文错误

## Verification
```
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
→ 105 passed, 11 skipped in 2.67s
```

## Files Changed
- `frontend/src/views/Backup.vue`（type radio + 按钮 + handleFullBackup 传 types）
- `frontend/src/api/index.js`（createAll 接受 body）
- `backend/app/routers/backup.py`（BackupAllRequest + 修 Bug A）
- `backend/tests/test_backup_api.py`（+2 case）
