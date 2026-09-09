# S1-001 QA 计划（S1-002 修订）

> 范围：本轮只定义"应新增的测试、关键断言与运行方式"，不实际跑真机、不启动/替换主线常驻容器、不打印生产凭据。后续测试必须走 QA 容器。

## 1. 应新增的测试

| 文件（拟） | 覆盖 | 关键断言 |
|---|---|---|
| `test_sdn_operation_idempotency.py` | 幂等/冲突 | 同 `idempotency_key`+同指纹返回同一 operation_id 且计数不增；同键异指纹 409；跨租户/设备不泄漏；已 success 的 deployment 再 apply 被拒 |
| `test_sdn_apply_atomic_claim.py` | 原子认领 | 并发 apply 同 pending deployment 只有唯一执行者（`pending→running` CAS）；running 无完成结果判 unknown，读不触发回读，仅显式 reconcile 对账 |
| `test_sdn_access_predeploy_guard.py` | 前置部署证明 | 无有效 create+新鲜观测时接入被拒；create 后 delete 成功→失效；gateway_delete→L2 在但网关未就绪 blocker；旧快照晚写入→stale 强制新采集 |
| `test_sdn_access_preview_stale.py` | 服务端预览指纹 | 服务端重算指纹不一致→plan_stale + 原因；不按客户端过期计划下发 |
| `test_sdn_evidence_causal_window.py` | 证据因果窗口 | `collection_started_at >= deployment.completed_at` 才成立；变更前缓存不回填成新事实 |
| `test_sdn_collect_failure.py` | 采集失败显式化 | 采集失败/不支持/证据不足 ≠ 主机失败，result 非 active |
| `test_sdn_controlled_withdraw.py` | 受控撤回所有权 | 仅所有者撤回本次新建且 version 未变无新引用；仅读取不 bump version、不阻止合法撤回；解绑成功回读失败→unknown；重复撤回幂等 |
| `test_sdn_access_overview.py` | 聚合读取 + 终端视图 | overview 一次返回 bindings+deployments+每设备最新 snapshot+来源标注；expected_host_ip 为 intent，远端 Type-2 不挂本地端口 |
| `test_sdn_migration_012.py` | 迁移列级幂等 | 空库 upgrade head；旧库（007-011）upgrade 只补缺列/索引；downgrade 反向 |

所有 mock 测试不连真机，符合既有 `sdn` spec "不依赖真机"；并发用例用多 Session 模拟，不用串行重复调用冒充并发。

## 2. 关键断言要点

- 幂等：重复提交后 `sdn_operations`/`sdn_port_bindings`/`sdn_deployments` 计数不增长；同键异指纹 409。
- 原子认领：并发 apply 同 deployment 时 `status=running` 的 `attempt_id` 只有一个胜者写入。
- 证据：`complete` 响应四维字段齐备且自洽；`collection_started_at >= deployment.completed_at`。
- 撤回：撤回后 `binding.status == "unbound"`，VPC/网关/租户记录仍在；版本未变才允许。
- 失败边界：`collect_failed`/`insufficient`/`stale`/`active` 不混淆。

## 3. 运行方式（QA 容器隔离，已修正路径）

- **容器工作目录**：`backend/Dockerfile.qa:3` `WORKDIR /app` + `:17` `COPY backend/ .`，因此容器内命令为 `python -m pytest tests/<file> -q`（相对 `/app`），**不是** `backend/tests/...`。
- 常规入口：
  ```sh
  docker compose -f docker-compose.dev.yml --profile qa run --rm \
    qa-backend python -m pytest tests/test_sdn_operation_idempotency.py -q
  ```
- **.env 缺失问题**：独立 worktree 无 `.env`，而 qa-backend compose `env_file: .env`（`docker-compose.dev.yml:136`）是硬依赖。契约/单元测试通过 `-e` 显式注入非敏感测试变量绕过：
  ```sh
  docker compose -p next-s1-qa -f docker-compose.dev.yml --profile qa run --rm \
    -e DB_PATH=/tmp/test_h3c.db \
    -e ENCRYPTION_KEY='<测试用随机键>' \
    -e INTERNAL_API_TOKEN='dev-token' \
    qa-backend python -m pytest tests/test_sdn_operation_idempotency.py -q
  ```
  生产凭据（DEVICE_USERNAME/DEVICE_PASSWORD 等）一律不注入、不复制、不打印；若运行需要其它非敏感 env，由 Codex 后续放行精确清单。
- **固定 container_name 与 docker.sock**：`docker-compose.dev.yml:135` `container_name: h3c-netctrl-qa-backend` 固定，`up` 会名冲突；用 `run --rm`（自动加后缀 + 用完即删）+ 独立 `-p next-s1-qa` 项目名避免网络/卷冲突。契约/单元测试**不需要** `docker.sock`（`:144`，仅真机 e2e 故障注入用），不挂依赖容器、不起 ctrl/config/data/frontend。
- **测试 DB 隔离**：qa-backend 不挂 `./data`，容器内 DB 走 `DB_PATH`；`conftest.py:8` 已设 `DB_PATH=/tmp/test_h3c.db`，`setup_db` fixture（`:52`）每测试 `create_all/drop_all`。注意 conftest 用 `Base.metadata.create_all` 绕过迁移，`test_sdn_migration_012.py` 须单独用真实 alembic 升级临时库。
- 红线：不裸写 SSH/paramiko、不 skip 关闭测试、不 `docker system prune -a`、默认设备 .177 不连生产。

## 4. 验收边界

- 新增 mock 测试全过证明"实现行为符合契约"；真机接入/撤回链路由后续集成工作包在隔离实验资源单独验证，两者不能互相替代。
- 本 change 不授权设备探测或写配置。
