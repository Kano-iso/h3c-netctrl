# SDN VPC 受限保障（S3-001 后端纵向切片）

## ADDED Requirements

### Requirement: VPC assurance policy with defaults and optimistic concurrency
The backend SHALL persist at most one assurance policy per VPC (enabled, cadence ∈
{manual,10m,30m,1h}, response_mode fixed to observe_only, optimistic version). A GET on a
VPC with no policy SHALL return the explicit default without writing to the database. A PUT
SHALL validate the payload and reject on cadence/response-mode/type errors, and SHALL accept
version 0 only when no policy exists (creating v1) and otherwise require the current version,
returning a version-conflict error without writing on mismatch.

#### Scenario: Missing policy returns defaults without writing
- **WHEN** a GET assurance-policy is issued for a VPC that has never saved a policy
- **THEN** the response is {enabled:false, cadence:'manual', response_mode:'observe_only', version:0}
- **AND** no policy row is created (GET does not implicitly write)

#### Scenario: Version conflict is rejected without writing
- **WHEN** a PUT carries a version that does not equal the current policy version
- **THEN** the response is sdn.assurance_policy_version_conflict with expected/given params
- **AND** the stored row is unchanged

#### Scenario: Invalid payload is rejected
- **WHEN** a PUT carries a cadence outside the whitelist, a response_mode other than
  observe_only, or a non-boolean enabled / non-integer version
- **THEN** the corresponding sdn.assurance_invalid_* error is returned and nothing is written

### Requirement: Read-only manual evaluation persisted as an auditable run
A POST manual evaluation SHALL derive its facts from the same single state-projection and
attention projection used by the S2 state-projection endpoint, evaluate them without
re-inferring device facts, and persist one assurance run (trigger manual, status completed)
recording policy_version/policy_enabled, a whitelisted facts snapshot, summary, and items. It
SHALL NOT call any collector/executor/Netconf/SSH, create any deployment/binding/operation/
snapshot/claim, or bump the VPC version. Policy disabled SHALL NOT prevent evaluation; the run
SHALL record policy_enabled=false. Trigger values other than manual SHALL be rejected.

#### Scenario: Manual run persists a completed run with zero side effects
- **WHEN** a POST assurance-runs with trigger manual is issued for an existing VPC
- **THEN** one completed run row is persisted with policy snapshots and whitelisted facts/items
- **AND** no deployment, binding, operation, snapshot, or claim row is created
- **AND** the VPC version is unchanged and no device-I/O client is reachable from the route

#### Scenario: Non-manual trigger is rejected
- **WHEN** a POST assurance-runs carries trigger scheduled or event
- **THEN** sdn.assurance_invalid_trigger is returned and no run is persisted

#### Scenario: Disabled policy still allows a manual run
- **WHEN** a manual run is posted for a VPC with no policy (equivalent disabled)
- **THEN** the run succeeds and explicitly records policy_enabled=false, policy_version=0

### Requirement: Deterministic overall outcomes from S2 facts
The evaluation SHALL map the S2 attention items to an overall of healthy / attention /
blocked / insufficient_evidence with this precedence: any blocking item → blocked; no eligible
EVPN Leaf → insufficient_evidence; only evidence_missing_or_stale items → insufficient_evidence;
any other item → attention; otherwise healthy. Each item SHALL
carry a whitelisted shape {key, vpc_id, device_id, name, host, severity, category,
source_refs, exception, recommendation} where recommendation is a deterministic code
(review_scope / refresh_evidence / inspect_drift / resolve_ambiguity / repair_context /
review_exception) that never contains device commands, auto-fix plans, or root-cause claims.

#### Scenario: Healthy
- **WHEN** every eligible EVPN Leaf is targeted and aligned with no attention items
- **THEN** overall is healthy with an empty item list

#### Scenario: Attention on coverage gap
- **WHEN** an EVPN Leaf is not targeted (coverage_gap)
- **THEN** overall is attention, the item is severity review with recommendation review_scope

#### Scenario: Blocked on confirmed drift
- **WHEN** a targeted Leaf is drifted (confirmed_drift)
- **THEN** overall is blocked, the item is severity blocking with recommendation inspect_drift

