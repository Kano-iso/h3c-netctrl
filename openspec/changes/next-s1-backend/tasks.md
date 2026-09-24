## 1. 数据模型与迁移

- [x] 1.1 新增 `SdnPlan` / `SdnOperation` / `SdnAttempt` / `SdnAttemptUnit` / `SdnResourceClaim` / `SdnIdentitySnapshot` ORM（列与约束见 design.md §1）— `app/models.py`
- [x] 1.2 存量表加列：`sdn_vpcs.version`、`sdn_port_bindings.{version, created_by_operation_id, last_changed_by_operation_id, operation_id}`、`sdn_deployments.{operation_id, version, claimed_at, claimed_by_attempt_id}`、`sdn_validation_snapshots.{operation_id, attempt_id, collection_started_at, collection_completed_at}` — `app/models.py`
- [x] 1.3 迁移 `012_add_sdn_operations.py`：无表建表、缺列加列、缺索引补索引，部分唯一索引 `(resource_key) WHERE released_at IS NULL`（覆盖 held 与 ambiguous），证据表不建父外键（用 sqlite_master/PRAGMA 幂等守卫）
- [x] 1.4 歧义 owner 并发测试：`test_ambiguous_claim_blocks_new_owner`（held→ambiguous 仍独占）
- [x] 1.4 迁移测试（真实 alembic，非 create_all）：`test_sdn_migration.py`（012 upgrade 建表加列+部分唯一索引、idempotent、downgrade）。注：项目为棕地迁移链，无法从空库 upgrade head（既有 003/004 对 create_all 预建的 devices/logs 做 ALTER），故用 stamp 011 + 旧表骨架隔离验证 012

## 2. 资源声明与并发仲裁（R1/R3）

- [x] 2.1 `sdn_resource_claims` 原子获取/释放（部分唯一索引互斥，按 rank 序升序获取、反序释放）— `ordered_claim_keys`/`acquire_claims`/`release_claims`；测 `test_ordered_claim_keys_uses_rank_not_lexicographic`/`test_acquire_same_key_conflicts`/`test_release_allows_reacquire`
- [x] 2.2 deployment CAS：`UPDATE ... SET status='running', claimed_at=now() WHERE id=:id AND status='pending'`（新增 `unknown` 终态）— executor `execute()` + `claim_deployment`；测 `test_claim_deployment_cas`/`test_concurrent_deployment_claim_single_winner`
- [ ] 2.3 TTL 不自动转移：`mark_claims_ambiguous` 已实现，但无后台 TTL 扫描器（沿用 S1-004 默认「认领无 TTL 自动释放，仅显式 reconcile」）
- [ ] 2.4 并发测试：已测「同 deployment 并发认领 + 旧入口被 claim 阻断」（`test_concurrent_deployment_claim_single_winner`/`test_legacy_create_port_binding_blocked_by_claim`）；「同 {device_id, if_index} 双新入口争抢」全矩阵未覆盖

## 3. 幂等与指纹（R1/R3）

- [x] 3.1 `idempotency_key` UNIQUE + `fingerprint`（规范化字段排序的 SHA-256）— `compute_access_fingerprint`/`resolve_operation`
- [x] 3.2 同 key 同指纹→200+duplicate；同 key 异指纹→409；跨范围 key→404（不泄漏）— `resolve_operation`；测 `test_resolve_operation_duplicate_conflict_and_scope`/`test_access_duplicate_returns_same_operation`
- [x] 3.3 幂等测试：同 key 同 payload 返回同 operation 且计数不增；异 payload 409；跨租户不泄漏 — 见 3.2 用例

## 4. 逐单元执行与崩溃对账（R1/R3）

- [x] 4.1 `sdn_attempt_units` 状态机 `not_started→started→(succeeded|failed_known|unknown)`，I/O 前写 started、I/O 后写终态+证据 — `mark_unit_started`/`mark_unit_done`
- [x] 4.2 重放规则：`mark_unit_started` 对非 not_started 阻塞（已测 `test_started_unit_without_completion_blocks_replay`）；「依赖全 succeeded 才可重放」已实现（`AttemptUnitHooks.before_unit` 校验前置单元全 succeeded）— 测 `test_cr18_dependency_prior_not_succeeded_blocks`
- [x] 4.3 reconcile 显式动作（kind=reconcile）读设备对账；读/刷新绝不触发设备 I/O — `POST /operations/{id}/reconcile` + `GET` 只读
- [x] 4.4 崩溃窗口测试：「started 无终态阻塞重放」+「设备已改/终态未落库」（`test_cr13_*`）「超时无结果」（`test_cr12_unknown_keeps_claims_ambiguous_and_blocks`）「失主 claim」（`test_cr4_release_requires_owner_and_scoped`）

## 5. 前置部署证明与预览（R2/R3）

- [x] 5.1 前置部署证明：vpc.version + 最近相关成功变更 + 新鲜观测；delete 失效规则 — `_l2_ready_status`；测 `test_access_missing_predeploy_blocks`
- [ ] 5.2 四项 deferred preflight 不得当通过：执行前权威元数据重拉已实现，但设备侧 4 项 preflight 证据仍 deferred（真机验收项）
- [x] 5.3 服务端预览 `sdn_plans`（plan_id 不可变 + 指纹 + 版本快照 + 10 分钟过期）；执行重算语义哈希比对，不一致 plan_stale — 测 `test_preview_persists_plan_only`/`test_access_stale_plan_rejected`/`test_plan_expire_and_consume`
- [x] 5.4 执行前用绕过缓存的分裂 API 重拉 sdn_role/protected_interfaces；ctrl 不可用阻塞 — `internal_api.get_device_fresh` + `_get_device_authoritative(fresh=True)`
- [ ] 5.5 反例测试：已测 create 缺失 + stale plan；「create 后 delete」「旧快照晚写入」「网关单独撤回」「权威元数据不可用」未覆盖

## 6. 证据与撤回（R4/R5）

- [x] 6.1 每次执行/验证稳定 attempt_id + started/completed + scope + config_version；因果断言 `collection_started_at >= deployment.completed_at` — `complete_access`；测 `test_complete_records_causal_window`
- [x] 6.2 缓存 600s 只作带时效历史，不回填成新事实；四维分离（execution/config_readback/business_validation/evidence）在 attempt/unit/evidence_json 可区分 — 独立四维断言用例 `test_cr17_*`
- [x] 6.3 撤回：created_by_operation_id 不可变 + version/last_changed 可变；所有者==本操作 且 version 未变 且无后续实际引用 — `withdraw_access`
- [x] 6.4 撤回测试：`test_withdraw_preserves_shared_resources` + 「仅读取不 bump version」`test_cr18_read_does_not_bump_version` + 「实际 rebind 阻断」`test_cr18_withdraw_blocked_by_new_reference` + 「回读失败→unknown」`test_cr12_withdraw_unknown_keeps_all_claims` + 「重复撤回幂等」`test_cr18_withdraw_idempotent`

