# S1-018 交接记录（handoff）— CODE_REVIEW_PASSED

> 状态：**CODE_REVIEW_PASSED**。S1-006 CR1-CR10、S1-007 CR11-CR18、S1-008 CR19-CR23、S1-009 CR24-CR26、S1-010 CR27、S1-011 CR28、S1-012 CR29、S1-013 CR30-CR31、S1-014 CR32、S1-015 CR35、S1-016 CR36、S1-017 CR37 已闭环；S1-018 CR38 Type-3 按目标 VPC 的 Route distinguisher 归属校验已落地（14 S1-006 + 21 S1-007 + 15 S1-008 + 7 S1-009 + 3 S1-010 + 3 S1-011 + 4 S1-012 + 11 S1-013 + 5 S1-014 + 10 S1-015 + 13 S1-016 + 10 S1-017 + 8 S1-018 对抗全绿）。Codex 于 2026-09-10 独立复跑 S1-016～018 共 31 条测试并复审通过。未连设备、未推送/tag/归档/close stage、未重启既有服务；真机链路仍待单独验证。

## 全量测试现状（S1-018 变更后）

`pytest tests/ -q` = **560 passed / 55 skipped / 11 failed**（S1-016 基线；失败 11 条全部为 `test_ops_toolkit_paramiko.py`：`ModuleNotFoundError: No module named '_paramiko_batch_exec'`，基线段 `6cd19fb` 既有，非本次引入；本轮按约定不重跑全量）。
`pytest tests/test_s1_018_adversarial.py -q` = **8 passed**。
`pytest tests/test_s1_016_adversarial.py tests/test_s1_017_adversarial.py tests/test_s1_018_adversarial.py -q` = **31 passed**。
`pytest tests/test_sdn_validation_api.py tests/test_sdn_access_api.py tests/test_sdn_operation_service.py tests/test_sdn_migration.py -q` = **32 passed**（validation/access/service/migration）。
`pytest tests/test_s1_017_adversarial.py -q` = **10 passed**。
`pytest tests/test_s1_006_adversarial.py -q` = **14 passed**。
`pytest tests/test_s1_007_adversarial.py -q` = **21 passed**。
`pytest tests/test_s1_008_adversarial.py -q` = **15 passed**。
`pytest tests/test_s1_009_adversarial.py -q` = **7 passed**。
`pytest tests/test_s1_010_adversarial.py -q` = **3 passed**。
`pytest tests/test_s1_011_adversarial.py -q` = **3 passed**。
`pytest tests/test_s1_012_adversarial.py -q` = **4 passed**。
`pytest tests/test_s1_013_adversarial.py -q` = **11 passed**。
`pytest tests/test_s1_014_adversarial.py -q` = **5 passed**。
`pytest tests/test_s1_015_adversarial.py -q` = **10 passed**。
`pytest tests/test_s1_016_adversarial.py -q` = **13 passed**。
`openspec validate --strict next-s1-backend` = **valid**；`git diff --check` = **clean**。

## CR1-CR10（S1-006 已闭环，回归仍绿）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR1-CR6 | ✅ | executor 短事务 CAS、逐单元证据、绑定先锁后写、撤回 owner CAS、reconcile、计划哈希/ipaddress/接口身份 | `test_s1_006_adversarial.py` + 既有回归 |
| CR7 split 元数据显式分派 | ✅ | `device_access` 显式分派 + fresh 参数 | `test_cr7_split_metadata_explicit_dispatch` |
| CR8 证据因果/四维 | ✅ | config_completed_at 因果 + 采集起止 + cached 不可变 + host/L2/L3 分离 | `test_cr8_*` |
| CR9 旧入口守卫矩阵 + PATCH 受限 | ✅ | `_acquire_resource_claims` + 全部 legacy mutation 先认领后释放 + PATCH 终态不可改写 | `test_cr9_*` |
| CR10 迁移/QA | ✅ | 012 部分 schema 修复 + 真实 bootstrap + base-vs-change 复现 | `test_sdn_migration.py` |

