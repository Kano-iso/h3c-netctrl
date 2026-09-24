## ADDED Requirements

### Requirement: 终端接入操作与尝试的稳定关联

后端 SHALL 用 `sdn_operations` 记录一次用户操作请求，并通过可空的 `operation_id` 把本次操作产生的端口绑定、配置下发与校验快照关联回该操作。刷新页面后 SHALL 能通过 operation 标识读取到本次操作的完整进度与证据。

#### Scenario: 刷新页面后恢复同一操作

- **WHEN** 用户对 VPC 发起终端接入并得到 `operation_id`
- **AND** 页面刷新后按 `operation_id` 查询该操作
- **THEN** 后端返回同一操作的请求负载、关联 binding、deployment 列表与最新校验快照
- **AND** 不创建新的 binding 或 deployment

### Requirement: 终端接入幂等与重复提交保护

后端 SHALL 接受调用方提供的 `idempotency_key`；相同键 + 相同授权 scope + 相同归一化请求 SHALL 返回已存在的同一操作，不重复创建绑定或下发；相同键 + 不同归一化请求 SHALL 按 409 冲突规则处理。deployment 的 apply SHALL 仅允许 `pending` 态执行，成功或失败后不可重复应用。完成验证 SHALL NOT 重放已经完成的配置步骤。

#### Scenario: 相同幂等键只创建一次操作

- **WHEN** 用户以 `idempotency_key=K` 提交终端接入并成功
- **AND** 用户再次以相同 `idempotency_key=K` 提交相同授权 scope 与相同归一化请求
- **THEN** 后端返回第一次创建的同一 `operation_id`
- **AND** 不新增 `sdn_port_bindings` 或 `sdn_deployments` 记录

#### Scenario: 已应用 deployment 不可重复 apply

- **WHEN** 一个 deployment 的 status 已为 `success`
- **AND** 再次调用该 deployment 的 apply
- **THEN** 后端拒绝并返回非 pending 错误，不向设备再次下发

### Requirement: 目标 Leaf 未部署 VPC 时阻止接入

终端接入执行前 SHALL 校验目标 Leaf 已具备该 VPC 的前置部署。目标 Leaf 未部署该 VPC 时 SHALL 明确阻塞并说明缺少前置部署，带上下文进入既有 VPC 部署流程；SHALL NOT 把一个端口接入静默扩大为整机 VPC 部署。

#### Scenario: 未部署 VPC 的 Leaf 被拒绝

- **WHEN** 用户对 VPC V 在 Leaf L 上发起终端接入
- **AND** 没有当前有效配置版本 + 最近相关成功变更 + 足够新观测证明该 VPC 的 L2 接入资源（VSI/EVPN）在 L 上就绪
- **THEN** 后端拒绝并返回"目标设备缺少 VPC 前置部署"的错误
- **AND** 不创建端口绑定或下发

### Requirement: 预览与执行分离及计划失效重校验

后端 SHALL 提供预览端点，持久化一条服务端计划记录（不写设备、不创建 binding/deployment/operation），返回将新增/保留的项与阻塞项。执行时 SHALL 依据服务端计划（plan_id）重新执行预览校验并重算语义哈希，检测预览后 VPC / 设备 / 绑定 / 依赖是否被其他入口改变；对象已改变时 SHALL 拒绝照常执行并要求重新预览。

#### Scenario: 预览后对象被旧入口改变

- **WHEN** 用户预览一次终端接入
- **AND** 预览后该 VPC 或目标端口被旧入口改变
- **THEN** 执行时后端重新校验并返回"计划失效，需重新预览"
- **AND** 不按失效计划下发

### Requirement: 证据新鲜度与四维状态分离

后端 SHALL 区分并分别表达：操作执行是否成功、配置是否被回读确认、业务验证是否通过、证据是否新鲜且完整。校验快照 SHALL 记录采集时刻与是否命中缓存，且 SHALL NOT 用变更前缓存证明新变更成功。

#### Scenario: 旧缓存不能证明新接入成功

- **WHEN** 完成验证时最新校验快照的 `collection_started_at` 早于本次配置下发的 `completed_at`（或回读完成 token）
- **THEN** 后端显式 force 采集（不命中缓存）后再判定业务验证
- **AND** 普通 GET/列表/概览不触发采集；仅显式 complete/validate/reconcile 可 force 采集
- **AND** 响应中标注本次证据的采集时刻与 `cached=false`

### Requirement: 采集失败与未知不可伪装为成功

后端 SHALL 用独立状态表达采集失败、证据不足与未知，SHALL NOT 把采集失败伪装成成功空列表或主机故障，SHALL NOT 把未知显示为正常。

#### Scenario: 采集失败不显示为成功

- **WHEN** display 采集任一命令失败或返回错误标记
- **THEN** 校验结果标记为失败或证据不足并保留逐项错误
- **AND** 不返回 `active` 的空成功结果

### Requirement: 受控撤回仅处理本次新建无新引用绑定

后端 SHALL 支持撤回一次终端接入本次新建的端口绑定，仅当该绑定无后续新引用时才执行解绑。撤回 SHALL 保留租户、VPC、网关与其他端口，SHALL NOT 删除共享资源或自动补回。

#### Scenario: 撤回仅移除本次新建绑定

- **WHEN** 用户对一次终端接入发起撤回
- **AND** 该绑定属于本次操作且无其他新引用
- **THEN** 后端生成 `port_unbind` deployment 并回读结果
- **AND** 不删除 VPC、网关、租户或其他端口绑定

### Requirement: VPC 接入情况聚合读取

后端 SHALL 提供聚合读取端点，一次返回某 VPC 的绑定、部署、每设备最新校验快照与证据元数据，并明确每条关联与证据的来源（计划/配置/采集/推断），供前端列表、画布与详情下钻使用。

#### Scenario: 聚合返回 VPC 接入情况

- **WHEN** 查询某 VPC 的接入聚合视图
- **THEN** 返回该 VPC 的端口绑定列表、关联 deployment、每设备最新校验快照及其采集时刻
- **AND** 每条关联标注来源，不生成不存在的物理邻接或主机位置

### Requirement: 执行原子认领与崩溃对账

后端 SHALL 在设备 I/O 前以原子状态转移把 deployment 从 `pending` 认领为 `running`，仅允许唯一执行者进入设备 I/O；并发 apply 的失败者 SHALL 返回冲突错误。崩溃后遗留的 `running` 无完成结果 SHALL 判为待对账；读 / 刷新 SHALL NOT 触发设备 I/O（包括 stale 检测），对账 SHALL 仅由显式 reconcile 动作执行。claim 的 TTL 过期 SHALL NOT 自动转移给新执行者，歧义 claim 仍 SHALL 独占资源。

#### Scenario: 并发 apply 只有一个执行者

- **WHEN** 两个并发请求对同一 pending deployment 调用 apply
- **THEN** 只有一个请求成功认领并进入设备 I/O
- **AND** 另一个请求返回冲突错误，不向设备重复下发

#### Scenario: 读取不触发设备对账

- **WHEN** 查询一个已崩溃遗留 running 状态的 deployment
- **THEN** 后端仅返回状态 unknown，不发起设备回读
- **AND** 只有显式 reconcile 动作才读取设备

### Requirement: 逐单元执行状态与重放规则

后端 SHALL 为每次执行保留每个配置单元的持久状态 `not_started | started | succeeded | failed_known | unknown`，并在设备 I/O 前持久化 `started`、I/O 后持久化终态与证据。`failed_known` SHALL NOT 被当作无副作用；没有确定性结果而只有 `started` 记录的单元 SHALL 为 `unknown`。重放 SHALL 仅允许显式 `not_started` 的单元，且其依赖单元均为 `succeeded`；任何 `unknown` 前置 SHALL 阻塞依赖单元；`unknown` / `failed_known` SHALL NOT 自动重放。

#### Scenario: 仅 started 无结果的单元是 unknown

