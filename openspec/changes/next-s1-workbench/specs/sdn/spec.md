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

