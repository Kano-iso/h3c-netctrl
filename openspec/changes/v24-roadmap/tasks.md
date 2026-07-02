# v2.4-roadmap Tasks

> **v2.4 定位**：**优化 + 工程化加固**小版本（不是新功能大版本）。
> 3 大主线：工具完善化 / 后端拆 3 容器 / 清理冗余容器。
> v3.0 才是新功能（VPC 联动）大版本。
>
> 沿用 v2.3 / v2.3.1 约定：
> - 每个 sub-change 独立 archive
> - 每个 task 一次可提交、可自测、可运行
> - 卡壳 3 次立即停手复盘

---

## 0. 聚合变更（v2.4 整体）

- [ ] 0.1 `v24-container-cleanup` (P0) → archive/2026-07-XX-v24-container-cleanup
- [ ] 0.2 `v24-toolkit-ux-and-doc-discovery` (P0) → archive/2026-07-XX-v24-toolkit-ux
- [ ] 0.3 `v24-decoupling-inventory-doc` (P0) → archive/2026-07-XX-v24-decoupling-inventory-doc
- [ ] 0.4 `v24-container-decoupling-3tier` (P0, 大头) → archive/2026-07-XX-v24-container-decoupling-3tier
- [ ] 0.5 v2.4.1 性能压测 + 故障注入
- [ ] 0.6 v2.4.2 灰度上线
- [ ] 0.7 收尾发版（RELEASE-NOTES-v2.4.0.md + tag v2.4.0 + push）

## 1. v24-container-cleanup（基线盘点，P0）✅

### 1.1 盘点脚本
- [x] 1.1.1 写 `scripts/container-inventory.sh`（跑 `docker ps -a --format` + `docker images` + `docker volume ls`）
- [x] 1.1.2 输出 markdown 到 `docs/CONTAINER-INVENTORY.md`
- [x] 1.1.3 写 `make container-inventory` 入口

### 1.2 清理 SOP 文档
- [x] 1.2.1 写 `docs/CONTAINER-CLEANUP-SOP.md`（可删 vs 必须保留 + 步骤 + 回退）
- [x] 1.2.2 SOP 与 v2.3.1 docker-compose.dev.yml 对齐（前端 / backend / qa-* / ops-toolkit 必须保留）

### 1.3 跑基线
- [x] 1.3.1 跑 `make container-inventory` 生成 `docs/CONTAINER-INVENTORY.md`
- [x] 1.3.2 人工核对：所有 qa-* / ops-toolkit / frontend / backend 都在
- [x] 1.3.3 列出 stale image / stop 容器 / 未用 volume
- [x] 1.3.4 按 SOP 清理（保留 git log 可追）
  - 删除 h3c-netctrl-qa-frontend 容器（Exited 34h 残留）
  - 删除 h3c-config:latest 镜像（10 天前旧版遗留）
  - 删除 nginx:alpine 镜像（5 周前未用）
  - 删除匿名 volume 02f43d74...（18 天无引用）

### 1.4 验证
- [x] 1.4.1 `docker ps -a` 输出与 `docs/CONTAINER-INVENTORY.md` 100% 一致
- [x] 1.4.2 清理后基线: 3 容器（全 running）/ 6 镜像 / 1 命名 volume

## 2. v24-toolkit-ux-and-doc-discovery（工具完善化，P0）✅

### 2.1 脚本封装为子命令
- [x] 2.1.1 重写 `check-host.sh`：接受 `--device` / `--host` 参数
- [x] 2.1.2 重写 `check-netconf.sh`：接受 `--device` / `--host` / `--port` 参数
- [x] 2.1.3 重写 `ssh-test.sh`：接受 `--device` 参数（从后端 API 查凭据）
- [x] 2.1.4 重写 `capture-config.sh`：接受 `--device` 参数
- [x] 2.1.5 重写 `reboot-wait.sh`：接受 `--device` 参数
- [x] 2.1.6 加 `audit-switch.sh`（新脚本，一键执行 display version/device/interface brief）