## 7. 历史保留与终端视图（R6）

- [x] 7.1 证据表非级联 + `sdn_operations.scope_json` 身份快照；父删除先写 `sdn_identity_snapshots` 再级联删除 — `delete_tenant`/`delete_port_binding`；测 `test_delete_tenant_keeps_identity_snapshot`
- [x] 7.2 终端读取视图：`access-overview` 提供 expected_host_ip + 绑定 + 最近快照 + `observations`（带 source/scope/timestamp 的 ARP/MAC/EVPN 观测明细，远端 Type-2 标 remote 不挂本地端口）— 测 `test_cr18_overview_observations_filter_remote`
- [x] 7.3 历史测试：删除 tenant 后操作历史仍可追溯 — `test_delete_tenant_keeps_identity_snapshot`

## 8. 契约与 QA（R8）

- [x] 8.1 修订 `contract-examples.json`（补 attempt/unit 状态、claim/reconcile、崩溃 unknown、非级联历史样本）
- [x] 8.2 用 `qa/docker-compose.qa.yml` 跑 mock 测试；迁移测试真实 alembic；命令 `python -m pytest tests/<file> -q` — 全量 504 passed / 55 skipped / 11 failed（11 失败为基线段 `_paramiko_batch_exec` 模块缺失环境问题，非本次引入）
- [x] 8.3 重新校验 OpenSpec、JSON、compose config 自洽 — 见 handoff §1/§4

## 9. 交接

- [x] 9.1 更新 `handoff.md`（真实校验命令与结果、未实现项、待 Codex 决定问题）
- [x] 9.2 校验文件完整性，标注 `READY_FOR_CODE_REVIEW` — CR18 SHALL（依赖重放/崩溃窗口/撤回矩阵/终端视图明细）已实现+测试；剩余 `[ ]` 为非阻断覆盖（2.3 无后台 TTL 扫描器为设计决定、2.4 并发全矩阵、5.2 真机 preflight 受「禁止设备 I/O」约束、5.5 反例测试），均诚实标注

## 10. S1-007（CR11-CR18 第二轮复审修正）

- [x] 10.1 CR11 owner-aware claim 复用：`acquire_or_reuse_claims` + apply 复用已有 claim
- [x] 10.2 CR12 unknown/withdraw claim 生命周期：success/failed 释放完整 scoped，unknown 保留 + `mark_operation_claims_ambiguous`
- [x] 10.3 CR13 reconcile 按 action/期望状态一致收尾：`_reconcile_outcome`（port_bind→active；port_unbind→scoped 缺失）
- [x] 10.4 CR14 逐单元 CAS 阻断 I/O + legacy 多单元：`AttemptUnitHooks` 返回 bool + executor 阻断 + `ensure_legacy_apply_operation` 真实 unit 列表
- [x] 10.5 CR15 迁移 012 列类型/唯一约束/复合索引：claimed_at DateTime + `uq_attempt_unit` + `ix_identity_kind_id_created` + `evidence_json`
- [x] 10.6 CR16 主机观测不混入远端 Type-2：`_build_host_observations` + `_ip_exact_match`
- [x] 10.7 CR17 四维验证不互相冒充 + ping 诚实持久化：`complete_access` 四维 + `_run_gateway_ping` + `evidence_json`
- [x] 10.8 CR18 文档不提前宣称完成：handoff/readiness/tasks/review-response 同步现状，`tasks.md 9.2` 标注 READY_FOR_CODE_REVIEW

## 11. S1-008（CR19-CR23 第三轮复审修正）

- [x] 11.1 CR19 reconcile 真正解析 unknown unit：`mark_unit_reconciled`（started|unknown→terminal + rowcount 逐项校验）+ 未全解析不释放 claims + 原 attempt 由 unit 重推
- [x] 11.2 CR20 port_bind 需目标端口 scoped 正向证据：`_scoped_port_evidence`（接口回读成功 + service-instance/xconnect vsi 结构化匹配）
- [x] 11.3 CR21 port_unbind 不把采集失败当配置缺失：命令缺失/success=false/CLI error→insufficient；结构化语法匹配替代裸数字
- [x] 11.4 CR22 complete/validate claim 与终态守卫：幂等/终态不改写 + owner-aware claims + 只选原 port_bind deployment
- [x] 11.5 CR23 主机 IP/端口同一条本地记录：`_build_host_observations` 逐行关联 + 命令失败不产生 observation=true

## 12. S1-009（CR24-CR26 第四轮复审修正）

- [x] 12.1 CR24 真实 reconcile 采到待对账目标接口：`SdnValidationCollector.sync` 增加 `scope_bindings`，reconcile 传 binding scope，普通周期采集边界不变
- [x] 12.2 CR25 unknown validation 恢复路径：complete 幂等仅限确定完成（succeeded/failed_known），unknown + 执行已成功允许显式重试新建 validate attempt
- [x] 12.3 CR26 CLI 错误 output/结构化字段共同识别：`_scoped_port_evidence` 复用 `_has_display_error(output)`
- [x] 12.4 真实链路反例：`test_s1_009_adversarial.py`（3 CR24 + 1 CR25 + 3 CR26）走真实 `_commands`/`_snapshot_data`，只 mock SSH/凭据

## 13. S1-010（CR27 第五轮复审修正）

- [x] 13.1 CR27 原子并发准入：`claim_validation_admission` 单行 CAS（awaiting_validation|unknown→validating）+ op.status `validating` 中间态
- [x] 13.2 complete/validate 赢者同事务建 attempt + claims；输家返回 `sdn.operation_in_progress`（新增 error key）
- [x] 13.3 准入后崩溃留 `validating` + claimed attempt 痕迹，不回退 awaiting_validation、不重放
- [x] 13.4 真实线程/barrier 反例：`test_s1_010_adversarial.py`（并发赢家 + unknown 恢复并发 + 崩溃痕迹守卫）

## 14. S1-011（CR28 第六轮复审修正）

- [x] 14.1 CR28 跨动作原子准入：`claim_action_admission` 泛化（from_statuses→to_status）+ `withdrawing` 中间态 + withdraw 设备 I/O 前 CAS 准入
- [x] 14.2 validate/withdraw 互斥：validate 在 validating/withdrawing 下返回 in-progress；withdraw 在 validating/withdrawing 下返回 in-progress
- [x] 14.3 条件收尾 CAS：`finish_action`（WHERE status=from_status）——零行更新不覆盖现状、不误释放 claims + late completion 诊断
- [x] 14.4 withdraw 允许/拒绝状态清单：WITHDRAW_FROM_STATUSES + withdrawn 不可逆幂等
- [x] 14.5 真实线程/barrier 反例：`test_s1_011_adversarial.py`（validate 先赢 + withdraw 先赢 + 迟到收尾不覆盖 withdrawn）

