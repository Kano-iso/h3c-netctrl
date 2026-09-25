# Readiness

状态：**READY_FOR_CODE_REVIEW**（后端周期评估切片；非 S3/NEXT 成品，未宣称 Codex 已通过）。

## 已交付（qa-backend 容器验证，真实 SQLite）

- 数据模型 + 迁移 015（幂等可升降；014 数据保持；CHECK 扩展含 failed；降级时已有
  failed 行诚实映射为 014 可表达的 started；CR61 唯一索引
  uq_sdn_assurance_runs_vpc_slot_key 与 ORM 命名一致，SQLite NULL 允许多个 manual）。
- 调度服务（CAS 唯一 winner / lease 接管 / 重启恢复 / 失败诚实可重试 / 批量上限 /
  SERVICE_NAME 门控 / 线程 start-stop）；manual 与 scheduled 共用公共评估路径。
- **CR61**：scheduled run 与 owner terminal CAS 同一事务（输掉竞态整个回滚，不留
  orphan/重复历史）；terminal CAS 匹配 status='claimed' 并清 token；claimed 未过期不抢
  代际；批量上限计入全部持久化窗口变更。
- **CR62**：认领 token 贯穿执行入口，执行前与异常 rollback 后都不会误用
  接管者 token；旧 worker 无权开始、无权替新 owner 收尾。
- GET 策略附加只读 schedule_status/next_due/last_scheduled_at；S3-001 API 向后兼容。
- 调度对抗 21 条 + 迁移 13 条（含 CR61/CR62 竞态顺序）= **34 passed**；
  受影响回归 78 条全绿。

## 明确未实现/未验证（诚实边界）

- scheduled/event 写接口仍未开放（trigger 写接口仅 manual；scheduled 仅由 scheduler 产生）。
- 自动修复 / 根因结论 / 设备采集或下发：未实现，scheduler 路径零设备 I/O。
- 评估基于合成/历史事实；真实多 Leaf 多 VPC 数值取决于真实记录（本包只验通道与契约语义）。
- 前端视觉扩展：本轮未做（仅服务端附加只读字段）。
- 并发竞态在处理器层/多 session 验证；未做跨多进程真机压测。
- scheduler 线程实测为单实例线程（config/core 单进程）；多进程部署下唯一性靠 DB CAS 保证，
  未经多进程真机验证。
