# add-auto-collect — Tasks（v2.6.1 拆细版）

> **Task 粒度规则**：1 Task = 1 commit
> **每步必须**：1 commit + 1 qa-backend 跑（如果改 backend）+ 1 报告给用户
> **卡壳 3 次立即停手**，回到 spec 对齐
> **前置依赖**：4 个 fix change 已闭环（fix-asset-stale-status / fix-asset-collect-failure / fix-asset-split-password-decrypt / fix-vite-proxy-route）

## Apply 阶段（9 个 task）

### Task 1：加 AUTO_COLLECT_* 配置项

- **文件**：
  - `backend/app/config.py`（加 3 个新字段）
  - `backend/.env.example`（加新配置）
- **改动**：
  ```python
  AUTO_COLLECT_ENABLED: bool = True
  AUTO_COLLECT_INTERVAL_MINUTES: int = 30
  AUTO_COLLECT_BATCH_SIZE: int = 3
  ```
- **commit**：`feat(config): 加 AUTO_COLLECT_* 配置项 (v2.6.1 add-auto-collect Task 1)`
- **验收**：
  - qa-backend 全量 302 passed 无回归
  - 配置可通过 env 覆盖
- **状态**：⏳

### Task 2：加 i18n key

- **文件**：`backend/app/i18n_keys.py`
- **改动**：加 4 个新 key
  ```python
  AUTO_COLLECT_STARTED = "log.auto_collect.started"
  AUTO_COLLECT_STOPPED = "log.auto_collect.stopped"
  AUTO_COLLECT_DEVICE_OK = "log.auto_collect.device_ok"
  AUTO_COLLECT_DEVICE_FAIL = "log.auto_collect.device_fail"
  AUTO_COLLECT_CYCLE_DONE = "log.auto_collect.cycle_done"
  ```
- **commit**：`feat(i18n): 加 AUTO_COLLECT_* log key (v2.6.1 add-auto-collect Task 2)`
- **验收**：
  - qa-backend 全量 302 passed 无回归
  - i18n_keys.py 加载通过
- **状态**：⏳

### Task 3：提取 _refresh_asset_for_device 纯业务函数

- **文件**：`backend/app/routers/asset.py`
- **改动**：从 `refresh_asset` HTTP endpoint 提取纯业务函数
  ```python
  def _refresh_asset_for_device(db: Session, device_id: int) -> dict:
      """返回 {success: bool, error: str, asset_status: str}"""
      # ... 核心业务逻辑（device + password → SSHExecutor → asset 落库）
  ```
- **HTTP endpoint 改为调它**（保持现有行为）
- **commit**：`refactor(backend): 提取 _refresh_asset_for_device 纯业务函数 (v2.6.1 add-auto-collect Task 3)`
- **验收**：
  - qa-backend 全量 302 passed 无回归
  - 现有 refresh_asset HTTP endpoint 行为不变（CMDB 采集按钮仍能用）
- **状态**：⏳

### Task 4：新建 AutoCollectScheduler 类

- **文件**：
  - `backend/app/services/__init__.py`（新建空文件）
  - `backend/app/services/auto_collect.py`（新建 AutoCollectScheduler 类）
- **改动**：
  ```python
  class AutoCollectScheduler:
      def __init__(self, db_factory, interval_minutes: int, batch_size: int):
          self.db_factory = db_factory
          self.interval = interval_minutes * 60
          self.batch_size = batch_size
          self._task = None
          self._stop = asyncio.Event()
      
      async def start(self):
          """启动后台循环任务"""
          self._stop.clear()
          self._task = asyncio.create_task(self._run_loop())
      
      async def stop(self):
          """停止后台循环任务"""
          self._stop.set()
          if self._task:
              self._task.cancel()
              try: await self._task
              except asyncio.CancelledError: pass
      
      async def _run_loop(self):
          while not self._stop.is_set():
              try:
                  await self._collect_cycle()
              except Exception as e:
                  logger.error(f"auto_collect 周期失败: {e}")
              await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
      
      async def _collect_cycle(self):
          """一轮采集：所有 device × batch_size 并发"""
          ...
      
      async def _collect_one(self, device_id: int) -> dict:
          """采集单台 device（调 _refresh_asset_for_device）"""
          ...
  ```
- **commit**：`feat(backend): 新建 AutoCollectScheduler 后台任务 (v2.6.1 add-auto-collect Task 4)`
- **验收**：
  - qa-backend 全量 302 passed 无回归
  - 单独 import 成功（无运行时错误）
