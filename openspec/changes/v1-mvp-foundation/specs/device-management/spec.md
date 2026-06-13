## ADDED Requirements

### Requirement: Device data model
The system SHALL store device information in a SQLite `devices` table with fields: `id` (INTEGER primary key auto-increment), `name` (VARCHAR device alias), `host` (VARCHAR IP address), `port` (INTEGER, default 830), `username` (VARCHAR), `password_encrypted` (VARCHAR encrypted password), `created_at` (DATETIME), `updated_at` (DATETIME).

#### Scenario: Device record creation
- **WHEN** a new device is created with name "Spine-01", host "192.168.1.1", port 830, username "admin", password "admin123"
- **THEN** a record is inserted with auto-generated id, encrypted password, and current timestamps

### Requirement: Device CRUD API
The system SHALL provide REST API endpoints for device management:
- `GET /api/device` — return current device info
- `POST /api/device` — create device (only one device supported in V1.0)
- `PUT /api/device` — update device info
- All endpoints SHALL return the unified format `{success: bool, data?: object, error?: string}`

#### Scenario: Create device successfully
- **WHEN** POST /api/device is called with valid device parameters
- **THEN** response is `{success: true, data: {id, name, host, port, username, created_at, updated_at}}`

#### Scenario: Create device with missing required fields
- **WHEN** POST /api/device is called without host or username
- **THEN** response is `{success: false, error: "缺少必填字段: host"}`

#### Scenario: Get device info
- **WHEN** GET /api/device is called and a device exists
- **THEN** response contains device info without password_encrypted field

#### Scenario: Get device when none exists
- **WHEN** GET /api/device is called and no device is configured
- **THEN** response is `{success: true, data: null}`

### Requirement: Password encryption
The system SHALL encrypt device passwords using Fernet symmetric encryption before storing in the database. The encryption key SHALL be loaded from the `ENCRYPTION_KEY` environment variable. Decryption SHALL be used only when establishing NETCONF connections.

#### Scenario: Password is stored encrypted
- **WHEN** a device is created with password "admin123"
- **THEN** the `password_encrypted` field in the database does not contain the plaintext "admin123"

#### Scenario: Password decrypts correctly for connection
- **WHEN** the system needs to connect to a device
- **THEN** the encrypted password is decrypted to the original plaintext for NETCONF authentication

### Requirement: NETCONF connection test
The system SHALL provide `POST /api/device/test` endpoint that attempts to establish a NETCONF SSH session to the configured device and returns a precise error message if the connection fails.

#### Scenario: Successful connection test
- **WHEN** POST /api/device/test is called and the device is reachable with correct credentials
- **THEN** response is `{success: true, data: {message: "连接成功"}}`

#### Scenario: Connection refused
- **WHEN** the device host is reachable but NETCONF port (830) is not open
- **THEN** response is `{success: false, error: "连接被拒绝，请检查设备NETCONF服务是否开启（端口830）"}`

#### Scenario: Authentication failure
- **WHEN** the NETCONF port is open but username/password is incorrect
- **THEN** response is `{success: false, error: "认证失败，请检查用户名或密码"}`

#### Scenario: Host unreachable
- **WHEN** the device host IP is not reachable
- **THEN** response is `{success: false, error: "设备不可达，请检查IP地址和网络连通性"}`

#### Scenario: NETCONF session creation failure
- **WHEN** SSH connects but NETCONF hello/capabilities exchange fails
- **THEN** response is `{success: false, error: "NETCONF会话创建失败，请确认设备已启用NETCONF over SSH"}`

#### Scenario: No device configured
- **WHEN** POST /api/device/test is called but no device exists in the database
- **THEN** response is `{success: false, error: "未配置设备，请先添加设备信息"}`