## 15. S1-012（CR29 第七轮复审修正）

- [x] 15.1 CR29 apply 准入：`applying` 中间态 + apply 设备 I/O 前原子 CAS `awaiting_wiring → applying`（与 validating/withdrawing 互斥）
- [x] 15.2 apply 条件收尾 CAS `applying → awaiting_validation|failed|unknown`（迟到/零行不覆盖、不误释放 claims）
- [x] 15.3 deployment CAS 失败即停：`SDN_DEPLOYMENT_NOT_PENDING` 停止上层收尾，不推导 unknown、不误标 claims
- [x] 15.4 auto_apply=True 内联 `claimed` 阶段兼容（阻挡 complete/withdraw，无第二套设备写窗口）
- [x] 15.5 真实线程/barrier 反例：`test_s1_012_adversarial.py`（apply 先赢 + withdraw 先赢 + 并发 apply 单赢家 + 迟到收尾）

## 16. S1-013（CR30-CR31 第八轮复审修正）

- [x] 16.1 CR30 代际令牌：`sdn_operations` 新增 `active_attempt_id`/`active_started_at` 持久列（ORM + 012 migration 幂等）
- [x] 16.2 准入/收尾 CAS 绑定 token：`claim_action_admission`/`finish_action` 匹配 phase + active_attempt_id，成功原子清空 token
- [x] 16.3 准入输家回滚临时 attempt（validate/withdraw/reconcile）
- [x] 16.4 CR31 reconcile 动作仲裁：`unknown → reconciling` 原子准入 + `claim_stale_takeover`（lease 判定失联）+ withdrawn 不可变
- [x] 16.5 reconcile 终态写入/deployment/binding/claims 在持有 reconciling+token 时才发生；collector 失败条件收尾到 unknown
- [x] 16.6 真实线程/barrier 反例：`test_s1_013_adversarial.py`（ABA×3 + live 拒绝×3 + unknown 单赢家 + stale lease + 迟到收尾）

## 17. S1-014（CR32 第九轮复审修正）

- [x] 17.1 reconcile 拆分 active_attempt（token 指向的失联动作）与 effect_attempt（设备写副作用 execute/withdraw）
- [x] 17.2 stale takeover 只把 active_attempt 及其 started unit 标 unknown，写入 stale_takeover 证据；token 无效/跨 operation 保守拒绝
- [x] 17.3 effect_attempt 已确定终态不降级；validate 失联按 port_bind 回读恢复到 awaiting_validation（不冒充完整验证成功）
- [x] 17.4 真实线程/回读反例：`test_s1_014_adversarial.py`（validating/applying/withdrawing 接管 + token 无效/跨 operation 拒绝）

## 18. S1-015（CR35 第十轮复审修正）

- [x] 18.1 唯一 phase→kind 映射 `ACTIVE_PHASE_EXPECTED_KIND` + 可接管状态 `STALE_TAKEOVERABLE_ATTEMPT_STATUSES`（claimed/running）
- [x] 18.2 `claim_stale_takeover` 单条原子 UPDATE + EXISTS 同时证明 op phase/token/lease 与 active attempt 的 operation/kind/status
- [x] 18.3 条件式 `mark_attempt_stale`（仅 claimed|running→unknown，rowcount==1 才继续；零行回滚接管）
- [x] 18.4 真实线程/barrier 反例：`test_s1_015_adversarial.py`（错 kind×3 + 终态×4 + 活动态×2 + CAS 竞态）

## 19. S1-016（CR36 第十一轮复审修正）

- [x] 19.1 design/spec 冻结两套门禁语义（VPC create preflight「VNI 应不存在」deferred vs terminal predeploy「VSI 必须存在」）
- [x] 19.2 `_l2_ready_status` 收紧：绝对新鲜度（600s）+ 采集晚于配置完成 + 命令成功无 CLI 错误 + validation_details 目标 scoped 条件 + validation_result=active（CR36 当时口径；CR37 已移除 `validation_result=active` 与全命令遍历，CR38 已按目标 RD 归属 type3）
- [x] 19.3 VPC 版本因果：`_create_sdn_deployment` 固化 `deployment.version = vpc.version`；`_l2_ready_status` 校验 `create.version == vpc.version`
- [x] 19.4 execute 在证据不足时强制重新取证（只读 display），采集失败在消费 plan 前阻断（零业务副作用）；preview 只展示已有证据
- [x] 19.5 `SdnPreflight` deferred `success=True` 明确为 create 路径 blocker/后续项，不接到 terminal access
- [x] 19.6 对抗测试：`test_s1_016_adversarial.py`（fresh 放行 + TTL/因果/状态/命令/CLI/缺项/非法 JSON/版本 阻断 + execute 取证失败零副作用 + create/terminal 语义反例，13 条）

## 20. S1-017（CR37 第十二轮复审修正）

- [x] 20.1 design/spec 冻结 terminal L2 必需条件（`bgp_peer_established`/`vsi_exists`/`vsi_up`/`type3_present`）与 L2 所需命令映射（BGP peer / VSI / Type-3）
- [x] 20.2 `_l2_ready_status` 移除「整张快照 `validation_result==active`」与「遍历整张快照所有命令」两处 L3 耦合；`raw_has_error` 按 L2 命令输出重算
- [x] 20.3 无关 L3/Vsi-interface/ARP 命令失败不拖垮纯 L2 门禁；支撑 BGP/VSI/Type-3 的命令缺失/失败/CLI 错误仍 conservative unknown
- [x] 20.4 网关/L3 健康继续由 complete 业务验证 `l3_gateway_ready` + ping 维度表达，不得用 L2 成功冒充 L3 成功
- [x] 20.5 保留 S1-016 的 TTL/配置完成时间/版本因果/execute 强制刷新与失败零业务副作用
- [x] 20.6 对抗测试：`test_s1_017_adversarial.py`（degraded+L2 健康 ready、L3 命令失败 ready、L2 条件/命令分别阻断、complete 仍表达 degraded，10 条）+ 修正 S1-016 一条受影响用例（validation_result 不再是 L2 门禁）

## 21. S1-018（CR38 第十三轮复审修正）

- [x] 21.1 `SdnValidationCollector._type3_scoped(text, vni)`：按 `Route distinguisher:` 分块，逐块精确 RD 等值比较，只在目标 `1:{vni}` 块中发现 `[3]` 才为真；1:2000 与 1:20000 不串匹配；目标 RD 缺失/只有 [2]/无法解析 → false
- [x] 21.2 `_validate()` 的 `type3_present.ok` 改用 `_type3_scoped(bgp_evpn_text, vpc.vni)`，替代 `"[3]" in text`
- [x] 21.3 清理 CR36/CR37 冲突口径：readiness S1-016、handoff CR36、review-response 历史 CR36、review-manifest CR36、tasks 19.2 标注「CR36 当时口径，已被 CR37/CR38 取代」，修正已重命名测试 `test_predeploy_validation_result_not_a_l2_gate`
- [x] 21.4 对抗测试：`test_s1_018_adversarial.py`（目标 RD [3] true、其他 RD [3]/目标 [2] false、目标 RD 缺失 false、1:2000 vs 1:20000、多 RD 中/末位、真实 `_validate` scoped、terminal 门禁 unknown，8 条）

