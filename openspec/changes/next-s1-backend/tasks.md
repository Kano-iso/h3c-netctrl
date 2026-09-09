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
