# S1 终端接入后端 — 规范设计（canonical, S1-004）

> 单一自洽契约。本设计只描述"如何实现"，不写应用代码；apply 工作包据此落地。
> 状态词汇（四层不混用）：operation.status / deployment.status / attempt.status / unit.state 各自独立（见 §1）。

## Context

v3.4 后端已有租户/VPC/端口绑定/下发/采集骨架。S1 需要"一次终端接入可解释、可恢复、可撤回"，核心缺口是：请求与尝试的稳定关联、原子仲裁、逐单元执行证据、崩溃对账、前置部署证明、受控撤回与历史保留。约束：复用 `sdn.py` 业务服务与 `SdnDeploymentExecutor` 执行链，写目标白名单 `.5/.6/.26`，准入只信 `sdn_role=evpn_leaf`，config 容器无本地 devices 表。

## Goals / Non-Goals

**Goals：** 原子仲裁（唯一执行者）、幂等（同请求同结果、异请求冲突、不跨范围泄漏）、逐单元状态+证据、崩溃对账（显式 reconcile，读不触发 I/O）、前置部署证明、受控撤回、历史在父对象删除后仍可追溯、独立可运行的 QA 定义。

**Non-Goals（实施 change 终态）：** 不建第二套执行引擎/对象库/全网部署/通用差异/自动修复/Agent/LLM/三维/物理布线自动发现；不把端口接入静默扩大为整机 VPC 部署。**本包（S1-004）额外不写应用实现、不连设备、不提交、不启动容器。**

## 1. 实体与约束

SDN 表归 config 容器。证据表（operations/attempts/attempt_units/plans/identity_snapshots）对父资源一律存**普通整数，不建外键**，不随父表级联删除。

### 状态词汇（canonical，四层分离）

| 层 | 状态值 |
|---|---|
| `sdn_operations.status` | planned / applied / awaiting_wiring / awaiting_validation / succeeded / degraded / failed / withdrawn / unknown |
| `sdn_deployments.status` | **pending / running / success / failed / unknown**（新增 `unknown`，与既有 API 词汇兼容） |
| `sdn_attempts.status` | claimed / running / succeeded / failed_known / unknown |
| `sdn_attempt_units.state` | not_started / started / succeeded / failed_known / unknown |
| `sdn_plans.status` | valid / consumed / expired / superseded |
| `sdn_resource_claims.status` | held / released / ambiguous（互斥见 §2） |

### 新表

| 表 | 关键列 | 约束 / 索引 |
|---|---|---|
| `sdn_plans` | id, plan_id, semantic_hash, version_snapshot_json, scope_json, status(valid/consumed/expired/superseded), expires_at, created_at, updated_at | `plan_id` UNIQUE；`expires_at` 索引 |
| `sdn_operations` | id, idempotency_key, fingerprint, operation_type(terminal_access/terminal_withdraw), tenant_id, vpc_id, device_id, plan_id?, expected_host_ip?, request_payload_json, scope_json, status, created_at, updated_at | `idempotency_key` UNIQUE；`(vpc_id, device_id)` 索引；**无公开删除端点（永久保留）** |
| `sdn_attempts` | id, operation_id, deployment_id?, kind(execute/validate/reconcile), status(claimed/running/succeeded/failed_known/unknown), owner?, claimed_at?, started_at?, completed_at?, scope_json, created_at, updated_at | `operation_id` FK→sdn_operations **ON DELETE CASCADE**（operation 永不删，级联安全） |
| `sdn_attempt_units` | id, attempt_id, unit_index, unit_name, state(not_started/started/succeeded/failed_known/unknown), evidence_json?, started_at?, completed_at?, created_at, updated_at | `attempt_id` FK→sdn_attempts ON DELETE CASCADE；`(attempt_id, unit_index)` UNIQUE |
| `sdn_resource_claims` | id, resource_key, owner_operation_id?, owner_attempt_id?, status(held/released/ambiguous), claimed_at, released_at?, created_at, updated_at | **部分唯一索引 `(resource_key) WHERE released_at IS NULL`** |
| `sdn_identity_snapshots` | id, entity_kind(tenant/vpc/device/binding/deployment/snapshot), entity_id, identity_json, deleted_at?, created_at | `(entity_kind, entity_id, created_at)` 索引 |

### 存量表加列（带默认/可空，历史零数据改写）

| 表 | 新列 |
|---|---|
| `sdn_vpcs` | `version INT NOT NULL DEFAULT 0` |
| `sdn_port_bindings` | `version INT NOT NULL DEFAULT 0`；`created_by_operation_id INT?`（不可变）；`last_changed_by_operation_id INT?`；`operation_id INT?` |
| `sdn_deployments` | `operation_id INT?`；`version INT NOT NULL DEFAULT 0`；`claimed_at?`；`claimed_by_attempt_id INT?` |
| `sdn_validation_snapshots` | `operation_id INT?`；`attempt_id INT?`；`collection_started_at?`；`collection_completed_at?` |

> 加列/建表有真实迁移成本；`operation_id`/`attempt_id` 全可空仅为历史兼容。downgrade 为**保守策略**：删 012 新增的 6 张表 + 2 个部分唯一索引，但**保留**存量表上加的列（SQLite 无法安全 drop 列），迁移显式声明。

## 2. 资源声明、互斥与锁序

**resource_key（确定性）：** `tenant:{tid}`、`vpc:{vid}`、`vpc-device:{vid}:{did}`、`device-port:{did}:{if_index}`。

**层级冲突规则（保守，一期安全优先）：** 每个**子级 mutation** 必须获取其**全部祖先 claim**，按**声明式等级序**（rank：`tenant` < `vpc` < `vpc-device` < `device-port`，同等级按数值标识符升序）逐个获取；**父级删除**获取祖先 key（如 `vpc:{vid}` 或 `tenant:{tid}`），因此与任何持有该祖先 claim 的子操作冲突。终端接入（tenant T、vpc V、device D、port P）按 rank 获取 `tenant:T, vpc:V, vpc-device:V:D, device-port:D:P`。可用性权衡：同一 tenant/VPC 内的 mutation 被串行化，换取安全——文档化接受。锁序是声明式 rank + 数值，**不是**字典序字符串比较。

**原子获取（SQLite 无 SELECT FOR UPDATE，用部分唯一索引做互斥）：**
```sql
INSERT INTO sdn_resource_claims(resource_key, owner_operation_id, owner_attempt_id, status, claimed_at)
VALUES (:k, :op, :att, 'held', now());
-- IntegrityError(UNIQUE) → 该资源已被持有或已被标记歧义 → 放弃并释放本次已获取的其他 claim
```

**互斥覆盖 held 与 ambiguous：** 部分唯一索引是 `(resource_key) WHERE released_at IS NULL`。`held` 与 `ambiguous` 的 `released_at` 均为 NULL，因此都独占该资源；把 stale 行改成 `ambiguous` **不会**让新 owner 插入 held 行。

**释放（仅显式 resolution 后）：**
```sql
UPDATE sdn_resource_claims SET status='released', released_at=now()
WHERE resource_key=:k AND released_at IS NULL AND owner_attempt_id=:att;
```

**TTL 不自动转移：** `claimed_at` 超阈值只把 claim 标 `ambiguous`（released_at 仍 NULL → 仍独占），attempt 置 `unknown`；由显式 `reconcile` 读设备后判定释放或完成。无对网络设备的 exactly-once 保证——设备侧动作不可回滚也不可重复，只能对账。

## 3. 核心决策

### C1 分层：计划 / 操作 / 尝试 / 单元
- `sdn_plans` = 服务端预览计划（不可变 plan_id + semantic_hash + version_snapshot + 10 分钟过期）。
- `sdn_operations` = 执行意图（幂等键 + fingerprint + scope 快照 + 状态机）。
- `sdn_attempts` / `sdn_attempt_units` = 尝试与逐单元状态。
- 四层状态词汇见 §1，互不混用。

