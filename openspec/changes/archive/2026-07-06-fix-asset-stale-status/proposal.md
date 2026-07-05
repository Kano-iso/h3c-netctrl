# fix-asset-stale-status — Proposal

## Why

v2.6.0 i18n 发版后 dashboard 显示 online=7 但所有设备 5~13 天未采集。根因是 `Asset.status` 是"采集时刻的状态快照"，**没有"过期降级"机制**。`openspec/specs/asset-status-fix/spec.md` §"已有错误数据不主动修复" 当时刻意不主动修复（避免改用户数据），结果 v2.6.0 上线后被证实治标不治本——只要用户不点采集按钮，错误状态永远不会被纠正。

现场数据（`docker exec h3c-data` 查 `data.db`）：

| asset_id | device_id | status | updated_at | 距今 |
|---|---|---|---|---|
| 1 | 2 | online | 2026-06-28 16:58:24 | 7.2 天 |
| 2 | 3 | online | 2026-06-22 13:22:29 | 13.3 天 |
| 3 | 4 | online | 2026-06-22 13:22:36 | 13.3 天 |
| 4 | 5 | online | 2026-06-23 16:34:52 | 12.2 天 |
| 5 | 6 | online | 2026-06-28 16:58:25 | 7.2 天 |
| 6 | 1 | online | 2026-06-23 19:57:49 | 12.1 天 |
| 7 | 7 | online | 2026-06-30 17:49:23 | 5.2 天 |

**全部 7 条 status='online'，最后更新 5~13 天前**。

## What Changes

- **后端新增 staleness 阈值配置**：`ASSET_STALE_HOURS`（默认 1h）+ `ASSET_STALE_ENABLED`（默认 True，可关闭）
- **dashboard 读取时按阈值过滤**：`online = status='online' AND updated_at >= now - 1h`；过期 asset 不算 online，也不算 offline，单独计 "stale"
- **data 容器启动时主动降级**：`on_startup` 跑一次"将 `updated_at > threshold` 的 `status='online'` 改为 `status='offline'`"；**幂等可重入**（无 matching 行 = noop）
- **采集时 `updated_at = now`**：现有 `refresh_asset` 已 commit，自然触发 `onupdate=func.now()`，无需改
- **/internal/assets 返回 `is_stale` 字段**：方便前端 / 其他容器判断
- **spec 修订**：`asset-status-fix/spec.md` §"已有错误数据不主动修复" 改为 §"过期资产自动降级"

## 设计决策

### 决策 1：阈值放在后端配置，不放前端

- **理由**：资产陈旧是后端数据模型问题，前端只读不存；放后端确保 3 容器模式下行为一致
- **环境变量**：`ASSET_STALE_HOURS=24`（默认）+ `ASSET_STALE_ENABLED=True`（默认）
- **关闭方式**：`ASSET_STALE_ENABLED=False` → 启动时不跑降级，dashboard 不过滤（兼容历史数据场景）

### 决策 2：降级时机 = 启动时写回 DB + dashboard 读取时算

- **写回 DB**（启动时）：data 容器 `on_startup` 跑一次 `UPDATE assets SET status='offline' WHERE status='online' AND updated_at < now - threshold`
  - 优点：Devices.vue 等其他视图也立即显示离线，无需各自加 staleness 逻辑
  - 缺点：写一次 DB，但幂等无副作用
- **读取时算**（dashboard）：`_get_asset_stats` 内联 `is_stale = (now - updated_at) > threshold`，不写回
  - 理由：dashboard 实时算避免"启动后才看得到效果"
- **不实时降级**（用户点击 / 每次 API 调用）：避免 DB 写压力；启动时一次够

### 决策 3：阈值默认 1h

- 依据：用户决定 1h（较严）。配合 v2.6.1 add-auto-collect 的 30 分钟自动采集，留 30 分钟缓冲
- 调试场景：用户想立刻看效果，临时设 `ASSET_STALE_HOURS=0.01`（36 秒）→ 立即降级

### 决策 4：不动 dashboard 4 象限

- dashboard KPI 仍保持 "在管 / 在线 / 离线" 3 个（不动 UI 文案 / 4 象限）
- 改动范围最小：只改 `_get_asset_stats` 的 SQL 过滤条件
- "stale" 概念本期不暴露给前端（避免 v2.6.1 改动面扩大）

### 决策 5：3 容器启动顺序

