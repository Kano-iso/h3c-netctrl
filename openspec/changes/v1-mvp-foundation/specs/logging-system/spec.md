## ADDED Requirements

### Requirement: Environment-variable controlled log level
The system SHALL read `LOG_LEVEL` from environment variables to control logging verbosity. Supported values: `INFO` (default) and `DEBUG`. The log level SHALL be configurable without code changes, only via environment variable.

#### Scenario: Default log level is INFO
- **WHEN** LOG_LEVEL environment variable is not set
- **THEN** the application logs at INFO level

#### Scenario: DEBUG level enabled
- **WHEN** LOG_LEVEL is set to "DEBUG"
- **THEN** the application logs at DEBUG level including NETCONF XML payloads

### Requirement: INFO level logging
At INFO level, the system SHALL log each operation action and result, including: operation type (query/create/update/delete), target (device/VLAN), and outcome (success/failure with reason).

#### Scenario: INFO log on VLAN creation
- **WHEN** a VLAN is successfully created
- **THEN** an INFO log entry records "VLAN创建成功: vlan_id=100, name=Office"

#### Scenario: INFO log on operation failure
- **WHEN** a VLAN operation fails
- **THEN** an INFO log entry records "VLAN操作失败: vlan_id=100, 原因=VLAN已存在"

### Requirement: DEBUG level NETCONF payload logging
At DEBUG level, the system SHALL log the complete NETCONF request XML and response XML for every RPC operation. Sensitive data (passwords) in the XML SHALL be masked with `***`.

#### Scenario: DEBUG log on get-config request
- **WHEN** a VLAN query is performed at DEBUG level
- **THEN** the complete get-config RPC request XML and response XML are logged

#### Scenario: DEBUG log on edit-config request
- **WHEN** a VLAN creation is performed at DEBUG level
- **THEN** the complete edit-config RPC request XML and response XML are logged

#### Scenario: Password masking in DEBUG logs
- **WHEN** a NETCONF request or response contains a password field
- **THEN** the password value is replaced with `***` in the log output

### Requirement: Error log with stack trace
The system SHALL log full stack traces for all exceptions at ERROR level, including the exception type, message, and complete traceback. This applies regardless of the LOG_LEVEL setting.

#### Scenario: Error log on unexpected exception
- **WHEN** an unhandled exception occurs during NETCONF communication
- **THEN** an ERROR log entry includes the full exception type, message, and stack trace

### Requirement: Log output destination
Logs SHALL be written to both stdout (for `docker-compose logs` viewing) and a log file mounted at `./logs/app.log` on the host machine.

#### Scenario: Logs visible via docker-compose
- **WHEN** developer runs `make logs`
- **THEN** recent application logs are displayed including NETCONF interaction details at DEBUG level

#### Scenario: Log file persistence
- **WHEN** the backend container writes log entries
- **THEN** the log file at `./logs/app.log` on the host machine contains the same entries