#### Scenario: Insufficient evidence
- **WHEN** no eligible EVPN Leaf exists for the VPC
- **THEN** overall is insufficient_evidence and cannot claim healthy

#### Scenario: Eligible Leaf has only missing or stale evidence
- **WHEN** eligible EVPN Leaves exist but every attention item is evidence_missing_or_stale
- **THEN** overall is insufficient_evidence with refresh_evidence recommendations, not healthy or generic attention

### Requirement: Exception boundary preserves drift facts
An active maintenance exception SHALL keep a coverage gap deferred (severity deferred,
recommendation review_exception) rather than escalating to blocking, but SHALL NOT swallow a
confirmed-drift blocking item: the blocking item stays blocking and carries the exception.

#### Scenario: Deferred gap and un-hidden drift coexist
- **WHEN** Leaf A is untargeted with an active maintenance exception and Leaf B is targeted
  and drifted with an active maintenance exception
- **THEN** Leaf A's item is coverage_deferred/deferred, Leaf B's item is
  confirmed_drift/blocking carrying the exception, and overall is blocked

### Requirement: Concurrent runs and bad-history degradation
Two concurrent manual runs for the same VPC SHALL each persist a complete, distinct run that
does not overwrite the other. A run evaluation against malformed history (invalid snapshot
JSON) SHALL still complete with a whitelisted overall and whitelisted item fields and never
raise a 500. Run list SHALL paginate stably (limit bounded, before cursor, id descending) and
detail SHALL be whitelisted with 404 semantics for runs outside the VPC.

#### Scenario: Concurrent runs both complete
- **WHEN** two manual runs are posted concurrently for the same VPC
- **THEN** two distinct completed runs exist with their own ids, summaries, and items

#### Scenario: Malformed history degrades
- **WHEN** a manual run evaluates a VPC whose latest snapshot has invalid snapshot JSON
- **THEN** the run completes with an overall in {healthy, attention, blocked,
  insufficient_evidence} and each item uses only whitelisted fields

#### Scenario: Stable pagination and detail 404
- **WHEN** run history is listed with limit and before cursors
- **THEN** runs are returned id-descending and bounded; a detail request for a run that does
  not belong to the VPC returns sdn.assurance_run_not_found

### Requirement: Idempotent migration 014
Migration 014 SHALL add sdn_assurance_policies and sdn_assurance_runs (FOREIGN KEY to
sdn_vpcs.id with ondelete CASCADE, named unique index on policy vpc_id, index on run vpc_id,
CHECK constraints for cadence/response_mode/trigger/status/version). It SHALL be repeatable on
both an empty database and a 013-era database, with a downgrade that drops both tables and
keeps the parent VPC table.

#### Scenario: 013-era database upgrades idempotently
- **WHEN** migration 014 runs on a 013-stamped skeleton database, then runs again
- **THEN** both tables, the named unique index, the run index, and CHECK constraints exist
  and a second upgrade is a no-op

#### Scenario: Empty database upgrades to head
- **WHEN** an empty database runs alembic upgrade head
- **THEN** the full chain including 014 succeeds and both assurance tables exist

#### Scenario: Downgrade drops assurance tables only
- **WHEN** migration 014 is downgraded to 013
- **THEN** sdn_assurance_policies and sdn_assurance_runs are dropped and sdn_vpcs remains

### Requirement: GUARD assurance perspective in the VPC workbench
The frontend API client SHALL expose typed, stable entry points getAssurancePolicy,
putAssurancePolicy, createAssuranceRun, listAssuranceRuns, and getAssuranceRun. The existing
VPC workbench SHALL expose a GUARD perspective in the selected VPC context, showing the latest
overall/summary, deterministic human recommendations, policy preference, and auditable run
history. It SHALL state that cadence is stored only and does not schedule execution, and SHALL
NOT present recommendations as automatic remediation.

#### Scenario: Manual evaluation is visible and remains device-read-only
- **WHEN** the user opens GUARD and selects Evaluate now
- **THEN** the real assurance API persists a completed run and the conclusion appears in history
- **AND** the device-I/O boundary records no additional call

#### Scenario: Stored cadence is not represented as a scheduler
- **WHEN** the user enables assurance and saves a cadence
- **THEN** the preference and its optimistic version are persisted
- **AND** the page explicitly says that no automatic schedule is active in this version