- **WHEN** 一个单元已有持久化的 `started` 记录但无终态与证据
- **AND** 设备未返回响应
- **THEN** 该单元状态为 unknown，不自动重放
- **AND** 阻塞其后依赖单元，等待显式 reconcile

#### Scenario: 失败结果不等于无副作用

- **WHEN** 一个单元记录为 `failed_known` 但未回读确认设备无变化
- **THEN** 该单元不自动重放
- **AND** 显式 reconcile 先回读设备再决定是否重试

### Requirement: 对账解析不确定单元与目标端口 scoped 证据

后端 SHALL 在对账时把 `started|unknown` 单元解析为 `succeeded|failed_known` 并逐项校验 rowcount；任一单元未解析成功 SHALL NOT 返回 reconciled、SHALL NOT 释放 claims，原 attempt 终态 SHALL 由解析后单元重推。显式 reconcile SHALL 把待对账 binding 作为显式采集 scope 传给 collector，使其无论 status 都能采到目标接口回读；普通周期采集 SHALL NOT 无差别混入 planned/unbound binding。port_bind 对账 SHALL 要求目标接口回读成功且本次 service-instance/access-vlan/VSI 关联 scoped 确认；port_unbind 对账 SHALL 先验证命令存在/成功/无 CLI error，再用结构化语法匹配证明配置缺失，采集失败 SHALL NOT 当配置缺失。CLI 错误 SHALL 同时从结构化 error 字段与 output 文本（`% Wrong parameter`/`Unrecognized command`/`Incomplete command` 等）识别，任何此类输出 SHALL 判 insufficient。

#### Scenario: unknown 单元对账一致收尾

- **WHEN** 原单元为 `unknown` 且目标端口 scoped 证据确认绑定成功
- **THEN** 单元解析为 `succeeded`、原 attempt/deployment/operation/binding 一致更新、claims 释放

#### Scenario: 采集失败不当配置缺失

- **WHEN** port_unbind 对账缺少接口命令、命令 `success=false` 或带 CLI error
- **THEN** 不返回成功，保持 unknown/ambiguous 且不释放 claims

#### Scenario: output 内 CLI 错误不算配置缺失

- **WHEN** port_unbind 对账命令返回 `success=true`/`error=null` 但 output 含 `% Wrong parameter` 等 CLI 错误
- **THEN** 判 insufficient，不返回成功、不判配置缺失

#### Scenario: 显式对账采集待对账接口

- **WHEN** 待对账 binding 仍为 `planned`/`unbound`（不在 active/expanding）
- **THEN** 显式 reconcile 仍发出目标接口 display 命令取得 scoped 证据

### Requirement: 完成验证守卫与主机观测同记录

后端 SHALL 仅在 operation 为 `awaiting_validation` 且存在 `port_bind` deployment 时执行 complete/validate，并在 mutation 前 owner-aware 获取/复用 tenant/vpc/vpc-device claims；已 `withdrawn` 等不可验证终态 SHALL NOT 改写或新建 validate attempt。主机观测 SHALL 仅在本地 ARP/MAC 同一条记录内同时出现 expected_host_ip 与目标接口（或经同一 MAC 关联）时计 `host_observed=true`；命令失败 SHALL NOT 产生观测为真；远端 Type-2 SHALL 仅标 remote/inferred。

#### Scenario: 已撤回不可再验证

- **WHEN** operation 已 `withdrawn` 且调用 complete
- **THEN** 返回原结果，不新建 validate attempt、不改写状态

#### Scenario: IP 与端口分属两行

- **WHEN** 本地 ARP 输出中 expected_host_ip 与目标接口分属不同记录
- **THEN** `host_observed=false`

### Requirement: 完成验证的确定完成幂等与 unknown 恢复

后端 SHALL 仅在 latest validate attempt 为确定完成（`succeeded`/`failed_known`）时对 complete 幂等返回；`unknown` validate attempt SHALL NOT 幂等返回，且旧 attempt 历史 SHALL 保留。当 operation 为 `unknown`、port_bind 执行已确定成功（`success` + `config_completed_at`）、且存在未完成的 validate attempt 时，complete SHALL 允许在持有同 operation claims 的前提下显式重试并新建 validate attempt，恢复后 SHALL 到达确定验证终态；SHALL NOT 自动重放设备写操作。

#### Scenario: 首次采集失败后重试成功

- **WHEN** 首次 complete 采集失败使 validate attempt/operation 为 unknown、claims 为 ambiguous
- **AND** port_bind 执行已确定成功
- **THEN** 再次 complete 新建 validate attempt 并采集，成功后 operation 到达确定终态、claims 释放
- **AND** 旧 unknown attempt 历史保留、新 attempt 可追溯

#### Scenario: 确定完成才幂等

- **WHEN** latest validate attempt 为 `succeeded` 且再次调用 complete
- **THEN** 幂等返回原结果，不新建 validate attempt

### Requirement: 同一 operation 至多一个活跃 validate attempt（并发准入）

后端 SHALL 用原子准入保证同一 operation 同时至多一个 validate attempt 进入设备读取/网关 ping I/O：complete SHALL 先把 `awaiting_validation`（或可恢复的 `unknown`）原子 CAS 为 `validating`，仅 rowcount==1 的请求获胜并在同一短事务内创建 validate attempt、获取/复用 claims；失败者 SHALL 返回明确的 `sdn.operation_in_progress`，不创建第二 attempt、不执行 collector/ping。准入后崩溃 SHALL 留下 `validating` + 未完成 attempt 的可对账痕迹，不静默回退 `awaiting_validation` 重放。

#### Scenario: awaiting_validation 并发只有一个赢家

- **WHEN** 两个并发 complete 同时从 `awaiting_validation` 进入
- **AND** 第一个请求的 collector 被 barrier 阻塞
- **THEN** 仅一个请求进入 collector/ping，仅存在一个活跃 validate attempt
- **AND** 另一请求返回 `sdn.operation_in_progress`

#### Scenario: unknown 恢复并发只有一个赢家

- **WHEN** 已有 unknown validate attempt 且两个并发 complete 同时恢复
- **THEN** 仅一个新 validate attempt 进入 I/O，旧 unknown attempt 历史保留
- **AND** 另一请求返回 `sdn.operation_in_progress`

#### Scenario: 准入后崩溃不留重放窗口

- **WHEN** 请求已准入（op=`validating`、attempt=`claimed`）但进程崩溃
- **THEN** 后续 complete 返回 `sdn.operation_in_progress`，不新建 attempt、不回退 `awaiting_validation`、不执行 collector/ping

### Requirement: validate 与 withdraw 跨动作互斥与条件收尾

后端 SHALL 用数据库持久状态的原子 CAS 保证同一 operation 的 validate 与 withdraw 互斥：withdraw 进入任何设备 I/O 前 SHALL CAS 取得 `withdrawing`（与 `validating`/`withdrawing` 互斥），validate 在 `validating`/`withdrawing` 下 SHALL 返回 `sdn.operation_in_progress`。无论谁先取得准入，另一方 SHALL NOT 创建有效 attempt/deployment、不得进入 collector/ping 或设备写 I/O。validate 与 withdraw 的最终 operation 状态写入 SHALL 带 phase + 代际令牌条件 CAS（`UPDATE ... WHERE status=from_status AND active_attempt_id=<attempt>`）；零行更新或状态已被终态/新代际改变时 SHALL NOT 覆盖现状、SHALL NOT 误释放另一动作仍需的 claims，并留下明确诊断。`withdrawn` SHALL 保持不可逆终态。

#### Scenario: validate 先取得准入

- **WHEN** validate 先 CAS 取得 `validating` 且 collector 被阻塞
- **AND** 同时发出 withdraw
- **THEN** withdraw 返回 `sdn.operation_in_progress`，不创建 withdraw attempt、不创建 port_unbind deployment、不调用 executor
- **AND** validate 正常收尾

#### Scenario: withdraw 先取得准入