## 22. S1-019（真机生命周期验证）

- [x] 22.1 新增默认 skip 真机集成测试 `backend/tests/test_s1_019_reallife.py`：`integration` 标记 + `S1_019_REAL=1` + `S1_019_REAL_HOST=192.168.100.5` 三重门；凭据只读 `.env` 注入、Fernet 进程内加解密、不落盘/打印；业务写入全走 backend API/executor（LSTN→SSH22 CLI）；try/finally 补偿撤回
- [x] 22.2 新增恢复清单 `openspec/changes/next-s1-backend/recovery-manifest-s1-019.md`（时间戳/目标设备/唯一测试名/基线/预期对象/清理项/原子状态），本轮真实对象（VSI `vpc0001`、RD `1:20000`、Vsi-interface1000、sdn_l3vpn、vxlan global、GE1/0/10 service-instance 3200）全部记录
- [x] 22.3 文档/工具别名一致性修正：`docs/ops-toolkit.md` §设备命名约定 删除错误的 `Leaf-05: .6`（.6 实为 SWD/Spine，Router ID 1.1.1.1），注明 `_lib.sh` 未实现 `leaf-05`；新增 `backend/tests/test_s1_019_doc_alias.py`（leaf-04→.5、leaf-05 不映射、test/spine-01 仍解析）
- [x] 22.4 真机一轮（.5 SWC/S6850 T7064P15/LSTN）：VPC create/apply ✅、display+目标 RD `1:20000` Type-3 `[3]` ✅、access preview ✅、access execute 被 predeploy gate `sdn.predeploy_unknown` 诚实阻断（`vsi_up=False`，无 AC/tunnel 时 VSI State Down）、VPC withdraw ✅
- [x] 22.5 兜底清理（fallback）：ops-toolkit `undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable`（产品保留的共享对象，基线不存在，前后 readback）
- [x] 22.6 最终 readback：VSI 空 / routes 0 / 无 sdn_l3vpn / 无 vxlan / GE1/0/10 回基线；未 save/改 startup-config；access apply/complete 因 vsi_up 数据面边界未端到端验证（诚实标注未验证，非伪造成功）
- [x] 22.7 QA：`test_s1_019_doc_alias.py` + `test_s1_019_reallife.py`（默认 skip 验证）+ S1-016~018 门禁 + validation/access/service/migration = **66 passed / 1 skipped**；`openspec validate --strict` 通过、`git diff --check` 干净

## 23. S1-020（修复首次接入自阻断 + .5 真机生命周期）

- [x] 23.1 对抗测试先行证明 S1-019 基线失败：`test_s1_020_adversarial.py`（无绑定+vsi_up=Down 应 ready、active/expanding 绑定+vsi_up=Down 应 block、绑定+vsi_up=True 应 ready、unbound/planned 不误判、preview/execute 同语义、force refresh 零副作用），修复前 5 failed/4 passed，修复后 9 passed
- [x] 23.2 实现 `_l2_ready_status` 动态 `vsi_up` 必需：目标 Leaf 无 active/expanding 本地绑定时 vsi_up 不作为门禁（首次 AC bootstrap），已有绑定时仍必需（Down 保守阻断）；其余三项 + 版本因果/TTL/配置完成时间/命令完整性/CLI 错误/BGP peer/VSI 存在/目标 RD Type-3 门禁不删不放宽
- [x] 23.3 修正 S1-017 `test_l2_condition_false_blocks` 参数化：vsi_up 移出「始终必需」列表（动态必需见 S1-020），更新 docstring
- [x] 23.4 重写 S1-019 真机测试：不再把 predeploy 阻断断言为 PASS，走 preview→execute→apply→readback GE1/0/10 service-instance/xconnect→complete（无主机诚实 degraded/unknown）→access withdraw→VPC withdraw，核对 operation/binding/deployment/attempt/claim 收尾
- [x] 23.5 非真机 QA：S1-016~020 + validation/access/service/migration = 74 passed / 1 skipped（skip=reallife 默认门）；真机只跑一次完整生命周期
- [x] 23.6 同步 spec/design/tasks/readiness/handoff/review-response/review-manifest，删除「固定四项始终必需」旧结论，明确首次 AC bootstrap 与已有 AC 健康检查差异

## 24. S1-021（真机生命周期安全 Runner 与交付口径修正，本轮未触真机）

- [x] 24.1 新增唯一、可复用宿主安全 runner `openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`：默认拒绝真机（`--integration`/`S1_019_REAL=1`/精确 `192.168.100.5`/`--cleanup-shared` 四重门禁，目标非 .5 设备 I/O 前退出）；凭据仅 `.env`/环境注入不落盘；额外设备读写走 ops-toolkit 既有入口；pytest 前保存最小基线（身份/VSI/EVPN/共享对象/GE1/0/10），共享对象基线已存在→拒绝承担所有权绝不 trap 删除；进入可写阶段装 trap，成功/失败/Ctrl-C/TERM 都按恢复清单精确兜底清理（仅两条共享 undo + 上下文，无 save/越界）+ 最终 readback 回基线（返回码 0 ≠ 清理成功）；保留 pytest 原始退出码但 cleanup/readback 失败整体失败并输出 MANUAL-NEEDED；本机 flock 锁防并发
- [x] 24.2 新增不触真机对抗测试 `backend/tests/test_s1_021_runner_adversarial.py`（16 条，stub/fake 命令）：缺门禁/目标非 .5 设备 I/O 前失败、基线共享对象拒绝且无 undo、pytest 成功/失败都进 cleanup+readback、SIGINT/SIGTERM 触发 trap、pytest 失败保留非零 / cleanup/readback 失败 runner 非零、cleanup 仅两条精确 undo 无 save/越界、并发锁退出 2
- [x] 24.3 QA compose 只读挂载 qa 目录（`.:/opt/s1-qa:ro` + `S1_021_QA_DIR`），供对抗测试在容器内访问 runner/stub
- [x] 24.4 口径修正：真机测试 docstring 与 review manifest 标准跑法改为唯一 runner（裸 pytest 只是 runner 内部实现，不承担共享对象清理）；readiness 去掉「Codex 已完成代码复审」提前结论改「等待 Codex 复审」；review manifest 完成只写 `READY_FOR_CODE_REVIEW` 不写 `CODE_REVIEW_PASSED`；如实记录 S1-020 历史共享残留由测试外 ops-toolkit 精确兜底（当时无自动 runner）
- [x] 24.5 同步 design/spec/tasks/handoff/review-response/review-manifest/recovery-manifest 的运行时与恢复契约（唯一 runner 标准跑法、清理所有权边界、历史人工/监督清理与自动 runner 区分）
- [x] 24.6 QA（本轮未触真机）：`test_s1_021_runner_adversarial.py` = 16 passed；S1-016~020 + validation/access/service/migration + runner 对抗 = **90 passed / 1 skipped**；`openspec validate --strict` valid、manifest JSON valid、`git diff --check` clean

