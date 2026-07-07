# v2.6.1 bug 修复轮次 — Roadmap

## Why

v2.6.0 i18n 发版后用户回归发现 **2 个遗留 bug**，均与"资产管理（asset）"路径相关：

1. **Dashboard online=7 数据陈旧**（用户描述："明明没采集 + 状态不在线，dashboard 仍显示 7 在线"）
   - **根因**：`Asset.status` 是"采集时刻的状态快照"，没有"过期降级"机制
   - **现场证据**：`data.db` 7 条 assets 全部 `status='online'`，`updated_at` 距今 5~13 天
   - **触发路径**：`dashboard._get_asset_stats` → `internal_api.get_assets()` → 拿 7 条 online → 统计 online=7
   - **设计漏洞**：`openspec/specs/asset-status-fix/spec.md` §"已有错误数据不主动修复" 当时为了"不改用户数据"刻意不主动修复，结果 v2.6.0 上线后这个决定被证实**治标不治本**——只要用户不点采集按钮，错误状态永远不会被纠正

2. **采集不采集会失败**（用户描述："也不知道为什么采集不采集会失败"）
   - **初步线索**：`logs/ctrl.log` 没有相关 `asset_refresh` 记录
   - **可能原因**（按概率排序）：① SSH 凭据过期 / 加密失败 ② 设备不可达（用户场景 .4/.5/.6/.177 真机） ③ 3 容器间 internal_api 调用失败 ④ front-end 请求未真正发出
   - **未复现**：需要前端 Devices.vue / CMDB.vue 点击"采集"按钮 + 看网络响应 + 看后端 logs/ctrl.log + ops-toolkit paramiko-batch-exec 复现

**驱动**：v2.6.0 archive 时 `qa-backend` 全量 pytest + `qa-frontend` lint+build 都过了（baseline 233 passed），但 pytest 测的是**代码逻辑**（try/except 分支、调用关系），根本不覆盖"data.db 里有 5~13 天前的老 online 数据"这种**数据陈旧**场景。**QA 套件不覆盖"线上数据陈旧"，所以没发现**。

## v2.6.0 复盘记录

> 本段为 fix-asset-stale-status 验证时回看 v2.6.0 archive 数据补的复盘（不动 archive/2026-07-06-v26-i18n/tasks.md，保留在路线文档里）

v2.6.0 archive 时（commit `9db780e` / `db6ff0a` 之前）`qa-backend` 实际 baseline 291 passed（不是当时记录里的 275+），`qa-frontend` 实际 lint + build + 53 vitest + 42 playwright 全过（不是 38+ vitest / 42+ playwright）。v2.6.0 archive 后用户立刻发现 dashboard online=7 陈旧数据 bug，证明 QA 套件覆盖度不足以替代真实场景验证。

**反思**：以后发版 archive 前必须做"线上数据 sanity check"（curl 真实 endpoints 看返回是否符合业务预期），不只是 qa-backend / qa-frontend 容器自动化测试。

本次起 v2.6.1 集中修 2 个 bug + 加 1 个新能力（自动采集），附带 review 报告反思 QA 套件盲区。

## What Changes

- **fix-asset-stale-status**：data 容器 Asset 表增加"主动降级"机制——上次采集超过 N 小时（默认 1h，可配）→ 自动判 offline；dashboard 读取时按"updated_at 阈值"过滤，过期数据不计入 online 统计
- **add-auto-collect**：data 容器后台 asyncio 任务，每 30 分钟自动遍历所有 device 触发 refresh_asset，配合 1h staleness 阈值保持 asset 数据新鲜
- **fix-asset-collect-failure**：定位并修复采集链路（设备→data 容器）失败原因；至少做到"采集失败时 error 信息准确可读"，避免"静默失败"现象
- **review 报告**：v2.6.0 review——QA 套件盲区 + 后续如何补"数据陈旧 / 业务时间敏感"场景测试

## Capabilities

### New Capabilities

- `asset-staleness-auto-degrade`: assets 表 status 主动降级（按 updated_at 阈值）+ dashboard 读取时按阈值过滤
- `auto-collect-scheduler`: data 容器后台 asyncio 任务，间隔自动采集所有 device 资产

### Modified Capabilities

- `asset-status-fix`: §"已有错误数据不主动修复" 改为 §"过期资产自动降级"（与新 capability 一致）

## Impact

- **代码**：
  - `backend/app/models.py`（Asset 加 staleness_threshold 字段或配置）
  - `backend/app/config.py`（`ASSET_STALE_HOURS` 默认 24）
  - `backend/app/routers/asset.py`（refresh 时更新 `last_check_at`；启动时跑一次降级）
  - `backend/app/routers/dashboard.py`（`_get_asset_stats` 按 `updated_at` 阈值过滤，过期 asset 不算 online）
  - `backend/app/routers/data_internal.py`（`/internal/assets` 返回时标注 `is_stale`）
  - `backend/app/routers/asset_collect.py`（新增或加在 asset.py — 排查采集失败链路）
  - `backend/tests/`（+ 5 staleness 测试 + 3 collect-failure 测试）
