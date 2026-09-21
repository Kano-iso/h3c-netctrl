# S1-026 交接记录（handoff）— READY_FOR_CODE_REVIEW（operation 解释投影，只读）

> **复审状态时间线**：S1-022（2026-09-10）Codex 独立复跑 95 passed / 1 skipped 并完成安全复审 → **CODE_REVIEW_PASSED**。S1-023（凭据卫生）经 Codex 复审发现 2 项阻断（CR43），**S1-024 已修复并经 Codex 复核 → CODE_REVIEW_PASSED**（2026-09-11）。本轮 **S1-026（operation 解释投影）现提交复审：`READY_FOR_CODE_REVIEW`，等待 Codex 复审**（未提前宣称通过；结论见 review-response.md）。
> **S1-026（本轮，operation 解释投影，只读 serializer，不连真机、无任何设备 I/O）**：`GET /api/sdn/operations/{id}` 响应新增只读、additive 的 `explanation` 投影，供 NEXT 工作台 PULSE/STRATA 消费真实后端语义。**实现**：新增 `backend/app/services/sdn_explanation.py` 纯函数（operation 级 intent/scope_summary/safety_boundary/truth_state/headline；attempt 级 kind/summary/result/finished/still_uncertain/evidence_basis/statement；unit 级 category/statement/truth_kind（desired|observed|inferred|pending）/source/scope/observed_at/freshness）；`sdn_access.py::_operation_to_dict` 只做组装，保留全部既有字段与原始 `scope`/`evidence` 原样返回；`_safe_explain` 包裹——解释失败降级为 `{"unavailable": true}` 绝不 500。**诚实表达**：succeeded 单元无观察证据只表达「执行记录成功」（truth_state=succeeded_recorded、truth_kind=desired、statement 含 not device-verified），绝不冒充「设备已验证成功」；reconcile 单元 execute→observed/readback_verified、withdraw→inferred/readback_syntax_match（结构化语法匹配证明配置缺失）；无法证明字段（protected_interfaces、unit freshness）一律 null，禁止编造。**中文不固化后端**：只回稳定 code + 语言中性 fallback statement，具体中文由前端 i18n 完成。**对抗测试**：新增 `test_sdn_explanation.py`（26 条）——正常 execute/validate/withdraw/reconcile、unknown、空/畸形 evidence、legacy operation 全覆盖 + API 级证明 raw evidence 未丢失、旧响应字段未移除、接口不因解释失败而 500。本轮**未运行真机测试、无任何设备 I/O**。

> **S1-024（本轮，窄整改，不连真机、无任何设备 I/O）**：修复 Codex 复审对 S1-023 的两项阻断——(1) `ztp_runtime_render.render_once` 原子写不彻底：`tmp.write_text` 受进程 umask 影响创建 0644，`tmp.replace` 用临时文件权限替换目标，运行中任何重渲染把 `autocfg.cfg` 从 0600 变回 0644；(2) `entrypoint.sh` 把 `ZTP_ADMIN_PASS` 等环境值直接插进 `python3 -c` 单引号源码，密码含单引号/反斜杠/换行等字符时语法失败甚至代码注入；且 `ZTP_PLATFORM_LONG` 只作 shell 变量未 export。**修复**：`_atomic_write_secret` 安全原子写（创建前 `umask 077` + `os.open(O_CREAT|O_EXCL, 0600)` 创建即 0600 → flush/fsync → `os.replace` → 显式 `os.chmod(0600)`，异常 unlink 临时文件）；entrypoint 渲染改纯环境注入（python3 -c 零 `$`/零单引号插值、全部渲染变量 `os.environ[...]` 读取、`ZTP_PLATFORM_LONG` 补 export、输出 `mktemp`(0600)+chmod 600+`mv -f` 原子替换+trap 清理，不经宽权限中间态）。**对抗测试**：新增 `test_s1_024_credential_hygiene.py`（6 条）——特殊字符密码原样渲染不执行注入（模块级 + entrypoint 全量运行级 stub dnsmasq/真实 jinja2）、首次与覆盖重渲染均 0600、失败路径不残留宽权限/含口令临时文件、缺 env 写盘前明确失败、entrypoint 渲染块静态断言。本轮**未运行真机测试、无任何设备 I/O**。

