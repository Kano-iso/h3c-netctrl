# v262-roadmap — Tasks

## 子 change 状态

| ID | 来源 | v2.6.2 状态 | 任务量 |
|---|---|---|---|
| [fix-backup-restore-support](../fix-backup-restore-support/tasks.md) | v2.6.1 STATUS.md | 🟢 主项（9 task 必做） | 9 commit + 测试 |
| add-auto-collect | v2.6.1 CANCELLED.md | ⚪ 悬置（按需重启） | 0 |

## fix-backup-restore-support — 9 task 总览

| # | Task | commit | 依赖 | 真机/单测 | 状态 |
|---|---|---|---|---|---|
| T1 | 后端 `check_restore_support(device)` probe | T1-commit | — | 单测 + 真机 | ⏳ |
| T2 | restore_async 端点预检 + 422 | T2-commit | T1 | 单测 + 真机 | ⏳ |
| T3 | `_restore_via_scp` 失败详细错误日志 | T3-commit | — | 单测 | ⏳ |
| T4 | 前端 toast 系统（taskStore 失败时弹） | T4-commit | — | lint + build | ⏳ |
| T5 | BackgroundTaskPanel "最近失败"高亮 | T5-commit | T4 | lint + build | ⏳ |
| T6 | device.status 加 `restore_unsupported` 字段 | T6-commit | T1 | 单测 | ⏳ |
| T7 | mock scp.put 抛 Channel closed 测试 | T7-commit | T1, T2, T4 | qa-backend | ⏳ |
| T8 | 真机 .177 + .5 双向验证 | T8-commit | T1, T2 | qa-backend + MCP 浏览器 | ⏳ |
| T9 | docs/ops-toolkit.md S6850 SCP 限制说明 | T9-commit | T1, T8 | — | ⏳ |

## 串行实施时序

```
T1 (probe 函数)
↓
T2 (端点预检)
↓                    ↓
T3 (错误日志)         T4 (toast 系统)
↓                    ↓
                   T5 (面板高亮)
↓
T6 (状态字段)
↓
T7 (mock 测试)
↓
T8 (真机双向验证)
↓
T9 (文档收尾)
```

**为什么 T3 和 T4 平行**：T3 是后端错误日志（不影响 API 行为），T4 是前端 toast 系统（独立新建组件），可交错做。

**为什么 T5 跟在 T4 后**：面板高亮是 toast 系统的视觉补充（红点 + 折叠态显示），T5 提交需要 T4 提交后做。

**为什么 T6 单独做**：device.status 字段改动涉及 schema + 多个路由（`/devices/{id}/status` / `/devices` list），T6 提交需要先收 T1 的 probe 结果。

## 每 Task 验收

详见 [fix-backup-restore-support/tasks.md](../fix-backup-restore-support/tasks.md) 每 task 详细描述。

## 闭环 checklist

Apply 阶段（每 Task 后）：
- [ ] `qa-backend` 单测全过（每次 T1/T2/T3/T6/T7 后跑）
- [ ] 涉及前端改动后 `qa-frontend` lint + build（T4/T5 后跑）

Archive 阶段：
- [ ] `qa-backend` 全量 pytest（与 245+ baseline 对比）
- [ ] `qa-frontend` lint + build + vitest + playwright
- [ ] `docs/REVIEW-v262-bugfix-round.md` 写（如 v2.6.1 反思有更新点）

发版前：
- [ ] RELEASE-NOTES-v2.6.2.md 写完
- [ ] VERSION-ROADMAP.md 加 §v2.6.2 详细 + §1 全景表加 1 行
- [ ] README.md 顶部版本表 + 当前架构表同步
- [ ] git tag v2.6.2 + push（需用户确认）
- [ ] 2 个 change archive 闭环（`git mv` 到 `archive/2026-07-08-*`）

## 状态

- 🟢 实施中（v2.6.2 闭环后起 v3.0）
