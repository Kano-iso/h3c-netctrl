## ADDED Requirements

### Requirement: VPC Deployment Withdraw Actions

The SDN backend MUST support deployment actions beyond initial VPC creation:

- `delete`: withdraw one VPC from one device using the VPC delete template.
- `gateway_delete`: withdraw only the VPC L3 gateway from one device by deleting the Vsi-interface unit.
- `port_bind`: bind one device interface to one VPC.
- `port_unbind`: remove one device interface binding from one VPC.

#### Scenario: Whole VPC withdraw is executable

- **WHEN** a pending deployment has action `delete`
- **AND** its planned config contains valid template units
- **THEN** applying the deployment executes the units through the platform-specific channel
- **AND** marks the deployment `success` when all units succeed
- **AND** marks the VPC status `withdrawn`

#### Scenario: Gateway-only withdraw does not delete L2 units

- **WHEN** a user requests gateway withdraw for one VPC on one device
- **THEN** the backend creates a `gateway_delete` deployment
- **AND** the planned config contains only the `vsi-l3` unit
- **AND** no `vsi-l2` or `evpn` unit is included

### Requirement: Port Binding Lifecycle API

The SDN backend MUST expose port binding operations from a VPC/user perspective:

- Create a port binding record for `{device_id, vpc_id, if_index, interface_name}`.
- List and read port bindings.
- Generate a `port_bind` deployment for a binding.
- Generate a `port_unbind` deployment for a binding.
- Reject binding to a protected interface.
- Reject duplicate active/planned bindings on the same device interface.

#### Scenario: Port bind deployment references binding

- **WHEN** a user creates a port binding and requests deploy
- **THEN** the backend creates a deployment with action `port_bind`
- **AND** the deployment references `port_binding_id`
- **AND** successful apply marks the binding `active`

#### Scenario: Port unbind deployment updates binding state

- **WHEN** a user requests undeploy for an existing binding
- **THEN** the backend creates a deployment with action `port_unbind`
- **AND** successful apply marks the binding `unbound`

