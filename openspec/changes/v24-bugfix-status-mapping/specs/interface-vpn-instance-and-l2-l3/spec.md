## ADDED Requirements

### Requirement: 接口 status 字段正确反映 H3C V7 链路层状态

`GET /api/devices/{id}/interfaces` 返回值中每个接口对象的 `status` 字段 MUST 正确反映 H3C V7 Ifmgr 的 `<OperStatus>` 链路层状态：

- **H3C V7 / IF-MIB (RFC 2863) 编码**：`AdminStatus` 与 `OperStatus` 都是 **1=UP, 2=DOWN**（3=testing, 4=unknown, 5=dormant, 6=notPresent, 7=lowerLayerDown）。
- **status 字段优先级**：`OperStatus` 优先（链路层是用户真正关心的"通没通"），`AdminStatus` 兜底（仅当 OperStatus 缺失时使用）。
- **admin_status 字段**：始终反映 `AdminStatus`（1=up, 2=down），独立于 status，**不**被 OperStatus 覆盖。
- **oper_status 字段**：始终反映 `OperStatus`（1=up, 2=down），缺失时为 "unknown"。
- **兜底值**：OperStatus 取 3/4/5/6/7 等非 1/2 值时，oper_status 兜底为 "down"（保守处理，H3C V7 实际不返这些值）。

#### Scenario: UP 链路 status=up

- **WHEN** H3C V7 设备 Ifmgr 返回 `<OperStatus>1</OperStatus>` 且 `<ActualSpeed>1000000</ActualSpeed>`（1Gbps 链路）
- **THEN** API 返回的 `status` = "up"
- **AND** `oper_status` = "up"
- **AND** `admin_status` = "up"（AdminStatus 也为 1 时）

#### Scenario: DOWN 链路 status=down

- **WHEN** H3C V7 设备 Ifmgr 返回 `<OperStatus>2</OperStatus>` 且 `<ActualSpeed>` 缺失或为 0
- **THEN** API 返回的 `status` = "down"
- **AND** `oper_status` = "down"

#### Scenario: admin shutdown 但链路激活 → status=up

- **WHEN** H3C V7 设备 Ifmgr 返回 `<AdminStatus>2</AdminStatus>` (admin shutdown) 但 `<OperStatus>1</OperStatus>` (链路仍 up)
- **THEN** API 返回的 `status` = "up"（优先看链路层）
- **AND** `admin_status` = "down"（admin 字段独立反映）

#### Scenario: OperStatus 缺失 admin_status 兜底

- **WHEN** H3C V7 设备 Ifmgr 返回 `<AdminStatus>1</AdminStatus>` 但 `<OperStatus>` 缺失
- **THEN** API 返回的 `status` = "up"（admin 兜底）
- **AND** `oper_status` = "unknown"（缺失）
