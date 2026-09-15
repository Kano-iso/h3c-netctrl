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

