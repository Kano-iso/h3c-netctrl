# 复审响应（review-response）

## Codex 最终复审结论（S1-026，2026-09-14）

**CODE_REVIEW_PASSED（经修正）**。首次复审发现三处诚实性/韧性问题并已直接修复：畸形历史 JSON 的解析移入安全边界；已确定终态不再被历史 stale takeover 永久标成当前 claims 歧义；无设备回读证据的执行记录不再填写 `observed_at`。后端相关回归 65 passed；前端已消费真实 explanation code，并通过 lint、type-check、build、62 个组件测试和 4 个 NEXT 浏览器流程。本轮未连接设备、未执行设备 I/O。

---

## S1-026（operation 解释投影，只读 serializer，最新；本轮未触真机）

> 本轮为增量只读投影，**不连真机、无任何设备 I/O、不改设备、不重写 Git 历史、不轮换凭据**。`GET /api/sdn/operations/{id}` 响应新增只读、additive 的 `explanation` 投影（保留全部既有字段与原始 `scope`/`evidence` 原样返回）：operation 级 `intent`/`scope_summary`/`safety_boundary`（target + ambiguous_claims + protected_interfaces=null）/`truth_state`/`headline`；attempt 级 `explanation`（kind/result/finished/still_uncertain/evidence_basis/statement）；unit 级 `explanation`（category/statement/truth_kind=desired|observed|inferred|pending/source/scope/observed_at/freshness=null）。投影为 serializer 纯函数层（新增 `services/sdn_explanation.py`，`sdn_access.py::_operation_to_dict` 只组装），不新增表、不迁移、不改 apply/validate/withdraw/reconcile 行为；解释失败 `_safe_explain` 降级 `{"unavailable": true}` 绝不 500。**诚实表达**：succeeded 单元无观察证据只表达「执行记录成功」（truth_state=succeeded_recorded、truth_kind=desired），不冒充「设备已验证成功」；中文不固化后端（稳定 code + 语言中性 fallback，前端 i18n）。

**QA（隔离容器，未触真机）：**
- `test_sdn_explanation.py` = **27 passed**（含 API 级畸形历史 JSON 安全降级）。
- 受影响回归（access/operation_service/validation/apply + 投影）= **65 passed**。
- `openspec validate --strict` valid；manifest JSON valid；`git diff --check` clean；活动源码凭据扫描干净。

**请 Codex 复审重点**：1) 投影契约（intent/truth_state 区分 verified 与 succeeded_recorded、unit truth_kind 的 desired/observed/inferred/pending 归类）是否诚实且数据可证；2) `_safe_explain` 降级与「解释失败不 500」是否满足 PULSE/STRATA 消费要求；3) 投影是否确实 additive——旧字段与原始 evidence 无任何移除/改写。

---

## S1-027（CR45：真实应用栈联调暴露的契约修复；本轮未触真机）

> 本轮为 S1-027 真实应用栈隔离联调（NEXT 工作台 ↔ 真实 FastAPI + 隔离 SQLite）暴露出的两处生产契约修复，**不连真机、无任何设备 I/O、不改设备、不重写 Git 历史、不轮换凭据**。修复后回归测试全部通过。

**CR45-1 前端语义 `mode='l2'` 被后端 schema 拒绝（422）**：前端 `SdnVpcWorkspace` 始终以 `mode:'l2'` 请求 preview/execute，而后端 `SdnAccessPreviewRequest`/`SdnAccessExecuteRequest.mode` 的 pattern 仅允许 `auto|service_instance|access_vlan`——真实联调在预览即 422，mock 基线永远测不到。修复（additive，语义不变）：两处 schema pattern 放行 `l2`；`H3cV7PortBindTemplate.render` 将 `l2` 归一化为 `auto`（service_instance 优先、access_vlan fallback，ADR-104 决策不动）。回归：`test_access_mode_l2_alias_preview_and_execute`（preview 200 + blocking=[] + execute 走 service-instance 模板）。

**CR45-2 全新库 `alembic upgrade head` 失败（003 `no such table: logs`）**：迁移链是「棕地」链——002/003/004 假设 devices/logs 基表已由 create_all 预建，但迁移从未创建这两张表；空库从 001 一路升级在 003 必失败，生产新装无法启动（qa 测试因 TestClient 不触发 startup 从未暴露）。修复：001（迁移链起点）`_bootstrap_base_tables()` 幂等补建缺失的 devices/logs 基表（仅基础列，protected_interfaces/platform/sdn_role/error_message 仍由各自迁移添加；守卫风格同 006）。已有库 alembic_version 已含 001，不重跑、不受影响。回归：`test_fresh_empty_db_upgrade_head_bootstraps_base_tables`（空库 upgrade head 成功 + 基表/后续列齐备 + 重复 upgrade 幂等）。

**QA（隔离容器，未触真机）：**
- 真实应用栈通道（`openspec/changes/next-s1-workbench/qa/`）：2 Playwright spec 通过 × 连续 2 次独立运行；`device-io.log` 断言 BOUNDARY_OK（21 事件全为边界 fake，netconf 目标均为 TEST-NET 合成地址）。
- **S1-028 整改（QA 通道可复现性 + 运行时硬隔离；无业务语义改动）**：镜像改 FROM 公开固定基础镜像 `node:20-alpine` 独立构建（apk python3/venv/系统 chromium；前端锁文件 `npm ci`，失败即构建失败、无 `|| true` 吞错；不依赖本项目预构建镜像）；compose 运行容器 `network_mode: none`（构建期联网、运行期无外部网络、loopback 内联调）。验证：移除 `next-s1-backend-qa-frontend:latest` 后独立构建成功；`compose config` 确认 network_mode none / 无 env_file / 无 docker.sock / 无生产挂载；完整 stack QA 一次运行 = 2 passed + BOUNDARY_OK + STACK_QA_OK。
- qa-backend：`test_sdn_explanation.py + test_sdn_access_api.py + test_sdn_migration.py` = **46 passed**（含上述 2 个新回归）；受影响回归（explanation/access/operation_service/validation/apply）= **66 passed**。
- 前端（qa-frontend）：lint / type-check / build / vitest / 默认 e2e 无回归。

**请 Codex 复审重点**：1) `l2` 归一化为 auto 是否与前端语义（L2 接入、service_instance 3200、access_vlan null）一致；2) 001 基表引导是否对已有库零影响、对空库可完整升级且幂等；3) 联调通道的边界 fake 注入是否只发生在测试入口、生产入口零加载。

---

## Codex 最终复审结论（S1-024，2026-09-11）

**CODE_REVIEW_PASSED**。CR43 两项阻断已闭环：运行时重渲染使用 0600 安全原子写，entrypoint 渲染变量全部经环境读取，不再把密码拼入 Python 源码或命令行。Codex 已复核实现与对抗测试，并再次通过 `bash -n`、OpenSpec strict、manifest JSON、`git diff --check` 和活动源码凭据扫描；本轮未连接真机、未执行设备 I/O。

该结论允许形成 Git 灾备检查点；历史中已暴露的设备口令仍必须在设备和运行环境中外部轮换。

## S1-024（CR43：ZTP 渲染凭据边界加固，最新；本轮未触真机）

> 本轮为 Codex 复审（S1-023）2 项阻断的修复，**不连真机、无任何设备 I/O、不改设备、不重写 Git 历史、不轮换凭据**。已修复：**CR43-1 渲染原子写权限回归**——`ztp_runtime_render.render_once` 旧实现 `tmp.write_text` 受 umask 影响创建 0644、`tmp.replace` 用临时文件权限替换目标，重渲染把 `autocfg.cfg` 从 0600 变 0644；现改 `_atomic_write_secret`（创建前 `umask 077` + `os.open(O_CREAT|O_EXCL, 0600)` 创建即 0600 → flush/fsync → `os.replace` → 显式 `os.chmod(0600)`，异常 unlink 临时文件）。**CR43-2 entrypoint 密码注入**——旧实现把 `ZTP_ADMIN_PASS` 等环境值直接插进 `python3 -c` 单引号源码（特殊字符语法失败/注入）；现改纯环境注入（python3 -c 零 `$`/零单引号插值、全部渲染变量 `os.environ[...]` 读取、`ZTP_PLATFORM_LONG` 补 export、输出 mktemp(0600)+chmod 600+mv 原子替换+trap 清理）。

**QA（隔离容器，未触真机）：**
- `test_s1_024_credential_hygiene.py` = **6 passed**（特殊字符密码原样渲染不执行注入——模块级 + entrypoint 全量运行级 stub dnsmasq/真实 jinja2；首次与覆盖重渲染后均 0600；os.replace 失败路径不残留宽权限/含口令临时文件；缺 env 写盘前明确失败；entrypoint 渲染块静态断言）。
- 受影响文件 + S1-023 + S1-016~022 + validation/access/service/migration + runner 对抗 = **187 passed / 16 skipped**（skip 全为 integration 门控）。
- 前端 lint + type-check + build + vitest = **62 passed**（8 文件，含 ZtpRecovery 4 条；本轮前端未改动）。
- `bash -n`、`openspec validate --strict` valid、manifest JSON valid、`git diff --check` clean、活动源码凭据扫描干净。