- **WHEN** withdraw 先 CAS 取得 `withdrawing` 且 executor 被阻塞
- **AND** 同时发出 complete
- **THEN** complete 返回 `sdn.operation_in_progress`，不创建 validate attempt、不调用 collector/ping
- **AND** withdraw 成功后 operation 保持 `withdrawn`

#### Scenario: 迟到收尾不覆盖现状

- **WHEN** validate 已准入但收尾前 operation 被并发动作改为 `withdrawn`
- **THEN** validate 的条件收尾 CAS 零行更新，不覆盖 `withdrawn`、不误释放 claims
- **AND** 返回明确 `late completion` 诊断

#### Scenario: withdraw 允许/拒绝状态

- **WHEN** operation 处于 `planned`/`applied`/`awaiting_wiring`/`awaiting_validation`/`succeeded`/`degraded`/`failed`/`unknown`
- **THEN** withdraw 允许准入
- **WHEN** operation 处于 `withdrawn`（不可逆终态）则幂等返回；处于 `validating`/`withdrawing` 则返回 `sdn.operation_in_progress`

### Requirement: apply 纳入同一操作动作仲裁

后端 SHALL 让 `apply_access` 与 validate/withdraw 共享同一持久化动作仲裁：显式 apply 进入任何设备 I/O 前 SHALL 原子 CAS `awaiting_wiring → applying`，只有赢家可调用 executor；`applying` SHALL 与 `validating`/`withdrawing` 互斥。两个并发 apply SHALL 只有一个赢家，输家 SHALL 返回 `sdn.operation_in_progress` 且不改变 execute attempt、deployment、operation、binding 或 claims。apply 收尾 SHALL 条件 CAS `applying → awaiting_validation|failed|unknown`（匹配 `applying + active_attempt_id=原 execute attempt`）；迟到/零行收尾 SHALL NOT 覆盖 `withdrawn` 或其他 phase、SHALL NOT 释放/误标另一动作 claims。apply 的 deployment CAS 失败（deployment 已被他人认领 running）SHALL 停止上层收尾，不把他人执行中的 deployment/attempt 推导为 unknown。准入后崩溃 SHALL 留下 `applying` + 原 execute attempt/deployment/claims 可对账痕迹，不自动重放 port_bind，走显式 reconcile。

#### Scenario: apply 先取得准入

- **WHEN** apply 先 CAS 取得 `applying` 且原 port_bind executor 被阻塞
- **AND** 同时发出 withdraw
- **THEN** 只有 bind I/O；withdraw 返回 `sdn.operation_in_progress`，不创建 attempt/port_unbind deployment、不进 executor
- **AND** apply 正常收尾

#### Scenario: withdraw 先取得准入

- **WHEN** withdraw 先 CAS 取得 `withdrawing` 且 port_unbind executor 被阻塞
- **AND** 同时发出 apply
- **THEN** apply 返回 `sdn.operation_in_progress`，不调用 port_bind executor、不改原 execute attempt/deployment
- **AND** withdraw 正常收尾

#### Scenario: 两个并发 apply 只有一个赢家

- **WHEN** 两个 apply 同时请求
- **THEN** 只有一次 executor/I/O；输家返回 `sdn.operation_in_progress` 且无状态副作用；赢家收尾一致

#### Scenario: apply 迟到收尾不覆盖现状

- **WHEN** apply 已准入但收尾前 operation 被并发动作改为 `withdrawn`
- **THEN** apply 的条件收尾 CAS 零行更新，不覆盖 `withdrawn`、不误释放 claims，返回明确诊断

#### Scenario: deployment CAS 失败即停

- **WHEN** apply 调 executor 时 deployment 已被他人认领（`running`）
- **THEN** apply 停止上层收尾并返回 `sdn.deployment_not_pending`，不把他人执行中的 deployment/attempt 推导为 unknown、不标 claims ambiguous

### Requirement: 动作代际令牌（收尾 CAS owner-aware）

后端 SHALL 为 operation 持久化当前动作代际令牌（`active_attempt_id`，不可复用整数 token）并持久化 `active_started_at`；动作准入 SHALL 在同一短事务绑定 `phase + active_attempt_id + active_started_at`。apply SHALL 使用原 execute attempt 身份，validate/withdraw/reconcile SHALL 使用各自新 attempt 身份；准入输家留下的临时 attempt SHALL 回滚。所有动作收尾 CAS SHALL 同时匹配 `operation_id + phase + active_attempt_id`，成功时原子清空 token；旧代际迟到收尾 SHALL 返回零行，绝不覆盖新代际状态、绝不释放/误标新代际 claims。令牌 SHALL 仅存于数据库持久状态，不得用进程内对象或内存锁保存。

#### Scenario: 旧代际迟到收尾被拒（ABA）

- **WHEN** 动作 A 已准入但被阻塞
- **AND** 其 phase 被接管后新一代 B 进入同名 phase（持有新 token）
- **THEN** A 的收尾 CAS 零行更新，不覆盖 B 的状态、不动 B 的 claims

### Requirement: reconcile 参与动作仲裁并区分活跃与失联

后端 SHALL 让 reconcile 参与同一动作仲裁。普通 reconcile SHALL 只能从明确 `unknown` 原子准入为 `reconciling`（绑定自身 attempt 令牌），与 `applying`/`validating`/`withdrawing`/`reconciling` 互斥，输家在 collector 前返回 `sdn.operation_in_progress`，不做采集/I/O、不改状态。对 admission 后崩溃留下的 active phase，SHALL 提供显式且受保护的 stale takeover：依据持久化 `active_started_at` 与明确最小租约（保守且大于单次网络 I/O 上限）判定失联，`phase + old active token + stale` 条件 CAS 抢占；未过 lease 或 `active_started_at IS NULL` 的活跃动作 SHALL NOT 被 reconcile。takeover 后 SHALL 把 `active_attempt`（token 指向的失联动作，见下）及其 started unit 按 unknown 留审计，再由新 reconcile attempt 采集，不自动重放设备写。reconcile 的全部终态写入、deployment/binding 修改及 claim 释放 SHALL 在仍持有 `reconciling + active token` 时发生；收尾 CAS 零行 SHALL NOT 改业务实体、SHALL NOT 释放 claims；collector 失败 SHALL 条件收尾到 unknown，不得无条件覆盖并发终态/phase；`withdrawn` SHALL NOT 被 reconcile 改写。

#### Scenario: 活跃动作下 reconcile 采集前被拒

- **WHEN** operation 处于 `applying`/`validating`/`withdrawing`（未过 lease）
- **AND** 同时发出 reconcile
- **THEN** reconcile 返回 `sdn.operation_in_progress`，collector 调用为 0，不新建 reconcile attempt，无业务状态副作用

#### Scenario: unknown 普通 reconcile 单赢家

- **WHEN** 两个并发 reconcile 从 `unknown` 进入
- **THEN** 仅一个赢家进入 collector，另一请求无副作用

#### Scenario: active phase 失联后受保护接管

- **WHEN** operation 处于 active phase 且 `active_started_at` 超过最小租约
- **THEN** reconcile 的 stale takeover CAS 抢占（单赢家），active_attempt（token 指向的失联动作）及其 started unit 记录为 unknown，新 reconcile attempt 依据回读收尾，且无设备写重放
- **WHEN** 未过 lease 或 `active_started_at IS NULL`
- **THEN** stale takeover 被拒

#### Scenario: reconcile collector 失败/迟到收尾

- **WHEN** reconcile collector 失败或收尾前 operation 被并发动作改为 `withdrawn`/新 phase
- **THEN** reconcile 条件收尾 CAS 零行，不覆盖现状、不释放 claims

### Requirement: stale takeover 正确归属 active attempt

