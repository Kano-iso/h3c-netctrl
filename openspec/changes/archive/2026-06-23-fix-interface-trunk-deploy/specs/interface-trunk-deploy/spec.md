## ADDED Requirements

### Requirement: 后端显式拒绝 trunk 模式 + allowed_vlans 的接口配置

当后端收到 `POST /api/devices/{id}/interfaces/config` 请求中 `mode=trunk` 且 `allowed_vlans` 非空时，系统 MUST 直接返回明确的中文错误，**不向设备发送任何 edit-config**。access 模式（`mode=access` 或 `mode=trunk` 但 `allowed_vlans` 为空/None）行为保持不变。

错误信息 MUST 包含：
1. 设备不支持该操作的明确说明
2. CLI 手工配置命令样例（`port trunk permit vlan <vlan-list>`）

#### Scenario: 下发 trunk 接口（带 allowed_vlans）— 显式拒绝
- **WHEN** 调用 `POST /api/devices/{id}/interfaces/config`，`mode=trunk` 且 `allowed_vlans=[10,20,30]`
- **THEN** 后端不向设备发送任何 edit-config 调用，直接返回 `success=false`，`error` 字段包含中文错误信息（包含"该设备不支持通过 NETCONF 配置 trunk 允许 VLAN 列表"和 CLI 修复命令 `port trunk permit vlan 10,20,30`）；并向 `logs` 表写入 `action=interface_config status=failed error_message=<同上错误信息>`

#### Scenario: 下发 access 接口 — 行为不变
- **WHEN** 调用 `POST /api/devices/{id}/interfaces/config`，`mode=access`，`access_vlan=100`
- **THEN** 后端正常走 edit-config 路径，下发 `<IfIndex>...</IfIndex><LinkType>1</LinkType><PVID>100</PVID>`；设备返回 ok 则 `logs` 表写 `status=success`

#### Scenario: 下发 trunk 接口（不带 allowed_vlans）— 行为不变
- **WHEN** 调用 `POST /api/devices/{id}/interfaces/config`，`mode=trunk`，`allowed_vlans=null` 或 `[]`
- **THEN** 后端正常下发 LinkType=2，不输出 TrunkVLANs 元素（与原代码一致）
