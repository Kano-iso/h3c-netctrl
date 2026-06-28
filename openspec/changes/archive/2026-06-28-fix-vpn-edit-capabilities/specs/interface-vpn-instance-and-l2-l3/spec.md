# interface-vpn-instance-and-l2-l3 Specification (Delta)

## Purpose

修复 v2.2 第一项 + v2.2.1 patch 上线后发现的 2 个能力缺失型 bug：
1. L2/L3 link type 不可调
2. 三层接口不能配 IP

## ADDED Requirements

### Requirement: 调整接口 link type (mode)

`PATCH /api/devices/{id}/interfaces/{if_index}/link-type` MUST 调整接口的 link type (mode)：

- Request body: `{"mode": "access" | "trunk", "force": bool}`（`force=false` 默认）
- 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝，`force=true` 时允许
- **破坏性操作必须二次确认**：H3C V7 实际行为下，mode 切换会清空该接口已有配置：
  - `access → trunk`：清空 `access_vlan`
  - `trunk → access`：清空 `allowed_vlans`（前端会丢失信息，但设备 NETCONF 配置层面的 trunk allowed VLAN 已确认不支持走 NETCONF，见 `fix-interface-trunk-deploy`）
  - `trunk → access` 同时清空 `pvid`
- 后端**不**做"会清空什么"的预测，**强制**前端展示当前 mode + 新 mode 时的差异，让用户自己确认
- 预校验：mode 必须是 "access" 或 "trunk"，否则 400
- 失败：
  - 设备返回 RPC error → 400 + 中文错误信息（透传 classify_netconf_error）
  - 设备不可达 → 503 + 中文错误信息
- 成功 → `record_log`

**实施**：NETCONF edit-config `<Ifmgr><Interfaces><Interface><IfIndex>N</IfIndex><LinkType>1|2|3</LinkType></Interface></Interfaces></Ifmgr>`

#### Scenario: access 改 trunk 成功

- **WHEN** 接口当前 mode=access，PVID=100（access_vlan）
- **AND** 用户在二次确认弹窗中确认（已知 access_vlan 会被清空）
- **THEN** `PATCH /api/devices/5/interfaces/5123/link-type` body `{"mode":"trunk","force":false}` → success=True
- **AND** 设备 `display current-configuration interface 5123` 中 mode 切换为 trunk
- **AND** 原 access_vlan 在接口下消失

#### Scenario: 受保护接口不带 force 被拒绝

- **WHEN** 接口 if_index=5121 在 device.protected_interfaces 中
- **AND** 调用 `PATCH /api/devices/5/interfaces/5121/link-type` body `{"mode":"trunk","force":false}`
- **THEN** 返回 `{"success": false, "error": "接口 if_index=5121 是受保护口，需要 force=true 才能继续"}`

#### Scenario: mode 非法值被拦截

- **WHEN** 调用 `PATCH /api/devices/5/interfaces/5123/link-type` body `{"mode":"hybrid"}`
- **THEN** 返回 `{"success": false, "error": "mode 必须是 access 或 trunk"}`（Pydantic Literal 校验失败）

### Requirement: 设置/替换 L3 接口 IPv4 地址

`POST /api/devices/{id}/interfaces/{if_index}/ipv4-address` MUST 给 L3 接口设置/替换 IPv4 地址：

- Request body: `{"ip": "X.X.X.X", "mask": "Y.Y.Y.Y"}`（点分十进制 + 点分十进制 mask）
- **layer=L3 校验**：接口不是 L3（无 IP 也无 VPN 也非 Vlan-interface 非子接口）→ 400 "该接口不是 L3 接口，无法配置 IP"
- 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝
- **IP/mask 格式校验**：
  - ip 必须是 4 段点分十进制，每段 0-255
  - mask 必须是 4 段点分十进制，连续 1 后跟连续 0（如 255.255.255.0 合法，255.0.255.0 非法）
- **clear + set 模式**：H3C V7 IPV4ADDRESS 模型下，set 不会自动清空原条目，所以后端先发 delete 再发 create（两步 edit-config）
- 失败：
  - 设备返回 RPC error → 400 + 中文错误信息
  - 设备不可达 → 503 + 中文错误信息
- 成功 → `record_log`

**实施**：NETCONF edit-config（两步）
1. 清空：`xc:operation="delete"` <IPV4ADDRESS><Ipv4Addresses><Ipv4Address><IfIndex>N</IfIndex></Ipv4Address></Ipv4Addresses></IPV4ADDRESS>
2. 设置：<IPV4ADDRESS><Ipv4Addresses><Ipv4Address><IfIndex>N</IfIndex><Ipv4Address>X</Ipv4Address><Ipv4Mask>Y</Ipv4Mask></Ipv4Address></Ipv4Addresses></IPV4ADDRESS>

#### Scenario: L3 接口成功配 IP

- **WHEN** 接口 if_index=5121 是 L3 接口（Vlan-interface100，无 IP）
- **AND** device.protected_interfaces 不含 5121
- **THEN** `POST /api/devices/5/interfaces/5121/ipv4-address` body `{"ip":"192.168.1.1","mask":"255.255.255.0"}` → success=True
- **AND** 设备 `display ip interface brief | include Vlan100` 显示 IP=192.168.1.1/24

