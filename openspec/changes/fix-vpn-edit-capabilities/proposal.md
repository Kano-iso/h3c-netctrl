# fix-vpn-edit-capabilities

## Why

v2.2 第一项 `interface-vpn-instance-and-l2-l3` 上线 + v2.2.1 patch 修完 UX bug 后，用户在 192.168.100.5 实测时发现 2 个**能力缺失**型 bug（与 v2.2.1 patch 修的 UX bug 不同，是新功能缺口）：

1. **bug 1（L2/L3 link type 不可调）**：前端接口表格展示 layer (L2/L3) 和 mode (access/trunk) 字段，但**没有提供"改 link type"的入口**。用户原话："为什么我不能调整呢？调整的话不就是改变一下它的这个 link 内容类型嘛，对吧？本质上也是下发配置"
2. **bug 2（三层接口不能配 IP）**：L3 接口表格展示 `ip_addresses` 字段，但**没有提供"加/改/删 IP"的入口**。用户原话："既然我们都可以去配置这些东西，为什么我们不能去配三层的 ip 呢，对吧？"

## What Changes

- **新后端能力**：
  - `PATCH /api/devices/{id}/interfaces/{if_index}/link-type` body `{"mode": "access"|"trunk", "force": bool}` — 调整 link type，**强制二次确认**告知会清空什么
  - `POST /api/devices/{id}/interfaces/{if_index}/ipv4-address` body `{"ip": "X.X.X.X", "mask": "Y.Y.Y.Y"}` — 给 L3 接口加 IP
  - `DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address` — 清空该接口所有 IP（清空而非单删是 H3C V7 IPV4ADDRESS 模型的实际行为：edit-config replace 整个 Ipv4Address 条目）
- **NETCONF 能力扩展**：
  - `netconf_xml.build_link_type_change_xml(if_index, new_mode, force=False)` — 调整 Ifmgr/Interfaces/Interface/LinkType
  - `netconf_xml.build_ipv4_address_set_xml(if_index, ip, mask)` — 设置/替换 IPV4ADDRESS/Ipv4Addresses/Ipv4Address
  - `netconf_xml.build_ipv4_address_clear_xml(if_index)` — 清空该接口 IP（xc:operation="delete"）
- **前端能力**：
  - `InterfaceConfigModal.vue`（或扩展 `Interfaces.vue` 现有 modal）加"link type"radio + "IP 地址"输入区
  - 改 link type 弹 `ConfirmModal` 二次确认，提示"会清空 X 现有 allowed-vlan / access-vlan"
  - 表格行加"改 IP"按钮（L3 接口才显示），弹 `Ipv4AddressEditModal` 增/删

## Capabilities

### New Capabilities
- `interface-vpn-instance-and-l2-l3`: 增加 link type 调整、IPv4 address 增/改/删能力

### Modified Capabilities
- `interface-vpn-instance-and-l2-l3`: 操作列增加"改 IP" / "改模式"按钮

## Impact

- **后端**：
  - `backend/app/utils/netconf_xml.py` — 新增 3 个 XML 构造函数
  - `backend/app/routers/interface.py` — 新增 3 个路由（PATCH link-type / POST ipv4-address / DELETE ipv4-address）
- **前端**：
  - `frontend/src/components/Ipv4AddressEditModal.vue`（新文件）— IP 编辑弹窗
  - `frontend/src/views/Interfaces.vue` — 表格行加"改 IP" / "改模式"按钮；接入新 modal
  - `frontend/src/api/index.js` — 加 3 个 API 方法
- **真机验证**：192.168.100.5（用户实测发现 bug 的设备）
- **不破坏**：`list_interfaces` / `list_vpn_instances` / `create_vpn_instance` / `delete_vpn_instance` / `bind_interface_vpn` / `unbind_interface_vpn` 端点（v2.2.1 patch 已 archive）