后端 SHALL 在 stale takeover 时严格区分两种 attempt 身份。`active_attempt` SHALL 按 takeover 前 `active_attempt_id` 查询且必须属于本 operation，是需要被标 unknown 的失联动作；后端 SHALL 只修改它及其 started units 并写入 stale takeover 证据。token 不存在、不属于本 operation、kind 不匹配 phase、或状态非活动态时 SHALL 保守拒绝接管（不采集、不改任何 attempt/claim）。`effect_attempt` SHALL 是与设备写副作用关联的 execute/withdraw attempt，用于确定 deployment/action/目标状态；其已确定终态 SHALL NOT 因 validate/reconcile 崩溃而被改写。applying/withdrawing 失联时 active 与 effect 可为同一对象，validating 失联时二者不同。reconcile 收尾 SHALL 只解析 effect_attempt 中真正 uncertain 的 started/unknown units；effect_attempt 已 succeeded/failed_known 时 SHALL NOT 降级。validate 失联 SHALL 按原 port_bind 回读恢复到合理状态，但 SHALL NOT 把「配置存在」冒充完整业务验证成功。

#### Scenario: validating 失联接管保留 execute 终态

- **WHEN** operation 处于 `validating`、execute attempt 已 succeeded、active validate attempt 为 claimed/running
- **AND** reconcile 通过 stale takeover 接管
- **THEN** execute attempt 保持 succeeded、validate attempt 变 unknown、新 reconcile attempt 独立留痕、无设备写重放
- **AND** operation 按 port_bind 回读恢复到 awaiting_validation（而非 succeeded）

#### Scenario: applying/withdrawing 失联接管标记 started unit

- **WHEN** operation 处于 `applying`/`withdrawing` 且 active 与 effect 为同一 execute/withdraw attempt
- **AND** reconcile 通过 stale takeover 接管
- **THEN** 该 attempt 的 started unit 记 unknown，随后按回读解析

#### Scenario: token 无效或跨 operation 拒绝接管

- **WHEN** `active_attempt_id` 指向不存在的 attempt 或属于其他 operation 的 attempt
- **THEN** reconcile 保守拒绝，不采集、不新建 reconcile attempt、不改任何 attempt/claim

### Requirement: stale takeover 的 active attempt 身份与终态保护

后端 SHALL 建立唯一 phase→kind 映射：`applying→execute`、`validating→validate`、`withdrawing→withdraw`；stale takeover 前 SHALL 在同一准入逻辑中校验 token 所属 operation、kind 与 phase 一致。可接管 attempt 状态 SHALL 仅限真实活动态 `claimed|running`；终态（`succeeded`/`failed`/`failed_known`）或 `unknown` attempt SHALL NOT 被 stale takeover 再次降级或覆盖。对 token 不存在、跨 operation、kind 不匹配、状态不可接管 SHALL 统一保守拒绝，不创建残留 reconcile attempt、不采集、不改 operation/attempt/unit/claim/deployment/binding。takeover 的原子更新 SHALL 同时证明 operation phase/token/lease 仍匹配，且 active attempt 的 operation/kind/status 仍可接管，不得依赖进程内锁或 Python 先读后改。条件式失联标记（`mark_attempt_stale`）SHALL 仅在 attempt 仍为活动态时生效且 rowcount 为 1；零行 SHALL 回滚接管或保守收尾，不得宣称成功。

#### Scenario: 同 operation 错 kind token 拒绝

- **WHEN** operation 处于 `applying` 且 `active_attempt_id` 指向同 operation 的 validate attempt
- **OR** operation 处于 `validating` 且 `active_attempt_id` 指向同 operation 的 execute attempt
- **OR** operation 处于 `withdrawing` 且 `active_attempt_id` 指向同 operation 的 execute/validate attempt
- **THEN** reconcile 保守拒绝，且原 execute/validate/withdraw attempt 历史完全不变

#### Scenario: 终态/unknown attempt 拒绝接管

- **WHEN** `active_attempt_id` 指向的 attempt 状态为 `succeeded`/`failed`/`failed_known`/`unknown`
- **THEN** reconcile 保守拒绝，不降级、不覆盖该 attempt 终态，不采集、不改 claim

#### Scenario: 正确 kind + 活动态仍可接管

- **WHEN** attempt kind 匹配 phase 且状态为 `claimed`/`running`
- **THEN** reconcile 通过 stale takeover 单赢家抢占，按回读解析并清空 token

#### Scenario: 读取后、CAS 前 attempt 被转终态

- **WHEN** reconcile 已读取 active attempt 为活动态，但在 takeover CAS 执行前 attempt 被并发转为终态
- **THEN** takeover CAS 失败（EXISTS 不再成立），不得覆盖终态、不得抢占 operation

### Requirement: 真实设备证据门禁与前置部署语义闭环

后端 SHALL 严格区分两套门禁语义：VPC create preflight（`SdnPreflight` 四项 deferred，其中「VNI/VLAN 应不存在」是创建前语义，其 deferred `success=True` 是占位而非通过）与 terminal access predeploy proof（目标 VPC 在目标 Leaf 已存在且 L2 可用，目标 VSI/VNI 必须存在），二者 SHALL NOT 混用。terminal access 的 `_l2_ready_status` SHALL 同时证明：① 成功 create deployment 对应当前 `vpc.version`（`create.version == vpc.version`，不一致/缺失 → unknown，不伪造）；② 快照绝对新鲜（`collection_completed_at` 距今 ≤ 600s）；③ 快照采集晚于相关配置完成时间；④ 原始命令按 L2 所需命令映射成功且无 CLI 错误；⑤ `validation_details` 中 L2 必需条件为真：`bgp_peer_established`/`vsi_exists`/`type3_present` 始终必需；`vsi_up` 动态必需——仅当目标 Leaf 已有 active/expanding 本地绑定时必需（S1-020 统一 collector `vsi_up.required = bool(active/expanding bindings)` 语义），无本地绑定时（首次 AC bootstrap）`vsi_up=False` SHALL NOT 阻断第一个本地 AC（L2-scoped 无 CLI 错误）。字段缺失、旧格式、解析失败、L2 命令失败、L2 CLI 错误一律 unknown/blocker。execute SHALL 在证据不足时重新取得足够新的权威设备证据（force 采集，只读 display），不得复用陈旧缓存；采集失败/SSH 不通/命令不支持/输出不完整 SHALL 在消费 plan、创建 operation/binding/deployment、占用 claim 之前阻断（零业务副作用）。单次空输出 SHALL NOT 被当作「设备无配置」。

#### Scenario: fresh + scoped healthy 快照放行

- **WHEN** create deployment 对应当前 `vpc.version`，且最新快照新鲜、晚于配置完成、L2 所需命令成功无 CLI 错误、L2 必需条件全真
- **THEN** `_l2_ready_status` 返回 `ready`

#### Scenario: 陈旧/缺项/命令失败快照阻断

- **WHEN** 快照超过 600s、早于配置完成、L2 所需命令缺失/失败/带 CLI 错误、`validation_details` 缺项或非法 JSON、或 L2 必需条件为假
- **THEN** `_l2_ready_status` 返回 `unknown` 并给出具体原因，不放行

#### Scenario: VPC 版本变化后旧 deployment 阻断

- **WHEN** 当前 `vpc.version` 变化，而成功 create deployment 的 `version` 不再等于 `vpc.version`
- **THEN** `_l2_ready_status` 返回 `unknown`，不伪造当前配置与旧 deployment 的对应关系

#### Scenario: execute 取证失败零业务副作用

- **WHEN** execute 证据不足而触发 force 采集，采集失败（SSH 不通/命令不支持/输出不完整）
- **THEN** execute 阻断，plan 未被消费，不创建 operation/binding/deployment、不占用 claim

#### Scenario: create preflight 与 terminal predeploy 语义反例

- **WHEN** `SdnPreflight.check_vpc_not_exists` 因 deferred 返回 `success=True`（「VNI 应不存在」的 create 语义）
- **AND** terminal access 的目标 VSI 实际不存在（`vsi_exists.ok=False`）
- **THEN** terminal access 的 `_l2_ready_status` 仍返回 `unknown`，SHALL NOT 把 create preflight 的「应不存在」复用为「已存在且就绪」的证明