## CR11-CR18（S1-007 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR11 apply owner-aware claim 复用 | ✅ | `acquire_or_reuse_claims` 复用本 operation 已持有 claim、仅补齐缺失；`apply_access` 改用之 | `test_cr11_apply_reuses_own_claims_and_releases_on_success` |
| CR12 unknown/withdraw claim 生命周期 | ✅ | execute/withdraw：确定性 success/failed 释放完整 scoped claims，unknown 保留并 `mark_operation_claims_ambiguous`（按 operation 归属，非零行 attempt 更新） | `test_cr12_unknown_keeps_claims_ambiguous_and_blocks` + `test_cr12_withdraw_success_releases_all_original_claims` + `test_cr12_withdraw_unknown_keeps_all_claims` |
| CR13 reconcile 按动作/期望状态一致收尾 | ✅ | `_reconcile_outcome` 按 deployment action（port_bind→active 证明；port_unbind→scoped 配置缺失证明）；一致更新 unit/attempt/deployment/operation/binding；证据不足 reconciled=false | `test_cr13_reconcile_port_bind_active_resolves_success` + `test_cr13_reconcile_port_unbind_active_not_success` + `test_cr13_reconcile_port_unbind_absent_resolves_success` |
| CR14 逐单元 CAS 失败阻断 I/O + legacy 多单元 | ✅ | `AttemptUnitHooks` 返回 bool；executor `before_unit` 失败即阻断 I/O（SDN_UNIT_NOT_STARTABLE）；`after_unit_*` 零行降级 unknown；`ensure_legacy_apply_operation` 从 planned_config 解析真实 unit 列表 | `test_cr14_started_unit_replay_blocks_io` + `test_cr14_legacy_two_units_created_and_updated` |
| CR15 迁移 012 列类型/唯一约束/复合索引 | ✅ | `claimed_at` 改为 DateTime（`claimed_by_attempt_id` 仍 Integer）；`uq_attempt_unit` UNIQUE(attempt_id, unit_index)；`ix_identity_kind_id_created` 复合索引；`sdn_attempts.evidence_json` 新列 | `test_cr15_constraints_column_type_and_indexes` |
| CR16 主机观测不混入远端 Type-2 | ✅ | `_build_host_observations` 结构化 source/scope；仅本地 ARP/MAC + 目标端口关联计 host_observed；远端 EVPN Type-2 标 remote 不计；`_ip_exact_match` 边界精确匹配 | `test_cr16_remote_type2_does_not_mark_host_observed` + `test_cr16_local_port_association_marks_host_observed` + `test_cr16_ip_substring_not_matched` |
| CR17 四维验证不互相冒充 + ping 诚实持久化 | ✅ | `complete_access` 四维（execution/config_readback/business_validation/evidence）显式 status+reason；`_run_gateway_ping` 结构化 reachable/unreachable/error/unsupported/not_run；ping 异常不再静默吞掉；四维+ping 持久化到 `sdn_attempts.evidence_json` | `test_cr17_ping_unreachable_degrades_not_succeeds` + `test_cr17_ping_error_unknown_not_succeeds` + `test_cr17_ping_unsupported_does_not_block_success` + `test_cr17_evidence_insufficient_not_success` |
| CR18 文档不提前宣称完成 | ✅ | handoff/readiness/tasks/review-response 同步现状；`tasks.md 9.2` 标注 READY_FOR_CODE_REVIEW；CR18 SHALL 覆盖缺口已实现：依赖重放 `AttemptUnitHooks.before_unit` 前置单元校验、撤回矩阵（幂等/rebind 阻断/读不 bump version）、终端视图 `access-overview.observations`（source/scope/timestamp + 远端 Type-2 过滤） | `test_cr18_*`（5 条） |

