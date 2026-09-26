# S1-027/S1-028 + S2-018 真实应用栈隔离联调通道（qa/）

浏览器驱动【真实 FastAPI + 隔离 SQLite + 真实 vite dev】完成 NEXT 工作台接入故事、
S2 用户故事验收（覆盖范围、范围例外、可行动关注队列）与 S3 GUARD 保障验收（手动、
策略与业务事件历史），设备执行/采集仅在进程内以边界 fake 替代，并事后断言
`device-io.log` 证明无真实设备 I/O。
默认不连任何真实设备；不连生产 DB、不读 `.env`、不挂 docker.sock、不碰 5174 演示环境。

S1-028 整改：镜像从**公开固定基础镜像（node:20-alpine）独立构建**（不依赖任何本项目
预构建镜像），前端依赖走仓库锁文件 `npm ci`（apk/npm 各设有界重试抵御构建期瞬时
网络错误——重试次数有上限、全部失败仍构建失败，无 `|| true` 吞错）；运行容器
`network_mode: none` 硬隔离——**构建期联网下载公开依赖，运行期无外部网络**，
FastAPI/Vite/Chromium 全部经容器内 loopback 通信。

## 一键运行（构建 + 跑 + 清理）

```bash
cd <worktree>   # 即 /root/workpace/h3c-netctrl/.agent-worktrees/next-s1-backend

# 本机 /root/.docker 只读 → 重定向 HOME 到 worktree 内 scratch（用完即删）
export HOME="$PWD/.stackqa/home"
mkdir -p "$HOME"

# 1) 构建单容器镜像（FROM node:20-alpine 公开基座；apk chromium + venv pip + npm ci；
#    干净主机仅需仓库 + Docker，构建期联网）
docker compose -f openspec/changes/next-s1-workbench/qa/docker-compose.stack-qa.yml build qa-stack

# 2) 运行联调（幂等、可重复；network_mode: none —— 容器无外部网络）
docker compose -f openspec/changes/next-s1-workbench/qa/docker-compose.stack-qa.yml \
  run --rm qa-stack bash /opt/stack/qa/run_stack_qa.sh
# 成功末尾：6 passed（S1 2 条 + S2 3 条 + S3 1 条）+ BOUNDARY_OK（device-io.log 全 fake）+ STACK_QA_OK
# S2-018 验收要求：完整运行连续两次全绿（空库/状态无污染），并记录真实 test 数。
```

## 通道内部（run_stack_qa.sh 顺序）

1. 端口检查：18000 / 5173 被占用 → exit 9（绝不误连 5174 演示环境）。
2. 起真实后端：`stack_backend_wrapper.py`（唯一测试入口，进程内注入
   `NetconfClient/FakeExecutor/FakeValidationCollector` 边界 fake）→ uvicorn
   127.0.0.1:18000，启动时 alembic 在**空库**上全链 `upgrade head`（001 幂等补建
   devices/logs 基表）。
3. `/health` 就绪后 seed 合成数据（EVPN Leaf 192.0.2.10/192.0.2.11 TEST-NET +
   tenant + deployed VPC + 新鲜验证快照 + 可用业务口 GE1/0/10、GE1/0/11 + 非 EVPN
   设备 192.0.2.20），写隔离 SQLite `/tmp/stack-qa/db.sqlite`。
   S2-018 基线：同一 VPC 对 Leaf-Stack targeted、Leaf-Spare 未覆盖 → 覆盖 1/2，
   非 EVPN 设备（带观测记录）排除、不进 scope 分母。
4. vite dev 5173（core 模式，`VITE_API_BACKEND_TARGET=http://127.0.0.1:18000`）
   代理到真实后端；Playwright 跑 `frontend/tests/stack-qa/`（无任何 page.route mock）。
5. 断言 `device-io.log`：必须含 executor_execute/executor_success/netconf_enter/
   collector_sync，netconf 目标 host 以 `192.0.2.` 开头 → BOUNDARY_OK；否则 exit 7。
6. trap（EXIT/INT/TERM）统一杀掉 uvicorn/vite 并 `rm -rf /tmp/stack-qa`（tmpfs）。

> S2-018 联调修复：S2 系列把执行器/收集器从 `sdn_access` 抽到 `services`，且
> `validation/sync` 路由位于 `sdn.py`——wrapper 必须按「调用点模块全局名」逐个替换
> （`interface`/`sdn_access`/`sdn` 三个模块的 NetconfClient/SdnDeploymentExecutor/
> SdnValidationCollector），否则该路由走真实收集器，在 `network_mode:none` 下产生
> “Network unreachable”脏快照并污染 predeploy 证明。此修复只改 qa 通道文件。

## 覆盖

- 接入故事 → 服务端 preview → execute（不下发真机）→ 持久化 operation → PULSE
  （intent/scope/safety + 逐单元 truth kind）→ STRATA 同一上下文。
- 诚实状态：执行成功无回读显示「执行记录/未由设备验证」；验证证据不足 → operation
  保持 unknown + `safety_boundary.ambiguous_claims=true`，绝不冒充设备已验证。
- S2-018（stack-qa-s2.spec.js，3 条）：STRATA 覆盖 1/2 + 逐 Leaf 分类 + attention
  coverage_gap（不当漂移）+ 非 EVPN 排除；范围例外真实 PUT/DELETE 闭环（仍
  not_targeted、active_exception+1、attention → coverage_deferred/恢复 coverage_gap、
  无 deployment/binding/snapshot 新增、device-io.log 无新增调用）；targeted Leaf
  经真实 API sync 落库漂移快照 → attention confirmed_drift blocking，active 例外
  不吞掉事实且携带 exception；浏览器层固定文案「不下发配置、不隐藏漂移」与
  「不代表根因、不会自动修复」。fake 收集器新增 `collector-mode=drifted`（vsi 缺失）。
- S3（stack-qa-s3.spec.js，1 条）：GUARD 真实保存策略并完成手动评估；启用保障后，
  scope-exception 新增/清除分别追加 event 历史，页面显示两条「事件」记录及稳定
  event_key；全过程 `device-io.log` 不增长。

## 网络边界

- **构建期**：`docker build` 联网拉公开镜像/依赖（apk 仓库、npm registry、pip 镜像）。
- **运行期**：`network_mode: none` —— 容器无 eth0，只有 loopback；uvicorn/vite/
  chromium/curl 全部走 127.0.0.1。断网后故事依旧成立（loopback 不依赖外网）。

## 清理

- 容器 `--rm` + tmpfs `/tmp` + trap：进程/DB/日志在成功、失败、中断后均自动清理。
- 本机唯一残留是 `.stackqa/home`（docker HOME 重定向），跑完后 `rm -rf .stackqa/`。