### Requirement: terminal L2 门禁与 L3 网关健康解耦

后端 SHALL 使 terminal L2 predeploy 门禁独立于 L3/网关健康：`_l2_ready_status` SHALL NOT 以整张快照 `validation_result == "active"` 为门禁，也 SHALL NOT 遍历整张快照所有命令。其 SHALL 按 L2 必需条件（`bgp_peer_established`/`vsi_exists`/`type3_present` 始终必需，`vsi_up` 仅当目标 Leaf 已有 active/expanding 本地绑定时必需）与 L2 所需命令映射（`display bgp peer l2vpn evpn` + `display l2vpn vsi name {vsi_name} verbose` + `display bgp l2vpn evpn`）独立判定；无 CLI 错误（`raw_has_error`）SHALL 按 L2 命令输出重算，不复用 collector 全量 all_text 的 `raw_has_error`。无关的 Vsi-interface/L3VNI/ARP/MAC/Type-2 命令失败或 L3 条件为假 SHALL NOT 阻断纯 L2 门禁；支撑 BGP/VSI/Type-3 的命令缺失、失败、CLI 错误仍 SHALL conservative unknown。网关/L3 健康 SHALL 继续由 complete/业务验证的 `l3_gateway_ready` 与 ping 维度表达，不得删除，也 SHALL NOT 用 L2 成功冒充 L3 成功。

#### Scenario: degraded 但 L2 健康 → ready

- **WHEN** 整张快照 `validation_result=degraded`（因 L3/网关条件失败）
- **AND** 所有 L2 必需条件（`bgp_peer_established`/`vsi_exists`/`type3_present`，以及有 active/expanding 绑定时的 `vsi_up`）及其命令健康
- **THEN** `_l2_ready_status` 返回 `ready`

#### Scenario: L3 命令失败但 L2 命令成功 → ready

- **WHEN** Vsi-interface/L3VNI 相关 display 命令失败或带 CLI 错误
- **AND** BGP peer / VSI / Type-3 三条 L2 命令成功且无 CLI 错误
- **THEN** `_l2_ready_status` 返回 `ready`，SHALL NOT 被 L3 命令失败拖垮

#### Scenario: L2 条件或命令失败分别阻断

- **WHEN** `bgp_peer_established`/`vsi_exists`/`type3_present` 任一为假，或目标 Leaf 已有 active/expanding 绑定而 `vsi_up` 为假，或 L2 所需命令缺失/`success=false`/CLI 错误
- **THEN** `_l2_ready_status` 返回 `unknown` 并给出具体原因，不放行

#### Scenario: 网关不健康仍表达为 degraded

- **WHEN** complete/业务验证时 L2 就绪但 `vsi_interface_exists`/`l3_vni_present` 为假（`l3_gateway_ready=False`）
- **THEN** 最终状态为 `degraded`（而非 `succeeded`），SHALL NOT 把 L2 ready 冒充完整业务成功

### Requirement: 首次 AC bootstrap 与已有 AC 健康检查差异（S1-020）

后端 SHALL 统一 `_l2_ready_status` 与 collector 的 `vsi_up.required = bool(active/expanding 本地绑定)` 语义，消除「fresh VPC 无本地 AC/tunnel 时 `VSI State: Down` 导致第一个端口接入永远无法创建 AC」的控制流因果悖论：

- 目标 Leaf **尚无** active/expanding 本地绑定时，`vsi_up` 不作为 predeploy 门禁（首次 AC bootstrap 放行），但 `bgp_peer_established`/`vsi_exists`/目标 RD `type3_present` 仍必须为真，版本因果、无后续成功 delete、证据新鲜且晚于配置完成、L2 三条 display 成功无 CLI 错误仍必须满足。
- 目标 Leaf **已有** active/expanding 本地绑定时，`vsi_up` 仍是必需条件；`VSI State: Down` SHALL 保守阻断后续接入，不得把真实故障掩盖成 ready。
- 判断「已有绑定」只认 `status ∈ {active, expanding}`；`unbound`/`planned` 等历史行 SHALL NOT 误判为「已有绑定」。
- preview 与 execute SHALL 使用同一动态必需语义；execute 证据不足仍 force refresh，失败零业务副作用。
- 不得删除或放宽版本因果、TTL、配置完成时间、命令完整性、CLI 错误、BGP peer、VSI 存在、目标 RD Type-3 等门禁。

#### Scenario: 无本地绑定 + vsi_up=Down → 放行首个 AC

- **WHEN** 目标 Leaf 无 active/expanding 本地绑定，`vsi_up.ok=False`，其余 L2 证据健康
- **THEN** `_l2_ready_status` 返回 `ready`，preview `predeploy_status=ready`，execute 不再返回 `sdn.predeploy_unknown`

#### Scenario: 已有 active/expanding 绑定 + vsi_up=Down → 保守阻断

- **WHEN** 目标 Leaf 已有 active/expanding 本地绑定，且 `vsi_up.ok=False`
- **THEN** `_l2_ready_status` 返回 `unknown`（detail 含 `vsi_up`），后续接入被阻断

#### Scenario: unbound/planned 历史行不误判为已有绑定

- **WHEN** 目标 Leaf 仅有 `unbound`/`planned` 状态的历史绑定，`vsi_up.ok=False`
- **THEN** `_l2_ready_status` 返回 `ready`（不要求 `vsi_up`）

### Requirement: Type-3 证据按目标 VPC 的 Route distinguisher 归属

后端 SHALL 使 `type3_present` 只证明目标 VPC 的 Type-3，而非设备上任意 VPC 的 Type-3：`SdnValidationCollector._validate()` SHALL 用 scoped 判定（`_type3_scoped`）只在目标 `Route distinguisher: 1:{vpc.vni}` 路由块中发现 `[3]` 时才令 `type3_present.ok=True`。多 RD 输出 SHALL 按 `Route distinguisher:` 行正确分块；其他 RD 有 `[3]`、目标 RD 只有 `[2]`、或目标 RD 块缺失/无法解析 SHALL 判定 False。判定 SHALL NOT 使用整段 `"[3]" in text`，也 SHALL NOT 用裸子串让 `1:2000` 命中 `1:20000`。False 由 `_l2_ready_status` 返回 `unknown`，不伪造成功。

#### Scenario: 目标 RD 块有 [3] → true

- **WHEN** `display bgp l2vpn evpn` 中目标 `Route distinguisher: 1:{vpc.vni}` 块内存在 `[3]` 路由
- **THEN** `type3_present.ok=True`

#### Scenario: 其他 RD 有 [3]、目标 RD 只有 [2] → false

- **WHEN** 另一 RD 块有 `[3]`，目标 RD 块只有 `[2]`（或无 `[3]`）
- **THEN** `type3_present.ok=False`，`_l2_ready_status` 返回 `unknown`

#### Scenario: 目标 RD 块缺失 → false

- **WHEN** 输出中不存在目标 `Route distinguisher: 1:{vpc.vni}` 块
- **THEN** `type3_present.ok=False`

#### Scenario: VNI 子串不串匹配

- **WHEN** 目标 vni=2000，输出只有 `Route distinguisher: 1:20000` 块的 `[3]`
- **THEN** `type3_present.ok=False`（`1:2000` SHALL NOT 命中 `1:20000`）

### Requirement: 资源声明互斥与层级冲突

后端 SHALL 用 `sdn_resource_claims` 的部分唯一索引 `(resource_key) WHERE released_at IS NULL` 保证每个未释放资源（含 `held` 与 `ambiguous`）独占，歧义 claim SHALL 继续排斥新 owner。子级 mutation SHALL 按升序获取全部祖先 claim（tenant、vpc、vpc-device、device-port），父级删除 SHALL 获取祖先 key 从而与子操作冲突。

#### Scenario: 歧义 claim 阻止新 owner

