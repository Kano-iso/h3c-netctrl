# fix-rotation-total-keep Tasks

## 阶段 1：代码改

- [ ] 1.1 `backend/app/config.py` `BACKUP_KEEP` 注释改 "每设备保留总份数（含锁定）"
- [ ] 1.2 `backend/app/utils/backup_manager.py:316-345` `rotate()` 改逻辑：
  - 查所有备份（不 filter locked）
  - 分离 locked / unlocked
  - 锁定数 ≥ keep → log warning + 不删任何（用户锁太多属预期，保留）
  - 锁定数 < keep → to_delete = 总 - keep，从最旧非锁定删
- [ ] 1.3 `.env.example` 注释改

## 阶段 2：单测

- [ ] 2.1 读 `backend/tests/test_backup_rotation.py` 现有 3 case
- [ ] 2.2 改 case "5 非锁定 + 2 锁定 → 保留 5（删 2 最旧非锁定）"
- [ ] 2.3 加 case "3 锁定 + 0 非锁定 → 保留 3（不删，锁不删）"
- [ ] 2.4 加 case "5 锁定 + 2 非锁定 → 保留 7（锁定优先）"
- [ ] 2.5 加 case "0 锁定 + 7 非锁定 → 保留 5（删 2 最旧）"
- [ ] 2.6 `pytest backend/tests/test_backup_rotation.py -v` → 全 PASS

## 阶段 3：UI 文案

- [ ] 3.1 Devices.vue 备份列表顶部加说明
- [ ] 3.2 BackupListModal 顶部加说明

## 阶段 4：真机集成（v2.3.1 一并跑）

- [ ] 4.1 192.168.100.4 backup 端到端跑 7 份全量 → 验证留 5 份
- [ ] 4.2 跑前 backup（n 状态）→ 跑（n+7 状态）→ 改回 n 状态（restore_original_state）

## 阶段 5：发版

- [ ] 5.1 1 个 commit `fix(backup-rotate): 改 BACKUP_KEEP 语义为总份数含锁定 + UI 文案`
- [ ] 5.2 archive 进 `archive/2026-06-30-fix-rotation-total-keep/`
- [ ] 5.3 进 v2.3.1 release notes

---

## 设备最终状态

- 192.168.100.4 备份列表 = 5 份（含 N 锁定）