**请 Codex 复审重点**：1) `_atomic_write_secret` 的 umask 收紧 + O_EXCL + replace 后 chmod 是否彻底解决「重渲染放宽权限」且失败不留中间文件；2) entrypoint python3 -c 环境注入是否仍有任何秘密拼入源码/命令行的路径；3) 特殊字符密码对抗测试（含 entrypoint 全量运行级）是否足以证明无注入。

---

## S1-023（仓库凭据卫生与 ZTP 密码边界；本轮未触真机）

> 本轮为凭据卫生整改，**不连真机、无任何设备 I/O、不改设备、不重写 Git 历史、不轮换凭据**。已修复：活跃源码真实口令字面量移除（`schemas.py` 去默认 / ztp-stack 三脚本 fail closed / 模板与活动文档去字面量 / 前端留空）；recovery state 0600 + API 递归脱敏（GET/POST 不回显密码，只回 `password_set`）；活动测试口令全替换 synthetic；`ops-toolkit/scripts/debug-v24-*.py`（5 个无入口临时脚本，裸 ncclient + 硬编码凭据）按规则移除。**历史已暴露，必须由用户在设备与 `.env` 外部轮换**；archive/ 历史 change 与 `RELEASE-NOTES-v2.3.1.md` 历史发布记录按「不改写历史」保留并登记。

**QA（隔离容器，未触真机）：**
- `test_ztp_recovery.py` + `test_ztp_onboard.py` + `test_s1_023_credential_hygiene.py` = **21 passed**（ZTP recovery 脱敏/权限/缺密码明确失败/环境注入/沿用已有 + onboard + 静态扫描 + ztp-stack fail closed + debug-* 移除）。
- 受影响文件 + S1-016~022 + validation/access/service/migration + runner 对抗 = **181 passed / 16 skipped**（skip 全为 integration 门控）。
- 前端 lint + type-check + build + vitest = **62 passed**（8 文件，含 ZtpRecovery 4 条）。
- `openspec validate --strict` valid；manifest JSON valid；`git diff --check` clean；活动源码凭据扫描干净（真实默认口令前缀（含截断变体））。

**请 Codex 复审重点**：1) ZTP 写操作密码解析（显式→既有→`ZTP_ADMIN_PASS` 环境，全缺明确失败）与 entrypoint/渲染/回调的 fail-closed 是否符合「缺失不回退代码内口令」；2) recovery state 0600 与 GET/POST 递归脱敏是否足以让浏览器不接触明文；3) 前端「加载 override 留空、修改重输、留空提交 null」是否符合预期；4) debug-v24-* 移除（无入口临时脚本）是否符合项目规则。

---

## Codex 最终复审结论（S1-022，2026-09-10）

**CODE_REVIEW_PASSED**。Codex 独立复跑 S1-016～S1-022、validation/access/service/migration 共 **95 passed / 1 skipped**；另以 stub 重放审计目录不可创建反例，确认退出码 6、设备调用 0、pytest 调用 0。`bash -n`、QA Compose 解析、OpenSpec strict、manifest JSON、`git diff --check` 与凭据/越界命令扫描均通过。本轮复审未连接真机、未执行设备 I/O。

该结论允许形成 Git 检查点并进入下一阶段，不等同于 NEXT 前端体验、跨 Leaf 数据面或正式版本发布已经验收。

---

## S1-022（Runner 审计目录失效时仍必须安全清理，最新；本轮未触真机）

> 审核方：Codex（对 S1-021 的复审反馈，暂不通过；阻断只在安全 runner，业务代码无新问题）。用 stub 独立复现：将 `RUNNER_ARTIFACT_DIR` 指向不可创建路径时，runner 在 baseline 文件写入失败后仍打印 `BASELINE-OK` 并进入可能写设备阶段；退出时 `run_ops ... > cleanup.txt` 的重定向在命令启动前失败，导致两条共享 undo 根本没有执行，只能报 `MANUAL-NEEDED`。这违反「保存基线后才允许写」和「trap 必须实际尝试清理」的核心契约。另有测试质量问题：`test_lock_prevents_concurrent_runners` 中 `assert not _has_undo(...) or True` 恒真。

**S1-022 修复映射（代码/测试）：**
- 任何设备 I/O 前可靠创建并验证审计目录可写：`umask 077` + `setup_artifact_dir`（`mkdir -p` + 临时探针文件后删除）；失败直接退出（码 6），不采集基线、不跑 pytest。
- baseline 必须成功持久化（`baseline.txt` 写失败 → 码 4）后才设置可写阶段；写失败在 pytest 前终止。
- EXIT trap 中 cleanup / final readback 一律「先真实执行并捕获返回码/输出（命令替换），再尽力写审计文件」：审计目录在 pytest 期间被删除/变只读/写失败不得阻止精确清理或回读执行；审计写入失败置 `AUDIT_FAIL=1` → `MANUAL-NEEDED` + runner 最终非零，但不替代 cleanup/readback；cleanup 失败不跳过 final readback。
- 修掉恒真断言：`test_lock_prevents_concurrent_runners` 真实断言并发 loser 无新增 ops 调用、无 undo（日志仅 1 次基线只读、read 计数 1）。
- `stub_pytest.sh` 增加 `STUB_PYTEST_HOOK`（pytest 期间删除/破坏审计目录的注入点）。

**新增对抗测试（全部 stub，未触真机；`test_s1_021_runner_adversarial.py` 16 → 21 条）：**
- `test_artifact_dir_uncreatable_fails_before_io` / `test_artifact_dir_is_a_file_fails_before_io`：设备 I/O 调用数 0、pytest 未调用、非零退出（码 6）。
- `test_baseline_persist_failure_stops_before_pytest`：仅 1 次基线只读、无 undo、无 pytest（码 4）。
- `test_artifact_dir_removed_during_pytest_cleanup_still_runs`：cleanup 两条精确 undo 仍实际调用、final readback 仍实际调用、runner 非零 + `MANUAL-NEEDED`（审计写失败不替代 cleanup/readback）。
- `test_cleanup_device_failure_and_audit_failure_still_readback`：cleanup 设备命令失败（写 rc=1）+ 审计目录被破坏，仍执行 final readback。

**QA 证据（本轮，未触真机）：** `test_s1_021_runner_adversarial.py` = **21 passed**；S1-016~020 + validation/access/service/migration + runner 对抗 = **95 passed / 1 skipped**（skip=reallife 默认门）。`openspec validate --strict` valid；manifest JSON valid；`git diff --check` clean。**未运行真机测试、未执行任何设备 I/O。**

---

## S1-021（真机生命周期安全 Runner 与交付口径修正，历史）

> 审核方：Codex（对 S1-020 交付的两个复审阻断项）。(1) `test_s1_019_reallife.py` 最后声称共享 `sdn_l3vpn`/VXLAN global「由 runner 兜底清理」，但仓库内没有该 runner；裸 pytest 的 `finally` 只尝试 VPC withdraw 且吞掉 withdraw 异常；实际 S1-020 运行后两个设备级共享配置确有残留，由测试外的 ops-toolkit 精确清理。(2) `readiness.md` 提前宣称「Codex 已完成代码复审与独立复跑」，整体仍因本单阻断，不能提前写成复审通过。

**S1-021 整改（代码/测试）：**
- 新增唯一、可复用宿主安全 runner `openspec/changes/next-s1-backend/qa/run_s1_019_real_lifecycle.sh`，包装 S1-019/S1-020 真机 pytest（本轮只实现 + 模拟验证，**禁止实际运行真机模式**）：默认拒绝真机（`--integration`/`S1_019_REAL=1`/精确 `.5`/`--cleanup-shared` 四重门禁，目标非 .5 设备 I/O 前退出）；凭据只从 `.env`/环境注入不落盘；额外设备读写走 ops-toolkit 既有入口；pytest 前保存最小基线，共享对象基线已存在→拒绝承担所有权、绝不在 trap 删除既有配置；进入可写阶段装 trap，成功/失败/Ctrl-C/TERM 都按恢复清单精确兜底清理（仅两条共享 undo + 上下文，无 save/越界）+ 最终 readback 确认回基线（返回码 0 ≠ 清理成功）；保留 pytest 原始退出码但 cleanup/readback 失败整体失败并指示人工；本机 flock 锁防并发。
- 新增对抗测试 `backend/tests/test_s1_021_runner_adversarial.py`（16 条，stub/fake 命令，不启动生产网络、不读真实凭据、不连接设备）：缺门禁/目标非 .5 设备 I/O 前失败、基线已有共享对象拒绝且不发 undo、pytest 成功/失败都进 cleanup+readback、SIGINT/SIGTERM 触发 trap（可控子进程 + killpg）、pytest 失败 cleanup 成功保留非零 / pytest 成功 cleanup/readback 失败 runner 非零、cleanup 仅两条精确 undo 无 save/越界、并发锁第二个 runner 退出 2。
- 口径修正：真机测试 docstring 与 review manifest 标准跑法改为唯一 runner（裸 pytest 只是 runner 内部实现，不再暗示能清共享对象）；readiness 去掉「Codex 已完成代码复审」提前结论改「等待 Codex 复审」；review manifest 完成只写 `READY_FOR_CODE_REVIEW` 不写 `CODE_REVIEW_PASSED`；如实记录 S1-020 历史共享残留由测试外 ops-toolkit 精确兜底。