- **WHEN** 一个 claim 因 TTL 过期被标记为 ambiguous（released_at 仍 NULL）
- **AND** 新请求尝试对同一 resource_key 获取 held claim
- **THEN** 唯一索引约束使插入失败，新请求被阻塞
- **AND** 只有显式 reconcile 释放后才可被新 owner 获取

#### Scenario: 父删除与子操作冲突

- **WHEN** 某 VPC 下的端口接入正持有 `vpc:{vid}` claim
- **AND** 另一请求删除该 VPC（需获取 `vpc:{vid}`）
- **THEN** 删除被阻塞，直到子操作释放 claim
- **AND** 不出现父删与子写并发

### Requirement: 幂等键冲突、隐私与鉴权顺序

后端 SHALL 在返回已存在操作前先校验鉴权与请求 scope；同 key 在不可访问 scope SHALL 返回 404 且不泄漏 fingerprint/status/body；授权且同 scope 同指纹 SHALL 返回 200；授权且同 scope 异指纹 SHALL 返回 409。并发 INSERT SHALL 依赖 `idempotency_key` 唯一约束 + IntegrityError 回查。

#### Scenario: 同键不同请求返回冲突

- **WHEN** 以 `idempotency_key=K` 首次提交请求 A
- **AND** 以相同 `idempotency_key=K` 提交归一化后不同的请求 B
- **THEN** 后端返回幂等冲突错误
- **AND** 不返回请求 A 的操作内容给 B 的调用方

#### Scenario: 不可访问 scope 的键不泄漏

- **WHEN** 以 `idempotency_key=K` 提交但 scope 对调用方不可访问
- **THEN** 后端返回 404
- **AND** 响应不包含该键对应操作的 fingerprint、状态或正文

### Requirement: 目标 VPC 前置部署证明与失效规则

后端 SHALL 以当前有效对象配置版本、最近相关变更与足够新观测判定目标 Leaf 是否已部署该 VPC。后续 `delete`、`gateway_delete`、失败 `redeploy` 或部分失败 SHALL 使前置部署失效或置为未知；证据不足 SHALL 返回 unknown/blocker，SHALL NOT 静默放行或自动全网部署。仅 DB 记录存在 SHALL NOT 证明设备侧 VSI/L3VNI/Vsi-interface 当前健康。

#### Scenario: create 成功后 delete 成功使前置部署失效

- **WHEN** 目标 Leaf 曾成功 `create` 该 VPC
- **AND** 之后该 Leaf 成功 `delete` 该 VPC
- **THEN** 终端接入被判定为缺少前置部署并阻塞
- **AND** 不创建端口绑定或下发

### Requirement: 服务端预览计划与指纹

后端 SHALL 持久化服务端预览计划记录（含服务端计算的归一化语义指纹、目标范围、版本、有效期与不可由客户端替换的 plan_id）。执行 SHALL 以 plan_id 绑定用户确认的计划，并据当前服务端状态重算指纹比对；不一致 SHALL 拒绝并要求重新预览。

#### Scenario: 服务端指纹不一致拒绝执行

- **WHEN** 用户携带 plan_id 执行终端接入
- **AND** 服务端据当前状态重算的指纹与计划记录不一致
- **THEN** 后端返回计划失效及原因，不执行
- **AND** 不按客户端提供的过期计划下发

### Requirement: 验证 attempt 因果窗口

后端 SHALL 为每次执行与验证保留稳定 attempt 标识、开始/完成时间、对象范围、配置版本与结果关联。验证证据 SHALL 断言采集开始时间不早于被验证配置的完成/回读时间；缓存 SHALL 仅作为带时效历史信息，SHALL NOT 回填成新的已验证事实或覆写原操作证据归属。

#### Scenario: 变更前缓存不能作为新验证事实

- **WHEN** 一次验证引用的快照采集开始时间早于本次配置完成时间
- **THEN** 后端判定该证据不成立并发起新采集
- **AND** 不把旧缓存标注为本次操作的新鲜验证

### Requirement: 撤回所有权与版本检查

后端 SHALL 用不可覆盖的创建所有者标识绑定来源，并以独立版本号记录后续变更者。撤回 SHALL 仅允许所有者撤回本次新建且版本未变、无后续新引用的绑定；仅读取 / 验证 SHALL NOT 改变版本或阻止合法撤回。撤回前 SHALL 原子认领并做版本检查；解绑成功但回读失败 SHALL 返回未知待对账；重复撤回 SHALL 幂等；部分解绑结果不明 SHALL NOT 自动补回或扩大为删除 VPC。

#### Scenario: 仅读取不阻止合法撤回

- **WHEN** 某操作 O 创建了绑定 B
- **AND** 另一操作仅读取 / 验证过 B 而未改变它
- **THEN** O 撤回 B 不被该读取阻止
- **AND** 版本号未因读取而改变

### Requirement: 终端读取视图

后端 SHALL 组合 expected_host_ip（用户期望）、当前带 scope/source/timestamp 的 ARP/MAC/EVPN 观测与端口绑定形成终端读取视图，逐条标注 intent / observation / inferred；SHALL NOT 把期望地址冒充已观察主机，SHALL NOT 把远端 Type-2 无依据挂成本地物理端口。

#### Scenario: 期望地址与观测分离

- **WHEN** 终端读取视图返回某 VPC 的接入情况
- **THEN** expected_host_ip 标注为 intent，不当作已观察主机
- **AND** 观测记录标注来源设备与采集时刻，远端 Type-2 不挂成本地物理端口

### Requirement: 操作历史身份快照

后端 SHALL 用非级联的证据表保留历史：`sdn_operations` 无公开删除路径、永久保留；`sdn_attempts`/`sdn_attempt_units` 仅从 `sdn_operations`/`sdn_attempts` 级联（operation 永不删，级联安全），且不建指向 tenant/VPC/绑定/设备的外键。`sdn_identity_snapshots` 记录父对象与受影响后代的身份快照；父硬删除 SHALL 先写身份快照并把操作历史所需 validation/config 证据复制进 attempt/unit 证据，再执行级联删除。设备删除发生在 ctrl，SHALL 由操作的 scope 快照保留身份。

#### Scenario: 父对象删除后历史仍可追溯

- **WHEN** 某 VPC 被删除并级联删除其绑定 / 下发 / 快照
- **THEN** 既有操作 / 尝试 / 单元记录仍保留（非级联），并可通过身份快照显示该 VPC 的已删除身份
- **AND** 历史过程不因级联删除而丢失

### Requirement: 迁移列级幂等

后端 SDN 迁移 SHALL 使用列级幂等守卫（无表建表、缺列加列、缺索引补索引），SHALL NOT 因表已存在而跳过后续缺失列 / 索引的修复。

#### Scenario: 旧库仅补缺失列

- **WHEN** 一个已应用 007-011 的旧数据库执行 012 迁移
- **THEN** 012 为既有表补充缺失的新列与索引
- **AND** 不因 `sdn_operations` 或既有表已存在而跳过列修复

### Requirement: 操作解释投影（只读，PULSE/STRATA 消费，S1-026）

后端 SHALL 在 operation detail 响应中提供只读、additive 的 `explanation` 投影，保留全部既有字段与原始 `scope`/`evidence` 原样返回。投影 SHALL 是 serializer 纯函数层，不新增表、不迁移、不改 apply/validate/withdraw/reconcile 行为；解释失败 SHALL NOT 让接口 500，而 SHALL 返回明确的 unavailable 降级标记。operation 级 SHALL 至少含 `intent`（稳定 code）、`scope_summary`、`safety_boundary`（含 target 与 claims 是否歧义）、`truth_state`、`headline`；attempt 级 SHALL 含 `explanation`（动作种类、结果、是否已完成、是否仍不确定、证据形态）；unit 级 SHALL 含 `explanation`（至少 `category`/`statement`/`truth_kind`/`source`/`scope`/`observed_at`/`freshness`，`truth_kind` ∈ `desired|observed|inferred|pending`）。无法从真实数据证明的字段 SHALL 为 null，禁止编造；`succeeded` 单元若无观察证据 SHALL 只表达「执行记录成功」，SHALL NOT 冒充「设备已验证成功」。中文展示 SHALL NOT 固化在后端：后端只返回稳定 code/事实字段与简短、语言中性的 fallback statement，具体中文由前端 i18n 完成。

