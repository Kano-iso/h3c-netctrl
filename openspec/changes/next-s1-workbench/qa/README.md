# S1-027/S1-028 真实应用栈隔离联调通道（qa/）

浏览器驱动【真实 FastAPI + 隔离 SQLite + 真实 vite dev】完成 NEXT 工作台接入故事，
设备执行/采集仅在进程内以边界 fake 替代，并事后断言 `device-io.log` 证明无真实设备 I/O。
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
# 成功末尾：2 passed + BOUNDARY_OK（device-io.log 全 fake）+ STACK_QA_OK
```

## 通道内部（run_stack_qa.sh 顺序）

1. 端口检查：18000 / 5173 被占用 → exit 9（绝不误连 5174 演示环境）。
2. 起真实后端：`stack_backend_wrapper.py`（唯一测试入口，进程内注入
   `NetconfClient/FakeExecutor/FakeValidationCollector` 边界 fake）→ uvicorn
   127.0.0.1:18000，启动时 alembic 在**空库**上全链 `upgrade head`（001 幂等补建
   devices/logs 基表）。
3. `/health` 就绪后 seed 合成数据（EVPN Leaf 192.0.2.10 TEST-NET + tenant +
   deployed VPC + 新鲜验证快照 + 可用业务口 GE1/0/10、GE1/0/11），写隔离 SQLite
   `/tmp/stack-qa/db.sqlite`。
4. vite dev 5173（core 模式，`VITE_API_BACKEND_TARGET=http://127.0.0.1:18000`）
   代理到真实后端；Playwright 跑 `frontend/tests/stack-qa/`（无任何 page.route mock）。
5. 断言 `device-io.log`：必须含 executor_execute/executor_success/netconf_enter/
   collector_sync，netconf 目标 host 以 `192.0.2.` 开头 → BOUNDARY_OK；否则 exit 7。
6. trap（EXIT/INT/TERM）统一杀掉 uvicorn/vite 并 `rm -rf /tmp/stack-qa`（tmpfs）。

## 覆盖

- 接入故事 → 服务端 preview → execute（不下发真机）→ 持久化 operation → PULSE
  （intent/scope/safety + 逐单元 truth kind）→ STRATA 同一上下文。
- 诚实状态：执行成功无回读显示「执行记录/未由设备验证」；验证证据不足 → operation
  保持 unknown + `safety_boundary.ambiguous_claims=true`，绝不冒充设备已验证。

## 网络边界

- **构建期**：`docker build` 联网拉公开镜像/依赖（apk 仓库、npm registry、pip 镜像）。
- **运行期**：`network_mode: none` —— 容器无 eth0，只有 loopback；uvicorn/vite/
  chromium/curl 全部走 127.0.0.1。断网后故事依旧成立（loopback 不依赖外网）。

## 清理

- 容器 `--rm` + tmpfs `/tmp` + trap：进程/DB/日志在成功、失败、中断后均自动清理。
- 本机唯一残留是 `.stackqa/home`（docker HOME 重定向），跑完后 `rm -rf .stackqa/`。
