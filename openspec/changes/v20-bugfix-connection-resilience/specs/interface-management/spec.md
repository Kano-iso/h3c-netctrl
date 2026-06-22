## MODIFIED Requirements

### Requirement: VLAN pre-validation
The system SHALL validate VLAN exists on device before configuring access port.

#### Scenario: VLAN exists
- **WHEN** user configures access port with VLAN ID
- **AND** VLAN exists on device
- **THEN** system proceeds with interface configuration

#### Scenario: VLAN not exist
- **WHEN** user configures access port with VLAN ID
- **AND** VLAN does not exist on device
- **THEN** system returns error "VLAN {id} 不存在，请先创建"
- **AND** does NOT send edit-config to device

#### Scenario: Trunk with PVID not exist
- **WHEN** user configures trunk port with PVID
- **AND** PVID VLAN does not exist on device
- **THEN** system returns error "PVID {id} VLAN 不存在"