**QA 证据（本轮，未触真机）：** `test_s1_021_runner_adversarial.py` = **16 passed**；S1-016~020 + validation/access/service/migration + runner 对抗 = **90 passed / 1 skipped**（skip=reallife 默认门）。`openspec validate --strict` valid；manifest JSON valid；`git diff --check` clean。**未运行真机测试、未执行任何设备 I/O。**

---

## Codex 最终复审结论（S1-018，历史）

**CODE_REVIEW_PASSED**。Codex 已核对 S1-018 的目标 RD 分块实现、L2/L3 门禁边界、CR36/CR37/CR38 文档口径，并在隔离 QA 容器独立复跑 S1-016～018 共 31 条对抗测试，结果全部通过；OpenSpec strict、review manifest JSON 与 `git diff --check` 均通过。

该结论表示本后端工作包可以形成 Git 检查点并进入真机验证准备，不表示真机链路、前端体验或版本发布已经验收。当前没有执行设备写入。

---

## S1-020（修复首次接入自阻断 + .5 完整真机生命周期，历史）

> 审核方：Codex（对 S1-019 真机验证的复审反馈）。S1-019 的清理、Type-3 scoped 证据与 QA 记录可信，但未达到「完整接入生命周期」：真机 fresh VPC 在目标 Leaf 尚无本地 AC/tunnel 时 `VSI State: Down`，而 terminal predeploy 硬要求 `vsi_up=True`，导致第一次端口接入永远无法创建 AC——控制流因果悖论，不能把 `sdn.predeploy_unknown` 作为真机测试通过条件。collector 已表达 `vsi_up.required = bool(bindings)`，但 `_l2_ready_status` 忽略 required、无条件遍历固定四项。

**S1-020 修复映射（代码/测试）：**
- `_l2_ready_status` 动态查询目标 Leaf `status ∈ {active, expanding}` 本地绑定：无绑定 → `vsi_up` 不作为门禁（首次 AC bootstrap 放行）；有绑定 → `vsi_up` 仍必需、Down 保守阻断；`unbound`/`planned` 历史行不误判。
- 其余三项（`bgp_peer_established`/`vsi_exists`/`type3_present`）与版本因果、TTL、配置完成时间、命令完整性、CLI 错误、BGP peer、VSI 存在、目标 RD Type-3 门禁**不删不放宽**；preview/execute 共用同一 `_l2_ready_status`（自动同语义），execute 证据不足仍 force refresh、失败零业务副作用。
- 修正 S1-017 `test_l2_condition_false_blocks` 参数化（vsi_up 移出「始终必需」列表，动态语义移至 S1-020）。
- 重写 S1-019 真机测试：不再把 predeploy 阻断断言为 PASS，走 preview → execute → apply → readback GE1/0/10 AC → complete → access withdraw → VPC withdraw，并核对 operation/binding/deployment/attempt/claim 收尾。
- 测试：`test_s1_020_adversarial.py` 9 条（无绑定+vsi_up=Down 应 ready、active/expanding+vsi_up=Down 应 block、绑定+vsi_up=True 应 ready、unbound/planned 不误判、preview/execute 同语义、force refresh 零副作用）。

**修复前失败证据：** 修复前 `test_s1_020_adversarial.py` 5 failed / 4 passed（`test_no_local_binding_vsi_up_down_is_ready`、`test_unbound_or_planned_binding_does_not_require_vsi_up[unbound/planned]`、`test_preview_uses_dynamic_vsi_up_semantics`、`test_execute_uses_dynamic_vsi_up_semantics` 失败），证明 S1-019 基线无条件要求 vsi_up；修复后 9 passed。

**QA 证据：** S1-016~020 + validation/access/service/migration = **74 passed / 1 skipped**（skip=reallife 默认门）；真机一轮 `test_s1_019_reallife.py -m integration --integration` = **1 passed**（49.9s，完整生命周期）。`openspec validate --strict` valid；`git diff --check` clean。

**真机生命周期（.5 / SWC / S6850 T7064P15 / LSTN，一轮）：** VPC create/apply ✅ → display+目标 RD `1:20000` Type-3 ✅ → access preview/execute/apply ✅（GE1/0/10 `service-instance 3200`+`xconnect vsi` 回读确认）→ complete 无主机诚实 `degraded`/`host_observed=False` ✅ → access withdraw ✅（回读确认撤销）→ VPC withdraw ✅ → 兜底清理 sdn_l3vpn+vxlan global ✅ → 最终残留空 ✅、`active_bindings=0`/`unreleased_claims=0`。未验证数据面边界：跨 leaf 转发、网关 ping reachable、主机 ARP/MAC 学习（无下联主机，未伪造成功）。

---

## S1-018（CR38 第十三轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-017 被复审打回的 CR38 问题：`SdnValidationCollector._validate()` 对 `type3_present` 仍只做 `"[3]" in display bgp l2vpn evpn`，只能证明设备上存在任意 VPC 的 Type-3，不能证明目标 VPC 的 Type-3；`_l2_ready_status` 又直接信任该布尔值，导致目标 VPC 缺 Type-3、另一 VPC 有 Type-3 时错误放行 terminal 接入。另有交接材料残留旧口径（validation_result=active / 全命令成功 / 已重命名测试名）。

**CR38 修正映射（代码/测试）：**
- 新增 `SdnValidationCollector._type3_scoped(text, vni)`：按 `Route distinguisher:` 行分块，逐块精确提取 RD 并做等值比较，只在目标 `Route distinguisher: 1:{vpc.vni}` 路由块中发现 `[3]` 才返回 True；其他 RD 有 `[3]`、目标 RD 只有 `[2]`/缺失/无法解析 → False（保守）。不搜整段 `"[3]"`，不做裸子串匹配（`1:2000` 与 `1:20000` 不串匹配）。
- `_validate()` 的 `type3_present.ok` 改用 `_type3_scoped(bgp_evpn_text, vpc.vni)`。
- 清理冲突口径：readiness S1-016、handoff CR36、review-response 历史 CR36、review-manifest CR36、tasks 19.2 统一标注「CR36 当时口径，已被 CR37/CR38 取代」，并修正已重命名测试 `test_predeploy_validation_result_not_a_l2_gate`。
- 保留 S1-017 的 L2/L3 解耦、三条 L2 命令健康检查，以及 S1-016 的 TTL/version/因果/刷新失败零副作用。
- 测试：`test_s1_018_adversarial.py` 8 条（目标 RD 有 [3] true、其他 RD [3]/目标 [2] false、目标 RD 缺失 false、1:2000 vs 1:20000 不串匹配、多 RD 中/末位、真实 `_validate` scoped、terminal 门禁 unknown）。

**修复前失败证据：** S1-017 的 `_validate` 仍 `"ok": "[3]" in bgp_evpn_text`，对「目标 RD 块只有 `[2]`、另一 RD 块有 `[3]`」的输出返回 `ok=True`；`test_validate_type3_is_scoped_to_target_rd`（断言 `ok is False`）修复前必失败；`test_terminal_gate_unknown_when_type3_not_in_target_rd` 修复前会错误放行（`ready`）。

**QA 证据：** `test_s1_018_adversarial.py` 8 passed；S1-016+017+018 = 31 passed；validation/access/service/migration = 32 passed；`openspec validate --strict` valid；`git diff --check` clean。全量未重跑（本轮约定）；上次全量基线 560 passed / 55 skipped / 11 failed（11 为基线段 paramiko 模块缺失）。真机链路未验证；未连接任何设备。

---

## S1-017（CR37 第十二轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-016 被复审打回的 CR37 问题：`_l2_ready_status` 要求整张快照 `validation_result == "active"` 并遍历整张快照所有命令，而 collector 的总体 `active` 又把 `vsi_interface_exists`/`l3_vni_present` 等 L3/网关维度设为 required——用户 gateway delete、L3VNI/Vsi-interface 暂不健康或某条仅 L3 的 display 不支持时，即使 BGP EVPN/VSI/Type-3 全部健康，terminal L2 接入也被错误阻断，违反 design C5 与「网关可独立撤回/补回」。

