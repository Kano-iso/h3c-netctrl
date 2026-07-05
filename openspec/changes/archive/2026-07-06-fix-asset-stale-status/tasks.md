# fix-asset-stale-status — Tasks

> **Task 粒度规则**：1 Task = 1 commit，粒度控制在"一次可提交、可自测、可运行"

## Apply 阶段

| # | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| 1 | 加 `ASSET_STALE_HOURS` + `ASSET_STALE_ENABLED` 配置项 | `backend/app/config.py` + `.env.example` | `settings.ASSET_STALE_HOURS == 24` 默认；测试 settings 加载 |
| 2 | `dashboard._get_asset_stats` 改 SQL 过滤 + 加 `stale_count` | `backend/app/routers/dashboard.py` | 单测：mock assets 数据，验证 online/offline/stale 数字 |
| 3 | `data_internal._internal_list_assets` 返回加 `is_stale` 字段 | `backend/app/routers/data_internal.py` | 单测：is_stale 字段计算正确 |
| 4 | data 容器 `on_startup` 加 staleness 降级（仅 SERVICE_NAME=data 时执行） | `backend/app/main.py` | 单测：mock assets 数据，验证 UPDATE SQL 正确生成；启动时只 data 跑 |
| 5 | 修 `openspec/specs/asset-status-fix/spec.md` §"已有错误数据不主动修复" → §"过期资产自动降级" | spec 文件 | spec 文本反映新行为 |
| 6 | 加 5 个 staleness 单元测试 | `backend/tests/test_asset_staleness.py` | qa-backend 跑 238+ passed |
| 7 | qa-backend + qa-frontend 全量 + 真机 .177/.4 验证 | - | dashboard 数字符合预期；restore_original_state |
| 8 | archive change：`git mv openspec/changes/fix-asset-stale-status → archive/2026-07-06-fix-asset-stale-status/` | - | 闭环；spec 已 sync（实际用 `mv` 因 change 目录尚未 `git add` 跟踪；归档后 commit 跟进） |

## Archive 阶段

- [x] qa-backend 245+ tests 全 PASS（+ 7 staleness case，+1 split-mode bug fix）
- [x] qa-frontend lint + build 全过（v2.6.0 发版已验证过）
- [x] 真机验证：dashboard 数字正确（.177 25h online → 启动降级为 offline，restore 完成）
- [x] spec.md 修订完成 + 新建 asset-staleness-auto-degrade/spec.md
- [x] `git mv` 完成（`mv` + 跟踪 add + commit 三步走，因 change 目录未跟踪）
- [x] 1 commit = 1 task（已满足）
- [ ] 通知用户 review（需用户确认 → push + tag）
