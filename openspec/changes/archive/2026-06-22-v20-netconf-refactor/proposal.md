## Why

接口管理（查询+配置）当前使用 SSH (paramiko) 实现，存在两个问题：
1. `port link-mode bridge` 命令在已是二层模式的接口上报 Wrong parameter，导致配置失败
2. 每次 API 请求都新建 SSH 连接，交换机日志中产生大量登录/登出记录

项目初衷是使用 NETCONF 进行设备管理（VLAN 操作已用 NETCONF 实现），接口管理也应统一使用 NETCONF，既符合大厂实践，又能避免 SSH 命令兼容性问题。

## What Changes

- 接口列表查询从 SSH `display interface brief` 改为 NETCONF `get-config` + Ifmgr filter
- 接口配置下发从 SSH `execute_commands` 改为 NETCONF `edit-config` + Ifmgr XML
- 移除 `port link-mode bridge` 命令（NETCONF 方式不存在此问题）
- DeviceDetail 页面进入时不再自动加载接口列表和资产信息，改为手动刷新（减少连接频率）

## Capabilities

### New Capabilities

（无新增能力）

### Modified Capabilities

- `interface-management`: 查询和配置从 SSH 改为 NETCONF 实现

## Impact

- 后端：interface.py 路由重写（SSH → NETCONF），netconf_client.py 可能需新增方法
- 前端：DeviceDetail.vue 去掉 onMounted 自动加载接口/资产
- SSH 连接频率大幅降低，仅运维终端和资产采集使用 SSH