- **状态**：⏳

### Task 5：data 容器集成

- **文件**：`backend/data_svc/main.py`
- **改动**：
  - 检测 `SERVICE_NAME == "data"` 才启动 scheduler
  - `on_startup` 创建 scheduler 实例 + 调 `start()`
  - `on_shutdown` 调 `stop()`
  - 优雅处理启动失败（log 错误，不阻塞容器启动）
- **commit**：`feat(backend): data 容器 on_startup 集成 AutoCollectScheduler (v2.6.1 add-auto-collect Task 5)`
- **验收**：
  - data 容器启动后 5s 内看到 `AUTO_COLLECT_STARTED` log
  - 1 分钟后看到 `AUTO_COLLECT_CYCLE_DONE` log
  - on_shutdown 看到 `AUTO_COLLECT_STOPPED` log
- **状态**：⏳

### Task 6：docker-compose.dev.yml 注入 env

- **文件**：`docker-compose.dev.yml`
- **改动**：data 容器 service 加 env 块
  ```yaml
  environment:
    AUTO_COLLECT_ENABLED: "true"
    AUTO_COLLECT_INTERVAL_MINUTES: "30"
    AUTO_COLLECT_BATCH_SIZE: "3"
  ```
- **commit**：`chore(docker): data 容器注入 AUTO_COLLECT_* env (v2.6.1 add-auto-collect Task 6)`
- **验收**：
  - data 容器重启后 env 注入成功
  - qa-backend 全量 302 passed 无回归
- **状态**：⏳

### Task 7：单元测试（5 case）

- **文件**：`backend/tests/test_auto_collect.py`（新建）
- **5 case**：
  1. scheduler start/stop 生命周期
  2. 间隔时间正确（mock asyncio.sleep 推进）
  3. 失败跳过（mock 1 台失败，本轮跳过）
  4. 并发限制（batch_size=3 时 10 台只 3 并发）
  5. AUTO_COLLECT_ENABLED=False 时 scheduler.run() 立即返回
- **commit**：`test(backend): 加 5 个 auto-collect 单元测试 (v2.6.1 add-auto-collect Task 7)`
- **验收**：
  - qa-backend 全量 307+ passed（302 + 5 新增）
  - 5 个 test case 全过
- **状态**：⏳

### Task 8：写 docs/AUTO-COLLECT.md

- **文件**：`docs/AUTO-COLLECT.md`（新建）
- **3 段**：
  - 配置（AUTO_COLLECT_* env 含义 + 默认值）
  - 调优（间隔 / 并发 / 失败处理）
  - 排错（scheduler 没启动 / 失败 / 性能问题）
- **commit**：`docs: 加 docs/AUTO-COLLECT.md 配置调优排错 (v2.6.1 add-auto-collect Task 8)`
- **验收**：
  - 文档可读，无技术错误
- **状态**：⏳

### Task 9：真机验证 + archive

- **步骤**：
  1. 重启 data 容器（确保 .env 注入 + scheduler 启动）
  2. 30s 后看 logs/data.log 出现 `AUTO_COLLECT_STARTED`
  3. 等 1 轮（30s with interval=1 min for test）看 `AUTO_COLLECT_CYCLE_DONE`
  4. curl `GET /api/assets/device/1` 看 status=online + updated_at=now
  5. curl `GET /api/assets/device/4` 看 status=offline（如果不可达）
  6. archive change：`mv openspec/changes/add-auto-collect → archive/2026-07-06-add-auto-collect/`
  7. sync spec.md 到 `openspec/specs/auto-collect-scheduler/spec.md`
  8. v261-roadmap/tasks.md 标子 change 5 为 ✅
- **commit**：`chore(openspec): add-auto-collect archive 闭环 (Task 9)`
- **验收**：
  - 真机 .177 refresh 成功
  - 真机 .4 refresh 失败但 scheduler 不卡住
  - qa-backend 307+ passed 无回归
- **状态**：⏳

## 卡壳 / 异常处理

- **3 次失败立即停手**：每个 task 跑 qa-backend 失败 3 次后立刻回到 proposal 重新对齐
- **脏代码零容忍**：不允许用 DEBUG 注释关掉 scheduler / 跳过测试 / 屏蔽报错
- **每步报告**：每个 commit 后告诉用户：
  - commit hash
  - qa 数字（passed / failed / skipped）
  - 真机状态（如有）
  - 下一步计划

## 串行顺序

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
