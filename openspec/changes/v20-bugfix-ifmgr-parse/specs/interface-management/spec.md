## MODIFIED Requirements

### Requirement: Interface list parser handles missing fields
The system SHALL parse H3C Ifmgr response correctly even when some Interface elements have only IfIndex (missing Name and LinkType).

#### Scenario: Interface with only IfIndex
- **WHEN** H3C Ifmgr response contains Interface element with only IfIndex and PVID
- **THEN** system includes this interface in the returned list
- **AND** uses IfIndex as the name (e.g., "If-2")
- **AND** defaults mode to "access"

#### Scenario: Interface with full fields
- **WHEN** H3C Ifmgr response contains Interface with all fields (IfIndex, Name, LinkType, PVID, TrunkVLANs)
- **THEN** system parses all fields as before

#### Scenario: All interfaces returned
- **WHEN** user queries interface list on real device
- **THEN** system returns at least one interface for each IfIndex in response
- **AND** empty data array is never returned when response has interfaces
