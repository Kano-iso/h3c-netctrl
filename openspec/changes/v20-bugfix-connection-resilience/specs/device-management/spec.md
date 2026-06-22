## MODIFIED Requirements

### Requirement: Gradual device diagnosis
The system SHALL perform gradual network diagnosis before establishing NETCONF connection: ping → TCP port check → NETCONF.

#### Scenario: Device unreachable
- **WHEN** user attempts any device operation
- **AND** device does not respond to ping
- **THEN** system returns error "设备不可达，请检查 IP 地址和网络连通性"

#### Scenario: NETCONF port closed
- **WHEN** device responds to ping
- **AND** TCP port 830 is not open
- **THEN** system returns error "NETCONF 端口 830 未开放，请在设备上执行 netconf service enable"

#### Scenario: NETCONF port open
- **WHEN** device responds to ping and port 830 is open
- **THEN** system proceeds to NETCONF connection

### Requirement: NETCONF auto retry
The system SHALL retry NETCONF connection 2 times with exponential backoff (1s, 2s) on transient failures.

#### Scenario: First connection succeeds
- **WHEN** NETCONF connect succeeds on first attempt
- **THEN** no retry is performed

#### Scenario: Connection fails then succeeds
- **WHEN** first NETCONF connect fails
- **AND** second attempt succeeds (within 2 retries)
- **THEN** operation completes normally
- **AND** warning is logged

#### Scenario: All retries exhausted
- **WHEN** all 3 NETCONF connect attempts fail
- **THEN** system returns the last error with full context

### Requirement: Error classification
The system SHALL classify NETCONF errors into four categories with Chinese messages.

#### Scenario: Network error
- **WHEN** connection error is socket-level (refused, no route, timeout)
- **THEN** message is "设备不可达: {具体原因}"

#### Scenario: Authentication error
- **WHEN** SSH auth fails (AuthenticationException)
- **THEN** message is "认证失败: 请检查用户名密码"

#### Scenario: Protocol error
- **WHEN** NETCONF RPC returns error
- **THEN** message translates error code to readable Chinese

#### Scenario: Business error
- **WHEN** operation is valid but business rule fails (e.g., VLAN not exist)
- **THEN** message includes the device's specific error