### C2 幂等（前端生成 UUID key，服务端强制范围，先鉴权后返回）
- `idempotency_key` 全局 UNIQUE；`fingerprint` = SHA-256(规范化请求字段，字段名排序、去客户端时间戳)。
- **顺序：** ①鉴权 → ②校验请求 scope（tenant/vpc/device 归属与存在）→ ③INSERT（撞 UNIQUE 走 IntegrityError 分支）→ ④回查已有 operation，再次校验 scope 与指纹：
  - 同 key 同 fingerprint → 200 + `duplicate=true` + 原 operation。
  - 同 key 异 fingerprint → 409 `SDN_IDEMPOTENCY_CONFLICT`。
  - key 存在但 scope 不可访问/不匹配 → **404，不返回 fingerprint/status/body 任何信息**（防跨范围泄漏）。
- 重试（同 key 同 payload）不改原请求语义。并发路径：唯一约束保证只有一个 INSERT 成功，其余走 IntegrityError 回查。

### C3 执行原子认领 + 逐单元状态
- **deployment 认领（沿用既有 pending 词汇）：** `UPDATE sdn_deployments SET status='running', claimed_at=now(), claimed_by_attempt_id=:att WHERE id=:id AND status='pending'`，rowcount=0 → 竞争失败。`unknown` 为新增终态（apply 阶段加到 `SdnDeploymentUpdate` status pattern，additive）。
- **单元状态机：** `not_started → started → (succeeded | failed_known | unknown)`。设备 I/O 前写 `started`（durable），I/O 后写终态 + evidence。
- **`failed_known` ≠ 无副作用：** 回读确认无变化才能降级，否则 `unknown`。
- **重放规则：** 只有 `not_started` 的 unit 可执行，且依赖 unit 全 `succeeded`；任何 `unknown` 前置阻塞依赖 unit。`unknown`/`failed_known` 不自动重放，需显式 reconcile。

### C4 并发与崩溃
- 设备 I/O 不置于长 DB 写事务内：claim 获取 + deployment CAS 在短事务完成并提交后，才进设备 I/O；I/O 后另开短事务写 unit 终态 + 释放 claim。
- 崩溃窗口与恢复见 §5；读/刷新绝不触发设备 I/O（含 stale running 检测——只读库返回 `unknown`，不发起回读）。

### C5 前置部署证明
- 判定 = 当前有效 `vpc.version` + 最近相关成功变更 + 新鲜观测。`create` 成功但后续 `delete` 成功 → 失效；`gateway_delete` → L2 在但网关未就绪；failed/partial → unknown/blocker；观测 `collected_at` 早于最近变更 → stale 强制重采。
- 只证明 L2 接入资源就绪（VSI/EVPN）与网关验证前置（Vsi-interface+L3VNI+VPN binding）分开。
- **两套门禁严格分离（不得混用）：** `SdnPreflight` 的四项 deferred（VNI 不存在 / VLAN 未占用 / BGP Established / l3vpn 存在）是「创建 VPC 前」的语义——其中「VNI/VLAN 应不存在」与「终端接入已有 VPC」相反。`SdnPreflight` 的 deferred `success=True` 是占位，不是已通过：本轮不实现 VPC create preflight 就明确保持为 create 路径 blocker/后续项，绝不接到 terminal access。terminal access predeploy proof 要求目标 VSI/VNI **已存在且 L2 可用**（见 §19 CR36）。

### C6 服务端预览与执行绑定（POST，持久化单条计划）
- **预览** `POST /vpcs/{id}/access-preview`：持久化一条 `sdn_plans` 记录（plan_id 服务端不可变 + semantic_hash + version_snapshot + scope + expires_at=now+600s），**不写设备、不创建 binding/deployment/operation**。
- **执行** `POST /vpcs/{id}/access`：只接受 `plan_id`（**不接受客户端 preview_fingerprint**）。后端据当前服务端状态重算 semantic_hash 并比对 version_snapshot：
  - 不一致 → `plan_stale` + 原因；
  - plan 已 consumed → `plan_consumed`；
  - plan 已 expired → `plan_expired`；
  - 有效 → 创建 operation（同 idempotency_key 命中则返回原 operation）。
- **两套指纹分离：** `fingerprint`（请求幂等，客户端字段）≠ `semantic_hash`（服务端计划语义，用于 stale 检测）。
- 执行前用**绕过缓存**的分裂 API 重拉 `sdn_role`/`protected_interfaces`；ctrl 不可用 → 阻塞报 `SDN_DEVICE_METADATA_UNAVAILABLE`，不用 5s 缓存静默放行。跨容器无原子事务，只保证"以重新拉取的权威值校验"。

### C7 证据与因果窗口
- 每次执行/验证有 `attempt_id` + `started_at`/`completed_at` + scope + config_version；验证断言 `collection_started_at >= deployment.completed_at`。
- 缓存（600s）只作带时效历史，标注 `cached` + `collected_at`，不回填成新事实；每次验证独立结果。
- 四维分离 execution/config_readback/business_validation/evidence；采集失败/不支持/证据不足 ≠ 主机失败。

### C8 撤回与所有权
- `sdn_port_bindings.created_by_operation_id` 不可变；`version` + `last_changed_by_operation_id` 可变。撤回 = 所有者==本操作 且 version 未变 且无后续实际引用。读取/验证不 bump version。
- 实际新增引用/再利用/变更才进入风险判断；旧入口 delete/unbind/rebind/redeploy 明确各自 version/引用更新（§4）。

### C9 历史保留（非级联证据 + 身份快照 + 证据复制）
- `sdn_operations` **无公开删除路径，永久保留**；`sdn_attempts`/`sdn_attempt_units` 仅从 operation 级联（operation 永不删，安全）。
- 证据表对 tenant/vpc/binding/device 存普通整数，不建外键，不随父删级联。
- **父硬删除前**：把父对象 + 受影响子对象（binding/deployment/snapshot）身份写入 `sdn_identity_snapshots`，并把操作历史所需的 validation/config 证据**复制进 `sdn_attempt_units.evidence_json`**，再执行既有 CASCADE 硬删。不复制则不得承诺删除后仍有完整证据。
- Device 删除发生在 ctrl，config 不拦截：历史身份由 `sdn_operations.scope_json` 保证；若元数据在操作中途消失 → 阻塞后续 revalidation，operation 标记 device 身份来自 scope 快照（诚实声明跨容器残余竞态，不伪造原子设备删除）。

### C10 迁移（列级幂等）
- 012 迁移用列级 `_has_column`/`has_table` 守卫；downgrade 显式声明丢 012 新增数据。SDN 表归 config；`on_startup` 每容器跑 `alembic upgrade head`；Device 身份跨容器读。

## 4. 变更守卫矩阵（层级 claim + 新旧入口全覆盖）

**层级 claim（声明式 rank 序）**：`tenant:{T}` < `vpc:{V}` < `vpc-device:{V}:{D}` < `device-port:{D}:{if}`（rank 序 + 同 rank 数值升序，非字典序）。子 mutation 获取全部祖先 claim；父删除只获取祖先 key。

