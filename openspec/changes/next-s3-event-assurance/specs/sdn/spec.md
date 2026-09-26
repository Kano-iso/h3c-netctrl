# VPC 事件触发保障（S3-003 后端切片）

## ADDED Requirements

### Requirement: Event-triggered read-only evaluation on persisted business events
When a VPC has assurance enabled, the backend SHALL append a trigger=event read-only
evaluation after the successful persistence of (1) a validation/sync snapshot and
(2) a scope-exception add/modify/clear. The evaluation SHALL reuse the S3-001
projection/whitelist path and SHALL NOT re-collect, not deploy, and not change
vpc.version or deployment/binding/operation/snapshot/claim rows. A VPC with no policy
or with enabled=false SHALL produce zero event runs; cadence=manual only disables the
periodic scheduler and SHALL NOT block event checks while enabled.

#### Scenario: Snapshot sync success appends an event run
- **WHEN** a validation/sync succeeds and a snapshot is persisted for an enabled VPC
- **THEN** one trigger=event run with event_key snapshot:{snapshot_id} and status
  completed is appended with the S3-001 whitelisted summary/facts

#### Scenario: Scope-exception add/modify/clear append event runs
- **WHEN** a scope exception is added, then modified, then cleared for an enabled VPC
- **THEN** three event runs exist with keys scope-exc:{id}:v1, scope-exc:{id}:v2 and
  scope-exc:{id}:cleared

#### Scenario: Disabled or no policy yields zero event runs; manual cadence still checks
- **WHEN** the VPC has no policy or enabled=false
- **THEN** zero event runs are appended for snapshot and scope-exception events
- **AND WHEN** the policy is enabled with cadence=manual
- **THEN** event checks still run

### Requirement: Deduplicated history via stable event_key
The runs table SHALL carry a nullable event_key carrying only stable internal ids/versions
(never credentials or raw CLI), and a DB named unique index SHALL reject duplicate event
keys (manual/scheduled runs with NULL event_key are unaffected). Retrying the same source
event SHALL NOT duplicate history, including failed event runs.

#### Scenario: Same source event retry dedups
- **WHEN** the same source event (same snapshot id, same exception id+version, or same
  cleared id) is recorded a second time
- **THEN** the unique index rejects the duplicate and only one event run remains

#### Scenario: Event keys carry no secrets
- **WHEN** event runs are serialized
- **THEN** event_key values contain only internal ids/versions (snapshot:... /
  scope-exc:...), never credentials, passwords, or raw CLI text

### Requirement: Evaluation failure does not break the source event
After the business event has committed, an evaluation failure SHALL NOT roll back or fake
the business event's success: the API stays successful, a status=failed event run with the
error is appended for audit, and the hook never raises to the caller. Zero extra device I/O
and zero business side effects SHALL hold for the event path.

#### Scenario: Eval failure appends a failed run and keeps business intact
- **WHEN** evaluation raises after a successful snapshot sync
- **THEN** the sync response is still success, one status=failed event run (event_key
  snapshot:{id}, error recorded, overall not faked) is appended, and vpc.version and
  business-table counts are unchanged

#### Scenario: Event path performs no device I/O or business writes
- **WHEN** event evaluations run
- **THEN** no collector/executor/Netconf/SSH call is made and no
  deployment/binding/operation/snapshot/claim row and no vpc.version change occurs

### Requirement: Idempotent migration 016
Migration 016 SHALL add the nullable event_key column and the named unique index
uq_sdn_assurance_runs_event_key (same name the ORM produces), be a no-op on repeat
upgrades, preserve existing runs, allow multiple NULL event_key runs, and reverse on
downgrade (index dropped, column removed, 015 schema preserved).

#### Scenario: 015-era database upgrades, dedups, and downgrades
- **WHEN** migration 016 runs on a 015-era database, a duplicate event_key insert is
  attempted, and the migration is then downgraded
- **THEN** the column and index exist with ORM-consistent naming, duplicate event_key is
  rejected while multiple NULL event_key runs coexist, a second upgrade is a no-op, and
  the downgrade removes the column and index while keeping slot_key/error and the CR61
  index