> **S1-023（历史轮次，凭据卫生）**：灾备审计确认远端历史与活跃源码携带真实设备默认口令字面量。**本包不改设备、不重写 Git 历史、不轮换凭据**；目标是让活跃源码不再携带真实默认口令、ZTP recovery 查询接口不再把密码回显给浏览器。具体：(1) `schemas.py` 两个 ZTP password 字段去掉默认（onboard 必填 / recovery Optional(None)）；(2) ztp-stack 三脚本（entrypoint / ztp_runtime_render / ztp_onboard_callback）密码只从 `ZTP_ADMIN_PASS` 环境或 recovery override 注入，缺失明确 fail closed，不回退代码内口令；(3) recovery state 明文密码落盘 git 忽略目录且权限 `0600`（仅 ztp-server 渲染读取），GET/POST `/api/ztp/recovery-override` 响应递归脱敏（只回 `password_set` 布尔，浏览器不拿明文）；(4) 前端 `ZtpRecovery.vue` 加载已有 override 密码保持空白、留空提交 `null`（沿用已有/环境注入）、修改需重新输入；(5) 活动测试口令全替换为明显 synthetic；`ops-toolkit/scripts/debug-v24-*.py` 5 个无入口临时脚本（裸 ncclient + 硬编码凭据，REVIEW-v242 已列为 P2 清理债）按规则移除；(6) 活动模板/活动运维文档（`autocfg.cfg.j2`/`docs/ztp-stack.md`/`.env.example`/`openspec/specs/device-crud-ui/spec.md`）移除字面量。**历史已暴露，必须由用户在设备与 `.env` 外部轮换**；archive/ 历史 change 与 `RELEASE-NOTES-v2.3.1.md` 历史发布记录按「不改写历史」保留并显式登记（见 review-manifest）。

