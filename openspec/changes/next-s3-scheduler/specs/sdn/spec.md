# SDN VPC 有界周期保障（S3-002 后端切片）

## ADDED Requirements

### Requirement: Persistent due/claim slots with CAS single-winner semantics
The backend SHALL keep at most one current scheduling window per VPC
(sdn_assurance_slots: slot_key, cadence, policy_version, generation,
status pending|claimed|completed|failed, due_at, claim_token, lease_expires_at,
run_id, error). Claims, completions, failures, and window advances SHALL be
conditional updates with rowcount checks (no process lock): two concurrent scheduler
ticks for the same VPC and the same due slot SHALL produce at most one completed
scheduled run, and a late arrival whose generation or claim token no longer matches
SHALL NOT overwrite the current generation. The terminal CAS SHALL additionally match
status='claimed' and clear claim_token/claimed_at/lease on success. A scheduled run
SHALL be inserted/flushed in the same transaction as its terminal CAS: when the CAS
matches 0 rows (lease taken over / generation or token changed), the run SHALL be
rolled back and no orphan or duplicate run history SHALL remain. The runs table SHALL
carry a defensive unique index on (vpc_id, slot_key) consistent between ORM and
migration 015 (SQLite NULLs stay distinct, so multiple manual runs with null slot_key
remain allowed).
The claim token returned to a worker SHALL be carried into the evaluation entry point;
before reading projection facts the worker SHALL still match generation, claimed status,
and that exact token. Owner identity SHALL remain a detached snapshot across rollback so
an expired ORM object cannot refresh to a takeover worker's token.

#### Scenario: Concurrent ticks single winner
- **WHEN** two sessions tick concurrently on the same due slot
- **THEN** exactly one completed scheduled run exists and the slot ends completed
  (or advances to the next window), never two runs for the same window

#### Scenario: Old-generation late arrival
- **WHEN** a completion carries a stale generation or stale claim token
- **THEN** the slot state is unchanged (no overwrite of the newer generation)
- **AND** when the same window was already taken over and completed, the late
  arrival's run is rolled back, leaving exactly one run for that slot_key

#### Scenario: Takeover before or during stale-owner evaluation
- **WHEN** worker A's lease is taken over before A begins projection, or while A is
  evaluating and A subsequently rolls back on an exception
- **THEN** A neither starts work with worker B's token nor finalizes B's claim
- **AND** B remains the sole owner of the claimed slot

#### Scenario: Terminal CAS is idempotent and token is cleared
- **WHEN** a slot is completed via terminal CAS
- **THEN** claim_token/claimed_at/lease_expires_at are cleared
- **AND** replaying the same-token complete, completing after failing, or using an old
  token or old generation matches 0 rows and leaves run_id/status unchanged

### Requirement: Crash and failure recovery without starvation
A claimed slot whose lease expired SHALL be takeable over by another tick (same
generation, new token); an unexpired lease SHALL NOT be taken over. A pending slot
already due after a restart SHALL be processed. An evaluation exception SHALL record
the run and the slot as failed (never faked completed/healthy) and SHALL be retryable
at the next window.

#### Scenario: Lease expiry takeover boundary
- **WHEN** a slot is claimed with a lease still valid
- **THEN** another tick cannot claim it
- **AND WHEN** the lease has expired
- **THEN** another tick can take it over

#### Scenario: Evaluation failure is honest and retryable
- **WHEN** evaluation raises during a scheduled run
- **THEN** the run is status failed with error and the slot is failed
- **AND** the next window can complete successfully

### Requirement: Shared evaluation path for manual and scheduled
Manual and scheduled runs SHALL reuse the same projection → whitelisted-persist path
(persist_assurance_run); scheduled runs SHALL carry trigger=scheduled, the auditable
slot key, policy version snapshot, and completed/failed status, with zero device I/O
and zero business side effects (no deployment/binding/operation/snapshot/claim
creation, no vpc.version bump).

