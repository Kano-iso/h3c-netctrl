## ADDED Requirements

### Requirement: VLAN query
The system SHALL provide `GET /api/vlans` endpoint that retrieves all VLANs from the configured H3C device via NETCONF get-config. The response SHALL include VLAN ID and VLAN name for each entry.

#### Scenario: Successful VLAN query
- **WHEN** GET /api/vlans is called and the device is reachable
- **THEN** response is `{success: true, data: [{vlan_id: 1, name: "VLAN0001"}, {vlan_id: 100, name: "Office"}, ...]}`

#### Scenario: VLAN query with no device configured
- **WHEN** GET /api/vlans is called but no device exists in the database
- **THEN** response is `{success: false, error: "未配置设备，请先添加设备信息"}`

#### Scenario: VLAN query with connection failure
- **WHEN** GET /api/vlans is called but the device is unreachable
- **THEN** response is `{success: false, error: "设备连接失败: <具体原因>"}`

### Requirement: VLAN creation
The system SHALL provide `POST /api/vlans` endpoint that creates a new VLAN on the H3C device via NETCONF edit-config. The request body SHALL include `vlan_id` (integer 1-4094) and `name` (string).

#### Scenario: Successful VLAN creation
- **WHEN** POST /api/vlans is called with `{vlan_id: 100, name: "Office"}`
- **THEN** the VLAN is created on the device and response is `{success: true, data: {vlan_id: 100, name: "Office"}}`

#### Scenario: VLAN ID out of range
- **WHEN** POST /api/vlans is called with `vlan_id: 5000`
- **THEN** response is `{success: false, error: "VLAN ID必须在1-4094范围内"}`

#### Scenario: Duplicate VLAN ID
- **WHEN** POST /api/vlans is called with a vlan_id that already exists on the device
- **THEN** response is `{success: false, error: "VLAN 100已存在"}`

#### Scenario: Missing required fields
- **WHEN** POST /api/vlans is called without vlan_id or name
- **THEN** response is `{success: false, error: "缺少必填字段: vlan_id"}`

### Requirement: VLAN name modification
The system SHALL provide `PUT /api/vlans/{vlan_id}` endpoint that modifies the name of an existing VLAN on the H3C device via NETCONF edit-config. Only the VLAN name SHALL be modifiable.

#### Scenario: Successful VLAN name modification
- **WHEN** PUT /api/vlans/100 is called with `{name: "NewOffice"}`
- **THEN** the VLAN name is updated on the device and response is `{success: true, data: {vlan_id: 100, name: "NewOffice"}}`

#### Scenario: Modify non-existent VLAN
- **WHEN** PUT /api/vlans/999 is called but VLAN 999 does not exist on the device
- **THEN** response is `{success: false, error: "VLAN 999不存在"}`

#### Scenario: Modify VLAN without name
- **WHEN** PUT /api/vlans/100 is called without the name field
- **THEN** response is `{success: false, error: "缺少必填字段: name"}`

### Requirement: VLAN deletion
The system SHALL provide `DELETE /api/vlans/{vlan_id}` endpoint that deletes a VLAN from the H3C device via NETCONF edit-config.

#### Scenario: Successful VLAN deletion
- **WHEN** DELETE /api/vlans/100 is called and VLAN 100 exists on the device
- **THEN** the VLAN is removed from the device and response is `{success: true, data: {message: "VLAN 100已删除"}}`

#### Scenario: Delete non-existent VLAN
- **WHEN** DELETE /api/vlans/999 is called but VLAN 999 does not exist on the device
- **THEN** response is `{success: false, error: "VLAN 999不存在"}`

### Requirement: NETCONF XML compatibility with H3C
All VLAN operations SHALL use H3C-compatible NETCONF XML namespace and structure. The system SHALL construct correct RPC payloads for H3C devices, using the appropriate YANG module namespace for VLAN configuration.

#### Scenario: get-config returns H3C VLAN data
- **WHEN** a NETCONF get-config request is sent to an H3C device
- **THEN** the response XML is correctly parsed to extract VLAN ID and name fields

#### Scenario: edit-config creates VLAN on H3C
- **WHEN** a NETCONF edit-config request is sent to create VLAN 100 named "Office"
- **THEN** the H3C device accepts the configuration and the VLAN appears in subsequent get-config queries

### Requirement: Unified error handling for VLAN operations
All VLAN API errors (device connection failure, NETCONF RPC error, device rejection) SHALL be caught and returned as readable Chinese error messages in the unified response format. The system SHALL NOT return raw 500 errors or stack traces to the frontend.

#### Scenario: Device returns NETCONF error during VLAN creation
- **WHEN** the H3C device rejects an edit-config operation
- **THEN** response is `{success: false, error: "设备返回错误: <H3C错误描述的中文翻译>"}`

#### Scenario: NETCONF session timeout
- **WHEN** a VLAN operation times out waiting for device response
- **THEN** response is `{success: false, error: "设备响应超时，请检查网络连接或设备状态"}`