**CR37 修正映射（代码/测试）：**
- 冻结 L2 必需条件 `TERMINAL_L2_REQUIRED_CHECKS = (bgp_peer_established, vsi_exists, vsi_up, type3_present)`，明确不含 `vsi_interface_exists`/`l3_vni_present`（L3/网关维度）。
- 新增 `_terminal_l2_required_commands(vpc)` = `display bgp peer l2vpn evpn` + `display l2vpn vsi name {vsi_name} verbose` + `display bgp l2vpn evpn`，只按这三条命令检查原始命令完整性。
- 移除两处 L3 耦合：不再要求 `validation_result == "active"`；不再遍历整张快照所有命令。`raw_has_error`（无 CLI 错误）按 L2 命令输出重算，不复用 collector 全量 all_text 的 `raw_has_error`。
- 保留 S1-016 的 TTL/配置完成时间/版本因果/execute 强制刷新与失败零业务副作用；网关/L3 健康继续由 complete `l3_gateway_ready` + ping 表达。
- 测试：`test_s1_017_adversarial.py` 10 条（degraded+L2 健康 ready、L3 命令失败 ready、L2 条件/命令分别阻断、complete 仍表达 degraded）；另将 S1-016 的 `test_predeploy_validation_failed_degraded_blocked` 改为 `test_predeploy_validation_result_not_a_l2_gate`（validation_result 不再是 L2 门禁）。

**修复前失败证据：** S1-016 的 `_l2_ready_status` 在第 228-229 行强制 `validation_result != "active"` → unknown，并在第 216-225 行遍历整张快照所有命令。构造「L2 健康、`validation_result=degraded`（L3 条件失败）」「L2 命令成功、Vsi-interface 命令失败/CLI 错误」两类快照时，S1-016 现状返回 `unknown`（错误阻断纯 L2）；S1-017 新用例断言 `ready`，修复前必失败。

**QA 证据：** `test_s1_017_adversarial.py` 10 passed；S1-016+017 = 23 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。全量未重跑（本轮约定）；上次全量基线 560 passed / 55 skipped / 11 failed（11 为基线段 paramiko 模块缺失）。真机链路未验证；未连接任何设备。

---

## S1-016（CR36 第十一轮复审修正，历史）

> 注：本节为 CR36 当时口径（`validation_result == "active"` + 全命令遍历 + `raw_has_error`），已被 S1-017 CR37（L2/L3 解耦）与 S1-018 CR38（type3 按目标 RD 归属）取代；当前不变式见上方 S1-017/S1-018 节与 design/spec。

> 审核方：Codex。本轮修正 S1-015 被复审打回的 CR36 问题：`_l2_ready_status` 只证明「存在成功 create + 之后无成功 delete + 快照晚于 config 完成」，未检查绝对新鲜度、命令成功/CLI 错误、`validation_details` 目标 scoped 条件、VPC 版本因果；失败/陈旧快照仍可能返回 `ready`；execute 复用陈旧缓存；`SdnPreflight` 四项 deferred「创建前」语义可能被误接到「终端接入已有 VPC」路径。

**CR36 修正映射（代码/测试）：**
- 两套门禁语义冻结（design C5 + spec CR36）：`SdnPreflight` 四项 deferred（`check_vpc_not_exists`/`check_vlan_not_conflict`/`check_bgp_peer_established`/`check_l3vpn_exists`）是「创建 VPC 前」语义，其 deferred `success=True` 是占位非通过，本轮明确保持 create 路径 blocker/后续项；terminal access predeploy proof 要求目标 VSI/VNI **已存在且 L2 可用**，二者不混用。
- `_l2_ready_status` 收紧：① `create.version == vpc.version`（版本因果）；② `collection_completed_at` 距今 ≤ `PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS`（600s）；③ 采集晚于配置完成；④ 原始命令全部 `success=True` 且无 `error` 且输出无 CLI 错误标记；⑤ `validation_result == "active"` 且 `validation_details` 含 `vsi_exists`/`vsi_up`/`type3_present`/`raw_has_error` 且 `ok=True`。缺失/旧格式/解析失败/命令失败/degraded/failed 一律 `unknown`。
- VPC 版本因果持久化：`_create_sdn_deployment` 创建时固化 `deployment.version = vpc.version`；`_l2_ready_status` 校验不一致 → 保守 `unknown`，旧数据 `version=0`/`vpc.version=0` 兼容。
- preview 只展示已有证据结果；execute 在 `_l2_ready_status == unknown` 且存在成功 create 时强制 `sync(force=True)` 重新取证（只读 display），采集失败在消费 plan 前阻断（零 operation/binding/deployment/claim）。
- 测试：`test_predeploy_fresh_scoped_healthy_snapshot_ready` + 陈旧/因果/状态/命令/CLI/缺项/非法 JSON/版本 阻断 + `test_execute_collection_failure_blocks_without_side_effects` + `test_terminal_predeploy_requires_vsi_exists_not_create_semantics`（语义反例）。

**修复前失败证据：** S1-015 旧 `_l2_ready_status` 只做「create 存在 + 无 delete + 快照晚于 config」，对 2 小时前旧快照、`validation_result=failed/degraded`、命令失败/带 CLI 错误、`validation_details` 缺项、`vpc.version` 已推进而 create deployment 仍为旧版本，全部仍返回 `ready`（错误放行）；execute 直接复用该陈旧缓存，取证失败不阻断、不保证零副作用。新增 13 条 CR36 用例把这些缺口逐条编码为「现状会错误放行」的断言。

**QA 证据：** 全量 `pytest tests/` = 560 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_016_adversarial.py` 13 passed；S1-006~015 对抗 14/21/15/7/3/3/4/11/5/10 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证；未连接任何设备。

---

## S1-015（CR35 第十轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-014 被复审打回的 CR35 问题：`reconcile_operation` 只检查 token 存在且属于 operation，随后无条件 `finish_attempt(..., "unknown")`，未证明 token 与 phase 匹配、也未证明 attempt 仍处于可接管的活动态。

**CR35 修正映射（代码/测试）：**
- 唯一 phase→kind 映射 `ACTIVE_PHASE_EXPECTED_KIND`：`applying→execute`、`validating→validate`、`withdrawing→withdraw`；可接管状态仅 `claimed|running`（`STALE_TAKEOVERABLE_ATTEMPT_STATUSES`）。
- `claim_stale_takeover` 改为单条原子 UPDATE，内含 `EXISTS` 子查询同时证明 op phase/token/lease 仍匹配，且 active attempt 的 operation/kind/status 仍可接管——消除「Python 先读后改」的 TOCTOU。
- 新增条件式 `mark_attempt_stale`（仅 claimed|running→unknown，返回 rowcount）；零行即回滚本次接管，绝不覆盖终态、不宣称成功。
- 测试：`test_cr35_applying_with_validate_token_rejected`（错 kind）、`test_cr35_validating_with_succeeded_execute_token_rejected`（execute 历史不变）、`test_cr35_withdrawing_with_terminal_withdraw_token_rejected`、`test_cr35_applying_with_terminal_execute_token_rejected[unknown/failed/failed_known/succeeded]`、`test_cr35_stale_takeover_allows_active_attempt[claimed/running]`、`test_cr35_cas_rejects_when_attempt_terminalized_between_read_and_cas`（真实线程/barrier，读取后 CAS 前转终态 → CAS 失败不覆盖终态）。

**修复前失败证据：** S1-014 代码仅在 takeover 分支做 `active_attempt = 查询(id+operation_id)` 后无条件 `finish_attempt(active_attempt.id, "unknown")`：applying 持 validate token 会被误接管；validating 持 succeeded execute token 会把 execute 降级 unknown；终态 attempt 会被再次降级；且读取与 CAS 分离存在竞态。将本次新守卫落地后，S1-013/014 两条旧用例（attempt 状态被写成 `unknown` 再接管）被正确拒绝，据此将其改为真实活动态 `running`；新增 10 条 CR35 用例全绿。

**QA 证据：** 全量 `pytest tests/` = 547 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_015_adversarial.py` 10 passed；S1-006~014 对抗 14/21/15/7/3/3/4/11/5 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-014（CR32 第九轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-013 被复审打回的 CR32 问题：stale takeover 把「当前失联动作」和「待对账设备副作用」混成同一个 attempt，validating 失联时会误改已成功的 execute attempt。

