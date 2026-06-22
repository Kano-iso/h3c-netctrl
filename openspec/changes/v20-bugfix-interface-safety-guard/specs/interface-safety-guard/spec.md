## ADDED Requirements

### Requirement: Protected interfaces field on Device
The system SHALL allow users to mark specific interfaces as protected (cannot be configured without force flag).

#### Scenario: Default state
- **WHEN** a new device is created
- **THEN** protected_interfaces is empty list `[]`
- **AND** no interfaces are protected by default

#### Scenario: User sets protected interfaces
- **WHEN** user sets protected_interfaces to [1, 2, 3] via API
- **THEN** device record stores JSON list
- **AND** subsequent configurations targeting if_index 1/2/3 are blocked

### Requirement: Interface configuration protected check
The system SHALL check if if_index is protected before sending edit-config to device.

#### Scenario: Protected interface blocked
- **WHEN** user configures if_index 2 (which is in protected_interfaces)
- **AND** request body has force=false (default)
- **THEN** system returns error without sending edit-config
- **AND** error message: "接口 if_index=2 在保护列表中，禁止配置。如需配置请加 force=true 或先在设备管理中解除保护"

#### Scenario: Protected interface with force
- **WHEN** user configures if_index 2 (which is in protected)
- **AND** request body has force=true
- **THEN** system proceeds with edit-config
- **AND** log entry records force=true for audit

#### Scenario: Non-protected interface
- **WHEN** user configures if_index 10 (not in protected)
- **THEN** system proceeds normally without checking force

### Requirement: Frontend interface protection UI
The system SHALL provide a UI for users to manage protected interfaces per device.

#### Scenario: View protected list
- **WHEN** user opens device management page
- **THEN** user can see current protected_interfaces for each device

#### Scenario: Add protected interface
- **WHEN** user adds if_index to protected list
- **THEN** system saves the updated list
- **AND** subsequent configurations require force=true

#### Scenario: Remove protected interface
- **WHEN** user removes if_index from protected list
- **THEN** system saves the updated list
- **AND** subsequent configurations work normally

### Requirement: Frontend config confirmation
The system SHALL show confirmation dialog when configuring protected interface with force=true.

#### Scenario: User configures protected with force
- **WHEN** user tries to configure protected interface
- **AND** checks "force" checkbox
- **THEN** system shows confirmation dialog: "此接口在保护列表中，强制配置可能影响网络，确认继续？"

#### Scenario: User confirms
- **WHEN** user confirms
- **THEN** system sends request with force=true

#### Scenario: User cancels
- **WHEN** user cancels
- **THEN** request is not sent