## 25. S1-022（Runner 审计目录失效时仍必须安全清理，本轮未触真机）

- [x] 25.1 启动审计目录探针：任何设备 I/O 前 `umask 077` + `setup_artifact_dir`（`mkdir -p` + 临时探针文件后删除），失败直接退出码 6（不采集基线、不跑 pytest）
- [x] 25.2 baseline 持久化门：`baseline.txt` 写失败 → 退出码 4，在 pytest/可写阶段前终止；持久化成功才设置 WRITE_PHASE
- [x] 25.3 EXIT trap 先执行后落盘：cleanup / final readback 一律先真实执行并捕获返回码/输出（命令替换），再尽力写审计文件；审计目录被删除/变只读/写失败不得阻止精确清理与回读；审计写入失败置 AUDIT_FAIL=1 → MANUAL-NEEDED + runner 最终非零但不替代 cleanup/readback；cleanup 失败不跳过 final readback
- [x] 25.4 `stub_pytest.sh` 增加 `STUB_PYTEST_HOOK`（pytest 期间删除/破坏审计目录的注入点）
- [x] 25.5 新增对抗测试 5 条（审计目录不可创建/不可写→ops 0/pytest 未调用/非零；baseline 持久化失败→不进入 pytest/可写阶段；pytest 期间删审计目录→cleanup 两条精确 undo 仍实际调用 + final readback 仍实际调用 + runner 非零提示人工；cleanup 设备失败 + 审计目录失败→仍执行 final readback）；修掉并发锁测试 `or True` 恒真断言改为真实断言
- [x] 25.6 QA（本轮未触真机）：`test_s1_021_runner_adversarial.py` = **21 passed**；S1-016~020 + validation/access/service/migration + runner 对抗 = **95 passed / 1 skipped**；`openspec validate --strict` valid、manifest JSON valid、`git diff --check` clean、凭据/越界命令扫描干净
- [x] 25.7 同步 design/tasks/handoff/review-response/review-manifest/readiness 为 S1-022 口径（审计目录可靠性 + 先执行后落盘契约）
- [x] 25.8 Codex 独立复跑与安全复审通过（95 passed / 1 skipped；stub 失效路径设备 I/O=0）

## 26. S1-023（仓库凭据卫生与 ZTP 密码边界，本轮未触真机）

- [x] 26.1 盘点全仓真实口令字面量（活动生产路径/模板/活动文档/测试/debug-*；值红化不落盘），确认唯一真实默认口令
- [x] 26.2 `schemas.py`：ZtpOnboardRequest.password 必填无默认；ZtpRecoveryOverrideRequest.password Optional(None)
- [x] 26.3 `ztp_recovery.py`：密码解析（显式→既有→ZTP_ADMIN_PASS，全缺明确 ValueError）+ state 0600 + GET/POST 响应 `_redact` 脱敏 + `password_set` 布尔
- [x] 26.4 `entrypoint.sh`：ZTP_ADMIN_PASS `${VAR:?}` 必填 fail closed + autocfg.cfg 600 + 日志无口令
- [x] 26.5 `ztp_runtime_render.py` / `ztp_onboard_callback.py`：`_require_admin_pass()` 只从环境/override 取密码，缺失明确 RuntimeError（fail closed）
- [x] 26.6 模板与文档：`autocfg.cfg.j2` / `docs/ztp-stack.md` / `.env.example` / `openspec/specs/device-crud-ui/spec.md` 移除字面量，改为环境注入口径
- [x] 26.7 前端：`ZtpRecovery.vue` 初始/加载 password 留空、留空提交 null、显式重输才提交；i18n 新增 `password_placeholder`（zh/en）
- [x] 26.8 ops-toolkit `debug-v24-*.py`（5 个）确认为无入口临时脚本（REVIEW-v242 P2 债、docs 未收录、裸 ncclient 违反红线）→ 移除，不新建裸 SSH 路径
- [x] 26.9 测试口令替换为 synthetic（test_device_api/test_ops_toolkit_paramiko/test_ztp_onboard/test_ztp_recovery/test_backup_integration/test_vpn_integration/test_split_integration/test_smoke 共 31 处）
- [x] 26.10 新增对抗测试 `test_s1_023_credential_hygiene.py`（活动生产路径/测试无字面量、debug-* 已移除、ztp-stack 三脚本缺密码 fail closed、onboard 缺密码 422、state 0600/API 脱敏）+ `test_ztp_recovery.py` 扩展 + `ZtpRecovery.spec.js` 扩展；QA compose 只读挂载仓库根供静态扫描
- [x] 26.11 QA（本轮未触真机）：ZTP+卫生 21 passed；受影响+S1 回归 = **181 passed / 16 skipped**（skip 全为 integration 门控）；前端 lint+type-check+build+vitest = **62 passed**（含 ZtpRecovery 4 条）；openspec strict / manifest JSON / git diff --check / 活动源码凭据扫描全部干净
- [x] 26.12 同步 design/tasks/handoff/review-response/review-manifest/readiness 为 S1-023 口径；明确「历史已暴露，必须由用户在设备与 .env 外部轮换」（不改 archive/历史、不重写 Git 历史）

## 27. S1-024（CR43：ZTP 渲染凭据边界加固，本轮未触真机）

- [x] 27.1 `ztp_runtime_render.py`：新增 `_atomic_write_secret`——临时文件创建前 `umask 077` + `os.open(O_CREAT|O_EXCL, 0600)`，写入 flush+fsync，`os.replace` 原子替换，替换后显式 `os.chmod(0600)`；异常 unlink 临时文件（修复重渲染把 0600 变 0644）
- [x] 27.2 `entrypoint.sh`：python3 -c 渲染块改环境注入——零 `$`/零单引号插值，全部渲染变量从 `os.environ` 读取；`ZTP_PLATFORM_LONG` 补 export；输出走 `mktemp`(0600) + chmod 600 + `mv -f` 原子替换 + trap 失败清理（修复特殊字符语法失败/注入 + 宽权限中间文件）
- [x] 27.3 新增对抗测试 `test_s1_024_credential_hygiene.py`（6 条）：特殊字符密码原样渲染不执行注入（模块级 + entrypoint 全量运行级 stub dnsmasq/真实 jinja2）；首次与覆盖重渲染后均 0600；失败路径不残留宽权限/含口令临时文件；缺 env 写盘前明确失败；entrypoint 渲染块静态断言（os.environ 读取、mktemp/chmod/mv/trap）
- [x] 27.4 QA（本轮未触真机）：S1-024 = **6 passed**；受影响+S1-023+回归 = **187 passed / 16 skipped**（skip 全为 integration 门控）；bash -n / openspec strict / manifest JSON / git diff --check / 活动源码凭据扫描全部干净
- [x] 27.5 同步 design/tasks/handoff/review-response/review-manifest/readiness 为 S1-024/CR43 口径（package_id=S1-024）