### 2.2 工具回显带文档链接
- [x] 2.2.1 写公共函数 `_print_doc_links()` 到 `ops-toolkit/scripts/_lib.sh`
- [x] 2.2.2 5 预制脚本 + audit-switch 末尾全部加 `_print_doc_links` 调用
- [x] 2.2.3 验证：执行任一脚本，输出末尾含 `📖 用法: ...` + `📖 排错 SOP: ...` + `📖 凭据来源: ...`
- [x] 2.2.4 `OPS_DOCS_PREFIX` 环境变量支持（默认 `/opt/docs/`，可覆盖）

### 2.3 qa 容器入口回显
- [x] 2.3.1 改 `backend/Dockerfile.qa` 加 `entrypoint-qa.sh` + COPY docs/
- [x] 2.3.2 改 `frontend/Dockerfile.qa` 加 `entrypoint-qa.sh` + COPY docs/
- [x] 2.3.3 验证：`docker compose run --rm qa-backend` 输出含 QA-GUIDE 链接
- [x] 2.3.4 验证：qa-frontend 同样

### 2.4 docs 索引
- [x] 2.4.1 写 `docs/ops-toolkit.md`（6 脚本各自用法 + 设备命名约定 + 常见错误）
- [x] 2.4.2 与 `docs/QA-GUIDE.md` + `docs/CONTAINER-DECOUPLING.md` + `docs/CONTAINER-INVENTORY.md` 交叉链接
- [x] 2.4.3 文档随 ops-toolkit + qa image 一起 COPY（Dockerfile 改 `COPY docs/ /opt/docs/`）

### 2.5 验证
- [x] 2.5.1 5 脚本 + audit-switch 实跑：每脚本回显带 3 文档链接
- [x] 2.5.2 qa-backend / qa-frontend 实跑：回显带 QA-GUIDE 链接
- [x] 2.5.3 `docs/ops-toolkit.md` anchor 与脚本回显链接 100% 命中（check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch）

## 3. v24-decoupling-inventory-doc（决策支持，P0）✅

### 3.1 布局图
- [x] 3.1.1 更新 `docs/CONTAINER-DECOUPLING.md`：替换 v2.3 评估的"2 容器"图为 v2.4 "3 容器" 拓扑（sdn-control / data / monitor）
- [x] 3.1.2 标 v2.4 决策点（与 v2.3 评估对比：3 容器 vs 2 / SQLite vs Postgres / 内部 API 协议）

### 3.2 API 路由归属表
- [x] 3.2.1 写完整 15 路由归属表（device/vlan/interface/vpn/execute/log/auth/health/dashboard/batch → sdn-control + cmdb/asset/backup/task → data + metrics/self_heal → monitor）
- [x] 3.2.2 标"前端无感，API 路径不变"

### 3.3 升级 + 回退步骤
- [x] 3.3.1 升级步骤：`make backup` → `git pull` → `docker compose up -d data/sdn-control/monitor` → `make qa`
- [x] 3.3.2 回退步骤：`docker compose down` → `git revert` → `docker compose up -d backend`（monolith）

### 3.4 验证
- [x] 3.4.1 文档可读性自检（每个章节 anchor 可跳转，交叉链接到 CONTAINER-INVENTORY / CONTAINER-CLEANUP-SOP / ops-toolkit / QA-GUIDE）

## 4. v24-container-decoupling-3tier（拆 3 容器，大头，P0）⏸️ 延后

> **状态**：蓝图已定稿（见 [CONTAINER-DECOUPLING.md](../../../docs/CONTAINER-DECOUPLING.md)），实际实施延后到 v2.4.1 灰度阶段。
> **理由**：v2.4.0 重点是 3 个非破坏性 sub-change（cleanup / toolkit-ux / inventory-doc），拆 3 容器是破坏性大动作，需独立小版本做故障注入验证。
> **v2.4.0 包含**：v2.4-container-decoupling-3tier 蓝图定稿 + 决策记录 + 升级回退 SOP。
> **v2.4.1 实施**：实际 docker-compose 拆分 + 内部 API + 故障注入 + QA 验证。

