## Why

下发 trunk 模式接口配置（创客/接口配置模块）持续失败。报送日志（logs 表 action=interface_config）显示自 2026-06-23 17:47 起连续 5 条失败记录，错误信息一致：

> VLAN 错误: Unexpected element 'http://www.h3c.com/netconf/config:1.0':'TrunkVLANs' under element '/rpc/edit-config[1]/config[1]/top[1]/Ifmgr[1]/Interfaces[1]/Interface[1]

发起 change 时假设 H3C Comware 7 标准模型是 trunk 允许 VLAN 走 `VLAN/TrunkPorts/TrunkPort/PermitVlanList`。**经 H3C 官方文档 + 设备实地探测双重确认，该假设错误**：

### H3C 官方文档（12-网络管理和监控命令参考 R8336Pxx-6W100）

> 例如，用户下发 edit-config 操作，配置指定索引的端口为 Trunk 端口、PVID 为 VLAN 100：
> ```
> <IfIndex>1647</IfIndex>
> <LinkType>2</LinkType>
> <PVID>100</PVID>
> ```
> 来源：https://www.h3c.com/cn/d_202509/2643258_30005_0.htm

H3C 官方配置样例**只输出 LinkType + PVID**，没有 allowed_vlans 字段。

### 设备实地探测（Ifmgr/Interface 节点）

试了 10 个常见字段名，全部被设备 `Unexpected element ... under 'Interface'` 拒绝：
- TrunkVlanList / PermitVlanList / TrunkVlanIDList / TaggedVlanList / VlanList
- TrunkPermitVlan / AccessVlan / TagVlanList / TrunkAccessVlanList / TrunkVLANList

### 设备实地探测（VLAN 节点）

设备 VLAN 模块下只有 `AccessInterfaces` / `VLANs` / `MACPorts`，**没有 TrunkPorts 节点**。下发 `VLAN/TrunkPorts/TrunkPort/PermitVlanList` 报 `Unexpected element 'TrunkPorts' under element 'VLAN'`。

### 结论

当前设备（用户确认为 HCL 模拟器，H3C Cloud Lab）通过 NETCONF `edit-config` **无法配置 trunk 允许 VLAN 列表**：

- H3C V7 真实设备的 trunk 允许 VLAN 列表走专用 **action RPC**（不是 edit-config）
- HCL 模拟器进一步简化了 V7 模型，**根本不支持配置 trunk 允许 VLAN 列表**
- 当前 `_build_interface_config_xml` 走 edit-config 路径，**从一开始方向就错了**

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