#### Scenario: Scheduled run audit trail
- **WHEN** a scheduled run completes
- **THEN** it records trigger scheduled, slot_key, policy_version, completed status,
  and links back to the slot's run_id

#### Scenario: Manual API backward compatible
- **WHEN** a manual run is posted
- **THEN** it records trigger manual with slot_key null, and no slot is created

### Requirement: Lifecycle gating and shutdown
The scheduler thread SHALL start only when SERVICE_NAME is config or monolith core
(data/ctrl SHALL NOT start), be stoppable on app shutdown, poll at an
environment-configurable interval with a safe floor, and be explicitly disable-able in
tests.

#### Scenario: Service gating
- **WHEN** service_name is config or core
- **THEN** the scheduler is enabled
- **AND WHEN** service_name is data or ctrl
- **THEN** it is not enabled

#### Scenario: Thread start/stop
- **WHEN** a Scheduler is started enabled
- **THEN** it processes due slots on its own
- **AND** stop() terminates the thread

### Requirement: Policy behaviors — disabled/manual skip, cadence change, batch cap
Enabled=false and cadence=manual SHALL never be scheduled. Changing cadence SHALL
continue under the new policy without backfilling history; while a window is claimed
with a valid lease, a policy change SHALL NOT let another tick advance or steal the
generation — the owner's completion/failure lands first and a later tick advances
under the new policy. Each tick SHALL honor a bounded batch cap that counts **all**
persistent slot changes (first-slot creation, claim+eval, terminal advance,
policy-change advance), not only evaluations: with max_slots=N at most N VPCs' slots
are modified per tick, and pure read-only skips do not count. The GET policy response
SHALL expose stable read-only schedule information (schedule_status, next_due,
last_scheduled_at) without changing the existing S3-001 API.

#### Scenario: Disabled and manual are skipped
- **WHEN** a policy is disabled or cadence is manual
- **THEN** no slot and no scheduled run are created

#### Scenario: Cadence change continues without backfill
- **WHEN** cadence changes to a new value
- **THEN** the next window uses the new cadence and no historical windows are replayed

#### Scenario: Claimed-valid window is not stolen by a policy change
- **WHEN** a window is claimed with an unexpired lease and the policy cadence/version
  changes
- **THEN** the slot stays claimed with the same generation and token, no advance and no
  run happen, and after the owner finalizes the next tick advances under the new policy

#### Scenario: Batch cap counts every persistent slot change
- **WHEN** 20+ windows are due for terminal or policy-change advance with max_slots=2
- **THEN** exactly 2 VPCs' slots are modified and the other 18 stay untouched

### Requirement: Idempotent migration 015
Migration 015 SHALL create sdn_assurance_slots (named unique index, CHECK constraints),
extend sdn_assurance_runs with slot_key/error and the failed status CHECK (preserving
014 data), add the defensive unique index uq_sdn_assurance_runs_vpc_slot_key with the
same name the ORM produces, be a no-op on repeat upgrades, and reverse on downgrade.

#### Scenario: 014-era database upgrades and preserves data
- **WHEN** migration 015 runs on a 014-era database with an existing manual run
- **THEN** the slots table and extended runs schema exist, the manual run is preserved,
  status='failed' is accepted, the ORM and migration unique index names match, and a
  second upgrade is a no-op

#### Scenario: Duplicate windows and duplicate runs are rejected
- **WHEN** a second slot row for the same vpc_id or a second run with the same
  (vpc_id, slot_key) is inserted
- **THEN** it is rejected by the unique index, while two manual runs (slot_key null)
  coexist

#### Scenario: Downgrade restores the 014 schema
- **WHEN** migration 015 is downgraded
- **THEN** the slots table is dropped, sdn_assurance_runs rejects status='failed', and
  the uq_sdn_assurance_runs_vpc_slot_key index is removed
- **AND** existing failed runs are preserved as started because 014 cannot represent
  failed, never converted to completed
