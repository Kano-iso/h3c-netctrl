## Why

下发 trunk 模式接口配置（创客/接口配置模块）持续失败。logs 表 action=interface_config 自 2026-06-23 17:47 起连续 5 条失败记录，错误均为：

> Unexpected element '...TrunkVLANs' under '/rpc/edit-config/.../Interface'

发起 change 时假设 H3C Comware 7 标准模型走 `VLAN/TrunkPorts/TrunkPort/PermitVlanList`。**经 H3C 官方文档 + 设备实地探测双重确认，该假设错误**：

- **H3C 官方文档**（12-网络管理和监控命令参考 R8336Pxx-6W100, h3c.com/cn/d_202509/2643258_30005_0.htm）：edit-config 范例**只配置 LinkType+PVID**，无 allowed_vlans 字段
- **设备实地探测**：试 10 个字段名（TrunkVlanList/PermitVlanList/TrunkVlanIDList/TaggedVlanList/VlanList/TrunkPermitVlan/AccessVlan/TagVlanList/TrunkAccessVlanList/TrunkVLANList）全部被 `Unexpected element ... under 'Interface'` 拒绝
- **VLAN 节点探测**：设备 VLAN 模块只有 AccessInterfaces/VLANs/MACPorts，无 TrunkPorts 节点

**结论**：当前 HCL 模拟器经 NETCONF edit-config **无法配置 trunk 允许 VLAN 列表**。原 `_build_interface_config_xml` 走 edit-config 路径从一开始方向就错了。

## What Changes

按用户决策（"先快解"），实施**显式拒绝 + 明确错误信息**：

- `backend/app/routers/interface.py::configure_interface` 在收到 `mode=trunk and allowed_vlans` 时，**不向设备发送任何 edit-config**，直接返回中文错误：
  ```
  当前设备不支持通过 NETCONF 配置 trunk 允许 VLAN 列表。
  请到设备 CLI 手工执行：port trunk permit vlan <vlan-list>
  ```
- access 模式（mode=access 或 trunk 不带 allowed_vlans）行为保持不变
- 写 `logs` 表记录 `status=failed error_message=<明确错误>`
- 失败时不计入"成功"统计，便于用户在 CMDB 看到完整失败记录

后续如果需要 trunk + allowed_vlans 真实落盘，将通过独立的 OpenSpec change 实施以下任一路径：
- SSH/CLI 路径下发 `port trunk permit vlan ...`
- 设备能力扩展（待 HCL 升级或换真机）

## Capabilities

### New Capabilities
- `interface-trunk-deploy`：trunk 模式接口的 NETCONF 下发能力（含 allowed_vlans 的设备能力边界处理）

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：`backend/app/routers/interface.py::configure_interface` 增加 6-10 行校验逻辑
- **API**：无破坏性变化，入参/出参结构不变；error 字段内容更具体
- **数据库**：无迁移
- **依赖**：无新增
- **回归**：access 模式未动，行为不变
- **运维**：trunk 用户看到明确错误指引（CLI 命令），不再困惑
