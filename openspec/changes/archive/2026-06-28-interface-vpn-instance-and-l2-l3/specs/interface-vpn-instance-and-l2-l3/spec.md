# Spec: interface-vpn-instance-and-l2-l3

## Purpose

增强接口管理能力：识别接口的二层 / 三层类型、展示 IP 地址与 VPN instance 绑定，并支持 VPN instance 的创建、删除以及接口与 VPN instance 的绑定 / 解绑。

## Requirements

### REQ-1: 接口列表展示 L2/L3 + IP + VPN instance

**系统 SHALL** 在 `GET /api/devices/{id}/interfaces` 返回值中，每个接口对象包含以下字段：

- `layer` (string, required): `"L2"` 或 `"L3"`
- `ip_addresses` (array of string): L3 接口的 IPv4/IPv6 地址列表（如 `["192.168.100.4/24"]`），L2 接口为空数组
- `vpn_instance` (string | null): 接口绑定的 VPN instance 名，未绑定为 `null`

**判定规则**：
1. 接口 `name` 以 `Vlan-interface` 开头 → `L3`
2. 接口存在 `Ipv4Address` 子元素（NETCONF 解析）且非空 → `L3`
3. 接口 `name` 匹配正则 `^.+\.\d+$`（子接口）→ `L3`
4. 其余情况 → `L2`

**兼容**：现有字段（`if_index` / `name` / `mode` / `pvid` / `allowed_vlans` / `status`）行为不变。

### REQ-2: VPN instance 列表

`GET /api/devices/{id}/vpn-instances` SHALL 返回设备上所有 VPN instance 列表：

```json
{
  "success": true,
  "data": {
    "vpn_instances": [
      { "name": "MGMT", "interfaces": ["M-GigabitEthernet0/0/0"], "rd": "auto" }
    ]
  }
}
```

**数据源**：NETCONF get-config `<Ipv4Vrf>`（优先），失败则 SSH CLI `display ip vpn-instance`（fallback）。

### REQ-3: 创建 VPN instance

`POST /api/devices/{id}/vpn-instances` SHALL 创建 VPN instance：

- Request body: `{"name": "X", "rd": "auto"}`（rd 默认 "auto"，可显式指定如 `"100:1"`）
- 成功：返回 `{"success": true, "data": {"name": "X"}}`
- 失败：
  - 设备返回 RPC error → 400 + 中文错误信息（如 "VPN instance 已存在"）
  - 设备不可达 → 503 + 中文错误信息
- 实施：NETCONF edit-config `<Ipv4Vrf><VRF><Name>X</Name><DefaultRD>auto</DefaultRD></VRF></Ipv4Vrf>` 优先，失败 fallback SSH CLI `system-view; ip vpn-instance X; route-distinguisher auto`

### REQ-4: 删除 VPN instance（带预校验）

`DELETE /api/devices/{id}/vpn-instances/{name}` SHALL 删除 VPN instance，**前置预校验**：

- 查询该 VPN instance 当前绑定数
- 绑定数 > 0 → 返回 400 `{"success": false, "error": "VPN instance {name} 还有 N 个接口绑定，请先解绑"}`
- 绑定数 = 0 → 执行删除 + record_log

**实施**：NETCONF delete-config `<Ipv4Vrf><VRF><Name>X</Name></VRF></Ipv4Vrf>` 优先，失败 fallback SSH CLI `system-view; undo ip vpn-instance X`。

### REQ-5: 接口绑 VPN instance

`POST /api/devices/{id}/interfaces/{if_index}/vpn-instance` body `{"name": "MGMT"}` SHALL 将接口绑到 VPN instance：

- 受保护接口（device.protected_interfaces JSON 列表中）禁止 → 返回 403（与现有 access/trunk 护栏一致）
- 设备不可达 → 503
- 实施：NETCONF edit-config `<Ifmgr><Interfaces><Interface><IfIndex>N</IfIndex><IpBindVrfInstance>Y</IpBindVrfInstance></Interface></Interfaces></Ifmgr>` 优先，失败 fallback SSH CLI

### REQ-6: 接口解绑 VPN instance

`DELETE /api/devices/{id}/interfaces/{if_index}/vpn-instance` SHALL 解绑：

- 未绑定 → 400 "接口未绑定 VPN instance"
- 成功 → record_log
- 实施：NETCONF delete-config + SSH CLI `undo ip binding vpn-instance` fallback

### REQ-7: 设备能力探测与降级

**系统 SHALL** 在第一次调用 VPN instance 端点时探测设备 NETCONF 能力：

- 探测动作：NETCONF get-config `<Ipv4Vrf>` 试取
- 缓存：进程内 dict（key=device_id），重启重测
- 降级：探测失败 → 标记该设备走 SSH CLI 模式
- UI 提示：降级模式下，前端接口列表的 `vpn_instance` 字段值可能滞后（标注 "SSH 模式，最新状态以设备为准"）

### REQ-8: 前端表格列扩展

`Interface.vue` 表格 SHALL 增加 3 列：

- `layer` (badge)：二层（灰）/ 三层（蓝）
- `ip` (text)：L3 显示 IP，L2 显示 "-"
- `vpn_instance` (text)：显示绑定名，nullable 显 "-"

### REQ-9: 前端联动配置

`Interface.vue` 行操作列 SHALL 增加按钮（仅 L3 接口 / 物理口可操作）：

- "创建 VPN" 按钮：弹 `VpnInstanceBindModal`（模式 1：创建 + 绑定）
- "绑 VPN" 按钮：弹 `VpnInstanceBindModal`（模式 2：仅绑定）
- 已绑 VPN 的接口显示 "解绑" 按钮 + 二次确认

所有写操作前 MUST 经过 `ConfirmModal` 二次确认，显示目标操作前后的关键信息。

## Non-Functional

- **性能**：VPN instance 列表 / 接口列表查询 < 5s（单设备 1 次 NETCONF get-config）
- **可靠性**：NETCONF 失败 → SSH fallback；SSH 失败 → 返回明确错误
- **可维护性**：XML 构造器独立 `utils/netconf_xml.py`，不与路由耦合
- **可观测性**：所有写操作 MUST `record_log`
