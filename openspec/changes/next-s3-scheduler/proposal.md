# Proposal

## 1. Why

S3-001 已让用户为 VPC 保存保障策略（enabled / cadence / observe_only）并发起只读手动
评估，但 cadence 只是"偏好"——没有任何机制周期执行。S3-002 在 config / monolith core
服务内实现**有界周期只读评估**：manual 保持手动，10m/30m/1h 才参与周期；真正可运行、
重启可恢复、多进程/重复 tick 不重复生成同一到期评估。仍然零设备 I/O、零自动修复，
不引入 Redis/etcd/Celery/APScheduler 等新依赖。

## 2. 范围（本包）

- 持久化 due/claim：迁移 015 新增 `sdn_assurance_slots`（每 VPC 至多一条当前窗口：
  slot_key / cadence / policy_version / generation / status pending|claimed|completed|failed /
  due_at / claim_token / lease_expires_at / run_id / error），并重建 `sdn_assurance_runs`
  加 slot_key/error 列、status CHECK 扩展为含 failed（诚实记录失败，不伪造 completed）。
- 调度服务 `app/services/sdn_assurance_scheduler.py`：tick_once（同步可测）+ 轮询线程；
  DB 条件更新 CAS（认领/完成/失败/推进均校验受影响行数）保证并发唯一 winner；
  lease 过期接管（崩溃恢复）；失败/崩溃不永久饿死后续周期；每 tick 批量上限防风暴。
- 抽取 S3-001 公共评估持久化 `persist_assurance_run`：manual 与 scheduled 共用同一
  投影/白名单路径（禁止复制一套判断）；scheduled run 保留 slot_key + policy_version +
  完成/失败状态。
- 生命周期：仅 SERVICE_NAME=config / monolith core 启动线程；data/ctrl 不启动；
  shutdown 停止线程；轮询间隔环境可配、安全下限 1.0s；测试可显式关闭。
- GET 策略响应**附加**稳定调度信息（schedule_status / next_due / last_scheduled_at），
  只读不写库；现有 S3-001 API 完全向后兼容。这轮不做前端视觉扩展（GUARD）。

## 3. 非目标（明确不做）

- 不做 scheduled/event 写接口（trigger 写接口仍仅 manual；scheduled 仅由 scheduler 产生）。
- 不做自动修复 / 根因结论 / 设备采集或下发；scheduler 路径不触达 collector/executor/Netconf/SSH。
- 不引入任何新外部依赖；不依赖进程锁（只靠 DB CAS）。
- 不补跑无限历史：cadence 改变按新策略续跑；停机后至多补一个窗口。
- 不做前端页面/视觉扩展（本轮仅后端切片 + API 附加只读字段）。
