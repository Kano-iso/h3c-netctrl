# add-auto-collect — Proposal (v2.6.1 拆细重做版)

## Why

v2.6.0 i18n 闭环后用户希望增加"自动采集"机制——data 容器后台 asyncio 任务，每 30 分钟自动遍历所有 device 触发 refresh_asset，保持资产数据新鲜。

**背景依赖**：4 个前置 bug fix change 已闭环（v2.6.1 fix-asset-stale-status / fix-asset-collect-failure / fix-asset-split-password-decrypt / fix-vite-proxy-route）——本次自动采集建立在这些 fix 之上。

## What Changes

- **后端**：
  - `backend/app/config.py` 加 3 个新配置项（AUTO_COLLECT_ENABLED / AUTO_COLLECT_INTERVAL_MINUTES / AUTO_COLLECT_BATCH_SIZE）
  - `backend/app/services/auto_collect.py` 新建 AutoCollectScheduler 类
  - `backend/app/services/__init__.py` 新建（空文件）
  - `backend/app/i18n_keys.py` 加 4 个 log key
  - `backend/app/routers/asset.py` 提取 `_refresh_asset_for_device` 纯业务函数
  - `backend/data_svc/main.py` 加 scheduler 生命周期管理（on_startup 启动 / on_shutdown 停止）
  - `backend/.env.example` 加新配置
- **docker**：`docker-compose.dev.yml` data 容器 env 块加 3 个 AUTO_COLLECT_* env
- **测试**：`backend/tests/test_auto_collect.py` 新建（5 unit + 2 integration）
- **文档**：`docs/AUTO-COLLECT.md` 新建（配置 / 调优 / 排错）
- **前端**：无（v2.6.0 i18n 已闭环，本期不展示 auto-collect 状态）

## 设计决策

### 决策 1：scheduler 写在 data 容器（不是 monolith）

- **理由**：auto-collect 的业务对象是 asset，归 data 容器
- **优势**：避免在 monolith 容器引入后台任务（影响启动时间）
- **取舍**：ctrl 容器不跑（device CRUD 不需要 scheduler），config 容器不跑（执行命令按需触发）

### 决策 2：5 字段配置 + 1 个 enabled 开关

- **决策**：3 个新配置项，不暴露到前端（运维内部配置）
- **默认值**：`enabled=true`, `interval=30min`, `batch_size=3`
- **理由**：30min 间隔 + 3 并发 = 平均 1 设备 10min 内被采集（足够保持新鲜度，且不会压垮 .177 max-session=7 限制）
- **可调优**：`batch_size=1` 安全模式（单并发），`interval=5` 密集模式

### 决策 3：失败跳过 1 轮 + 不重试

- **理由**：避免某台设备持续失败导致 scheduler 卡住
- **实现**：每轮失败的 device 跳过，下轮 30min 后再试
- **取舍**：极致稳定性 > 立即重试速度

### 决策 4：scheduler 启动失败不阻塞容器

- **理由**：data 容器启动必须快，前端"采集"按钮仍可手动触发
- **实现**：try/except 包裹 scheduler 启动，失败只记 log
- **降级**：scheduler 挂了 → 等下次 on_startup 重启时恢复

## Apply 拆细（关键：每个 task 1 commit + 1 qa 验证 + 1 报告）

**v2.6.1 拆细原则**：v2.6.0 subagent 跑得太快（9 commit 一次过完），本次拆成 9 个独立 commit，每步：
- 1 commit
- 1 qa-backend 跑（如果改 backend）
- 1 真机验证（如果涉及容器）
- 1 报告数字给用户

详见 [tasks.md](tasks.md)。

## 串行顺序

1. → 加 config（基础）
2. → 加 i18n key
3. → 提取 _refresh_asset_for_device
4. → 新建 AutoCollectScheduler 类（独立业务）
5. → data 容器集成（生命周期）
6. → docker-compose.dev.yml 注入
7. → 单元测试
8. → 文档
9. → 真机验证 + archive

## Capabilities

### Modified Capabilities

- 无（新增功能，不改 spec 语义）

## Impact

- **代码**：
  - `backend/app/config.py`（+3 字段）
  - `backend/app/services/auto_collect.py`（新建）
  - `backend/app/services/__init__.py`（新建）
  - `backend/app/i18n_keys.py`（+4 log key）
  - `backend/app/routers/asset.py`（提取 _refresh_asset_for_device）
  - `backend/data_svc/main.py`（+scheduler lifecycle）
  - `backend/.env.example`（+3 配置）
  - `docker-compose.dev.yml`（+3 env）
  - `backend/tests/test_auto_collect.py`（新建 5 unit + 2 integration）
  - `docs/AUTO-COLLECT.md`（新建）
- **API**：无破坏性变更（新增后台功能）
- **配置**：3 个新 env（默认值开箱即用）
- **测试 baseline**：302 → 307+ passed（+5 unit）
- **用户体验**：
  - 修复前：资产数据需手动采集（用户点 CMDB 页面"采集"按钮）
  - 修复后：30 分钟自动采集，仪表盘状态自动保持新鲜

## Non-Goals

- 不做定时任务可视化（v2.6.x 不展示，下次再说）
- 不做采集失败告警（log 记录足够，告警推 v2.7+）
- 不做主动告警 email（保持当前简单）
- 不改 refresh_asset 业务逻辑（v2.6.1 fix-asset-split-password-decrypt 已闭环）
- 不重写 ssh_executor（已用 paramiko，OK）

## QA 验证计划

### 单元测试（5 case）

1. scheduler start/stop 生命周期
2. 间隔时间正确（mock 时间推进）
3. 失败跳过（mock 1 台失败）
4. 并发限制（batch_size=3 时 10 台只 3 并发）
5. AUTO_COLLECT_ENABLED=False 不启动

### 集成测试（2 case）

1. 真机 .177 自动 refresh 成功（data 容器 30min 内）
2. 真机 .4 失败后跳过下轮（避免卡住）

### qa-backend 全量

- baseline 302 + 5 新增 = 307+ passed
- 无回归

### 真机（split 模式 data 容器）

- 启动后 30s 看到 auto_collect log
- 1 台设备 refresh 成功 + asset.status=online
- 1 台设备 refresh 失败 + asset.status=offline
- scheduler 启动失败不阻塞容器启动
