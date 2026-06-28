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

### Requirement: 创建 VPN instance

`POST /api/devices/{id}/vpn-instances` MUST 创建 VPN instance：

- Request body: `{"name": "X", "rd": "auto"}`（rd 默认 "auto"）
- 成功：返回 `{"success": true, "data": {"name": "X", "rd": "auto"}}`
- 名称校验：仅允许字母、数字、下划线、连字符
- 失败：
  - 设备返回 RPC error → 400 + 中文错误信息（如 "VPN instance X 已存在"）
  - 设备不可达 → 503 + 中文错误信息

**实施**：NETCONF edit-config `<L3vpn><L3vpnVRF><VRF>...<VRF>X</VRF><DefaultRD>auto</DefaultRD>...</VRF></L3vpnVRF></L3vpn>`

### Requirement: 删除 VPN instance（带预校验）

`DELETE /api/devices/{id}/vpn-instances/{name}` MUST 删除 VPN instance，**前置预校验**：

1. 查询设备上所有 VPN instance：不存在 → 400 "VPN instance {name} 不存在"
2. 查询该 VPN instance 当前绑定数：> 0 → 400 `{"success": false, "error": "VPN instance {name} 还有 N 个接口绑定（...），请先解绑"}`
3. 绑定数 = 0 → 执行删除 + `record_log`

**实施**：NETCONF edit-config，xc:operation="delete" 挂在外层 VRF 容器元素（H3C V7 要求，不能挂在内层 VRF name 元素）。

### Requirement: 接口绑 VPN instance

`POST /api/devices/{id}/interfaces/{if_index}/vpn-instance` body `{"name": "Y"}` MUST 将接口绑到 VPN instance：

- 受保护接口（device.protected_interfaces JSON 列表中）禁止 → 返回错误（与现有 access/trunk 护栏一致）
- 预校验：VPN instance 不存在 → 400 "VPN instance Y 不存在，请先创建"
- 设备约束：H3C V7 L3vpn/L3vpnIf/Bind 只接受 L3 接口；绑 L2 接口 → 设备返回 `The interface is not supported`，后端透传为中文错误
- 成功 → `record_log`

**实施**：NETCONF edit-config `<L3vpn><L3vpnIf><Bind><VRF>Y</VRF><IfIndex>N</IfIndex></Bind></L3vpnIf></L3vpn>`

### Requirement: 接口解绑 VPN instance

`DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance` MUST 解绑：

- 预校验：接口未绑定 → 400 "接口未绑定 VPN instance"
- 成功 → `record_log`

**实施**：NETCONF edit-config 移除 `L3vpnIf/Bind` 对应条目。

### Requirement: 前端表格列扩展

`Interface.vue` 表格 MUST 增加：
- `layer` 列（badge）：二层（灰）/ 三层（蓝）
- `IP/VPN` 列（合并显示 IP 地址列表 + VPN instance 绑定名）
- `vpn_action` 列：操作按钮（"创建 VPN" / "绑 VPN" / "解绑"）

### Requirement: 前端联动 Modal

`frontend/src/components/VpnInstanceBindModal.vue` MUST 支持两种模式：
- 模式 1（create）：填写名称 → 创建 VPN → 自动绑定到当前接口
- 模式 2（bind）：从已有 VPN instance 列表选择 → 直接绑定

所有写操作前 MUST 经过 `ConfirmModal` 二次确认。

## Non-Functional

- **性能**：VPN instance 列表 / 接口列表查询 < 5s（单设备 1 次 NETCONF get-config 三模块合并）
- **可维护性**：XML 构造器独立 `utils/netconf_xml.py`，不与路由耦合
- **可观测性**：所有写操作 MUST `record_log`（vpn_instance_create / delete / bind / unbind）
- **错误处理**：NETCONF 错误经 `classify_netconf_error` 分类，连接错误和业务错误分别给出可读中文提示

## Out of Scope（v2.3 跟进）

- 设备能力探测与缓存（v2.2 假设 H3C V7 都支持 L3vpn 模型）
- NETCONF 失败降级走 SSH CLI（v2.2 直接透传 NETCONF 错误）
