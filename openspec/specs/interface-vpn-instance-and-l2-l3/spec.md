# interface-vpn-instance-and-l2-l3 Specification

## Purpose

增强 H3C 设备接口管理能力：识别接口的二层 / 三层类型、展示 IP 地址与 VPN instance 绑定信息，并支持 VPN instance 的创建、删除以及接口与 VPN instance 的绑定 / 解绑。
## Requirements
### Requirement: 接口列表展示 L2/L3 + IP + VPN instance

`GET /api/devices/{id}/interfaces` 返回值中，每个接口对象 MUST 包含以下字段：

- `layer` (string, required): `"L2"` 或 `"L3"`
- `ip_addresses` (array of string): L3 接口的 IPv4/IPv6 地址列表（如 `["192.168.100.4/24"]`），L2 接口为空数组
- `vpn_instance` (string | null): 接口绑定的 VPN instance 名，未绑定为 `null`

**判定规则**（H3C V7 实际模型）：
1. 接口存在 IPv4 地址（IPV4ADDRESS 模块查询）→ `L3`
2. 接口绑了 VPN instance（L3vpn 模块查询）→ `L3`
3. 接口 `name` 以 `Vlan-interface` 开头 → `L3`
4. 接口 `name` 匹配子接口正则 `^.+\.\d+$` → `L3`
5. 其余情况 → `L2`

**数据源**（H3C V7 多模块合并查询）：
- Ifmgr：物理/子接口（L2 + 部分 L3）
- IPV4ADDRESS：L3 接口的 IP 地址
- L3vpn：VPN instance 定义 + 接口绑定

**兼容**：现有字段（`if_index` / `name` / `mode` / `pvid` / `allowed_vlans` / `status`）行为不变。

#### Scenario: 设备接口含 L2 和 L3 类型

- **WHEN** 设备上同时存在 L2 接口（如 GigabitEthernet0/0/1）和 L3 接口（如 Vlan-interface100 + IP 192.168.1.1/24）
- **THEN** 返回值中 `layer` 字段分别填 `"L2"` / `"L3"`
- **AND** L3 接口的 `ip_addresses` 包含 `["192.168.1.1/24"]`
- **AND** L2 接口的 `ip_addresses` 为 `[]`

### Requirement: VPN instance 列表

`GET /api/devices/{id}/vpn-instances` MUST 返回设备上所有 VPN instance 列表：

```json
{
  "success": true,
  "data": {
    "device_id": 4,
    "total": 2,
    "vpn_instances": [
      {
        "name": "mgt",
        "rd": "auto",
        "interfaces": [{"if_index": 5121, "name": "If-5121"}]
      }
    ]
  }
}
```

**数据源**：NETCONF get-config `<L3vpn>`（H3C V7 实际模型，**不**用 `<Ipv4Vrf>`）。

#### Scenario: 设备存在 N 个 VPN instance

- **WHEN** 设备上配置了 2 个 VPN instance（`mgt` 和 `MGMT`）
- **AND** 各自绑了不同接口
- **THEN** 返回 `vpn_instances` 长度为 2
- **AND** 每项的 `interfaces` 数组列出绑定的 if_index

### Requirement: 创建 VPN instance

`POST /api/devices/{id}/vpn-instances` MUST 创建 VPN instance：

- Request body: `{"name": "X", "rd": "auto"}`（rd 默认 "auto"）
- 成功：返回 `{"success": true, "data": {"name": "X", "rd": "auto"}}`
- 名称校验：仅允许字母、数字、下划线、连字符
- 失败：
  - 设备返回 RPC error → 400 + 中文错误信息（如 "VPN instance X 已存在"）
  - 设备不可达 → 503 + 中文错误信息

**实施**：NETCONF edit-config `<L3vpn><L3vpnVRF><VRF>...<VRF>X</VRF><DefaultRD>auto</DefaultRD>...</VRF></L3vpnVRF></L3vpn>`

#### Scenario: 创建合法名称的 VPN