## CR19-CR23（S1-008 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR19 reconcile 真正解析 unknown unit | ✅ | `mark_unit_reconciled`（started\|unknown→succeeded\|failed_known，rowcount 逐项校验）；reconcile 未全解析→reconciled=false、不释放 claims、上层 unknown/ambiguous；原 attempt 终态由 unit 重推 | `test_cr19_unknown_unit_reconciles_consistently` + `test_cr19_cas_zero_row_keeps_unknown_ambiguous_no_release` |
| CR20 port_bind 需目标端口 scoped 正向证据 | ✅ | `_scoped_port_evidence` 校验接口回读命令存在/success/无 CLI error + 结构化匹配 service-instance/xconnect vsi；仅 VPC active 不算 | `test_cr20_port_bind_vpc_active_without_port_config_not_success` + `test_cr20_port_bind_scoped_config_complete_success` |
| CR21 port_unbind 不把采集失败当缺失 | ✅ | 命令缺失/success=false/CLI error→insufficient；结构化语法匹配（非裸数字） | `test_cr21_port_unbind_missing_command_not_success` + `test_cr21_port_unbind_command_failed_not_success` + `test_cr21_port_unbind_cli_error_not_success` + `test_cr21_port_unbind_number_false_hit_not_success` + `test_cr21_port_unbind_scoped_absent_success` |
| CR22 complete/validate claim 与终态守卫 | ✅ | complete 幂等/终态守卫（非 awaiting_validation 不改状态不建 attempt）；owner-aware 获取/复用 tenant/vpc/vpc-device claims；只选原 port_bind deployment | `test_cr22_complete_claim_conflict` + `test_cr22_withdrawn_complete_no_mutation` + `test_cr22_complete_uses_original_port_bind_deployment` |
| CR23 主机 IP/端口同一条本地记录 | ✅ | `_build_host_observations` 逐行关联 IP+接口（同一行），或 ARP MAC→MAC 表端口关联；命令失败不产生 observation=true | `test_cr23_arp_different_lines_not_host_observed` + `test_cr23_arp_same_line_host_observed` + `test_cr23_command_failed_not_observed` |

## CR24-CR26（S1-009 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR24 真实 reconcile 采到待对账目标接口 | ✅ | `SdnValidationCollector.sync(scope_bindings=...)` + `_commands` 追加 scope 接口回读；reconcile 传 binding scope；普通周期采集不混入 planned | `test_cr24_reconcile_port_bind_collects_target_interface` + `test_cr24_reconcile_port_unbind_collects_target_interface` + `test_cr24_periodic_collection_excludes_planned_binding`（走真实 `_commands`/`_snapshot_data`，只 mock SSH/凭据） |
| CR25 unknown validation 恢复路径 | ✅ | complete 幂等仅限 latest validate attempt 为 succeeded/failed_known；unknown + port_bind 执行已成功允许显式重试新建 attempt，旧 attempt 历史保留 | `test_cr25_unknown_validation_recovers_on_retry`（首次采集失败→重试成功→幂等，断言 claims/attempt/op 一致） |
| CR26 CLI 错误 output/结构化字段共同识别 | ✅ | `_scoped_port_evidence` 复用 `SdnValidationCollector._has_display_error(output)`；success=true/error=null + 错误文本 → insufficient | `test_cr26_port_unbind_cli_error_in_output_not_success`（% Wrong parameter / Unrecognized / Incomplete 三例） |

## CR27（S1-010 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR27 complete/validate 并发准入 | ✅ | `claim_action_admission` 单行 CAS（`awaiting_validation\|unknown → validating`）；赢者同事务建 validate attempt + claims 才进入 collector/ping；输家/读到 validating 返回 `sdn.operation_in_progress`（新增 error key）；准入后崩溃留 `validating`+`claimed` 痕迹不回退、不重放 | `test_cr27_concurrent_complete_single_winner`（真实线程 + barrier）+ `test_cr27_concurrent_unknown_recovery_single_winner` + `test_cr27_validating_stuck_not_replayed` |

## CR28（S1-011 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR28 validate/withdraw 跨动作互斥 + 条件收尾 | ✅ | `claim_action_admission` 泛化（from_statuses→to_status）+ `withdrawing` 中间态；withdraw 设备 I/O 前 CAS 准入（`WITHDRAW_FROM_STATUSES`，排除 withdrawn/validating/withdrawing）；validate 在 validating/withdrawing 下返回 in-progress；`finish_action` 条件收尾 CAS（WHERE status=from_status），零行不覆盖现状、不误释放 claims + late completion 诊断；withdrawn 不可逆幂等 | `test_cr28_validate_wins_withdraw_blocked` + `test_cr28_withdraw_wins_complete_blocked` + `test_cr28_late_complete_does_not_overwrite_withdrawn`（真实线程 + 阻塞 barrier） |