> 状态：**READY_FOR_CODE_REVIEW**（**等待 Codex 复审**，未提前宣称复审通过）。S1-006～S1-018 全部 CR 闭环（CODE_REVIEW_PASSED）。S1-019 真机验证发现「首次接入自阻断」：collector 已表达 `vsi_up.required = bool(active/expanding 本地绑定)`，但 `_l2_ready_status` 忽略 required、无条件要求 `vsi_up=True`，fresh VPC 无下联 AC/tunnel 时 `VSI State: Down` 永远阻断第一个端口接入（控制流因果悖论）。S1-020 已修复（统一两处语义：无 active/expanding 绑定时 `vsi_up` 不作为门禁，首次 AC bootstrap 放行；有绑定时仍保守阻断），并于 2026-09-10 在 `.5 / 192.168.100.5 / SWC / S6850 T7064P15 / LSTN` 走完一轮**完整真机生命周期**（默认 skip 的 `test_s1_019_reallife.py`）：VPC create/apply ✅、真实 display + 目标 RD `1:20000` 块内 Type-3 `[3]` ✅、access preview/execute/apply ✅（GE1/0/10 `service-instance 3200` + `xconnect vsi` AC 回读确认）、complete 无主机诚实 `degraded`/`host_observed=False` ✅、access withdraw ✅（GE1/0/10 回读确认撤销）、VPC withdraw ✅、兜底清理 sdn_l3vpn/vxlan global ✅、最终 readback 残留为空 ✅。未伪造成功、未 save/改 startup-config、未触碰 GE1/0/1~3/MGE0/0/0/underlay/OSPF/BGP 邻居、未碰 `.6`；未推送/tag/归档/close stage、未重启既有服务。
>
> **S1-021（历史轮次）**：修复两个复审阻断项——(1) 真机测试 docstring 与 review manifest 曾声称共享 `sdn_l3vpn`/VXLAN global「由 runner 兜底清理」，但仓库内没有该 runner；裸 pytest 的 `finally` 只尝试 VPC withdraw 且吞掉 withdraw 异常。**真实事实**：S1-020 完整生命周期通过后，测试自身 VPC/access withdraw 完成后仍发现两个共享对象残留，由**测试外的 ops-toolkit** 精确兜底清理并最终 readback 干净（当时尚无自动 runner，不写成当时已有 runner 自动完成）。(2) readiness 曾提前宣称「Codex 已完成代码复审与独立复跑」——已改为「**等待 Codex 复审**」。新增唯一宿主安全 runner（`qa/run_s1_019_real_lifecycle.sh`）包装真机 pytest：默认拒绝真机（`--integration` / `S1_019_REAL=1` / 精确 `192.168.100.5` / `--cleanup-shared` 四重门禁，目标非 .5 在设备 I/O 前退出）；凭据只从 `.env`/环境注入不落盘；额外设备读写走 ops-toolkit 既有入口；pytest 前保存最小基线、共享对象基线已存在则拒绝承担所有权、绝不在 trap 中删除既有配置；进入可写阶段装 trap，无论成功/失败/Ctrl-C/TERM 都按恢复清单精确兜底清理 + 最终 readback 回到基线（返回码 0 ≠ 清理成功）；保留 pytest 原始退出码但 cleanup/readback 失败时整体失败并指示人工；本机 flock 锁防并发。
>
> **S1-022（本轮，窄整改，不连真机、无任何设备 I/O）**：修复 Codex 复审两个阻断项——(1) 审计目录指向不可创建路径时，runner 在 baseline 文件写入失败后仍打印 `BASELINE-OK` 并进入可写阶段；退出时 `run_ops ... > cleanup.txt` 的重定向在命令启动前失败，导致两条共享 undo 根本没执行，只能报 `MANUAL-NEEDED`，违反「保存基线后才允许写」与「trap 必须实际尝试清理」契约。(2) `test_lock_prevents_concurrent_runners` 中 `assert not _has_undo(...) or True` 恒真。**S1-022 修复**：任何设备 I/O 前可靠创建并验证审计目录可写（`umask 077` + 临时探针文件后删除，失败直接退出码 6，不采集基线、不跑 pytest）；baseline 必须成功持久化后才设置可写阶段（写失败在 pytest 前终止，退出码 4）；EXIT trap 中 cleanup/final readback 一律「先真实执行并捕获返回码/输出，再尽力写审计文件」——审计目录在 pytest 期间被删除/变只读/写失败不得阻止精确清理与回读，审计写入失败本身让 runner 最终非零（`MANUAL-NEEDED`）但不替代 cleanup/readback；cleanup 失败不跳过 final readback；修掉恒真断言（并发 loser 真实断言：无新增 ops 调用、无 undo）。**本轮未运行真机模式、未执行任何设备 I/O**（runner 与对抗测试仅以 stub/fake 命令验证）。

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
`pytest tests/test_s1_020_adversarial.py -q` = **9 passed**（修复前 5 failed / 4 passed 证明 S1-019 基线失败）。
`pytest tests/test_s1_021_runner_adversarial.py -q` = **21 passed**（S1-021 16 条 + S1-022 新增 5 条，stub/fake 命令，未触真机；见下「S1-022 真机运行与恢复契约」）。
`pytest tests/test_ztp_recovery.py tests/test_ztp_onboard.py tests/test_s1_023_credential_hygiene.py -q` = **21 passed**（S1-023 新增 11 条 + ZTP recovery 扩展 5 条 + onboard 5 条；未触真机；见下「CR42」）。
`pytest tests/test_sdn_explanation.py -q` = **27 passed**（S1-026：含畸形历史 JSON 的 API 安全降级；未触真机）。
`pytest tests/test_s1_024_credential_hygiene.py -q` = **6 passed**（S1-024/CR43：特殊字符密码原样渲染不执行注入（模块级 + entrypoint 全量运行级 stub dnsmasq/真实 jinja2）、首次与覆盖重渲染均 0600、失败路径不残留宽权限/含口令临时文件、缺 env 写盘前明确失败、entrypoint 渲染块静态断言；未触真机；见下「CR43」）。
`pytest tests/test_sdn_explanation.py tests/test_sdn_access_api.py tests/test_sdn_operation_service.py tests/test_sdn_validation_api.py tests/test_sdn_apply_endpoint.py -q` = **65 passed**（受影响回归 + 投影；未触真机）。
`pytest tests/test_s1_024_credential_hygiene.py tests/test_ztp_recovery.py tests/test_ztp_onboard.py tests/test_s1_023_credential_hygiene.py tests/test_device_api.py tests/test_ops_toolkit_paramiko.py tests/test_smoke.py tests/test_backup_integration.py tests/test_vpn_integration.py tests/test_split_integration.py tests/test_s1_019_doc_alias.py tests/test_s1_019_reallife.py tests/test_s1_016_adversarial.py tests/test_s1_017_adversarial.py tests/test_s1_018_adversarial.py tests/test_s1_020_adversarial.py tests/test_s1_021_runner_adversarial.py tests/test_sdn_validation_api.py tests/test_sdn_access_api.py tests/test_sdn_operation_service.py tests/test_sdn_migration.py -q` = **187 passed / 16 skipped**（skip 全为 integration 门控：reallife/backup/vpn/split/ops_toolkit_paramiko/smoke 的 `--integration` 用例；S1-020 时 74/1，S1-021 时 90/1，S1-022 时 95/1，S1-023 时 181/16）。
前端（qa-frontend 镜像，隔离，无 .env）：lint + type-check + build + vitest = **62 passed**（8 文件，含 ZtpRecovery.spec.js 4 条：密码留空/提交 null/显式重输/无字面量）。
真机一轮（S1-020 历史执行，完整生命周期）：`test_s1_019_reallife.py -m integration --integration` = **1 passed**（49.9s）。**S1-021/S1-022/S1-023/S1-024/S1-026 均未跑真机、无任何设备 I/O。**
`openspec validate --strict next-s1-backend` = **valid**；manifest JSON = **valid**；`git diff --check` = **clean**；活动源码凭据扫描（真实默认口令前缀（含截断变体））= **干净**（仅 archive/ 历史与 `RELEASE-NOTES-v2.3.1.md` 按「不改写历史」保留并登记）。

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