| 入口（文件:行） | 获取 claim（rank 序全集） | CAS/版本检查 | 幂等 | I/O 前写 | I/O 后写 |
|---|---|---|---|---|---|
| create_port_binding (sdn.py:848) | tenant, vpc, vpc-device, device-port | 端口占用改为 claim | 可选 key | attempt+unit started | unit 终态 + 释放 |
| start_vpc_expansion (sdn.py:997) | tenant, vpc, vpc-device, device-port | 前置部署 + vpc.version | 必填 key | 同上 | 同上 |
| deployment apply (sdn.py:718) | tenant, vpc, vpc-device | deployment CAS **pending→running** | — | attempt+unit started | unit 终态 + 释放 |
| deployment update PATCH (sdn.py:775) | tenant, vpc, vpc-device | 仅非 running 可改 | — | — | — |
| undeploy_port_binding (sdn.py:970) | tenant, vpc, vpc-device, device-port | binding.version + created_by | 可选 key | attempt+unit started | unit 终态 + 释放 |
| delete_port_binding (sdn.py:923) | tenant, vpc, vpc-device, device-port | binding.version；非 active | — | identity_snapshot + 证据复制 | 硬删 + 释放 |
| vpc withdraw (sdn.py:600) | tenant, vpc, 各 vpc-device | vpc.version | 可选 key | attempt+unit started | unit 终态 + 释放 |
| vpc redeploy (sdn.py:645) | tenant, vpc, vpc-device | vpc.version | 可选 key | 同上 | 同上 |
| gateway deploy/undeploy (sdn.py:709) | tenant, vpc, vpc-device | vpc.version | 可选 key | 同上 | 同上 |
| create/delete tenant/vpc (sdn.py:208/400) | tenant（或 tenant+vpc） | 父版本 | — | identity_snapshot(delete) + 证据复制 | 硬删 + 释放 |
| start_access (新) | tenant, vpc, vpc-device, device-port | 前置部署 + vpc.version + 权威成员/OOB | 必填 key | operation+attempt+unit | 同上 |
| complete_access / 显式 validate (新) | tenant, vpc, vpc-device | attempt 归属 + 因果窗口 | 幂等（已 complete 返回原） | validate attempt | 快照 + 释放 |
| withdraw_access (新) | tenant, vpc, vpc-device, device-port | created_by==op + version 未变 | 幂等 | attempt+unit | unit 终态 + 释放 |
| access-preview (新) | 无（只写 sdn_plans，不写设备/binding/deployment/operation） | — | — | 写 sdn_plans 一条 | — |

> 读取型 validation（普通 GET/latest/overview）不获取 claim、不写 attempt、不触发设备 I/O；显式 complete/validate/reconcile 属 mutation，按上表获取祖先 claim。行号为既有源码近似定位；apply 阶段按最终 diff 核对。ctrl 侧设备删除不在本表（config 无法原子跨容器删除），见 C9。

## 5. 事务与崩溃窗口伪代码

```
# execute(deployment):
# 1) 短事务：deployment CAS + 获取层级 claims（升序）
tx1:
  n = UPDATE sdn_deployments SET status='running', claimed_at=now(), claimed_by_attempt_id=:att
      WHERE id=:id AND status='pending'
  if n==0: return 409 (lost race)
  for k in ordered_claim_keys(claim_keys):  # 声明式 rank 序（tenant<vpc<vpc-device<device-port），非字典序
      try INSERT sdn_resource_claims(resource_key=k,...,status='held', claimed_at=now())
      except UNIQUE: rollback tx1; return 409 (resource busy/ambiguous)
  commit tx1

# 2) 设备 I/O（无 DB 写事务）
for each unit in planned_config (按 index):
    UPDATE sdn_attempt_units SET state='started', started_at=now()
      WHERE attempt_id=:att AND unit_index=:i AND state='not_started'
    if rowcount==0: skip (已在别的状态 → 前置 unknown 阻塞时 return unknown)
    result = device_io(unit)
    UPDATE sdn_attempt_units SET state=:result, evidence=:ev, completed_at=now()
      WHERE attempt_id=:att AND unit_index=:i
    if result in (failed_known, unknown): 后续未执行 unit 保持 not_started; break

# 3) 收尾（短事务）
UPDATE sdn_attempts SET status=:final, completed_at=now() WHERE id=:att
UPDATE sdn_deployments SET status=:final WHERE id=:id AND claimed_by_attempt_id=:att
for k in reversed(ordered_claim_keys(claim_keys)): UPDATE sdn_resource_claims SET status='released', released_at=now() WHERE resource_key=k AND released_at IS NULL AND owner_attempt_id=:att
```

**崩溃窗口：**
- 崩溃于 started 前：unit 仍 not_started，安全重放。
- 崩溃于 started 后、设备 I/O 前：unit=started 无终态 → `unknown`，不自动重放。
- 崩溃于设备已改、终态未落库前：unit=started 无终态 → `unknown`，显式 reconcile 读设备判定。
- 崩溃于终态落库后、收尾前：unit 有终态但 deployment/claim 未收尾 → reconcile 补写 attempt 终态 + 释放 claim。
- 超时无结果：unit=started → `unknown`，不凭"无响应"当未执行。
- 失主 claim（重启后 held 且 attempt 无 completed_at）：标 `ambiguous`（released_at 仍 NULL，仍独占），需显式 reconcile 释放。

**reconcile（显式，读不触发）：**
```
reconcile(operation):
  create attempt(kind=reconcile, status=claimed)
  read device display (显式授权采集)
  for each unknown unit: 比对 display 事实 → succeeded/failed_known/unknown
  release claims（显式 resolution）; update deployment/operation 终态
```

## 6. 幂等指纹与预览（分离）

- **请求指纹 `fingerprint`（幂等用）**：SHA-256(规范化请求字段，字段名排序、去时间戳)：`auto_apply, device_id, expected_host_ip, if_index, interface_name, service_instance, access_vlan, mode, tenant_id, vpc_id`。
- **计划语义哈希 `semantic_hash`（stale 检测用）**：服务端在预览/执行时计算，含解析后的目标版本（vpc.version、权威设备元数据、端口占用、前置部署证明版本）。
- **预览**：POST 持久化一条 `sdn_plans`，无设备写、无 binding/deployment/operation。plan_id 服务端不可变。
- **执行**：只收 `plan_id`；服务端重算 semantic_hash + 比对 version_snapshot。plan 有效→建 operation；同 idempotency_key 命中→返回原 operation（幂等优先于 plan 状态）。

**计划/幂等事务顺序（短事务内完成，不跨设备 I/O）：**
1. 鉴权 + 校验请求 scope（tenant/vpc/device 归属与存在）。
2. 解析 plan：plan_id 不存在→`plan_not_found`；`status=expired`→`plan_expired`；`status=consumed`→进入第 4 步（若同 key 命中返回原 operation，否则 `plan_consumed`）。
3. 若 plan `status=valid`：重算 semantic_hash + 比对 version_snapshot，不一致→`plan_stale`；一致→在**同一短事务**内 `UPDATE sdn_plans SET status='consumed' WHERE id=:id AND status='valid'`（rowcount=0 表示被并发消费）并 `INSERT sdn_operations`。
4. 幂等回查：`idempotency_key` 唯一约束 INSERT；撞 IntegrityError→回查已有 operation，重新校验 scope：同 scope 同 fingerprint→返回原 operation（**即使 plan 已 consumed**）；同 scope 异 fingerprint→409；不可访问 scope→404（不泄漏）。

> 并发同 key 同 plan：只有一个事务成功消费 plan 并建 operation；其余撞 key 唯一约束后回查到该 operation，返回原 operation（200 duplicate），**不是** `plan_consumed`。不同 key 对已 consumed plan：返回 `plan_consumed` 冲突。客户端从不发送 `preview_fingerprint`。

## 7. 迁移计划

- `012_add_sdn_operations.py`：列级幂等建表/加列/加索引，含部分唯一索引 `(resource_key) WHERE released_at IS NULL`；down_revision 按当前 head `011`（apply 时确认）。
- 迁移测试（真实 alembic，不用 create_all 替代）：空库 upgrade head；旧库（007-011）upgrade 只补缺；downgrade 反向。

## 8. QA（独立定义）

见 `qa/docker-compose.qa.yml`（已 `docker compose config` 解析通过）。要点：复用 `backend/Dockerfile.qa`（build context=worktree 根）、无 env_file/docker.sock/固定名/依赖/生产 DB、tmpfs `/tmp` 测试 DB、只读挂载 backend、项目名 `next-s1-qa`。测试路径为容器内 `/app/tests`，命令 `python -m pytest tests/<file> -q`。迁移测试单独真实 alembic。

## 9. Risks / Trade-offs

