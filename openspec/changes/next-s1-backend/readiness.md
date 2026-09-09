# S1-001 后端基线核对（readiness）

> 状态：**CODE_REVIEW_PASSED**（S1-005 实现 → S1-006 闭环 CR1-CR10 → S1-007 闭环 CR11-CR18 → S1-008 闭环 CR19-CR23 → S1-009 闭环 CR24-CR26 → S1-010 闭环 CR27 → S1-011 闭环 CR28 → S1-012 闭环 CR29 → S1-013 闭环 CR30-CR31 → S1-014 闭环 CR32 → S1-015 闭环 CR35 → S1-016 闭环 CR36 → S1-017 闭环 CR37 → S1-018 闭环 CR38）。Codex 于 2026-09-10 完成代码复审与 31 条关键门禁测试独立复跑；本状态仅允许形成 Git 检查点并进入真机验证准备，真机链路尚未验收。

## S1-005/S1-006/S1-007/S1-008/S1-009/S1-010/S1-011/S1-012/S1-013/S1-014/S1-015/S1-016/S1-017 处置（S1-018 修正后）

- S1-005 已落地 6 张 S1 表 + 迁移 012 + 共享仲裁服务 + 接入路由 + 旧入口 claim 守卫 + executor CAS。复审发现 CR1-CR10 阻断项（见 `review-response.md`）。
- S1-006 已修正 CR1-CR10（短事务先认领后 I/O、逐单元证据、绑定先锁后写、撤回 owner CAS、reconcile、计划哈希/ipaddress/接口身份、split 分派、证据因果/四维、旧入口守卫矩阵、迁移/QA）。
- S1-007 已修正 CR11-CR18（owner-aware claim 复用、unknown/withdraw claim 生命周期、reconcile 按动作/期望状态一致收尾、逐单元 CAS 阻断 I/O + legacy 多单元、迁移 012 列类型/唯一约束/复合索引、主机观测不混入远端 Type-2、四维验证不互相冒充 + ping 诚实持久化、文档不提前宣称完成）。
- S1-008 已修正 CR19-CR23：reconcile 真正解析 unknown unit、port_bind 需目标端口 scoped 正向证据、port_unbind 不把采集失败当配置缺失、complete/validate claim 与终态守卫、主机 IP/端口同一条本地记录。
- S1-009 本轮修正 CR24-CR26：真实 reconcile 把待对账 binding 作为显式采集 scope（`collector.sync(scope_bindings=...)`）从而采到 planned/unbound 目标接口；complete 幂等仅限确定完成的 validate attempt，unknown validation 在执行已成功时允许显式重试新建 attempt（不自动重放写）；CLI 错误从 output 文本共同识别。
- S1-010 本轮修正 CR27：complete/validate 并发准入收口——`claim_action_admission` 单行 CAS（`awaiting_validation|unknown → validating`），同一 operation 至多一个 validate attempt 进入 collector/ping；输家返回 `sdn.operation_in_progress`；准入后崩溃留 `validating` + `claimed` attempt 痕迹不回退、不重放。
- S1-011 本轮修正 CR28：validate/withdraw 跨动作原子仲裁——withdraw 设备 I/O 前 CAS 取得 `withdrawing`（与 `validating` 互斥）；validate/withdraw 最终状态写入带 phase 条件 CAS（`finish_action`），迟到收尾不覆盖现状、不误释放 claims；`withdrawn` 不可逆终态；允许/拒绝状态清单见 design/spec。
- S1-012 本轮修正 CR29：apply 纳入同一动作仲裁——显式 apply 设备 I/O 前原子 CAS `awaiting_wiring → applying`（与 validating/withdrawing 互斥）；收尾条件 CAS `applying → awaiting_validation|failed|unknown`；deployment CAS 失败即停（不推导 unknown、不误标 claims）；并发 apply 单赢家；auto_apply 内联 `claimed` 阶段保持兼容（阻挡 complete/withdraw）。
- S1-013 本轮修正 CR30-CR31：动作代际令牌 + reconcile 原子准入——`sdn_operations` 新增 `active_attempt_id`/`active_started_at` 持久列；准入/收尾 CAS 绑定 phase + token（旧代际迟到零行，杜绝 ABA）；reconcile 从 `unknown` 原子准入 `reconciling`，active phase 走 lease 判定失联的 `claim_stale_takeover`，`withdrawn` 不可被 reconcile 改写。
- S1-014 本轮修正 CR32：stale takeover 正确归属 active attempt——拆分 `active_attempt`（token 指向的失联动作，只标它及其 started unit 为 unknown，无效/跨 operation token 保守拒绝）与 `effect_attempt`（设备写副作用 execute/withdraw，已确定终态不降级）；validating 失联按 port_bind 回读恢复到 `awaiting_validation` 而不冒充完整业务验证成功。
- S1-015 本轮修正 CR35：收紧 stale takeover 的 active attempt 身份与终态保护——唯一 phase→kind 映射（applying→execute/validating→validate/withdrawing→withdraw）；可接管状态仅 claimed/running；`claim_stale_takeover` 单条原子 UPDATE + EXISTS 消除「先读后改」竞态；条件式 `mark_attempt_stale`（rowcount==1 才继续，零行回滚接管）；终态/unknown/错 kind token 一律保守拒绝。
- S1-016 本轮修正 CR36：真实设备证据门禁与前置部署语义闭环——冻结两套门禁语义（VPC create preflight「VNI 应不存在」deferred vs terminal access predeploy「VSI 必须存在」，不得混用）；`_l2_ready_status` 收紧为绝对新鲜度（600s）+ 采集晚于配置完成；VPC 版本因果（`create.version == vpc.version`，deployment 创建时固化）；execute 证据不足时强制重新取证（只读 display），采集失败在消费 plan 前阻断（零业务副作用）；`SdnPreflight` deferred `success=True` 明确为 create 路径 blocker/后续项。注：CR36 当时口径的 `validation_result=active`/全命令遍历/`raw_has_error` 已被 S1-017 CR37（L2/L3 解耦）与 S1-018 CR38（type3 按目标 RD 归属）取代。
- S1-017 本轮修正 CR37：解除 terminal L2 接入门禁对 L3 网关健康的隐式耦合——移除「整张快照 `validation_result==active`」与「遍历整张快照所有命令」两处 L3 耦合；冻结 L2 必需条件（`bgp_peer_established`/`vsi_exists`/`vsi_up`/`type3_present`）+ L2 所需命令映射（BGP peer / VSI / Type-3）；`raw_has_error` 按 L2 命令输出重算；无关 L3/Vsi-interface/ARP 命令失败不拖垮纯 L2 门禁，支撑 L2 的命令缺失/失败/CLI 错误仍 conservative unknown；网关/L3 健康继续由 complete `l3_gateway_ready` + ping 表达，不用 L2 成功冒充 L3 成功。
- S1-018 本轮修正 CR38：Type-3 证据按目标 VPC 的 Route distinguisher 归属校验——`SdnValidationCollector._type3_scoped(text, vni)` 按 `Route distinguisher:` 分块、逐块精确 RD 等值比较，只在目标 `1:{vni}` 块中发现 `[3]` 才为真；替代 `"[3]" in text`；多 RD 正确分块、1:2000 与 1:20000 不串匹配、目标 RD 缺失/只有 [2]/无法解析 → false（由 `_l2_ready_status` 返回 unknown）；清理 CR36/CR37 冲突口径与已重命名测试。
- 隔离 QA：独立 `qa/docker-compose.qa.yml`；S1-018 定向 `test_s1_018_adversarial.py` = **8 passed**；S1-016+017+018 = **31 passed**；validation/access/service/migration = **32 passed**；全量 `pytest tests/` = **560 passed / 55 skipped / 11 failed**（S1-016 基线，11 失败为 `test_ops_toolkit_paramiko.py` 的 `_paramiko_batch_exec` 模块缺失环境问题，非本次引入；本轮按约定不再重跑全量）；`openspec validate --strict` valid；`git diff --check` clean。详见 `handoff.md`。