**CR32 修正映射（代码/测试）：**
- `reconcile_operation` 拆分两种身份：`active_attempt`（严格按 `old_active_attempt_id` 查询且必须 `operation_id == op.id`，只标它及其 started unit 为 unknown，写入 `stale_takeover` 证据；token 无效/跨 operation 保守拒绝）与 `effect_attempt`（execute/withdraw 设备写副作用，确定 deployment/action/目标状态，已确定终态不降级）。
- applying/withdrawing 失联时 active==effect；validating 失联时 active(validate)≠effect(execute)。
- reconcile 收尾只解析 effect_attempt 中真正 uncertain 的 started/unknown units；validate 失联按原 port_bind 回读恢复到 `awaiting_validation`（不把「配置存在」冒充完整业务验证成功）。
- 测试：`test_cr32_stale_validating_takeover_preserves_succeeded_execute`（execute 保持 succeeded、validate 变 unknown、新 reconcile 独立、无写重放）、`test_cr32_stale_applying_takeover_marks_started_unit_unknown`、`test_cr32_stale_withdrawing_takeover_resolves_via_readback`、`test_cr32_stale_takeover_rejects_invalid_token` + `test_cr32_stale_takeover_rejects_other_operation_token`。

**QA 证据：** 全量 `pytest tests/` = 537 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_014_adversarial.py` 5 passed；S1-006/007/008/009/010/011/012/013 对抗 14/21/15/7/3/3/4/11 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-013（CR30-CR31 第八轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-012 被复审打回的 CR30 phase-only CAS 的 ABA/迟到收尾窗口 + CR31 reconcile 无动作准入问题，不新增 change、不复制设计。

**CR30 修正映射（代码/测试）：**
- `sdn_operations` 新增持久列 `active_attempt_id`/`active_started_at`；`claim_action_admission` 在同一短事务绑定 `phase + token + time`；`finish_action` 匹配 `operation_id + phase + active_attempt_id` 且成功原子清空 token。
- apply 用原 execute attempt 身份，validate/withdraw/reconcile 用各自新 attempt 身份；准入输家回滚临时 attempt（不留垃圾）。
- 测试：`test_cr30_aba_{validate,withdraw,apply}_generation_token`——旧代际迟到收尾 CAS 零行，不覆盖新代际、不动新 claims。

**CR31 修正映射（代码/测试）：**
- 普通 reconcile 只能从 `unknown` 原子准入 `reconciling`（绑定自身 attempt 令牌），与 applying/validating/withdrawing/reconciling 互斥；输家在 collector 前返回 in-progress。
- 对 admission 后崩溃的 active phase，`claim_stale_takeover` 依据 `active_started_at` + `STALE_ACTION_LEASE_SECONDS=300`（保守、大于单次网络 I/O 上限）判定失联，`phase + old token + stale` CAS 抢占；未过 lease/`active_started_at IS NULL` 拒绝；takeover 后 active_attempt（token 指向的失联动作）及其 started unit 记 unknown 留审计，不重放设备写。
- reconcile 全部终态写入/deployment/binding/claim 释放在仍持有 `reconciling + token` 时发生；收尾 CAS 零行不改业务实体、不释放 claims；collector 失败条件收尾到 unknown；`withdrawn` 不可被 reconcile 改写。
- 测试：live apply/validate/withdraw 下 reconcile 采集前被拒（3）、unknown 单赢家、stale lease 拒/接（2）、collector 失败/迟到收尾（2）。

**QA 证据：** 全量 `pytest tests/` = 532 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_013_adversarial.py` 11 passed；S1-006/007/008/009/010/011/012 对抗 14/21/15/7/3/3/4 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-012（CR29 第七轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-011 被复审打回的 CR29 apply 游离于 operation 状态机之外的设备写并发 P1 窗口，不新增 change、不复制设计。

**CR29 修正映射（代码/测试）：**
- apply 准入：`apply_access` 进入任何设备 I/O 前原子 CAS `awaiting_wiring → applying`（`claim_action_admission`），与 `validating`/`withdrawing` 互斥；输家返回 `sdn.operation_in_progress`，不改变 execute attempt/deployment/operation/binding/claims。
- 收尾条件 CAS：`finish_action` 把 `applying → awaiting_validation|failed|unknown`；迟到/零行不覆盖 `withdrawn` 或其他 phase、不释放/误标另一动作 claims。
- deployment CAS 失败即停：`executor.execute` 抛 `SDN_DEPLOYMENT_NOT_PENDING`（deployment 已被他人认领 running）时停止上层收尾、回滚返回，不把他人执行中的 deployment/attempt 推导 unknown、不标 ambiguous。
- auto_apply 内联 `claimed` 阶段兼容：其值不在 complete/withdraw 合法来源集合，天然阻挡 complete/withdraw，未引入第二套设备写窗口。
- 测试：`test_cr29_apply_wins_withdraw_blocked`、`test_cr29_withdraw_wins_apply_blocked`、`test_cr29_concurrent_apply_single_winner`、`test_cr29_late_apply_does_not_overwrite_withdrawn`。均为真实线程 + 阻塞 barrier。

**QA 证据：** 全量 `pytest tests/` = 521 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_012_adversarial.py` 4 passed；S1-006/007/008/009/010/011 对抗 14/21/15/7/3/3 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-011（CR28 第六轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-010 被复审打回的 CR28 validate/withdraw 跨动作并发 P1 窗口，不新增 change、不复制设计。

**CR28 修正映射（代码/测试）：**
- 跨动作原子准入：`claim_action_admission`（`sdn_operation_service.py`）泛化为 `from_statuses→to_status` 单行 CAS；op.status 新增 `withdrawing` 中间态；withdraw 进入任何设备 I/O 前 CAS 取得 `withdrawing`，合法来源 `WITHDRAW_FROM_STATUSES`（planned/applied/awaiting_wiring/awaiting_validation/succeeded/degraded/failed/unknown），与 `validating` 互斥；validate 在 `validating`/`withdrawing` 下直接返回 `sdn.operation_in_progress`。
- 条件收尾 CAS：`finish_action`（`UPDATE ... WHERE status=from_status`）；validate/withdraw 最终 op.status 写入改走条件 CAS，零行更新不覆盖现状、不误释放 claims，返回 `late completion` 诊断；`withdrawn` 保持不可逆终态。
- 测试：`test_cr28_validate_wins_withdraw_blocked`（阻塞 collector，withdraw 被拒且不建 attempt/deployment、不调 executor）、`test_cr28_withdraw_wins_complete_blocked`（阻塞 executor，complete 被拒且不建 validate attempt、不调 collector/ping，withdraw 后保持 withdrawn）、`test_cr28_late_complete_does_not_overwrite_withdrawn`（迟到收尾条件 CAS 零行不覆盖 withdrawn、不误释放 claims）。均为真实线程 + 阻塞 barrier。

**QA 证据：** 全量 `pytest tests/` = 517 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_011_adversarial.py` 3 passed；S1-006/007/008/009/010 对抗 14/21/15/7/3 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-010（CR27 第五轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-009 被复审打回的 CR27 complete/validate 并发准入 P1 窗口，不新增 change、不复制设计。

**CR27 修正映射（代码/测试）：**
- 原子准入：`claim_validation_admission`（`sdn_operation_service.py`）单行 UPDATE CAS 把 `awaiting_validation|unknown → validating`；op.status 新增 `validating` 中间态（String(30) 内，无需迁移）。
- 赢者：`complete_access` 在同事务内建 validate attempt + 获取/复用 claims 后 commit，才进入 collector/ping；输家（读到 `validating` 或 CAS 零行）返回 `sdn.operation_in_progress`（新增 error key），不建第二 attempt、不执行 I/O。
- 崩溃边界：准入后崩溃留 `validating` + `claimed` attempt 可对账痕迹，不回退 `awaiting_validation`、不重放。
- 测试：`test_cr27_concurrent_complete_single_winner`（真实线程 + barrier，阻塞第一个 collector，断言仅一次 collector 调用 + 一个活跃 attempt + 另一请求 in-progress）、`test_cr27_concurrent_unknown_recovery_single_winner`（unknown 恢复并发仅一个赢家，旧历史保留）、`test_cr27_validating_stuck_not_replayed`（崩溃痕迹守卫，不重复进入 collector/ping）。

**QA 证据：** 全量 `pytest tests/` = 514 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_010_adversarial.py` 3 passed；S1-006/007/008/009 对抗 14/21/15/7 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-009（CR24-CR26 第四轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-008 被复审打回的 CR24-CR26 真实链路缺口，不新增 change、不复制设计。

**CR24-CR26 修正映射（代码/测试）：**
- CR24 真实 reconcile 采到待对账目标接口：`SdnValidationCollector.sync` 增加 `scope_bindings` 参数，`_commands` 对 scope binding 无论 status 都追加接口回读；`reconcile_operation` 传 binding scope；普通周期采集不传 scope，边界不变；测 `test_cr24_*`（走真实 `_commands`/`_snapshot_data`，只 mock SSH/凭据）。
- CR25 unknown validation 恢复路径：`complete_access` 幂等仅限 latest validate attempt 为 `succeeded`/`failed_known`；`unknown` + port_bind 执行已成功允许显式重试新建 attempt，旧 attempt 历史保留；不自动重放设备写；测 `test_cr25_unknown_validation_recovers_on_retry`。
- CR26 CLI 错误 output/结构化字段共同识别：`_scoped_port_evidence` 复用 `SdnValidationCollector._has_display_error(output)`，success=true/error=null + 错误文本判 insufficient；测 `test_cr26_*`（3 例参数化）。

**QA 证据：** 全量 `pytest tests/` = 511 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_009_adversarial.py` 7 passed；S1-006/007/008 对抗 14/21/15 passed；access/service/migration 28 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-008（CR19-CR23 第三轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-007 被复审打回的 CR19-CR23 阻断项，不新增 change、不复制设计。

