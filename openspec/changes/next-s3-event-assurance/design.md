# Design

## 1. 触发点与去重 key

业务事务 commit 之后、响应返回之前，在同一请求 session 上调用 `record_event_check`。

| 事件 | 触发点（sdn.py 路由） | event_key |
|---|---|---|
| validation/sync 成功落入快照 | `sync_vpc_validation`（error=None 时，含 cached 命中同一快照——由去重兜底） | `snapshot:{snapshot.id}` |
| scope-exception 新增/修改 | `upsert_vpc_scope_exception`（commit 后重读 row） | `scope-exc:{row.id}:v{row.version}` |
| scope-exception 清除 | `clear_vpc_scope_exception`（deleted=True） | `scope-exc:{row.id}:cleared` |

- event_key 只含稳定内部 ID/版本（快照 id / 例外 id+version），不含凭据/原始 CLI。
- 同源事件重试不重复历史：DB 具名唯一索引 `uq_sdn_assurance_runs_event_key` 兜底，
  flush 撞唯一约束即 rollback 跳过（与 S3-002 CR61 同模式）。

## 2. 记录流程（record_event_check）

```
policy = policy(vpc_id)
if policy is None or not policy.enabled: return None        # 未配/禁用 → 零 event run
run(status='started', trigger='event', event_key, policy_version)  # 先占 key（唯一防御生效）
db.add+flush  → IntegrityError → rollback, return None      # 同源事件已记录
projection = build_projection_payload(db, vpc_id)            # 复用 S3-001（DB 只读）
result = evaluate_assurance(projection, now)                 # 复用 S3-001（白名单快照）
run → completed（facts/summary/items 白名单 JSON）; commit; return run
except: rollback; 追加 status=failed run（error 截断 500，summary overall=None 诚实）；
         commit（失败也撞唯一约束则跳过）; 绝不向调用方抛异常
```

- 崩溃留下 `started` run：诚实（已尝试，未伪装 completed/healthy）。
- 失败 run 的 event_key 同样参与去重：同一源事件失败重试也不重复历史。

## 3. 不变式与安全

- 评估只读：不调用 collector/executor/Netconf/SSH；不写 deployment/binding/operation/
  snapshot/claim；不 bump vpc.version。钩子失败仅追加 failed run，原业务成功响应不变。
- 业务事务已 commit，事件评估在独立事务追加 run；评估失败绝不 rollback 原业务。
- 路由侧 `_record_event_check` 再包一层 try/except（双保险），任何异常都只记日志。
- 迁移 016：`runs.event_key`(String 128, nullable) + 具名唯一索引；幂等（列/索引存在即
  跳过）；降级 drop 索引 + SQLite 表重建回 015 schema（保留 slot_key/error 与 CR61 索引）。
  ORM 与迁移索引命名一致（uq_sdn_assurance_runs_event_key）。

## 4. API 变更（向后兼容）

- run 序列化（GET runs / POST manual 响应）**附加**只读 `event_key`（manual/scheduled 为
  None）；既有字段与行为不变。前端本轮零改动。