## 28. S1-026（operation 解释投影：只读 serializer，本轮未触真机）

- [x] 28.1 新增 `backend/app/services/sdn_explanation.py` 纯函数投影：operation 级（intent/scope_summary/safety_boundary/truth_state/headline/statement）、attempt 级（kind/summary/result/finished/still_uncertain/evidence_basis/statement）、unit 级（category/statement/truth_kind/source/scope/observed_at/freshness）；truth_kind=desired|observed|inferred|pending；无法证明字段一律 null；succeeded 无观察证据只表达执行记录成功；中文不固化后端
- [x] 28.2 `sdn_access.py::_operation_to_dict` 只做组装：operation/attempt/unit 三级 `explanation`（additive，保留全部既有字段与原始 scope/evidence 原样）；`_safe_explain` 包裹——解释失败返回 `{"unavailable": true}` 降级标记，绝不 500
- [x] 28.3 新增对抗测试 `test_sdn_explanation.py`（27 条）：正常 execute/validate/withdraw/reconcile、unknown、空/畸形 evidence、legacy operation；API 级证明 raw evidence 未丢失、旧响应字段未移除、畸形历史 JSON 安全降级、接口不因解释失败而 500
- [x] 28.4 Codex 复审修正：确定终态不被历史 stale/insufficient 永久标记歧义；无设备证据的执行记录 `observed_at=null`；JSON 解析纳入安全边界
- [x] 28.5 QA（本轮未触真机）：`test_sdn_explanation.py` = **27 passed**；受影响回归（access/operation_service/validation/apply + 投影）= **65 passed**；`openspec validate --strict` valid；`git diff --check` clean
- [x] 28.5 同步 design(§27)/tasks(§28)/spec.md(新 Requirement)/readiness/handoff/review-response/review-manifest（package_id=S1-026）/collaboration.md（S1-026 状态）

## 29. S2-001（VPC 目标态/观测态/差异投影，只读，本轮未触真机）

- [x] 29.1 新增 `backend/app/services/sdn_state_projection.py` 纯函数（零 I/O、畸形输入稳定降级）：`desired`（VSI/VSI-interface/L3VNI/端口绑定摘要 + kind/id/version 来源记录）、`observed`（最新快照命令级解析 + snapshot id + 采集完成时间 + stale 判定）、`diff` 逐维 `aligned|drifted|unknown|stale|not_applicable` + 稳定 reason code；命令 `success != true`/缺失 → unknown 绝不 drift；TTL 600s 对齐既有 PREDEPLOY_DEFAULT_MAX_AGE；`planned` 绑定不断言设备侧；聚合取最差，永不覆盖逐维
- [x] 29.2 `sdn.py` 新增 `GET /api/sdn/vpcs/{vpc_id}/state-projection`：只读组装（VPC+tenant 身份与版本、deployment∪binding∪snapshot 覆盖设备 → `sdn_role==evpn_leaf` leaves + 非 evpn_leaf excluded(reason=not_evpn_leaf)、latest 快照解码）；绝不触发 collector.sync/SSH/NETCONF、绝不写库
- [x] 29.3 新增契约测试 `backend/tests/test_s2_001_state_projection.py`（10 条）：无快照 unknown、过期 stale、全一致、l3-vni 明确偏差、部分命令失败 unknown 不 drift、vsi_up not_applicable、planned 绑定 not_asserted、非 EVPN 排除、GET 零设备 I/O/零写入、vpc_not_found
- [x] 29.4 QA（本轮未触真机）：`test_s2_001_state_projection.py` = **10 passed**；直接受影响 SDN 回归（port_binding/expansion/access/operation_service/explanation/migration + S1-007/S1-016）= **103 passed**；openspec strict / manifest JSON / git diff --check 通过
- [x] 29.5 同步 spec.md(新 Requirement：目标态/观测态/差异投影)/tasks(§29)/design(§28)/review-manifest（package_id=S2-001，baseline_sha=10d032d，新增 CR46/测试条目/文件清单）

## 29-R1. S2-001-R1（CR47-CR49 复审返工，本轮未触真机）

- [x] 29-R1.1 CR47 目标态由生命周期证明：`resolve_base_lifecycle` 折叠 create/delete（仅 success 确定、id 升序、版本因果），`desired` 存在性取 True/False/None，`_classify_presence` 消除假 drift；absent+operable binding → `lifecycle_conflict`；路由传入 deployment 序列；来源保留 deployment id/version/action/status
- [x] 29-R1.2 CR48 多值成员比较：观测解析返回有序列表，`值∈列表` 判定，绑定 diff 输出 `observed` 列表
- [x] 29-R1.3 CR49 token 精确匹配：l3-vni/Vsi-interface 编号/VSI 名改行首/词边界正则，杜绝前缀串扰
- [x] 29-R1.4 契约测试补 10 条（create→delete / delete→new create / snapshot-only / failed delete / absent+operable conflict / 多值成员 2 / 前缀反例 3）
- [x] 29-R1.5 Codex 复审补齐 L2 VSI 与 L3 网关独立生命周期：`gateway_delete` 仅令 VSI-interface/L3VNI 期望 absent，局部 `vsi-l3 create` 不冒充整套 L2 VSI 已部署；新增 2 条反例
- [x] 29-R1.6 Codex 复审补齐 CLI 错误正文与损坏快照：命令返回成功但正文含 H3C CLI 错误时仍为 unknown；有 snapshot id 但载荷不可读时为 evidence_missing，不冒充 no_snapshot
- [x] 29-R1.7 QA（本轮未触真机）：S2-001 投影与直接受影响 SDN 回归合并运行 = **127 passed**；openspec strict / manifest JSON / git diff --check 通过

## 30. S2-003（逐维差异证据指针，只读，本轮未触真机）

- [x] 30.1 `_observed_evidence`（有快照 → {kind=snapshot, snapshot_id, collected_at, command}，命令失败/畸形/过期仍保留）+ `_evidence`（{desired_source, observed_source}）纯函数；vsi/vsi_up/vsi_interface/l3_vni 与绑定字段 diff 附加 evidence；desired_source 复用 deployment/binding/operable_binding_count，无证明 null
- [x] 30.2 脱敏边界：evidence 只含稳定元数据与 display 命令名，绝不回传原始 CLI output/error/凭据；不改状态/reason/聚合/生命周期语义；零 I/O、零写库、无迁移/表/采集命令/接口变更
- [x] 30.3 对抗测试补 4 条（aligned 指针 / 命令失败保留指针但脱敏 / 整棵投影永不泄漏 output 或凭据 / 端点证据脱敏）
- [x] 30.4 QA（本轮未触真机）：`test_s2_001_state_projection.py` = **28 passed**；直接受影响 SDN 回归 = **131 passed**；openspec strict / manifest JSON / git diff --check 通过