- [跨容器无原子事务] → 只承诺"以绕过缓存的权威值校验"，不承诺跨容器原子性；ctrl 不可用则阻塞。
- [无设备 exactly-once] → 明确 reconcile 语义，不伪造 exactly-once；unknown 不自动重放。
- [claim 互斥覆盖 ambiguous] → 失主 claim 仍独占，需显式 reconcile 释放；牺牲可用性换安全。
- [同 tenant/VPC 内 mutation 串行化] → 层级 claim 保守策略，文档化可用性权衡。
- [非级联证据表 + 证据复制] → 牺牲 DB 级联一致性换历史保留，靠 identity_snapshots + attempt/unit evidence 复制。
- [SQLite 单写者] → 唯一约束互斥 + 短事务，单机部署可接受。

## 10. 开放问题（已择默认，不留给实现猜测）

- 预览有效期 10 分钟，`SDN_PLAN_TTL_SECONDS` 可配（默认 600）。
- 幂等键前端生成 UUID；服务端强制范围/指纹/隐私顺序。
- 撤回"无新引用" = 本操作创建后无其他操作产生引用；读取/验证不计。
- 观测新鲜度 600s；执行/验证/对账可 force 采集。
- apply 认领无 TTL 自动释放；失主显式 reconcile。

## 11. S1-008 增量（CR19-CR23 修订）

- **CR19 reconcile 解析 unknown**：新增 `mark_unit_reconciled`，只允许 `started|unknown → succeeded|failed_known` 的受限 CAS；`reconcile_operation` 逐单元校验 rowcount，任一失败→`reconciled=false`、不释放 claims、上层保持 unknown/ambiguous；原 attempt 终态由 `derive_attempt_status_from_units` 重推（不得硬写）。
- **CR20/CR21 目标端口 scoped 证据**：`_scoped_port_evidence` 要求接口回读命令存在且 `success=true` 且无 CLI error，再用结构化语法匹配（`service-instance <si>`、`xconnect vsi <name>`、`port access vlan <id>`）判定 present/absent；命令缺失/失败/部分匹配一律 insufficient。port_bind 需全部标记 present；port_unbind 需全部标记 absent。
- **CR22 complete/validate 守卫**：complete 只允许 `awaiting_validation` + `port_bind` deployment；已验证幂等返回原结果；withdrawn/failed/unknown 等不可验证终态不改写、不新建 validate attempt；mutation 前 owner-aware 获取/复用 tenant/vpc/vpc-device claims，确定性终态释放、unknown 标 ambiguous。
- **CR23 主机观测同记录**：`_build_host_observations` 按行关联 `expected_host_ip` 与目标接口（同一行），或经 ARP MAC→MAC 表端口建立关联；命令失败不产生 observation=true；远端 Type-2 仅 remote/inferred。

## 12. S1-009 增量（CR24-CR26 修订）

- **CR24 显式 scoped collection**：`SdnValidationCollector.sync` 增加 `scope_bindings` 参数；显式 reconcile 把待对账 binding 作为 scope 传入，`_commands` 无论 binding 状态（planned/unbound）都追加目标接口回读命令；普通周期采集不传 scope，保持只采 `active|expanding` 的边界。测试走真实 `_commands`/`_snapshot_data`，只 mock SSH `_collect` 与凭据解析。
- **CR25 unknown validation 恢复**：complete 幂等仅限「确定完成」的 validate attempt（`succeeded`/`failed_known`）；`unknown` validate attempt 不幂等返回，保留旧 attempt 历史，在执行已确定成功（port_bind `success` + `config_completed_at`）时允许显式重试新建 validate attempt；不自动重放设备写操作（执行未知/失败不得经 complete 恢复，需显式 reconcile）。
- **CR26 CLI 错误 output 识别**：`_scoped_port_evidence` 在 `success=true/error=null` 时复用 `SdnValidationCollector._has_display_error(output)` 识别 `% Wrong parameter`/`Unrecognized command`/`Incomplete command` 等输出内错误，一律 insufficient，绝不当 port_unbind 配置缺失。

## 13. S1-010 增量（CR27 修订）

- **CR27 complete/validate 并发准入**：新增 op.status `validating` 中间态；`claim_action_admission` 用单行 UPDATE CAS 把 `awaiting_validation|unknown → validating`，只有 rowcount==1 的请求赢；赢者在同一短事务内创建 validate attempt + 获取/复用 claims 后 commit，才进入 collector/ping；输家（读到 validating 或 CAS 零行）返回 `sdn.operation_in_progress`，不建第二 attempt、不执行 I/O。准入后崩溃留下 `validating` + `claimed` attempt 痕迹，不回退 awaiting_validation、不重放。

## 14. S1-011 增量（CR28 修订）

- **CR28 validate/withdraw 跨动作原子仲裁**：`claim_action_admission` 泛化为任意 `from_statuses → to_status` 的单行 CAS；新增 op.status `withdrawing` 中间态。withdraw 在进入任何设备 I/O 前 CAS 取得 `withdrawing`（合法来源 `WITHDRAW_FROM_STATUSES`，排除 `withdrawn`/`validating`/`withdrawing`），与 `validating` 互斥；validate 的准入在 `validating`/`withdrawing` 下直接返回 `sdn.operation_in_progress`。
- **条件收尾 CAS**：新增 `finish_action`，validate/withdraw 的最终 op.status 写入必须 `UPDATE ... WHERE status=from_status AND active_attempt_id=<attempt>`；零行更新（状态被并发动作改变或代际被接管）时不得覆盖现状、不得释放/误标另一动作仍需的 claims，并返回 `late completion` 诊断。仲裁完全由数据库持久状态（op.status + active_attempt_id 单行 UPDATE）保证，无进程内锁。
- **withdraw 允许/拒绝状态**：`WITHDRAW_FROM_STATUSES` = planned/applied/awaiting_wiring/awaiting_validation/succeeded/degraded/failed/unknown；`withdrawn` 不可逆终态幂等返回，`validating`/`withdrawing` 返回 in-progress。
- **崩溃边界**：准入后崩溃留下 `validating`/`withdrawing` + attempt/deployment/claim 痕迹，不自动重放设备写。

## 15. S1-012 增量（CR29 修订）

- **CR29 apply 纳入动作仲裁**：新增 op.status `applying` 中间态；`apply_access` 进入任何设备 I/O 前原子 CAS `awaiting_wiring → applying`（`claim_action_admission`），只有 rowcount==1 的请求可调用 executor，与 `validating`/`withdrawing` 互斥；输家返回 `sdn.operation_in_progress`，不改变 execute attempt/deployment/operation/binding/claims。
- **apply 条件收尾 CAS**：`finish_action` 把 `applying → awaiting_validation|failed|unknown`（匹配 `applying + active_attempt_id=原 execute attempt`）；迟到/零行收尾不覆盖 `withdrawn` 或其他 phase、不释放/误标另一动作 claims。
- **deployment CAS 失败即停**：`executor.execute` 抛 `SDN_DEPLOYMENT_NOT_PENDING`（deployment 已被他人认领 running）时，apply 停止上层收尾、回滚并返回该错误，不把他人执行中的 deployment/attempt 推导为 unknown、不标 claims ambiguous。
- **准入崩溃边界**：准入后崩溃留下 `applying` + 原 execute attempt/deployment/claims 可对账痕迹，不自动重放 port_bind，走显式 reconcile。
- **auto_apply 兼容**：`claimed` 阶段保持兼容，其值不在 complete/withdraw 的合法来源集合，天然阻挡 complete/withdraw，不引入第二套设备写窗口。

## 16. S1-013 增量（CR30-CR31 修订）

