# SDN Workbench Increment

## ADDED Requirements

### Requirement: VPC business context
The UI SHALL present one selected VPC with its known bindings, operations, validations and host observations without inventing missing relationships.

#### Scenario: Missing observation
- **WHEN** no scoped host observation exists
- **THEN** the UI shows an unknown or not-yet-observed state instead of a healthy terminal

### Requirement: Preview before terminal access
The UI SHALL call the server preview endpoint before execution and SHALL NOT execute while blocking items exist.

#### Scenario: Preview blocked
- **WHEN** the server returns one or more blocking items
- **THEN** the UI explains each blocker and does not enable confirmation

### Requirement: Resumable operation
The UI SHALL render persisted operation status and attempts and provide only actions valid for the current state.

#### Scenario: Refresh during wiring
- **WHEN** the page reloads while an operation awaits validation
- **THEN** the same operation remains visible and can continue to validation without creating another binding

### Requirement: Controlled withdrawal
The UI SHALL describe and invoke operation-scoped withdrawal without implying that the VPC, gateway or unrelated ports are removed.

#### Scenario: Scope exception is explicit business context

- **WHEN** a user opens an eligible EVPN Leaf from VPC coverage and creates, edits, or clears an intentional exclusion or maintenance pause
- **THEN** reason is required, expiry is optional, active/expired/invalid context is visible, and the UI explicitly states that the action neither configures devices nor hides drift nor changes coverage facts

#### Scenario: Attention items lead to evidence, not automatic remediation

- **WHEN** STRATA receives additive VPC attention items
- **THEN** it presents backend severity, category, target Leaf and recommended navigation in stable order; actions only inspect differences, explicitly refresh evidence, or open scope context, while the UI states that the queue is neither root-cause proof nor automatic remediation

#### Scenario: Withdraw completed access
- **WHEN** the user confirms withdrawal
- **THEN** the UI displays the returned withdrawn binding and retained shared resources

### Requirement: Accessible responsive layout
The UI SHALL keep IP addresses, interface names, status text and primary actions readable at desktop and 390px widths.

#### Scenario: Narrow viewport
- **WHEN** the viewport is 390px wide
- **THEN** regions stack without text overlap or requiring whole-page zoom-out

### Requirement: Real application-stack integration channel
The change SHALL provide a repeatable, isolated integration channel that exercises the real backend application (FastAPI + routes + isolated database), a real frontend build/dev server, and a browser, with synthetic data only and no production database, credentials, resident containers, or docker.sock. Device execution and collection SHALL be replaced at the explicit boundary by fakes, with an assertion proving no real device I/O occurred, and the channel SHALL NOT mock the whole HTTP API or reuse a previous mock backend.

#### Scenario: Full access story over the real stack
- **WHEN** the isolated channel runs the workbench against the real backend and synthetic EVPN Leaf/tenant/deployed VPC data
- **THEN** the user can select the existing VPC, choose a legal Leaf and business port, preview server-side, execute without device write, reopen the persisted operation, and see PULSE intent/scope/safety plus per-unit truth kind while STRATA keeps the same context

#### Scenario: Honest state when readback is absent or insufficient
- **WHEN** execution is recorded successfully but no device readback exists, or validation evidence is insufficient
- **THEN** the UI shows the record as not device-verified (desired/execution_record), or keeps the operation unknown/ambiguous with ambiguous claims, and never presents execution success as device-verified

#### Scenario: Cleanup and port isolation
- **WHEN** the channel succeeds, fails, or is interrupted
- **THEN** processes, ports, the database, and temporary files can be cleaned; port conflicts fail explicitly or use an isolated port, and the channel never connects to the demo environment

#### Scenario: S2 user stories over the real stack (S2-018)
- **WHEN** the isolated channel seeds two EVPN leaves (one targeted, one not targeted) and one non-EVPN device for the same VPC, and the browser opens STRATA against the real backend
- **THEN** the coverage is shown as 1/2 with per-leaf classification (targeted / not targeted), the non-EVPN device is excluded from the scope denominator, and the attention panel shows coverage_gap without labeling it as drift
- **WHEN** the user opens the scope exception for the uncovered leaf, sets maintenance_pause with a reason and a future expiry, and saves
- **THEN** the real PUT persists the exception: the leaf stays not_targeted, the exception is active, active_exception increases by one, attention changes from coverage_gap to coverage_deferred, and no deployment/binding/snapshot row and no fake device-I/O call are added
- **WHEN** the user clears the exception
- **THEN** the real DELETE removes the row, attention returns to coverage_gap, and parent objects and history are unaffected
- **WHEN** a targeted leaf has a real persisted snapshot that makes it drifted and then receives an active maintenance exception
- **THEN** attention keeps confirmed_drift as blocking with the exception attached, and the deferred coverage does not swallow the drift
- **WHEN** the browser shows the scope-exception modal and the attention panel
- **THEN** the fixed copy states the action does not push config to the device, does not hide drift, and that the attention queue is not root cause and does not auto-fix