- **API**：
  - `GET /api/dashboard`：device_stats 字段不变（保持兼容），但 online 数字按阈值过滤
  - `GET /internal/assets`：每个 asset dict 加 `is_stale: bool` 字段
- **配置**：`ASSET_STALE_HOURS`（默认 24h），`ASSET_STALE_ENABLED`（默认 True，调试用）
- **文档**：
  - `docs/REVIEW-v261-bugfix-round.md`（新建，QA 套件盲区反思）
  - `VERSION-ROADMAP.md` §v2.6.1 章节 + §1 全景表加 1 行
  - `RELEASE-NOTES-v2.6.1.md`（新建）
  - `README.md` 顶部版本表
- **测试 baseline**：233 → 预计 245+ passed（+5 staleness + 3 collect + 4 review 反思）
- **用户体验**：
  - 修复前：dashboard 永远显示陈旧 online=7
  - 修复后：dashboard 按"最近 24h 是否采集过"判定 online，过期设备正确归 offline

## Non-Goals

- 不做"自动定时采集"（避免引入新 cron / scheduler，保留手动触发）
- 不做"告警 / 通知"（监控是 v3.0+ monitor 子项目）
- 不动 dashboard UI 4 象限（"在管/在线/离线/未采集" 留 v2.7+ 评估，避免本次 bug 修复影响范围扩大）
- 不动 ops-toolkit 脚本（CLI 不受影响）
- 不重写 asset refresh 业务逻辑（只在现有 `refresh_asset` 流程加 staleness 时间戳更新）

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | `GET /api/dashboard` | `backend/app/routers/dashboard.py` |
| 后端 API | `GET /internal/assets` | `backend/app/routers/data_internal.py` |
| 后端 API | `POST /api/devices/{id}/asset/refresh` | `backend/app/routers/asset.py` |
| 前端 UI | Dashboard.vue 4 个 KPI 卡片 | `frontend/src/views/Dashboard.vue` |
| 配置 | `ASSET_STALE_HOURS` 环境变量 | `backend/app/config.py` |
| 真实设备 | 192.168.100.177 (Test-Switch-177) | - |
| 真实设备 | 192.168.100.4/.5 (Leaf-03/04) | - |

### 2. QA 验证项

#### 2.1 后端 API 单元 / 集成（qa-backend 容器跑）

- [ ] staleness 阈值过滤逻辑：asset.updated_at > 24h → 不算 online
- [ ] staleness 阈值过滤逻辑：asset.updated_at <= 24h → 算 online
- [ ] 启动时自动降级：mock 一条 25h 前的 online asset，restart data 容器，验证 status 变 offline
- [ ] `ASSET_STALE_HOURS=0` 关闭降级（兼容性测试）
- [ ] `GET /internal/assets` 返回 `is_stale` 字段正确
- [ ] collect-failure：错误信息准确（mock SSH 失败，验证 error_key + fallback）
- [ ] 中文错误信息（"采集失败: SSH 不可达" 而非裸抛技术异常）

#### 2.2 前端 UI 验证（qa-frontend 容器跑 vite build + 人工浏览器验证）

- [ ] `npm run build` 编译过
- [ ] Dashboard 4 个 KPI 数字与后端一致
- [ ] i18n 中英文下文案正确

#### 2.3 真机集成（pytest --integration 跑 192.168.100.4/.5/.177）

- [ ] 设备 .177 触发 refresh → 验证 asset.status=online + updated_at=now
- [ ] 设备 .4 触发 refresh（已知 SSH 失败）→ 验证 asset.status=offline + 错误信息可读
- [ ] 24h 阈值测试：手动改 asset.updated_at → 24h 前，restart data 容器 → 验证 status 自动降级
- [ ] **最后必须 restore_original_state**（n → n+1 → n）

#### 2.4 回归

- [ ] qa-backend 跑 245+ tests 全 PASS
- [ ] 不破坏 v2.6.0 i18n 任何功能
- [ ] 不破坏 backup / vlan / interface / cmdb 等现有路由
- [ ] qa-frontend lint + build 全过

### 3. 跑法

```bash
# unit + smoke（CI 必跑，秒级）
docker compose -f docker-compose.dev.yml --profile qa up qa-backend

# 真机集成（按需）
docker exec h3c-data pytest tests/ -m integration --integration -v
```

### 4. 子 change 关联

| 子 change | 状态 | 关联 spec |
|---|---|---|
| `fix-asset-stale-status` | ✅ 已闭环（8 commits） | `asset-staleness-auto-degrade` + 修改 `asset-status-fix` |
| `fix-asset-collect-failure` | ✅ 已闭环（8 commits） | `asset-route-split-fix` |
| `fix-asset-split-password-decrypt` | ✅ 已闭环（3 commits） | `asset-split-password-fix` |
| `fix-vite-proxy-route` | ✅ 已闭环（1 commit） | `vite-proxy-route-fix` |
| `add-auto-collect` | ⏳ Propose 完，Apply 待拆细重做 | `auto-collect-scheduler` |
| `docs/REVIEW-v261-bugfix-round.md` | ⏳ 计划 | `review-report-process`（继承） |
