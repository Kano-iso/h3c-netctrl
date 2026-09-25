# Proposal

## 1. Why

S2 建立了 VPC 的 scope（范围覆盖）、state projection（目标/观测差异）与 attention
（可行动关注队列）等**已持久化**事实。S3-001 是 S3「受限保障」的第一个可用纵向切片：
用户能为 VPC 保存一份有限保障策略（enabled / cadence / observe_only），基于这些事实
发起**只读手动评估**，得到可审计的评估历史和确定性人工建议。

本切片**不采集设备、不下发配置、不自动修复、不做后台调度**——为后续 scheduler /
repair 预留契约，但明确不做。

## 2. 范围（本包）

- 数据模型 + Alembic migration 014：`sdn_assurance_policies`（每 VPC 至多一条）、
  `sdn_assurance_runs`（追加式评估历史）。
- API（沿用 `/api/sdn` + APIResponse）：
  - GET/PUT `/vpcs/{vpc_id}/assurance-policy`（缺失 GET 返回明确默认值且不写库；
    PUT 乐观并发 version）。
  - POST `/vpcs/{vpc_id}/assurance-runs`（trigger 仅 manual；零设备 I/O、零业务写副作用）。
  - GET run list（limit/before 稳定分页）/ run detail（白名单输出）。
- 评估语义：复用 S2 projection/attention 契约；overall ∈
  {healthy, attention, blocked, insufficient_evidence}；建议只允许确定性码
  （review_scope / refresh_evidence / inspect_drift / resolve_ambiguity /
  repair_context / review_exception），不含设备命令/自动修复/根因暗示。
- 前端 API client 只补 typed 调用入口，不做页面（Codex 后续负责 S3 页面）。

## 3. 非目标（明确不做）

- scheduler / 自动触发（cadence 只记录产品意图；trigger=scheduled/event 枚举保留不实现）。
- 任何设备 I/O（collector/executor/Netconf/SSH）、deployment/binding/operation/
  snapshot/claim 写入、vpc.version bump。
- 自动修复 / 根因结论（建议是确定性人工动作码）。

## 4. 兼容性

- 纯新增表/端点，零现有行为改动；`get_vpc_state_projection` 载荷构建抽为
  `build_projection_payload` 供两处复用（行为保持字节等价，回归已验证）。
- 迁移 014 幂等（空库与 013 旧库均可升级、可降级）。
