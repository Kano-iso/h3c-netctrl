# fix-vite-proxy-route — Tasks

> **Task 粒度规则**：1 Task = 1 commit
> **前置**：v2.6.1 fix-asset-collect-failure + fix-asset-stale-status + fix-asset-split-password-decrypt（已闭环）

## Apply 阶段

| # | 任务 | 涉及文件 | 验收 | 状态 |
|---|---|---|---|---|
| 1 | 改 vite.config.js proxy 配置：用 `configure` 钩子 + 正则精确分发 | `frontend/vite.config.js` | 长前缀路由到正确容器 | ✅ 843a302 |
| 2 | qa-frontend lint + build 验证 | - | 53 vitest + 42 playwright pass | ✅ |
| 3 | MCP 浏览器 6 端点 + 4 页面 smoke test | - | ops / interfaces / backup / CMDB 全过 | ✅ |
| 4 | qa-backend 全量回归 | - | 302 passed 无回归（47.85s） | ✅ |
| 5 | archive change | - | 已 mv → archive/2026-07-06-fix-vite-proxy-route/ | ✅ |
| 6 | v261-roadmap/tasks.md 标子 change 4 为 ✅ | - | 已改 | ✅ |
| 7 | 通知用户 review | - | 待用户确认 | ⏳ |

## Archive 阶段

- [ ] qa-frontend lint + build 通过
- [ ] qa-backend 302+ tests 全 PASS
- [ ] MCP 浏览器 8 个菜单 smoke test 通过
- [ ] spec.md 已 sync 到 openspec/specs/（如需要）
- [ ] `git mv` 完成
- [ ] 1 commit = 1 task（已满足）
- [ ] 通知用户 review

## 串行顺序

1 → 2 → 3 → 4 → 5 → 6 → 7（验证步骤不 commit，仅作 commit 前置条件）