- **CR30 动作代际令牌**：op 新增持久列 `active_attempt_id`（Integer, nullable）+ `active_started_at`（DateTime, nullable）。动作准入 CAS `claim_action_admission` 在同一短事务绑定 `phase + active_attempt_id + active_started_at`；所有动作收尾 CAS `finish_action` 同时匹配 `operation_id + phase + active_attempt_id`，成功时原子清空 token。apply 用原 execute attempt 身份；validate/withdraw/reconcile 用各自新 attempt 身份；准入输家回滚临时 attempt（不留垃圾）。phase-only CAS 不再被视为 owner-aware——旧代际迟到收尾零行，绝不覆盖新代际、绝不释放/误标新代际 claims。
- **CR31 reconcile 动作仲裁**：reconcile 参与仲裁。普通 reconcile 只能从明确 `unknown` 原子准入为 `reconciling`（绑定自身 attempt 令牌），与 applying/validating/withdrawing/reconciling 互斥，输家在 collector 前返回 in-progress。admission 后崩溃留下的 active phase 走显式受保护 `claim_stale_takeover`：依据 `active_started_at` + `STALE_ACTION_LEASE_SECONDS`（保守 300s，大于单次网络 I/O 上限）判定失联，`phase + old token + stale` 条件 CAS 抢占；未过 lease 或 `active_started_at IS NULL` 一律拒绝（不假装识别进程存活）。takeover 后把 `active_attempt`（token 指向的失联动作，见 §17 CR32）及其 started unit 记 unknown 留审计，再由新 reconcile attempt 采集，不重放任何设备写。reconcile 的全部终态写入/deployment/binding 修改/claim 释放在仍持有 `reconciling + token` 时发生；收尾 CAS 零行不改业务实体、不释放 claims；collector 失败条件收尾到 unknown；`withdrawn` 不可被 reconcile 改写。
- **schema 变化**：`sdn_operations` 新增 `active_attempt_id`、`active_started_at` 两列（012 migration 已含，`_create_table_if_missing` 幂等补列；ORM 同步）。

## 17. S1-014 增量（CR32 修订）

- **CR32 stale takeover 正确归属 active attempt**：reconcile 明确拆分两种 attempt 身份。
  - `active_attempt`：严格按 takeover 前 `old_active_attempt_id` 查询（且必须 `operation_id == op.id`），是需要被标 unknown 的失联动作；只修改它及其 started units，并写入 `stale_takeover` 证据。token 不存在、不属于本 operation、kind 不匹配 phase、或状态非活动态（claimed|running）时保守拒绝（不采集、不改 attempt/claim）。
  - `effect_attempt`：与设备写副作用关联的 execute/withdraw attempt，用于确定 deployment/action/目标状态；其已确定终态不得因 validate/reconcile 崩溃被改写。
  - applying/withdrawing 失联时 active 与 effect 可为同一对象；validating 失联时二者不同（active=validate、effect=execute）。
  - reconcile 收尾只解析 effect_attempt 中真正 uncertain 的 started/unknown units；effect_attempt 已 succeeded/failed_known 时不重放、不降级。validate 失联按原 port_bind 回读恢复到 `awaiting_validation`，不把「配置存在」冒充完整业务验证成功。

## 18. S1-015 增量（CR35 修订）

- **CR35 收紧 stale takeover 的 active attempt 身份与终态保护**：
  - 唯一 phase→kind 映射：`applying→execute`、`validating→validate`、`withdrawing→withdraw`（`ACTIVE_PHASE_EXPECTED_KIND`）。token 的 operation、kind、phase 三者在同一准入中校验，缺一即保守拒绝。
  - 可接管 attempt 状态仅限真实活动态 `claimed|running`（`STALE_TAKEOVERABLE_ATTEMPT_STATUSES`）；`succeeded`/`failed`/`failed_known`/`unknown` 等终态/未知绝不可被 stale takeover 再次降级覆盖。
  - 消除「Python 先读后改」竞态：`claim_stale_takeover` 在单条原子 UPDATE 内用 `EXISTS` 子查询同时证明 op phase/token/lease 仍匹配，且 active attempt 的 operation/kind/status 仍可接管；EXISTS 与 op 行更新同语句原子求值。
  - 新增条件式 `mark_attempt_stale`（仅 claimed|running → unknown，返回 rowcount）；零行说明 attempt 已在 CAS 后被并发转终态，调用方回滚接管，绝不覆盖终态、绝不宣称成功。

## 19. S1-016 增量（CR36 修订）

- **CR36 真实设备证据门禁与前置部署语义闭环**：
  - **两套门禁语义**（§3 C5）：`SdnPreflight` 四项 deferred 是「创建 VPC 前」（VNI/VLAN 应不存在）语义，`deferred success=True` 是占位非通过，本轮保持 create 路径 blocker/后续项；terminal access predeploy proof 是「终端接入已有 VPC」（目标 VSI/VNI 必须存在）语义，二者不得混用。
  - **`_l2_ready_status` 收紧**（terminal access predeploy gate）：除「成功 create + 之后无成功 delete + 采集晚于配置完成」外，新增：① create deployment `version == vpc.version`（版本因果，不伪造）；② 绝对新鲜度 `collection_completed_at` 距今 ≤ `PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS`（600s）；③ 原始命令按 L2 所需命令映射检查（BGP peer / VSI / Type-3），无关 L3/Vsi-interface/ARP 命令失败不参与（S1-017 CR37 修正）；④ 不再要求整张快照 `validation_result == "active"`（S1-017 CR37 修正）；⑤ `validation_details` 含 L2 必需条件 `bgp_peer_established`/`vsi_exists`/`type3_present` 且 `ok=True`；`vsi_up` 动态必需——仅当目标 Leaf 已有 active/expanding 本地绑定时要求 `ok=True`（S1-020 统一 collector `vsi_up.required = bool(bindings)` 语义，见 §22）（L2-scoped，无 CLI 错误按 L2 命令输出重算）。L2 字段缺失/旧格式/解析失败/L2 命令失败/L2 CLI 错误 → `unknown`。
  - **VPC 版本因果持久化**：`_create_sdn_deployment` 在创建时把 `deployment.version = vpc.version` 固化；`_l2_ready_status` 校验 `create.version == vpc.version`，不一致 → 保守 `unknown`（不伪造），旧数据 `version=0` 与 `vpc.version=0` 兼容。
  - **preview 与 execute 证据语义分离**：preview 只展示已有证据结果（读库，陈旧/不足显示 blocker）；execute 在 `_l2_ready_status == unknown` 且存在成功 create 时**强制重新取证**（`SdnValidationCollector.sync(force=True, min_interval_seconds=0)`，只读 display），不得复用陈旧缓存。采集失败/SSH 不通/命令不支持/输出不完整 → `SDN_PREDEPLOY_UNKNOWN` 阻断，且发生在消费 plan、创建 operation/binding/deployment、占用 claim 之前（零业务副作用）。
  - **空输出不等于无配置**：单次 `vpc-show`/`display` 空段是工具单次 recv 等待的非权威结果，不当作「设备无配置」；terminal predeploy 只信「正向 scoped 证据为真」，缺证据即 `unknown`。真机核对只允许 ops-toolkit 对 `.5` 执行只读 `display`，不写设备。

## 20. S1-017 增量（CR37 修订）

- **CR37 解除 terminal L2 接入门禁对 L3 网关健康的隐式耦合**：
  - **冻结 L2 必需条件**：`TERMINAL_L2_REQUIRED_CHECKS = (bgp_peer_established, vsi_exists, vsi_up, type3_present)`。明确不含 `vsi_interface_exists`/`l3_vni_present`（L3/网关维度，交由 complete 业务验证的 `l3_gateway_ready` 表达）。S1-020 起 `vsi_up` 为动态必需（见 §22），其余三项始终必需。
  - **L2 原始命令映射**：`_terminal_l2_required_commands(vpc)` = `display bgp peer l2vpn evpn` + `display l2vpn vsi name {vsi_name} verbose` + `display bgp l2vpn evpn`。只检查这三条命令的成功/CLI 错误；Vsi-interface/L3VNI/ARP/MAC/Type-2 命令失败/缺失/CLI 错误不拖垮纯 L2 门禁。
  - **移除两处 L3 耦合**：不再要求整张快照 `validation_result == "active"`；不再遍历整张快照所有命令。`raw_has_error`（无 CLI 错误）按 L2 命令输出重算，不复用 collector 全量 all_text 的 `raw_has_error`（后者会把 Vsi-interface/L3VNI 的 CLI 错误错误地耦合到 L2）。
  - **网关/L3 健康继续独立表达**：complete/业务验证的 `l3_gateway_ready`（`vsi_interface_exists`+`l3_vni_present`）与 gateway ping 维度保留，不得用 L2 成功冒充 L3 成功。
  - **保留 S1-016 的 TTL/配置完成时间/版本因果/execute 强制刷新与失败零业务副作用**。

