# Design

## 1. 数据模型（`app/models.py`）

### SdnAssurancePolicy（每 VPC 至多一条）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | Integer PK | autoincrement | |
| vpc_id | Integer FK sdn_vpcs.id | ondelete=CASCADE, unique | 至多一条策略（具名唯一索引 `uq_sdn_assurance_policies_vpc`） |
| enabled | Boolean | default False | 自动保障开关（本包只记录） |
| cadence | String(10) | default 'manual' | CHECK ∈ ('manual','10m','30m','1h')；只记录产品意图，本包无 scheduler |
| response_mode | String(20) | default 'observe_only' | CHECK = 'observe_only'（本包固定） |
| version | Integer | default 1 | 乐观并发；PUT 必须携带当前版本 |
| created_at / updated_at | DateTime | server_default now | |

父 VPC 删除 → ORM relationship cascade（项目既有 SQLite 级联方式，与
SdnVpc.port_bindings/scope_exceptions 一致）；删除子行不会向上级联父对象。

### SdnAssuranceRun（追加式评估历史）

| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | Integer PK | | |
| vpc_id | Integer FK | ondelete=CASCADE, index | |
| trigger | String(10) | CHECK ∈ ('manual','scheduled','event') | 写接口只允许 manual |
| status | String(20) | CHECK ∈ ('started','completed') | 本包恒 completed |
| started_at / completed_at | DateTime | started 必填 | |
| policy_version / policy_enabled | Int/Bool | default 0 / False | 评估时策略快照（无策略=0/False） |
| facts_json / summary_json / items_json | Text | 白名单快照 | 不含原始配置/CLI/凭据/error |

并发两次 manual run = 追加两条独立行，互不覆盖（无唯一冲突路径）。

## 2. 评估语义（`app/services/sdn_assurance.py`，纯函数）

- 输入：`build_projection_payload` 的同一次 state projection/attention 载荷（复用
  S2 契约，不重新推断设备事实）。
- `overall`：
  1. 存在 blocking 项 → `blocked`（confirmed_drift / scope_uncertain / exception_invalid）；
  2. 否则 scope eligible == 0 → `insufficient_evidence`（无可评估对象，不能断言 healthy）；
  3. 否则全部项均为 evidence_missing_or_stale → `insufficient_evidence`（有对象但没有足够新鲜证据）；
  4. 否则存在项 → `attention`（review/deferred）；
  5. 否则 → `healthy`。
- 逐项：白名单字段 `{key, vpc_id, device_id, name, host, severity, category,
  source_refs, exception, recommendation}`；`recommendation` 由 category 确定性映射：
  coverage_gap→review_scope、evidence_missing_or_stale→refresh_evidence、
  confirmed_drift→inspect_drift、scope_uncertain→resolve_ambiguity、
  exception_expired→refresh_evidence、exception_invalid→repair_context、
  coverage_deferred→review_exception。
- 例外边界：active maintenance exception 把 coverage gap 保持 deferred（不升级
  blocking），但 confirmed_drift blocking 不被吞掉且携带 exception（沿用 S2-016 矩阵）。
- policy disabled 不改变评估语义，run 明确记录 `policy_enabled=false`。

## 3. API（`app/routers/sdn_assurance.py`，prefix `/api/sdn`）

| 方法/路径 | 语义 |
|---|---|
| GET `/vpcs/{vpc_id}/assurance-policy` | 缺失 → 默认值 {enabled:false, cadence:'manual', response_mode:'observe_only', version:0}，**不写库** |
| PUT `/vpcs/{vpc_id}/assurance-policy` | 校验 enabled/cadence/response_mode/version；缺失=0 → 创建 v1；更新使用 id+version 单条原子 CAS，零行即 `sdn.assurance_policy_version_conflict`，禁止并发覆盖 |
| POST `/vpcs/{vpc_id}/assurance-runs` | trigger 仅 manual；同一次 projection 事实 → 持久化一条 run；零设备 I/O/零业务写副作用 |
| GET `/vpcs/{vpc_id}/assurance-runs?limit=&before=` | 稳定游标分页（id 降序，limit 上限 100，before=上一页最后 run_id） |
| GET `/vpcs/{vpc_id}/assurance-runs/{run_id}` | 白名单详情；不属于该 VPC → `sdn.assurance_run_not_found` |

新增 i18n error keys（均注册 FALLBACK_MESSAGES）：assurance_policy_version_conflict /
assurance_invalid_policy / assurance_invalid_cadence / assurance_invalid_response_mode /
assurance_invalid_trigger / assurance_run_not_found。

## 4. 投影复用（`app/routers/sdn.py` 重构）

`get_vpc_state_projection` 的载荷构建抽为模块函数
`build_projection_payload(db, vpc_id, now=None) -> Optional[dict]`（VPC 不存在 → None）；
端点与 S3 手动评估共用同一份事实。重构为行为保持（S2-001/004/012/014/016 回归全绿）。

## 5. 零设备 I/O 保证

- 新路由不 import collector/executor/Netconf/SSH；不写 deployment/binding/operation/
  snapshot/claim；不 bump vpc.version；不做后台调度。
- 测试用模块命名空间断言（无 I/O 绑定）+ 表计数不变 + version 不变三重复核。