## 31. S2-004（设备快照时间线，只读，本轮未触真机）

- [x] 31.1 抽取共享投影助手（load context / target devices / serialize bindings / deployments / decode snapshot / excluded entry / device dict），既有 state-projection endpoint 改用且行为不变
- [x] 31.2 新增 `GET /vpcs/{vpc_id}/state-projection/history`：device_id 可选、limit 默认 10（1..50）；evpn_leaf 时间线按 snapshot id 倒序，每点复用 build_leaf_projection（当前目标 desired + 该历史快照观测）+ desired.basis=current_target + snapshot_id/collected_at/validation_result；非 EVPN 仅 excluded；坏快照保留 unknown/evidence_missing 不跳过不改写
- [x] 31.3 只读零 I/O 零写库、响应脱敏（只保留 S2-003 evidence 指针，无原始 output/error/凭据）；无迁移/表/采集命令/接口字段
- [x] 31.4 对抗测试 10 条（倒序与 limit / device 过滤 / 非 EVPN 排除 / 坏快照保留 unknown / current target basis / validation_result / 零 I/O 零写入 / 响应脱敏 / VPC 404 / limit 越界 422）
- [x] 31.5 QA（本轮未触真机）：`test_s2_004_state_projection_history.py` + 投影 = **38 passed**；直接受影响 SDN 回归 = **141 passed**；openspec strict / manifest JSON / git diff --check 通过

## 32. S2-006（历史快照 × 操作/尝试关联，只读，本轮未触真机）

- [x] 32.1 `_snapshot_correlation` 纯函数：零引用 unlinked；op/attempt 引用 dangling → missing；operation 跨 VPC/设备、attempt 属于另一 operation → mismatch；全部一致 → linked（白名单 operation 摘要 id/operation_type/status/expected_host_ip/created_at/updated_at + attempt 摘要 id/kind/status/started_at/completed_at）
- [x] 32.2 history endpoint 批量读取窗口内 op/attempt（一次 IN 查询避免逐点 N+1），逐点附加 correlation；linked 只复制白名单字段，绝不携带 request_payload_json/scope_json/idempotency_key/fingerprint/owner/evidence_json/凭据
- [x] 32.3 只读零 I/O 零写库零隐式采集；correlation 只表达证据归属/时间相关，不宣称操作导致状态变化；不改变既有 history 字段语义；无迁移/表/接口字段
- [x] 32.4 对抗测试 9 条（linked 摘要 / unlinked / op dangling / attempt dangling / attempt 跨 operation mismatch / operation 跨 VPC mismatch / operation 跨设备 mismatch / 响应脱敏 / 零 I/O 零写入）
- [x] 32.5 QA（本轮未触真机）：`test_s2_006_history_correlation.py` + S2-004 + S2-001 = **47 passed**；直接受影响 SDN 回归 = **150 passed**；openspec strict / manifest JSON / git diff --check 通过

## 33. S2-008（多对象变更影响投影，只读 additive，本轮未触真机）

- [x] 33.1 `build_operation_impact` 纯函数：节点（vpc/device/interface/host，仅持久化字段、缺失 null、接口为 device+if_index 稳定复合身份、id 为身份、名称只是 label、source 区分 operation_scope/operation_record）+ 业务范围关系（targets/exposes；interface→host 按类型 expects|withdraws，不称物理邻接/因果链，legacy 不编造）+ 变更项（attempt/unit 持久化顺序，truth_kind/source/statement 复用 explain_attempt/explain_unit）
- [x] 33.2 safety 复用 explain_operation 判定（target_only/ambiguous_claims，未传 explanation 时用真实 attempt facts 调用既有 explain_operation）；共享 VPC/网关不属于 terminal access/withdraw 操作目标，legacy_apply 不可证明 → null；protected_interfaces 未持久化 → null
- [x] 33.3 `_operation_to_dict` 只读组装嵌套 `explanation.impact`（_safe_explain 包裹、explanation/impact 异常置 unavailable 且 detail 仍 200、复用已加载数据无逐 unit/attempt N+1、旧字段不删不改、顶层无影子字段）；legacy/畸形/字段缺失稳定降级不 500；零 DB 写零 SSH/NETCONF 零隐式采集；无迁移/表/采集命令/接口字段
- [x] 33.4 对抗测试 14 条（完整 terminal_access / withdraw 用 withdraws 关系 / legacy 不编造 / 畸形 source=operation_record / 缺 device 接口不编造全局身份 / 多 attempts-units 顺序与去重 / 脱敏 / stale_takeover 歧义同源 / fallback 复用 explain_operation / builder 异常 200 + unavailable / unknown 歧义 / 零 I/O 零写入 / 垃圾输入纯函数 / API 端到端）
- [x] 33.5 QA（本轮未触真机）：`test_s2_008_operation_impact.py` = **14 passed**；直接受影响 SDN 回归（含 S1-026 解释 24 条）= **125 passed**；openspec strict / manifest JSON / git diff --check 通过

## 34. S2-010（快照状态转变投影，只读 additive，本轮未触真机）

- [x] 34.1 `build_transition` 纯函数：逐维状态转变矩阵（unchanged / drift_detected / drift_cleared / evidence_gained / evidence_lost / state_changed / baseline_unavailable；drifted→unknown/stale 只能 evidence_lost、unknown/stale→drifted 只能 drift_detected、not_applicable 变化按 state_changed）；固定维度 vsi/vsi_up/vsi_interface/l3_vni 恒出现、绑定维度按稳定 binding_id 匹配并取两侧并集顺序稳定
- [x] 34.2 每项含 dimension key / from-to status / from-to reason_code / transition kind；顶层含 from/to snapshot_id 与 collected_at；输出脱敏 summary（changed_dimensions + 按 kind counts）、desired_basis=current_target，不含原始 CLI output/error/凭据
- [x] 34.3 history endpoint 每点只读组装 `transition_from_prior`（较新点与紧邻较旧点比较；窗口最旧点明确 baseline_unavailable，不拿窗口外/当前实时状态补造基线；复用同一查询窗口与已加载数据无新查询/N+1；旧字段不删不改）；零 DB 写零 SSH/NETCONF 零隐式采集；无迁移/新 endpoint/表/采集命令
- [x] 34.4 对抗测试 10 条（倒序相邻配对 / 最旧点无基线 / aligned→drifted / drifted→unknown 只能 evidence_lost / unknown→aligned evidence_gained / unchanged / binding 复合维度按 binding_id / limit 截断边界 / 坏快照稳定 / 脱敏 / 零 I/O 零写入 / 垃圾输入纯函数矩阵）
- [x] 34.5 QA（本轮未触真机）：`test_s2_010_transition_projection.py` = **10 passed**；S2-001/S2-004/S2-006/S2-008 与 S1-026 及直接受影响 SDN 回归 = **163 passed**；openspec strict / manifest JSON / git diff --check 通过

