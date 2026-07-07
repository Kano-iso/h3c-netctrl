# v2.6.1 bug 修复轮次 — Tasks

## 路线总览

| # | 任务 | 子 change | 状态 |
|---|---|---|---|
| 1 | fix-asset-stale-status 子 change（Propose + Apply + Archive） | `fix-asset-stale-status` | ✅ 已闭环 |
| 2 | fix-asset-collect-failure 子 change（Propose + Apply + Archive） | `fix-asset-collect-failure` | ✅ 已闭环 |
| 3 | fix-asset-split-password-decrypt 子 change（split 模式密码二次解密 bug） | `fix-asset-split-password-decrypt` | ✅ 已闭环 |
| 4 | fix-vite-proxy-route 子 change（vite proxy 长前缀错配 /api/devices/{id}/* → 404） | `fix-vite-proxy-route` | ✅ 已闭环 |
| 5 | add-auto-collect 子 change（**v2.6.0 复盘砍掉 — 9 commit 没真验证，移到 archive + CANCELLED.md**） | `add-auto-collect` | ⛔ 已砍掉（v2.6.2 重新评估） |
| 6 | fix-backup-data-integrity 子 change（备份数据完整性 4 防线） | `fix-backup-data-integrity` | ✅ 已闭环 |
| 7 | fix-asset-backup-state-sync 子 change（offline 设备 force 逃生 + `backups.forced` 审计） | `fix-asset-backup-state-sync` | ✅ 已闭环 |
| 8 | fix-backup-restore-no-response 子 change（**v2.6.1 范围：仅根因定位文档，修复推 v2.6.2**） | `fix-backup-restore-no-response` | 🟡 部分完成（v2.6.2 backlog） |
| 9 | REVIEW-v261-bugfix-round 报告（QA 套件盲区反思） | 本路线 | ✅ 完成 |
| 10 | VERSION-ROADMAP §v2.6.1 + §1 全景表加 1 行 | 本路线 | ✅ 完成 |
| 11 | RELEASE-NOTES-v2.6.1.md | 本路线 | ✅ 完成 |
| 12 | README.md 顶部版本表 + 当前架构表 | 本路线 | ✅ 完成 |
| 13 | git tag v2.6.1 + push | 本路线 | ⏳ 待执行（commit + push 后） |

## 串行顺序

1 → 2 → 3 → 4 ✅
5 → 6 → 7 → 8 → 9 → 10

---

## 子 change 1: fix-asset-stale-status

详见 [openspec/changes/fix-asset-stale-status/tasks.md](../fix-asset-stale-status/tasks.md)。

## 子 change 2: add-auto-collect

详见 [openspec/changes/add-auto-collect/tasks.md](../add-auto-collect/tasks.md)。

## 子 change 3: fix-asset-collect-failure

详见 [openspec/changes/fix-asset-collect-failure/tasks.md](../fix-asset-collect-failure/tasks.md)。

---

## 路线级 checklist（archive 前必查）

- [x] 子 change 1 fix-asset-stale-status 闭环
- [x] 子 change 2 fix-asset-collect-failure 闭环
- [x] 子 change 3 fix-asset-split-password-decrypt 闭环
- [x] 子 change 4 fix-vite-proxy-route 闭环
- [x] 子 change 5 add-auto-collect 砍掉（v2.6.0 复盘后明确不实施）
- [x] 子 change 6 fix-backup-data-integrity 闭环
- [x] 子 change 7 fix-asset-backup-state-sync 闭环
- [x] 子 change 8 fix-backup-restore-no-response 根因定位完成（修复推 v2.6.2）
- [x] 7 个子 change 的 spec.md 已 sync 到 openspec/specs/（add-auto-collect / fix-backup-restore-no-response 因未实施无 main spec）
- [x] `docs/REVIEW-v261-bugfix-round.md` 写完
- [x] `VERSION-ROADMAP.md` 加 §v2.6.1 章节 + §1 全景表加 1 行
- [x] `README.md` 顶部版本表 + 当前架构表 同步
- [x] `RELEASE-NOTES-v2.6.1.md` 写完（含 commit 序列 + 测试统计 + 真机示例）
- [x] `git status` 干净
- [x] `qa-backend` 全量 pytest 与 baseline 对比通过
- [x] `qa-frontend` lint + build 通过
- [x] 通知用户 review
- [ ] git tag v2.6.1 + push（**待执行**）