## 21. S1-018 增量（CR38 修订）

- **CR38 Type-3 按目标 VPC 的 Route distinguisher 归属校验**：
  - **可单测 scoped 判定**：`SdnValidationCollector._type3_scoped(text, vni)`——按 `Route distinguisher:` 行把 `display bgp l2vpn evpn` 输出分块，逐块精确提取 RD（`\d+:\d+` 等值比较，`1:2000` 与 `1:20000` 不串匹配）；只在目标 `Route distinguisher: 1:{vpc.vni}` 块中发现 `[3]` 才为真。
  - **多 RD 正确分块**：目标块位于开头/中间/末尾均正确；其他 RD 有 `[3]`、目标 RD 只有 `[2]`、或目标 RD 块缺失 → False。
  - **保守失败**：无法可靠解析 / 缺少目标 RD 块 → False，由 `_l2_ready_status` 返回 `unknown`，不伪造成功。
  - **`_validate()` 接入**：`type3_present.ok = _type3_scoped(bgp_evpn_text, vpc.vni)`，替代 `"[3]" in bgp_evpn_text`。
  - **保留 S1-017 的 L2/L3 解耦、三条 L2 命令健康检查，以及 S1-016 的 TTL/version/因果/刷新失败零副作用**。

## 22. S1-020 增量（首次接入自阻断修复 + .5 真机生命周期）

- **问题**：collector 已表达 `vsi_up.required = bool(active/expanding 本地绑定)`，但 `_l2_ready_status` 忽略 `required`、无条件遍历固定四项，导致 fresh VPC 在目标 Leaf 尚无本地 AC/tunnel 时 `VSI State: Down`（`vsi_up.ok=False`）永远阻断第一个端口接入——控制流因果悖论。
- **修复（统一两处语义）**：`_l2_ready_status` 在遍历 `TERMINAL_L2_REQUIRED_CHECKS` 时，动态查询当前 `status ∈ {active, expanding}` 的本地绑定决定 `vsi_up` 是否必需：
  - 无 active/expanding 绑定 → `vsi_up` 不作为门禁（首次 AC bootstrap），`bgp_peer_established`/`vsi_exists`/`type3_present` 仍必需；
  - 有 active/expanding 绑定 → `vsi_up` 仍必需，`Down` 保守阻断后续接入；
  - `unbound`/`planned` 历史行不误判为「已有绑定」。
- **不改动**：版本因果（`create.version == vpc.version`）、TTL 600s、配置完成时间、L2 三条命令完整性/CLI 错误、BGP peer、VSI 存在、目标 RD Type-3、execute force refresh 与失败零业务副作用；preview/execute 共用同一 `_l2_ready_status`，自动同语义。
- **真机验收**：S1-019 真机测试不再把 predeploy 阻断断言为 PASS，改走 preview → execute → apply → readback GE1/0/10 service-instance/xconnect → complete（无主机诚实 degraded/unknown）→ access withdraw → VPC withdraw，并核对 operation/binding/deployment/attempt/claim 收尾与设备残留。

## 23. S1-021 增量（真机生命周期安全 Runner 与交付口径修正，本轮未触真机）

- **背景（两个复审阻断项）**：(1) S1-020 真机测试 docstring 与 review manifest 曾声称共享 `sdn_l3vpn`/VXLAN global「由 runner 兜底清理」，但仓库内没有该 runner；裸 pytest 的 `finally` 只尝试 VPC withdraw 且吞掉 withdraw 异常；实际 S1-020 运行后两个共享对象确有残留，由测试外的 ops-toolkit 精确清理。(2) readiness 曾提前宣称「Codex 已完成代码复审」，整体仍被本单阻断，不能提前写成复审通过。
- **唯一宿主安全 runner**（`openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`）：
  - **默认拒绝真机**：`--integration` / `S1_019_REAL=1` / `S1_019_REAL_HOST` 精确 `192.168.100.5` / `--cleanup-shared`（单独显式共享清理确认门）四重门禁；目标非 `.5` 在**任何设备 I/O 前**退出（码 3）。凭据只从 `.env`/环境注入，不打印、不复制到文件。
  - **设备 I/O 入口**：额外读取与兜底写入全部走 ops-toolkit 既有入口（`paramiko-batch-exec.sh`），不新增裸 SSH/paramiko；业务生命周期仍由 backend API/executor 执行。
  - **基线所有权契约**：pytest 前读取并保存最小基线（设备身份 `1.1.1.4`/`S6850`、VSI 空、EVPN routes 0、无 `ip vpn-instance sdn_l3vpn`、无 `vxlan tunnel mac-learning disable`、GE1/0/10 `port link-mode bridge`+`combo enable fiber`）。**共享对象基线已存在 → 拒绝承担其所有权（码 5），绝不在 trap 中删除既有配置**。
  - **trap 兜底清理**：进入可写阶段后安装 shell trap；无论 pytest 成功/失败/Ctrl-C/TERM 或后续步骤失败，只要基线证明两个共享对象原先不存在，就按恢复清单精确兜底清理——仅 `system-view` + `undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable` + `return`（无 `save`/startup-config/`.6`/管理口/GE1/0/1~3/underlay/OSPF/BGP 邻居）。
  - **最终 readback**：cleanup 后始终执行最终 readback 确认 VSI/测试 VPC、测试 AC、共享对象均回基线；**命令返回码 0 ≠ 清理成功**（以 readback 证据为准）。
  - **退出码语义**：保留 pytest 原始退出码；但 cleanup 或 final readback 失败时整体失败（码 6）并输出 `MANUAL-NEEDED` 指示人工。并发执行用本机 flock 锁（第二个 runner 在设备 I/O 前退出码 2）。
  - **对抗测试**：`test_s1_021_runner_adversarial.py`（16 条）用 stub/fake 命令验证全部守卫行为，不启动生产网络、不读真实凭据、不连接设备。
- **交付口径**：真机测试 docstring 与 review manifest 标准跑法改为唯一 runner；裸 pytest 只是 runner 内部实现，不承担共享对象清理。如实记录：S1-020 完整生命周期通过，但测试自身 VPC/access withdraw 完成后两个共享对象仍残留，由**测试外的 ops-toolkit** 监督精确兜底并最终 readback 干净（当时无自动 runner，不写成已有 runner 自动完成）。readiness 改为「等待 Codex 复审」，review manifest 完成只写 `READY_FOR_CODE_REVIEW` 不写 `CODE_REVIEW_PASSED`。本轮**未运行真机测试、无任何设备 I/O**。

## 24. S1-022 增量（Runner 审计目录失效时仍必须安全清理，本轮未触真机）

- **背景（Codex 复审阻断，业务代码无新问题）**：`RUNNER_ARTIFACT_DIR` 指向不可创建路径时，runner 在 baseline 文件写入失败后仍打印 `BASELINE-OK` 并进入可写阶段；退出时 `run_ops ... > cleanup.txt` 的重定向在命令启动前失败，导致两条共享 undo 根本没执行，只能报 `MANUAL-NEEDED`。违反「保存基线后才允许写」与「trap 必须实际尝试清理」。另有 `test_lock_prevents_concurrent_runners` 中 `assert not _has_undo(...) or True` 恒真。
- **修复**：
  - **启动审计目录探针（任何设备 I/O 前）**：`umask 077` + `setup_artifact_dir`（`mkdir -p` + 创建临时探针文件后删除）；失败直接退出码 6，不采集基线、不跑 pytest。
  - **baseline 持久化门**：`baseline.txt` 写失败 → 退出码 4，在 pytest/可写阶段前终止；只有持久化成功才设置 `WRITE_PHASE`。
  - **先执行后落盘（EXIT trap）**：cleanup 与 final readback 一律先用命令替换真实执行并捕获返回码/输出，再尽力写审计文件；审计目录被删除/变只读/写失败**不得阻止**精确清理或回读执行；审计写入失败置 `AUDIT_FAIL=1` → `MANUAL-NEEDED` + runner 最终非零（不替代 cleanup/readback）；cleanup 失败不跳过 final readback。
  - **测试注入点**：`stub_pytest.sh` 增加 `STUB_PYTEST_HOOK`（pytest 期间删除/破坏审计目录）。
