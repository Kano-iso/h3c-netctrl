# fix-rotation-total-keep

## Why

v2.3.0 用户实测（2026-06-30）报："保留 5 个这一点没做到啊...保留 7 个的情况"。

**根因**：
`backend/app/config.py` `BACKUP_KEEP: int = 5  # 每设备保留非锁定份数`
`backend/app/utils/backup_manager.py:316-345` `rotate()` 只删**非锁定**备份（filter `locked == False`），保留 5 份**非锁定**，**锁定备份不计**。

**实际效果**：5 份非锁定 + 2 份锁定 = 7 份总数（用户感受"5 没做到"）。
**用户期望**（按 BACKUP_KEEP 名字 = "保留 5 个"）：**总数 ≤ 5**，含锁定。

按 v2.3.1 patch 修复。

## What Changes

### 1. 语义改：BACKUP_KEEP = 总数（含锁定）

- `BACKUP_KEEP: int = 5  # 每设备保留**总份数**（含锁定）`（注释改）
- **不重命名变量名**（保持 BACKUP_KEEP 减少 .env 改动）
- 实际行为 = "该设备最多 5 份，锁定优先保留"

### 2. rotate 逻辑改

- 旧：只查非锁定，删超出 keep 的最旧非锁定
- 新：
  1. 查该设备**所有**备份（按 created_at ASC）
  2. 分离锁定 vs 非锁定
  3. 锁定数 ≥ keep → 锁定就超了，**警告 + 不删任何非锁定**（防误删锁定）
     实际：锁定 ≥ keep → 删 0 个非锁定，但**总份数 > keep** 是预期行为（用户锁太多）
  4. 锁定数 < keep → `to_delete = 总份数 - keep`，从最旧**非锁定**里删
  5. 锁定永远不被轮转删（保留 v2.2.0 承诺）

### 3. 单测加边界

- `backend/tests/test_backup_rotation.py`（已有）改 3 个 case
  - 旧 case "5 非锁定 + 2 锁定 → 保留 7（不轮转）" 改 "5 非锁定 + 2 锁定 → **保留 5**（删 2 最旧非锁定）"
  - 加 case "3 锁定 + 0 非锁定 → 保留 3（不删，锁定数已达 keep 但锁的不删）"
  - 加 case "5 锁定 + 2 非锁定 → 保留 7（锁定优先，不删任何）"（防误删）
  - 加 case "0 锁定 + 7 非锁定 → 保留 5（删 2 最旧非锁定）"（行为不变）

### 4. .env.example 更新

```
# 备份保留份数（含锁定）。保留最新 5 份，锁定优先保留不被轮转。
BACKUP_KEEP=5
```

### 5. UI 文案

- Backup.vue / Devices.vue 备份列表顶部说明："每设备保留最新 5 份（锁定优先保留不被轮转）"

## Verification

### 单元测试

- [ ] 跑 `pytest backend/tests/test_backup_rotation.py -v` → 全 PASS

### 真机集成（v2.3.1 patch 一并跑）

- [ ] 192.168.100.4：跑 7 份全量（14 行：7 startup + 7 running）→ 验证留 5 份（不含 N 锁定）
- [ ] n → n+1 → n 恢复

### UI 验收

- [ ] Devices.vue 表格行备份列表总数 ≤ 5
- [ ] BackupListModal 列表总数 ≤ 5

## Out of Scope

- 不改锁定的"防误删"语义（v2.2.0 承诺）
- 不改 `BACKUP_KEEP` 变量名（避免 .env 改动，只改注释）
- 不动 `create_backup` 行为

## Lessons Learned

- **变量名和注释必须一致**——`BACKUP_KEEP = "每设备保留非锁定份数"` 注释错的（实际是"非锁定份数"对，但用户以为是"总数"）。修：注释改对 + 行为改对。
- **用户语义 = 直觉**——"保留 5 个"在备份场景下直觉是总数，不能是"5 个某类型"。

## 关联

- v2.3.1 patch（一起发）
- 上版 v2.2.0 备份保留 5 份（按"非锁定"实现）→ v2.3.0 改回"非锁定" → v2.3.1 改"总数"
