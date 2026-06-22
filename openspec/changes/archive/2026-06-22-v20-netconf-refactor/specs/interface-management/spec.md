## MODIFIED Requirements

### Requirement: Interface list query via NETCONF
The system SHALL query interface list using NETCONF get-config with Ifmgr filter, instead of SSH display command.

#### Scenario: Successful interface query
- **WHEN** user requests interface list for a device
- **THEN** system uses NETCONF get-config with Ifmgr/Interfaces filter
- **AND** returns interface name, IfIndex, link type, PVID, and status

#### Scenario: NETCONF query fails
- **WHEN** NETCONF get-config fails for interface query
- **THEN** system returns error with specific NETCONF error message
- **AND** records error_message in operation log

### Requirement: Interface configuration via NETCONF
The system SHALL configure interfaces using NETCONF edit-config with Ifmgr XML, instead of SSH commands.

#### Scenario: Configure access port
- **WHEN** user configures an interface as access mode with VLAN ID
- **THEN** system sends NETCONF edit-config with Ifmgr Interface XML (LinkType=1, PVID=vlan_id)
- **AND** returns success with no SSH login/logout on device

#### Scenario: Configure trunk port
- **WHEN** user configures an interface as trunk mode with allowed VLANs and PVID
- **THEN** system sends NETCONF edit-config with Ifmgr Interface XML (LinkType=2, TrunkVLANs, PVID)
- **AND** returns success with no SSH login/logout on device

#### Scenario: NETCONF config fails
- **WHEN** NETCONF edit-config returns RPC error
- **THEN** system returns error with translated Chinese message
- **AND** records error_message in operation log

## ADDED Requirements

### Requirement: DeviceDetail lazy loading
The system SHALL NOT automatically load interface list and asset info when entering DeviceDetail page.

#### Scenario: Enter device detail page
- **WHEN** user navigates to a device's detail page
- **THEN** system loads only device basic info and VLAN list
- **AND** interface list and asset info show "click refresh to load" state

#### Scenario: Manual refresh interfaces
- **WHEN** user clicks refresh button on interface section
- **THEN** system loads interface list via NETCONF

#### Scenario: Manual refresh asset
- **WHEN** user clicks refresh button on asset section
- **THEN** system loads asset info via SSH
