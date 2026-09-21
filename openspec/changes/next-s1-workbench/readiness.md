# NEXT S1 Workbench Readiness

## Delivered

- VPC 业务范围、EVPN Leaf、端口绑定、终端观测和操作过程统一到一个工作台。
- 终端接入固定为服务端预览后执行；存在 blocker 时前端禁止确认。
- 持久化 operation 可从页面重新打开，并按状态提供验证、对账或操作级撤回。
- 旧版租户/VPC 创建与 Fabric 下发/撤回保留在次级资源工具中。
- 全局导航补充窄屏收敛，390px 页面无横向溢出。
- ATLAS、PULSE、STRATA 共享当前 VPC 和选中对象：分别回答业务覆盖、操作过程和跨层依赖。
- PULSE 将后端 operation/attempt/unit/evidence 译为用户可读的意图、范围、安全边界和执行生命线，不再只显示一个状态值。
- STRATA 分开显示业务目标、逻辑网络与设备承载，并明确目标、设备观测与系统推断不是同一种事实。
- STRATA 的每台 EVPN Leaf 可按需展开设备证据轨迹；历史点明确使用当前目标配置作比较基准，支持下钻查看采集时间、采集结论与关键维度，不因切换视图自动采集设备。
- 5174 隔离预览显示非生产提示；预览仍不连接生产数据库或设备。
- PULSE 已消费后端 S1-026 explanation 契约；执行记录、设备观测、系统推断和未决状态分别展示，不再依赖 mock 专属 summary。
- S1-027 真实应用栈隔离联调：独立镜像 + 隔离 compose + seed/边界 fake/launcher + 独立 Playwright spec（`tests/stack-qa/`），浏览器驱动真实 FastAPI + 隔离 SQLite + 真实 vite dev 完成接入故事，无 page.route mock、无真机 I/O。
- S1-028 整改（可复现性 + 硬隔离）：`qa/Dockerfile.stack-qa` 改 FROM **公开固定基础镜像 node:20-alpine** 独立构建（apk python3/venv/系统 chromium；前端依赖走仓库锁文件 `npm ci`，失败即构建失败、删除 `|| true` 吞错，不依赖任何本项目预构建镜像）；compose 运行容器 **`network_mode: none`**（构建期联网下载公开依赖，运行期无外部网络，FastAPI/Vite/Chromium 全部经 loopback 通信）。
- S1-027 契约修复（后端，随 workbench 联调暴露）：`mode='l2'` 请求此前会被后端 422；现 schema 放行 + `plan_port_bind` 归一化为 auto，并加回归测试。
- S1-027 迁移契约修复（后端，随联调暴露）：`alembic upgrade head` 空库此前在 003 失败；001 现幂等补建 devices/logs 基表，全新库可完整升级。

## Verification

- `eslint`: passed
- `vue-tsc --noEmit`: passed
- production build: passed
- component tests: 68 passed（其中 NEXT 工作台 11 条，含证据轨迹按需加载与刷新后重载）
- Playwright full baseline: 46 passed（含 STRATA 证据轨迹）；NEXT focused suite 与桌面/390px 实图复核通过；real application-stack suite (`tests/stack-qa`): 2 passed，连续 2 次独立容器运行均通过（接入故事 + 诚实 unknown/ambiguous）
- 真实栈通道：seed → uvicorn（隔离 SQLite，alembic 全链迁移）→ vite dev（core 模式 → 真实后端）→ Playwright 2 passed → device-io.log 断言 BOUNDARY_OK（21 事件全 fake，netconf 目标均为 TEST-NET 合成地址，无真实设备 I/O）；端口占用明确失败（exit 9），trap 统一清理进程与 /tmp/stack-qa
- S1-028 验证：移除 `next-s1-backend-qa-frontend:latest` 后 stack 镜像从 node:20-alpine 独立构建成功；`docker compose config` 显示运行服务 `network_mode: none`、无 env_file、无 docker.sock、无生产挂载；完整 stack QA 断网（无外部网络）下一次运行 = 2 passed + BOUNDARY_OK + STACK_QA_OK
- 后端回归（qa-backend）：`test_sdn_explanation.py + test_sdn_access_api.py + test_sdn_migration.py` = 46 passed（含 S1-027 新增 mode-l2 与空库 bootstrap 回归）；全量 `tests/` 无回归
- `openspec validate --strict next-s1-workbench`: passed
- Device I/O: not performed（全部为边界 fake，launcher 事后断言）

## Pending

- 当前已形成更有辨识度的展示节点；仍等待用户确认后再进入 OpenSpec archive 或主分支集成。5174 已按真实接口契约展示，但模拟环境不替代生产数据库联调——S1-027 的真实应用栈隔离通道已补齐该联调证据（合成数据，仍不连生产数据库/设备）。