## CR39（S1-020 本轮修正：首次接入自阻断）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR39 统一 `_l2_ready_status` 与 collector 的 `vsi_up.required = bool(active/expanding 本地绑定)` 语义 | ✅ | `_l2_ready_status` 动态查询目标 Leaf `status ∈ {active, expanding}` 本地绑定：无绑定 → `vsi_up` 不作为门禁（首次 AC bootstrap 放行）；有绑定 → `vsi_up` 仍必需、Down 保守阻断；`unbound/planned` 不误判；其余三项 + 版本因果/TTL/配置完成时间/命令完整性/CLI 错误/BGP peer/VSI 存在/目标 RD Type-3 门禁不删不放宽；preview/execute 共用同一 `_l2_ready_status`，force refresh 与失败零业务副作用保留；S1-017 `test_l2_condition_false_blocks` 参数化移除 `vsi_up`（动态语义移至 S1-020） | `test_no_local_binding_vsi_up_down_is_ready` + `test_active_binding_vsi_up_down_blocks[active/expanding]` + `test_active_binding_vsi_up_true_ready` + `test_unbound_or_planned_binding_does_not_require_vsi_up` + `test_preview_uses_dynamic_vsi_up_semantics` + `test_execute_uses_dynamic_vsi_up_semantics` + `test_execute_active_binding_vsi_up_down_blocks_without_side_effects` |

## CR40（S1-021 本轮：真机生命周期安全 Runner 与交付口径修正）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR40 唯一宿主安全 runner + 诚实清理契约 | ✅ | `openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`：默认拒绝真机（`--integration`/`S1_019_REAL=1`/精确 `.5`/`--cleanup-shared` 四重门禁，目标非 .5 设备 I/O 前退出）；凭据仅 `.env`/环境注入不落盘；额外设备读写走 ops-toolkit 既有入口；pytest 前保存最小基线（身份/VSI/EVPN/共享/GE1/0/10），共享对象基线已存在→拒绝承担所有权、绝不在 trap 删除既有配置；进入可写阶段装 trap，成功/失败/Ctrl-C/TERM 都按恢复清单精确兜底清理（仅 system-view + undo sdn_l3vpn + undo vxlan global + return，无 save/越界）+ 最终 readback 回到基线（返回码 0 ≠ 清理成功）；保留 pytest 原始退出码但 cleanup/readback 失败整体失败并指示人工；本机 flock 锁防并发；compose 只读挂载 qa 目录供对抗测试。真机测试 docstring/readiness/review-manifest 标准跑法改为唯一 runner，裸 pytest 不再暗示能清共享对象；如实记录 S1-020 历史共享残留由测试外 ops-toolkit 精确兜底 | `test_s1_021_runner_adversarial.py`（16 条，stub/fake 命令：缺门禁/目标非 .5 设备 I/O 前失败、基线共享对象拒绝且无 undo、pytest 成功/失败都进 cleanup+readback、SIGINT/SIGTERM 触发 trap、pytest 失败保留非零/cleanup/readback 失败 runner 非零、cleanup 仅两条精确 undo 无 save/越界、并发锁退出 2） |

