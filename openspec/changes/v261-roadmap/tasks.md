# v2.6.1 bug 修复轮次 — Tasks

## 路线总览

| # | 任务 | 子 change | 状态 |
|---|---|---|---|
| 1 | fix-asset-stale-status 子 change（Propose + Apply + Archive） | `fix-asset-stale-status` | ✅ 已闭环 |
| 2 | fix-asset-collect-failure 子 change（Propose + Apply + Archive） | `fix-asset-collect-failure` | ✅ 已闭环 |
| 3 | fix-asset-split-password-decrypt 子 change（split 模式密码二次解密 bug） | `fix-asset-split-password-decrypt` | ✅ 已闭环 |
| 4 | fix-vite-proxy-route 子 change（vite proxy 长前缀错配 /api/devices/{id}/* → 404） | `fix-vite-proxy-route` | ✅ 已闭环 |
| 5 | add-auto-collect 子 change（**拆细重做**——subagent 跑得太快，9 commit 没真验证） | `add-auto-collect` | ⏳ Propose 完，Apply 待开始 |
| 6 | REVIEW-v261-bugfix-round 报告（QA 套件盲区反思） | 本路线 | ⏳ |
| 7 | VERSION-ROADMAP §v2.6.1 + §1 全景表加 1 行 | 本路线 | ⏳ |
| 8 | RELEASE-NOTES-v2.6.1.md | 本路线 | ⏳ |
| 9 | README.md 顶部版本表 + 当前架构表 | 本路线 | ⏳ |
| 10 | git tag v2.6.1 + push（**需用户确认**） | 本路线 | ⏳ |

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

- [ ] 子 change 1 闭环（Propose + Apply + Archive）
- [ ] 子 change 2 闭环（Propose + Apply + Archive）
- [ ] 子 change 3 闭环（Propose + Apply + Archive）
- [ ] 3 个子 change 的 spec.md 已 sync 到 openspec/specs/
- [ ] `docs/REVIEW-v261-bugfix-round.md` 写完
- [ ] `VERSION-ROADMAP.md` 加 §v2.6.1 章节 + §1 全景表加 1 行
- [ ] `README.md` 顶部版本表 + 当前架构表 同步
- [ ] `RELEASE-NOTES-v2.6.1.md` 写完（含 commit 序列 + 测试统计 + 真机示例）
- [ ] `git status` 干净
- [ ] `qa-backend` 全量 pytest 与 baseline 对比通过
- [ ] `qa-frontend` lint + build 通过
- [ ] 通知用户 review
- [ ] git tag v2.6.1 + push（**需用户确认**）