- **WHEN** 调用 `POST /api/devices/5/vpn-instances` body `{"name": "TEST", "rd": "auto"}`
- **AND** 设备支持 L3vpn 模型
- **THEN** 返回 `{"success": true, "data": {"name": "TEST", "rd": "auto"}}`
- **AND** 设备上 `display ip vpn-instance` 可见 `TEST`

#### Scenario: 名称不合法被拦截

- **WHEN** 调用 `POST /api/devices/5/vpn-instances` body `{"name": "test vpn"}`（含空格）
- **THEN** 返回 `{"success": false, "error": "VPN instance 名只能包含字母、数字、下划线、连字符"}`

### Requirement: 删除 VPN instance（带预校验）

`DELETE /api/devices/{id}/vpn-instances/{name}` MUST 删除 VPN instance，**前置预校验**：

1. 查询设备上所有 VPN instance：不存在 → 400 "VPN instance {name} 不存在"
2. 查询该 VPN instance 当前绑定数：> 0 → 400 `{"success": false, "error": "VPN instance {name} 还有 N 个接口绑定（...），请先解绑"}`
3. 绑定数 = 0 → 执行删除 + `record_log`

**实施**：NETCONF edit-config，xc:operation="delete" 挂在外层 VRF 容器元素（H3C V7 要求，不能挂在内层 VRF name 元素）。

#### Scenario: 删除无绑定的 VPN

- **WHEN** VPN instance `TEST` 存在且绑定数 = 0
- **THEN** 调用 `DELETE /api/devices/5/vpn-instances/TEST` → success=True
- **AND** 设备 `display ip vpn-instance` 中 `TEST` 消失

#### Scenario: 有绑定时拒绝删除

- **WHEN** VPN instance `mgt` 绑定了 1 个接口（if_index=5121）
- **THEN** 调用 `DELETE /api/devices/5/vpn-instances/mgt` → success=False
- **AND** error 含 "还有 1 个接口绑定"

### Requirement: 接口绑 VPN instance

`POST /api/devices/{id}/interfaces/{if_index}/vpn-instance` body `{"name": "Y"}` MUST 将接口绑到 VPN instance：

- 受保护接口（device.protected_interfaces JSON 列表中）禁止 → 返回错误（与现有 access/trunk 护栏一致）
- 预校验：VPN instance 不存在 → 400 "VPN instance Y 不存在，请先创建"
- 设备约束：H3C V7 L3vpn/L3vpnIf/Bind 只接受 L3 接口；绑 L2 接口 → 设备返回 `The interface is not supported`，后端透传为中文错误
- 成功 → `record_log`

**实施**：NETCONF edit-config `<L3vpn><L3vpnIf><Bind><VRF>Y</VRF><IfIndex>N</IfIndex></Bind></L3vpnIf></L3vpn>`

#### Scenario: 成功绑定 L3 接口到 VPN

- **WHEN** 设备上有 VPN `TEST`（无绑定）
- **AND** L3 接口 5128（Vlan-interface100）无 VPN 绑定
- **THEN** `POST /api/devices/5/interfaces/5128/vpn-instance` body `{"name":"TEST"}` → success=True
- **AND** 设备 `display ip interface brief` 中 5128 显示 VPN 列 = `TEST`

### Requirement: 接口解绑 VPN instance

`DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance` MUST 解绑：

- 预校验：接口未绑定 → 400 "接口未绑定 VPN instance"
- **预校验数据源 MUST 包含 L3vpn 模块**：路由在判断 `target.vpn_instance` 之前，必须通过 `get_config` 拉取 L3vpn filter 并将 `vpn_by_idx` 合并到接口解析结果中——**不能**只依赖 Ifmgr 单模块查询
- 成功 → `record_log`

**实施**：NETCONF edit-config 移除 `L3vpnIf/Bind` 对应条目。

#### Scenario: 正确读取已绑 VPN 的接口