## CR41（S1-022 本轮：Runner 审计目录失效时仍必须安全清理）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR41 审计目录可靠性 + 先执行后落盘契约 | ✅ | `run_s1_019_real_lifecycle.sh`：(1) 任何设备 I/O 前 `setup_artifact_dir`（`umask 077` + `mkdir -p` + 临时探针文件后删除），失败直接退出码 6（不采集基线、不跑 pytest）；(2) baseline 成功持久化（`baseline.txt` 写失败→退出码 4）后才进入可写阶段；(3) EXIT trap 中 cleanup/final readback 一律「先真实执行并捕获返回码/输出（命令替换），再尽力写审计文件」——审计目录被删除/变只读/写失败不得阻止精确清理或回读执行；审计写入失败置 `AUDIT_FAIL=1` → `MANUAL-NEEDED` + runner 最终非零，但不替代 cleanup/readback；(4) cleanup 失败不跳过 final readback；(5) `stub_pytest.sh` 增加 `STUB_PYTEST_HOOK`（pytest 期间破坏审计目录的注入点） | `test_s1_021_runner_adversarial.py` 新增 5 条：`test_artifact_dir_uncreatable_fails_before_io` + `test_artifact_dir_is_a_file_fails_before_io`（ops 调用 0/pytest 未调用/非零）、`test_baseline_persist_failure_stops_before_pytest`（只 1 次基线只读、无 undo、无 pytest）、`test_artifact_dir_removed_during_pytest_cleanup_still_runs`（cleanup 两条精确 undo 仍实际调用 + final readback 仍实际调用 + runner 非零 + MANUAL-NEEDED）、`test_cleanup_device_failure_and_audit_failure_still_readback`（cleanup 设备失败 + 审计目录失败仍执行 final readback）；`test_lock_prevents_concurrent_runners` 去掉 `or True` 恒真断言，真实断言 loser 无新增 ops 调用/undo |

## CR42（S1-023 本轮：仓库凭据卫生与 ZTP 密码边界）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR42 活跃源码无真实口令字面量 + ZTP 密码边界（显式提交/环境注入、缺密码明确失败、state 0600、API 脱敏、前端留空） | ✅ | `schemas.py`（onboard password 必填 / recovery Optional(None)）；`ztp_recovery.py`（密码解析 显式→既有→`ZTP_ADMIN_PASS` 环境，全缺 `ValueError`；state 0600；GET/POST `_redact` 递归脱敏 + `password_set`）；`entrypoint.sh`（`${ZTP_ADMIN_PASS:?}` fail closed；autocfg.cfg 600；日志无口令）；`ztp_runtime_render.py`/`ztp_onboard_callback.py`（`_require_admin_pass()` 只从环境/override 取，缺失 `RuntimeError`）；`autocfg.cfg.j2`/`docs/ztp-stack.md`/`.env.example`/`openspec/specs/device-crud-ui/spec.md`（移除字面量，环境注入口径）；`ZtpRecovery.vue`（初始/加载留空、留空提交 null、显式重输）；移除 `ops-toolkit/scripts/debug-v24-*.py`（5 个无入口临时脚本，REVIEW-v242 P2 债 + 裸 ncclient 违反红线） | `test_s1_023_credential_hygiene.py`（11 条：活动生产路径/活动测试无真实默认口令前缀字面量、debug-* 已移除、ztp-stack 三脚本缺密码 fail closed、onboard 缺密码 422、state 0600/API 脱敏）；`test_ztp_recovery.py` 扩展 5 条（脱敏/0600/缺密码明确失败/环境注入/沿用已有）+ schema 无默认；`ZtpRecovery.spec.js` 3 条（留空/提交 null/显式重输/无字面量）；活动测试口令全替换 synthetic（31 处） |

## CR43（S1-024 本轮：ZTP 渲染凭据边界加固——安全原子写 + 环境注入渲染）

| CR | 状态 | 代码 | 测试 |
|---|---|---|---|
| CR43 渲染原子写权限回归 + entrypoint 密码注入 | ✅ | `ztp_runtime_render.py`：`_atomic_write_secret`——临时文件创建前 `umask 077` + `os.open(O_CREAT\|O_EXCL, 0600)`（创建即 0600，规避进程 umask 放宽）→ `os.fdopen` 写入 + flush + fsync → `os.replace` 原子替换 → 显式 `os.chmod(0600)`；任何异常 `unlink` 临时文件（不残留宽权限/含口令中间文件）。`entrypoint.sh`：python3 -c 渲染块改纯环境注入——零 `$`/零单引号插值，全部渲染变量（`ZTP_PLATFORM`/`ZTP_PLATFORM_LONG`/`ZTP_MGMT_IP`/`ZTP_SYSNAME`/`ZTP_ADMIN_USER`/`ZTP_ADMIN_PASS`/`ZTP_HCL_T7064P15`/`ZTP_DATE`/`ZTP_AUTOCFG_TEMPLATE`）`os.environ[...]` 读取；`ZTP_PLATFORM_LONG` 补 export；输出 `mktemp`（创建即 0600）+ 显式 `chmod 600` + `mv -f` 原子替换 + trap 失败清理，不经宽权限中间态 | `test_s1_024_credential_hygiene.py`（6 条）：`test_renderer_special_char_password_verbatim_no_injection`（特殊字符密码模块级原样渲染、无注入、0600）、`test_entrypoint_full_run_special_char_password_verbatim_no_injection`（entrypoint 全量运行级：stub dnsmasq + 真实 jinja2，env 注入渲染原样、无注入、0600、无中间文件）、`test_renderer_first_and_rerender_keep_0600`（首次与覆盖重渲染均 0600，直击 0644 回归）、`test_renderer_failure_leaves_no_wide_secret_temp`（os.replace 失败路径不残留 .tmp/含口令中间文件）、`test_renderer_missing_env_fails_before_any_write`、`test_entrypoint_render_snippet_is_env_only_no_shell_interpolation`（静态断言 os.environ 读取/mktemp/chmod/mv/trap） |