#### Scenario: L2 接口配 IP 被拒绝

- **WHEN** 接口 if_index=5123 是 L2 接口（access mode）
- **THEN** `POST /api/devices/5/interfaces/5123/ipv4-address` body `{"ip":"10.0.0.1","mask":"255.255.255.0"}` → success=False
- **AND** error 含 "不是 L3 接口"

#### Scenario: mask 非法被拦截

- **WHEN** 调用 `POST` body `{"ip":"10.0.0.1","mask":"255.0.255.0"}`（非连续 1）
- **THEN** 返回 `{"success": false, "error": "mask 格式非法，必须是连续 1 后跟连续 0（如 255.255.255.0）"}`

#### Scenario: 替换已有 IP（clear + set）

- **WHEN** 接口 5121 已有 IP 192.168.1.1/24
- **AND** 调用 `POST /api/devices/5/interfaces/5121/ipv4-address` body `{"ip":"10.0.0.1","mask":"255.255.255.0"}`
- **THEN** 后端先发 delete 清空 5121 的 Ipv4Address，再发 create 新 IP
- **AND** 设备 `display ip interface brief` 中 5121 只显示新 IP 10.0.0.1/24
- **AND** 旧 IP 192.168.1.1/24 已消失

### Requirement: 清空 L3 接口所有 IPv4 地址

`DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address` MUST 清空 L3 接口的所有 IPv4 地址：

- **layer=L3 校验**：接口不是 L3 → 400
- 受保护接口护栏：device.protected_interfaces 中的接口默认拒绝
- **不**做"会清空什么"的预校验，直接发 delete
- 成功 → `record_log`

**实施**：NETCONF edit-config `<IPV4ADDRESS xmlns:xc="..."><Ipv4Addresses><Ipv4Address xc:operation="delete"><IfIndex>N</IfIndex></Ipv4Address></Ipv4Addresses></IPV4ADDRESS>`

#### Scenario: 清空已有 IP

- **WHEN** 接口 5121 有 IP 192.168.1.1/24
- **THEN** `DELETE /api/devices/5/interfaces/5121/ipv4-address` → success=True
- **AND** 设备 `display ip interface brief` 中 5121 无 IP

#### Scenario: 没有任何 IP 的接口清空

- **WHEN** 接口 5121 是 L3 但无 IP
- **THEN** `DELETE` → success=True（无操作）

### Requirement: 前端编辑 UI

`frontend/src/views/Interfaces.vue` 表格行 MUST 增加：

- L3 接口 → "改 IP" 按钮（弹 `Ipv4AddressEditModal`）
- L2 接口 → "改模式" 按钮（弹 `ConfirmModal` 二次确认，强制让用户确认会清空什么）

`frontend/src/components/Ipv4AddressEditModal.vue` MUST：

- 顶部展示接口名 + if_index
- 中间展示当前 IP 列表（如果有）
- 下方输入框（新 IP + mask）+ "应用" 按钮
- 单独 "清空所有 IP" 按钮（带二次确认）
- 所有写操作前 MUST 经过 `ConfirmModal` 二次确认

`Interfaces.vue` 改 link type 二次确认弹窗 MUST 展示：

- 当前 mode + 当前 mode 下的字段（access_vlan / pvid / allowed_vlans）
- 新 mode
- 固定提示文字："切换后会清空 {新 mode 不需要的字段}"

#### Scenario: L3 接口点改 IP 弹窗

- **WHEN** 用户在 Interfaces.vue 选 192.168.100.5 + L3 接口 5121
- **AND** 点击 "改 IP" 按钮
- **THEN** 弹出 `Ipv4AddressEditModal`
- **AND** 顶部展示 "Vlan-interface100 #5121"
- **AND** 中间展示当前 IP 列表（"192.168.1.1/24"）
- **AND** 输入框预填当前 IP

#### Scenario: L2 接口点改模式二次确认

- **WHEN** 用户在 Interfaces.vue 选 192.168.100.5 + L2 接口 5123（mode=access）
- **AND** 点击 "改模式" 按钮
- **THEN** 弹出 `ConfirmModal`
- **AND** 展示"当前 mode: access (PVID 100)；新 mode: trunk；切换后会清空 access_vlan"
- **AND** 用户确认后调 PATCH `/api/devices/5/interfaces/5123/link-type` body `{"mode":"trunk","force":false}`

## Non-Functional

- **可观测性**：所有写操作 MUST `record_log`（link_type_change / ipv4_address_set / ipv4_address_clear）
- **错误处理**：NETCONF 错误经 `classify_netconf_error` 分类，连接错误和业务错误分别给出可读中文提示
- **原子性**：clear + set 模式下两步 edit-config 间隔 < 1s，设备层面无中间态

## Out of Scope（v2.3 跟进）

- IPv6 配置
- 子接口批量改 IP
- mask 前缀写法（/24）
- 单 IP 单删（v2.2 范围只做"清空所有"）
- hybrid mode 切换
