# Proposal

## 1. Why

S3-001 提供只读保障评估与白名单历史，S3-002 提供了有界周期（scheduled）通道。但
"VPC 保障策略"在**业务状态变化**时还没有即时、可审计的评估记录。S3-003 在两类已成功
持久化的业务事件后追加 `trigger=event` 的只读评估，复用 S3-001 的投影/白名单路径：
1. validation/sync 成功落入新快照；
2. scope-exception 新增/修改/清除。

## 2. 范围（本包）

- 事件钩子 `services/sdn_assurance_events.record_event_check`：业务事务 commit **之后**
  调用；未配策略或 enabled=false → 零 event run；manual cadence 只禁用周期，已 enabled
  仍允许事件检查。
- 评估完全复用 S3-001（build_projection_payload + evaluate_assurance + 白名单快照）：
  不再次采集、不下发、不改 vpc.version 与 deployment/binding/operation/snapshot/claim。
- 原业务事件一旦成功不受影响：评估失败不回滚、不伪装业务失败，追加 `status=failed` 的
  event run 供审计；钩子绝不向调用方抛异常。
- 去重：run 新增稳定 `event_key`（snapshot:{id} / scope-exc:{id}:v{ver} / :cleared），
  仅含稳定内部 ID/版本，不含凭据/原始 CLI；DB 具名唯一索引防御（manual/scheduled NULL
  不受影响）；迁移 016 幂等可升降。
- `event_key` 作为只读审计字段在 run 序列化中返回。

## 3. 非目标（明确不做）

- 不做 scheduled/event 的写接口（trigger 写接口仍仅 manual；event 仅由业务事件钩子产生）。
- 不做自动修复 / 根因结论 / 设备采集或下发；事件评估路径零设备 I/O。
- 不为事件评估回滚原业务事务；不改 S1/S2 设备写语义。
- 不做前端视觉扩展（本轮仅服务端附加只读 event_key 字段）。
