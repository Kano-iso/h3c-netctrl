# Tasks

- [x] 1. 数据模型：`SdnRemediationProposal`（vpc/run/device FK + item_key + 固定
       action/category + vpc_version_at_create + policy_version + evidence_snapshot_id +
       status/expires_at/fingerprint/summary_json + created/updated）+ 具名唯一索引
       `uq_sdn_remediation_proposals_run_item`（ORM Index 与迁移命名一致）+ CHECK 防御；
       SdnVpc 关系级联
- [x] 2. 迁移 017：建表 + 唯一/普通索引，幂等可升降（重复升级 no-op、降级整表删除且保留
       016 runs.event_key 结构）
- [x] 3. 服务 `services/sdn_remediation.py`：create_proposal（准入 + 防陈旧全过才生成；
       服务端从 run 白名单取 device/item；planner dry-run 只取语义单元名/描述；幂等/
       并发唯一兜底）/ get_proposal / list_proposals（读取时保守标 stale 的 CAS）/
       cancel_proposal（仅 proposed → cancelled）/ serialize_proposal（白名单 + 无 CLI/
       凭据）
- [x] 4. 路由 `routers/sdn_remediation.py`：POST 创建 / GET 列表 / GET 详情 / POST 取消，
       沿用 `/api/sdn/vpcs/{vpc_id}` 风格与 APIResponse 语义；注册 main.py；新增
       i18n_keys REMEDIATION_* 错误键
- [x] 5. 对抗测试 `test_s3_004_remediation_proposal.py`（16 条）：准入/防陈旧（VPC 版本/
       分类/证据/例外/非 Leaf）/ 幂等并发唯一 / 读取保守标 stale（CAS）/ 取消幂等 /
       陈旧后的重复请求仍返回同一提案 / 白名单无 CLI 凭据（API + DB 双层）/
       零设备 I/O 零业务副作用（planner 仅 1 次、
       vpc.version 与业务计数不变、无 confirm/apply 路由）；迁移 017 3 条
- [x] 6. OpenSpec change `next-s3-remediation-proposal` + review-manifest 扩展 +
       collaboration.md 索引