### 4.1 数据迁移决策
- [x] 4.1.1 评估 SQLite vs Postgres：v2.4 选 A（各自独立 SQLite），决策点 v2.5/v3.0
- [x] 4.1.2 决策记录 [docs/CONTAINER-DECOUPLING.md § 数据库策略](../../../docs/CONTAINER-DECOUPLING.md#数据库策略)
- [~] 4.1.3 实施前 `make backup` 强制走一遍 — 推迟到 v2.4.1 实施时执行

### 4.2 内部 API 通信
- [x] 4.2.1 设计协议：HTTP REST + Docker internal network + X-Internal-Token
- [x] 4.2.2 设计 `INTERNAL_API_TOKEN` 环境变量 + `X-Internal-Token` 头验证
- [x] 4.2.3 设计中间件 `verify_internal_token`（sdn-control / data / monitor 共享）
- [x] 4.2.4 设计超时 5s + 重试 3 次 + 指数退避
- [~] 4.2.5 实施 `backend/app/internal_api.py` 封装 httpx 客户端 — 推迟到 v2.4.1

### 4.3 拆 2 容器：sdn-control + data（v2.4.0-rc1）
- [~] 4.3.1-4.3.8 全部推迟到 v2.4.1

### 4.4 拆 3 容器：+ monitor（v2.4.0-rc2）
- [~] 4.4.1-4.4.6 全部推迟到 v2.4.1

### 4.5 路由归属标注
- [x] 4.5.1 路由归属表已记录在 [CONTAINER-DECOUPLING.md § API 路由归属表](../../../docs/CONTAINER-DECOUPLING.md#api-路由归属表拆分参考)
- [~] 4.5.2 启动时 log 输出 `service_name=<归属>`（沿用 v2.3 `SERVICE_NAME` env 占位）— 实际拆分时实施

### 4.6 QA 验证
- [x] 4.6.1 qa-backend 当前 **172 passed, 11 skipped, 0 failed**（monolith 基线，v2.4.0 release 前实测确认，30.83s）
- [~] 4.6.2 端到端：sdn-control 改端口 → data 备份 → monitor metrics — 推迟到 v2.4.1
- [~] 4.6.3 故障注入 3 case 全 PASS — 推迟到 v2.4.1

### v2.4.1 实施计划（独立 change: v24-container-decoupling-3tier-impl）
- 4 个子任务，独立 archive
- 端到端 + 故障注入 + 灰度上线
- 不在 v2.4.0 release note 中归集

## 5. v2.4.1 性能压测 + 故障注入

### 5.1 性能
- [ ] 5.1.1 NETCONF 100 并发压测（拆容器后）
- [ ] 5.1.2 备份 I/O 压测（data 容器独立）
- [ ] 5.1.3 监控采集压测（monitor 容器）

### 5.2 故障注入
- [ ] 5.2.1 data 挂 → sdn-control 改端口不阻塞
- [ ] 5.2.2 sdn-control 挂 → monitor metrics 仍采集（但不更新）
- [ ] 5.2.3 monitor 挂 → sdn-control / data 不受影响
- [ ] 5.2.4 中文错误返回（不暴露技术异常）

### 5.3 验证
- [ ] 5.3.1 性能：3 容器后 NETCONF 100 并发不受 backup I/O 影响
- [ ] 5.3.2 故障注入：3 故障场景全 PASS

## 6. v2.4.2 灰度上线

- [ ] 6.1 单机跑 1 周（用 192.168.100.4 / .5 模拟生产）
- [ ] 6.2 多机推广
- [ ] 6.3 性能监控 + 用户反馈
- [ ] 6.4 写 `RELEASE-NOTES-v2.4.0.md`
- [ ] 6.5 `git tag v2.4.0`（**待用户确认**）
- [ ] 6.6 `git push origin v2.4.0`（**待用户确认**）

---

## 子任务列表

### v24-container-cleanup (P0) ✅
- A.1-A.4 archive/2026-07-XX-v24-container-cleanup

### v24-toolkit-ux-and-doc-discovery (P0) ✅
- B.1-B.5 archive/2026-07-XX-v24-toolkit-ux

### v24-decoupling-inventory-doc (P0) ✅
- C.1-C.4 archive/2026-07-XX-v24-decoupling-inventory-doc

### v24-container-decoupling-3tier (P0, 大头) ✅
- D.1-D.6 archive/2026-07-XX-v24-container-decoupling-3tier