## 35. S2-012（VPC EVPN Leaf 范围覆盖投影，只读 additive，本轮未触真机）

- [x] 35.1 `build_scope_member` 纯函数：保守分类（targeted=base present 或有 planned/active/expanding 当前目标绑定；withdrawn=base absent 且无当前目标绑定；not_targeted=无记录；ambiguous=有历史但生命周期未证明且无当前目标绑定），复用 resolve_base_lifecycle 与 BINDING_DESIRED_STATUSES 同一判定，不复制一套；畸形/缺字段稳定降级不抛异常
- [x] 35.2 每个 member 只返回白名单（device_id/name/host、classification、reason_code、record_sources、desired_base_state、desired_binding_count），不回传凭据/protected_interfaces/原始配置或快照
- [x] 35.3 state-projection endpoint 顶层只读组装 scope：evpn_leaf 设备一次查询枚举，deployment/binding/snapshot 各一次批量查询按 device_id 分组避免逐 Leaf N+1（复用同一行序列化器）；summary 只计 EVPN Leaf、无 EVPN Leaf 时 counts 全 0；既有 leaves/excluded/aggregate 不变；零 DB 写零 SSH/NETCONF 零隐式采集；无迁移/新 endpoint/表/采集命令
- [x] 35.4 对抗测试 13 条（四类分类与 summary / 版本不匹配 / snapshot-only / failed、pending 不覆盖生命周期 / gateway_delete 不改变 base / planned+active binding 无 deployment 也 targeted / 非 EVPN 排除 / 成员角色大小写归一化 / 空 inventory / 脱敏白名单 / 零 I/O 零写入 / 既有字段不变 / 纯函数矩阵与垃圾输入）
- [x] 35.5 QA（本轮未触真机）：`test_s2_012_scope_projection.py` = **13 passed**；S2-001/S2-004/S2-006/S2-008/S2-010 与 S1-026 及直接受影响 SDN 回归 = **176 passed**；openspec strict / manifest JSON / git diff --check 通过

## 36. S2-014（VPC 范围例外管理，业务上下文，本轮未触真机）

- [x] 36.0 复审返工（S2-014-R1）：vpc_id/device_id 加 FK+父侧 ORM cascade（父删除不留 orphan、子删除不向上级联）；expires_at 接受 Z/offset 统一 UTC naive 存库；畸形历史稳定 state=invalid（CHECK 拒新脏数据）；聚焦 20 passed + 回归 196 passed

- [x] 36.1 模型 SdnScopeException（vpc_id+device_id 唯一约束 uq_sdn_scope_exceptions_live；exception_type 仅 intentional_exclusion|maintenance_pause；reason 非空≤200；expires_at 可选；version/created/updated）+ 迁移 013（幂等建表/唯一索引/查询索引，空库与旧库均可升级，不重写旧迁移）
- [x] 36.2 REST：GET /vpcs/{id}/scope-exceptions（过期标 state=expired 不自动删除）、PUT /vpcs/{id}/devices/{device_id}/scope-exception（新建或替换，短事务 + IntegrityError 回滚重读防并发双写）、DELETE 同路径（幂等清除 deleted=true/false）；成员准入：VPC/设备不存在既有 404 语义、非 EVPN Leaf 明确拒绝、过期时间必须晚于当前、reason/类型/时间格式校验；i18n 新增 7 键
- [x] 36.3 state-projection additive：批量读例外按 device_id 附加 `exception`（无例外 null）与 summary.active_exception 计数；不触碰 build_scope_member 分类事实、不改 aggregate/leaves/excluded、不从分母移除设备
- [x] 36.4 写操作只改数据库：零 SSH/NETCONF/配置下发/状态采集/隐式部署撤回；响应脱敏不含凭据/protected_interfaces/原始配置/快照/owner/fingerprint
- [x] 36.5 对抗测试 20 条（CRUD / 清除不向上级联父对象与历史 / 替换版本与单行 / 唯一约束直插拒绝 / 重复提交稳定 / 成员准入 / 过期边界不自动删除 / 过期拒绝 / Z 与 offset 时区换算 / 校验错误 / 脱敏 / 零设备 I/O / scope 事实与 aggregate 不受影响 / 无例外 null 与幂等清除 / 畸形字段纯函数矩阵 state=invalid / CHECK 拒新脏数据 / 父 VPC 删除不留 orphan / 父 device 删除不留 orphan / 迁移建表索引 FK CHECK / 迁移幂等）
- [x] 36.6 QA（本轮未触真机）：`test_s2_014_scope_exception.py` = **20 passed**；S2-012 13 条 + S2-001/S2-004/S2-006/S2-008/S2-010 与 S1-026 及直接受影响 SDN 回归 = **196 passed**；openspec strict / manifest JSON / git diff --check 通过

## 37. S2-016（VPC 可行动关注队列，只读 additive，未触真机）

- [x] 37.1 纯函数矩阵 `backend/app/services/sdn_attention.py`（8 条：scope_uncertain/confirmed_drift/evidence_missing_or_stale/coverage_gap/coverage_deferred/exception_expired/exception_invalid/无 item）+ 稳定 key（vpc:device:category）+ 固定排序（blocking→review→deferred 再 device_id/category）+ 脱敏 source_refs + exception 复用 S2-014 白名单
- [x] 37.2 state-projection 顶层 additive `attention`：复用同一次已加载 scope members 与 leaves，零额外查询/无逐 Leaf N+1；summary.total/blocking/review/deferred；既有 scope/leaves/excluded/aggregate 完全不变
- [x] 37.3 矩阵语义：active exception 不消灭 drift（confirmed_drift 仍 blocking 携带 exception）；not_targeted/withdrawn+active exception → deferred 保留原分类；expired/invalid exception 独立成项且与 blocking 共存 key 不冲突；targeted+aligned 无 item；非 EVPN 不进入；坏字段稳定降级绝不 500
- [x] 37.4 对抗测试 14 条（全矩阵 / targeted unknown / drift+active exception 仍 blocking / expired+blocking 共存 / aligned+expired / not_targeted+expired 双项 / 空态 / 非 EVPN / 稳定 key 排序 / 脱敏白名单 / 既有投影不变 / 零写入零 I/O / 纯函数畸形降级 / aligned 无 item）
- [x] 37.5 QA（未触真机）：`test_s2_016_attention.py` = **14 passed**；S2-014 20 条 + S2-012 13 条 + S2-001/S2-004/S2-006/S2-008/S2-010 与 S1-026 及直接受影响 SDN 回归 = **210 passed**；openspec strict / manifest JSON / git diff --check 通过