## CR29（S1-012 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR29 apply 纳入动作仲裁 | ✅ | `applying` 中间态；apply 设备 I/O 前原子 CAS `awaiting_wiring → applying`（与 validating/withdrawing 互斥）；收尾条件 CAS `applying → awaiting_validation\|failed\|unknown`；deployment CAS 失败（`SDN_DEPLOYMENT_NOT_PENDING`）即停、不推导 unknown/不误标 claims；并发 apply 单赢家；auto_apply 内联 `claimed` 阶段兼容（阻挡 complete/withdraw） | `test_cr29_apply_wins_withdraw_blocked` + `test_cr29_withdraw_wins_apply_blocked` + `test_cr29_concurrent_apply_single_winner` + `test_cr29_late_apply_does_not_overwrite_withdrawn`（真实线程 + 阻塞 barrier） |

## CR30-CR31（S1-013 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR30 动作代际令牌 | ✅ | `sdn_operations` 新增 `active_attempt_id`/`active_started_at` 持久列；`claim_action_admission` 绑定 phase+token+time，`finish_action` 匹配 `operation_id+phase+active_attempt_id` 且成功原子清空 token；准入输家回滚临时 attempt | `test_cr30_aba_validate_generation_token` + `test_cr30_aba_withdraw_generation_token` + `test_cr30_aba_apply_generation_token` |
| CR31 reconcile 动作仲裁 | ✅ | `unknown → reconciling` 原子准入（绑定 attempt token）；`claim_stale_takeover`（`active_started_at` + `STALE_ACTION_LEASE_SECONDS=300` lease 判定失联）；终态写入/deployment/binding/claims 在持有 reconciling+token 时发生；collector 失败条件收尾到 unknown；withdrawn 不可变 | `test_cr31_reconcile_rejected_during_live_{validate,apply,withdraw}` + `test_cr31_unknown_reconcile_single_winner` + `test_cr31_stale_takeover_{rejected_within_lease,succeeds_past_lease}` + `test_cr31_reconcile_collector_fail_keeps_claims` + `test_cr31_reconcile_late_finish_does_not_overwrite_withdrawn` |

## CR32（S1-014 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR32 stale takeover 正确归属 active attempt | ✅ | reconcile 拆分 `active_attempt`（按 `old_active_attempt_id` 查询且必须 `operation_id==op.id`，只标它及其 started unit 为 unknown 并写 stale_takeover 证据）与 `effect_attempt`（设备写副作用 execute/withdraw，已确定终态不降级）；token 无效/跨 operation 保守拒绝；validate 失联按 port_bind 回读恢复到 awaiting_validation | `test_cr32_stale_validating_takeover_preserves_succeeded_execute` + `test_cr32_stale_applying_takeover_marks_started_unit_unknown` + `test_cr32_stale_withdrawing_takeover_resolves_via_readback` + `test_cr32_stale_takeover_rejects_invalid_token` + `test_cr32_stale_takeover_rejects_other_operation_token` |

## CR35（S1-015 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR35 收紧 stale takeover 的 active attempt 身份与终态保护 | ✅ | 唯一 phase→kind 映射 `ACTIVE_PHASE_EXPECTED_KIND`；可接管状态仅 `claimed/running`；`claim_stale_takeover` 单条原子 UPDATE + EXISTS 同时证明 op phase/token/lease 与 active attempt 的 operation/kind/status；条件式 `mark_attempt_stale`（rowcount==1 才继续，零行回滚接管） | `test_cr35_applying_with_validate_token_rejected` + `test_cr35_validating_with_succeeded_execute_token_rejected` + `test_cr35_withdrawing_with_terminal_withdraw_token_rejected` + `test_cr35_applying_with_terminal_execute_token_rejected[unknown/failed/failed_known/succeeded]` + `test_cr35_stale_takeover_allows_active_attempt[claimed/running]` + `test_cr35_cas_rejects_when_attempt_terminalized_between_read_and_cas` |

