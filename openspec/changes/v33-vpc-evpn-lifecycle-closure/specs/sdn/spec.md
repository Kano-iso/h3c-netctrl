## ADDED Requirements

### Requirement: VPC Deployment Withdraw Actions

The SDN backend MUST support user actions beyond initial VPC creation:

- `delete`: withdraw one VPC from one device using the VPC delete template.
- `redeploy`: restore one VPC to one Leaf using a VPC `create` deployment and the saved VPC definition.
- `gateway_delete`: withdraw only the VPC L3 gateway from one device by deleting the Vsi-interface unit.
- `gateway_deploy`: restore only the VPC L3 gateway on one device using a `create` deployment with the Vsi-interface unit from the saved VPC definition.
- `port_bind`: bind one device interface to one VPC.
- `port_unbind`: remove one device interface binding from one VPC.

#### Scenario: Whole VPC withdraw is executable

- **WHEN** a pending deployment has action `delete`
- **AND** its planned config contains valid template units
- **THEN** applying the deployment executes the units through the platform-specific channel
- **AND** marks the deployment `success` when all units succeed
- **AND** marks the VPC status `withdrawn`

#### Scenario: Whole VPC withdraw does not recreate an empty VSI

- **WHEN** a VPC withdraw plan is generated
- **THEN** the EVPN/RD cleanup unit MUST run before the final VSI delete unit
- **AND** the final VSI delete unit MUST NOT be followed by commands that enter the same `vsi <name>` view
- **AND** post-withdraw device config MUST NOT retain an empty VSI shell for the withdrawn VPC

#### Scenario: Gateway-only withdraw does not delete L2 units

- **WHEN** a user requests gateway withdraw for one VPC on one device
- **THEN** the backend creates a `gateway_delete` deployment
- **AND** the planned config contains only the `vsi-l3` unit
- **AND** no `vsi-l2` or `evpn` unit is included

#### Scenario: Single Leaf VPC redeploy uses the saved VPC definition

- **WHEN** a user requests redeploy for one VPC on one Leaf
- **THEN** the backend creates a VPC `create` deployment
- **AND** the planned config contains the full VPC create unit set
- **AND** RD/VNI/gateway parameters are read from the saved VPC definition

#### Scenario: Gateway-only deploy does not recreate L2 units

- **WHEN** a user requests gateway deploy for one VPC on one Leaf
- **THEN** the backend creates a `create` deployment with unit `vsi-l3`
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

### Requirement: Existing VPC Expansion Workflow

The SDN backend MUST support adding a new access interface to an existing VPC from a user-oriented expansion workflow.

- The expansion target MUST be a Leaf device.
- The expansion MUST inherit the existing VPC CIDR, gateway, VNI, and VSI; the user MUST NOT provide a new subnet mask for the expansion.
- The expansion MAY accept an expected host IP for completion validation.
- Starting an expansion MUST create a port binding and a `port_bind` deployment.
- If the deployment is applied successfully, the port binding and VPC MUST enter `expanding`.
- Completing an expansion MUST optionally ping the expected host IP from the VPC gateway and MUST collect a display validation snapshot.
- Successful completion MUST mark the port binding and VPC `active`.
- Failed completion MUST mark the binding `failed` and the VPC `degraded`.

#### Scenario: Start expansion only accepts Leaf targets

- **WHEN** a user starts VPC expansion on a non-Leaf device
- **THEN** the backend rejects the request
- **AND** no port binding is created

#### Scenario: Start expansion enters expanding after apply

- **WHEN** a user starts VPC expansion on a Leaf device and the generated `port_bind` deployment succeeds
- **THEN** the backend marks the port binding `expanding`
- **AND** marks the VPC `expanding`

#### Scenario: Complete expansion validates host reachability

- **WHEN** a user completes VPC expansion with an expected host IP
- **THEN** the backend pings that host from the VPC gateway
- **AND** forces a display validation sync
- **AND** marks the expansion active only when both checks pass

### Requirement: Fabric Level VPC Operations

The SDN backend MUST expose VPC-level deployment and withdraw operations that expand one user action into per-device deployment records.

- `POST /api/sdn/vpcs/{vpc_id}/deploy` MUST create VPC `create` deployments for all target Leaf devices.
- `POST /api/sdn/vpcs/{vpc_id}/withdraw` MUST create `port_unbind` deployments before VPC `delete` deployments when active bindings exist.
- If `device_ids` is omitted, the backend MUST select default Leaf candidates.
- If `device_ids` is provided, the backend MUST use the explicit target list.
- `auto_apply` MUST default to `false`; the default behavior is plan generation, not device modification.

#### Scenario: Default VPC deploy expands to all Leaf devices

- **WHEN** a VPC deploy request omits `device_ids`
- **AND** two Leaf candidates exist
- **THEN** the backend creates one VPC `create` deployment per Leaf
- **AND** includes planned/pending port bindings for matching devices after each VPC `create` deployment

#### Scenario: VPC withdraw orders port unbind before delete

- **WHEN** a VPC withdraw request targets one device with one active port binding
- **THEN** the backend creates a `port_unbind` deployment first
- **AND** creates the VPC `delete` deployment after it
- **AND** records the delete deployment parent as the unbind deployment