- ctrl / config 容器不需要跑降级（它们没有 assets 表）
- 只在 **data 容器** `on_startup` 跑降级
- 检测方式：`SERVICE_NAME=data` 时执行

## Capabilities

### New Capabilities

- `asset-staleness-auto-degrade`: assets 表 status 主动降级（按 updated_at 阈值）+ dashboard 读取时按阈值过滤

### Modified Capabilities

- `asset-status-fix`: §"已有错误数据不主动修复" 改为 §"过期资产自动降级"（与新 capability 一致）

## Impact

- **代码**：
  - `backend/app/config.py`（`ASSET_STALE_HOURS` + `ASSET_STALE_ENABLED`）
  - `backend/app/routers/dashboard.py`（`_get_asset_stats` 改 SQL 过滤 + 加 `stale_count` 字段）
  - `backend/app/routers/asset.py`（`refresh_asset` 启动时跑降级 — 实际放 data 容器的 on_startup）
  - `backend/app/main.py`（`on_startup` 增加降级调用 — 但只在 SERVICE_NAME=data 时执行）
  - `backend/app/routers/data_internal.py`（`/internal/assets` 返回加 `is_stale` 字段）
  - `backend/tests/test_asset_staleness.py`（新建 5 case）
- **API**：
  - `GET /api/dashboard`：device_stats 字段加 `stale`（暂不暴露给前端，但接口返回了方便 debug）
  - `GET /internal/assets`：每个 asset dict 加 `is_stale: bool` 字段
- **配置**：
  - `.env.example` 加 `ASSET_STALE_HOURS=24` + `ASSET_STALE_ENABLED=True`
  - `docker-compose.dev.yml` data 容器 env 注入
- **文档**：
  - `openspec/specs/asset-status-fix/spec.md` 修订 §"已有错误数据不主动修复" → §"过期资产自动降级"
  - `openspec/specs/asset-staleness-auto-degrade/spec.md`（新建）
  - `VERSION-ROADMAP.md` §v2.6.1
  - `RELEASE-NOTES-v2.6.1.md`
- **测试 baseline**：233 → 238+ passed（+5 staleness 测试）
- **用户体验**：
  - 修复前：dashboard online=7 永远不变
  - 修复后：dashboard online=0（因为全部陈旧），离线 7（启动时降级）— 跟用户描述的"应该的状态"一致

## Non-Goals

- 不做"自动定时采集"（避免引入新 cron / scheduler）
- 不动 dashboard UI（4 象限 KPI 留 v2.7+ 评估）
- 不动 Device / CMDB / Asset 等其他路由的 staleness 行为（只 dashboard 读时过滤；其他路由等启动时降级后自动正确）
- 不动 ops-toolkit 脚本
- 不改 SSHExecutor 行为

## QA 验证计划

详见 [v261-roadmap/proposal.md §QA 验证计划](../v261-roadmap/proposal.md#qa-验证计划) 公共部分。

本 change 专属验证项：

### 2.1 后端单元 / 集成（qa-backend 容器跑）

- [ ] staleness 阈值过滤：asset.updated_at > 24h → 不算 online
- [ ] staleness 阈值过滤：asset.updated_at <= 24h → 算 online
- [ ] 启动时自动降级：mock 一条 25h 前的 online asset，restart data 容器，验证 status 变 offline
- [ ] `ASSET_STALE_HOURS=0.01` 立即降级（边界）
- [ ] `ASSET_STALE_ENABLED=False` 不降级（兼容性）
- [ ] `GET /internal/assets` 返回 `is_stale: true/false` 正确
- [ ] dashboard 返 `device_stats.stale` 字段正确

### 2.2 前端 UI 验证

- [ ] `npm run build` 编译过
- [ ] Dashboard 4 KPI 数字 = 后端返回值（可能 online=0，offline=7）
- [ ] i18n 中英文文案正确

### 2.3 真机集成（pytest --integration 跑 .177 / .4 / .5）

- [ ] .177 触发 refresh → asset.status=online + updated_at=now（30s 内）→ dashboard 算 online
- [ ] .4 触发 refresh（已知 SSH 失败）→ asset.status=offline → dashboard 算 offline
- [ ] 24h 阈值测试：手动 SQL `UPDATE assets SET updated_at = datetime('now', '-25 hours') WHERE device_id=X` → restart data 容器 → 验证 status 变 offline
- [ ] **最后必须 restore_original_state**（n → n+1 → n）