## CR36（S1-016 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR36 真实设备证据门禁与前置部署语义闭环 | ✅ | 两套门禁语义分离（create preflight「VNI 应不存在」deferred vs terminal predeploy「VSI 必须存在」）；`_l2_ready_status` 收紧（绝对新鲜度 600s + 采集晚于配置完成）；VPC 版本因果（`create.version == vpc.version`，`_create_sdn_deployment` 固化）；execute 证据不足强制重新取证（只读 display），采集失败在消费 plan 前阻断（零业务副作用）；`SdnPreflight` deferred `success=True` 明确为 create 路径 blocker/后续项。注：CR36 当时口径的 `validation_result=active`/全命令遍历/`raw_has_error` 已被 CR37/CR38 取代 | `test_predeploy_fresh_scoped_healthy_snapshot_ready` + `test_predeploy_stale_snapshot_blocked` + `test_predeploy_snapshot_predates_config_blocked` + `test_predeploy_validation_result_not_a_l2_gate[failed/degraded]` + `test_predeploy_command_failed_blocked` + `test_predeploy_command_cli_error_blocked` + `test_predeploy_display_error_in_output_blocked` + `test_predeploy_validation_details_missing_key_blocked` + `test_predeploy_validation_details_invalid_json_blocked` + `test_predeploy_vpc_version_change_blocked` + `test_execute_collection_failure_blocks_without_side_effects` + `test_terminal_predeploy_requires_vsi_exists_not_create_semantics` |

## CR37（S1-017 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR37 解除 terminal L2 门禁对 L3 网关健康的隐式耦合 | ✅ | 冻结 L2 必需条件 `TERMINAL_L2_REQUIRED_CHECKS=(bgp_peer_established, vsi_exists, vsi_up, type3_present)` + L2 所需命令映射 `_terminal_l2_required_commands`（BGP peer / VSI / Type-3）；移除「整张快照 `validation_result==active`」与「遍历整张快照所有命令」两处 L3 耦合；`raw_has_error` 按 L2 命令输出重算；无关 L3/Vsi-interface/ARP 命令失败不拖垮纯 L2 门禁，支撑 L2 的命令缺失/失败/CLI 错误仍 conservative unknown；网关/L3 健康继续由 complete `l3_gateway_ready` + ping 表达 | `test_l2_ready_with_degraded_overall_and_healthy_l2` + `test_l2_ready_with_l3_command_failure` + `test_l2_condition_false_blocks[bgp_peer_established/vsi_exists/vsi_up/type3_present]` + `test_l2_command_missing_blocks` + `test_l2_command_failed_blocks` + `test_l2_command_cli_error_blocks` + `test_complete_still_expresses_l3_unhealth_as_degraded` |

## CR38（S1-018 本轮修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR38 Type-3 按目标 VPC 的 Route distinguisher 归属校验 | ✅ | `SdnValidationCollector._type3_scoped(text, vni)`：按 `Route distinguisher:` 分块、逐块精确 RD 等值比较，只在目标 `1:{vni}` 块中发现 `[3]` 才为真；替代 `"[3]" in text`；多 RD 正确分块、1:2000 与 1:20000 不串匹配、目标 RD 缺失/只有 [2]/无法解析 → false（`_l2_ready_status` 返回 unknown）；`_validate()` 的 `type3_present.ok` 改用之；清理 CR36/CR37 冲突口径与已重命名测试 | `test_type3_scoped_target_rd_has_type3_true` + `test_type3_scoped_other_rd_type3_target_type2_false` + `test_type3_scoped_target_rd_missing_false` + `test_type3_scoped_vni_substring_no_false_match` + `test_type3_scoped_multi_rd_target_middle_true` + `test_type3_scoped_multi_rd_target_last_true` + `test_validate_type3_is_scoped_to_target_rd` + `test_terminal_gate_unknown_when_type3_not_in_target_rd` |

## schema 变化

`openspec/changes/next-s1-backend/` 的 012 migration 已扩展：`sdn_operations` 新增 `active_attempt_id`（Integer, nullable）与 `active_started_at`（DateTime, nullable）两列；`_create_table_if_missing` 对已存在表幂等补列，ORM `SdnOperation` 同步。令牌/租约仅存于数据库持久状态，无进程内锁。

## 下一轮待办

1. 等待 Codex 复审；若再审提出新 CR，在本 worktree 继续修正（不新建 change）。
2. 清理 __pycache__/logs（每轮结尾已执行）。

真机链路仍显式未验证。
