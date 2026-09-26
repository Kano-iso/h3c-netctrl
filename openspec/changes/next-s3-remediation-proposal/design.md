# Design

## 1. 数据模型与迁移 017

新表 `sdn_remediation_proposals`（SQLite，具名约束/索引模式与 015/016 一致）：

| 列 | 语义 |
|---|---|
| vpc_id / run_id / device_id | 归属（FK ondelete=CASCADE；父删除级联清理，历史不级联伪造成功） |
| item_key | run 白名单 item 的稳定 key |
| action / category | 固定 `redeploy_vpc_on_device` / `confirmed_drift`（DB CHECK 防御） |
| vpc_version_at_create | 创建时 VPC version（防陈旧 CAS 锚点） |
| policy_version | 创建时 run.policy_version |
| evidence_snapshot_id | 创建时证据快照 id（来自 run item source_refs） |
| status | proposed / stale / cancelled（CHECK） |
| expires_at | 提案过期时间（TTL，配置 `REMEDIATION_PROPOSAL_TTL_SECONDS` 默认 86400） |
| fingerprint | 稳定 SHA-256（vpc/run/item/device/action/category/版本/证据 全量摘要） |
| summary_json | 脱敏摘要：语义单元（planner dry-run 的 name/description）+ 保留项 + executed=false；绝不含 CLI/凭据/planned_config |
| created_at / updated_at | 时间戳 |

唯一索引 `uq_sdn_remediation_proposals_run_item(run_id, item_key)`：每个 run+item 至多
一条提案，重复创建/并发创建幂等兜底（与 S3-002 CR61 同模式）。

迁移 017 幂等可升降：upgrade 表不存在才建（含索引），重复升级 no-op；downgrade 整表删除
（索引随表删除），不触碰 016 的 runs.event_key 结构。ORM `__table_args__` 用
`Index(name, cols, unique=True)` 与迁移命名一致（`test_orm_create_all_matches_017_*`）。

## 2. 准入与防陈旧（创建）

```
run = completed 且 run.vpc_id == vpc_id                          # 否则 run_not_found
item = run.items_json 中 key 匹配且 severity=blocking 且
       category=confirmed_drift 且 item.vpc_id == vpc_id         # 否则 item_not_found
device = item.device_id；必须仍 _is_sdn_fabric_member            # 否则 device_not_leaf
vpc 上存在该 device 的 deployment（归属一致）                     # 否则 ownership_mismatch
facts.vpc_version == vpc.version                                 # 否则 stale(vpc_version)
当前 projection 重新评估：同 key 仍 confirmed_drift+blocking     # 否则 stale(classification)
最新 snapshot.id == item source_refs[].snapshot.snapshot_id      # 否则 stale(evidence)
无 active maintenance_pause 例外                                 # 否则 active_maintenance_exception
→ planner dry-run → summary（仅语义单元名/描述）→ 插入 proposed
```

- 服务端只读 body 的 `run_id` / `item_key`；device/action 一律取自 run 白名单 item。
- run/item 白名单确认后先查同 (run_id, item_key) → 已存在则刷新其陈旧状态并幂等返回
  既有行（duplicate），即使证据后来变化也不把重试误报成一次新建失败；
  并发双写撞唯一索引 → rollback 重查并刷新后返回既有行；非该唯一键导致的
  IntegrityError 不得被吞掉。
- 每个条件失败都返回明确 error_key（HTTP 200 + success:false，项目 APIResponse 语义）。

## 3. 读取时保守标 stale（短事务/CAS）

`get_proposal` / `list_proposals` 对每条 proposed 重新核对：expires_at 未过期、当前
vpc.version == vpc_version_at_create、最新 snapshot.id == evidence_snapshot_id、设备仍为
EVPN Leaf、当前投影同 key 仍 confirmed_drift+blocking、无 active maintenance 例外。任一
不满足 → `UPDATE ... WHERE id AND status='proposed'` 标 stale（CAS，绝不覆盖 cancelled）。
取消：仅 proposed → cancelled 的 CAS；重复取消/已 stale 幂等返回当前行，cancelled 不被
复活也不被改写为 stale。

## 4. 影响范围（planner dry-run，无设备 I/O）

`VPCConfigPlanner(H3cV7Adapter()).plan_vpc_create(vpc, tenant, dry_run=True)` → 5 个语义
unit（vsi-l2/evpn/l3vpn/vsi-l3/global）。只提取 `(name, description)` 存入 summary；
`cli_commands` / `xml_payloads` 绝不落库、绝不出现在 API。响应列出 units、保留项
（tenant/vpc/other_leaves/port_bindings 不删除）与 `executed: false` 边界。

## 5. 端点

- `POST /api/sdn/vpcs/{vpc_id}/remediation-proposals`（body: run_id, item_key）
- `GET  /api/sdn/vpcs/{vpc_id}/remediation-proposals`（列表，读取时保守标 stale）
- `GET  /api/sdn/vpcs/{vpc_id}/remediation-proposals/{proposal_id}`（详情）
- `POST /api/sdn/vpcs/{vpc_id}/remediation-proposals/{proposal_id}/cancel`

无 confirm/apply/execute 端点；proposal 序列化只含白名单字段与语义摘要。

## 6. 零设备 I/O / 零业务副作用

创建/读取/取消全程只读 DB + 一次 projection 评估 + planner dry-run（纯计算）：不调用
executor/collector/Netconf/SSH，不创建 deployment/operation/binding/claim，不改
vpc.version，不新增 run。对抗测试以业务表计数 + vpc.version + run 计数不变 + planner
call_count==1 证明。
