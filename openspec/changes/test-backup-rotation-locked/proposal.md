# test-backup-rotation-locked

## Why

v2.2.0 backup-frontend 用户提问：锁定备份能否被轮转掉？
- 担心：备份锁了还会被覆盖
- 实际：老代码已按"非锁定 keep N"轮转，锁定的不会被覆盖
- **问题**：无回归测试，逻辑对不对靠肉眼看代码

## What Changes

3 个 pytest 单元测试覆盖 `BackupManager.rotate()`：

### Test 1: 5 非锁定 + 2 锁定 → 保留 7（不轮转）
- 7 份 ≤ keep=5 + 2 锁定边界
- 期望：rotate(0) — 不删

### Test 2: 7 非锁定 + 1 锁定 → 保留 6（删 2 非锁定）
- 8 份 > keep=5 + 1 锁定
- 期望：删 2 个最旧的非锁定，留 5 非锁定 + 1 锁定

### Test 3: 旧锁定 + 5 新非锁定 → 保留 6（保护旧锁定）
- 1 锁定（早于其他）+ 5 非锁定
- 期望：rotate(0) — 锁定在前，不删

## Verification
- pytest tests/test_backup_rotation.py -v
- 全部 PASS

## Files Changed
- `backend/tests/test_backup_rotation.py`（新增）