## S1-026（本轮：operation 解释投影，只读 serializer）

- **形态核对**（先看真实证据再定投影，不照抄前端 mock 的 summary/source/scope）：execute/withdraw attempt 的 unit evidence 成功时为 `None`、失败为 `{"error", "definitive"}`、reconcile 解析后为 `{"reconciled", "snapshot_id", "reason"}`；validate attempt 的 attempt-level evidence 为 `{"dimensions", "gateway_ping", "observations"}`（或采集失败 `{"dimensions": {"evidence": {"status": "insufficient"}}}`、stale takeover `{"stale_takeover": true}`）；reconcile attempt 无 units；legacy operation 为 `legacy_apply` 且可能无 scope。
- **诚实表达缺口登记**：`protected_interfaces` 未持久化于 operation → 投影为 null（不编造）；unit 级 `freshness` 无独立时效时间戳 → null；无回读证据的执行记录 `observed_at=null`；operation `verified` 与 `succeeded_recorded` 的区分依赖 validate attempt 的确定完成。
- **契约**：operation 级 intent/scope_summary/safety_boundary(target/target_only/ambiguous_claims/protected_interfaces)/truth_state/headline/statement；attempt 级 explanation(kind/summary/result/finished/still_uncertain/evidence_basis/statement/started_at/completed_at)；unit 级 explanation(category/statement/truth_kind/source/scope/observed_at/freshness)，truth_kind ∈ desired|observed|inferred|pending。中文由前端 i18n，后端只回稳定 code + 语言中性 fallback。

## schema 变化

`openspec/changes/next-s1-backend/` 的 012 migration 已扩展：`sdn_operations` 新增 `active_attempt_id`（Integer, nullable）与 `active_started_at`（DateTime, nullable）两列；`_create_table_if_missing` 对已存在表幂等补列，ORM `SdnOperation` 同步。令牌/租约仅存于数据库持久状态，无进程内锁。

## S1-020 真机生命周期结果（de-identified，完整链路，历史执行 2026-09-10）

> 前置：S1-019 首次真机验证暴露 `vsi_up` 无条件必需导致「首次接入自阻断」（fresh VPC 无 AC 时 VSI Down 永远阻断第一个端口）。S1-020 修复后重跑一次完整生命周期，**不再把 predeploy 阻断断言为 PASS**。
> 清理口径（如实）：本轮执行时仓库内**尚无**自动 runner；测试自身 VPC/access withdraw 完成后，`sdn_l3vpn` 与 VXLAN global 两个共享对象仍有残留，由**测试外的 ops-toolkit** 监督执行精确兜底清理（`undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable`）并最终 readback 干净。S1-021 起真机轮次由唯一宿主 runner 自动承担该契约。

