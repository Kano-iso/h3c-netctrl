# spec: add-backup-type-radio-ui

## 能力

前端全量备份按钮加 type radio 选项（全部 / startup / running）。

## 范围

### 前端
- `Backup.vue` 顶部"立即全量备份"按钮左侧加 3 选项 radio
- 默认"全部"（向后兼容）
- 选 startup / running 时只备该类型

### 后端
- `POST /api/backups` 加 `BackupAllRequest` (types: Optional[List[str]])
- 不传 = 默认全备
- 传 `["xxx"]` = 200 + 中文错误

### Bug 修复
- 路由 `create_all_backups` 硬编码 `types=["startup","running"]`，body 不生效
- 修真：`mgr.create_backup(types=types, db=db)`

## 设计决策

- **向后兼容**：不传 types = 全备（旧行为）
- **错误中文**：业务层 200 + success=False + 中文 error
- **UI radio**：业界主流（RANCID / Oxidized / Ansible Network）按类型区分

## 验收标准

- [x] 19/19 backup_api 测试 PASS
- [x] UI 渲染 radio（前端构建通过）
- [x] 修真 bug 后 body 真正生效

## 关联 change
- `openspec/changes/archive/2026-06-29-add-backup-type-radio-ui/`
