# Readiness

状态：**READY_FOR_CODE_REVIEW**（受控修复提案后端切片；非 S3/NEXT 成品，未宣称 Codex 已通过）。

## 已交付（qa-backend 容器验证，真实 SQLite）

- 持久化 remediation plan（迁移 017 `sdn_remediation_proposals`，ORM/迁移一致、幂等可升降）
  + 创建/列表/详情/取消 API（`/api/sdn/vpcs/{vpc_id}/remediation-proposals*`）。
- 创建仅接受 completed run 中 blocking confirmed_drift 的真实 item，服务端从 run 白名单
  取 device/item，不信任调用方重填；创建时重读投影，VPC version / 分类 / 证据快照 / Leaf
  角色 / active maintenance 例外任一不满足 → 明确拒绝或 stale。
- action 固定 redeploy_vpc_on_device；VPCConfigPlanner dry-run 只提取语义单元名/描述，
  API/DB 均不保存或返回原始 CLI/凭据/planned_config；响应列出重建单元、保留项与
  executed=false 边界。
- 幂等：同 run+item 返回同一提案（DB 唯一约束兜底并发）；读取时保守标 stale（短事务
  CAS）；取消仅 proposed → cancelled 且重复幂等。
- 全路径零设备 I/O、零业务副作用：不创建 deployment/operation/binding/claim、不改
  vpc.version、无 confirm/apply 端点。
- 对抗测试 **16 条**（准入/防陈旧/真实空表并发/陈旧后幂等重试/读取标 stale/取消/
  白名单无密钥/零设备 I/O 零副作用）+ 完整迁移测试 **20 条**（含 017 升降 3 条）=
  **36 passed**。
- 直接受影响回归 **169 passed**（清单见 review-manifest.json）。

## 未实现 / 未验证边界（诚实声明）

- 提案仅 proposed/stale/cancelled，无执行/确认/回滚端点；下一轮人工确认执行由 Codex 契约
  复审后另行交付。
- 未做多进程真机并发压测（唯一性由 DB 唯一索引保证，与 S3-002/S3-003 同模式）；
  未做前端展示（前端由 Codex 契约复审后实现）；评估基于合成/历史事实，非真实多 VPC 数值。
- 预存在 ops_toolkit_paramiko 环境失败不在本包范围（未跑全量测试）。

## 请求复审要点

1. 防陈旧门槛是否过严/过松（VPC version / 最新快照 / 分类 / 例外四重 CAS）。
2. summary_json 白名单是否足以支撑前端"将重建单元 + 保留项 + 尚未执行"展示。
3. 迁移 017 升降与 ORM 命名一致性。
