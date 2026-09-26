# VPC 受控修复提案（S3-004 后端切片）

## ADDED Requirements

### Requirement: Auditable non-executing remediation proposals
The backend SHALL persist a remediation plan bound to the assurance run, the VPC version
at creation, the target Leaf and the latest evidence, without ever executing device
configuration. The plan SHALL retain VPC, assurance run, item key, device, category/action,
VPC version at creation, policy version, evidence snapshot id, status
proposed/stale/cancelled, expiry time, a stable fingerprint, a sanitized summary, and
created/updated timestamps. There SHALL be at most one proposal per run+item; cancelling or
staling history SHALL NOT cascade into a fake success of the business state.

#### Scenario: Create accepts only a real blocking confirmed_drift item from a completed run
- **WHEN** creating a proposal for a completed run item with severity=blocking and
  category=confirmed_drift and correct VPC ownership
- **THEN** a proposed plan is created with action redeploy_vpc_on_device, the server-side
  device derived from the run whitelist item (caller-supplied device/action ignored), and a
  stable fingerprint
- **AND** when the run is missing/not completed, or the item is not a blocking
  confirmed_drift item, or ownership mismatches
- **THEN** the create is explicitly rejected and no usable proposal is generated

### Requirement: Freshness gates on create and conservative stale on read
Creating a proposal SHALL re-read the current projection and require all of: VPC/run/item
ownership consistent, current VPC version equals the run facts version, target still an EVPN
Leaf and still confirmed_drift, the current latest snapshot equals the run source_refs
evidence snapshot, and no active maintenance exception. Any failure SHALL explicitly reject
or return stale. Reading a proposed plan SHALL conservatively mark it stale (short
transaction/CAS) when VPC version, latest snapshot, current classification, or exception
state changed, so it is never shown as executable.

#### Scenario: Create rejects stale or excepted state
- **WHEN** the VPC version changed, or the drift classification is gone, or the latest
  snapshot changed, or the device is no longer an EVPN Leaf, or an active maintenance
  exception exists at create time
- **THEN** create is rejected with the matching error key and no proposal is created

#### Scenario: Read marks proposed stale when state changed
- **WHEN** a proposed plan is read after the VPC version changed, or a newer snapshot
  appeared, or an active maintenance exception was added
- **THEN** the plan is conservatively marked stale via a CAS update and is no longer shown
  as executable

### Requirement: Whitelisted impact summary without raw CLI or credentials
The proposal action SHALL be fixed to redeploy_vpc_on_device and the semantic unit names and
impact scope SHALL be computed via the existing planner dry-run. Neither the API nor the DB
SHALL save or return raw CLI, credentials, or planned_config. The response SHALL list the
semantic units to rebuild, the preserved items (tenant/VPC/other leaves/port bindings not
deleted) and the boundary that execution has not happened.

#### Scenario: Response and storage expose only semantic units and boundary
- **WHEN** a proposal is created or read
- **THEN** its summary contains only unit names/descriptions and preserved items with
  executed=false, and neither the response nor the stored summary_json contains
  cli_commands/xml_payloads/system-view/credentials

### Requirement: Idempotent duplicate, cancel, and concurrency
Repeated create for the same run+item SHALL return the same proposal (DB unique constraint
backs concurrent duplicates). Cancel SHALL transition only proposed to cancelled and be
idempotent.

#### Scenario: Duplicate and concurrent create dedup
- **WHEN** the same run+item is requested twice, or concurrently by multiple sessions
- **THEN** exactly one proposal row exists and all requests return that same proposal

#### Scenario: Cancel is proposed-only and idempotent
- **WHEN** a proposed plan is cancelled once and then again
- **THEN** it transitions to cancelled exactly once and repeated cancels return the same
  cancelled plan (a cancelled plan is never resurrected or overwritten as stale)

### Requirement: Zero device I/O and zero business side effects
The proposal path SHALL not invoke executor/collector/Netconf/SSH, not create
deployment/operation/binding/claim rows, not change vpc.version, and SHALL NOT implement a
confirm/apply endpoint nor mark proposed as fixed.

#### Scenario: Proposal lifecycle keeps business state intact
- **WHEN** a proposal is created, read, and cancelled
- **THEN** deployment/binding/operation/plan/snapshot counts and vpc.version are unchanged,
  no new assurance runs exist, the planner dry-run ran exactly once, and no confirm/apply
  route exists

### Requirement: Idempotent migration 017
Migration 017 SHALL add the proposals table with its named unique index idempotently
(repeated upgrade is a no-op) and be downgradable (table dropped, 016 runs.event_key
structure preserved), with ORM/ migration index naming consistent.

#### Scenario: 016-era database upgrades, dedups, and downgrades
- **WHEN** an existing 016 database is upgraded to 017, then upgraded again, then downgraded
  to 016
- **THEN** the table and unique index exist after upgrade, duplicate (run_id, item_key) is
  rejected while different run/item combos coexist, and downgrade removes the table while
  keeping the 016 runs.event_key column and index
