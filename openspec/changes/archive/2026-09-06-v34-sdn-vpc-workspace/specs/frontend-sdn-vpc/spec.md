## ADDED Requirements

### Requirement: SDN VPC Workspace Entry

The frontend MUST expose an SDN/VPC workspace from the operations management navigation.

#### Scenario: User opens SDN VPC workspace

- **WHEN** the user opens the operations management navigation
- **THEN** an SDN/VPC entry is available
- **AND** clicking it routes to the SDN/VPC workspace page

### Requirement: VPC User Workflow

The workspace MUST support the v3.3 user-facing VPC workflow without exposing raw deployment internals as the primary entry.

#### Scenario: User manages a VPC

- **WHEN** tenants, VPCs, devices, port bindings, and deployments are returned by the backend
- **THEN** the page shows VPC inventory, selected VPC details, associated bindings, and recent deployment records
- **AND** the user can create tenants and VPCs
- **AND** the user can create deploy and withdraw change records for selected EVPN Fabric devices
- **AND** the device-apply section explains that VPC creation only stores data in the platform until a change is executed on devices

#### Scenario: User expands an existing VPC

- **WHEN** a user selects a VPC, an EVPN Fabric device, an interface, and an optional host IP
- **THEN** the page calls the existing VPC expansion API
- **AND** the user can complete validation after host cabling and IP configuration

#### Scenario: User manually enters interface identity

- **WHEN** an EVPN Fabric device is selected but its interface list is unavailable or empty
- **THEN** the interface list control may be disabled
- **AND** the user can still manually enter `if_index` and interface name before creating a binding or starting expansion

#### Scenario: Access-only devices are hidden from SDN target selectors

- **WHEN** the device list includes a device whose name contains `Leaf` or whose platform is `LSTN`/`RSTN` but whose `sdn_role` is not `evpn_leaf`
- **THEN** the workspace does not show that device in SDN deploy, withdraw, validation, or expansion target selectors
- **AND** only `sdn_role=evpn_leaf` devices are shown as EVPN Fabric targets

#### Scenario: User reads status guidance

- **WHEN** a selected VPC status is `pending`, `planned`, `active`, `degraded`, `failed`, or `withdrawn`
- **THEN** the page explains what that state means
- **AND** the guidance recommends the next user action

#### Scenario: User opens best-practice guide

- **WHEN** the user clicks the best-practice action
- **THEN** the page displays step-by-step guidance for new VPC creation, existing VPC expansion, and troubleshooting

### Requirement: Manual Validation Rhythm

The workspace MUST use manual display synchronization and latest snapshots instead of high-frequency polling.

#### Scenario: User syncs VPC validation

- **WHEN** the user selects a VPC and a device
- **AND** clicks validation sync
- **THEN** the frontend calls the validation sync endpoint
- **AND** renders the latest validation result
