# Design

## 1. 调度窗口状态机（sdn_assurance_slots，每 VPC 至多一条）

```
pending --(claim CAS, due<=now)--> claimed --(eval ok)--> completed
                                    |                        |
                 (lease 过期，他 tick 接管，同代际新 token)   v
                                    |                  _advance CAS (id,generation)
                                    v                        |
                                claimed(新token)          pending(gen+1, due=terminal+cadence)
   eval 异常 --> failed (error 记录) --advance--> pending(gen+1)
```

- **CAS 原语**（SQLite 串行化写 + 条件 UPDATE + rowcount 校验，无进程锁）：
  - 认领：`WHERE id, generation, (status='pending' OR (status='claimed' AND lease_expires_at<=now))`
  - 完成/失败：`WHERE id, generation, status='claimed', claim_token`（成功后清空
    claim_token/claimed_at/lease_expires_at）
  - 推进：`WHERE id, generation, status∈{pending,completed,failed}`（claimed 窗口绝不推进）
  - 旧代际迟到（token/generation 不匹配）→ 0 行，不覆盖新代际。
- **run 与 slot 终态原子（CR61）**：scheduled 的 run INSERT/flush 与 owner-aware terminal
  CAS 在同一 DB 事务——CAS 0 行（lease 被接管/代际已变/已被推进）或 flush 撞唯一约束
  （同 (vpc_id, slot_key) 已有 run）→ 整个事务 rollback，run 一并回滚，绝不留
  orphan/重复历史；manual 保持 S3-001 原 API 事务语义（slot_key=NULL，唯一索引允许多行）。
  另加 DB 防御唯一索引 `uq_sdn_assurance_runs_vpc_slot_key`（ORM 与迁移 015 命名一致，
  SQLite NULL 允许多个 manual）。
- **owner 快照（CR62）**：`_claim_slot` 返回的 token 必须显式传到评估入口，开始投影前
  同时匹配 generation/status/token。slot 以脱离 Session 的快照进入评估，避免异常
  rollback 使 ORM 对象过期并刷新成接管者 token；旧 worker 因此既不能在接管后开始，
  也不能在执行中接管后代新 owner 收尾。
- **重启恢复**：pending 已到期 / claimed lease 已过期均可恢复执行；lease 未过期不可接管。
- **失败语义**：评估异常 → run 落 failed + slot 落 failed（诚实，不伪造 completed/healthy）；
  下一窗口（推进后）自然重试；崩溃 → lease 过期接管重试同一窗口。
- **防风暴（CR61）**：批量上限计入**每 tick 的全部持久化窗口变更**（建首窗口 / 认领评估 /
  terminal 推进 / policy-change 推进），max_slots=N 时最多 N 个 VPC 的 slot 被修改；
  纯只读跳过不计。停机后 advance due 锚定 now，至多补一个窗口。

## 2. 评估共用路径（manual 与 scheduled 同一套）

`services/sdn_assurance.persist_assurance_run(db, vpc_id, trigger, policy?, slot_key?)`：
build_projection_payload（同一次事实）→ evaluate_assurance → 白名单 JSON 快照 →
追加一条 run。manual 由路由调用（trigger=manual，slot_key=NULL，保持 S3-001 事务语义）；
scheduled 由 scheduler 走 **CR61 原子路径**（`_persist_scheduled_completed_atomic` /
`_persist_scheduled_failed_atomic`：run flush + owner terminal CAS 同一事务，输掉竞态
整个回滚）。评估异常由 scheduler 捕获并诚实记录（status=failed + error）。零设备 I/O、
零业务写副作用。

## 3. API 变更（向后兼容）

- GET/PUT `/api/sdn/vpcs/{vpc_id}/assurance-policy` 响应**附加**：
  `schedule_status`（disabled/manual_only/scheduled/due/running）、`next_due`、
  `last_scheduled_at`（最近一条 scheduled run 的 completed_at）。全部只读计算，不写库；
  既有字段与 S3-001 行为不变（GET 缺失仍返回默认值且零写）。
- POST runs、GET runs list/detail 不变；run 序列化附加 `slot_key`/`error`（失败 run 的
  overall 为 null，不伪装成 insufficient_evidence）。

## 4. 生命周期

- `main.py on_startup`：迁移后，若 `settings.ASSURANCE_SCHEDULER_ENABLED` 且
  SERVICE_NAME ∈ {config, core} → 启动调度线程；`on_shutdown` → stop 并 join。
- 轮询间隔 `ASSURANCE_SCHEDULER_INTERVAL_SECONDS`（默认 5.0，下限 1.0）；
  租约 `ASSURANCE_SLOT_LEASE_SECONDS`（默认 120）；测试 conftest 置
  `ASSURANCE_SCHEDULER_ENABLED=false`，测试直接同步调 tick_once 或显式构造 Scheduler。
- SQLite 引擎 connect_args 加 `timeout=5`：并发写（认领/完成 CAS 与 API 写）在锁竞争时
  等待而非立刻 "database is locked"。

## 5. 迁移 015（幂等可升降）

- 新增 `sdn_assurance_slots`（具名唯一索引 uq_sdn_assurance_slots_vpc；CHECK 约束
  status/cadence/generation）；`sdn_assurance_runs` SQLite 重建：加 slot_key/error 列、
  status CHECK 扩展为 ('started','completed','failed')（014 旧数据保持，slot_key=NULL）。
- 守卫：表/列存在即跳过（重复升级 no-op）；降级反向（删 slots、runs 还原旧 CHECK）。
  014 无 `failed` 语义，已有 failed run 降级时保留行并映射为 `started`，不冒充成功。