| 步骤 | 结果 | 证据/说明 |
|---|---|---|
| 设备身份交叉确认 | ✅ | `display bgp peer l2vpn evpn` Router ID `1.1.1.4` + `display version` S6850 T7064P15，prompt `<SWC>` |
| VPC create/apply | ✅ | 5 unit 成功（LSTN→SSH22 CLI）；VSI `vpc0001` + VXLAN 20000 + EVPN RD `1:20000` + Vsi-interface1000 + sdn_l3vpn + vxlan global 落设备 |
| 真实 display 采集 + Type-3 作用域 | ✅ | `vsi_exists=True`、`bgp_peer_established=True`、`type3_present=True`（目标 RD `1:20000` 块内 `[3]`）；`vsi_up=False`（无 AC，VSI State Down，S1-020 起不再阻断首个 AC） |
| GE1/0/10 access preview | ✅ | `predeploy_status=ready`（S1-020 动态语义：无绑定不要求 vsi_up） |
| GE1/0/10 access execute | ✅ | **成功**（operation 创建；S1-020 修复后不再 `sdn.predeploy_unknown`） |
| GE1/0/10 access apply | ✅ | port_bind 1 unit 下发成功；回读 `display current-configuration interface GE1/0/10` 确认 `service-instance 3200` + `xconnect vsi vpc0001` 实际存在 |
| access complete（无下联主机） | ✅ 诚实 | `status=degraded`、`dimensions.business_validation.host_observed=False`（无主机证据，不冒充业务成功；l2_ready=True/l3 网关维度 ok） |
| access withdraw | ✅ | port_unbind 1 unit 下发成功；回读 GE1/0/10 确认 `service-instance/xconnect` 已撤销 |
| VPC withdraw | ✅ | delete deployment（3 unit）成功，VSI/Vsi-interface/RD 移除 |
| 兜底清理（fallback） | ✅ 发生 | **测试外的 ops-toolkit**（当时无自动 runner）`undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable`（产品保留的共享对象，基线不存在，前后 readback）；S1-021 起由 `qa/run_s1_019_real_lifecycle.sh` 自动兜底 |
| 最终设备残留 | ✅ 空 | VSI 空 / `display bgp l2vpn evpn` routes 0 / 无 sdn_l3vpn / 无 vxlan / 无 service-instance / GE1/0/10 回基线（`port link-mode bridge` + `combo enable fiber`） |
| DB 收尾 | ✅ | `active_bindings=0`、`unreleased_claims=0` |
| 未验证数据面边界 | ⚠️ | 跨 leaf 数据面转发、网关 ping reachable、主机 ARP/MAC 学习（无下联主机，未伪造成功）；complete 已诚实表达为 degraded |

## S1-022 真机运行与恢复契约（唯一宿主安全 runner）

**runner 路径**：`openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`（唯一、可复用）。

**标准跑法（后续所有真机轮次一律走此）**：
```bash
cd openspec/changes/next-s1-backend/qa
S1_019_REAL=1 S1_019_REAL_HOST=192.168.100.5 \
  ./run_s1_019_real_lifecycle.sh --integration --cleanup-shared
```

**守卫行为**（`test_s1_021_runner_adversarial.py` 21 条以 stub/fake 命令验证，未触真机）：
1. 默认拒绝真机；四重门禁缺一 / 目标非 `.5` → 在**任何设备 I/O 前**退出（码 3）。
2. 凭据只从既有 `.env`/环境注入，不打印、不复制到文件。
3. 额外设备读取与兜底写入全部走 ops-toolkit 既有入口（`paramiko-batch-exec.sh`）；业务生命周期仍由 backend API/executor 执行；不新增裸 SSH/paramiko。
4. **任何设备 I/O 前**：`umask 077` + 创建并验证审计目录可写（临时探针文件后删除）；失败直接退出（码 6），不采集基线、不跑 pytest。
5. pytest 前读取并保存最小基线（设备身份 `1.1.1.4`/`S6850`、VSI 空、EVPN routes 0、无 `ip vpn-instance sdn_l3vpn`、无 `vxlan tunnel mac-learning disable`、GE1/0/10 `port link-mode bridge`+`combo enable fiber`）；**baseline 必须成功持久化后才进入可写阶段**（写失败 → 码 4 在 pytest 前终止）；**共享对象基线已存在 → 拒绝承担其所有权（退出码 5），绝不在 trap 中删除既有配置**。
6. 进入可写阶段后安装 shell trap：无论 pytest 成功/失败/Ctrl-C/TERM，只要基线证明两个共享对象原先不存在，就按恢复清单精确兜底清理——仅 `system-view` + `undo ip vpn-instance sdn_l3vpn` + `undo vxlan tunnel mac-learning disable` + `return`（无 `save`、无越界命令）。
7. **cleanup / final readback 均「先真实执行并捕获返回码/输出，再尽力写审计文件」**：审计目录在 pytest 期间被删除/变只读/写失败，不得阻止精确清理或回读执行；审计写入失败 → `MANUAL-NEEDED` + runner 最终非零，但不替代 cleanup/readback；cleanup 失败不跳过 final readback。
8. cleanup 之后始终最终 readback，确认 VSI/测试 VPC、测试 AC、共享对象均回到基线；**命令返回码 0 ≠ 清理成功**（以 readback 证据为准）。
9. 保留 pytest 原始退出码；但 cleanup、final readback 或审计写入失败时 runner 整体失败（码 6）并输出 `MANUAL-NEEDED` 指示人工处理。
10. 本机 flock 锁防并发（第二个 runner 在设备 I/O 前退出码 2；测试真实断言 loser 无新增 ops 调用/undo）。