#### Scenario: 执行记录成功不被冒充设备验证成功

- **WHEN** 一个 execute attempt 的所有单元 `succeeded` 且无观察证据，且不存在确定完成的 validate attempt
- **THEN** operation `truth_state` 为 `succeeded_recorded`（而非 verified），单元 `truth_kind` 为 `desired`、category 为 `execution_record`
- **AND** 响应仍原样返回原始 `scope` 与单元 `evidence`，未移除或改写

#### Scenario: 设备验证成功与未知/证据不足的区别

- **WHEN** 存在确定完成的 validate attempt（四维证据）且 operation `succeeded`
- **THEN** operation `truth_state` 为 `verified`，claims 不标歧义
- **AND** 当 operation 为 `unknown` 或存在 stale takeover / insufficient 证据时，`safety_boundary.ambiguous_claims` 为 true

#### Scenario: 解释失败与畸形证据稳定降级

- **WHEN** evidence 为空、畸形 JSON 或 legacy operation 缺少 scope
- **THEN** 投影对无法证明的字段返回 null、truth_kind 归为 pending，接口不 500、既有响应字段不变化

### Requirement: VPC 目标态 / 观测态 / 差异投影（只读，STRATA 消费，S2-001）

后端 SHALL 提供单一只读 API `GET /api/sdn/vpcs/{vpc_id}/state-projection`，复用现有 VPC/deployment/binding/validation snapshot 与设备 `sdn_role`，不新增执行器、不新增采集命令、不引入图数据库。响应 SHALL 含 VPC 稳定身份与版本、每台合格 EVPN Leaf（`sdn_role=evpn_leaf`）的稳定身份；对每台 Leaf 返回 `desired`（VPC/VSI/VSI-interface/L3VNI/端口绑定摘要 + 来源记录 kind/id/version）、`observed`（最新快照中可证明的结构化事实 + snapshot id + 采集完成时间）、`diff`（逐维 `aligned|drifted|unknown|stale|not_applicable` + 稳定 reason code）。聚合状态 SHALL NOT 覆盖逐维事实；非 EVPN Leaf SHALL NOT 进入可操作目标集合（仅作明确 excluded/unsupported 历史残留），不混入健康分母。

#### Scenario: 无快照 → unknown

- **WHEN** VPC 在合格 Leaf 上没有任何验证快照
- **THEN** 各维 diff 均为 `unknown`（reason=no_snapshot），聚合为 unknown

#### Scenario: 快照超过 TTL → stale

- **WHEN** 最新快照采集完成时间距今超过 600s
- **THEN** 可观测各维 diff 为 `stale`（reason=snapshot_stale），不因内容匹配而谎报 aligned

#### Scenario: 命令失败或缺失 → unknown，不 drift

- **WHEN** 快照中某命令 `success != true` 或缺失
- **THEN** 依赖该命令的维为 `unknown`（采不到），绝不降级为 `drifted`

#### Scenario: 明确偏差仅落在偏差维

- **WHEN** VSI 存在但 l3-vni 在 VSI-interface 配置中缺失
- **THEN** l3_vni 维为 `drifted`，vsi / vsi_interface 仍为 aligned；聚合为 drifted 但逐维事实不被覆盖

#### Scenario: 非 EVPN Leaf 排除

- **WHEN** 某设备在本 VPC 有历史 deployment/binding/snapshot 但 `sdn_role != evpn_leaf`
- **THEN** 该设备进入 excluded（reason=not_evpn_leaf），不进入 leaves、不进健康分母

#### Scenario: 只读无副作用

- **WHEN** 调用该 GET 接口
- **THEN** 不触发 SSH/NETCONF、不写库、不刷新时间戳、不新增快照/binding/deployment

#### Scenario: 目标态由生命周期记录证明（CR47）

- **WHEN** 每台设备有 create/delete deployment 与 binding 的 action/status/version/时间顺序记录
- **THEN** 成功且当前版本有效的 create 表示基础对象期望存在；后续成功 delete 表示期望不存在；pending/failed/unknown 历史不覆盖最后一个确定结果；仅历史 snapshot 的设备为 observation-only（desired 不武断 present，diff 不制造 drift）；基础对象已 delete 但仍有 operable binding 时标 unknown/conflict，不凭空选一边；响应保留来源 deployment id/version/action/status

#### Scenario: 多值接口配置按成员关系比较（CR48）

- **WHEN** 端口接口含多个 service-instance / access-vlan
- **THEN** 以「目标值是否精确属于观测集合」判定，观测值按有序列表返回；目标值不是第一个但存在 → aligned，确实缺失 → drifted

#### Scenario: 配置 token 精确匹配（CR49）

- **WHEN** l3-vni / Vsi-interface 编号 / VSI 名可能前缀串扰（如 3000 vs 30000、Vsi-interface1 vs Vsi-interface10）
- **THEN** 用行首/词边界精确匹配；命令成功但目标 token 确实不存在才是 drift，命令失败/缺失仍是 unknown

#### Scenario: L2 与 L3 网关生命周期独立

- **WHEN** 完整 VPC 已部署后成功执行 `gateway_delete`，或只执行局部 `vsi-l3 create`
- **THEN** 前者只把 VSI-interface/L3VNI 的目标态改为 absent、保留 L2 VSI 目标态；后者只证明网关目标态 present，不得冒充整套 L2 VSI 已部署

#### Scenario: CLI 错误正文或损坏快照不是漂移

- **WHEN** 命令传输成功但正文包含 H3C CLI 错误，或快照记录存在但载荷不可读
- **THEN** 对应维度为 unknown/evidence_missing，不得判成配置缺失，也不得冒充从未采集

#### Scenario: 逐维差异证据指针（S2-003）

- **WHEN** 每个可比较维度的 diff 附带 evidence 指针
- **THEN** `desired_source` 复用 deployment/binding/operable_binding_count 来源（无可证明目标为 null），`observed_source` 在有快照记录时含 `{kind=snapshot, snapshot_id, collected_at, command}`（无快照为 null）；仅含稳定元数据与 display 命令名，绝不回传原始 CLI output/error/凭据；命令失败/快照畸形/stale/not_applicable/lifecycle conflict 仍保留能诚实证明的指针，且不改变既有状态、reason、聚合或生命周期语义

#### Scenario: 设备快照时间线（S2-004）

- **WHEN** STRATA 查询 `GET /api/sdn/vpcs/{vpc_id}/state-projection/history`（`device_id` 可选，`limit` 默认 10、1..50）
- **THEN** 每台 evpn_leaf 返回按 snapshot id/采集时间倒序的 points（非 EVPN 仅 excluded、不进聚合）；每个点至少含 snapshot_id/collected_at/validation_result，以及复用纯函数得到的 aggregate 与逐维 diff，desired 标记 `basis=current_target`（复用当前 deployment/binding 生命周期），明确是「历史设备快照 vs 当前目标态」而非历史目标态；快照 JSON 损坏/命令失败/时间缺失诚实降级 unknown/evidence_missing，不跳过坏点、不改写快照；端点零 SSH/NETCONF、零写库、零刷新时间戳，响应只保留 S2-003 脱敏 evidence 指针

#### Scenario: 历史快照 × 操作/尝试关联（S2-006）