- **WHEN** 接口在设备上**已**绑定 VPN instance（如 L3vpn/Bind/IfIndex = N）
- **AND** 调用 `DELETE /api/devices/{id}/interfaces/N/vpn-instance`
- **THEN** 后端预校验必须正确读到 `target.vpn_instance` 不为 null
- **AND** 调用 NETCONF edit-config 删除 Bind
- **AND** 返回 `{"success": true, "data": {"if_index": N}}`

#### Scenario: 误判修复（之前会报"未绑定"）

- **WHEN** 接口在设备上**已**绑定 VPN instance
- **AND** 调用 unbind 路由
- **THEN** 后端**不**返回 "接口未绑定 VPN instance" 错误
- **AND** 设备的 L3vpnIf/Bind 条目被成功删除

### Requirement: 前端表格列扩展

`Interface.vue` 表格 MUST 增加：
- `layer` 列（badge）：二层（灰）/ 三层（蓝）
- `IP/VPN` 列（合并显示 IP 地址列表 + VPN instance 绑定名）
- `vpn_action` 列：操作按钮（"创建 VPN" / "绑 VPN" / "解绑"）

#### Scenario: 接口表格展示 L2/L3 + IP/VPN + 操作按钮

- **WHEN** 用户进入 `Interface.vue` 选中设备 5
- **THEN** 表格中每个接口有 `layer` 列（L2/L3 badge）、`IP/VPN` 列（IP 地址 + VPN 名称）、`操作` 列
- **AND** L3 接口 + 未绑 VPN 显示 "绑 VPN" + "+ VPN" 按钮
- **AND** L3 接口 + 已绑 VPN 显示 "解绑 VPN" 按钮

### Requirement: 前端联动 Modal

`frontend/src/components/VpnInstanceBindModal.vue` MUST 支持两种模式：
- 模式 1（create）：填写名称 → 创建 VPN → 自动绑定到当前接口
- 模式 2（bind）：从已有 VPN instance 列表选择 → 直接绑定
- **Modal 顶部 MUST 展示"现有 VPN instance"section**：
  - 列表项显示 name / rd / 绑定接口数
  - 两种模式（create / bind）下都显示
  - create 模式下，列表下方有"或新建"折叠区
  - 列表为空时显示"该设备尚无 VPN instance，请先创建"

所有写操作前 MUST 经过 `ConfirmModal` 二次确认。

#### Scenario: create 模式可见现有 VPN 列表

- **WHEN** 用户在 Interfaces.vue 上点击 L3 接口的 `+ VPN` 按钮
- **AND** 设备上已有 VPN instance（如 `mgt`）
- **THEN** Modal 顶部展示"现有 VPN instance"列表（含 `mgt` 等）
- **AND** 列表下方有"或新建"折叠区
- **AND** 用户可选择列表中的项直接绑定，或展开折叠区新建

#### Scenario: bind 模式可见现有 VPN 列表

- **WHEN** 用户在 Interfaces.vue 上点击 L3 接口的 `绑 VPN` 按钮
- **AND** 设备上有 N 个 VPN instance
- **THEN** Modal 展示全部 N 个 VPN instance 供选择
- **AND** 选中后点击"绑定"按钮

#### Scenario: 列表为空时引导用户

- **WHEN** 设备上**没有**任何 VPN instance
- **AND** 用户打开 Modal（create 或 bind 模式）
- **THEN** 列表区显示"该设备尚无 VPN instance，请先创建"
- **AND** create 模式下"或新建"折叠区默认展开

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

## Non-Functional

- **性能**：VPN instance 列表 / 接口列表查询 < 5s（单设备 1 次 NETCONF get-config 三模块合并）
- **可维护性**：XML 构造器独立 `utils/netconf_xml.py`，不与路由耦合
- **可观测性**：所有写操作 MUST `record_log`（vpn_instance_create / delete / bind / unbind）
- **错误处理**：NETCONF 错误经 `classify_netconf_error` 分类，连接错误和业务错误分别给出可读中文提示

## Out of Scope（v2.3 跟进）

- 设备能力探测与缓存（v2.2 假设 H3C V7 都支持 L3vpn 模型）
- NETCONF 失败降级走 SSH CLI（v2.2 直接透传 NETCONF 错误）