- **对抗测试（新增 5 条，共 21 条）**：审计目录不可创建/不可写 → ops 调用 0 / pytest 未调用 / 非零退出；baseline 持久化失败 → 不进入 pytest/可写阶段；pytest 期间删除审计目录 → cleanup 两条精确 undo 仍实际调用 + final readback 仍实际调用 + runner 非零提示人工；cleanup 设备命令失败 + 审计目录失败 → 仍执行 final readback；并发锁测试真实断言（loser 无新增 ops 调用/undo）。本轮**未运行真机测试、无任何设备 I/O**。

## 25. S1-023 增量（仓库凭据卫生与 ZTP 密码边界，本轮未触真机）

- **背景**：灾备审计发现远端历史与活跃源码携带真实设备默认口令字面量。历史泄露只能靠用户外部轮换（本包不改设备、不重写 Git 历史）；本包目标 = 活跃源码不再携带真实默认口令，ZTP recovery 查询接口不再把密码回显给浏览器。
- **生产路径移除真实密码字面量**：
  - `backend/app/schemas.py`：`ZtpOnboardRequest.password` 改必填 `Field(..., min_length=1)`（无默认）；`ZtpRecoveryOverrideRequest.password` 改 `Optional[str] default=None`（留空 = 沿用已有 / 环境注入）。
  - `docker/ztp-stack/entrypoint.sh`：`ZTP_ADMIN_PASS` 改 `${VAR:?}` 必填（缺失 fail closed，无代码内口令）；渲染产物 `autocfg.cfg` 权限收紧 600；日志行不打印口令。
  - `docker/ztp-stack/ztp_runtime_render.py` / `ztp_onboard_callback.py`：新增 `_require_admin_pass()`，密码只来自环境/override，缺失明确 `RuntimeError`（fail closed）。
  - `docker/ztp-stack/tftp/autocfg.cfg.j2` + `docs/ztp-stack.md` + `.env.example`：注释/示例移除字面量，改为「环境注入、仓库无代码内口令」。
- **ZTP 密码边界（写操作）**：`ztp_recovery.write_recovery_override` 密码优先级 = 请求显式提交 → 既有 override → `ZTP_ADMIN_PASS` 环境；全缺失 → 明确 `ValueError`。
- **recovery state 与 API 脱敏**：明文密码仅落盘 git 忽略的 `ZTP_STATE_DIR/recovery_override.json` 且权限 `0600`（仅 ztp-server 渲染读取）；GET/POST `/api/ztp/recovery-override` 响应一律 `_redact`（递归剔除 password，仅返回 `password_set` 布尔），浏览器不接触明文。
- **前端**：`ZtpRecovery.vue` 初始/加载 override 时 password 保持空白（不填充 API 值）；留空提交 `null`（沿用已有 / 环境注入），显式重输才提交；i18n 新增 `password_placeholder` 提示。
- **ops-toolkit debug-***：确认无入口临时脚本（REVIEW-v242 已列为 P2 清理债、docs/ops-toolkit.md 未收录、裸 ncclient 直连设备违反红线）→ 移除 5 个 `debug-v24-*.py`，不新建裸 SSH 路径。
- **测试**：活动测试文件真实口令字面量全部替换为明显 synthetic（`SyntheticTestPass!1`，非可用默认口令）；新增 `test_s1_023_credential_hygiene.py`（静态扫描活动生产路径/测试无字面量 + debug-* 已移除 + ztp-stack 三脚本缺密码 fail closed + onboard 缺密码 422 + state 0600/API 脱敏）；`test_ztp_recovery.py` 扩展脱敏/权限/缺密码/env 注入/沿用已有断言；`ZtpRecovery.spec.js` 断言密码留空/提交 null/无字面量。
- **历史边界（明确不改）**：archive/ 下历史 change、`RELEASE-NOTES-v2.3.1.md`（历史发布记录）仍含已暴露口令文本 → 不重写历史；handoff/readiness 明确「历史已暴露，必须由用户在设备与 `.env` 外部轮换」。本轮**未运行真机测试、无任何设备 I/O**。

## 26. S1-024 增量（CR43：ZTP 渲染凭据边界加固，本轮未触真机）

- **背景（Codex 复审阻断）**：S1-023 移除字面量后仍有两处凭据边界缺口——(1) `ztp_runtime_render.render_once` 的原子写不彻底：`tmp.write_text` 受进程 umask 影响创建 0644，`tmp.replace` 用临时文件权限替换目标，运行中任何一次重渲染都会把 `autocfg.cfg` 从 0600 变回 0644；(2) `entrypoint.sh` 把 `ZTP_ADMIN_PASS` 等环境值直接插进 `python3 -c` 的单引号源码，密码含单引号/反斜杠/换行等字符时语法失败甚至代码注入；且 `ZTP_PLATFORM_LONG` 只作 shell 变量未 export，env-only 渲染读不到。
- **修复**：
  - **安全原子写 `_atomic_write_secret`**（`ztp_runtime_render.py`）：临时文件创建前收紧 `umask 077` + `os.open(..., O_CREAT|O_EXCL, 0o600)`（创建即 0600）→ `os.fdopen` 写入 + flush + fsync → `os.replace` 原子替换 → 替换后显式 `os.chmod(0600)`；任何异常 `unlink` 临时文件（不残留宽权限或含口令中间文件）。
  - **entrypoint.sh 环境注入渲染**：python3 -c 块内零 `$`、零单引号插值，全部渲染变量（`ZTP_PLATFORM`/`ZTP_PLATFORM_LONG`/`ZTP_MGMT_IP`/`ZTP_SYSNAME`/`ZTP_ADMIN_USER`/`ZTP_ADMIN_PASS`/`ZTP_HCL_T7064P15`/`ZTP_DATE`/`ZTP_AUTOCFG_TEMPLATE`）一律 `os.environ[...]` 读取；`ZTP_PLATFORM_LONG` 补 `export`；输出走 `mktemp`（创建即 0600）+ 显式 `chmod 600` + `mv -f` 原子替换 + `trap` 失败清理，不经宽权限中间态。
- **对抗测试（新增 `test_s1_024_credential_hygiene.py`，6 条）**：特殊字符密码（单引号/反斜杠/换行/`$()`/反引号/通配符/中文）模块级与 entrypoint 全量运行级（stub dnsmasq + 真实 jinja2）均原样渲染、不执行注入；runtime 首次与覆盖重渲染后均 0600（直击 0644 回归）；`os.replace` 失败路径不残留 `.tmp`/含口令中间文件；缺环境变量在写盘前明确失败；entrypoint 渲染块静态断言（无 `$` 插值、`os.environ` 读取、mktemp/chmod/mv/trap 契约）。本轮**未运行真机测试、无任何设备 I/O**。

## 27. S1-026 增量（operation 解释投影，只读 serializer 纯函数，本轮未触真机）