- **WHEN** 历史时间线每个 point 附带 correlation（快照自带的 operation_id/attempt_id + 状态 linked/unlinked/missing/mismatch）
- **THEN** 仅当 operation 存在且其 vpc_id/device_id 与当前时间线一致时返回脱敏 operation 摘要（id/operation_type/status/expected_host_ip/created_at/updated_at），仅当 attempt 存在、属于该 operation 且与快照引用一致时返回脱敏 attempt 摘要（id/kind/status/started_at/completed_at）；dangling 引用、attempt 属于另一 operation、operation 属于另一 VPC/设备不得错误关联，保留快照点并以 missing/mismatch 表达；零引用为 unlinked；不返回 request_payload_json/scope_json/idempotency_key/fingerprint/owner/evidence_json/凭据；correlation 只表达「证据归属/时间相关」，不宣称操作导致状态变化

#### Scenario: 多对象变更影响投影（S2-008）

- **WHEN** STRATA/NEXT PULSE 查询 `GET /api/sdn/operations/{id}`（既有 additive `explanation` 之下的 `explanation.impact`，顶层无影子字段）
- **THEN** impact 至少含：稳定对象节点（VPC/目标 EVPN Leaf/目标接口/期望主机，仅持久化字段出现、缺失为 null、接口为 device identity + if_index 稳定复合身份且 scope 缺 device 不编造全局身份、稳定 kind/id/label/truth_kind/source、名称不充当唯一身份，source 如实区分 operation_scope/operation_record）；稳定业务范围关系（vpc targets device / device exposes interface；interface→host 按操作类型取 expects|withdraws，不得称为真实物理邻接、实时转发路径或因果链，legacy 无法证明不编造）；按 attempt/unit 真实持久化顺序的变更项（attempt_id/kind、unit_index/unit_name/state + 复用 explanation 的 truth_kind/source/statement）；safety 明确 target_only、ambiguous_claims、共享 VPC/网关不属于 terminal access/withdraw 操作目标（既有受控边界）、无法证明的 protected list 仍为 null；truth 复用 sdn_explanation 同一判定（execute succeeded 无回读仍 desired/recorded，validate readback 才 observed，unknown 诚实保留）；legacy/畸形/字段缺失稳定降级不 500，explanation 或 impact builder 异常时 detail 仍 200 且 explanation.impact 明确 unavailable；只读零 DB 写、零 SSH/NETCONF、零隐式采集，不回传凭据/raw/owner/fingerprint/idempotency key

#### Scenario: 快照状态转变投影（S2-010）

- **WHEN** STRATA 查询 `GET /api/sdn/vpcs/{vpc_id}/state-projection/history`（每个历史点新增 `transition_from_prior`，既有字段保持兼容）
- **THEN** 每个较新的点与紧邻的较旧点比较同一 Leaf、同一 `current_target` 基准下的逐维状态转变，并携带 from/to snapshot_id 与 collected_at；窗口最旧点明确 `baseline_unavailable`，不得拿窗口外状态或当前实时状态补造基线；固定维度 `vsi`/`vsi_up`/`vsi_interface`/`l3_vni` 与按数据库整数 `binding_id` 稳定匹配的 `service_instance`/`access_vlan`，每项至少含 dimension key、from/to status、from/to reason_code、transition kind；kind 用语言中性稳定枚举且保守：`unchanged`、`drift_detected`、`drift_cleared`、`evidence_gained`、`evidence_lost`、`state_changed`、`baseline_unavailable`——drifted→unknown/stale 只能 `evidence_lost`（不得称 drift_cleared）、unknown/stale→drifted 只能 `drift_detected`、not_applicable 的变化按 `state_changed`；每 transition 给出脱敏 summary（changed_dimensions + 按 kind counts），不返回原始 CLI output/error/凭据；这仅是证据状态转变，不是根因/物理拓扑/转发路径，不证明关联 operation 导致了变化；只读零 DB 写、零 SSH/NETCONF、零隐式采集、无迁移、无新 endpoint

#### Scenario: VPC EVPN Leaf 范围覆盖投影（S2-012）

- **WHEN** STRATA 查询 `GET /api/sdn/vpcs/{vpc_id}/state-projection`（顶层 additive 增加 `scope`，既有 `leaves/excluded/aggregate` 行为不变）
- **THEN** scope 枚举当前数据库全部 `sdn_role=evpn_leaf` 设备（不按名称/platform 推断），每个 member 只返回稳定白名单 device_id/name/host、classification、reason_code、record_sources（deployment/binding/snapshot 存在与计数）、desired_base_state、desired_binding_count，不回传凭据/protected_interfaces/原始配置或快照；classification 保守稳定——`targeted`（当前版本生命周期可证明 base present，或存在 planned/active/expanding 当前目标绑定）、`withdrawn`（生命周期可证明 base absent 且无当前目标绑定）、`not_targeted`（无任何记录）、`ambiguous`（有历史记录但当前生命周期不能证明 present/absent 且无当前目标绑定）；snapshot 单独不能证明 targeted、历史成功 create 版本不匹配仍 ambiguous、failed/pending 不覆盖确定生命周期、局部 gateway_delete 不改变 base 范围；summary 给 eligible/targeted/withdrawn/not_targeted/ambiguous counts 且只计 EVPN Leaf（非 EVPN 继续只走既有 excluded 不混入分母；无 EVPN Leaf 时 counts 全 0）；范围不是健康度，未覆盖不得自动冒充故障或漂移；只读零 DB 写、零 SSH/NETCONF、零隐式采集、无迁移、无新 endpoint

#### Scenario: VPC 范围例外管理（S2-014）

- **WHEN** 用户记录某台 EVPN Leaf 对某 VPC 的范围例外（PUT `scope-exception`），或读取/清除（GET 列表 / DELETE）
- **THEN** 例外类型仅 `intentional_exclusion`（有意不纳入）与 `maintenance_pause`（维护暂停），reason 非空且长度受限、可选 `expires_at`（必须晚于当前时间）、记录创建/更新与版本；同一 VPC+device 至多一条当前记录（数据库唯一约束）；仅当前存在且 `_is_sdn_fabric_member` 认可的 EVPN Leaf 可设置例外（VPC/设备不存在按既有 404 语义、非成员明确拒绝，不按名称/platform 推断）；清除=直接删除该行且不级联 operation/deployment/snapshot 历史；过期例外在读取时明确 `state=expired`（不自动删除、不写库），有效为 active，时间全部 ISO；写操作只改数据库——零 SSH/NETCONF、零配置下发、零状态采集、零隐式部署/撤回；API 响应不含设备凭据、原始配置、快照或内部 owner/fingerprint
- **WHEN** STRATA 读取 `GET /api/sdn/vpcs/{id}/state-projection`
- **THEN** 既有 `scope.members[].classification`、reason_code、desired_base_state 与 aggregate/leaves/excluded 事实语义不变；仅 additive 增加白名单 `exception`（无例外为 null）及 summary 的 `active_exception` 计数；例外不得把 not_targeted 改成 targeted、不得把 drifted 改成 aligned、不得从 scope 分母移除设备；畸形历史数据保守降级，state-projection 不 500

#### Scenario: VPC 范围例外管理（S2-014-R1 复审返工增补）

- **WHEN** 父 VPC/device 被删除，或范围例外子行被清除
- **THEN** vpc_id/device_id 指向 `sdn_vpcs.id`/`devices.id`（FK ondelete=CASCADE 声明）；父删除后例外子行经项目 ORM relationship cascade 清理（不留 orphan），删除例外子行不向上级联父对象与 operation/deployment/snapshot 历史
- **WHEN** `expires_at` 携带时区（标准 Z 或 ±HH:MM offset）或无时区 ISO
- **THEN** 统一换算为 UTC naive 存储（与项目 DateTime 一致）且序列化稳定；过去时间仍明确拒绝
- **WHEN** 历史数据畸形（非法 exception_type、空/超长 reason、非 datetime expires_at、非法/缺失 version）
- **THEN** 序列化稳定返回脱敏白名单且 `state=invalid`，绝不 active、绝不计入 active_exception、绝不 500；数据库 CHECK 约束阻止新脏数据；有效（active）/过期（expired）旧语义不变
