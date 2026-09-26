# Proposal

## 1. Why

S3-001 提供只读保障评估与白名单历史，S3-002/S3-003 提供周期与事件评估通道，但 S3 只到
"发现 `confirmed_drift` + `inspect_drift` 建议"，没有可审计、防陈旧的修复提案。S3-004
把 S3 推进到"受控修复提案"：**只生成提案、绝不执行设备配置**，为下一轮人工确认执行建立
防陈旧边界。

## 2. 范围（本包）

- 持久化 remediation plan（迁移 017 新表 `sdn_remediation_proposals`，ORM/迁移一致、
  幂等可升降）。至少保留：VPC、assurance run、item key、device、category/action、创建时
  VPC version、policy version、证据 snapshot id、状态 proposed/stale/cancelled、过期时间、
  稳定 fingerprint、脱敏摘要（summary_json）、created/updated。
- 创建/读取列表/详情/取消 API，沿用 `/api/sdn/vpcs/{vpc_id}` 风格；创建仅接受 completed
  run 中 severity=blocking、category=confirmed_drift 的真实 item；服务端从 run 白名单
  items 取 device/item，**不信任调用方重填设备或动作**。
- 创建时重新读取当前 projection，必须同时满足：VPC/run/item 归属一致、当前 VPC version
  与 run facts 一致、目标仍是 EVPN Leaf 且当前仍 confirmed_drift、当前最新 snapshot 与
  run source_refs 指向同一证据、没有 active maintenance exception；任一不满足 → 明确拒绝
  或返回 stale，不生成可用提案。
- 提案 action 固定 `redeploy_vpc_on_device`，使用既有 VPCConfigPlanner **dry-run** 计算
  语义 unit 名称与影响范围；API/DB 不保存、不返回原始 CLI、凭据、planned_config。响应
  清楚列出将重建的语义单元、保留项（租户/VPC/其他 Leaf/端口绑定不删除）与边界（尚未执行）。
- 幂等：重复请求同 run+item 返回同一 proposed plan；并发由 DB 唯一约束
  `uq_sdn_remediation_proposals_run_item` 兜底；每个 run+item 至多一条提案。
- 读取时保守标 stale（短事务/CAS）：VPC version / 最新 snapshot / 当前分类 / 例外状态任一
  变化 → proposed 标 stale，绝不仍显示可执行。取消仅 proposed → cancelled，重复取消幂等。
- 全路径零设备 I/O：不调用 executor/collector/Netconf/SSH，不创建
  deployment/operation/binding/claim，不改 vpc.version；不实现 confirm/apply 端点，不把
  proposed 写成已修复。

## 3. 非目标（明确不做）

- 不执行/下发/回滚任何设备配置；无 confirm/apply/execute 端点。
- 不做自动修复或根因结论；不做跨 VPC 聚合提案；不做提案生命周期之外的状态机。
- 前端本轮零改动（仅服务端提供 API 与只读字段），由 Codex 契约复审后实现。

## 4. 复用与一致

复用 S3-001 的 `build_projection_payload` / `evaluate_assurance` / 白名单 item 与 S2 的
VPCConfigPlanner dry-run / `_is_sdn_fabric_member` / `_serialize_scope_exception` / 最新
快照查询——不另造第二套 VPC 引擎。