**本轮状态**：未运行真机模式、未执行任何设备 I/O；以上全部通过 stub/fake 命令在隔离 QA 容器验证。

## 下一轮待办

1. **S1-026 已由 Codex 复审通过**（operation 解释投影，CODE_REVIEW_PASSED，尚未归档）。
2. **S1-027（CR45）真实应用栈联调契约修复**：随 NEXT 工作台真实联调通道（`openspec/changes/next-s1-workbench/qa/`）暴露并修复两处生产契约——(a) 前端语义 `mode='l2'` 放行并归一化为 auto（schemas + `h3c_v7_port_bind.render`）；(b) 001 迁移幂等补建 devices/logs 基表，空库 `alembic upgrade head` 可完整升级。回归测试 `test_access_mode_l2_alias_preview_and_execute` + `test_fresh_empty_db_upgrade_head_bootstraps_base_tables`。等待 Codex 复审。
3. **凭据轮换（外部，用户执行）**：历史已暴露——用户须在**设备**与 `.env`（`DEVICE_PASSWORD`/`ZTP_ADMIN_PASS`）外部轮换真实口令；本包不改设备、不重写 Git 历史、不改 archive/ 历史 change 与 `RELEASE-NOTES-v2.3.1.md` 历史发布记录。
4. 真机验证轮次须走 `qa/run_s1_019_real_lifecycle.sh`（唯一 runner），不再裸跑 pytest；`ZTP_ADMIN_PASS` 缺失时 ztp-server 按契约 fail closed（先设 `.env` 再启）。
5. 清理 __pycache__/logs（每轮结尾已执行）。

真机链路已按 S1-020 走完完整生命周期（见上表）；仅剩无下联主机导致的数据面边界（跨 leaf/网关 ping/主机 ARP-MAC）为「未验证」而非「伪造成功」。

## S1-027 真实应用栈联调（隔离，无设备 I/O）

联调通道与契约修复细节见 `openspec/changes/next-s1-workbench/qa/` 与 review-response.md CR45。后端本轮改动：`backend/app/schemas.py`（mode pattern 放行 `l2`）、`backend/app/services/templates/h3c_v7_port_bind.py`（l2→auto 归一化）、`backend/migrations/versions/0c1928618be4_add_assets_table.py`（空库 bootstrap）、`backend/tests/test_sdn_access_api.py` / `backend/tests/test_sdn_migration.py`（回归）。QA：qa-backend 46 passed（含新回归）+ 受影响回归 66 passed；真实栈 Playwright 2 passed × 2 次。未执行任何设备 I/O。

**S1-028 整改（QA 通道可复现性 + 运行时硬隔离，无业务语义改动）**：`qa/Dockerfile.stack-qa` 不再 FROM 本项目预构建镜像（原 `next-s1-backend-qa-frontend:latest`），改 FROM 公开固定基础镜像 `node:20-alpine`，apk 装 python3/venv/系统 chromium，前端依赖走仓库锁文件 `npm ci`（删除 `npm install ... || true` 吞错；安装失败即构建失败）；`docker-compose.stack-qa.yml` 运行容器加 `network_mode: none`——构建期联网下载公开依赖，运行期无外部网络，FastAPI/Vite/Chromium 全部经 loopback 通信。验证：移除 qa-frontend 镜像后 stack 镜像独立构建成功；`compose config` 确认 network_mode none / 无 env_file / 无 docker.sock / 无生产挂载；完整 stack QA 一次运行 = 2 passed + BOUNDARY_OK + STACK_QA_OK（断网 loopback 故事成立）。

**S2-001 状态差异投影**：新增 `GET /api/sdn/vpcs/{id}/state-projection`，按 EVPN Leaf 返回目标态、最近观测和逐维差异。目标态由 deployment 生命周期与版本证明，并分开 L2 VSI 与 L3 网关；缺失/失败/过期/损坏证据不冒充漂移，多值接口配置与编号/名称均精确匹配。只读零设备 I/O/零写入；隔离 QA 127 passed。前端 STRATA 尚未消费该接口。