## 1. 实际基线与证据入口

| 能力 | 实现位置（worktree `backend/`） | 关键事实 |
|---|---|---|
| 租户/VPC CRUD | `app/routers/sdn.py` + `app/models.py` `SdnTenant`/`SdnVpc` | 5 张 SDN 表已建（007 迁移）；编号自动分配 `app/utils/sdn_allocator.py` |
| 端口绑定/解绑 | `app/routers/sdn.py` `create_port_binding` / `deploy` / `undeploy` | 绑定有 `if_index`/`interface_name`/`access_vlan`/`service_instance`/`status`（planned/active/expanding/failed/unbound） |
| VPC 级编排 | `app/routers/sdn.py` `deploy_vpc_to_fabric` / `withdraw_vpc_from_fabric` | 按 EVPN Fabric 成员展开 create/port_bind 或 port_unbind/delete |
| 已有 VPC 扩容 | `app/routers/sdn.py` `start_vpc_expansion` / `complete_vpc_expansion` | 创建 binding + port_bind deployment；完成时网关 ping + display 校验 |
| 下发执行 | `app/services/sdn_deployment_executor.py` | LSTN→SSH22 CLI，RSTN→NETCONF830 XML；写白名单 `.5/.6/.26`；仅 `pending` 可 apply |
| 状态采集 | `app/services/sdn_validation_collector.py` | display 命令集 + 600s 缓存 + force 强制采集 + 逐项校验 |
| 成员准入 | `app/routers/sdn.py` `_is_sdn_fabric_member` | 仅信 `Device.sdn_role == "evpn_leaf"`，不信设备名/platform |
| OOB 保护 | `app/routers/sdn.py` `_parse_protected_interfaces` | `Device.protected_interfaces` 拦截绑定 |
| 预检 | `app/services/sdn_preflight.py` | 本地 2 项（型号/online）；设备侧 4 项仍是 deferred 占位 |

