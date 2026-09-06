## MODIFIED Requirements

### Requirement: Fabric Level VPC Operations

The SDN backend MUST expose VPC-level deployment and withdraw operations that expand one user action into per-device deployment records.

- `POST /api/sdn/vpcs/{vpc_id}/deploy` MUST create VPC `create` deployments for all target EVPN Fabric devices.
- `POST /api/sdn/vpcs/{vpc_id}/withdraw` MUST create `port_unbind` deployments before VPC `delete` deployments when active bindings exist.
- If `device_ids` is omitted, the backend MUST select default EVPN Fabric candidates.
- If `device_ids` is provided, the backend MUST use the explicit target list only after validating that every target is an EVPN Fabric member.
- A device MUST be considered an EVPN Fabric member only when its trusted `sdn_role` is `evpn_leaf`.
- Device names, inferred model support, and `platform=LSTN/RSTN` MUST NOT be used as SDN/VPC target eligibility.
- `auto_apply` MUST default to `false`; the default behavior is pending change creation, not device modification.

#### Scenario: Default VPC deploy expands to all EVPN Fabric devices

- **WHEN** a VPC deploy request omits `device_ids`
- **AND** two EVPN Fabric candidates exist
- **AND** one access-only device name contains `Leaf` and has `platform=LSTN`
- **THEN** the backend creates one VPC `create` deployment per EVPN Fabric candidate
- **AND** excludes the access-only device
- **AND** includes planned/pending port bindings for matching EVPN Fabric devices after each VPC `create` deployment

#### Scenario: Explicit non-EVPN device is rejected

- **WHEN** a VPC deploy or withdraw request includes a device whose `sdn_role` is not `evpn_leaf`
- **THEN** the backend rejects the operation
- **AND** no deployment is created for that device
