# fix-rotation-total-keep Tasks

> **v2.3.1 patch**：BACKUP_KEEP 语义从"非锁定"改为"总份数（含锁定）"
> v2.2 行为是 `keep` = 非锁定保留数，但用户实测发现 5 份 keep 时出现 7 份（2 锁定 + 5 非锁定）
> v2.3.1 改为 `keep` = 总份数（含锁定），更符合直觉。
>
> **实测状态**：单元测试 7 case 全 PASS + 真机 backup 集成 7/7 PASS + 177 上 backup 6 份时仅留 5 份

---

## 阶段 1：代码改

- [x] 1.1 `backend/app/utils/backup_manager.py:316-345` `rotate()` 改逻辑：
  - 查所有备份（不 filter locked）
  - 分离 locked / unlocked
  - 锁定数 ≥ keep → log warning + 不删任何（用户锁太多属预期，保留）
  - 锁定数 < keep → to_delete = 总 - keep，从最旧非锁定删
- [x] 1.2 `backend/app/config.py` BACKUP_KEEP 注释改"每设备保留总份数（含锁定）"
- [x] 1.3 `.env.example` 注释改

## 阶段 2：单测

- [x] 2.1 改 `backend/tests/test_backup_rotation.py` 现有 3 case
- [x] 2.2 改 case "5 非锁定 + 2 锁定 → 保留 5（删 2 最旧非锁定）"
- [x] 2.3 加 case "3 锁定 + 0 非锁定 → 保留 3（不删，锁不删）"
- [x] 2.4 加 case "5 锁定 + 2 非锁定 → 保留 7（锁定优先）"
- [x] 2.5 加 case "0 锁定 + 7 非锁定 → 保留 5（删 2 最旧）"
- [x] 2.6 `pytest backend/tests/test_backup_rotation.py -v` → **7 passed**

## 阶段 3：UI 文案

- [x] 3.1 Devices.vue 备份列表顶部加说明（待用户测，本批 [x] 标"代码完成"）
- [x] 3.2 BackupListModal 顶部加说明（待用户测，本批 [x] 标"代码完成"）

## 阶段 4：真机集成（v2.3.1 一并跑）

- [x] 4.1 192.168.100.177 backup 端到端跑 6 份 → 验证留 5 份（`test_backup_integration.py::test_backup_rotation_keeps_limit` PASS）
- [x] 4.2 pytest `--integration` 跑通（127 passed, 4 skipped, 0 failed）

## 阶段 5：发版

- [x] 5.1 commit `fix(backup-rotate): 改 BACKUP_KEEP 语义为总份数含锁定（v2.3.1 patch）` = `dfd3166`
- [x] 5.2 commit `test(backend): 修 conftest mock + 3 个 rotation 测试适配 v2.3.1 新 BACKUP_KEEP 语义` = `8262086`
- [ ] 5.3 archive 进 `archive/2026-07-01-fix-rotation-total-keep/`
- [ ] 5.4 进 v2.3.1 release notes
- [ ] 5.5 push（**待用户确认**）
- [ ] 5.6 tag v2.3.1（**待用户确认**）

---

## 设备最终状态

- 192.168.100.177 备份列表 = 5 份（实测 PASS）
- 192.168.100.5 未动（生产设备，v2.3.1 不跑真机 backup，仅 177 测试机验证）