**CR19-CR23 修正映射（代码/测试）：**
- CR19 reconcile 真正解析 unknown unit：`sdn_operation_service.mark_unit_reconciled`（started|unknown→succeeded|failed_known，rowcount 逐项校验）；`reconcile_operation` 未全解析→reconciled=false、不释放 claims、上层 unknown/ambiguous，原 attempt 终态由 `derive_attempt_status_from_units` 重推；测 `test_cr19_*`。
- CR20 port_bind 需目标端口 scoped 正向证据：`sdn_access._scoped_port_evidence`（接口回读命令存在/success/无 CLI error + `service-instance`/`xconnect vsi` 结构化匹配）；仅 VPC active 不算；测 `test_cr20_*`。
- CR21 port_unbind 不把采集失败当缺失：命令缺失/success=false/CLI error→insufficient；`_token_present` 语法级匹配替代裸 `str(number) in output`；测 `test_cr21_*`。
- CR22 complete/validate claim 与终态守卫：`complete_access` 幂等/终态守卫（非 awaiting_validation 不改状态不建 attempt）+ owner-aware 获取/复用 tenant/vpc/vpc-device claims + 只选原 port_bind deployment；测 `test_cr22_*`。
- CR23 主机 IP/端口同一条本地记录：`_build_host_observations` 逐行关联 IP+接口（或 ARP MAC→MAC 表端口），命令失败不产生 observation=true，远端 Type-2 仅 remote；测 `test_cr23_*`。

