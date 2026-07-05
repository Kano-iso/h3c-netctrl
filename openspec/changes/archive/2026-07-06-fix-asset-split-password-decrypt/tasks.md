# fix-asset-split-password-decrypt — Tasks

> **Task 粒度规则**：1 Task = 1 commit
> **前置**：v2.6.1 fix-asset-collect-failure（已闭环）+ fix-asset-stale-status（已闭环）

## Apply 阶段

| # | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| 1 | 改 `refresh_asset` 用 `get_device_with_password` | `backend/app/routers/asset.py` | ✅ split 模式不再二次 decrypt；monolith 行为不变 |
| 2 | 加 3 个 password-decrypt 单元测试 | `backend/tests/test_asset_password_decrypt.py` | ✅ qa-backend 302 passed（含 monolith + split + 错误凭据 3 case）|
| 3 | 验证：本地 qa-backend 跑全量 pytest | - | ✅ 302 passed, 23 skipped（baseline 299 + 3 新增）|
| 4 | 真机验证：data 容器跑 POST /api/assets/device/1/refresh | - | ✅ .177 (id=7) → 200 online；.4 (id=4) → 200 online（.4 实际可达）|
| 5 | archive change：`git mv openspec/changes/fix-asset-split-password-decrypt → archive/2026-07-06-fix-asset-split-password-decrypt/` | - | ✅ 闭环 |
| 6 | 通知用户 review | - | ⏳ 等用户确认 |

## Archive 阶段

- [x] qa-backend 302+ tests 全 PASS
- [x] spec.md 已 sync 到 openspec/specs/asset-split-password-fix/spec.md
- [x] `git mv` 完成
- [x] 1 commit = 1 task（已满足）
- [x] 通知用户 review