- **背景**：`GET /api/sdn/operations/{id}` 已返回 operation / attempts / units / raw evidence，但证据结构随执行路径变化，前端只能依赖演示数据拼出「动作、范围、证据、结论」。本轮新增只读、兼容、稳定的 `explanation` 投影，供 NEXT 工作台 PULSE / STRATA 消费真实后端语义。
- **范围约束**：serializer / projection 层——不新增表、不迁移数据库、不改 apply/validate/withdraw/reconcile 行为、不连设备、不改 ops-toolkit；保留所有既有字段与原始 `scope`/`evidence` 原样返回。
- **实现（新增 `backend/app/services/sdn_explanation.py` 纯函数；`sdn_access.py::_operation_to_dict` 只负责组装）**：
  - **operation 级**：`intent`（稳定 code：`terminal_access→access_bind` / `terminal_withdraw→access_unbind` / `legacy_apply→legacy_apply`）、`scope_summary`（由 scope + expected_host_ip 拼紧凑中性摘要，无 scope→null）、`safety_boundary`（`target`{device_id,if_index,interface_name}、`target_only`（单接口语义仅 access/withdraw 为 true，legacy 为 false）、`ambiguous_claims`（只表达当前未决状态；历史 stale takeover/insufficient 在 operation 已确定收尾后不再冒充当前歧义）、`protected_interfaces`（未持久化→null，禁止编造））、`truth_state`（`succeeded` 且存在确定完成 validate attempt → `verified`，否则 `succeeded_recorded`；`degraded`/`failed`/`withdrawn`/`unknown`/`pending`/`applied` 各归位）、`headline`、`statement`。
  - **attempt 级**：`explanation`{`kind`、`summary`（语言中性 fallback）、`result`（raw status）、`finished`、`still_uncertain`（claimed/running/unknown 为 true；failed_known 是确定结论不算仍不确定）、`evidence_basis`（`four_dimension_validation`/`insufficient_evidence`/`stale_takeover`/`execution_record`/`reconciliation`/null）、`statement`、`started_at`、`completed_at`}。
  - **unit 级**：`explanation`{`category`、`statement`、`truth_kind`（`desired|observed|inferred|pending`）、`source`、`scope`（继承 attempt scope，数据可证）、`observed_at`、`freshness`（单元级无独立时效时间戳→null，handoff 登记缺口）}。诚实表达：succeeded 无观察证据→`desired`/`execution_record`/「not device-verified」，且 `observed_at=null`，不把执行完成时间冒充观测时间；failed_known+definitive→`observed`/`device_rejection`/`device_response`；reconciled 单元 execute→`observed`/`readback_verified`、withdraw→`inferred`/`readback_syntax_match`（结构化语法匹配证明配置缺失）；unknown/started/not_started→`pending`。历史 JSON 损坏时只读详情安全降级为 null，不因投影解析 500。
  - **稳定性**：`_safe_explain` 包裹（解释失败→`{"unavailable": true, "reason": "explanation_failed"}`，绝不 500）；三个纯函数对 None/畸形主参稳定降级（`_dict`/`_s` 防御），绝不抛出。中文不固化后端，只回稳定 code + 语言中性 fallback statement，具体中文由前端 i18n 完成。
- **对抗测试（`test_sdn_explanation.py`，27 条）**：除原投影契约外，增加 API 级畸形历史 JSON 降级测试；复审修正“历史 stale 永久污染当前 claim 状态”和“执行完成时间冒充设备观测时间”。相关回归 65 passed。本轮**未运行真机测试、无任何设备 I/O**。

## 28. S2-001 增量（VPC 目标态/观测态/差异投影，只读 pure function，本轮未触真机）

- **背景**：STRATA 需要直接消费「平台期望 vs 设备观测 vs 差异」的只读后端能力，且不能再把数据库配置记录冒充设备事实。复用 S1 已固化的 VPC/binding/deployment/snapshot 与设备 `sdn_role`，不新增执行器/采集命令/图数据库/迁移。
- **范围约束（只读）**：`GET /api/sdn/vpcs/{vpc_id}/state-projection` 不触发 SSH/NETCONF、不写库、不刷新时间戳、不隐式同步；只比较现有验证快照可证明的维度。非 evpn_leaf 设备不进可操作目标集合（历史残留仅作 excluded/unsupported），不混入健康分母。
- **实现（新增 `backend/app/services/sdn_state_projection.py` 纯函数；`sdn.py` 新增只读端点组装）**：
  - `build_leaf_projection`：`desired`（VSI / VSI-interface / L3VNI / 端口绑定摘要，各带 `source = {kind, id, version}` 来源记录；vsi_up 期望由 operable 绑定数量驱动）、`observed`（从 `snapshot_data.commands[*]` 直接解析——命令键与 `SdnValidationCollector` 一致：`display l2vpn vsi name {vsi_name} verbose` / `display current-configuration interface Vsi-interface{n}` / `display current-configuration interface {GE}`，含 snapshot_id + 采集完成时间 + snapshot_age_seconds + stale）、`diff` 逐维 `aligned|drifted|unknown|stale|not_applicable` + 稳定 reason code。
  - **诚实表达铁律**：命令 `success != true` / 缺失 / `error` 非空 → `unknown`（采不到，绝不降级 drift）；TTL 600s（对齐 `PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS`）超时 → `stale`；`planned` 绑定（意图未下发）→ `not_applicable`/`planned_not_deployed`，不进健康分母；`unbound` 不进 desired；远端 EVPN Type-2/BGP 摘要不进本投影（只读本地 config 回读，绝不冒充本地下联端口/主机事实）；聚合取最差（stale>drifted>unknown>aligned），永不覆盖逐维事实；空 Leaf 集合 → 聚合 unknown。
  - `sdn.py::get_vpc_state_projection`：目标集合 = `sdn_deployments ∪ sdn_port_bindings ∪ sdn_validation_snapshots` 覆盖的 device_id；`_is_sdn_fabric_member`（`sdn_role=evpn_leaf`）分 leaves / excluded（reason=not_evpn_leaf）；每台 leaf 取最新快照解码后投影。
- **对抗测试（新增 `test_s2_001_state_projection.py`，10 条）**：无快照/过期/全一致/l3-vni 明确偏差/部分命令失败 unknown 不 drift/planned 不断言/vsi_up not_applicable/非 EVPN 排除/GET 零 I/O 零写入穿透契约。本轮**未运行真机测试、无任何设备 I/O**。

**S2-001-R1（CR47-CR49 复审返工，本轮未触真机）**：
- **CR47 目标态由生命周期证明**：路由把每台设备的 deployment（id/action/unit/status/version/config_completed_at）传入投影；新增 `resolve_base_lifecycle` 纯函数折叠基础对象存在性——只认 `action∈{create,delete}` 且 `status==success` 的确定事件，按 id 升序折叠；成功且 `version==vpc.version` 的 create → present，其后成功 delete → absent，pending/failed/unknown 不覆盖最后确定结果，版本不一致/无 create → unknown。`desired.vsi/vsi_interface/l3_vni.present` 依此取 True/False/None，diff 用 `_classify_presence`（desired absent + observed 存在 → `*_unexpected`，desired absent + observed 不存在 → `*_absent`，desired unknown → `desired_unknown`）；基础对象 absent 且仍有 operable binding → `desired.base.conflict=true`，绑定维与 vsi_up 标 `lifecycle_conflict`。响应 `desired.base={state,source,conflict}` 保留来源 deployment。
- **CR48 多值成员比较**：`_service_instances`/`_access_vlans` 返回有序列表；`next(iter(set))` 改为「目标值 ∈ 观测列表」；绑定 diff 输出 `observed` 列表。
- **CR49 token 精确匹配**：`_vsi_name_present`/`_vsi_state_up`/`_vsi_interface_present`/`_l3_vni_present` 改为行首/词边界正则（`(?m)` + `\b` + `lookahead`），杜绝 l3-vni 3000↔30000、Vsi-interface1↔10、VSI 名前缀串扰。
- **Codex 复审补齐网关生命周期**：生命周期按 L2 基础对象与 L3 网关拆分。完整 create/delete 同时改变两者；局部 `create + unit=vsi-l3` 与 `gateway_delete + unit=vsi-l3` 只改变网关期望。由此网关撤回后仍可判定 L2 VSI aligned，且局部补回网关不能反向证明 L2 VSI 已存在。
- **Codex 复审补齐失败证据边界**：SSH executor 返回 success 但正文含 H3C CLI 错误标记时，观测仍为 unknown；存在 snapshot id 但 JSON/commands 不可读时标 evidence_missing，不退化为 no_snapshot。