**QA 证据：** 全量 `pytest tests/` = 504 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_008_adversarial.py` 15 passed；`test_s1_006/007_adversarial.py` 14/21 passed；`openspec validate --strict` valid；`git diff --check` clean。真机链路未验证。

---

## S1-007（CR11-CR18 第二轮复审修正，历史）

> 审核方：Codex。本轮修正 S1-006 被复审打回的 CR11-CR18 阻断项，不新增 change、不复制设计。

**CR11-CR18 修正映射（代码/测试）：**
- CR11 apply owner-aware claim 复用：`sdn_operation_service.acquire_or_reuse_claims` + `sdn_access.apply_access`；测 `test_cr11_apply_reuses_own_claims_and_releases_on_success`。
- CR12 unknown/withdraw claim 生命周期：execute/withdraw 确定性 success/failed 释放完整 scoped claims，unknown 保留并 `mark_operation_claims_ambiguous`；测 `test_cr12_*`。
- CR13 reconcile 按动作/期望状态一致收尾：`sdn_access._reconcile_outcome`（port_bind→active；port_unbind→scoped 配置缺失）+ withdraw attempt 关联 `deployment_id`；测 `test_cr13_*`。
- CR14 逐单元 CAS 阻断 I/O + legacy 多单元：`AttemptUnitHooks` 返回 bool + executor `before_unit` 失败阻断 I/O + `after_unit_*` 零行降级 unknown + `ensure_legacy_apply_operation` 解析真实 unit 列表；测 `test_cr14_*`。
- CR15 迁移 012 列类型/唯一约束/复合索引：`claimed_at` DateTime + `uq_attempt_unit` UNIQUE + `ix_identity_kind_id_created` 复合索引 + `sdn_attempts.evidence_json`；测 `test_cr15_constraints_column_type_and_indexes`。
- CR16 主机观测不混入远端 Type-2：`sdn_access._build_host_observations` + `_ip_exact_match`；测 `test_cr16_*`。
- CR17 四维验证不互相冒充 + ping 诚实持久化：`complete_access` 四维显式 status/reason + `_run_gateway_ping` 结构化 + 持久化到 `sdn_attempts.evidence_json`；测 `test_cr17_*`。
- CR18 文档不提前宣称完成：handoff/readiness/tasks 同步现状并标注 `READY_FOR_CODE_REVIEW`；SHALL 覆盖缺口实现——依赖重放（`AttemptUnitHooks.before_unit` 前置单元校验）、撤回矩阵（幂等/rebind 阻断/读不 bump version）、终端视图明细（`access-overview.observations` source/scope/timestamp + 远端 Type-2 过滤）；测 `test_cr18_*`。

**QA 证据：** 全量 `pytest tests/` = 489 passed / 55 skipped / 11 failed（11 失败为基线段 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失，非本次引入）；`test_s1_007_adversarial.py` 21 passed；`test_s1_006_adversarial.py` 14 passed；`test_sdn_migration.py` 5 passed。真机链路未验证。

---

## S1-005（历史，后端实现与隔离 QA）

> 审核方：Codex。本轮按 S1-004 定稿契约落地后端实现 + 隔离 QA，未追加新设计层。S1-004 及更早章节降为历史。

**实现与证据（文件/命令）：**
- ORM 6 表 + 存量加列：`backend/app/models.py`。
- 迁移 012（sqlite_master/PRAGMA 幂等守卫 + 部分唯一索引）：`backend/migrations/versions/012_add_sdn_operations.py`。
- 共享仲裁服务（锁序/claim/CAS/幂等/指纹/计划/attempt-unit/身份快照）：`backend/app/services/sdn_operation_service.py`。
- 接入路由（preview/access/complete/withdraw/reconcile/detail/overview）：`backend/app/routers/sdn_access.py`。
- 旧入口守卫 + 父删快照：`backend/app/routers/sdn.py`。
- executor CAS（check-then-act → 原子认领）：`backend/app/services/sdn_deployment_executor.py`。
- 缓存绕过权威元数据重拉：`backend/app/internal_api.py`。
- QA：独立 `qa/docker-compose.qa.yml`（合成 env + tmpfs 隔离 DB + 禁 .pyc/cache），`pytest` **76 passed**（含真实 alembic 迁移 + 并发/幂等/崩溃窗口/撤回/历史用例），全量 `tests/` 449 passed/55 skipped/11 failed（11 失败均为既有 `test_ops_toolkit_paramiko.py` 的 QA 镜像环境问题，与本 change 无关）。

**未覆盖缺口（诚实清单，见 `handoff.md` §2/§3）：** TTL 自动标 ambiguous 无后台扫描器；双新入口同端口并发全矩阵、重放依赖编排、crash-window 全矩阵、deferred preflight 反例、四维分离、撤回全矩阵、终端视图明细未独立成测；真机链路未验证。

---

## S1-004（历史记录，已被 S1-005 取代）

> 审核方：Codex。本轮修正 S1-003 的 7 处矛盾与 1 个并发洞，未追加新设计层，只把文档收敛为单一契约。S1-003/S1-002 章节降为历史，不再作为活跃指导。

**逐项处置（文件/章节）：**
1. 歧义 claim 继续互斥：部分唯一索引改为 `(resource_key) WHERE released_at IS NULL`（held 与 ambiguous 的 released_at 均 NULL，都独占），reconcile 仅显式 resolution 后释放（`design.md` §2、§1 表；`specs` 「资源声明互斥与层级冲突」）。
2. 层级冲突规则：子 mutation 升序获取全部祖先 claim（tenant→vpc→vpc-device→device-port），父删除取祖先 key 冲突（`design.md` §2、§4 矩阵）；串行化可用性权衡文档化（§9）。
3. deployment 词汇统一：`pending→running→success|failed|unknown`（新增 `unknown`，additive 兼容既有 API）；operation/attempt/unit 四层状态分离（`design.md` §1、§3 C3；`specs`/`tasks`/`contracts`/`qa-plan` 同步）。
4. 预览语义：POST 持久化一条 `sdn_plans`（无设备写/无 binding/deployment/operation）；执行只收 `plan_id`，不收客户端 preview_fingerprint；请求 fingerprint（幂等）≠ 计划 semantic_hash（stale）（`design.md` C6、§6；`contracts` preview_invalidated）。
5. 幂等隐私顺序：鉴权→scope 校验→INSERT→IntegrityError 回查；不可访问 scope 404 不泄漏；同 scope 同指纹 200/异指纹 409（`design.md` C2；`specs` 「幂等键冲突、隐私与鉴权顺序」）。
6. 历史证据：`sdn_operations` 无公开删除路径、永久保留；attempts/units 仅从 operation 级联；父硬删前快照父+后代并复制 validation/config 证据到 attempt/unit 再级联；ctrl 设备删除靠 scope 快照（`design.md` C9；`specs` 「操作历史身份快照」）。
7. 陈旧子句清除：rg 审计并改写「不写库」预览、「binding.created_at」新鲜度、planned/claimed 词汇、preview_fingerprint、证据表无父外键与 attempts 级联矛盾（`readiness.md`、`specs`、`contracts`、`qa-plan`、`tasks`）。

**对抗用例（已入 specs/tasks/contracts）：** 歧义 claim 阻新 owner、父删与子操作冲突、并发 INSERT IntegrityError、执行只认 plan_id、不可访问 scope 不泄漏、父硬删后历史/证据可追溯。

---

## S1-003（历史记录，已被 S1-004 取代）

> 审核方：Codex。本轮把 S1-002 的叠加式决策 D1-D20 重写为单一自洽设计（见 `design.md` 的 C1-C10 + §1 实体约束表 + §4 守卫矩阵 + §5 伪代码），删除被取代的旧机制（含"零迁移成本"说法）。S1-002 章节降级为历史记录，不再作为活跃决策。

**逐项阻断项处置（文件/章节链接）：**
1. 单一自洽决策：`design.md` 已全文重写为 C1-C10，旧 D1-D20 不再存在；`readiness.md`/`specs`/`tasks`/`contracts`/`handoff` 同步；"零迁移成本"已删除（`design.md` §1 澄清）。
2. D12 不安全：改为逐单元持久状态 `not_started/started/succeeded/failed_known/unknown`（`design.md` C3、§1 `sdn_attempt_units`、`specs` 「逐单元执行状态与重放规则」）；`failed_known`≠无副作用；仅 started 无终态=unknown；读不触发 I/O，reconcile 显式（`design.md` §5）。
3. D8/D10/D20 落地：`design.md` §1 实体约束表 + §2 锁序/原子获取 + §4 守卫矩阵（全覆盖旧新入口）+ §5 事务与崩溃伪代码；claim 部分唯一索引互斥，TTL 不自动转移，失主显式 reconcile。
4. D18 保留设计：非级联证据表 + `sdn_identity_snapshots`（`design.md` C9、§1）；明确 ORM/FK 行为与删除测试（`tasks.md` 7.3）。
5. QA：`qa/docker-compose.qa.yml` 独立定义，`docker compose config` 解析通过（build context=worktree 根、无 env_file/docker.sock/固定名/依赖/生产 DB、tmpfs 测试 DB、项目名 next-s1-qa）；迁移测试真实 alembic（`tasks.md` 1.4）。

**采纳的 Codex 决策默认值：** 预览 10 分钟过期（可配）；前端生成 UUID 幂等键 + 服务端范围/指纹；display 600s 新鲜度标注；执行/验证/对账可 force 采集、普通读不采集；执行前绕过缓存重拉权威成员/OOB；读取不阻撤回；终端视图=期望+观测+绑定；无全局主机资产表。详见 `design.md` §6/§8/§10。

**对抗用例（已入 specs/tasks/contracts）：** 同/异 deployment 并发、跨旧新入口、父删时子 apply 已认领、崩溃于 started 前后与设备响应前后、超时无结果、失主 claim、stale plan、晚写入旧快照、删除父对象后历史可追溯。

---

## S1-002（历史记录，已被 S1-003、S1-004 取代）

> 审核方：Codex（基线 `6cd19fb`，首次请求 `0235534e-f200-45a7-bb76-d06e5ee58d0f`）。
> 本节为历史记录；活跃决策见上方 S1-003 与 `design.md`（C1-C10）。

## R1 并发、幂等与崩溃边界

**修改入口**：design.md 新增 D8（原子认领）、D9（幂等作用域/指纹）、D10（新旧入口共享守卫矩阵）、D11（设备 I/O 前后事实写入 + 崩溃对账）、D12（重试边界）；specs/sdn/spec.md 新增「执行原子认领」「幂等冲突」「共享资源仲裁」需求；tasks.md 第 2/3 组补并发与崩溃任务。

**方案要点**
- 原子认领：apply 不再"读 status==pending 后直接 I/O"，改为 `UPDATE sdn_deployments SET status='running', claimed_at=now(), attempt_id=:aid WHERE id=:id AND status='pending'`，以 rowcount 判定唯一执行者；失败者返回 409。崩溃后 `running + claimed_at` 超租约判定为 stale，先读设备回读对账（display），再落 success/failed/unknown，不盲目重试。
- 幂等：`idempotency_key` UNIQUE + `request_fingerprint`（服务端归一化 SHA-256）。插入撞唯一约束时回查：指纹一致→返回同一 operation（duplicate=true）；不一致→409 `SDN_IDEMPOTENCY_CONFLICT`；跨租户/跨 VPC/跨设备一律按不存在处理，不泄漏他人 operation。
- 幂等作用域：key 全局唯一，但校验时强制匹配 `tenant_id + operation_type + vpc_id + device_id`；指纹排除客户端时间戳等易变字段。
- 共享资源仲裁：端口级 `{device_id, if_index}` 与 VPC 级 `{vpc_id, device_id}` 用同一守卫，既有 SELECT-then-INSERT 改为依赖 DB 约束 + 原子状态转移（见 D10 覆盖表）。
- 崩溃窗口：设备 I/O 前写"attempt started"，I/O 后写"attempt finished + 每 unit 结果"；设备已改而 DB 未落库时，下次读取检测到"running 无 finished"→返回 unknown/待对账，先回读设备真实状态。
- 重试：只允许对"有证明未执行"的 unit 重放；部分已落地或结果不明时，不得凭终态 failed 从头重放。

**代码证据**
- `sdn_deployment_executor.py:130-144` 读取 deployment 并校验 `status != "pending"`，`:209-244` 直接进入设备 I/O，中间无 `running` 认领写入（check-then-act 竞态真实存在）。
- `sdn.py:861-874`（create_port_binding）与 `:1014-1027`（start_vpc_expansion）均为 SELECT 冲突 + INSERT，无 DB 唯一约束兜底。
- `database.py:7-10` SQLite `check_same_thread=False` + `:12-20` `SessionLocal` 无显式隔离/原子认领机制。

**剩余不确定性**：SQLite 是否加 `BEGIN IMMEDIATE`/`busy_timeout` 需在 apply 阶段按并发测试定；租约超时时长（设备 SSH 最长 ~30s+）需 Codex 确认容忍值。

## R2 前置部署存在性证明

**修改入口**：design.md D13；specs 新增「目标 VPC 前置部署证明与失效规则」需求；tasks 第 2 组补反例测试。

**方案要点**
- 判定改为三元证据链：当前有效对象配置版本 + 最近相关变更 + 足够新的观测。`create` 成功但后续有 `delete`/`gateway_delete`/failed `redeploy` 成功覆盖时，前置部署失效。
- 失效规则：最近一次相关成功变更是完整 `create`/`redeploy` 且其后无 `delete` → 有效；`gateway_delete` → L2 在但网关未就绪，接入但需网关验证时判定 blocker；failed/partial → unknown/blocker；快照 `collected_at` 早于最近变更 → stale，强制新采集。
- DB 可证明 vs 设备证据：DB 只证明"存在过下发计划/记录"，不证明"VSI/L3VNI/Vsi-interface 当前健康"。四项 deferred preflight（`vpc_not_exists/vlan_not_conflict/bgp_peer_established/l3vpn_exists`）不得视为通过，接入前须给出设备侧证据或显式 unknown/blocker。
- 区分 L2 接入资源就绪（VSI/EVPN，够 port_bind）与网关验证前置（Vsi-interface + L3VNI + VPN binding，够网关 ping）；RD/RT、VRF、L3VNI、VSI 接口联动语义保持一致。
- 反例测试：create 成功后 delete 成功；旧快照晚写入；网关单独撤回。

**代码证据**：`sdn_preflight.py:101-131` 四项设备侧检查全部 `return success=True, reason="deferred..."`（占位）；`sdn.py:279-305` `_ping_from_vpc_gateway` 直接假设网关可用，无前置部署证明。

**剩余不确定性**：观测新鲜度阈值（复用 600s 还是接入前强制 fresh）需 Codex 确认。

## R3 预览确认必须能被后端验证

**修改入口**：design.md D14、D20；specs 新增「服务端预览计划与指纹」「执行前服务端重校验」需求。

**方案要点**
- 预览持久化为服务端 `sdn_operations`（`operation_type=terminal_access_preview`，status=draft/previewed），存服务端计算的归一化语义指纹与目标范围、版本、有效期。
- 计划标识 `plan_id` 由服务端生成，客户端不可替换；执行携带 `plan_id`，后端据当前服务端状态重算指纹并比对，不一致→`plan_stale` + 失效原因，不用客户端 `updated_at`。
- 执行前重查：成员准入、受保护接口策略、资源占用、VPC 与依赖版本、前置部署证明。
- 事务顺序（D20）：原子认领 + 重校验在短 DB 事务内完成（不含设备 I/O）；重校验失败即释放认领；设备 I/O 在认领持久化后、独立于长写事务执行。

**代码证据**：上一版设计仅比对三个 `updated_at`（同秒漏检、未变 binding 不能反映竞争绑定/策略/父资源变化）；现有 `sdn.py:861-874/1014-1027` 冲突检查不含父资源版本与策略版本。

**剩余不确定性**：指纹归一化字段集（是否含 `auto_apply`、`expected_host_ip`）待 Codex 定；有效期默认值待定。

## R4 证据归属与真实过程

**修改入口**：design.md D15；specs 新增「验证 attempt 标识与因果窗口」「缓存不回填为新事实」需求；contract-examples.json 补 `attempt_id`/`scope`/`limitations`。

**方案要点**
- 每次执行/验证有稳定 `attempt_id` + `started_at`/`completed_at` + 对象范围 + 配置版本 + 结果关联；验证证据记录 `collection_started_at`/`collection_completed_at` 或等价因果令牌，并断言 `collection_started_at >= deployment.completed_at`。
- 缓存只作带时效的历史信息，不回填成新的已验证事实；每次验证保留独立结果，不覆写原 operation 证据归属。
- 四维分离：execution / config_readback / business_validation / evidence；采集失败/不支持/证据不足 ≠ 主机失败。
- 持久化真实步骤与尝试，含未执行/已完成/未知部分，不由终态编造过程。
- N1-05 样本带 `scope`/`limitations`：本地网关 ping 通过不代表跨 Leaf 端到端成功。

**代码证据**：`sdn_validation_collector.py:106-110` `_is_fresh` 仅比较 `created_at` 与 now；`:94-104` `to_response` 只带 `created_at`/`cached`，无 attempt 窗口；`binding.created_at` 为插入时刻（`models.py:232`），早于实际下发。

**剩余不确定性**：因果令牌用 deployment id 还是显式时间窗，待 apply 阶段与 Codex 对齐后固化。

## CR46-CR49：S2-001 只读状态差异投影

已新增单 VPC 的 desired/observed/diff 只读投影。Codex 两轮复审修正：目标态必须由 deployment 生命周期与当前版本证明；多 service-instance 按成员关系比较；配置 token 精确匹配；L2 VSI 与可独立撤回/补回的 L3 网关分别折叠生命周期；CLI 错误正文和损坏快照保持 unknown。读取不触发采集、设备 I/O 或写库。隔离 QA 合并运行 127 passed，本轮未触真机。

## R5 撤回与资源所有权

**修改入口**：design.md D16；specs 新增「撤回所有权与版本检查」需求；tasks 第 5 组补旧入口交错测试。

**方案要点**
- `sdn_port_bindings` 增加不可覆盖的 `created_by_operation_id`（创建所有者）与可变的 `version`/`last_changed_by_operation_id`；撤回检查"所有者==本操作 且 version 未变 且 无后续新引用"。
- 仅读取/验证（非变更）不 bump version，不阻止合法撤回；实际新增引用、再利用或变更才进入风险判断。
- 旧入口映射：delete/unbind/rebind/redeploy/withdraw/gateway 各自如何改 version/引用，列覆盖表。
- 撤回前原子认领 + 版本检查；解绑成功但回读失败→unknown 对账；重复撤回幂等；部分解绑结果不明→不自动补回、不扩大为删除 VPC。
- 保留共享 VPC/租户/网关/其他端口。

**代码证据**：`models.py:209-241` `SdnPortBinding` 无 owner/version 字段；`sdn.py:970-994` `undeploy_port_binding` 无"本次新建且无新引用"守卫；`sdn.py:923-933` `delete_port_binding` 仅拦截 `active`。

**剩余不确定性**："无新引用"判定是否覆盖任何后续 operation 引用，待 Codex 确认边界。

## R6 终端展示与历史保留

**修改入口**：design.md D17、D18；specs 新增「终端读取视图」「操作历史身份快照」需求。

**方案要点**
- 一期不新增全局主机资产表。终端读取视图 = expected_host_ip（用户期望，非观察）+ 当前带 scope/source/timestamp 的 ARP/MAC/EVPN 观测 + 绑定，逐条标注 intent/observation/inferred，不把期望地址冒充已观察主机，不把远端 Type-2 无依据挂成本地物理端口。
- 历史保留：operation/deployment/snapshot 记录保存父对象身份快照（denormalized 关键身份字段 + 删除态），VPC/绑定/设备被 CASCADE 删除后仍能追溯过程；可选软删除。

**代码证据**：`models.py:138-235` VPC/PortBinding 用 `ondelete="CASCADE"` 外键，父删即级联丢子记录；`sdn.py:400-408` delete_tenant 直接 `db.delete(tenant)`。

**剩余不确定性**：身份快照是否拆独立表，apply 阶段定。

## R7 迁移与现有架构

**修改入口**：design.md D19 + Migration Plan；specs 新增「迁移列级幂等」需求；tasks 第 1 组补迁移测试。

**方案要点**
- 012 迁移采用**列级幂等守卫**（同 008/010/011 的 `_has_column`），不做"建表存在就 return"；分别：无表则建、缺列则加列、缺索引则补索引，避免跳过后续列修复。
- nullable ≠ 零成本：`operation_id` 全可空仅为兼容历史；downgrade 采用**保守策略**（删 012 新增 6 表 + 2 部分唯一索引，**保留**存量表新增列，SQLite 无法安全 drop 列），迁移说明已明示。
- 所有权与启动路径：`on_startup` 对每个容器跑 `alembic upgrade head`（main.py:99-107）；SDN 表归 config 容器（007 注释）；Device 在 config/data 无本地表，经 `internal_api.get_device`（5s TTL 缓存）取 ctrl。
- 测试：空 DB upgrade head、旧 DB（007-011）upgrade 只补缺、downgrade 反向，均需真实跑 alembic（现有 conftest 用 `Base.metadata.create_all` 绕过迁移，须补迁移测试）。
- 历史只读端点、所有权、数据保留与 data 容器快照归属：历史只读端点放 config；设备身份按需跨容器读；不假定每个容器有全表或实时同库事务。

**代码证据**：`007_add_sdn_tables.py:22-23` 用 `if "sdn_tenants" in get_table_names(): return`（表格存在即返回，会跳过缺列）；`008/010/011` 用 `_has_column` 列级守卫（正确范式）；`main.py:99-107` 每容器启动跑迁移；`internal_api.py:30-32/62-69` GET 5s TTL 缓存；`device_access.py:85-97` split 模式走 internal API。

**剩余不确定性**：012 的 down_revision 需在 apply 时按当前 head（011）确认。

## R8 QA 与交付严谨性

**修改入口**：qa-plan.md 重写路径/隔离/迁移测试；design.md Non-Goals 拆分；handoff.md 更新状态；本文为代码行号来源。

**方案要点**
- pytest 路径纠正：QA 容器 `WORKDIR /app`、`COPY backend/ .`，因此容器内命令为 `pytest tests/<file> -q`，不是 `backend/tests/...`。
- 隔离：worktree 无 `.env`，而 qa-backend compose `env_file: .env`（docker-compose.dev.yml:136）是硬依赖；契约/单元测试用 `-e DB_PATH=/tmp/test_h3c.db -e ENCRYPTION_KEY=...` 显式注入非敏感测试变量，或由 Codex 提供不含生产凭据的最小 QA env，绝不复制/打印生产凭据。
- 固定 `container_name`（docker-compose.dev.yml:135）与 `docker.sock` 挂载（:144）：`run --rm` + 独立 `-p next-s1-qa` 项目名避免名冲突；契约/单元测试不需要 docker.sock（仅故障注入 e2e 用），不挂依赖容器、不起 ctrl/config/data/frontend。
- 迁移测试须真实跑 alembic（现有 conftest `Base.metadata.create_all` 绕过了迁移，见 conftest.py:52）。
- Non-Goals 区分：本次仅方案阶段不写业务代码，是"本包范围"非"实施 change 终态禁令"；apply 工作包会写业务实现。
- 复核：`openspec validate`、JSON 合法、状态样本自洽；区分"阅读前 worktree clean @6cd19fb"与"产出后 `?? openspec/changes/next-s1-backend/` 未提交"。

**代码证据**：`backend/Dockerfile.qa:3` `WORKDIR /app`、`:17` `COPY backend/ .`；`docker-compose.dev.yml:130-146` qa-backend（container_name :135、env_file :136、docker.sock :144）；`conftest.py:52` `Base.metadata.create_all`、`:8` `DB_PATH=/tmp/test_h3c.db`。

**剩余不确定性**：QA 容器是否允许挂 docker.sock（真机 e2e 才需要）需 Codex 后续放行精确测试范围。