## 2. N1-01 ~ N1-10 逐项核对

| 编号 | 现状（可复用） | 缺口 / 待确认 |
|---|---|---|
| N1-01 找到 VPC 及接入情况 | tenant/vpc/binding/deployment/snapshot 5 表 + 列表/详情端点 | 无聚合读取端点；无终端/主机模型（仅 `expected_host_ip` 字符串）；跨业务/技术/证据视图的对象身份未统一表达 |
| N1-02 看清知道/不知道 | snapshot 有 `collection_started_at/completed_at` + `cached` + `validation_result/details` | S1-006 已分离 L2（vsi/EVPN）与 L3/网关（Vsi-interface/L3VNI）两维 + `host_observed` 主机证据 + 因果窗口；scoped 网关 ping 仍未实现（`gateway_reachable=None`） |
| N1-03 预览新增接入 | 成员准入、受保护接口、绑定冲突、地址/绑定检查 | 目标 Leaf 未部署该 VPC 的前置检查缺失；预览/执行未分离（expansion `auto_apply=True` 默认直接执行）；preflight 设备侧 4 项仍是占位 |
| N1-04 执行并保留进度 | deployment 有 `parent_deployment_id`/`unit`/`port_binding_id` + apply + status | 无"操作请求"实体关联 request→attempts→results；无幂等键；刷新后恢复进度只能按 vpc/device/action 过滤；auto_apply 默认值不一致（fabric=false，expansion=true） |
| N1-05 接线后验证 | `complete_vpc_expansion` 用 `force_validation=True` 强制新采集 + 网关 ping | 证据未显式绑定"本次操作后"；变更前缓存保护依赖 force 语义，无操作时间戳关联；ping 走裸 `SSHExecutor`（业务层） |
| N1-06 深入分析 | 无聚合下钻端点 | 缺业务→逻辑→设备/端口联动 + 脱敏原始证据的统一返回 |
| N1-07 理解过程与失败 | deployment 列表/详情 + `error` 字段 | 无操作级事件链；中间事件非持久化；部分失败未建模（executor 首错即停整单 failed） |
| N1-08 撤回本次新增 | `undeploy_port_binding` → port_unbind；整 VPC withdraw | 无"仅本次新建且无新引用"守卫；无操作级撤回（只有单绑定 undeploy 或整 VPC withdraw） |
| N1-09 新旧入口共存 | 同一 `sdn.py` 路由；共享受保护接口/成员准入 | 预览后对象被旧入口改变→重校验机制缺失（无计划版本/有效性戳） |
| N1-10 交互可用 | `APIResponse` 统一 error_key/error_params + 空列表 | 部分失败/未知/不支持未统一建模为可解释状态 |

## 3. 关键架构事实（复用边界 + 并发缺口）

- 执行链唯一：frontend → config 容器 → `SdnDeploymentExecutor` → `NetconfClient`/`SSHExecutor` → 设备；ops-toolkit 不参与业务下发。
- **并发缺口（R1，S1-005 已修复）**：executor 改 CAS `UPDATE ... WHERE status='pending'`（`sdn_deployment_executor.py`）；绑定冲突改为层级 claim（部分唯一索引）兜底（`sdn.py`/`sdn_access.py` + `sdn_operation_service.py`）。原 `:139-144` check-then-act 缺口已关闭。
- **前置部署缺口（R2）**：`sdn_preflight.py:101-131` 四项设备侧检查为 deferred 占位（返 `success=True, reason="deferred"`），不能当作通过。
- **证据缺口（R4，现状，规范设计已替换）**：现有 `sdn_validation_collector.py:106-110` `_is_fresh` 只比较 `created_at` 与 now，无 attempt 因果窗口；现有 `binding.created_at`（`models.py:232`）为插入时刻，早于实际下发。规范设计（design.md C7）改为 `collection_started_at >= deployment.completed_at` 因果断言，不再以 `binding.created_at` 判新鲜度。
- `SdnDeployment.planned_config` 已是可序列化命令计划（`TemplateUnit` 双套 payload），可直接复用为"计划→执行→结果"的持久化载体。
- `SdnValidationSnapshot` 已是"采集→校验结论"的持久化载体，缺的是与 operation 的关联与四维状态拆分。
- 写白名单 `.5/.6/.26` 与 `sdn_role=evpn_leaf` 准入是既有安全边界，S1 不改变。
- 未提交共享阅读副本：`PRD-VNEXT.md`、`openspec/changes/next-product-blueprint/` 仅在原目录，worktree 分支内无这些文件。

## 4. 结论

现有 v3.4 后端已覆盖 S1 的"执行/采集/准入"骨架，可复用；核心增量是补"操作级关联 + 幂等 + 前置部署检查 + 预览失效重校验 + 证据新鲜度分离 + 受控撤回"这一层最小语义，不需要重建执行引擎或对象库。详见 proposal.md / design.md / specs。
