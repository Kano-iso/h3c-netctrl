# fix-asset-collect-failure — Tasks

> **Task 粒度规则**：1 Task = 1 commit

## Apply 阶段

| # | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| 1 | 后端 asset router 改 path：`/devices/{id}/asset/*` → `/assets/device/{id}/*` | `backend/app/routers/asset.py` | curl `/api/assets/device/1` 200，curl `/api/devices/1/asset` 404 |
| 2 | 前端 `assetApi` 改 path | `frontend/src/api/index.js` | build 过 + 浏览器点"采集"按钮真发到新 path |
| 3 | 加 i18n key `asset.route.*` | `backend/app/i18n_keys.py` + `frontend/src/i18n/zh-CN.js` + `en-US.js` | 错误信息可读；fallback 中文 |
| 4 | 同步 `test_smoke.py` / `test_asset_staleness.py` path | `backend/tests/test_*.py` | qa-backend pytest 全过 |
| 5 | 同步前端 vitest / playwright 测试 URL | `frontend/src/__tests__/*.spec.js` + `frontend/tests/e2e/*.spec.js` | qa-frontend 全过 |
| 6 | 修 `RELEASE-NOTES-v2.6.1.md` 标注 BREAKING | `RELEASE-NOTES-v2.6.1.md` | 标注 BREAKING + 给出旧→新 path 对照表 |
| 7 | qa-backend + qa-frontend + 真机 .177/.4 验证 | - | 全过；restore_original_state |
| 8 | archive change：`mv openspec/changes/fix-asset-collect-failure → archive/2026-07-06-fix-asset-collect-failure/` | - | 闭环；spec 已 sync |

## Archive 阶段

- [ ] qa-backend 240+ tests 全 PASS
- [ ] qa-frontend lint + build + vitest + playwright 全过
- [ ] 真机验证：CMDB 采集按钮真能采（手动 + 真机）
- [ ] spec.md 已 sync 到 openspec/specs/
- [ ] `mv` 完成（用 plain mv + git add，change 目录未跟踪）
- [ ] 1 commit = 1 task（已满足）
- [ ] 通知用户 review
