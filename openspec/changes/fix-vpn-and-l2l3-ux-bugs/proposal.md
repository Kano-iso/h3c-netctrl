## Why

v2.2 第一项 `interface-vpn-instance-and-l2-l3` 在 192.168.100.4 真机验证时只跑了创建/查询/删除路径，bind/unbind 因设备只有 1 个 L3 接口（已绑 mgt）被标 N/A。用户切换到 192.168.100.5 实地使用后发现 4 个 UX bug，本 change 修其中最严重的 2 个：

1. **解绑预校验逻辑错误**（bug 4）：unbind 路由从设备拉接口 + VPN 绑定信息时，filter XML 实际上**只查了 Ifmgr 没查 L3vpn**，导致 `_parse_interface_response` 永远拿不到 `vpn_instance` 字段 → 后端误判"未绑定" → 用户看到"删除删除不掉就是解绑解绑不掉他会告诉我说现在已经没有vpn，但是实际上我是有的"。
2. **看不到现有 VPN 列表**（bug 3）：Interfaces.vue 上 "绑 VPN" 按钮（mode=bind）和 "+ VPN" 按钮（mode=create）共用一个 `VpnInstanceBindModal`，但 create 模式不显示 `existingVpns`，只让用户填新名字 → 用户在不知道设备已有 VPN 的情况下创建重名/冲突实例。

bug 1（L2/L3 不可调）和 bug 2（三层不能配 IP）涉及新增 IPV4ADDRESS edit-config 能力，工作量 2-3h，留作 v2.2.1 follow-up。

## What Changes

- **修 bug 4**：`build_interface_extended_filter_xml()` 改名/重写为"双模块查询"——分别拉 Ifmgr 和 L3vpn，合并 `vpn_by_idx` 后再调 `_parse_interface_response`；保证 unbind 预校验能读到 `target.vpn_instance`。
- **修 bug 3**：`VpnInstanceBindModal` 顶部新增"现有 VPN instance"section，**两种模式（create / bind）都显示**；create 模式下增加"或新建"折叠区，避免用户重复创建。
- **回归保险**：`list_vpn_instances` 端点已在 v2.2 第一项 archive 任务中真机验证通过，本次修改不破坏 list 行为。

## Capabilities

### New Capabilities
<!-- 无新增能力，纯 bug 修复 -->

### Modified Capabilities
<!-- v2.2 第一项的 VPN 能力 spec 已经在 openspec/specs/interface-vpn-instance-and-l2-l3/ -->
- `interface-vpn-instance-and-l2-l3`: unbind 预校验要求正确读到 vpn_instance；bind/create 流程要求用户可见现有 VPN 列表。

## Impact

- **后端**：
  - `backend/app/utils/netconf_xml.py` — `build_interface_extended_filter_xml` 改造（改名 + 双查询）
  - `backend/app/routers/interface.py` — `unbind_interface_vpn` 适配新 filter / 合并解析
- **前端**：
  - `frontend/src/components/VpnInstanceBindModal.vue` — 顶部加"现有 VPN 列表"section（两种模式都显示）
  - `frontend/src/views/Interfaces.vue` — 必要时调整 vpnInstances 加载时机
- **真机验证**：192.168.100.5（用户实测发现 bug 的设备，验证修复有效）
- **不影响**：`list_vpn_instances` / `create_vpn_instance` / `delete_vpn_instance` / `bind_interface_vpn` 端点（list 已 archive 验证通过，create/delete/bind 实测过）
