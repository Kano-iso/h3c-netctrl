# spec: test-backup-rotation-locked

## 能力

3 个 pytest 单元测试覆盖 `BackupManager.rotate()` 的锁定逻辑。

## 范围

### 测试用例
1. **5 非锁定 + 2 锁定 = 7 份 → 保留全部**
2. **7 非锁定 + 1 锁定 = 8 份 → 删 2 个最旧非锁定，剩 5+1**
3. **1 旧锁定 + 5 新非锁定 → 旧锁定保护，不删**

## 设计决策

- 用内存 SQLite + `create_all` 隔离测试
- 手动设 `created_at` 模拟时间序列
- 不依赖真机（纯算法测试）

## 验收标准

- [x] 3/3 PASS in < 1s
- [x] 覆盖锁定保护的所有边界

## 关联 change
- `openspec/changes/archive/2026-06-29-test-backup-rotation-locked/`
